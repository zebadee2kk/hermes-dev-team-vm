import platform
from pathlib import Path

from forge_controller.sandbox_host import (
    HostCommandResult,
    SandboxHostPreflight,
)


class FakeRunner:
    def __init__(self, *, include_runsc_runtime: bool = True) -> None:
        self.include_runsc_runtime = include_runsc_runtime
        self.commands: list[list[str]] = []

    def run(self, command: list[str], *, timeout_seconds: int = 15) -> HostCommandResult:
        self.commands.append(command)
        if command[:2] == ["docker", "version"]:
            return HostCommandResult(returncode=0, stdout="29.0.0")
        if command[:2] == ["runsc", "--version"]:
            return HostCommandResult(returncode=0, stdout="runsc version release-20260801.0")
        if command[:2] == ["docker", "info"]:
            runtimes = '{"io.containerd.runc.v2":{},"runc":{}'
            if self.include_runsc_runtime:
                runtimes += ',"runsc":{}'
            runtimes += "}"
            return HostCommandResult(returncode=0, stdout=runtimes)
        return HostCommandResult(returncode=127, stderr="unexpected command")


def test_host_preflight_accepts_linux_supported_arch_with_runsc(tmp_path, monkeypatch) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")

    report = SandboxHostPreflight(FakeRunner()).inspect(root)

    assert report.ready is True
    assert report.workspace_root == str(root.resolve())
    assert report.versions["docker_server"] == "29.0.0"
    assert "runsc version" in report.versions["runsc"]
    assert all(check.ok for check in report.checks)


def test_host_preflight_fails_when_docker_has_no_runsc_runtime(tmp_path, monkeypatch) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "aarch64")

    report = SandboxHostPreflight(FakeRunner(include_runsc_runtime=False)).inspect(root)

    assert report.ready is False
    runtime_check = next(check for check in report.checks if check.name == "docker_runsc_runtime")
    assert runtime_check.ok is False


def test_host_preflight_rejects_workspace_root_slash(monkeypatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")

    report = SandboxHostPreflight(FakeRunner()).inspect(Path("/"))

    assert report.ready is False
    workspace_check = next(check for check in report.checks if check.name == "workspace_root")
    assert workspace_check.ok is False
