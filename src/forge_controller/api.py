from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hmac import compare_digest

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

from .contracts import InferenceDeployment, RealityAnchor, TaskCapsule, TrustEnvelope
from .decision import classify_decision
from .model_gateway import (
    ModelGatewayUnavailable,
    UnknownForgeModel,
    forward_chat_completion,
    model_catalogue,
)
from .models import (
    Availability,
    DecisionClassification,
    DecisionRequest,
    ModelCandidate,
    QuotaObservation,
    RouteRequest,
    Sensitivity,
)
from .persistence import create_schema, make_engine, make_session_factory
from .placement import WaitingForCompute, observe, place
from .quota import classify_observation
from .repository import AssuranceRepository, CapsuleRevisionConflict


class ProjectCreate(BaseModel):
    project_id: str
    name: str


def create_app(
    *,
    database_url: str | None = None,
    auto_create_schema: bool | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        url = database_url or os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is required")
        engine = make_engine(url)
        should_create = auto_create_schema
        if should_create is None:
            should_create = os.environ.get("FORGE_AUTO_CREATE_SCHEMA", "false").lower() == "true"
        if should_create:
            await create_schema(engine)
        app.state.engine = engine
        app.state.repository = AssuranceRepository(make_session_factory(engine))
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Hermes Forge Controller", version="0.4.0", lifespan=lifespan)

    def repository(request: Request) -> AssuranceRepository:
        return request.app.state.repository

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models")
    async def models(request: Request) -> dict[str, object]:
        _authorize_model_gateway(request)
        return model_catalogue()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        _authorize_model_gateway(request)
        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid JSON request") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="request body must be a JSON object")

        raw_sensitivity = request.headers.get("x-forge-sensitivity", Sensitivity.PUBLIC.value)
        try:
            sensitivity = Sensitivity(raw_sensitivity.upper())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid X-Forge-Sensitivity") from exc

        litellm_base_url = os.environ.get("LITELLM_BASE_URL")
        litellm_master_key = os.environ.get("LITELLM_MASTER_KEY")
        if not litellm_base_url or not litellm_master_key:
            raise HTTPException(status_code=503, detail="LiteLLM execution gateway is not configured")

        try:
            result = await forward_chat_completion(
                repository(request),
                payload,
                litellm_base_url=litellm_base_url,
                litellm_master_key=litellm_master_key,
                sensitivity=sensitivity,
            )
        except UnknownForgeModel as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except WaitingForCompute as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "reason": str(exc),
                    "state": "WAITING_COMPUTE",
                    "retry_at": exc.retry_at.isoformat() if exc.retry_at else None,
                },
            ) from exc
        except ModelGatewayUnavailable as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        content_type = result.headers.get("content-type", "application/json").split(";", 1)[0]
        return Response(
            content=result.content,
            status_code=result.status_code,
            media_type=content_type,
            headers={"X-Forge-Deployment-ID": result.deployment_id},
        )

    @app.post("/v1/projects", response_model=ProjectCreate)
    async def project_create(payload: ProjectCreate, request: Request) -> ProjectCreate:
        await repository(request).create_project(payload.project_id, payload.name)
        return payload

    @app.post("/v1/capsules", response_model=TaskCapsule)
    async def capsule_checkpoint(capsule: TaskCapsule, request: Request) -> TaskCapsule:
        try:
            await repository(request).save_capsule(capsule)
        except CapsuleRevisionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return capsule

    @app.get("/v1/capsules/{task_id}", response_model=TaskCapsule)
    async def capsule_latest(task_id: str, request: Request) -> TaskCapsule:
        capsule = await repository(request).latest_capsule(task_id)
        if capsule is None:
            raise HTTPException(status_code=404, detail="Task Capsule not found")
        return capsule

    @app.post("/v1/anchors", response_model=RealityAnchor)
    async def anchor_record(anchor: RealityAnchor, request: Request) -> RealityAnchor:
        await repository(request).record_anchor(anchor)
        return anchor

    @app.post("/v1/trust-envelopes", response_model=TrustEnvelope)
    async def trust_envelope_record(envelope: TrustEnvelope, request: Request) -> TrustEnvelope:
        await repository(request).record_trust_envelope(envelope)
        return envelope

    @app.put("/v1/deployments", response_model=InferenceDeployment)
    async def deployment_upsert(
        deployment: InferenceDeployment, request: Request
    ) -> InferenceDeployment:
        await repository(request).upsert_deployment(deployment)
        return deployment

    @app.get("/v1/candidates", response_model=list[ModelCandidate])
    async def candidates(request: Request) -> list[ModelCandidate]:
        return await repository(request).list_candidates()

    @app.post("/v1/route", response_model=ModelCandidate)
    async def route(route_request: RouteRequest, request: Request) -> ModelCandidate:
        try:
            return await place(repository(request), route_request)
        except WaitingForCompute as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "reason": str(exc),
                    "state": "WAITING_COMPUTE",
                    "retry_at": exc.retry_at.isoformat() if exc.retry_at else None,
                },
            ) from exc

    @app.post("/v1/deployments/{deployment_id:path}/observations", response_model=Availability)
    async def availability_observe(
        deployment_id: str,
        observation: QuotaObservation,
        request: Request,
    ) -> Availability:
        availability = classify_observation(observation)
        try:
            await observe(repository(request), deployment_id, observation)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return availability

    @app.post("/v1/quota/classify", response_model=Availability)
    async def quota_classify(observation: QuotaObservation) -> Availability:
        return classify_observation(observation)

    @app.post("/v1/decisions/classify", response_model=DecisionClassification)
    async def decision_classify(decision_request: DecisionRequest) -> DecisionClassification:
        return classify_decision(decision_request)

    return app


def _authorize_model_gateway(request: Request) -> None:
    expected = os.environ.get("FORGE_GATEWAY_KEY")
    if not expected:
        return
    authorization = request.headers.get("authorization", "")
    prefix = "Bearer "
    supplied = authorization[len(prefix) :] if authorization.startswith(prefix) else ""
    if not supplied or not compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid Forge gateway credential")


app = create_app()
