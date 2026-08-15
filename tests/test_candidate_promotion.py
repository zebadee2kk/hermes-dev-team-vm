from datetime import UTC, datetime, timedelta

import pytest

from forge_controller.candidate_promotion import (
    promote_candidate_with_assurance,
    verify_promotion_evidence,
)
from forge_controller.contracts import RealityAnchor
from forge_controller.knowledge import (
    CandidateEvaluation,
    CandidateKind,
    CandidateSignalInput,
    CandidateStatus,
    EvaluationOutcome,
    KnowledgeError,
    KnowledgeStore,
    TechnologyCandidate,
    assess_candidate_signal,
)
from forge_controller.persistence import create_schema, make_engine, make_session_factory
from forge_controller.repository import AssuranceRepository


def _candidate(now: datetime) -> TechnologyCandidate:
    signal = assess_candidate_signal(
        CandidateSignalInput(
            primary_source=True,
            concrete_artifact=True,
            reproducible=True,
            production_evidence=True,
        )
    )
    return TechnologyCandidate(
        candidate_id="runtime-candidate",
        name="Runtime candidate",
        kind=CandidateKind.PRIMITIVE,
        status=CandidateStatus.PROBATION,
        problem="Test a bounded leaf-worker runtime.",
        proposed_value="Use an additional execution backend without changing orchestration.",
        evidence_refs=["raw:primary-docs"],
        signal_assessment=signal,
        integration_seam="Hermes leaf-worker runtime",
        test_plan=["Run two real workloads"],
        acceptance=["Current Reality Anchors prove both workloads"],
        probation_started_at=now - timedelta(days=15),
        rollback="Disable the runtime and return the worker lane to forge/coding.",
    )


def _evaluations(candidate: TechnologyCandidate) -> list[CandidateEvaluation]:
    return [
        CandidateEvaluation(
            evaluation_id="E1",
            candidate_id=candidate.candidate_id,
            task_id="T1",
            outcome=EvaluationOutcome.PASS,
            real_workload=True,
            anchor_refs=["RA-1"],
        ),
        CandidateEvaluation(
            evaluation_id="E2",
            candidate_id=candidate.candidate_id,
            task_id="T2",
            outcome=EvaluationOutcome.PASS,
            real_workload=True,
            anchor_refs=["RA-2"],
        ),
    ]


@pytest.fixture
async def repo(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'forge.db'}")
    await create_schema(engine)
    repository = AssuranceRepository(make_session_factory(engine))
    await repository.create_project("forge", "Forge")
    try:
        yield repository
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_fabricated_anchor_ids_do_not_authorise_promotion(repo) -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    candidate = _candidate(now)
    decision = await verify_promotion_evidence(
        repo,
        candidate,
        _evaluations(candidate),
        project_id="forge",
        now=now,
    )

    assert decision.eligible is False
    assert decision.missing_anchor_refs == ["RA-1", "RA-2"]
    assert "promotion evidence contains missing Reality Anchors" in decision.reasons


@pytest.mark.asyncio
async def test_stale_or_wrong_task_anchor_does_not_authorise_promotion(repo) -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    candidate = _candidate(now)
    await repo.record_anchor(
        RealityAnchor(
            anchor_id="RA-1",
            project_id="forge",
            task_id="T1",
            type="test",
            claim_ref="candidate:runtime-candidate:E1",
            stale=True,
        )
    )
    await repo.record_anchor(
        RealityAnchor(
            anchor_id="RA-2",
            project_id="forge",
            task_id="OTHER",
            type="test",
            claim_ref="candidate:runtime-candidate:E2",
        )
    )

    decision = await verify_promotion_evidence(
        repo,
        candidate,
        _evaluations(candidate),
        project_id="forge",
        now=now,
    )

    assert decision.eligible is False
    assert decision.stale_anchor_refs == ["RA-1"]
    assert decision.task_mismatch_anchor_refs == ["RA-2"]


@pytest.mark.asyncio
async def test_assurance_guard_promotes_only_with_current_task_bound_anchors(repo, tmp_path) -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    candidate = _candidate(now)
    for anchor_id, task_id in (("RA-1", "T1"), ("RA-2", "T2")):
        await repo.record_anchor(
            RealityAnchor(
                anchor_id=anchor_id,
                project_id="forge",
                task_id=task_id,
                type="test",
                claim_ref=f"candidate:runtime-candidate:{task_id}",
                result={"passed": True},
            )
        )

    store = KnowledgeStore(tmp_path / "knowledge")
    promoted = await promote_candidate_with_assurance(
        store,
        repo,
        candidate,
        _evaluations(candidate),
        project_id="forge",
        now=now,
    )

    assert promoted.status == CandidateStatus.PROMOTED


@pytest.mark.asyncio
async def test_assurance_guard_refuses_store_mutation_when_evidence_is_missing(repo, tmp_path) -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    candidate = _candidate(now)
    store = KnowledgeStore(tmp_path / "knowledge")

    with pytest.raises(KnowledgeError, match="missing Reality Anchors"):
        await promote_candidate_with_assurance(
            store,
            repo,
            candidate,
            _evaluations(candidate),
            project_id="forge",
            now=now,
        )
    assert not (store.candidates_dir / f"{candidate.candidate_id}.yaml").exists()
