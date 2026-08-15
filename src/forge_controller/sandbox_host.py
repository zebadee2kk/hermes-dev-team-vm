from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Protocol

from pydantic import BaseModel, Field


@dataclass(frozen=True, slots=True)
class HostCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class HostCommandRunner(Protocol):
    def run(self, command: list[str], *, timeout_seconds: int = 15) -> HostCommandResult: ...


class SubprocessHostCommandRunner:
    def run(self, command: list[str], *, timeout_seconds: int = 15) -> HostCommandResult:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return HostCommandResult(returncode=127, stderr=str(exc))
        return HostCommandResult(
            returncode=result.returncode,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
        )


class HostCheck(BaseModel):
    name: str
    ok: bool
    detail: str = ""


class SandboxHostPreflightReport(BaseModel):
    ready: bool
    architecture: str
    workspace_root: str
    versions: dict[str, str] = Field(default_factory=dict)
    checks: list[HostCheck]


class SandboxHostPreflight:
    """Non-mutating validation for a host that will run the trusted Sandbox Broker."""

    SUPPORTED_ARCHITECTURES: ClassVar[frozenset[str]] = frozenset(
        {"x86_64", "amd64", "aarch64", "arm64"}
    )

    def __init__(self, runner: HostCommandRunner | None = None) -> None:
        self.runner = runner or SubprocessHostCommandRunner()

    def inspect(self, workspace_root: str | Path) -> SandboxHostPreflightReport:
        root = Path(workspace_root).resolve()
        architecture = platform.machine().lower()
        checks: list[HostCheck] = []
        versions: dict[str, str] = {}

        checks.append(
            HostCheck(
                name="linux_host",
                ok=platform.system().lower() == "linux",
                detail=platform.system(),
            )
        )
        checks.append(
            HostCheck(
                name="supported_architecture",
                ok=architecture in self.SUPPORTED_ARCHITECTURES,
                detail=architecture,
            )
        )
        checks.append(
            HostCheck(
                name="workspace_root",
                ok=root.is_dir() and root != Path("/"),
                detail=str(root),
            )
        )

        docker_version = self.runner.run(
            ["docker", "version", "--format", "{{.Server.Version}}"]
        )
        if docker_version.returncode == 0:
            versions["docker_server"] = docker_version.stdout
        checks.append(
            HostCheck(
                name="docker_server",
                ok=docker_version.returncode == 0 and bool(docker_version.stdout),
                detail=docker_version.stdout or docker_version.stderr,
            )
        )

        runsc_version = self.runner.run(["runsc", "--version"])
        if runsc_version.returncode == 0:
            versions["runsc"] = runsc_version.stdout
        checks.append(
            HostCheck(
                name="runsc_binary",
                ok=runsc_version.returncode == 0,
                detail=runsc_version.stdout or runsc_version.stderr,
            )
        )

        runtimes = self.runner.run(
            ["docker", "info", "--format", "{{json .Runtimes}}"]
        )
        runtime_names: set[str] = set()
        parse_detail = runtimes.stdout or runtimes.stderr
        if runtimes.returncode == 0:
            try:
                payload = json.loads(runtimes.stdout)
                if isinstance(payload, dict):
                    runtime_names = {str(name) for name in payload}
            except json.JSONDecodeError:
                runtime_names = set()
        checks.append(
            HostCheck(
                name="docker_runsc_runtime",
                ok=runtimes.returncode == 0 and "runsc" in runtime_names,
                detail=", ".join(sorted(runtime_names)) or parse_detail,
            )
        )

        return SandboxHostPreflightReport(
            ready=all(check.ok for check in checks),
            architecture=architecture,
            workspace_root=str(root),
            versions=versions,
            checks=checks,
        )
