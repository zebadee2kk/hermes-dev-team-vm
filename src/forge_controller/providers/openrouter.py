from __future__ import annotations

from .openai_compatible import OpenAICompatibleAdapter


class OpenRouterAdapter(OpenAICompatibleAdapter):
    provider = "openrouter"
    # User-scoped discovery respects provider preferences, privacy settings and guardrails.
    models_url = "https://openrouter.ai/api/v1/models/user"
    discovery_source = "openrouter_user_models_api"
