from pathlib import Path

import yaml

from forge_controller.litellm_publish import publish_config


def test_publish_is_atomic_change_detecting_and_contains_no_extra_secret_material(tmp_path) -> None:
    target = tmp_path / "runtime" / "config.yaml"
    config = {
        "model_list": [
            {
                "model_name": "forge/deployment/groq/free/model",
                "litellm_params": {
                    "model": "groq/model",
                    "api_key": "os.environ/GROQ_API_KEY",
                },
            }
        ]
    }

    first = publish_config(target, config)
    second = publish_config(target, config)

    assert first.changed is True
    assert second.changed is False
    assert first.digest == second.digest
    assert yaml.safe_load(target.read_text()) == config
    assert "GROQ_API_KEY" in target.read_text()
    assert "test-secret" not in target.read_text()
    assert target.stat().st_mode & 0o777 == 0o600


def test_changed_config_is_replaced_and_returns_new_digest(tmp_path) -> None:
    target = Path(tmp_path) / "config.yaml"
    first = publish_config(target, {"model_list": []})
    second = publish_config(target, {"model_list": [{"model_name": "new"}]})

    assert first.digest != second.digest
    assert second.changed is True
    assert yaml.safe_load(target.read_text())["model_list"][0]["model_name"] == "new"
