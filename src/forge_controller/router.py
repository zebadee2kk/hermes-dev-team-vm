from __future__ import annotations

from datetime import UTC, datetime

from .models import CostClass, ModelCandidate, ProviderState, RouteRequest


class NoEligibleModel(RuntimeError):
    pass


def _available(candidate: ModelCandidate, now: datetime) -> bool:
    if candidate.state == ProviderState.AVAILABLE:
        return True
    return bool(candidate.retry_at and candidate.retry_at <= now)


def select_candidate(
    request: RouteRequest,
    candidates: list[ModelCandidate],
    now: datetime | None = None,
) -> ModelCandidate:
    now = now or datetime.now(UTC)
    eligible: list[tuple[float, ModelCandidate]] = []

    for candidate in candidates:
        if not candidate.enabled or not _available(candidate, now):
            continue
        if request.sensitivity not in candidate.accepted_sensitivity:
            continue
        if candidate.cost_class == CostClass.PAID and not request.allow_paid:
            continue
        capability = candidate.capability_scores.get(request.capability, 0.0)
        if capability <= 0:
            continue

        free_bonus = 0.10 if candidate.cost_class == CostClass.FREE_API else 0.0
        local_bonus = 0.15 if request.prefer_local and candidate.cost_class == CostClass.LOCAL else 0.0
        score = (
            capability * 0.55
            + candidate.reliability * 0.20
            + candidate.latency_score * 0.15
            + free_bonus
            + local_bonus
        )
        eligible.append((score, candidate))

    if not eligible:
        raise NoEligibleModel("no policy-compatible model has usable compute")

    eligible.sort(key=lambda item: (-item[0], item[1].id))
    return eligible[0][1]
