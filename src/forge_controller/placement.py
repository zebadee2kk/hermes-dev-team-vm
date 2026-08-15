from __future__ import annotations

from datetime import UTC, datetime

from .models import ModelCandidate, QuotaObservation, RouteRequest
from .quota import classify_observation
from .repository import AssuranceRepository
from .router import NoEligibleModel, select_candidate


class WaitingForCompute(NoEligibleModel):
    def __init__(self, retry_at: datetime | None) -> None:
        self.retry_at = retry_at
        message = "no policy-compatible deployment has usable compute"
        if retry_at:
            message += f"; next candidate re-evaluation at {retry_at.isoformat()}"
        super().__init__(message)


async def place(
    repository: AssuranceRepository,
    request: RouteRequest,
    *,
    now: datetime | None = None,
) -> ModelCandidate:
    now = now or datetime.now(UTC)
    candidates = await repository.list_candidates()
    try:
        return select_candidate(request, candidates, now=now)
    except NoEligibleModel as exc:
        retry_at = await repository.next_retry_at(request, now)
        raise WaitingForCompute(retry_at) from exc


async def observe(
    repository: AssuranceRepository,
    deployment_id: str,
    observation: QuotaObservation,
    *,
    now: datetime | None = None,
) -> None:
    availability = classify_observation(observation, now=now)
    await repository.record_availability(deployment_id, observation, availability)
