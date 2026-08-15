from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_lane_manifest_uses_stable_forge_aliases_and_no_direct_provider_models() -> None:
    manifest = yaml.safe_load((ROOT / "config/hermes-lanes.yaml").read_text())
    assert manifest["hermes"]["provider"] == "custom"
    assert manifest["hermes"]["base_url"].endswith("/v1")
    for lane in manifest["lanes"].values():
        assert lane["model"].startswith("forge/")
        assert "deployment" not in lane["model"]


def test_bootstrap_does_not_inject_database_or_provider_secrets() -> None:
    script = (ROOT / "integrations/hermes/bootstrap.sh").read_text()
    assert "${FORGE_GATEWAY_KEY}" in script
    assert "LITELLM_MASTER_KEY" not in script
    assert "--env DATABASE_URL" not in script
    assert "--env GROQ_API_KEY" not in script
    assert "fallback_providers '[]'" in script
    assert "python -m forge_controller.mcp_server" in script


def test_forge_worker_skills_have_valid_minimal_frontmatter() -> None:
    skills = [
        ROOT / "integrations/hermes/skills/forge-task-contract/SKILL.md",
        ROOT / "integrations/hermes/skills/forge-reality-anchor/SKILL.md",
    ]
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
