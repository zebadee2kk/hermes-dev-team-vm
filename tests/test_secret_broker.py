import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from forge_controller.capabilities import AuthorizedCapability
from forge_controller.secret_broker import (
    CredentialBindingRegistry,
    SecretAccessDenied,
    SecretBrokerError,
    SystemdCredentialSecretBroker,
)

NOW = datetime(2026, 8, 15, 23, 25, tzinfo=UTC)
RESOURCE = "zebadee2kk/hermes-dev-team-vm"


def _capability(**overrides: object) -> AuthorizedCapability:
    values: dict[str, object] = {
        "grant_id": "grant-1",
        "service": "github",
        "resource": RESOURCE,
        "operation": "branch.push",
        "branch": "forge/task-123",
        "credential_binding": "trusted_gateway",
        "expires_at": NOW + timedelta(minutes=10),
    }
    values.update(overrides)
    return AuthorizedCapability(**values)


def _registry(path: Path, resource: str = RESOURCE) -> CredentialBindingRegistry:
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "bindings:",
                "  - binding_id: trusted_gateway",
                "    service: github",
                "    operations: [branch.push, pr.create]",
                "    credential_name: github-app-private-key",
                f"    resources: [{resource}]",
                "    max_bytes: 65536",
                "",
            ]
        )
    )
    os.chmod(path, 0o644)
    return CredentialBindingRegistry(path, required_owner_uid=os.geteuid())


def test_secret_lease_requires_exact_authorized_binding_operation_and_resource(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path / "bindings.yaml")
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    secret_path = credentials / "github-app-private-key"
    secret_path.write_text("private-key-material")
    os.chmod(secret_path, 0o600)
    broker = SystemdCredentialSecretBroker(
        registry=registry,
        credentials_directory=credentials,
        allowed_owner_uids={os.geteuid()},
    )

    lease = broker.lease(_capability())
    assert repr(lease) == "SecretLease(<redacted>)"
    assert lease.text_copy() == "private-key-material"
    lease.close()
    assert lease.closed is True
    with pytest.raises(SecretBrokerError, match="closed"):
        lease.bytes_copy()

    with pytest.raises(SecretAccessDenied, match="operation"):
        broker.lease(_capability(operation="issue.comment"))
    with pytest.raises(SecretAccessDenied, match="resource"):
        broker.lease(_capability(resource="zebadee2kk/other"))
    with pytest.raises(SecretAccessDenied, match="no credential binding"):
        broker.lease(_capability(credential_binding=None))


def test_secret_file_permissions_and_size_fail_closed(tmp_path: Path) -> None:
    registry_path = tmp_path / "bindings.yaml"
    registry = _registry(registry_path)
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    secret_path = credentials / "github-app-private-key"
    secret_path.write_text("secret")
    broker = SystemdCredentialSecretBroker(
        registry=registry,
        credentials_directory=credentials,
        allowed_owner_uids={os.geteuid()},
    )

    os.chmod(secret_path, 0o644)
    with pytest.raises(SecretBrokerError, match="group/world accessible"):
        broker.lease(_capability())

    os.chmod(secret_path, 0o600)
    secret_path.write_bytes(b"x" * 65537)
    with pytest.raises(SecretBrokerError, match="size limit"):
        broker.lease(_capability())


def test_binding_registry_itself_must_not_be_worker_writable(tmp_path: Path) -> None:
    registry_path = tmp_path / "bindings.yaml"
    registry = _registry(registry_path)
    os.chmod(registry_path, 0o666)
    with pytest.raises(SecretBrokerError, match="must not be group/world writable"):
        registry.resolve(_capability())


def test_duplicate_binding_identity_is_rejected(tmp_path: Path) -> None:
    registry_path = tmp_path / "bindings.yaml"
    registry_path.write_text(
        """version: 1
bindings:
  - binding_id: trusted_gateway
    service: github
    operations: [branch.push]
    credential_name: one
  - binding_id: trusted_gateway
    service: github
    operations: [branch.push]
    credential_name: two
"""
    )
    os.chmod(registry_path, 0o644)
    registry = CredentialBindingRegistry(registry_path, required_owner_uid=os.geteuid())
    with pytest.raises(SecretBrokerError, match="duplicate"):
        registry.resolve(_capability())
