# Sandbox Broker deployment

This directory turns the M4 gVisor design into a deployable, evidence-producing Hand boundary.

## Trust boundary

The Sandbox Broker is trusted host-control infrastructure. It may talk to Docker; Hands may not. Membership in the host `docker` group is effectively host-control authority, so only the dedicated `forge-sandbox` service account receives it. The broker listens on a local Unix-domain socket and requires its own bearer credential. Ordinary workers receive neither the Docker socket nor the broker credential.

The normal Hand stays `network=none`. Do not enable ordinary Docker bridge networking to make a model CLI work. The Codex probation exception uses a separate internal-only network plus a service-scoped CONNECT proxy; see `docs/23-codex-capability-egress.md`.

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

## Codex probation capability

The Codex-specific capability-egress slice now exists and must remain separate from the normal no-network Hand. Follow `docs/23-codex-capability-egress.md` to deploy the internal-only network, CONNECT proxy, dedicated auth volume, UDS bridge and Hermes service-scoped shim.

Before device authentication, collect the machine-verifiable boundary/preflight evidence in one run:

```bash
export FORGE_NORMAL_HAND_IMAGE='sha256:<normal-hand-image-id>'
infra/sandbox/probation-001-preflight-evidence.sh
```

The helper:

1. runs the normal gVisor compromise smoke against the exact probation workspace;
2. normalizes the smoke report into a hash-bound Reality Anchor;
3. runs the Codex app-server preflight through the Hermes shim/bridge;
4. normalizes that report into a second Reality Anchor;
5. optionally submits both anchors to a local Forge controller when `FORGE_CONTROLLER_URL` is set;
6. stops before ChatGPT device authentication.

Device authentication remains an explicit human gate:

```bash
sudo infra/sandbox/codex-device-login.sh
```

Do not enable `model.openai_runtime=codex_app_server` until the remaining proxy/secret/socket negative tests in `docs/23-codex-capability-egress.md` also have current Reality Anchors.

See `docs/24-reality-anchor-evidence.md` for the evidence-normalisation and ingestion rules.
