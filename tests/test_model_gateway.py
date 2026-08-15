import json

import httpx
import pytest

from forge_controller.contracts import InferenceDeployment
from forge_controller.model_gateway import (
    UnknownForgeModel,
    forward_chat_completion,
    model_catalogue,
)
from forge_controller.models import Capability, CostClass, ProviderState, Sensitivity
from forge_controller.persistence import create_schema, make_engine, make_session_factory
from forge_controller.repository import AssuranceRepository


def deployment(identifier: str, score: float) -> InferenceDeployment:
    provider, account, model = identifier.split("/", 2)
    return InferenceDeployment(
        deployment_id=identifier,
        provider=provider,
        model=model,
        account_ref=account,
        tier="free",
        endpoint=f"https://{provider}.invalid/v1",
        credential_binding=f"provider:{provider}:{account}",
        enabled=True,
        state=ProviderState.AVAILABLE,
        cost_class=CostClass.FREE_API,
        accepted_sensitivity={Sensitivity.PUBLIC},
        capability_scores={Capability.CODING: score},
        terms_evidence_ref="evidence://terms",
    )


@pytest.mark.asyncio
async def test_gateway_replaces_stable_alias_and_fails_over_after_retryable_quota(tmp_path) -> None:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    await create_schema(engine)
    repository = AssuranceRepository(make_session_factory(engine))
    await repository.upsert_deployment(deployment("groq/free/model-a", 0.95))
    await repository.upsert_deployment(deployment("openrouter/free/model-b", 0.80))
    seen_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen_models.append(body["model"])
        assert body["messages"] == [{"role": "user", "content": "hello"}]
        assert request.headers["Authorization"] == "Bearer litellm-secret"
        if len(seen_models) == 1:
            return httpx.Response(429, headers={"retry-after": "30"}, json={"error": "limit"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await forward_chat_completion(
            repository,
            {
                "model": "forge/coding",
                "messages": [{"role": "user", "content": "hello"}],
            },
            litellm_base_url="http://litellm.invalid",
            litellm_master_key="litellm-secret",
            client=client,
        )

    assert seen_models == [
        "forge/deployment/groq/free/model-a",
        "forge/deployment/openrouter/free/model-b",
    ]
    assert result.status_code == 200
    assert result.deployment_id == "openrouter/free/model-b"
    candidates = {candidate.id: candidate for candidate in await repository.list_candidates()}
    assert candidates["groq/free/model-a"].state == ProviderState.THROTTLED_SHORT
    await engine.dispose()


@pytest.mark.asyncio
async def test_gateway_preserves_stream_request_flag_even_when_response_is_buffered(tmp_path) -> None:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'stream.db'}")
    await create_schema(engine)
    repository = AssuranceRepository(make_session_factory(engine))
    await repository.upsert_deployment(deployment("groq/free/model-a", 0.95))

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["stream"] is True
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"data: {\"choices\":[]}\n\ndata: [DONE]\n\n",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await forward_chat_completion(
            repository,
            {"model": "forge/coding", "messages": [], "stream": True},
            litellm_base_url="http://litellm.invalid",
            litellm_master_key="secret",
            client=client,
        )

    assert result.headers["content-type"] == "text/event-stream"
    assert b"[DONE]" in result.content
    await engine.dispose()


def test_catalogue_contains_only_stable_forge_aliases() -> None:
    catalogue = model_catalogue()
    ids = {item["id"] for item in catalogue["data"]}
    assert "forge/coding" in ids
    assert "forge/research" in ids
    assert all(not item.startswith("forge/deployment/") for item in ids)


def test_unknown_model_alias_fails_closed() -> None:
    with pytest.raises(UnknownForgeModel):
        from forge_controller.model_gateway import capability_for_model

        capability_for_model("vendor/surprise-model")
