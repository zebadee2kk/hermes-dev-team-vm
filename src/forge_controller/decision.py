from __future__ import annotations

from .models import AuthorityLevel, DecisionClassification, DecisionRequest


def classify_decision(request: DecisionRequest) -> DecisionClassification:
    # Consequence/materiality dominate; confidence reduces uncertainty but never downgrades a hard gate.
    uncertainty = 1.0 - request.confidence
    score = min(
        1.0,
        request.materiality * 0.35
        + request.irreversibility * 0.25
        + request.consequence * 0.30
        + uncertainty * 0.10,
    )

    if request.hard_gate or (request.irreversibility >= 0.85 and request.consequence >= 0.8):
        level = AuthorityLevel.L3
    elif score >= 0.58:
        level = AuthorityLevel.L2
    elif score >= 0.30:
        level = AuthorityLevel.L1
    else:
        level = AuthorityLevel.L0

    return DecisionClassification(
        authority=level,
        autonomous=level in {AuthorityLevel.L0, AuthorityLevel.L1},
        defer_allowed=level != AuthorityLevel.L3,
        score=round(score, 4),
    )
