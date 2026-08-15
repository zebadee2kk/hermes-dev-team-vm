from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from .sandbox import SandboxPlan, docker_run_command


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False


@dataclass(frozen=True, slots=True)
class SandboxExecutionResult:
    request_id: str
    container_name: str
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    cleanup_attempted: bool
    cleanup_returncode: int | None = None


class CommandRunner(Protocol):
    async def run(self, command: list[str], *, timeout_seconds: int) -> CommandResult: ...


class SubprocessCommandRunner:
    async def run(self, command: list[str], *, timeout_seconds: int) -> CommandResult:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            process.kill()
            stdout, stderr = await process.communicate()
            return CommandResult(
                returncode=process.returncode if process.returncode is not None else -9,
                stdout=stdout,
                stderr=stderr,
                timed_out=True,
            )
        return CommandResult(
            returncode=process.returncode if process.returncode is not None else -1,
            stdout=stdout,
            stderr=stderr,
        )


class DockerGVisorRuntime:
    """Trusted broker backend. Worker processes never receive this runtime control."""

    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or SubprocessCommandRunner()

    async def execute(self, plan: SandboxPlan) -> SandboxExecutionResult:
        result = await self.runner.run(
            docker_run_command(plan),
            timeout_seconds=plan.limits.timeout_seconds,
        )
        cleanup_attempted = result.timed_out
        cleanup_returncode: int | None = None
        if cleanup_attempted:
            cleanup = await self.runner.run(
                ["docker", "rm", "-f", plan.container_name],
                timeout_seconds=30,
            )
            cleanup_returncode = cleanup.returncode

        return SandboxExecutionResult(
            request_id=plan.request_id,
            container_name=plan.container_name,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
            cleanup_attempted=cleanup_attempted,
            cleanup_returncode=cleanup_returncode,
        )
