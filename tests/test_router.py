from forge_controller.models import Capability, CostClass, ModelCandidate, RouteRequest, Sensitivity
from forge_controller.router import NoEligibleModel, select_candidate


def candidate(identifier: str, score: float, sensitivity: set[Sensitivity], cost=CostClass.FREE_API):
    return ModelCandidate(
        id=identifier,
        provider=identifier.split("/")[0],
        model=identifier,
        cost_class=cost,
        accepted_sensitivity=sensitivity,
        capability_scores={Capability.CODING: score},
        reliability=0.8,
        latency_score=0.8,
    )


def test_best_eligible_free_candidate_wins() -> None:
    request = RouteRequest(capability=Capability.CODING)
    selected = select_candidate(
        request,
        [candidate("a/m1", 0.6, {Sensitivity.PUBLIC}), candidate("b/m2", 0.9, {Sensitivity.PUBLIC})],
    )
    assert selected.id == "b/m2"


def test_public_provider_cannot_receive_confidential() -> None:
    request = RouteRequest(capability=Capability.CODING, sensitivity=Sensitivity.CONFIDENTIAL)
    try:
        select_candidate(request, [candidate("a/m1", 1.0, {Sensitivity.PUBLIC})])
    except NoEligibleModel:
        pass
    else:
        raise AssertionError("router should reject incompatible sensitivity")


def test_paid_candidate_requires_explicit_permission() -> None:
    paid = candidate("paid/m", 1.0, {Sensitivity.PUBLIC}, CostClass.PAID)
    free = candidate("free/m", 0.5, {Sensitivity.PUBLIC})
    selected = select_candidate(RouteRequest(capability=Capability.CODING), [paid, free])
    assert selected.id == "free/m"
