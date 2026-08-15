from forge_controller.decision import classify_decision
from forge_controller.models import AuthorityLevel, DecisionRequest


def decision(**overrides):
    values = {
        "id": "D1",
        "question": "Use library A?",
        "recommendation": "yes",
        "confidence": 0.9,
        "materiality": 0.1,
        "irreversibility": 0.1,
        "consequence": 0.1,
        "hard_gate": False,
    }
    values.update(overrides)
    return DecisionRequest(**values)


def test_low_risk_decision_is_autonomous() -> None:
    result = classify_decision(decision())
    assert result.authority == AuthorityLevel.L0
    assert result.autonomous is True


def test_material_decision_requires_owner() -> None:
    result = classify_decision(decision(materiality=0.9, consequence=0.9, irreversibility=0.5))
    assert result.authority == AuthorityLevel.L2
    assert result.autonomous is False


def test_hard_gate_never_allows_defer() -> None:
    result = classify_decision(decision(hard_gate=True))
    assert result.authority == AuthorityLevel.L3
    assert result.defer_allowed is False
