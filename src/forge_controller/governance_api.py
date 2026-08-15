from __future__ import annotations

import os
from hmac import compare_digest

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .assurance import DecisionRecord, DecisionStatus
from .contracts import TrustEnvelope
from .decision import classify_decision
from .governance import (
    DecisionPrompt,
    DecisionTransition,
    GovernanceError,
    apply_owner_action,
    build_decision_prompt,
)
from .models import DecisionAction, DecisionClassification, DecisionRequest, Sensitivity
from .repository import AssuranceRepository
from .trust_gateway import SourceDescriptor, TrustGateway, TrustGatewayError

router = APIRouter(prefix="/v1/governance", tags=["governance"])

_API_SOURCE_KINDS = {
    "browser",
    "email",
    "github",
    "github_connector",
    "mcp_external",
    "package_metadata",
    "subagent_output",
    "web",
    "webhook",
}


class TrustIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str
    task_id: str | None = None
    content_ref: str
    content: str
    source: SourceDescriptor
    sensitivity: Sensitivity = Sensitivity.PUBLIC
    parent_envelope_ids: list[str] = Field(default_factory=list, max_length=64)


class DecisionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str
    task_id: str | None = None
    decision: DecisionRequest
    evidence_refs: list[str] = Field(default_factory=list, max_length=64)
    blocked_refs: list[str] = Field(default_factory=list, max_length=64)
    why_now: str
    yes_effect: str
    no_effect: str


class DecisionCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record: DecisionRecord
    classification: DecisionClassification
    prompt: DecisionPrompt


class OwnerActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: DecisionAction
    evidence_refs: list[str] = Field(default_factory=list, max_length=64)


def _repository(request: Request) -> AssuranceRepository:
    return request.app.state.repository


def _authorize_control(request: Request) -> None:
    expected = os.environ.get("FORGE_CONTROL_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Forge control credential is not configured")
    authorization = request.headers.get("authorization", "")
    prefix = "Bearer "
    supplied = authorization[len(prefix) :] if authorization.startswith(prefix) else ""
    if not supplied or not compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid Forge control credential")


@router.post("/trust/ingest", response_model=TrustEnvelope)
async def trust_ingest(payload: TrustIngestRequest, request: Request) -> TrustEnvelope:
    _authorize_control(request)
    if payload.source.kind not in _API_SOURCE_KINDS:
        raise HTTPException(
            status_code=403,
            detail="trusted owner/control-plane source classes are not accepted through generic ingestion",
        )
    repository = _repository(request)
    try:
        parents = await repository.trust_envelopes(payload.parent_envelope_ids)
        envelope = TrustGateway().ingest(
            project_id=payload.project_id,
            task_id=payload.task_id,
            content_ref=payload.content_ref,
            content=payload.content,
            source=payload.source,
            sensitivity=payload.sensitivity,
            parent_envelopes=parents,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, TrustGatewayError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await repository.record_trust_envelope(envelope)
    await repository.append_event(
        "trust.ingested",
        project_id=envelope.project_id,
        task_id=envelope.task_id,
        payload={
            "envelope_id": envelope.envelope_id,
            "trust": envelope.trust,
            "taint": envelope.taint,
            "source_kind": payload.source.kind,
        },
    )
    return envelope


@router.post("/decisions", response_model=DecisionCreateResponse)
async def decision_create(
    payload: DecisionCreateRequest,
    request: Request,
) -> DecisionCreateResponse:
    _authorize_control(request)
    classification = classify_decision(payload.decision)
    proposed = DecisionRecord(
        decision_id=payload.decision.id,
        project_id=payload.project_id,
        task_id=payload.task_id,
        question=payload.decision.question,
        recommendation=payload.decision.recommendation,
        authority=classification.authority,
        classification=classification,
        evidence_refs=list(dict.fromkeys(payload.evidence_refs)),
        blocked_refs=list(dict.fromkeys(payload.blocked_refs)),
    )
    repository = _repository(request)
    existing = await repository.get_decision(proposed.decision_id)
    if existing is not None:
        if existing.status is not DecisionStatus.OPEN:
            raise HTTPException(status_code=409, detail="decision id already resolved or superseded")
        if not _same_decision_intent(existing, proposed):
            raise HTTPException(status_code=409, detail="decision id already exists with different content")
        record = existing
    else:
        record = proposed
        await repository.save_decision(record)
    await repository.append_event(
        "decision.opened",
        project_id=record.project_id,
        task_id=record.task_id,
        payload={
            "decision_id": record.decision_id,
            "authority": record.authority.value,
            "defer_allowed": classification.defer_allowed,
        },
        idempotency_key=f"decision.opened:{record.decision_id}",
    )
    prompt = build_decision_prompt(
        record,
        classification,
        why_now=payload.why_now,
        yes_effect=payload.yes_effect,
        no_effect=payload.no_effect,
    )
    return DecisionCreateResponse(record=record, classification=classification, prompt=prompt)


@router.get("/decisions/{decision_id}", response_model=DecisionRecord)
async def decision_get(decision_id: str, request: Request) -> DecisionRecord:
    _authorize_control(request)
    record = await _repository(request).get_decision(decision_id)
    if record is None:
        raise HTTPException(status_code=404, detail="decision not found")
    return record


@router.post("/decisions/{decision_id}/owner-action", response_model=DecisionTransition)
async def decision_owner_action(
    decision_id: str,
    payload: OwnerActionRequest,
    request: Request,
) -> DecisionTransition:
    _authorize_control(request)
    repository = _repository(request)
    record = await repository.get_decision(decision_id)
    if record is None:
        raise HTTPException(status_code=404, detail="decision not found")
    if record.classification is None:
        raise HTTPException(status_code=409, detail="decision lacks persisted classification context")
    try:
        transition = apply_owner_action(
            record,
            record.classification,
            payload.action,
            evidence_refs=payload.evidence_refs,
        )
    except GovernanceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await repository.save_decision(transition.record)
    await repository.append_event(
        "decision.owner_action",
        project_id=record.project_id,
        task_id=record.task_id,
        payload={
            "decision_id": decision_id,
            "action": payload.action.value,
            "disposition": transition.disposition.value,
            "resume_task": transition.resume_task,
            "keep_blocked": transition.keep_blocked,
        },
    )
    return transition


def _same_decision_intent(first: DecisionRecord, second: DecisionRecord) -> bool:
    fields = (
        "decision_id",
        "project_id",
        "task_id",
        "question",
        "recommendation",
        "authority",
        "classification",
        "evidence_refs",
        "blocked_refs",
    )
    return all(getattr(first, field) == getattr(second, field) for field in fields)
