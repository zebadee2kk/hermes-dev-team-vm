from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HighIsolationPolicyError(RuntimeError):
    pass


class HighIsolationBackendKind(StrEnum):
    FIRECRACKER = "firecracker"
    EXTERNAL_VM = "external_vm"


class HighIsolationHostFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    os_name: str
    architecture: str
    kvm_readable: bool = False
    kvm_writable: bool = False
    firecracker_binary: Path | None = None
    jailer_binary: Path | None = None

    @field_validator("firecracker_binary", "jailer_binary")
    @classmethod
    def binaries_are_absolute(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("high-isolation binary paths must be absolute")
        return value


class FirecrackerBackendConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    require_jailer: bool = True
    require_seccomp: bool = True
    kernel_image: str | None = None
    rootfs_image: str | None = None


class ExternalVMBackendConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    driver_id: str | None = None
    image_ref: str | None = None


class HighIsolationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    firecracker: FirecrackerBackendConfig = Field(default_factory=FirecrackerBackendConfig)
    external_vm: ExternalVMBackendConfig = Field(default_factory=ExternalVMBackendConfig)
    allow_normal_profile_fallback: bool = False


class HighIsolationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    backend: HighIsolationBackendKind
    disposable: bool = True
    network_default: str = "none"
    workspace_delivery: str = "task_snapshot"
    credential_delivery: str = "broker_only"
    metadata_service: str = "disabled"
    backend_ref: str


class HighIsolationSelector:
    """Select a stronger Hand boundary; never silently downgrade to gVisor/runc."""

    def __init__(self, config: HighIsolationConfig) -> None:
        if config.allow_normal_profile_fallback:
            raise HighIsolationPolicyError("high-isolation fallback to the normal Hand is forbidden")
        self.config = config

    def select(self, host: HighIsolationHostFacts) -> HighIsolationPlan:
        firecracker_error: str | None = None
        if self.config.firecracker.enabled:
            try:
                return self._firecracker(host)
            except HighIsolationPolicyError as exc:
                firecracker_error = str(exc)

        if self.config.external_vm.enabled:
            external = self.config.external_vm
            if not external.driver_id or not external.image_ref:
                raise HighIsolationPolicyError(
                    "external VM backend requires an explicit driver_id and immutable image_ref"
                )
            return HighIsolationPlan(
                backend=HighIsolationBackendKind.EXTERNAL_VM,
                backend_ref=f"{external.driver_id}:{external.image_ref}",
            )

        detail = f"; Firecracker unavailable: {firecracker_error}" if firecracker_error else ""
        raise HighIsolationPolicyError(
            "no approved high-isolation backend is available; fail closed" + detail
        )

    def _firecracker(self, host: HighIsolationHostFacts) -> HighIsolationPlan:
        config = self.config.firecracker
        if host.os_name.lower() != "linux":
            raise HighIsolationPolicyError("Firecracker requires a Linux host")
        if host.architecture not in {"x86_64", "aarch64"}:
            raise HighIsolationPolicyError("Firecracker host architecture is unsupported")
        if not host.kvm_readable or not host.kvm_writable:
            raise HighIsolationPolicyError("Firecracker requires read/write access to /dev/kvm")
        if host.firecracker_binary is None:
            raise HighIsolationPolicyError("Firecracker binary is not pinned/configured")
        if config.require_jailer and host.jailer_binary is None:
            raise HighIsolationPolicyError("production Firecracker requires the jailer")
        if not config.require_seccomp:
            raise HighIsolationPolicyError("Firecracker seccomp cannot be disabled for high isolation")
        if not config.kernel_image or not _immutable_ref(config.kernel_image):
            raise HighIsolationPolicyError("Firecracker kernel image must be immutable/content-addressed")
        if not config.rootfs_image or not _immutable_ref(config.rootfs_image):
            raise HighIsolationPolicyError("Firecracker rootfs image must be immutable/content-addressed")
        return HighIsolationPlan(
            backend=HighIsolationBackendKind.FIRECRACKER,
            backend_ref=f"{config.kernel_image}|{config.rootfs_image}",
        )


def _immutable_ref(value: str) -> bool:
    lowered = value.lower()
    return "sha256:" in lowered or lowered.startswith("sha256-")
