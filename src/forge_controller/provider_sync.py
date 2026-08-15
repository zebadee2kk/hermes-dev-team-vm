from __future__ import annotations

from dataclasses import dataclass

import httpx

from .discovery import probationary_deployment
from .models import CostClass, Sensitivity
from .providers.base import ProviderAdapter
from .repository import AssuranceRepository


@dataclass(frozen=True, slots=True)
class DiscoveryTarget:
    provider: str
    account_ref: str
    tier: str
    endpoint: str
    cost_class: CostClass = CostClass.UNKNOWN
    accepted_sensitivity: frozenset[Sensitivity] = frozenset({Sensitivity.PUBLIC})


@dataclass(frozen=True, slots=True)
class DiscoverySyncResult:
    provider: str
    discovered: int
    created: int
    already_known: int
    inactive: int


async def sync_provider_discovery(
    repository: AssuranceRepository,
    adapter: ProviderAdapter,
    target: DiscoveryTarget,
    *,
    api_key: str,
    client: httpx.AsyncClient | None = None,
) -> DiscoverySyncResult:
    """Persist only new models as probationary deployments; never downgrade known state."""
    if adapter.provider != target.provider:
        raise ValueError(
            f"adapter provider {adapter.provider!r} does not match target {target.provider!r}"
        )

    discovered = await adapter.discover_models(api_key=api_key, client=client)
    known_ids = {candidate.id for candidate in await repository.list_candidates()}
    created = 0
    already_known = 0
    inactive = 0

    for model in discovered:
        if not model.active:
            inactive += 1
        deployment = probationary_deployment(
            model,
            account_ref=target.account_ref,
            tier=target.tier,
            endpoint=target.endpoint,
            cost_class=target.cost_class,
            accepted_sensitivity=set(target.accepted_sensitivity),
        )
        if deployment.deployment_id in known_ids:
            already_known += 1
            continue
        await repository.upsert_deployment(deployment)
        known_ids.add(deployment.deployment_id)
        created += 1

    await repository.append_event(
        "provider.discovery_synced",
        payload={
            "provider": target.provider,
            "account_ref": target.account_ref,
            "tier": target.tier,
            "discovered": len(discovered),
            "created": created,
            "already_known": already_known,
            "inactive": inactive,
        },
    )
    return DiscoverySyncResult(
        provider=target.provider,
        discovered=len(discovered),
        created=created,
        already_known=already_known,
        inactive=inactive,
    )
