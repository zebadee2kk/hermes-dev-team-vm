# Sandbox Broker boundary

The Sandbox Broker is a **trusted runtime-control service**. It is the only component allowed to control the host container runtime. Hermes workers, external runtime Hands, the Forge Model Gateway and the Forge assurance API do not receive the Docker/containerd socket.

## Normal worker baseline

The first executable profile is `normal`, backed by gVisor `runsc` on Linux. The planner materialises a worker with:

- image pinned by `sha256` digest;
- one validated task-scoped host workspace mounted read/write at `/workspace`;
- read-only root filesystem;
- non-root UID/GID `65532:65532`;
- all Linux capabilities dropped;
- `no-new-privileges`;
- `network=none`;
- bounded CPU, memory, PIDs, temporary storage and execution time;
- `tmpfs` `/tmp` with `noexec,nosuid,nodev`;
- no host devices;
- no Docker/containerd socket;
- no provider, Forge gateway, database or LiteLLM credential in environment variables.

The normal profile uses Docker's trusted runtime-control surface only as a broker backend: the generated invocation specifies `--runtime runsc`. gVisor supports Linux AMD64/x86_64 and ARM64, so the same policy shape can be used by local/Proxmox and OCI ARM deployment profiles after runtime validation.

## Why `network=none` first

`config/sandbox-profiles.yaml` describes the eventual `capability_gateway` network model, but the launch policy intentionally starts with no network at all. A destination allowlist is not a sufficient security boundary because an approved destination plus a broadly scoped credential can still be abused.

M4 will add a separate capability-egress path that materialises only the operation/resource/credential a task is granted. Until that gateway exists, a worker that requires network access must block rather than receive unrestricted Docker bridge/host networking.

## Workspace validation

The broker is configured with one host workspace root. A requested workspace must resolve to a **child** beneath that root; the root itself, parent directories and paths that resolve outside it are rejected. The worker request does not contain arbitrary extra mount definitions.

This prevents a model from turning a legitimate coding task into a request to mount `/`, `/etc`, the Forge repository, credential directories, runtime sockets or another task's workspace.

## Secrets

`SandboxLaunchRequest.environment` is for non-secret task metadata only. Secret-looking variable names are rejected. Future secret access uses `secret_refs` plus a trusted Secret/Capability Gateway; refs do not contain secret values and are not materialised by the sandbox planner.

## Broker process isolation

The trusted broker should run as a separate host service or dedicated management container/process identity. If Docker is the selected backend, only that broker identity may access the Docker API/socket. Do not mount `/var/run/docker.sock` into:

- the Forge controller/API;
- LiteLLM;
- Hermes profiles/gateway;
- MCP sidecars;
- worker Hands; or
- external coding runtimes.

A later deployment slice will expose a narrow broker Unix-domain API to Forge and keep the runtime socket on the broker side of that boundary.

## Profiles

- `normal`: gVisor/runsc, non-root, no network; this is the current executable policy foundation.
- `low`: not implemented. Do not silently fall back to ordinary `runc` merely because work is labelled low risk.
- `high`: not implemented. Intended for VM/microVM isolation when hostile inputs/client policy require a stronger boundary.

Requests for an unimplemented profile fail closed.

## Required live acceptance before unattended use

1. gVisor is installed from a pinned/reviewed release on the target host.
2. `runsc` is registered as the container runtime.
3. broker launches a digest-pinned fixture using the generated normal policy.
4. fixture cannot see host/container runtime sockets, host root, control-plane files or metadata endpoints.
5. fixture cannot reach the Internet or LAN in the no-egress profile.
6. workspace writes are confined to the assigned task workspace.
7. CPU/RAM/PID/timeout termination works.
8. destroy/recreate produces a clean sandbox while the Task Capsule/workspace persists independently.

Do not use in-sandbox `dmesg` output as a security-sensitive proof that gVisor is active; runtime verification belongs to the trusted broker/deployment plane.
