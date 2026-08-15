from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_configure_knowledge_cron_uses_hermes_script_sandbox_and_safe_radar(tmp_path) -> None:
    bin_dir = tmp_path / "bin"
    hermes_home = tmp_path / "hermes-home"
    log_path = tmp_path / "hermes-calls.jsonl"
    bin_dir.mkdir()

    fake_hermes = bin_dir / "hermes"
    fake_hermes.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["HERMES_FAKE_LOG"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(args) + "\\n")
if args[:2] == ["cron", "list"]:
    print("no jobs")
sys.exit(0)
"""
    )
    fake_hermes.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "HERMES_FAKE_LOG": str(log_path),
            "HERMES_HOME": str(hermes_home),
            "FORGE_REPO_ROOT": str(ROOT),
            "FORGE_KNOWLEDGE_ROOT": str(ROOT / "knowledge"),
        }
    )
    result = subprocess.run(
        ["bash", str(ROOT / "integrations/hermes/configure-knowledge-cron.sh")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    lint_wrapper = hermes_home / "scripts/forge-knowledge-lint.sh"
    digest_wrapper = hermes_home / "scripts/forge-knowledge-digest.sh"
    assert lint_wrapper.exists()
    assert digest_wrapper.exists()
    assert f"FORGE_REPO_ROOT={ROOT}" in lint_wrapper.read_text()
    assert str(ROOT / "integrations/hermes/knowledge-maintenance.sh") in lint_wrapper.read_text()

    calls = [json.loads(line) for line in log_path.read_text().splitlines()]
    creates = [call for call in calls if call[:2] == ["cron", "create"]]
    assert len(creates) == 3

    lint = next(call for call in creates if "Forge knowledge lint" in call)
    digest = next(call for call in creates if "Forge knowledge digest" in call)
    radar = next(call for call in creates if "Forge weekly technology radar" in call)
    for call, script_name in (
        (lint, "forge-knowledge-lint.sh"),
        (digest, "forge-knowledge-digest.sh"),
    ):
        assert "--no-agent" in call
        assert ["--script", script_name] == call[call.index("--script") : call.index("--script") + 2]
        assert str(ROOT / "integrations/hermes") not in call[call.index("--script") + 1]

    assert "--no-agent" not in radar
    assert ["--skill", "forge-tech-radar"] == radar[
        radar.index("--skill") : radar.index("--skill") + 2
    ]
    assert "forge-knowledge-compiler" in radar
    assert "--workdir" in radar and str(ROOT) in radar
    prompt = radar[3]
    assert "Do not install" in prompt
    assert "promote" in prompt
    assert "Trust Envelope" in prompt
    assert "idempotency key" in prompt


def test_knowledge_maintenance_queues_findings_on_hermes_kanban() -> None:
    script = (ROOT / "integrations/hermes/knowledge-maintenance.sh").read_text()
    assert "forge-knowledge" in script
    assert "hermes kanban create" in script
    assert "--idempotency-key" in script
    assert "--skill forge-knowledge-compiler" in script
    assert "kanban.db" not in script


def test_bootstrap_keeps_knowledge_cron_explicitly_opt_in() -> None:
    script = (ROOT / "integrations/hermes/bootstrap.sh").read_text()
    assert 'FORGE_ENABLE_KNOWLEDGE_CRON:-false' in script
    assert "configure-knowledge-cron.sh" in script
    assert "Knowledge cron remains disabled" in script
