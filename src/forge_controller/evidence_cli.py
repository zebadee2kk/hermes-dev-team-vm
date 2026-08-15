from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .contracts import RealityAnchor

_MAX_REPORT_BYTES = 1024 * 1024
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "refresh_token",
    "secret",
    "token",
    "access_token",
}


class EvidenceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EvidenceProfile:
    success_field: str
    anchor_type: str
    claim_ref: str
    executor: str


_KNOWN_PROFILES = {
    "forge-sandbox-live-smoke": EvidenceProfile(
        success_field="passed",
        anchor_type="sandbox_compromise_smoke",
        claim_ref="M4:normal-hand-isolation",
        executor="forge-sandbox-smoke",
    ),
    "forge-codex-probation-preflight": EvidenceProfile(
        success_field="ready",
        anchor_type="codex_app_server_preflight",
        claim_ref="Probation-001:codex-app-server-preflight",
        executor="codex-probation-preflight",
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge-evidence")
    parser.add_argument("--input", required=True, help="machine-readable JSON evidence report")
    parser.add_argument("--output", help="write the validated Reality Anchor JSON here")
    parser.add_argument("--project-id")
    parser.add_argument("--task-id")
    parser.add_argument("--type", dest="anchor_type")
    parser.add_argument("--claim-ref")
    parser.add_argument("--executor")
    parser.add_argument("--pass-field", default="passed")
    parser.add_argument("--observed-at")
    parser.add_argument("--workspace-revision")
    parser.add_argument("--reproduce")
    parser.add_argument("--submit-url", help="Forge controller base URL; loopback only by default")
    parser.add_argument(
        "--allow-remote-controller",
        action="store_true",
        help="explicitly permit submitting evidence to a non-loopback controller URL",
    )
    return parser


def load_report(path: str | Path) -> tuple[Path, dict[str, object], str]:
    source = Path(path).resolve()
    try:
        size = source.stat().st_size
    except FileNotFoundError as exc:
        raise EvidenceError(f"evidence file not found: {source}") from exc
    if size > _MAX_REPORT_BYTES:
        raise EvidenceError(f"evidence report exceeds {_MAX_REPORT_BYTES} bytes")
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError("evidence report must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise EvidenceError("evidence report must be a JSON object")
    sensitive = sorted(_find_sensitive_keys(payload))
    if sensitive:
        raise EvidenceError(
            "evidence report contains credential-like fields and will not be persisted: "
            + ", ".join(sensitive)
        )
    return source, payload, digest


def anchor_from_report(
    source: Path,
    report: dict[str, object],
    digest: str,
    *,
    project_id: str | None = None,
    task_id: str | None = None,
    anchor_type: str | None = None,
    claim_ref: str | None = None,
    executor: str | None = None,
    pass_field: str = "passed",
    observed_at: str | None = None,
    workspace_revision: str | None = None,
    reproduce: str | None = None,
) -> RealityAnchor:
    source_kind = _source_kind(report)
    profile = _KNOWN_PROFILES.get(source_kind)
    success_field = profile.success_field if profile else pass_field
    if _field(report, success_field) is not True:
        raise EvidenceError(
            f"evidence report is not a passing result ({success_field!r} must be true)"
        )

    resolved_project = project_id or _required_text(report, "project_id")
    resolved_task = task_id or _required_text(report, "task_id")
    resolved_type = anchor_type or (profile.anchor_type if profile else None)
    resolved_claim = claim_ref or (profile.claim_ref if profile else None)
    resolved_executor = executor or (profile.executor if profile else None)
    if not resolved_type:
        raise EvidenceError("unknown report kind requires --type")
    if not resolved_claim:
        raise EvidenceError("unknown report kind requires --claim-ref")
    if not resolved_executor:
        raise EvidenceError("unknown report kind requires --executor")

    raw_observed_at = observed_at or report.get("observed_at")
    if not isinstance(raw_observed_at, str) or not raw_observed_at.strip():
        raise EvidenceError("evidence report requires an explicit observed_at timestamp")
    _validate_aware_datetime(raw_observed_at)

    environment: dict[str, object] = {
        "source_kind": source_kind,
        "evidence_sha256": digest,
        "source_file": str(source),
    }
    for key in ("image", "host_preflight", "working_directory", "candidate_id"):
        if key in report:
            environment[key] = report[key]

    artifact_ref = f"{source.as_uri()}#sha256={digest}"
    return RealityAnchor(
        project_id=resolved_project,
        task_id=resolved_task,
        type=resolved_type,
        claim_ref=resolved_claim,
        executor=resolved_executor,
        workspace_revision=workspace_revision,
        environment=environment,
        observed_at=raw_observed_at,
        result={"passed": True, "report": report},
        artifact_refs=[artifact_ref],
        reproduce=reproduce,
        stale=False,
    )


def submit_anchor(
    anchor: RealityAnchor,
    base_url: str,
    *,
    allow_remote_controller: bool = False,
) -> None:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise EvidenceError("--submit-url must be an absolute HTTP(S) URL")
    if not allow_remote_controller and parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise EvidenceError(
            "refusing remote evidence submission; use --allow-remote-controller explicitly"
        )
    endpoint = base_url.rstrip("/") + "/v1/anchors"
    try:
        response = httpx.post(endpoint, json=anchor.model_dump(mode="json"), timeout=10.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise EvidenceError(f"Forge evidence submission failed: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("anchor_id") != anchor.anchor_id:
        raise EvidenceError("Forge returned an unexpected Reality Anchor acknowledgement")


def _source_kind(report: dict[str, object]) -> str:
    value = report.get("kind")
    if isinstance(value, str) and value:
        return value
    if report.get("candidate_id") == "hermes-codex-app-server-runtime":
        return "forge-codex-probation-preflight"
    return "unknown"


def _field(report: dict[str, object], dotted: str) -> object:
    value: object = report
    for segment in dotted.split("."):
        if not isinstance(value, dict) or segment not in value:
            return None
        value = value[segment]
    return value


def _required_text(report: dict[str, object], key: str) -> str:
    value = report.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"evidence report requires {key!r} or an explicit CLI override")
    return value


def _validate_aware_datetime(value: str) -> None:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EvidenceError("observed_at must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError("observed_at must include a timezone")


def _find_sensitive_keys(value: object, prefix: str = "") -> set[str]:
    findings: set[str] = set()
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized = key.lower().replace("-", "_")
            location = f"{prefix}.{key}" if prefix else key
            if normalized in _SENSITIVE_KEYS:
                findings.add(location)
            findings.update(_find_sensitive_keys(child, location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.update(_find_sensitive_keys(child, f"{prefix}[{index}]"))
    return findings


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source, report, digest = load_report(args.input)
        anchor = anchor_from_report(
            source,
            report,
            digest,
            project_id=args.project_id,
            task_id=args.task_id,
            anchor_type=args.anchor_type,
            claim_ref=args.claim_ref,
            executor=args.executor,
            pass_field=args.pass_field,
            observed_at=args.observed_at,
            workspace_revision=args.workspace_revision,
            reproduce=args.reproduce,
        )
        if args.submit_url:
            submit_anchor(
                anchor,
                args.submit_url,
                allow_remote_controller=args.allow_remote_controller,
            )
    except EvidenceError as exc:
        print(f"forge-evidence: {exc}", file=sys.stderr)
        return 2

    payload = anchor.model_dump_json(indent=2)
    print(payload)
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
