from datetime import UTC, datetime

from forge_controller.models import ProviderState, QuotaObservation
from forge_controller.quota import classify_observation, parse_delay


def test_parse_provider_duration() -> None:
    assert parse_delay("2m59.5s").total_seconds() == 179.5


def test_groq_style_exhaustion_uses_reset() -> None:
    now = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
    result = classify_observation(
        QuotaObservation(
            provider="groq",
            status_code=429,
            headers={
                "x-ratelimit-remaining-requests": "0",
                "x-ratelimit-reset-requests": "2h",
            },
        ),
        now=now,
    )
    assert result.state == ProviderState.QUOTA_EXHAUSTED
    assert result.retry_at.isoformat() == "2026-08-15T12:00:00+00:00"


def test_credit_exhaustion_is_distinct() -> None:
    result = classify_observation(QuotaObservation(provider="openrouter", status_code=402))
    assert result.state == ProviderState.CREDIT_EXHAUSTED
