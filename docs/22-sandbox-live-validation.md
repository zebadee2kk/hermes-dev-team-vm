# M4 live Hand validation and Codex dependency

This document defines the evidence path from the M4 sandbox design to a real autonomous engineering Hand.

## What is implemented

The normal profile is a Docker container executed with gVisor `runsc`, one task-scoped writable workspace, read-only root filesystem, non-root UID, all Linux capabilities dropped, `no-new-privileges`, no IPC sharing, bounded CPU/RAM/PID/tmpfs/time and `network=none`. The host Docker/containerd sockets are never mounted.

The trusted Sandbox Broker owns host-control authority and exposes only authenticated plan/run operations over a local Unix-domain socket. Execution remains explicitly disabled unless the broker service configuration enables it.

The live smoke path adds three pieces:

1. non-mutating host preflight for Linux architecture, Docker server, `runsc` binary and Docker runtime registration;
2. a digest-built generic Hand image containing a trusted security probe;
3. an evidence-producing live smoke command that executes the probe through the same `DockerGVisorRuntime` used by the broker.

## Required runtime evidence

A host is not considered validated merely because `docker run --runtime=runsc` exits zero. Keep the JSON evidence from `forge-sandbox-smoke` and bind it to a Reality Anchor for the deployment/task.

The probe must demonstrate:

- non-root execution;
- assigned `/workspace` write/read/delete succeeds;
- container root filesystem write fails;
- execution from `/tmp` fails because the tmpfs is `noexec`;
- `/var/run/docker.sock` and `/run/containerd/containerd.sock` are absent;
- no secret-like environment variables were injected;
- cloud metadata and a public Internet IP are unreachable while `network=none` is active.

The exact Hand image digest, host architecture, Docker server version and `runsc` version must be retained with the result.

## gVisor installation source of truth

Use the current upstream gVisor installation guidance. As of August 2026 the project recommends its Debian package/apt repository as the future-proof path. This matters because the manual release format changed in July 2026 from a legacy two-binary layout to a tarball that includes `runsc`, the containerd shim and `gvisor-bin/` sidecars.

Primary sources:
- https://gvisor.dev/docs/user_guide/install/
- https://gvisor.dev/docs/user_guide/quick_start/docker/

## Why Codex probation is not enabled yet

Probation 001 targets Hermes' Codex app-server runtime. A valid no-network Hand cannot run it because the Codex client needs authenticated outbound connectivity. Turning the Hand onto a normal Docker bridge would defeat ADR-006 by converting destination access into broad network authority.

The next M4 slice therefore needs:

- an internal-only Hand network with no direct external route;
- a trusted capability gateway on that internal network;
- per-task grants binding subject, service, resource, operation, credential binding and expiry;
- a dedicated Codex authentication strategy whose credential is not mixed with Forge/LiteLLM/GitHub/control-plane secrets;
- negative tests proving direct Internet, metadata, private/LAN and out-of-scope capability use remain blocked.

Only after that exists should the Codex probation configuration be enabled for one engineering Hand.

OpenAI's current product documentation confirms Codex CLI can be signed into with an eligible ChatGPT account and that the CLI stores authentication locally. Treat that state as a dedicated candidate credential, not as a reason to expose unrelated provider or control-plane secrets.
