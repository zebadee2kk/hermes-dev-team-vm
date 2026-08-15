from __future__ import annotations

from typing import Protocol

import httpx
from pydantic import BaseModel, Field

from ..models import QuotaObservation


class DiscoveredModel(BaseModel):
    model_id: str
    provider: str
    active: bool = True
    context_window: int | None = None
    max_completion_tokens: int | None = None
    owned_by: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ProviderAdapter(Protocol):
    provider: str

    async def discover_models(
        self,
        *,
        api_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> list[DiscoveredModel]: ...

    def observation_from_response(
        self,
        response: httpx.Response,
        *,
        model: str | None = None,
        deployment_id: str | None = None,
    ) -> QuotaObservation: ...
