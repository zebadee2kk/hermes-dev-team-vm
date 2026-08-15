# Sandbox Broker deployment

This directory turns the M4 gVisor design into a deployable, evidence-producing normal Hand boundary.

## Trust boundary

The Sandbox Broker is trusted host-control infrastructure. It may talk to Docker; Hands may not. Membership in the host `docker` group is effectively host-control authority, so only the dedicated `forge-sandbox` service account receives it. The broker listens on a local Unix-domain socket and requires its own bearer credential. Ordinary workers receive neither the Docker socket nor the broker credential.

The normal Hand stays `network=none`. Do not enable ordinary Docker bridge networking to make a model CLI work. Subscription-backed Codex probation requires the later capability-egress slice so the Hand can reach only a trusted, operation-scoped gateway rather than the Internet directly.

## 1. Install gVisor on Ubuntu/Debian

Docker must already be installed. Then run:

```bash
sudo infra/sandbox/install-gvisor-ubuntu.sh
```

The script follows the current gVisor apt-repository installation path and verifies that Docker exposes a runtime named `runsc`.

Upstream references:
- https://gvisor.dev/docs/user_guide/install/
- https://gvisor.dev/docs/user_guide/quick_start/docker/

## 2. Build a content-addressed Hand image

Choose a Debian/Ubuntu-family base image and resolve it to a registry digest first. Do not pass a mutable tag.

```bash
IMAGE_ID="$(infra/sandbox/build-hand-image.sh 'debian:bookworm-slim@sha256:<digest>')"
echo "$IMAGE_ID"
```

The build helper returns Docker's immutable local image ID (`sha256:<digest>`), which the Sandbox Planner accepts for a local smoke. A published deployment should use the registry form `repo@sha256:<digest>`.

## 3. Prepare the task-scoped workspace

```bash
sudo install -d -o 65532 -g 65532 -m 0750 /var/lib/forge/workspaces/forge/sandbox-live-smoke
```

Never mount `/var/lib/forge/workspaces` itself into a Hand. The planner accepts only a task-scoped descendant.

## 4. Run the live compromise smoke

With the Python package installed on the host:

```bash
forge-sandbox-smoke \
  --workspace-root /var/lib/forge/workspaces \
  --workspace /var/lib/forge/workspaces/forge/sandbox-live-smoke \
  --image "$IMAGE_ID" \
  --project-id forge \
  --task-id sandbox-live-smoke \
  --evidence-out /var/lib/forge/evidence/sandbox-live-smoke.json
```

A passing result proves, for that host/image/runtime combination, that the Hand launched through `runsc`, runs non-root, can write its assigned workspace, cannot write the container root filesystem, cannot execute from `/tmp`, cannot see Docker/containerd sockets, has no secret-like environment variables, and cannot reach cloud metadata or a public Internet IP while the no-network profile is active.

This is runtime evidence, not a proof against every possible container escape. Keep the exact image digest, host architecture, Docker/runsc versions and JSON output with the associated Reality Anchor.

## 5. Install the broker service

Create a dedicated account and directories, install the virtual environment under `/opt/forge/venv`, and install the unit/env template:

```bash
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin forge-sandbox || true
sudo usermod -aG docker forge-sandbox
sudo install -d -m 0750 /etc/forge /var/lib/forge/workspaces
sudo install -m 0600 infra/sandbox/sandbox-broker.env.example /etc/forge/sandbox-broker.env
# Replace FORGE_SANDBOX_BROKER_KEY with a generated secret before starting.
sudo install -m 0644 infra/sandbox/forge-sandbox-broker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now forge-sandbox-broker
```

Do not expose `/run/forge/sandbox-broker.sock` to Hands.

## Codex probation dependency

Do not run Probation 001 inside this no-network Hand yet. Codex CLI/app-server needs authenticated outbound access. The next M4 slice must provide an internal-only Hand network plus a trusted capability gateway (and a dedicated Codex credential strategy) so direct worker Internet remains impossible.
