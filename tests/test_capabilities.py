from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from forge_controller.capabilities import (
    CapabilityDenied,
    CapabilityGrant,
    CapabilityPolicy,
    CapabilityPolicyError,
    CapabilityUse,
    authorize,
    issue_grant,
)

ROOT = Path(__file__).parents[1]
POLICY = ROOT / "config/capability-policy.yaml"
NOW = datetime(2026, 8, 15, 22, 45, tzinfo=UTC)


def policy() -> CapabilityPolicy:
    return CapabilityPolicy.load(POLICY)


def grant(**overrides: object) -> CapabilityGrant:
    values: dict[str, object] = {
        "template": "github_task_branch_write",
        "project_id": "forge",
        "task_id": "task-123",
        "subject_id": "engineering-worker-1",
        "resource": "zebadee2kk/hermes-dev-team-vm",
        "operations": {"branch.push", "pr.create"},
        "ttl_minutes": 20,
        "branch": "forge/task-123",
        "now": NOW,
    }
    values.update(overrides)
    return issue_grant(policy(), **values)  # type: ignore[arg-type]


def use(**overrides: object) -> CapabilityUse:
    values: dict[str, object] = {
        "project_id": "forge",
        "task_id": "task-123",
        "subject_id": "engineering-worker-1",
        "service": "github",
        "resource": "zebadee2kk/hermes-dev-team-vm",
        "operation": "branch.push",
        "branch": "forge/task-123",
        "default_branch": "main",
    }
    values.update(overrides)
    return CapabilityUse(**values)


def test_exact_task_branch_push_is_authorized_without_exposing_credentials() -> None:
    issued = grant(operations={"branch.push"})
    decision = authorize(policy(), issued, use(), now=NOW + timedelta(minutes=1))

    assert decision.operation == "branch.push"
    assert decision.branch == "forge/task-123"
    assert decision.credential_binding == "trusted_gateway"
    payload = issued.model_dump_json().lower()
    assert "access_token" not in payload
    assert "refresh_token" not in payload
    assert "authorization" not in payload
    assert "password" not in payload


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("project_id", "other", "project"),
        ("task_id", "task-999", "task"),
        ("subject_id", "review-worker", "subject"),
        ("resource", "zebadee2kk/other", "resource"),
        ("branch", "forge/task-999", "branch"),
    ],
)
def test_identity_resource_and_branch_cannot_escape_grant(
    field: str, value: str, message: str
) -> None:
    with pytest.raises(CapabilityDenied, match=message):
        authorize(policy(), grant(), use(**{field: value}), now=NOW + timedelta(minutes=1))


def test_direct_default_branch_push_and_force_push_are_denied() -> None:
    default_grant = grant(branch="main", operations={"branch.push"})
    with pytest.raises(CapabilityDenied, match="default branch"):
        authorize(
            policy(),
            default_grant,
            use(branch="main", default_branch="main"),
            now=NOW + timedelta(minutes=1),
        )

    with pytest.raises(CapabilityDenied, match="force push"):
        authorize(
            policy(),
            grant(operations={"branch.push"}),
            use(force=True),
            now=NOW + timedelta(minutes=1),
        )


def test_pr_creation_requires_exact_head_and_default_base() -> None:
    request = use(operation="pr.create", base_branch="main")
    result = authorize(policy(), grant(operations={"pr.create"}), request, now=NOW)
    assert result.operation == "pr.create"

    with pytest.raises(CapabilityDenied, match="pull request base"):
        authorize(
            policy(),
            grant(operations={"pr.create"}),
            use(operation="pr.create", base_branch="release"),
            now=NOW,
        )


def test_operation_must_be_explicitly_in_grant() -> None:
    with pytest.raises(CapabilityDenied, match="operation"):
        authorize(
            policy(),
            grant(operations={"branch.push"}),
            use(operation="pr.create", base_branch="main"),
            now=NOW,
        )


def test_expired_future_and_revoked_grants_fail_closed() -> None:
    issued = grant(ttl_minutes=5)
    with pytest.raises(CapabilityDenied, match="expired"):
        authorize(policy(), issued, use(), now=NOW + timedelta(minutes=5))
    with pytest.raises(CapabilityDenied, match="not active"):
        authorize(policy(), issued, use(), now=NOW - timedelta(seconds=1))

    revoked = issued.model_copy(update={"revoked": True})
    with pytest.raises(CapabilityDenied, match="revoked"):
        authorize(policy(), revoked, use(), now=NOW)


def test_policy_ttl_and_credential_binding_cannot_be_self_escalated() -> None:
    with pytest.raises(CapabilityPolicyError, match="ttl"):
        grant(ttl_minutes=31)

    issued = grant()
    forged = issued.model_copy(update={"credential_binding": "worker_supplied"})
    with pytest.raises(CapabilityPolicyError, match="credential binding"):
        authorize(policy(), forged, use(), now=NOW)


def test_grant_rejects_raw_credential_fields_and_ambiguous_scopes() -> None:
    issued = grant()
    payload = issued.model_dump(mode="json")
    payload["token"] = "never"
    with pytest.raises(ValidationError):
        CapabilityGrant.model_validate(payload)

    with pytest.raises(ValidationError, match="owner/repository"):
        grant(resource="https://github.com/zebadee2kk/hermes-dev-team-vm")
    with pytest.raises(ValidationError, match="branch"):
        grant(branch="../main")


def test_branch_scoped_template_no_longer_includes_issue_comments() -> None:
    selected = policy().templates["github_task_branch_write"]
    assert selected.operations == frozenset({"branch.push", "pr.create"})
    assert selected.deny_default_branch_write is True
    assert selected.allow_force_push is False
    assert selected.pr_base_must_equal_default is True
    assert selected.credential_exposure == "never"
