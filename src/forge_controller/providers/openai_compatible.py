from __future__ import annotations

from collections.abc import Mapping

import httpx

from ..models import QuotaObservation
from .base import DiscoveredModel


def extract_error_code(response: httpx.Response) -> str | None:
    """Extract the most useful machine-readable provider error code we can find."""
    if not response.is_error:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, Mapping):
        return None

    error = payload.get("error", payload)
    if not isinstance(error, Mapping):
        return None

    metadata = error.get("metadata")
    if isinstance(metadata, Mapping):
        value = metadata.get("error_type") or metadata.get("provider_code")
        if isinstance(value, str) and value:
            return value.lower()

    for key in ("code", "type", "status"):
        value = error.get(key)
        if isinstance(value, str) and value:
            return value.lower()
    return None


class OpenAICompatibleAdapter:
    """Minimal discovery/quota adapter for OpenAI-compatible provider APIs."""

    provider = "generic"
    models_url = ""
    discovery_source = "openai_compatible_models_api"
    metadata_fields = (
        "name",
        "canonical_slug",
        "pricing",
        "supported_parameters",
        "architecture",
        "top_provider",
        "per_request_limits",
        "expiration_date",
    )

    def __init__(
        self,
        *,
        provider: str | None = None,
        models_url: str | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        if provider is not None:
            self.provider = provider
        if models_url is not None:
            self.models_url = models_url
        self.extra_headers = dict(extra_headers or {})
        if not self.models_url:
            raise ValueError("models_url is required for an OpenAI-compatible adapter")

    def discovery_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            **self.extra_headers,
        }

    async def discover_models(
        self,
        *,
        api_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> list[DiscoveredModel]:
        owns_client = client is None
        http = client or httpx.AsyncClient(timeout=15)
        try:
            response = await http.get(
                self.models_url,
                headers=self.discovery_headers(api_key),
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, Mapping):
                return []
            data = payload.get("data", [])
            if not isinstance(data, list):
                return []
            return [model for item in data if (model := self._model_from_item(item)) is not None]
        finally:
            if owns_client:
                await http.aclose()

    def _model_from_item(self, item: object) -> DiscoveredModel | None:
        if not isinstance(item, Mapping):
            return None
        model_id = item.get("id")
        if not isinstance(model_id, str) or not model_id:
            return None

        top_provider = item.get("top_provider")
        if not isinstance(top_provider, Mapping):
            top_provider = {}
        context_window = item.get("context_window") or item.get("context_length")
        max_completion_tokens = item.get("max_completion_tokens") or top_provider.get(
            "max_completion_tokens"
        )
        metadata = {
            "source": self.discovery_source,
            "object": item.get("object"),
        }
        for key in self.metadata_fields:
            if key in item:
                metadata[key] = item[key]

        return DiscoveredModel(
            model_id=model_id,
            provider=self.provider,
            active=bool(item.get("active", True)),
            context_window=context_window if isinstance(context_window, int) else None,
            max_completion_tokens=(
                max_completion_tokens if isinstance(max_completion_tokens, int) else None
            ),
            owned_by=item.get("owned_by") if isinstance(item.get("owned_by"), str) else None,
            metadata=metadata,
        )

    def observation_from_response(
        self,
        response: httpx.Response,
        *,
        model: str | None = None,
        deployment_id: str | None = None,
    ) -> QuotaObservation:
        return QuotaObservation(
            provider=self.provider,
            model=model,
            deployment_id=deployment_id,
            status_code=response.status_code,
            headers={key.lower(): value for key, value in response.headers.items()},
            error_code=extract_error_code(response),
        )
