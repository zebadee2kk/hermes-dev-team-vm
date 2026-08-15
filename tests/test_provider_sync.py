import httpx
import pytest

from forge_controller.contracts import InferenceDeployment
from forge_controller.models import Capability, CostClass, ProviderState, Sensitivity
from forge_controller.persistence import create_schema, make_engine, make_session_factory
from forge_controller.provider_sync import DiscoveryTarget, sync_provider_discovery
from forge_controller.providers.groq import GroqAdapter
from forge_controller.providers.registry import built_in_adapter
from forge_controller.repository import AssuranceRepository


@pytest.mark.asyncio
async def test_discovery_sync_creates_only_new_quarantined_deployments(tmp_path) -> None:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'sync.db'}")
    await create_schema(engine)
    repository = AssuranceRepository(make_session_factory(engine))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "model-a", "active": True},
                    {"id": "model-b", "active": False},
                ]
            },
        )

    target = DiscoveryTarget(
        provider="groq",
        account_ref="free-account",
        tier="free",
        endpoint="https://api.groq.com/openai/v1",
        cost_class=CostClass.FREE_API,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = await sync_provider_discovery(
            repository, GroqAdapter(), target, api_key="secret", client=client
        )
        second = await sync_provider_discovery(
            repository, GroqAdapter(), target, api_key="secret", client=client
        )

    assert first.discovered == 2
    assert first.created == 2
    assert first.inactive == 1
    assert second.created == 0
    assert second.already_known == 2
    candidates = await repository.list_candidates()
    assert len(candidates) == 2
    assert all(candidate.state == ProviderState.QUARANTINED for candidate in candidates)
    assert all(not candidate.enabled for candidate in candidates)
    await engine.dispose()


@pytest.mark.asyncio
async def test_discovery_resync_never_downgrades_known_qualified_deployment(tmp_path) -> None:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'preserve.db'}")
    await create_schema(engine)
    repository = AssuranceRepository(make_session_factory(engine))
    qualified = InferenceDeployment(
        deployment_id="groq/free-account/model-a",
        provider="groq",
        model="model-a",
        account_ref="free-account",
        tier="free",
        endpoint="https://api.groq.com/openai/v1",
        credential_binding="provider:groq:free-account",
        enabled=True,
        state=ProviderState.AVAILABLE,
        cost_class=CostClass.FREE_API,
        accepted_sensitivity={Sensitivity.PUBLIC},
        capability_scores={Capability.CODING: 0.9},
        terms_evidence_ref="evidence://terms",
        metadata={"probationary": False},
    )
    await repository.upsert_deployment(qualified)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "model-a", "active": True}]})

    target = DiscoveryTarget(
        provider="groq",
        account_ref="free-account",
        tier="free",
        endpoint="https://api.groq.com/openai/v1",
        cost_class=CostClass.FREE_API,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await sync_provider_discovery(
            repository, GroqAdapter(), target, api_key="secret", client=client
        )

    assert result.created == 0
    candidate = (await repository.list_candidates())[0]
    assert candidate.enabled is True
    assert candidate.state == ProviderState.AVAILABLE
    assert candidate.capability_scores[Capability.CODING] == 0.9
    await engine.dispose()


def test_builtin_registry_is_explicit_and_unknown_provider_does_not_guess() -> None:
    assert built_in_adapter("groq").provider == "groq"
    with pytest.raises(KeyError):
        built_in_adapter("mystery-provider")
