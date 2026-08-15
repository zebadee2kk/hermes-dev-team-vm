import hashlib
import json
from pathlib import Path

import pytest

from forge_controller.evidence_cli import EvidenceError, anchor_from_report, load_report, submit_anchor


def _write_report(path: Path, payload: dict[str, object]) -> tuple[Path, dict[str, object], str]:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n")
    return load_report(path)


def test_sandbox_smoke_becomes_hash_bound_reality_anchor(tmp_path: Path) -> None:
    source, report, digest = _write_report(
        tmp_path / "sandbox.json",
        {
            "kind": "forge-sandbox-live-smoke",
            "observed_at": "2026-08-15T22:00:00+00:00",
            "project_id": "forge",
            "task_id": "sandbox-live-smoke",
            "image": "sha256:" + "a" * 64,
            "host_preflight": {"architecture": "x86_64", "runtime": "runsc"},
            "passed": True,
        },
    )
    anchor = anchor_from_report(source, report, digest)

    assert anchor.type == "sandbox_compromise_smoke"
    assert anchor.claim_ref == "M4:normal-hand-isolation"
    assert anchor.project_id == "forge"
    assert anchor.task_id == "sandbox-live-smoke"
    assert anchor.result["passed"] is True
    assert anchor.environment["evidence_sha256"] == digest
    assert anchor.artifact_refs == [f"{source.as_uri()}#sha256={digest}"]
    assert digest == hashlib.sha256(source.read_bytes()).hexdigest()


def test_codex_preflight_maps_to_probation_anchor(tmp_path: Path) -> None:
    source, report, digest = _write_report(
        tmp_path / "codex-preflight.json",
        {
            "kind": "forge-codex-probation-preflight",
            "candidate_id": "hermes-codex-app-server-runtime",
            "observed_at": "2026-08-15T22:05:00+00:00",
            "project_id": "forge",
            "task_id": "probation-001-codex-preflight",
            "working_directory": "/var/lib/forge/workspaces/forge/probation-001",
            "ready": True,
            "checks": {"codex_version": {"ok": True, "value": "codex 0.130.0"}},
        },
    )
    anchor = anchor_from_report(source, report, digest)

    assert anchor.type == "codex_app_server_preflight"
    assert anchor.claim_ref == "Probation-001:codex-app-server-preflight"
    assert anchor.executor == "codex-probation-preflight"
    assert anchor.environment["candidate_id"] == "hermes-codex-app-server-runtime"


def test_failed_report_cannot_be_normalized_as_passing_anchor(tmp_path: Path) -> None:
    source, report, digest = _write_report(
        tmp_path / "failed.json",
        {
            "kind": "forge-sandbox-live-smoke",
            "observed_at": "2026-08-15T22:10:00+00:00",
            "project_id": "forge",
            "task_id": "sandbox-live-smoke",
            "passed": False,
        },
    )
    with pytest.raises(EvidenceError, match="not a passing result"):
        anchor_from_report(source, report, digest)


def test_credential_like_fields_are_rejected_before_persistence(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.json"
    path.write_text(
        json.dumps(
            {
                "kind": "forge-sandbox-live-smoke",
                "observed_at": "2026-08-15T22:10:00+00:00",
                "project_id": "forge",
                "task_id": "sandbox-live-smoke",
                "passed": True,
                "token": "must-not-persist",
            }
        )
    )
    with pytest.raises(EvidenceError, match="credential-like fields"):
        load_report(path)


def test_unknown_report_requires_explicit_semantics_and_identity(tmp_path: Path) -> None:
    source, report, digest = _write_report(
        tmp_path / "custom.json",
        {
            "kind": "custom-security-test",
            "observed_at": "2026-08-15T22:15:00+00:00",
            "passed": True,
        },
    )
    anchor = anchor_from_report(
        source,
        report,
        digest,
        project_id="forge",
        task_id="custom-test",
        anchor_type="security_negative_test",
        claim_ref="M9:custom-negative-test",
        executor="custom-runner",
    )
    assert anchor.type == "security_negative_test"
    assert anchor.claim_ref == "M9:custom-negative-test"


def test_remote_controller_submission_requires_explicit_override(tmp_path: Path) -> None:
    source, report, digest = _write_report(
        tmp_path / "sandbox.json",
        {
            "kind": "forge-sandbox-live-smoke",
            "observed_at": "2026-08-15T22:20:00+00:00",
            "project_id": "forge",
            "task_id": "sandbox-live-smoke",
            "passed": True,
        },
    )
    anchor = anchor_from_report(source, report, digest)
    with pytest.raises(EvidenceError, match="refusing remote evidence submission"):
        submit_anchor(anchor, "https://forge.example.com")
