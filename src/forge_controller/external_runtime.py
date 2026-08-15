from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from .contracts import TaskCapsule


class ExternalRuntimeKind(StrEnum):
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"
    OPENCODE = "opencode"
    GEMINI_CLI = "gemini_cli"


class ExternalRuntimeRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    runtime: ExternalRuntimeKind
    project_id: str
    task_id: str
    capsule_id: str
    capsule_revision: int = Field(ge=1)
    objective: str
    acceptance: list[str] = Field(min_length=1)
    constraints: dict[str, object] = Field(default_factory=dict)
    workspace_path: str
    allowed_paths: list[str] = Field(default_factory=list)
    capability_grant_refs: list[str] = Field(default_factory=list)
    verification_requirements: list[str] = Field(default_factory=list)
    result_schema: str = "schemas/worker-result.schema.json"
    timeout_seconds: int = Field(default=1800, ge=60, le=14400)


class ExternalRuntimeResult(BaseModel):
    request_id: str
    task_id: str
    capsule_revision: int = Field(ge=1)
    status: str
    changed_artifacts: list[dict[str, object]] = Field(default_factory=list)
    verification: list[dict[str, object]] = Field(default_factory=list)
    anchor_refs: list[str] = Field(default_factory=list)
    trust_envelope_refs: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    block_reason: dict[str, object] | None = None
    residual_risk: list[str] = Field(default_factory=list)
    usage: dict[str, object] = Field(default_factory=dict)


def request_from_capsule(
    capsule: TaskCapsule,
    *,
    runtime: ExternalRuntimeKind,
    workspace_path: str,
    allowed_paths: list[str] | None = None,
    capability_grant_refs: list[str] | None = None,
    timeout_seconds: int = 1800,
) -> ExternalRuntimeRequest:
    """Build a bounded external-runtime handoff from durable Task Capsule state."""
    verification_requirements = list(capsule.verification.required_anchor_types)
    if capsule.verification.independent_review:
        verification_requirements.append("independent_review")

    return ExternalRuntimeRequest(
        runtime=runtime,
        project_id=capsule.project_id,
        task_id=capsule.task_id,
        capsule_id=capsule.capsule_id,
        capsule_revision=capsule.revision,
        objective=capsule.objective,
        acceptance=capsule.acceptance,
        constraints=capsule.constraints,
        workspace_path=workspace_path,
        allowed_paths=allowed_paths or [workspace_path],
        capability_grant_refs=capability_grant_refs or [],
        verification_requirements=verification_requirements,
        timeout_seconds=timeout_seconds,
    )
