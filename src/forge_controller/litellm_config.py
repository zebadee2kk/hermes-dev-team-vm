from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from .contracts import InferenceDeployment
from .models import ProviderState

_PROVIDER_PREFIX = {
    "gemini": "gemini",
    "groq": "groq",
    "openrouter": "openrouter",
    "sambanova": "sambanova",
}


class LiteLLMMaterializationError(ValueError):
    pass


def deployment_alias(deployment: InferenceDeployment) -> str:
    """Return an exact LiteLLM alias; Forge remains authoritative for placement."""
    return f"forge/deployment/{deployment.deployment_id}"


def is_materializable(
    deployment: InferenceDeployment,
    *,
    now: datetime | None = None,
    include_development: bool = False,
) -> bool:
    now = now or datetime.now(UTC)
    if not deployment.enabled:
        return False
    if deployment.development_only and not include_development:
        return False
    if not any(score > 0 for score in deployment.capability_scores.values()):
        return False
    if deployment.state == ProviderState.AVAILABLE:
        return True
    return bool(deployment.retry_at and deployment.retry_at <= now)


def _provider_model(deployment: InferenceDeployment) -> tuple[str, str | None]:
    prefix = _PROVIDER_PREFIX.get(deployment.provider)
    if prefix:
        return f"{prefix}/{deployment.model}", None

    # Generic OpenAI-compatible deployments must opt in explicitly rather than
    # assuming every unknown provider speaks the same API dialect.
    litellm_provider = deployment.metadata.get("litellm_provider")
    if isinstance(litellm_provider, str) and litellm_provider:
        return f"{litellm_provider}/{deployment.model}", deployment.endpoint
    raise LiteLLMMaterializationError(
        f"deployment {deployment.deployment_id!r} has no explicit LiteLLM provider mapping"
    )


def materialize_model_entry(
    deployment: InferenceDeployment,
    *,
    credential_env: Mapping[str, str],
) -> dict[str, object]:
    binding = deployment.credential_binding
    if not binding:
        raise LiteLLMMaterializationError(
            f"deployment {deployment.deployment_id!r} has no credential binding"
        )
    env_name = credential_env.get(binding)
    if not env_name:
        raise LiteLLMMaterializationError(
            f"credential binding {binding!r} has no environment-variable mapping"
        )

    model, api_base = _provider_model(deployment)
    params: dict[str, object] = {
        "model": model,
        "api_key": f"os.environ/{env_name}",
    }
    if api_base:
        params["api_base"] = api_base

    return {
        "model_name": deployment_alias(deployment),
        "litellm_params": params,
    }


def materialize_model_list(
    deployments: Sequence[InferenceDeployment],
    *,
    credential_env: Mapping[str, str],
    now: datetime | None = None,
    include_development: bool = False,
) -> list[dict[str, object]]:
    eligible = [
        deployment
        for deployment in deployments
        if is_materializable(
            deployment,
            now=now,
            include_development=include_development,
        )
    ]
    eligible.sort(key=lambda deployment: deployment.deployment_id)
    return [
        materialize_model_entry(deployment, credential_env=credential_env)
        for deployment in eligible
    ]


def build_litellm_config(
    deployments: Sequence[InferenceDeployment],
    *,
    credential_env: Mapping[str, str],
    now: datetime | None = None,
    include_development: bool = False,
) -> dict[str, object]:
    """Build a complete LiteLLM config without embedding credential values."""
    return {
        "model_list": materialize_model_list(
            deployments,
            credential_env=credential_env,
            now=now,
            include_development=include_development,
        ),
        "router_settings": {
            "num_retries": 1,
            "retry_after": 1,
            "allowed_fails": 2,
            "cooldown_time": 60,
        },
        "general_settings": {
            "master_key": "os.environ/LITELLM_MASTER_KEY",
            "database_url": "os.environ/LITELLM_DATABASE_URL",
        },
        "litellm_settings": {
            "drop_params": True,
            "set_verbose": False,
        },
    }
