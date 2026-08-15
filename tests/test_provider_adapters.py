from datetime import UTC, datetime

import httpx
import pytest

from forge_controller.discovery import probationary_deployment
from forge_controller.models import CostClass, ProviderState
from forge_controller.providers.gemini import GeminiAdapter
from forge_controller.providers.openai_compatible import OpenAICompatibleAdapter
from forge_controller.providers.openrouter import OpenRouterAdapter
from forge_controller.providers.sambanova import SambaNovaAdapter
from forge_controller.quota import classify_observation


@pytest.mark.asyncio
async def test_generic_openai_compatible_discovery_and_error_normalization() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "model-a",
                        "owned_by": "vendor",
                        "context_length": 32768,
                        "max_completion_tokens": 4096,
                    }
                ]
            },
        )

    adapter = OpenAICompatibleAdapter(
        provider="example",
        models_url="https://example.invalid/v1/models",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        models = await adapter.discover_models(api_key="secret", client=client)

    assert models[0].model_id == "model-a"
    assert models[0].context_window == 32768
    assert models[0].max_completion_tokens == 4096

    response = httpx.Response(
        429,
        json={"error": {"metadata": {"error_type": "rate_limit_exceeded"}}},
    )
    observation = adapter.observation_from_response(response)
    assert observation.error_code == "rate_limit_exceeded"


@pytest.mark.asyncio
async def test_openrouter_uses_user_filtered_catalogue_and_stays_quarantined() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/models/user"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "vendor/model:free",
                        "context_length": 65536,
                        "pricing": {"prompt": "0", "completion": "0"},
                        "top_provider": {"max_completion_tokens": 8192},
                        "supported_parameters": ["tools"],
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        models = await OpenRouterAdapter().discover_models(api_key="secret", client=client)

    deployment = probationary_deployment(
        models[0],
        account_ref="free-account",
        tier="free",
        endpoint="https://openrouter.ai/api/v1",
        cost_class=CostClass.FREE_API,
    )
    assert deployment.state == ProviderState.QUARANTINED
    assert not deployment.enabled
    assert deployment.metadata["pricing"]["prompt"] == "0"
    assert deployment.metadata["supported_parameters"] == ["tools"]


@pytest.mark.asyncio
async def test_gemini_native_discovery_paginates_and_marks_non_generation_models_inactive() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["x-goog-api-key"] == "secret"
        assert request.headers["x-goog-api-client"] == "hermes-forge/0.3.0"
        if calls == 1:
            assert request.url.params["pageSize"] == "1000"
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/gemini-example-001",
                            "baseModelId": "gemini-example",
                            "version": "001",
                            "inputTokenLimit": 1000000,
                            "outputTokenLimit": 8192,
                            "supportedGenerationMethods": ["generateContent"],
                            "thinking": True,
                        }
                    ],
                    "nextPageToken": "next",
                },
            )
        assert request.url.params["pageToken"] == "next"
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/embedding-example",
                        "inputTokenLimit": 2048,
                        "supportedGenerationMethods": ["embedContent"],
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        models = await GeminiAdapter().discover_models(api_key="secret", client=client)

    assert [model.model_id for model in models] == ["gemini-example", "embedding-example"]
    assert models[0].active is True
    assert models[0].context_window == 1000000
    assert models[0].max_completion_tokens == 8192
    assert models[0].metadata["thinking"] is True
    assert models[1].active is False


def test_sambanova_deprecated_and_unbounded_quota_errors_are_safe_states() -> None:
    adapter = SambaNovaAdapter()
    now = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)

    deprecated = adapter.observation_from_response(
        httpx.Response(410, json={"error": {"code": "model_deprecated"}})
    )
    deprecated_state = classify_observation(deprecated, now=now)
    assert deprecated_state.state == ProviderState.OFFLINE

    exhausted = adapter.observation_from_response(
        httpx.Response(429, json={"error": {"code": "insufficient_quota"}})
    )
    exhausted_state = classify_observation(exhausted, now=now)
    assert exhausted_state.state == ProviderState.QUOTA_EXHAUSTED
    assert exhausted_state.retry_at is None
