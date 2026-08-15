import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from forge_controller.capabilities import CapabilityDenied, CapabilityPolicy, issue_grant
from forge_controller.capability_envelope import seal_grant
from forge_controller.github_broker import (
    GitHubBroker,
    GitHubBrokerError,
    GitHubPullRequestRequest,
    GitHubPushRequest,
    InstallationToken,
    SubprocessGitExecutor,
    TrustedWorkspace,
    WorkspaceState,
)

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 8, 15, 23, 0, tzinfo=UTC)
KEY = b"g" * 32
HEAD = "a" * 40
RESOURCE = "zebadee2kk/hermes-dev-team-vm"
BRANCH = "forge/task-123"


class FakeTokens:
    def __init__(self) -> None:
        self.minted: list[tuple[str, dict[str, str], InstallationToken]] = []
        self.revoked: list[str] = []

    def mint(self, resource: str, permissions: dict[str, str]) -> InstallationToken:
        token = InstallationToken(
            value=f"secret-token-{len(self.minted) + 1}",
            expires_at=NOW + timedelta(minutes=60),
        )
        self.minted.append((resource, dict(permissions), token))
        return token

    def revoke(self, token: InstallationToken) -> None:
        self.revoked.append(token.value)


class FakeGit:
    def __init__(self, workspace: TrustedWorkspace, *, dangerous: bool = False) -> None:
        self.workspace = workspace
        self.dangerous = dangerous
        self.pushes: list[tuple[str, str, str]] = []

    def inspect(self, workspace: TrustedWorkspace) -> WorkspaceState:
        assert workspace == self.workspace
        return WorkspaceState(
            head_sha=HEAD,
            clean=True,
            top_level=workspace.path,
            git_common_dir=workspace.git_common_dir,
            dangerous_config_keys=("url.https://evil.invalid.insteadof",) if self.dangerous else (),
        )

    def push(
        self,
        workspace: TrustedWorkspace,
        *,
        resource: str,
        branch: str,
        token: InstallationToken,
    ) -> None:
        assert workspace == self.workspace
        self.pushes.append((resource, branch, token.value))


def _policy() -> CapabilityPolicy:
    return CapabilityPolicy.load(ROOT / "config/capability-policy.yaml")


def _envelope(*operations: str):
    grant = issue_grant(
        _policy(),
        template="github_task_branch_write",
        project_id="forge",
        task_id="task-123",
        subject_id="engineering-worker-1",
        resource=RESOURCE,
        operations=set(operations),
        ttl_minutes=20,
        branch=BRANCH,
        now=NOW,
    )
    return seal_grant(grant, key_id="cap-v1", key=KEY)


def _http_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Bearer secret-token-")
        if request.method == "GET" and request.url.path == f"/repos/{RESOURCE}":
            return httpx.Response(200, json={"default_branch": "main"})
        if request.method == "GET" and "/git/ref/heads/" in request.url.path:
            return httpx.Response(200, json={"object": {"sha": HEAD}})
        if request.method == "POST" and request.url.path == f"/repos/{RESOURCE}/pulls":
            sent = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "number": 42,
                    "html_url": f"https://github.com/{RESOURCE}/pull/42",
                    "head": {"ref": sent["head"], "sha": HEAD},
                    "base": {"ref": sent["base"]},
                    "draft": sent["draft"],
                },
            )
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _broker(tmp_path: Path, *, dangerous: bool = False):
    workspace_path = tmp_path / "task-123"
    workspace_path.mkdir()
    git_dir = tmp_path / "git-state" / "task-123.git"
    git_dir.mkdir(parents=True)
    workspace = TrustedWorkspace(path=workspace_path.resolve(), git_common_dir=git_dir.resolve())
    tokens = FakeTokens()
    git = FakeGit(workspace, dangerous=dangerous)
    broker = GitHubBroker(
        policy=_policy(),
        capability_keyring={"cap-v1": KEY},
        token_provider=tokens,
        workspace_resolver=lambda project, task: workspace,
        workspace_root=tmp_path,
        git_executor=git,
        client=_http_client(),
        clock=lambda: NOW + timedelta(minutes=1),
    )
    return broker, tokens, git


def test_push_uses_exact_scope_short_lived_tokens_and_verifies_remote(tmp_path: Path) -> None:
    broker, tokens, git = _broker(tmp_path)
    result = broker.push_task_branch(
        _envelope("branch.push"),
        GitHubPushRequest(
            project_id="forge",
            task_id="task-123",
            subject_id="engineering-worker-1",
            resource=RESOURCE,
            branch=BRANCH,
            expected_head=HEAD,
        ),
    )

    assert result.remote_verified is True
    assert result.head_sha == HEAD
    assert git.pushes == [(RESOURCE, BRANCH, "secret-token-2")]
    assert [permissions for _, permissions, _ in tokens.minted] == [
        {"metadata": "read"},
        {"contents": "write"},
        {"contents": "read"},
    ]
    assert tokens.revoked == ["secret-token-1", "secret-token-2", "secret-token-3"]
    assert "secret-token" not in result.model_dump_json()


def test_scope_or_envelope_failure_happens_before_any_github_token_is_minted(
    tmp_path: Path,
) -> None:
    broker, tokens, _ = _broker(tmp_path)
    request = GitHubPushRequest(
        project_id="forge",
        task_id="task-999",
        subject_id="engineering-worker-1",
        resource=RESOURCE,
        branch=BRANCH,
        expected_head=HEAD,
    )
    with pytest.raises(CapabilityDenied, match="task"):
        broker.push_task_branch(_envelope("branch.push"), request)
    assert tokens.minted == []

    envelope = _envelope("branch.push")
    tampered = envelope.model_copy(
        update={"grant": envelope.grant.model_copy(update={"branch": "forge/other"})}
    )
    valid_request = request.model_copy(update={"task_id": "task-123"})
    with pytest.raises(CapabilityDenied, match="authentication"):
        broker.push_task_branch(tampered, valid_request)
    assert tokens.minted == []


def test_dangerous_workspace_git_config_blocks_write_token(tmp_path: Path) -> None:
    broker, tokens, git = _broker(tmp_path, dangerous=True)
    with pytest.raises(GitHubBrokerError, match="dangerous Git config"):
        broker.push_task_branch(
            _envelope("branch.push"),
            GitHubPushRequest(
                project_id="forge",
                task_id="task-123",
                subject_id="engineering-worker-1",
                resource=RESOURCE,
                branch=BRANCH,
                expected_head=HEAD,
            ),
        )
    assert git.pushes == []
    assert [permissions for _, permissions, _ in tokens.minted] == [{"metadata": "read"}]
    assert tokens.revoked == ["secret-token-1"]


def test_pr_creation_targets_only_default_branch_and_verifies_head(tmp_path: Path) -> None:
    broker, tokens, _ = _broker(tmp_path)
    result = broker.create_pull_request(
        _envelope("pr.create"),
        GitHubPullRequestRequest(
            project_id="forge",
            task_id="task-123",
            subject_id="engineering-worker-1",
            resource=RESOURCE,
            branch=BRANCH,
            expected_head=HEAD,
            title="Task 123",
            body="Automated probation change",
            draft=True,
        ),
    )

    assert result.number == 42
    assert result.base_branch == "main"
    assert result.head_branch == BRANCH
    assert result.head_sha == HEAD
    assert [permissions for _, permissions, _ in tokens.minted] == [
        {"metadata": "read"},
        {"contents": "read"},
        {"pull_requests": "write"},
    ]
    assert len(tokens.revoked) == 3


def test_subprocess_inspection_detects_local_url_rewrite(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Forge Test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "forge@example.invalid"], check=True)
    (repo / "README.md").write_text("test\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    executor = SubprocessGitExecutor(git_binary="/usr/bin/git", askpass_path="/bin/false")
    workspace = TrustedWorkspace(path=repo.resolve(), git_common_dir=(repo / ".git").resolve())

    safe = executor.inspect(workspace)
    assert safe.clean is True
    assert safe.dangerous_config_keys == ()

    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "config",
            "url.https://evil.invalid/.insteadOf",
            "https://github.com/",
        ],
        check=True,
    )
    poisoned = executor.inspect(workspace)
    assert "url.https://evil.invalid/.insteadof" in tuple(
        key.lower() for key in poisoned.dangerous_config_keys
    )
