from __future__ import annotations

import os
import stat
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .capabilities import AuthorizedCapability

_MAX_BINDINGS_FILE_BYTES = 1024 * 1024


class SecretBrokerError(RuntimeError):
    pass


class SecretAccessDenied(SecretBrokerError):
    pass


class CredentialBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    binding_id: str = Field(min_length=1, max_length=128)
    service: str = Field(min_length=1, max_length=128)
    operations: frozenset[str] = Field(min_length=1)
    credential_name: str = Field(min_length=1, max_length=255)
    resources: frozenset[str] = Field(default_factory=frozenset)
    max_bytes: int = Field(default=65536, ge=1, le=1024 * 1024)

    @field_validator("credential_name")
    @classmethod
    def credential_is_a_leaf_name(cls, value: str) -> str:
        if Path(value).name != value or value in {".", ".."}:
            raise ValueError("credential_name must be a leaf filename")
        return value


class CredentialBindingRegistry:
    """Non-secret, root-owned mapping from capability bindings to systemd credential names."""

    def __init__(self, path: str | Path, *, required_owner_uid: int = 0) -> None:
        self.path = Path(path)
        self.required_owner_uid = required_owner_uid

    def resolve(self, capability: AuthorizedCapability) -> CredentialBinding:
        if not capability.credential_binding:
            raise SecretAccessDenied("authorized capability has no credential binding")
        bindings = self._read()
        matches = [
            binding
            for binding in bindings
            if binding.binding_id == capability.credential_binding
            and binding.service == capability.service
        ]
        if len(matches) != 1:
            raise SecretAccessDenied("credential binding is not uniquely registered for this service")
        binding = matches[0]
        if capability.operation not in binding.operations:
            raise SecretAccessDenied("credential binding does not permit this operation")
        if binding.resources and capability.resource not in binding.resources:
            raise SecretAccessDenied("credential binding does not permit this resource")
        return binding

    def _read(self) -> list[CredentialBinding]:
        try:
            info = self.path.stat()
        except FileNotFoundError as exc:
            raise SecretBrokerError("credential binding registry is missing") from exc
        if not stat.S_ISREG(info.st_mode):
            raise SecretBrokerError("credential binding registry must be a regular file")
        if info.st_uid != self.required_owner_uid:
            raise SecretBrokerError("credential binding registry has an unexpected owner")
        if info.st_mode & 0o022:
            raise SecretBrokerError("credential binding registry must not be group/world writable")
        if info.st_size > _MAX_BINDINGS_FILE_BYTES:
            raise SecretBrokerError("credential binding registry is too large")
        try:
            raw = yaml.safe_load(self.path.read_text())
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            raise SecretBrokerError("credential binding registry is not valid YAML") from exc
        if not isinstance(raw, dict) or raw.get("version") != 1:
            raise SecretBrokerError("unsupported credential binding registry version")
        items = raw.get("bindings")
        if not isinstance(items, list):
            raise SecretBrokerError("credential binding registry requires a bindings list")
        try:
            bindings = [CredentialBinding.model_validate(item) for item in items]
        except ValueError as exc:
            raise SecretBrokerError(f"invalid credential binding registry: {exc}") from exc
        identities = [(binding.binding_id, binding.service) for binding in bindings]
        if len(identities) != len(set(identities)):
            raise SecretBrokerError("duplicate credential binding/service registration")
        return bindings


class SecretLease(AbstractContextManager["SecretLease"]):
    """Short-lived mutable secret buffer for trusted in-process gateway code only."""

    __slots__ = ("_buffer", "_closed")

    def __init__(self, value: bytes) -> None:
        self._buffer = bytearray(value)
        self._closed = False

    def __repr__(self) -> str:
        return "SecretLease(<redacted>)"

    def bytes_copy(self) -> bytes:
        if self._closed:
            raise SecretBrokerError("secret lease is closed")
        return bytes(self._buffer)

    def text_copy(self, encoding: str = "utf-8") -> str:
        return self.bytes_copy().decode(encoding)

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        for index in range(len(self._buffer)):
            self._buffer[index] = 0
        self._closed = True

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class SystemdCredentialSecretBroker:
    """Resolve a secret only after an already-authorized capability selects its binding."""

    def __init__(
        self,
        *,
        registry: CredentialBindingRegistry,
        credentials_directory: str | Path,
        allowed_owner_uids: set[int] | frozenset[int] | None = None,
    ) -> None:
        self.registry = registry
        self.credentials_directory = Path(credentials_directory).resolve()
        self.allowed_owner_uids = frozenset(
            allowed_owner_uids if allowed_owner_uids is not None else {0, os.geteuid()}
        )

    def lease(self, capability: AuthorizedCapability) -> SecretLease:
        binding = self.registry.resolve(capability)
        source = (self.credentials_directory / binding.credential_name).resolve()
        try:
            source.relative_to(self.credentials_directory)
        except ValueError as exc:
            raise SecretAccessDenied("credential path escapes the systemd credential directory") from exc
        try:
            info = source.stat()
        except FileNotFoundError as exc:
            raise SecretBrokerError("bound systemd credential is missing") from exc
        if not stat.S_ISREG(info.st_mode):
            raise SecretBrokerError("bound credential must be a regular file")
        if info.st_uid not in self.allowed_owner_uids:
            raise SecretBrokerError("bound credential has an unexpected owner")
        if info.st_mode & 0o077:
            raise SecretBrokerError("bound credential must not be group/world accessible")
        if info.st_size > binding.max_bytes:
            raise SecretBrokerError("bound credential exceeds its configured size limit")
        value = source.read_bytes()
        if not value:
            raise SecretBrokerError("bound credential is empty")
        return SecretLease(value)
