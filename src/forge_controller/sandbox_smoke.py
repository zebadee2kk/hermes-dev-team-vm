from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from .sandbox import SandboxLaunchRequest, SandboxPlanner
from .sandbox_host import SandboxHostPreflight
from .sandbox_runtime import DockerGVisorRuntime

_PROBE_COMMAND = ["python3", "/opt/forge/hand_security_probe.py"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge-sandbox-smoke")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--project-id", default="forge")
    parser.add_argument("--task-id", default="sandbox-live-smoke")
    parser.add_argument("--evidence-out")
    return parser


async def _run(args: argparse.Namespace) -> tuple[int, dict[str, object]]:
    preflight = SandboxHostPreflight().inspect(args.workspace_root)
    report: dict[str, object] = {
        "kind": "forge-sandbox-live-smoke",
        "observed_at": datetime.now(UTC).isoformat(),
        "project_id": args.project_id,
        "task_id": args.task_id,
        "image": args.image,
        "host_preflight": preflight.model_dump(mode="json"),
    }
    if not preflight.ready:
        report["passed"] = False
        report["reason"] = "host preflight failed"
        return 2, report

    request = SandboxLaunchRequest(
        project_id=args.project_id,
        task_id=args.task_id,
        image=args.image,
        command=_PROBE_COMMAND,
        workspace_path=args.workspace,
        environment={"FORGE_TASK_ID": args.task_id, "FORGE_PROJECT_ID": args.project_id},
    )
    plan = SandboxPlanner(args.workspace_root).plan(request)
    execution = await DockerGVisorRuntime().execute(plan)
    report["execution"] = {
        "request_id": execution.request_id,
        "container_name": execution.container_name,
        "returncode": execution.returncode,
        "timed_out": execution.timed_out,
        "cleanup_attempted": execution.cleanup_attempted,
        "cleanup_returncode": execution.cleanup_returncode,
        "stderr": execution.stderr.decode("utf-8", errors="replace")[-4000:],
    }

    probe: dict[str, object] | None = None
    try:
        parsed = json.loads(execution.stdout.decode("utf-8"))
        if isinstance(parsed, dict):
            probe = parsed
    except (UnicodeDecodeError, json.JSONDecodeError):
        probe = None
    report["probe"] = probe
    passed = (
        execution.returncode == 0
        and not execution.timed_out
        and probe is not None
        and probe.get("passed") is True
    )
    report["passed"] = passed
    return (0 if passed else 2), report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code, report = asyncio.run(_run(args))
    payload = json.dumps(report, indent=2, sort_keys=True)
    print(payload)
    if args.evidence_out:
        destination = Path(args.evidence_out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
