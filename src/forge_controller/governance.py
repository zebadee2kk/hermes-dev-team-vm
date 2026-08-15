from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .assurance import DecisionRecord, DecisionStatus
from .models import AuthorityLevel, DecisionAction, DecisionClassification


class GovernanceError(RuntimeError):
    pass


class DecisionDisposition(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"
    DEFERRED = "deferred"
    NEEDS_INFO = "needs_info"


class DecisionPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str
    project_id: str
    task_id: str | None = None
    authority: AuthorityLevel
    question: str
    recommendation: str
    why_now: str
    yes_effect: str
    no_effect: str
    options: tuple[DecisionAction, ...]


class DecisionTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    disposition: DecisionDisposition
    record: DecisionRecord
    resume_task: bool
    keep_blocked: bool
    request_more_info: bool = False


class DenialDirective(StrEnum):
    RETRY_SAFER_ALTERNATIVE = "retry_safer_alternative"
    ESCALATE_HUMAN = "escalate_human"


class DenialPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    consecutive_before_escalate: int = Field(default=3, ge=1)
    total_before_escalate: int = Field(default=10, ge=1)


class DenialState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signature: str
    consecutive: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    last_reason: str | None = None
    last_denied_at: datetime | None = None


class DenialOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: DenialState
    directive: DenialDirective
    owner_interrupt_required: bool


def build_decision_prompt(
    record: DecisionRecord,
    classification: DecisionClassification,
    *,
    why_now: str,
    yes_effect: str,
    no_effect: str,
) -> DecisionPrompt:
    if record.authority != classification.authority:
        raise GovernanceError("decision record/classification authority mismatch")
    options = [DecisionAction.YES, DecisionAction.NO]
    if classification.defer_allowed:
        options.append(DecisionAction.DEFER)
    options.append(DecisionAction.MORE_INFO)
    return DecisionPrompt(
        decision_id=record.decision_id,
        project_id=record.project_id,
        task_id=record.task_id,
        authority=record.authority,
        question=record.question,
        recommendation=record.recommendation,
        why_now=why_now,
        yes_effect=yes_effect,
        no_effect=no_effect,
        options=tuple(options),
    )


def apply_owner_action(
    record: DecisionRecord,
    classification: DecisionClassification,
    action: DecisionAction,
    *,
    evidence_refs: list[str] | None = None,
    now: datetime | None = None,
) -> DecisionTransition:
    if record.status is not DecisionStatus.OPEN:
        raise GovernanceError("only open decisions can accept an owner action")
    if record.authority != classification.authority:
        raise GovernanceError("decision record/classification authority mismatch")
    timestamp = now or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise GovernanceError("decision timestamp must be timezone-aware")
    refs = list(dict.fromkeys([*record.evidence_refs, *(evidence_refs or [])]))

    if action is DecisionAction.YES:
        updated = record.model_copy(
            update={
                "status": DecisionStatus.RESOLVED,
                "owner_action": action,
                "evidence_refs": refs,
                "resolved_at": timestamp,
            }
        )
        return DecisionTransition(
            disposition=DecisionDisposition.APPROVED,
            record=updated,
            resume_task=True,
            keep_blocked=False,
        )
    if action is DecisionAction.NO:
        updated = record.model_copy(
            update={
                "status": DecisionStatus.RESOLVED,
                "owner_action": action,
                "evidence_refs": refs,
                "resolved_at": timestamp,
            }
        )
        return DecisionTransition(
            disposition=DecisionDisposition.DENIED,
            record=updated,
            resume_task=True,
            keep_blocked=False,
        )
    if action is DecisionAction.DEFER:
        if not classification.defer_allowed:
            raise GovernanceError("DEFER is not allowed for this decision")
        updated = record.model_copy(
            update={
                "owner_action": action,
                "evidence_refs": refs,
            }
        )
        return DecisionTransition(
            disposition=DecisionDisposition.DEFERRED,
            record=updated,
            resume_task=False,
            keep_blocked=True,
        )
    if action is DecisionAction.MORE_INFO:
        updated = record.model_copy(
            update={
                "owner_action": action,
                "evidence_refs": refs,
            }
        )
        return DecisionTransition(
            disposition=DecisionDisposition.NEEDS_INFO,
            record=updated,
            resume_task=False,
            keep_blocked=True,
            request_more_info=True,
        )
    raise GovernanceError(f"unsupported owner action: {action}")


def record_policy_denial(
    state: DenialState,
    *,
    reason: str,
    policy: DenialPolicy | None = None,
    material: bool = False,
    now: datetime | None = None,
) -> DenialOutcome:
    active_policy = policy or DenialPolicy()
    timestamp = now or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise GovernanceError("denial timestamp must be timezone-aware")
    updated = state.model_copy(
        update={
            "consecutive": state.consecutive + 1,
            "total": state.total + 1,
            "last_reason": reason,
            "last_denied_at": timestamp,
        }
    )
    escalate = (
        material
        or updated.consecutive >= active_policy.consecutive_before_escalate
        or updated.total >= active_policy.total_before_escalate
    )
    return DenialOutcome(
        state=updated,
        directive=(
            DenialDirective.ESCALATE_HUMAN
            if escalate
            else DenialDirective.RETRY_SAFER_ALTERNATIVE
        ),
        owner_interrupt_required=escalate,
    )


def record_safe_alternative_success(state: DenialState) -> DenialState:
    """A successful safer path breaks the consecutive-denial streak but keeps lifetime recurrence."""
    return state.model_copy(update={"consecutive": 0, "last_reason": None})
