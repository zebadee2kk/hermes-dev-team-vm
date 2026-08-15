from pathlib import Path

import pytest

from forge_controller.codex_runtime import (
    CodexRuntimeConfig,
    docker_codex_command,
    validate_codex_args,
    validate_cwd,
)
from forge_controller.sandbox import SandboxPolicyError

IMAGE = "sha256:" + "d" * 64


def config(workspace: Path) -> CodexRuntimeConfig:
    return CodexRuntimeConfig(
        workspace=workspace,
        image=IMAGE,
        network="forge-codex-internal",
        auth_volume="forge-codex-probation-auth",
        proxy_url="http://forge-codex-egress:3128",
    )


def test_codex_runtime_mounts_only_exact_probation_workspace_at_same_path(tmp_path) -> None:
    workspace = tmp_path / "workspaces" / "forge" / "probation-001"
    cwd = workspace / "repo" / "src"
    cwd.mkdir(parents=True)

    command = docker_codex_command(config(workspace), cwd=cwd, codex_args=["app-server"])
    joined = " ".join(command)

    assert command[:4] == ["docker", "run", "--rm", "-i"]
    assert "--runtime runsc" in joined
    assert "--network forge-codex-internal" in joined
    assert "--ipc none" in joined
    assert "--read-only" in command
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges:true" in joined
    assert f"type=bind,src={workspace.resolve()},dst={workspace.resolve()},rw" in joined
    assert "type=volume,src=forge-codex-probation-auth,dst=/codex-home,rw" in joined
    assert f"--workdir {cwd.resolve()}" in joined
    assert "HTTPS_PROXY=http://forge-codex-egress:3128" in joined
    assert "CODEX_HOME=/codex-home" in joined
    assert "/var/run/docker.sock" not in joined
    assert command[-3:] == [IMAGE, "codex", "app-server"]


def test_codex_runtime_rejects_sibling_or_parent_workspace_cwd(tmp_path) -> None:
    workspace = tmp_path / "workspaces" / "forge" / "probation-001"
    sibling = tmp_path / "workspaces" / "forge" / "other-task"
    workspace.mkdir(parents=True)
    sibling.mkdir(parents=True)

    with pytest.raises(SandboxPolicyError, match="escapes probation workspace"):
        validate_cwd(sibling, workspace)
    with pytest.raises(SandboxPolicyError, match="escapes probation workspace"):
        validate_cwd(workspace.parent, workspace)


def test_codex_runtime_whitelists_only_app_server_preflight_shapes(tmp_path) -> None:
    workspace = tmp_path / "probation"
    schema = workspace / ".schema"
    workspace.mkdir()

    assert validate_codex_args(["--version"], workspace) == ["--version"]
    assert validate_codex_args(["app-server"], workspace) == ["app-server"]
    assert validate_codex_args(["app-server", "--stdio"], workspace) == ["app-server", "--stdio"]
    assert validate_codex_args(
        ["app-server", "generate-json-schema", "--out", str(schema)], workspace
    ) == ["app-server", "generate-json-schema", "--out", str(schema)]

    for rejected in (
        ["exec", "do something"],
        ["login"],
        ["mcp", "list"],
        ["app-server", "generate-json-schema", "--out", str(tmp_path / "outside")],
    ):
        with pytest.raises(SandboxPolicyError):
            validate_codex_args(rejected, workspace)
