from pathlib import Path

import pytest
from pydantic import ValidationError

from forge_controller.sandbox import (
    SandboxLaunchRequest,
    SandboxPlanner,
    SandboxPolicyError,
    docker_run_command,
)

DIGEST = "sha256:" + "a" * 64
IMAGE = f"ghcr.io/example/forge-worker@{DIGEST}"


def request(workspace: Path, **updates: object) -> SandboxLaunchRequest:
    payload: dict[str, object] = {
        "request_id": "12345678-1234-5678-1234-567812345678",
        "project_id": "P1",
        "task_id": "T1",
        "image": IMAGE,
        "command": ["python", "-m", "pytest", "-q"],
        "workspace_path": str(workspace),
        "environment": {"CI": "true", "FORGE_TASK_ID": "T1"},
    }
    payload.update(updates)
    return SandboxLaunchRequest.model_validate(payload)


def test_normal_plan_is_fail_closed_and_mounts_only_task_workspace(tmp_path) -> None:
    root = tmp_path / "workspaces"
    workspace = root / "P1" / "T1"
    workspace.mkdir(parents=True)
    plan = SandboxPlanner(root).plan(request(workspace))
    command = docker_run_command(plan)

    assert plan.runtime == "runsc"
    assert plan.network_mode == "none"
    assert plan.read_only_rootfs is True
    assert plan.cap_drop == ["ALL"]
    assert plan.security_opt == ["no-new-privileges:true"]
    assert plan.user == "65532:65532"
    assert plan.workspace_source == str(workspace.resolve())
    assert plan.workspace_destination == "/workspace"
    assert plan.tmpfs["/tmp"].startswith("rw,noexec,nosuid,nodev")

    joined = " ".join(command)
    assert "--runtime runsc" in joined
    assert "--network none" in joined
    assert "--read-only" in command
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges:true" in joined
    assert "/var/run/docker.sock" not in joined
    assert "/run/containerd" not in joined
    assert str(root.resolve().parent) not in plan.workspace_source


def test_workspace_escape_is_rejected(tmp_path) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(SandboxPolicyError):
        SandboxPlanner(root).plan(request(outside))


def test_workspace_root_itself_is_not_a_valid_task_mount(tmp_path) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    with pytest.raises(SandboxPolicyError):
        SandboxPlanner(root).plan(request(root))


def test_unpinned_image_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SandboxLaunchRequest(
            project_id="P1",
            task_id="T1",
            image="ghcr.io/example/forge-worker:latest",
            command=["true"],
            workspace_path="/work/P1/T1",
        )


@pytest.mark.parametrize(
    "name",
    [
        "GROQ_API_KEY",
        "FORGE_GATEWAY_TOKEN",
        "DATABASE_URL",
        "MY_PASSWORD",
        "SSH_PRIVATE_KEY",
        "CLOUD_CREDENTIAL",
    ],
)
def test_secret_like_environment_names_are_rejected(name: str) -> None:
    with pytest.raises(ValidationError):
        SandboxLaunchRequest(
            project_id="P1",
            task_id="T1",
            image=IMAGE,
            command=["true"],
            workspace_path="/work/P1/T1",
            environment={name: "should-not-be-here"},
        )


def test_unimplemented_profiles_fail_closed(tmp_path) -> None:
    root = tmp_path / "workspaces"
    workspace = root / "P1" / "T1"
    workspace.mkdir(parents=True)
    with pytest.raises(SandboxPolicyError):
        SandboxPlanner(root).plan(request(workspace, profile="high"))
