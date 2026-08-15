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
LOCAL_IMAGE = "sha256:" + "b" * 64


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
    assert plan.ipc_mode == "none"
    assert plan.read_only_rootfs is True
    assert plan.cap_drop == ["ALL"]
    assert plan.security_opt == ["no-new-privileges:true"]
    assert plan.user == "65532:65532"
    assert plan.workspace_source == str(workspace.resolve())
    assert plan.workspace_destination == "/workspace"
    assert plan.named_volumes == []
    assert plan.tmpfs["/tmp"].startswith("rw,noexec,nosuid,nodev")

    joined = " ".join(command)
    assert "--runtime runsc" in joined
    assert "--network none" in joined
    assert "--ipc none" in joined
    assert "--read-only" in command
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges:true" in joined
    assert "/var/run/docker.sock" not in joined
    assert "/run/containerd" not in joined
    assert f"src={workspace.resolve()},dst=/workspace,rw" in joined
    assert f"src={root.resolve()},dst=/workspace" not in joined
    assert f"src={tmp_path.resolve()},dst=/workspace" not in joined


def test_codex_probation_profile_has_only_internal_proxy_and_dedicated_state_volume(tmp_path) -> None:
    root = tmp_path / "workspaces"
    workspace = root / "P1" / "T1"
    workspace.mkdir(parents=True)
    planner = SandboxPlanner(root)
    launch = request(
        workspace,
        profile=planner.CODEX_PROFILE,
        capability_grant_refs=[planner.CODEX_GRANT_REF],
    )

    plan = planner.plan(launch)
    command = docker_run_command(plan)
    joined = " ".join(command)

    assert plan.network_mode == "forge-codex-internal"
    assert plan.secret_refs == []
    assert len(plan.named_volumes) == 1
    volume = plan.named_volumes[0]
    assert volume.source == "forge-codex-probation-auth"
    assert volume.destination == "/codex-home"
    assert volume.read_only is False
    assert plan.environment["CODEX_HOME"] == "/codex-home"
    assert plan.environment["HTTPS_PROXY"] == "http://forge-codex-egress:3128"
    assert plan.environment["HTTP_PROXY"] == "http://forge-codex-egress:3128"
    assert "--network forge-codex-internal" in joined
    assert "type=volume,src=forge-codex-probation-auth,dst=/codex-home,rw" in joined
    assert "/var/run/docker.sock" not in joined


def test_codex_probation_profile_requires_exact_capability_grant(tmp_path) -> None:
    root = tmp_path / "workspaces"
    workspace = root / "P1" / "T1"
    workspace.mkdir(parents=True)
    planner = SandboxPlanner(root)

    with pytest.raises(SandboxPolicyError, match="dedicated OpenAI egress"):
        planner.plan(request(workspace, profile=planner.CODEX_PROFILE))
    with pytest.raises(SandboxPolicyError, match="dedicated OpenAI egress"):
        planner.plan(
            request(
                workspace,
                profile=planner.CODEX_PROFILE,
                capability_grant_refs=[planner.CODEX_GRANT_REF, "capability:extra"],
            )
        )


def test_codex_probation_profile_rejects_forge_secret_refs_and_proxy_override(tmp_path) -> None:
    root = tmp_path / "workspaces"
    workspace = root / "P1" / "T1"
    workspace.mkdir(parents=True)
    planner = SandboxPlanner(root)
    grants = [planner.CODEX_GRANT_REF]

    with pytest.raises(SandboxPolicyError, match="does not accept Forge secret refs"):
        planner.plan(
            request(
                workspace,
                profile=planner.CODEX_PROFILE,
                capability_grant_refs=grants,
                secret_refs=["vault:forge-master"],
            )
        )
    with pytest.raises(SandboxPolicyError, match="controls proxy/home"):
        planner.plan(
            request(
                workspace,
                profile=planner.CODEX_PROFILE,
                capability_grant_refs=grants,
                environment={"HTTPS_PROXY": "http://evil.example:8080"},
            )
        )


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


def test_local_content_addressed_image_id_is_allowed() -> None:
    launch = SandboxLaunchRequest(
        project_id="P1",
        task_id="T1",
        image=LOCAL_IMAGE,
        command=["true"],
        workspace_path="/work/P1/T1",
    )
    assert launch.image == LOCAL_IMAGE


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
