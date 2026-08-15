from __future__ import annotations

from .openai_compatible import OpenAICompatibleAdapter


class SambaNovaAdapter(OpenAICompatibleAdapter):
    provider = "sambanova"
    models_url = "https://api.sambanova.ai/v1/models"
    discovery_source = "sambanova_models_api"
    metadata_fields = OpenAICompatibleAdapter.metadata_fields + ("sn_metadata",)
