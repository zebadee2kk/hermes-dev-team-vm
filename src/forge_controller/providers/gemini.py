from __future__ import annotations

from collections.abc import Mapping

import httpx

from ..models import QuotaObservation
from .base import DiscoveredModel
from .openai_compatible import extract_error_code


class GeminiAdapter:
    """Gemini discovery uses the native Models API for richer capability metadata."""

    provider = "gemini"
    models_url = "https://generativelanguage.googleapis.com/v1beta/models"
    api_client = "hermes-forge/0.3.0"

    async def discover_models(
        self,
        *,
        api_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> list[DiscoveredModel]:
        owns_client = client is None
        http = client or httpx.AsyncClient(timeout=15)
        discovered: list[DiscoveredModel] = []
        page_token: str | None = None
        try:
            while True:
                params = {"pageSize": "1000"}
                if page_token:
                    params["pageToken"] = page_token
                response = await http.get(
                    self.models_url,
                    headers={
                        "x-goog-api-key": api_key,
                        "x-goog-api-client": self.api_client,
                    },
                    params=params,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, Mapping):
                    break
                models = payload.get("models", [])
                if isinstance(models, list):
                    for item in models:
                        model = self._model_from_item(item)
                        if model is not None:
                            discovered.append(model)
                next_token = payload.get("nextPageToken")
                if not isinstance(next_token, str) or not next_token:
                    break
                page_token = next_token
            return discovered
        finally:
            if owns_client:
                await http.aclose()

    def _model_from_item(self, item: object) -> DiscoveredModel | None:
        if not isinstance(item, Mapping):
            return None
        resource_name = item.get("name")
        base_model_id = item.get("baseModelId")
        if isinstance(base_model_id, str) and base_model_id:
            model_id = base_model_id
        elif isinstance(resource_name, str) and resource_name.startswith("models/"):
            model_id = resource_name.removeprefix("models/")
        else:
            return None

        methods = item.get("supportedGenerationMethods", [])
        if not isinstance(methods, list):
            methods = []
        input_limit = item.get("inputTokenLimit")
        output_limit = item.get("outputTokenLimit")
        return DiscoveredModel(
            model_id=model_id,
            provider=self.provider,
            active="generateContent" in methods,
            context_window=input_limit if isinstance(input_limit, int) else None,
            max_completion_tokens=output_limit if isinstance(output_limit, int) else None,
            owned_by="google",
            metadata={
                "source": "gemini_native_models_api",
                "resource_name": resource_name,
                "version": item.get("version"),
                "display_name": item.get("displayName"),
                "description": item.get("description"),
                "supported_generation_methods": methods,
                "thinking": item.get("thinking"),
            },
        )

    def observation_from_response(
        self,
        response: httpx.Response,
        *,
        model: str | None = None,
        deployment_id: str | None = None,
    ) -> QuotaObservation:
        error_code = extract_error_code(response)
        if error_code == "resource_exhausted":
            error_code = "rate_limit_exceeded"
        return QuotaObservation(
            provider=self.provider,
            model=model,
            deployment_id=deployment_id,
            status_code=response.status_code,
            headers={key.lower(): value for key, value in response.headers.items()},
            error_code=error_code,
        )
