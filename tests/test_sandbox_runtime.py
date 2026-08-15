from pathlib import Path

import pytest

from forge_controller.sandbox import SandboxLaunchRequest, SandboxPlanner
from forge_controller.sandbox_runtime import CommandResult, DockerGVisorRuntime

DIGEST = "sha256:" + "b" * 64
IMAGE = f"ghcr.io/example/forge-worker@{DIGEST}"


class FakeRunner:
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[list[str], int]] = []

    async def run(self, command: list[str], *, timeout_seconds: int) -> CommandResult:
        self.calls.append((command, timeout_seconds))
        return self.results.pop(0)


def plan(tmp_path: Path):
    root = tmp_path / "workspaces"
    workspace = root / "P1" / "T1"
    workspace.mkdir(parents=True)
    request = SandboxLaunchRequest(
        request_id="12345678-1234-5678-1234-567812345678",
        project_id="P1",
        task_id="T1",
        image=IMAGE,
        command=["python", "-m", "pytest", "-q"],
        workspace_path=str(workspace),
    )
    return SandboxPlanner(root).plan(request)


@pytest.mark.asyncio
async def test_successful_sandbox_does_not_issue_forced_cleanup(tmp_path) -> None:
    runner = FakeRunner([CommandResult(returncode=0, stdout=b"ok")])
    runtime = DockerGVisorRuntime(runner)
    result = await runtime.execute(plan(tmp_path))

    assert result.returncode == 0
    assert result.stdout == b"ok"
    assert result.timed_out is False
    assert result.cleanup_attempted is False
    assert len(runner.calls) == 1
    assert runner.calls[0][0][:3] == ["docker", "run", "--rm"]


@pytest.mark.asyncio
async def test_timeout_always_attempts_named_container_force_removal(tmp_path) -> None:
    sandbox_plan = plan(tmp_path)
    runner = FakeRunner(
        [
            CommandResult(returncode=-9, stderr=b"timeout", timed_out=True),
            CommandResult(returncode=0),
        ]
    )
    runtime = DockerGVisorRuntime(runner)
    result = await runtime.execute(sandbox_plan)

    assert result.timed_out is True
    assert result.cleanup_attempted is True
    assert result.cleanup_returncode == 0
    assert len(runner.calls) == 2
    assert runner.calls[1] == (["docker", "rm", "-f", sandbox_plan.container_name], 30)
