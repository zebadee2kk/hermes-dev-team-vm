from __future__ import annotations

from .openai_compatible import OpenAICompatibleAdapter


class GroqAdapter(OpenAICompatibleAdapter):
    provider = "groq"
    models_url = "https://api.groq.com/openai/v1/models"
    discovery_source = "groq_models_api"
