from datetime import UTC, datetime

import pytest

from forge_controller.contracts import InferenceDeployment
from forge_controller.deployment_policy import (
    DeploymentQualification,
    DeploymentQualificationError,
    qualify_deployment,
)
from forge_controller.models import Capability, CostClass, ProviderState, Sensitivity
from forge_controller.retry_policy import exponential_probe_delay, probe_after_reset


def probationary(*, active: bool = True) -> InferenceDeployment:
    return InferenceDeployment(
        deployment_id="groq/free/model",
        provider="groq",
        model="model",
        account_ref="free",
        tier="free",
        endpoint="https://api.groq.com/openai/v1",
        credential_binding="provider:groq:free",
        enabled=False,
        state=ProviderState.QUARANTINED,
        cost_class=CostClass.UNKNOWN,
        accepted_sensitivity={Sensitivity.PUBLIC},
        capability_scores={},
        metadata={"probationary": True, "discovered_active": active},
    )


def qualification(cost: CostClass = CostClass.FREE_API) -> DeploymentQualification:
    return DeploymentQualification(
        terms_evidence_ref="evidence://groq/free-terms-2026-08-15",
        smoke_test_passed=True,
        accepted_sensitivity={Sensitivity.PUBLIC},
        capability_scores={Capability.CODING: 0.82, Capability.FAST: 0.75},
        cost_class=cost,
    )


def test_qualification_is_the_only_path_out_of_discovery_quarantine() -> None:
    promoted = qualify_deployment(probationary(), qualification())
    assert promoted.enabled
    assert promoted.state == ProviderState.AVAILABLE
    assert promoted.terms_evidence_ref
    assert promoted.capability_scores[Capability.CODING] == 0.82
    assert promoted.metadata["probationary"] is False


def test_inactive_or_failed_smoke_test_cannot_be_promoted() -> None:
    with pytest.raises(DeploymentQualificationError):
        qualify_deployment(probationary(active=False), qualification())

    failed = qualification().model_copy(update={"smoke_test_passed": False})
    with pytest.raises(DeploymentQualificationError):
        qualify_deployment(probationary(), failed)


def test_trial_and_promotional_capacity_is_development_only() -> None:
    for cost in (CostClass.TRIAL, CostClass.PROMOTIONAL):
        promoted = qualify_deployment(probationary(), qualification(cost))
        assert promoted.development_only is True


def test_reset_probe_jitter_never_probes_before_provider_reset_and_is_stable() -> None:
    reset = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
    first = probe_after_reset("groq/free/model", reset, max_jitter_seconds=30)
    second = probe_after_reset("groq/free/model", reset, max_jitter_seconds=30)
    assert first == second
    assert reset <= first <= reset.replace(second=30)


def test_exponential_probe_backoff_is_bounded_and_deterministic() -> None:
    first = exponential_probe_delay("groq/free/model", 1)
    fifth = exponential_probe_delay("groq/free/model", 5)
    capped = exponential_probe_delay("groq/free/model", 20)
    assert first.total_seconds() >= 1
    assert fifth > first
    assert capped.total_seconds() <= 60
    assert capped == exponential_probe_delay("groq/free/model", 20)
