from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from .models import AuthorityLevel, Capability, DecisionAction


class SemanticKind(StrEnum):
    IDEA = "idea"
    REQUIREMENT = "requirement"
    DECISION = "decision"
    COMPONENT = "component"
    INTERFACE = "interface"
    FILE = "file"
    TEST = "test"
    RISK = "risk"
    DOCUMENT = "document"
    CLAIM = "claim"


class SemanticNode(BaseModel):
    node_id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    kind: SemanticKind
    external_ref: str | None = None
    label: str
    data: dict[str, object] = Field(default_factory=dict)
    stale: bool = False


class SemanticEdge(BaseModel):
    edge_id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    source_id: str
    relationship: str
    target_id: str
    metadata: dict[str, object] = Field(default_factory=dict)


class DecisionStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    SUPERSEDED = "SUPERSEDED"


class DecisionRecord(BaseModel):
    decision_id: str
    project_id: str
    task_id: str | None = None
    question: str
    recommendation: str
    authority: AuthorityLevel
    status: DecisionStatus = DecisionStatus.OPEN
    owner_action: DecisionAction | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    blocked_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    supersedes: str | None = None


class CapabilityScoreRecord(BaseModel):
    score_id: str = Field(default_factory=lambda: str(uuid4()))
    deployment_id: str
    capability: Capability
    score: float = Field(ge=0, le=1)
    sample_count: int = Field(default=1, ge=1)
    uncertainty: float = Field(default=1.0, ge=0, le=1)
    source: str = "observed"
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, object] = Field(default_factory=dict)


class LearningStatus(StrEnum):
    QUARANTINED = "QUARANTINED"
    EVALUATING = "EVALUATING"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


class LearningCandidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: str(uuid4()))
    project_id: str
    lesson_type: str
    content: dict[str, object]
    provenance_refs: list[str] = Field(default_factory=list)
    status: LearningStatus = LearningStatus.QUARANTINED
    evaluation: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
