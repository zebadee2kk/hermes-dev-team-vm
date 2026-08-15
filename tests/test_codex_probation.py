from datetime import UTC, datetime
from pathlib import Path

import yaml

from forge_controller.knowledge import (
    CandidateStatus,
    SignalTier,
    TechnologyCandidate,
    evaluate_promotion,
)

ROOT = Path(__file__).parents[1]
CANDIDATE = ROOT / "knowledge/candidates/hermes-codex-app-server-runtime.yaml"
PROBATION = ROOT / "config/probation/hermes-codex-app-server-runtime.yaml"


def test_codex_runtime_is_a_high_signal_quarantined_probation_candidate() -> None:
    candidate = TechnologyCandidate.model_validate(yaml.safe_load(CANDIDATE.read_text()))
    assert candidate.status == CandidateStatus.PROBATION
    assert candidate.signal_assessment.tier == SignalTier.TEST
    assert candidate.signal_assessment.score >= 70
    assert candidate.probation_started_at == datetime(2026, 8, 15, 20, 36, tzinfo=UTC)
    assert candidate.promoted_at is None
    assert candidate.rollback
    assert candidate.replacement_scope == ["engineering leaf-worker turns only"]


def test_probation_clock_cannot_replace_evidence() -> None:
    candidate = TechnologyCandidate.model_validate(yaml.safe_load(CANDIDATE.read_text()))
    before_gate = evaluate_promotion(
        candidate,
        [],
        now=datetime(2026, 8, 29, 20, 35, 59, tzinfo=UTC),
    )
    assert before_gate.eligible is False
    assert "minimum probation period has not elapsed" in before_gate.reasons

    after_time_gate = evaluate_promotion(
        candidate,
        [],
        now=datetime(2026, 8, 29, 20, 36, tzinfo=UTC),
    )
    assert after_time_gate.eligible is False
    assert "insufficient passing real-workload evaluations" in after_time_gate.reasons
    assert "insufficient independent Reality Anchor evidence" in after_time_gate.reasons


def test_codex_probation_does_not_enable_external_adapter_or_orchestrator() -> None:
    lanes = yaml.safe_load((ROOT / "config/worker-lanes.yaml").read_text())
    probation = yaml.safe_load(PROBATION.read_text())

    assert lanes["external_runtime_adapters"]["codex"] == "disabled"
    assert probation["runtime"]["external_runtime_adapter_enabled"] is False
    assert probation["probation"]["default_runtime_must_remain"] == "auto"
    assert probation["probation"]["allowed_lanes"] == ["engineering"]
    assert "forge-orchestrator" in probation["probation"]["forbidden_lanes"]
    assert probation["probation"]["max_concurrent_trial_workers"] == 1


def test_probation_requires_outer_boundary_and_database_backed_evidence() -> None:
    probation = yaml.safe_load(PROBATION.read_text())
    assert probation["preflight"]["require_outer_worker_boundary_before_real_workload"] is True
    assert probation["preflight"]["require_no_control_plane_secrets"] is True
    assert probation["promotion"]["requires_database_backed_anchor_verification"] is True
    assert probation["rollback"]["preserve_task_capsule"] is True
    assert probation["rollback"]["redispatch_through_standard_lane"] is True


def test_preflight_is_non_mutating_and_does_not_enable_runtime() -> None:
    script = (ROOT / "integrations/hermes/codex-probation-preflight.py").read_text()
    assert '"mutated_configuration": False' in script
    assert "generate-json-schema" in script
    assert "model.openai_runtime" not in script
    assert "/codex-runtime" not in script
