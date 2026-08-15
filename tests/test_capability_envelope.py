from datetime import UTC, datetime
from pathlib import Path

import pytest

from forge_controller.capabilities import CapabilityDenied, CapabilityPolicy, issue_grant
from forge_controller.capability_envelope import CapabilityGrantEnvelope, open_grant, seal_grant

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 8, 15, 22, 50, tzinfo=UTC)
KEY = b"k" * 32


def _grant():
    policy = CapabilityPolicy.load(ROOT / "config/capability-policy.yaml")
    return issue_grant(
        policy,
        template="github_task_branch_write",
        project_id="forge",
        task_id="task-123",
        subject_id="engineering-worker-1",
        resource="zebadee2kk/hermes-dev-team-vm",
        operations={"branch.push"},
        ttl_minutes=10,
        branch="forge/task-123",
        now=NOW,
    )


def test_sealed_grant_round_trips_without_serializing_key() -> None:
    grant = _grant()
    envelope = seal_grant(grant, key_id="forge-capability-v1", key=KEY)

    assert open_grant(envelope, keyring={"forge-capability-v1": KEY}) == grant
    serialized = envelope.model_dump_json()
    assert KEY.decode() not in serialized


def test_tampered_grant_is_rejected() -> None:
    envelope = seal_grant(_grant(), key_id="forge-capability-v1", key=KEY)
    payload = envelope.model_dump(mode="json")
    payload["grant"]["resource"] = "zebadee2kk/other"
    tampered = CapabilityGrantEnvelope.model_validate(payload)

    with pytest.raises(CapabilityDenied, match="failed authentication"):
        open_grant(tampered, keyring={"forge-capability-v1": KEY})


def test_unknown_key_and_revocation_fail_closed() -> None:
    grant = _grant()
    envelope = seal_grant(grant, key_id="forge-capability-v1", key=KEY)

    with pytest.raises(CapabilityDenied, match="unknown capability signing key"):
        open_grant(envelope, keyring={})
    with pytest.raises(CapabilityDenied, match="revoked"):
        open_grant(
            envelope,
            keyring={"forge-capability-v1": KEY},
            revoked_grant_ids={grant.grant_id},
        )


def test_short_signing_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        seal_grant(_grant(), key_id="forge-capability-v1", key=b"too-short")
