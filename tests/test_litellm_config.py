from datetime import UTC, datetime, timedelta

import pytest

from forge_controller.contracts import InferenceDeployment
from forge_controller.litellm_config import (
    LiteLLMMaterializationError,
    build_litellm_config,
    deployment_alias,
    materialize_model_list,
)
from forge_controller.models import Capability, CostClass, ProviderState, Sensitivity

NOW = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)


def deployment(
    identifier: str,
    *,
    provider: str = "groq",
    model: str = "example",
    state: ProviderState = ProviderState.AVAILABLE,
    enabled: bool = True,
    retry_at: datetime | None = None,
    development_only: bool = False,
    metadata: dict[str, object] | None = None,
) -> InferenceDeployment:
    return InferenceDeployment(
        deployment_id=identifier,
        provider=provider,
        model=model,
        account_ref="free",
        tier="free",
        endpoint=f"https://{provider}.invalid/v1",
        credential_binding=f"provider:{provider}:free",
        enabled=enabled,
        state=state,
        retry_at=retry_at,
        cost_class=CostClass.FREE_API,
        accepted_sensitivity={Sensitivity.PUBLIC},
        capability_scores={Capability.CODING: 0.8},
        development_only=development_only,
        metadata=metadata or {},
    )


def test_only_forge_eligible_deployments_are_materialized() -> None:
    ready = deployment("groq/free/ready")
    quarantined = deployment("groq/free/quarantined", state=ProviderState.QUARANTINED)
    exhausted = deployment(
        "groq/free/exhausted",
        state=ProviderState.QUOTA_EXHAUSTED,
        retry_at=NOW + timedelta(hours=2),
    )
    reset = deployment(
        "groq/free/reset",
        state=ProviderState.QUOTA_EXHAUSTED,
        retry_at=NOW - timedelta(seconds=1),
    )
    disabled = deployment("groq/free/disabled", enabled=False)

    entries = materialize_model_list(
        [ready, quarantined, exhausted, reset, disabled],
        credential_env={"provider:groq:free": "GROQ_API_KEY"},
        now=NOW,
    )

    assert [entry["model_name"] for entry in entries] == [
        deployment_alias(ready),
        deployment_alias(reset),
    ]


def test_exact_alias_preserves_forge_placement_and_secrets_stay_environment_references() -> None:
    selected = deployment("openrouter/free/vendor/model", provider="openrouter", model="vendor/model")
    config = build_litellm_config(
        [selected],
        credential_env={"provider:openrouter:free": "OPENROUTER_API_KEY"},
        now=NOW,
    )
    entry = config["model_list"][0]

    assert entry["model_name"] == "forge/deployment/openrouter/free/vendor/model"
    assert entry["litellm_params"]["model"] == "openrouter/vendor/model"
    assert entry["litellm_params"]["api_key"] == "os.environ/OPENROUTER_API_KEY"
    assert "secret" not in str(config).lower()


def test_generic_openai_compatible_requires_explicit_provider_mapping() -> None:
    unknown = deployment("example/free/model", provider="example")
    with pytest.raises(LiteLLMMaterializationError):
        materialize_model_list(
            [unknown],
            credential_env={"provider:example:free": "EXAMPLE_API_KEY"},
            now=NOW,
        )

    explicit = unknown.model_copy(
        update={"metadata": {"litellm_provider": "openai"}}
    )
    entries = materialize_model_list(
        [explicit],
        credential_env={"provider:example:free": "EXAMPLE_API_KEY"},
        now=NOW,
    )
    assert entries[0]["litellm_params"]["model"] == "openai/example"
    assert entries[0]["litellm_params"]["api_base"] == "https://example.invalid/v1"


def test_development_only_deployments_require_explicit_materialization_permission() -> None:
    dev = deployment("groq/free/dev", development_only=True)
    env = {"provider:groq:free": "GROQ_API_KEY"}
    assert materialize_model_list([dev], credential_env=env, now=NOW) == []
    assert len(
        materialize_model_list(
            [dev], credential_env=env, now=NOW, include_development=True
        )
    ) == 1
