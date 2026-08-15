import json

import pytest
import yaml

from forge_controller.contracts import InferenceDeployment
from forge_controller.litellm_runtime import credential_env_from_json, render_database_config
from forge_controller.models import Capability, CostClass, ProviderState, Sensitivity
from forge_controller.persistence import create_schema, make_engine, make_session_factory
from forge_controller.repository import AssuranceRepository


@pytest.mark.asyncio
async def test_runtime_renderer_reads_durable_registry_and_emits_only_qualified_models(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'runtime.db'}"
    engine = make_engine(database_url)
    await create_schema(engine)
    repository = AssuranceRepository(make_session_factory(engine))
    qualified = InferenceDeployment(
        deployment_id="groq/free/model",
        provider="groq",
        model="model",
        account_ref="free",
        tier="free",
        endpoint="https://api.groq.com/openai/v1",
        credential_binding="provider:groq:free",
        enabled=True,
        state=ProviderState.AVAILABLE,
        cost_class=CostClass.FREE_API,
        accepted_sensitivity={Sensitivity.PUBLIC},
        capability_scores={Capability.CODING: 0.9},
        terms_evidence_ref="evidence://terms",
    )
    quarantined = qualified.model_copy(
        update={
            "deployment_id": "groq/free/new-model",
            "model": "new-model",
            "enabled": False,
            "state": ProviderState.QUARANTINED,
            "capability_scores": {},
            "terms_evidence_ref": None,
        }
    )
    await repository.upsert_deployment(qualified)
    await repository.upsert_deployment(quarantined)
    await engine.dispose()

    output = tmp_path / "runtime" / "config.yaml"
    result = await render_database_config(
        database_url=database_url,
        path=output,
        credential_env={"provider:groq:free": "GROQ_API_KEY"},
    )

    assert result.changed
    config = yaml.safe_load(output.read_text())
    assert len(config["model_list"]) == 1
    assert config["model_list"][0]["model_name"] == "forge/deployment/groq/free/model"
    assert config["model_list"][0]["litellm_params"]["api_key"] == "os.environ/GROQ_API_KEY"


def test_credential_mapping_accepts_names_not_values() -> None:
    mapping = credential_env_from_json(
        json.dumps({"provider:groq:free": "GROQ_API_KEY"})
    )
    assert mapping["provider:groq:free"] == "GROQ_API_KEY"
    with pytest.raises(ValueError):
        credential_env_from_json('{"provider:groq:free":"bad-name!"}')
