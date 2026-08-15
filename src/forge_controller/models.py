from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ProviderState(StrEnum):
    AVAILABLE = "AVAILABLE"
    THROTTLED_SHORT = "THROTTLED_SHORT"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    CREDIT_EXHAUSTED = "CREDIT_EXHAUSTED"
    PROVIDER_DEGRADED = "PROVIDER_DEGRADED"
    OFFLINE = "OFFLINE"
    AUTH_FAILED = "AUTH_FAILED"
    POLICY_BLOCKED = "POLICY_BLOCKED"


class CostClass(StrEnum):
    FREE_API = "free_api"
    LOCAL = "local"
    PAID = "paid"
    TRIAL = "trial"
    PROMOTIONAL = "promotional"


class Sensitivity(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class AuthorityLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class DecisionAction(StrEnum):
    YES = "YES"
    NO = "NO"
    DEFER = "DEFER"
    MORE_INFO = "MORE_INFO"


class Capability(StrEnum):
    FAST = "fast"
    REASONING = "reasoning"
    CODING = "coding"
    REVIEW = "review"
    RESEARCH = "research"
    DOCUMENTATION = "documentation"
    TOOL_USE = "tool_use"


class QuotaObservation(BaseModel):
    provider: str
    model: str | None = None
    status_code: int | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    error_code: str | None = None
    observed_at: datetime = Field(default_factory=datetime.utcnow)


class Availability(BaseModel):
    state: ProviderState
    retry_at: datetime | None = None
    reason: str
    confidence: float = Field(default=0.5, ge=0, le=1)


class ModelCandidate(BaseModel):
    id: str
    provider: str
    model: str
    enabled: bool = True
    state: ProviderState = ProviderState.AVAILABLE
    retry_at: datetime | None = None
    cost_class: CostClass = CostClass.FREE_API
    accepted_sensitivity: set[Sensitivity] = Field(default_factory=lambda: {Sensitivity.PUBLIC})
    capability_scores: dict[Capability, float] = Field(default_factory=dict)
    reliability: float = Field(default=0.5, ge=0, le=1)
    latency_score: float = Field(default=0.5, ge=0, le=1)


class RouteRequest(BaseModel):
    capability: Capability
    sensitivity: Sensitivity = Sensitivity.PUBLIC
    allow_paid: bool = False
    prefer_local: bool = False


class DecisionRequest(BaseModel):
    id: str
    question: str
    recommendation: str
    confidence: float = Field(ge=0, le=1)
    materiality: float = Field(ge=0, le=1)
    irreversibility: float = Field(ge=0, le=1)
    consequence: float = Field(ge=0, le=1)
    hard_gate: bool = False


class DecisionClassification(BaseModel):
    authority: AuthorityLevel
    autonomous: bool
    defer_allowed: bool
    score: float
