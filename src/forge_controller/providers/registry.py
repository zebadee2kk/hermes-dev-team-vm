from __future__ import annotations

from .base import ProviderAdapter
from .gemini import GeminiAdapter
from .groq import GroqAdapter
from .openrouter import OpenRouterAdapter
from .sambanova import SambaNovaAdapter


def built_in_adapters() -> dict[str, ProviderAdapter]:
    adapters: list[ProviderAdapter] = [
        GroqAdapter(),
        OpenRouterAdapter(),
        GeminiAdapter(),
        SambaNovaAdapter(),
    ]
    return {adapter.provider: adapter for adapter in adapters}


def built_in_adapter(provider: str) -> ProviderAdapter:
    try:
        return built_in_adapters()[provider]
    except KeyError as exc:
        raise KeyError(
            f"provider {provider!r} has no built-in adapter; configure an explicit generic adapter"
        ) from exc
