import base64
from pathlib import Path

from fastapi.testclient import TestClient

from forge_controller.sandbox import SandboxLaunchRequest, SandboxPlanner
from forge_controller.sandbox_broker import create_broker_app
from forge_controller.sandbox_runtime import SandboxExecutionResult

DIGEST = "sha256:" + "c" * 64
IMAGE = f"ghcr.io/example/forge-worker@{DIGEST}"


class FakeExecutor:
    def __init__(self) -> None:
        self.plans = []

    async def execute(self, plan):
        self.plans.append(plan)
        return SandboxExecutionResult(
            request_id=plan.request_id,
            container_name=plan.container_name,
            returncode=0,
            stdout=b"sandbox-ok",
            stderr=b"",
            timed_out=False,
            cleanup_attempted=False,
        )


def payload(workspace: Path) -> dict[str, object]:
    return SandboxLaunchRequest(
        request_id="12345678-1234-5678-1234-567812345678",
        project_id="P1",
        task_id="T1",
        image=IMAGE,
        command=["true"],
        workspace_path=str(workspace),
    ).model_dump(mode="json")


def test_plan_requires_broker_auth_and_preserves_fail_closed_policy(tmp_path) -> None:
    root = tmp_path / "workspaces"
    workspace = root / "P1" / "T1"
    workspace.mkdir(parents=True)
    app = create_broker_app(
        planner=SandboxPlanner(root),
        executor=FakeExecutor(),
        execution_enabled=False,
        broker_key="broker-secret",
    )

    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["execution_enabled"] is False

        assert client.post("/v1/sandboxes/plan", json=payload(workspace)).status_code == 401
        response = client.post(
            "/v1/sandboxes/plan",
            json=payload(workspace),
            headers={"Authorization": "Bearer broker-secret"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["runtime"] == "runsc"
        assert body["network_mode"] == "none"
        assert body["read_only_rootfs"] is True

        disabled = client.post(
            "/v1/sandboxes/run",
            json=payload(workspace),
            headers={"Authorization": "Bearer broker-secret"},
        )
        assert disabled.status_code == 503


def test_enabled_broker_returns_encoded_output_without_exposing_runtime_control(tmp_path) -> None:
    root = tmp_path / "workspaces"
    workspace = root / "P1" / "T1"
    workspace.mkdir(parents=True)
    executor = FakeExecutor()
    app = create_broker_app(
        planner=SandboxPlanner(root),
        executor=executor,
        execution_enabled=True,
        broker_key="broker-secret",
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/sandboxes/run",
            json=payload(workspace),
            headers={"Authorization": "Bearer broker-secret"},
        )

    assert response.status_code == 200
    body = response.json()
    assert base64.b64decode(body["stdout_b64"]) == b"sandbox-ok"
    assert body["timed_out"] is False
    assert len(executor.plans) == 1
    plan = executor.plans[0]
    assert plan.network_mode == "none"
    assert plan.workspace_source == str(workspace.resolve())
