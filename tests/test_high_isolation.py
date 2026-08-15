import pytest

from forge_controller.high_isolation import (
    ExternalVMBackendConfig,
    FirecrackerBackendConfig,
    HighIsolationBackendKind,
    HighIsolationConfig,
    HighIsolationHostFacts,
    HighIsolationPolicyError,
    HighIsolationSelector,
)


def _host(**overrides: object) -> HighIsolationHostFacts:
    values: dict[str, object] = {
        "os_name": "linux",
        "architecture": "x86_64",
        "kvm_readable": True,
        "kvm_writable": True,
        "firecracker_binary": "/usr/local/bin/firecracker",
        "jailer_binary": "/usr/local/bin/jailer",
    }
    values.update(overrides)
    return HighIsolationHostFacts(**values)


def test_high_isolation_can_never_fall_back_to_normal_hand() -> None:
    with pytest.raises(HighIsolationPolicyError, match="fallback"):
        HighIsolationSelector(HighIsolationConfig(allow_normal_profile_fallback=True))


def test_firecracker_requires_linux_supported_arch_kvm_jailer_and_immutable_images() -> None:
    config = HighIsolationConfig(
        firecracker=FirecrackerBackendConfig(
            enabled=True,
            kernel_image="kernel@sha256:" + "a" * 64,
            rootfs_image="rootfs@sha256:" + "b" * 64,
        )
    )
    selector = HighIsolationSelector(config)
    plan = selector.select(_host())
    assert plan.backend is HighIsolationBackendKind.FIRECRACKER
    assert plan.disposable is True
    assert plan.network_default == "none"
    assert plan.credential_delivery == "broker_only"

    with pytest.raises(HighIsolationPolicyError, match="fail closed"):
        selector.select(_host(kvm_writable=False))
    with pytest.raises(HighIsolationPolicyError, match="fail closed"):
        selector.select(_host(jailer_binary=None))
    with pytest.raises(HighIsolationPolicyError, match="fail closed"):
        selector.select(_host(architecture="riscv64"))


def test_external_vm_is_explicit_fallback_only_when_configured() -> None:
    selector = HighIsolationSelector(
        HighIsolationConfig(
            firecracker=FirecrackerBackendConfig(
                enabled=True,
                kernel_image="kernel@sha256:" + "a" * 64,
                rootfs_image="rootfs@sha256:" + "b" * 64,
            ),
            external_vm=ExternalVMBackendConfig(
                enabled=True,
                driver_id="proxmox",
                image_ref="template@sha256:" + "c" * 64,
            ),
        )
    )
    plan = selector.select(_host(kvm_readable=False, kvm_writable=False))
    assert plan.backend is HighIsolationBackendKind.EXTERNAL_VM
    assert plan.backend_ref.startswith("proxmox:")


def test_no_available_high_backend_fails_closed() -> None:
    selector = HighIsolationSelector(HighIsolationConfig())
    with pytest.raises(HighIsolationPolicyError, match="fail closed"):
        selector.select(_host())


def test_firecracker_seccomp_cannot_be_disabled() -> None:
    selector = HighIsolationSelector(
        HighIsolationConfig(
            firecracker=FirecrackerBackendConfig(
                enabled=True,
                require_seccomp=False,
                kernel_image="kernel@sha256:" + "a" * 64,
                rootfs_image="rootfs@sha256:" + "b" * 64,
            )
        )
    )
    with pytest.raises(HighIsolationPolicyError, match="fail closed"):
        selector.select(_host())
