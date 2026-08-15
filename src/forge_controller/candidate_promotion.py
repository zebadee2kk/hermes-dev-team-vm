from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select

from .knowledge import (
    CandidateEvaluation,
    EvaluationOutcome,
    KnowledgeError,
    KnowledgeStore,
    PromotionPolicy,
    TechnologyCandidate,
    evaluate_promotion,
)
from .persistence import RealityAnchorRow
from .repository import AssuranceRepository


class AnchoredPromotionDecision(BaseModel):
    eligible: bool
    reasons: list[str] = Field(default_factory=list)
    requested_anchor_refs: list[str] = Field(default_factory=list)
    verified_anchor_refs: list[str] = Field(default_factory=list)
    missing_anchor_refs: list[str] = Field(default_factory=list)
    stale_anchor_refs: list[str] = Field(default_factory=list)
    task_mismatch_anchor_refs: list[str] = Field(default_factory=list)


def _passing_real_workload_evaluations(
    candidate: TechnologyCandidate,
    evaluations: list[CandidateEvaluation],
) -> list[CandidateEvaluation]:
    return [
        item
        for item in evaluations
        if item.candidate_id == candidate.candidate_id
        and item.real_workload
        and item.outcome == EvaluationOutcome.PASS
    ]


async def verify_promotion_evidence(
    repository: AssuranceRepository,
    candidate: TechnologyCandidate,
    evaluations: list[CandidateEvaluation],
    *,
    project_id: str,
    policy: PromotionPolicy | None = None,
    now: datetime | None = None,
) -> AnchoredPromotionDecision:
    """Require promotion evidence to resolve to current Forge Reality Anchors.

    The pure knowledge policy remains useful for reporting structural gaps. This guard is for
    the state-changing promotion path: anchor ids in evaluation YAML are not trusted until the
    assurance database proves that they exist, are not stale, belong to this project, and match
    the task that produced the evaluation.
    """

    structural = evaluate_promotion(candidate, evaluations, policy=policy, now=now)
    reasons = list(structural.reasons)
    passing = _passing_real_workload_evaluations(candidate, evaluations)
    task_for_anchor: dict[str, str] = {}
    for evaluation in passing:
        for anchor_ref in evaluation.anchor_refs:
            task_for_anchor[anchor_ref] = evaluation.task_id

    requested = sorted(task_for_anchor)
    if not requested:
        return AnchoredPromotionDecision(eligible=False, reasons=reasons)

    async with repository.sessions() as session:
        rows = (
            await session.execute(
                select(RealityAnchorRow).where(
                    RealityAnchorRow.project_id == project_id,
                    RealityAnchorRow.anchor_id.in_(requested),
                )
            )
        ).scalars().all()

    found = {row.anchor_id: row for row in rows}
    missing = sorted(set(requested) - set(found))
    stale = sorted(anchor_id for anchor_id, row in found.items() if row.stale)
    mismatch = sorted(
        anchor_id
        for anchor_id, row in found.items()
        if row.task_id != task_for_anchor[anchor_id]
    )
    verified = sorted(
        anchor_id
        for anchor_id, row in found.items()
        if not row.stale and row.task_id == task_for_anchor[anchor_id]
    )

    if missing:
        reasons.append("promotion evidence contains missing Reality Anchors")
    if stale:
        reasons.append("promotion evidence contains stale Reality Anchors")
    if mismatch:
        reasons.append("promotion evidence contains task-mismatched Reality Anchors")

    required = (policy or PromotionPolicy()).min_anchor_count
    if len(set(verified)) < required:
        reasons.append("insufficient verified current Reality Anchor evidence")

    return AnchoredPromotionDecision(
        eligible=not reasons,
        reasons=reasons,
        requested_anchor_refs=requested,
        verified_anchor_refs=verified,
        missing_anchor_refs=missing,
        stale_anchor_refs=stale,
        task_mismatch_anchor_refs=mismatch,
    )


async def promote_candidate_with_assurance(
    store: KnowledgeStore,
    repository: AssuranceRepository,
    candidate: TechnologyCandidate,
    evaluations: list[CandidateEvaluation],
    *,
    project_id: str,
    policy: PromotionPolicy | None = None,
    now: datetime | None = None,
) -> TechnologyCandidate:
    decision = await verify_promotion_evidence(
        repository,
        candidate,
        evaluations,
        project_id=project_id,
        policy=policy,
        now=now,
    )
    if not decision.eligible:
        raise KnowledgeError("candidate promotion blocked: " + "; ".join(decision.reasons))
    return store.promote_candidate(candidate, evaluations, policy=policy, now=now)
