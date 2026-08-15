import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from forge_controller.capabilities import CapabilityDenied, CapabilityPolicy, issue_grant
from forge_controller.capability_envelope import seal_grant
from forge_controller.github_broker import (
    GitHubBrokerError,
    GitHubPullRequestRequest,
    GitHubPullRequestResult,
    GitHubPushRequest,
    GitHubPushResult,
)
from forge_controller.github_broker_service import (
    RootOwnedWorkspaceRegistry,
    create_github_broker_app,
)

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 8, 15, 23, 15, tzinfo=UTC)
KEY = b"s" * 32
RESOURCE = "zebadee2kk/hermes-dev-team-vm"
BRANCH = "forge/task-123"
HEAD = "a" * 40


class FakeDispatcher:
    def __init__(self) -> None:
        self.push_calls = 0
        self.pr_calls = 0
        self.deny = False

    def push_task_branch(self, envelope, request):
        self.push_calls += 1
        if self.deny:
            raise CapabilityDenied("denied by test")
        return GitHubPushResult(
            repository=request.resource,
            branch=request.branch,
            head_sha=request.expected_head,
            remote_verified=True,
        )

    def create_pull_request(self, envelope, request):
        self.pr_calls += 1
        return GitHubPullRequestResult(
            repository=request.resource,
            number=7,
            url=f"https://github.com/{request.resource}/pull/7",
            head_branch=request.branch,
            head_sha=request.expected_head,
            base_branch="main",
            draft=request.draft,
        )


def _envelope():
    policy = CapabilityPolicy.load(ROOT / "config/capability-policy.yaml")
    grant = issue_grant(
        policy,
        template="github_task_branch_write",
        project_id="forge",
        task_id="task-123",
        subject_id="engineering-worker-1",
        resource=RESOURCE,
        operations={"branch.push", "pr.create"},
        ttl_minutes=20,
        branch=BRANCH,
        now=NOW,
    )
    return seal_grant(grant, key_id="cap-v1", key=KEY)


def _push_payload() -> dict[str, object]:
    return {
        "envelope": _envelope().model_dump(mode="json"),
        "request": GitHubPushRequest(
            project_id="forge",
            task_id="task-123",
            subject_id="engineering-worker-1",
            resource=RESOURCE,
            branch=BRANCH,
            expected_head=HEAD,
        ).model_dump(mode="json"),
    }


def test_http_service_requires_transport_auth_before_dispatch() -> None:
    dispatcher = FakeDispatcher()
    client = TestClient(create_github_broker_app(dispatcher, transport_key="t" * 32))

    response = client.post("/v1/github/push", json=_push_payload())
    assert response.status_code == 401
    assert dispatcher.push_calls == 0

    response = client.post(
        "/v1/github/push",
        json=_push_payload(),
        headers={"Authorization": "Bearer " + "t" * 32},
    )
    assert response.status_code == 200
    assert response.json()["remote_verified"] is True
    assert dispatcher.push_calls == 1


def test_policy_denial_is_returned_as_forbidden() -> None:
    dispatcher = FakeDispatcher()
    dispatcher.deny = True
    client = TestClient(create_github_broker_app(dispatcher, transport_key="t" * 32))
    response = client.post(
        "/v1/github/push",
        json=_push_payload(),
        headers={"Authorization": "Bearer " + "t" * 32},
    )
    assert response.status_code == 403
    assert dispatcher.push_calls == 1


def test_typed_pr_endpoint_has_no_arbitrary_url_or_base_field() -> None:
    dispatcher = FakeDispatcher()
    client = TestClient(create_github_broker_app(dispatcher, transport_key="t" * 32))
    request = GitHubPullRequestRequest(
        project_id="forge",
        task_id="task-123",
        subject_id="engineering-worker-1",
        resource=RESOURCE,
        branch=BRANCH,
        expected_head=HEAD,
        title="Task 123",
        body="change",
        draft=True,
    )
    payload = {
        "envelope": _envelope().model_dump(mode="json"),
        "request": request.model_dump(mode="json"),
    }
    payload["request"]["base_branch"] = "attacker-selected"
    response = client.post(
        "/v1/github/pulls",
        json=payload,
        headers={"Authorization": "Bearer " + "t" * 32},
    )
    assert response.status_code == 422
    assert dispatcher.pr_calls == 0


def _write_registry(path: Path, entries: list[dict[str, str]]) -> None:
    path.write_text(json.dumps({"version": 1, "entries": entries}))
    os.chmod(path, 0o644)


def test_workspace_registry_binds_project_task_and_repository(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "forge" / "task-123"
    git_common = tmp_path / "git" / "repo.git"
    workspace.mkdir(parents=True)
    git_common.mkdir(parents=True)
    registry_path = tmp_path / "registry.json"
    _write_registry(
        registry_path,
        [
            {
                "project_id": "forge",
                "task_id": "task-123",
                "resource": RESOURCE,
                "workspace": str(workspace),
                "git_common_dir": str(git_common),
            }
        ],
    )
    registry = RootOwnedWorkspaceRegistry(
        registry_path,
        workspace_root=workspace_root,
        required_owner_uid=os.geteuid(),
    )

    resolved = registry.resolve("forge", "task-123", RESOURCE)
    assert resolved.path == workspace.resolve()
    assert resolved.git_common_dir == git_common.resolve()
    with pytest.raises(GitHubBrokerError, match="exactly one"):
        registry.resolve("forge", "task-123", "zebadee2kk/other")


def test_workspace_registry_rejects_duplicates_and_writable_policy_file(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspaces"
    workspace = workspace_root / "forge" / "task-123"
    workspace.mkdir(parents=True)
    git_common = tmp_path / "git.git"
    git_common.mkdir()
    item = {
        "project_id": "forge",
        "task_id": "task-123",
        "resource": RESOURCE,
        "workspace": str(workspace),
        "git_common_dir": str(git_common),
    }
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path, [item, item])
    registry = RootOwnedWorkspaceRegistry(
        registry_path,
        workspace_root=workspace_root,
        required_owner_uid=os.geteuid(),
    )
    with pytest.raises(GitHubBrokerError, match="duplicate"):
        registry.resolve("forge", "task-123", RESOURCE)

    _write_registry(registry_path, [item])
    os.chmod(registry_path, 0o666)
    with pytest.raises(GitHubBrokerError, match="must not be group/world writable"):
        registry.resolve("forge", "task-123", RESOURCE)
