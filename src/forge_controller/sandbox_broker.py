from __future__ import annotations

import base64
import os
from hmac import compare_digest
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from .sandbox import SandboxLaunchRequest, SandboxPlan, SandboxPlanner, SandboxPolicyError
from .sandbox_runtime import DockerGVisorRuntime, SandboxExecutionResult

_DEFAULT_WORKSPACE_ROOT = "/var/lib/forge/workspaces"


class SandboxExecutor(Protocol):
    async def execute(self, plan: SandboxPlan) -> SandboxExecutionResult: ...


class SandboxExecutionResponse(BaseModel):
    request_id: str
    container_name: str
    returncode: int
    stdout_b64: str
    stderr_b64: str
    timed_out: bool
    cleanup_attempted: bool
    cleanup_returncode: int | None = None


def create_broker_app(
    *,
    workspace_root: str | Path | None = None,
    planner: SandboxPlanner | None = None,
    executor: SandboxExecutor | None = None,
    execution_enabled: bool | None = None,
    broker_key: str | None = None,
) -> FastAPI:
    root = workspace_root or os.environ.get("FORGE_SANDBOX_WORKSPACE_ROOT") or _DEFAULT_WORKSPACE_ROOT
    if planner is None:
        planner = SandboxPlanner(root)
    executor = executor or DockerGVisorRuntime()
    enabled = execution_enabled
    if enabled is None:
        enabled = os.environ.get("FORGE_SANDBOX_EXECUTION_ENABLED", "false").lower() == "true"
    expected_key = broker_key if broker_key is not None else os.environ.get("FORGE_SANDBOX_BROKER_KEY")

    app = FastAPI(title="Forge Sandbox Broker", version="0.1.0")

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {
            "status": "ok",
            "runtime": planner.runtime_name,
            "execution_enabled": enabled,
        }

    @app.post("/v1/sandboxes/plan", response_model=SandboxPlan)
    async def sandbox_plan(payload: SandboxLaunchRequest, request: Request) -> SandboxPlan:
        _authorize(request, expected_key)
        try:
            return planner.plan(payload)
        except SandboxPolicyError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/v1/sandboxes/run", response_model=SandboxExecutionResponse)
    async def sandbox_run(
        payload: SandboxLaunchRequest,
        request: Request,
    ) -> SandboxExecutionResponse:
        _authorize(request, expected_key)
        if not enabled:
            raise HTTPException(status_code=503, detail="sandbox execution is disabled")
        try:
            plan = planner.plan(payload)
        except SandboxPolicyError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        result = await executor.execute(plan)
        return SandboxExecutionResponse(
            request_id=result.request_id,
            container_name=result.container_name,
            returncode=result.returncode,
            stdout_b64=base64.b64encode(result.stdout).decode("ascii"),
            stderr_b64=base64.b64encode(result.stderr).decode("ascii"),
            timed_out=result.timed_out,
            cleanup_attempted=result.cleanup_attempted,
            cleanup_returncode=result.cleanup_returncode,
        )

    return app


def _authorize(request: Request, expected_key: str | None) -> None:
    if not expected_key:
        raise HTTPException(status_code=503, detail="sandbox broker authentication is not configured")
    authorization = request.headers.get("authorization", "")
    prefix = "Bearer "
    supplied = authorization[len(prefix) :] if authorization.startswith(prefix) else ""
    if not supplied or not compare_digest(supplied, expected_key):
        raise HTTPException(status_code=401, detail="invalid sandbox broker credential")


app = create_broker_app()
