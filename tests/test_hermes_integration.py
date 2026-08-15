from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_worker_lane_manifest_is_authoritative_and_uses_stable_forge_aliases() -> None:
    manifest = yaml.safe_load((ROOT / "config/worker-lanes.yaml").read_text())
    assert manifest["hermes"]["provider"] == "custom"
    assert manifest["hermes"]["base_url"].endswith("/v1")
    assert manifest["hermes"]["api_key_ref"] == "${FORGE_GATEWAY_KEY}"
    assert manifest["rules"]["prefer_task_skills_over_new_persistent_profiles"] is True
    for lane in manifest["lanes"].values():
        assert lane["durable"] is True
        assert lane["model"].startswith("forge/")
        assert "deployment" not in lane["model"]
        assert lane["description"].endswith(".")


def test_bootstrap_consumes_worker_lane_manifest_and_does_not_inject_secrets() -> None:
    script = (ROOT / "integrations/hermes/bootstrap.sh").read_text()
    assert "config/worker-lanes.yaml" in script
    assert "manifest[\"lanes\"]" in script
    assert "manifest_value hermes.api_key_ref" in script
    assert 'config set model.api_key "$HERMES_API_KEY_REF"' in script
    assert "FORGE_KNOWLEDGE_ROOT" in script
    assert "LITELLM_MASTER_KEY" not in script
    assert "--env DATABASE_URL" not in script
    assert "--env GROQ_API_KEY" not in script
    assert "fallback_providers '[]'" in script
    assert "python -m forge_controller.mcp_server" in script
    assert "integrations/hermes/skills/*" in script
    assert "LANES=(" not in script
    assert "MODELS=(" not in script


def test_duplicate_hermes_lane_manifest_does_not_exist() -> None:
    assert not (ROOT / "config/hermes-lanes.yaml").exists()


def test_forge_worker_skills_have_valid_minimal_frontmatter() -> None:
    skills = sorted((ROOT / "integrations/hermes/skills").glob("*/SKILL.md"))
    assert {path.parent.name for path in skills} >= {
        "forge-task-contract",
        "forge-reality-anchor",
        "forge-knowledge-compiler",
        "forge-tech-radar",
    }
    for path in skills:
        content = path.read_text()
        assert content.startswith("---\n")
        _, raw_frontmatter, body = content.split("---", 2)
        frontmatter = yaml.safe_load(raw_frontmatter)
        assert frontmatter["name"]
        assert frontmatter["description"].endswith(".")
        assert len(frontmatter["description"]) <= 60
        assert frontmatter["platforms"] == ["linux", "macos", "windows"]
        assert body.strip()
