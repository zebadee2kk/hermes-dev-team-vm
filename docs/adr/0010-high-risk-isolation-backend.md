# ADR-010: High-risk Hands use a VM/microVM boundary

- Status: Accepted design / execution backend not yet deployed
- Date: 2026-08-15

## Context

The normal autonomous Hand uses gVisor and is intentionally strong enough for routine arbitrary project code. M4 also needs a materially stronger boundary for hostile inputs, high-risk security work and client policy that requires VM-grade isolation.

Using the same gVisor profile with more restrictive flags would not create an independent virtualization boundary, and silently dropping a high-risk request back to normal isolation would defeat the profile's meaning.

Firecracker is a suitable microVM backend when the host can prove the prerequisites. Upstream Firecracker requires Linux/KVM access and supports x86_64 and aarch64 hosts. Its production guidance recommends running Firecracker with the `jailer` and keeping the restrictive seccomp filters enabled.

## Decision

High-risk isolation is a separate adapter with two possible backend classes:

1. **Firecracker microVM** — preferred when the execution host has proven read/write `/dev/kvm`, a supported architecture, pinned Firecracker/jailer binaries, restrictive seccomp, and immutable kernel/rootfs artifacts.
2. **External disposable VM driver** — for environments where nested KVM/Firecracker is unavailable but Forge has an explicitly configured VM lifecycle driver, initially expected to include Proxmox/local virtualization. The driver and immutable image reference must be explicit.

There is **no gVisor/runc fallback** for the high-risk profile. If neither approved backend is available, scheduling fails closed and the task stays blocked/waiting for suitable compute.

## Common high-risk invariants

Regardless of backend:

- disposable instance per bounded task/attempt unless policy explicitly says otherwise;
- no host/container-control socket inside the guest;
- no Brain/control-plane secrets;
- network defaults to none;
- external services are reached only through Forge capability brokers;
- task state arrives as a snapshot/Task Capsule + repository/workspace artifact, not a host filesystem authority;
- credentials are broker-only, never baked into the image/rootfs;
- guest metadata services are disabled unless a specific capability requires one;
- immutable/content-addressed base image/kernel/rootfs;
- CPU/RAM/PID/time budgets still apply at the broker/driver layer;
- destruction and non-persistence are part of the success criteria;
- execution produces Reality Anchors covering backend identity, image/kernel digest, isolation probes and cleanup.

## Host placement

`HighIsolationSelector` performs only fail-closed placement. It does not launch VMs.

For Firecracker, it requires:

- Linux;
- `x86_64` or `aarch64`;
- readable and writable KVM;
- explicitly configured Firecracker binary;
- jailer when production policy requires it;
- restrictive seccomp enabled;
- immutable kernel and rootfs refs.

If any prerequisite fails and no external VM backend is explicitly enabled, selection fails rather than downgrading.

## Consequences

- Normal/portable/OCI-style hosts can still run the gVisor profile even when they cannot run Firecracker.
- A high-risk task may wait for a different worker host; this is preferable to silently weakening isolation.
- M8 deployment automation must expose backend availability/capacity as placement facts.
- M9 must deliberately test that a high-risk request cannot be routed to the normal Hand when VM-grade capacity is absent.

## Remaining implementation

This ADR completes the backend/placement contract, not the live VM runtime. Remaining M4/M8 work includes:

- Firecracker jailer launcher and guest-image build pipeline;
- external VM driver implementation (for example Proxmox);
- snapshot/workspace transfer and result extraction;
- capability-gateway connectivity from guest to trusted host services;
- destroy/recreate/timeout cleanup;
- real host Reality Anchors on at least one supported backend.
