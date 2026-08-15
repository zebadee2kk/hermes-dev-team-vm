from __future__ import annotations

import httpx

from ..models import QuotaObservation
from .base import DiscoveredModel


class GroqAdapter:
    provider = "groq"
    models_url = "https://api.groq.com/openai/v1/models"

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
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            payload = response.json()
            discovered: list[DiscoveredModel] = []
            for item in payload.get("data", []):
                if not item.get("id"):
                    continue
                discovered.append(
                    DiscoveredModel(
                        model_id=item["id"],
                        provider=self.provider,
                        active=bool(item.get("active", True)),
                        context_window=item.get("context_window"),
                        max_completion_tokens=item.get("max_completion_tokens"),
                        owned_by=item.get("owned_by"),
                        metadata={
                            "source": "provider_models_api",
                            "object": item.get("object"),
                        },
                    )
                )
            return discovered
        finally:
            if owns_client:
                await http.aclose()

    def observation_from_response(
        self,
        response: httpx.Response,
        *,
        model: str | None = None,
        deployment_id: str | None = None,
    ) -> QuotaObservation:
        error_code = None
        if response.is_error:
            try:
                payload = response.json()
                error = payload.get("error", {}) if isinstance(payload, dict) else {}
                if isinstance(error, dict):
                    error_code = error.get("code") or error.get("type")
            except ValueError:
                pass
        return QuotaObservation(
            provider=self.provider,
            model=model,
            deployment_id=deployment_id,
            status_code=response.status_code,
            headers={key.lower(): value for key, value in response.headers.items()},
            error_code=error_code,
        )
