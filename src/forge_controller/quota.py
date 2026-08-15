from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from .models import Availability, ProviderState, QuotaObservation

_DURATION = re.compile(r"(?:(?P<h>\d+(?:\.\d+)?)h)?(?:(?P<m>\d+(?:\.\d+)?)m)?(?:(?P<s>\d+(?:\.\d+)?)s)?$")


def _now() -> datetime:
    return datetime.now(UTC)


def parse_delay(value: str | None) -> timedelta | None:
    if not value:
        return None
    value = value.strip()
    try:
        return timedelta(seconds=float(value))
    except ValueError:
        pass
    match = _DURATION.fullmatch(value)
    if not match:
        return None
    parts = {k: float(v or 0) for k, v in match.groupdict().items()}
    return timedelta(hours=parts["h"], minutes=parts["m"], seconds=parts["s"])


def _rate_limit_state(delay: timedelta) -> ProviderState:
    return ProviderState.THROTTLED_SHORT if delay <= timedelta(hours=1) else ProviderState.QUOTA_EXHAUSTED


def classify_observation(obs: QuotaObservation, now: datetime | None = None) -> Availability:
    now = now or _now()
    headers = {k.lower(): v for k, v in obs.headers.items()}
    status = obs.status_code

    if status in (401, 403):
        return Availability(state=ProviderState.AUTH_FAILED, reason=f"HTTP {status}", confidence=0.95)
    if status == 402:
        return Availability(state=ProviderState.CREDIT_EXHAUSTED, reason="insufficient credit", confidence=0.95)
    if status in (502, 503, 504) or obs.error_code in {"capacity_exceeded", "provider_unavailable"}:
        delay = parse_delay(headers.get("retry-after")) or timedelta(minutes=2)
        return Availability(
            state=ProviderState.PROVIDER_DEGRADED,
            retry_at=now + delay,
            reason="provider unavailable/capacity constrained",
            confidence=0.8,
        )
    if status == 429:
        retry = parse_delay(headers.get("retry-after"))
        request_reset = parse_delay(headers.get("x-ratelimit-reset-requests"))
        token_reset = parse_delay(headers.get("x-ratelimit-reset-tokens"))
        remaining_requests = headers.get("x-ratelimit-remaining-requests")
        remaining_tokens = headers.get("x-ratelimit-remaining-tokens")

        if remaining_requests == "0" and request_reset:
            return Availability(
                state=_rate_limit_state(request_reset),
                retry_at=now + request_reset,
                reason="request quota exhausted",
                confidence=0.95,
            )
        if remaining_tokens == "0" and token_reset:
            return Availability(
                state=_rate_limit_state(token_reset),
                retry_at=now + token_reset,
                reason="token quota exhausted",
                confidence=0.95,
            )
        delay = retry or request_reset or token_reset or timedelta(minutes=1)
        return Availability(
            state=_rate_limit_state(delay),
            retry_at=now + delay,
            reason="rate limited",
            confidence=0.8,
        )
    if status is not None and status >= 500:
        return Availability(
            state=ProviderState.PROVIDER_DEGRADED,
            retry_at=now + timedelta(minutes=1),
            reason=f"HTTP {status}",
            confidence=0.6,
        )
    return Availability(state=ProviderState.AVAILABLE, reason="successful/no limiting signal", confidence=0.7)
