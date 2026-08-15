from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

MIN_CODEX_VERSION = (0, 130, 0)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _version_tuple(text: str) -> tuple[int, int, int] | None:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)", text)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-probation-preflight")
    parser.add_argument("--project-id", default="forge")
    parser.add_argument("--task-id", default="probation-001-codex-preflight")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report: dict[str, object] = {
        "kind": "forge-codex-probation-preflight",
        "candidate_id": "hermes-codex-app-server-runtime",
        "observed_at": datetime.now(UTC).isoformat(),
        "project_id": args.project_id,
        "task_id": args.task_id,
        "mutated_configuration": False,
        "working_directory": str(Path.cwd().resolve()),
        "checks": {},
    }
    checks = report["checks"]
    assert isinstance(checks, dict)

    hermes_path = shutil.which("hermes")
    codex_path = shutil.which("codex")
    checks["hermes_cli"] = {"ok": bool(hermes_path), "path": hermes_path}
    checks["codex_cli"] = {"ok": bool(codex_path), "path": codex_path}

    if not hermes_path or not codex_path:
        report["ready"] = False
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2

    hermes_version = _run(hermes_path, "--version")
    checks["hermes_version"] = {
        "ok": hermes_version.returncode == 0,
        "value": (hermes_version.stdout or hermes_version.stderr).strip(),
    }

    codex_version = _run(codex_path, "--version")
    codex_version_text = (codex_version.stdout or codex_version.stderr).strip()
    parsed = _version_tuple(codex_version_text)
    checks["codex_version"] = {
        "ok": codex_version.returncode == 0 and parsed is not None and parsed >= MIN_CODEX_VERSION,
        "value": codex_version_text,
        "parsed": ".".join(str(part) for part in parsed) if parsed else None,
        "minimum": ".".join(str(part) for part in MIN_CODEX_VERSION),
    }
    checks["absolute_codex_path"] = {
        "ok": Path(codex_path).is_absolute(),
        "path": codex_path,
    }

    # Keep generated files inside the probation workspace. The trusted Codex shim mounts only that
    # exact workspace into the gVisor Hand and deliberately rejects host-/tmp output paths.
    with tempfile.TemporaryDirectory(prefix=".forge-codex-schema-", dir=str(Path.cwd())) as temp_dir:
        schema = _run(
            codex_path,
            "app-server",
            "generate-json-schema",
            "--out",
            temp_dir,
        )
        generated = sorted(
            str(path.relative_to(temp_dir))
            for path in Path(temp_dir).rglob("*")
            if path.is_file()
        )
        checks["app_server_schema"] = {
            "ok": schema.returncode == 0 and bool(generated),
            "generated_files": generated,
            "stderr": schema.stderr.strip()[-1000:],
        }

    required = (
        "hermes_cli",
        "codex_cli",
        "hermes_version",
        "codex_version",
        "absolute_codex_path",
        "app_server_schema",
    )
    report["ready"] = all(bool(checks[name].get("ok")) for name in required)
    report["next_gate"] = (
        "device-login + live gVisor/proxy isolation proof; this preflight does not enable codex_app_server"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
