from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from forge_controller.knowledge import (
    CandidateEvaluation,
    CandidateKind,
    CandidateSignalInput,
    CandidateStatus,
    ClaimOrigin,
    EvaluationOutcome,
    KnowledgeError,
    KnowledgeStore,
    SignalTier,
    TechnologyCandidate,
    WikiClaim,
    WikiPage,
    WikiPageStatus,
    assess_candidate_signal,
    evaluate_promotion,
)


def strong_signal():
    return assess_candidate_signal(
        CandidateSignalInput(
            primary_source=True,
            concrete_artifact=True,
            reproducible=True,
            production_evidence=True,
        )
    )


def test_high_signal_filter_rewards_artifacts_not_hype() -> None:
    strong = assess_candidate_signal(
        CandidateSignalInput(
            primary_source=True,
            concrete_artifact=True,
            reproducible=True,
            production_evidence=True,
            measurable_results=True,
            independent_corroboration=True,
        )
    )
    hype = assess_candidate_signal(
        CandidateSignalInput(
            primary_source=False,
            concrete_artifact=False,
            rumor_only=True,
            marketing_only=True,
        )
    )
    assert strong.tier == SignalTier.TEST
    assert strong.score >= 70
    assert hype.tier == SignalTier.IGNORE
    assert hype.score == 0


def test_technology_candidate_requires_signal_assessment() -> None:
    with pytest.raises(ValidationError):
        TechnologyCandidate(
            candidate_id="missing-signal",
            name="Missing signal",
            kind=CandidateKind.WRAPPER,
            problem="Unknown",
            proposed_value="Unknown",
            evidence_refs=["raw:source"],
            integration_seam="none",
            test_plan=["test"],
            acceptance=["pass"],
        )


def test_raw_sources_are_immutable_and_wiki_claims_are_grounded(tmp_path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    source = store.add_raw_source(
        source_id="karpathy-llm-wiki",
        content=b"immutable source",
        trust_envelope_ref="TE-1",
        source_url="https://gist.github.com/karpathy/example",
    )
    assert source.sha256

    page = WikiPage(
        slug="patterns/compiled-knowledge",
        title="Compiled knowledge",
        summary="Persistent derivative knowledge compiled from immutable sources.",
        about=["knowledge architecture"],
        status=WikiPageStatus.ACTIVE,
        claims=[
            WikiClaim(
                claim_id="C1",
                text="The wiki is a persistent derivative artifact.",
                origin=ClaimOrigin.ASSERTED,
                source_refs=["raw:karpathy-llm-wiki"],
            )
        ],
    )
    path = store.compile_page(page)
    content = path.read_text()
    assert "raw:karpathy-llm-wiki" in content
    assert "derived_from:" in content
    assert "patterns/compiled-knowledge" in (store.wiki_dir / "index.md").read_text()

    with pytest.raises(KnowledgeError):
        store.add_raw_source(
            source_id="karpathy-llm-wiki",
            content=b"changed source",
            trust_envelope_ref="TE-2",
        )


def test_wiki_cannot_ground_claims_in_other_wiki_pages() -> None:
    with pytest.raises(ValidationError):
        WikiClaim(
            claim_id="C1",
            text="Recursive folklore must not become truth.",
            origin=ClaimOrigin.INFERRED,
            source_refs=["wiki:patterns/compiled-knowledge"],
        )


def test_unknown_raw_source_blocks_compilation(tmp_path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    page = WikiPage(
        slug="broken",
        title="Broken",
        summary="Unknown source.",
        about=["test"],
        claims=[
            WikiClaim(
                claim_id="C1",
                text="Unsupported.",
                origin=ClaimOrigin.ASSERTED,
                source_refs=["raw:missing"],
            )
        ],
    )
    with pytest.raises(KnowledgeError):
        store.compile_page(page)


def test_search_and_lint_are_plain_file_deterministic(tmp_path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge")
    store.add_raw_source(
        source_id="source-1",
        content=b"source",
        trust_envelope_ref="TE-1",
    )
    store.compile_page(
        WikiPage(
            slug="mcp",
            title="MCP",
            summary="Stateless tool protocol.",
            about=["MCP"],
            status=WikiPageStatus.ACTIVE,
            claims=[
                WikiClaim(
                    claim_id="C1",
                    text="MCP provides a protocol for agent tool access.",
                    origin=ClaimOrigin.ASSERTED,
                    source_refs=["raw:source-1"],
                )
            ],
            links=["missing-page"],
        )
    )
    assert store.search("protocol tool") == ["mcp"]
    lint = store.lint()
    assert "mcp->missing-page" in lint.broken_links
    assert "mcp" in lint.orphan_pages


def _candidate(now: datetime) -> TechnologyCandidate:
    return TechnologyCandidate(
        candidate_id="new-primitive",
        name="New Primitive",
        kind=CandidateKind.PRIMITIVE,
        status=CandidateStatus.PROBATION,
        problem="Improve durable agent execution.",
        proposed_value="Reduce glue and improve reliability.",
        evidence_refs=["raw:primary-docs"],
        signal_assessment=strong_signal(),
        integration_seam="MCP boundary",
        test_plan=["Run against a real project workflow"],
        acceptance=["No regression in security, tracing, cost or task completion"],
        probation_started_at=now - timedelta(days=15),
        rollback="Remove adapter and restore previous implementation.",
    )


def _passing_evaluations(candidate: TechnologyCandidate) -> list[CandidateEvaluation]:
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


def test_candidate_promotion_requires_real_workload_anchors_and_probation() -> None:
    now = datetime(2026, 8, 15, tzinfo=UTC)
    candidate = _candidate(now)
    decision = evaluate_promotion(candidate, _passing_evaluations(candidate), now=now)
    assert decision.eligible is True
    assert decision.reasons == []


def test_candidate_failure_blocks_promotion() -> None:
    now = datetime(2026, 8, 15, tzinfo=UTC)
    candidate = _candidate(now)
    evaluations = [
        CandidateEvaluation(
            evaluation_id="E1",
            candidate_id=candidate.candidate_id,
            task_id="T1",
            outcome=EvaluationOutcome.PASS,
            real_workload=True,
            anchor_refs=["RA-1", "RA-2"],
        ),
        CandidateEvaluation(
            evaluation_id="E2",
            candidate_id=candidate.candidate_id,
            task_id="T2",
            outcome=EvaluationOutcome.FAIL,
            real_workload=True,
            anchor_refs=[],
        ),
    ]
    decision = evaluate_promotion(candidate, evaluations, now=now)
    assert decision.eligible is False
    assert "candidate has unresolved failing evaluations" in decision.reasons


def test_direct_promoted_candidate_write_is_rejected(tmp_path) -> None:
    now = datetime(2026, 8, 15, tzinfo=UTC)
    store = KnowledgeStore(tmp_path / "knowledge")
    candidate = _candidate(now).model_copy(update={"status": CandidateStatus.PROMOTED})
    with pytest.raises(KnowledgeError, match="promote_candidate"):
        store.save_candidate(candidate)


def test_promote_candidate_is_the_controlled_state_transition(tmp_path) -> None:
    now = datetime(2026, 8, 15, tzinfo=UTC)
    store = KnowledgeStore(tmp_path / "knowledge")
    candidate = _candidate(now)
    promoted = store.promote_candidate(
        candidate,
        _passing_evaluations(candidate),
        now=now,
    )
    assert promoted.status == CandidateStatus.PROMOTED
    assert promoted.promoted_at == now
    stored = (store.candidates_dir / f"{candidate.candidate_id}.yaml").read_text()
    assert "status: promoted" in stored
