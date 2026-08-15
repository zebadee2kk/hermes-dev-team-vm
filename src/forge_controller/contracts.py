from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from .models import Capability, CostClass, ProviderState, Sensitivity


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PRODUCTION = "production"


class VerificationPlan(BaseModel):
    risk_level: RiskLevel = RiskLevel.LOW
    required_anchor_types: list[str] = Field(default_factory=list)
    independent_review: bool = False


class TaskCapsule(BaseModel):
    capsule_id: str = Field(default_factory=lambda: str(uuid4()))
    revision: int = Field(default=1, ge=1)
    project_id: str
    task_id: str
    kanban_task_id: str | int | None = None
    objective: str
    acceptance: list[str] = Field(min_length=1)
    constraints: dict[str, object] = Field(default_factory=dict)
    graph_refs: list[str] = Field(default_factory=list)
    workspace: dict[str, object] = Field(default_factory=dict)
    attempt: dict[str, object] = Field(default_factory=lambda: {"number": 1, "max_attempts": 3})
    previous_results: list[dict[str, object]] = Field(default_factory=list)
    verification: VerificationPlan = Field(default_factory=VerificationPlan)
    capability_requirements: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, object]] = Field(default_factory=list)
    residual_risk: list[str] = Field(default_factory=list)


class RealityAnchor(BaseModel):
    anchor_id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    task_id: str
    type: str
    claim_ref: str
    executor: str | None = None
    workspace_revision: str | None = None
    environment: dict[str, object] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    result: dict[str, object] = Field(default_factory=dict)
    artifact_refs: list[str] = Field(default_factory=list)
    reproduce: str | None = None
    stale: bool = False


class TrustEnvelope(BaseModel):
    envelope_id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    task_id: str | None = None
    content_ref: str
    source: dict[str, object]
    trust: str
    taint: list[str] = Field(default_factory=list)
    data_sensitivity: Sensitivity = Sensitivity.PUBLIC
    integrity_hash: str | None = None
    injection_findings: list[dict[str, object]] = Field(default_factory=list)
    parent_refs: list[str] = Field(default_factory=list)
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InferenceDeployment(BaseModel):
    deployment_id: str
    provider: str
    model: str
    account_ref: str | None = None
    tier: str = "unknown"
    endpoint: str
    credential_binding: str | None = None
    enabled: bool = True
    state: ProviderState = ProviderState.AVAILABLE
    retry_at: datetime | None = None
    cost_class: CostClass = CostClass.UNKNOWN
    accepted_sensitivity: set[Sensitivity] = Field(default_factory=lambda: {Sensitivity.PUBLIC})
    capability_scores: dict[Capability, float] = Field(default_factory=dict)
    reliability: float = Field(default=0.5, ge=0, le=1)
    latency_score: float = Field(default=0.5, ge=0, le=1)
    development_only: bool = False
    terms_evidence_ref: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
