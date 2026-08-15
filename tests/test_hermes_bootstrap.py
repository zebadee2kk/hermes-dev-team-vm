from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_bootstrap_materializes_all_manifest_lanes_without_direct_provider_secrets(tmp_path) -> None:
    manifest = yaml.safe_load((ROOT / "config/worker-lanes.yaml").read_text())
    bin_dir = tmp_path / "bin"
    profile_root = tmp_path / "profiles"
    log_path = tmp_path / "hermes-calls.jsonl"
    bin_dir.mkdir()
    profile_root.mkdir()

    fake_hermes = bin_dir / "hermes"
    fake_hermes.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
with open(os.environ[\"HERMES_FAKE_LOG\"], \"a\", encoding=\"utf-8\") as handle:
    handle.write(json.dumps(args) + \"\\n\")

profile = None
if len(args) >= 2 and args[0] == \"-p\":
    profile = args[1]
    command = args[2:]
else:
    command = args

if command[:2] == [\"profile\", \"show\"]:
    sys.exit(1)

if profile and command == [\"config\", \"path\"]:
    path = Path(os.environ[\"HERMES_FAKE_PROFILE_ROOT\"]) / profile / \"config.yaml\"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    print(path)

sys.exit(0)
"""
    )
    fake_hermes.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "HERMES_FAKE_LOG": str(log_path),
            "HERMES_FAKE_PROFILE_ROOT": str(profile_root),
            "FORGE_BASE_URL": "http://forge.invalid/v1",
            "FORGE_INTERNAL_URL": "http://forge.invalid",
        }
    )
    result = subprocess.run(
        ["bash", str(ROOT / "integrations/hermes/bootstrap.sh")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    calls = [json.loads(line) for line in log_path.read_text().splitlines()]
    lane_names = list(manifest["lanes"])
    create_calls = [call for call in calls if call[:2] == ["profile", "create"]]
    assert [call[2] for call in create_calls] == lane_names

    for lane, config in manifest["lanes"].items():
        assert ["-p", lane, "config", "set", "model.provider", "custom"] in calls
        assert ["-p", lane, "config", "set", "model.default", config["model"]] in calls
        assert [
            "-p",
            lane,
            "config",
            "set",
            "model.base_url",
            "http://forge.invalid/v1",
        ] in calls
        assert [
            "-p",
            lane,
            "config",
            "set",
            "model.api_key",
            "${FORGE_GATEWAY_KEY}",
        ] in calls
        assert ["-p", lane, "config", "set", "fallback_providers", "[]"] in calls

        mcp_calls = [
            call
            for call in calls
            if call[:4] == ["-p", lane, "mcp", "add"] and "forge-assurance" in call
        ]
        assert len(mcp_calls) == 1
        assert "FORGE_INTERNAL_URL=http://forge.invalid" in mcp_calls[0]
        assert "DATABASE_URL" not in " ".join(mcp_calls[0])
        assert "GROQ_API_KEY" not in " ".join(mcp_calls[0])

        lane_root = profile_root / lane / "skills"
        assert (lane_root / "forge-task-contract/SKILL.md").exists()
        assert (lane_root / "forge-reality-anchor/SKILL.md").exists()

    kanban = manifest["hermes"]["kanban"]
    assert [
        "config",
        "set",
        "kanban.dispatch_in_gateway",
        str(kanban["dispatch_in_gateway"]).lower(),
    ] in calls
    assert [
        "config",
        "set",
        "kanban.orchestrator_profile",
        kanban["orchestrator_profile"],
    ] in calls
    assert [
        "config",
        "set",
        "kanban.default_assignee",
        kanban["default_assignee"],
    ] in calls
