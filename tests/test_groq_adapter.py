from datetime import UTC, datetime, timedelta

import httpx
import pytest

from forge_controller.discovery import probationary_deployment
from forge_controller.models import CostClass, ProviderState
from forge_controller.providers.groq import GroqAdapter
from forge_controller.quota import classify_observation


@pytest.mark.asyncio
async def test_groq_model_discovery_is_probationary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-secret"
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {
                        "id": "example-model",
                        "object": "model",
                        "owned_by": "example",
                        "active": True,
                        "context_window": 131072,
                        "max_completion_tokens": 8192,
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        discovered = await GroqAdapter().discover_models(api_key="test-secret", client=client)

    assert len(discovered) == 1
    deployment = probationary_deployment(
        discovered[0],
        account_ref="free-account",
        tier="free",
        endpoint="https://api.groq.com/openai/v1",
        cost_class=CostClass.FREE_API,
    )
    assert deployment.state == ProviderState.QUARANTINED
    assert not deployment.enabled
    assert deployment.capability_scores == {}
    assert deployment.metadata["probationary"] is True


def test_groq_token_429_uses_token_reset() -> None:
    response = httpx.Response(
        429,
        headers={
            "retry-after": "7",
            "x-ratelimit-remaining-requests": "100",
            "x-ratelimit-reset-requests": "10h",
            "x-ratelimit-remaining-tokens": "0",
            "x-ratelimit-reset-tokens": "7.66s",
        },
        json={"error": {"type": "rate_limit_error"}},
    )
    observation = GroqAdapter().observation_from_response(
        response, model="example", deployment_id="groq/free/example"
    )
    now = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
    availability = classify_observation(observation, now=now)
    assert availability.state == ProviderState.THROTTLED_SHORT
    assert availability.retry_at == now + timedelta(seconds=7.66)
    assert availability.reason == "token quota exhausted"
