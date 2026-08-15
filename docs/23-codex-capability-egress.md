# Codex probation: capability egress and gVisor Hand

This is the deployment design for Probation 001. It preserves ADR-005: Hermes remains Brain-side and the Codex process is a disposable Hand.

## Runtime path

```text
Hermes engineering lane
  -> bare `codex` lookup
  -> /opt/forge/codex-shim/bin/codex (unprivileged stdio client)
  -> /run/forge-codex/codex.sock
  -> forge-codex-bridge (trusted local service; Docker group only here)
  -> fixed root-owned runtime policy (/etc/forge/codex-runtime.env)
  -> docker run --runtime=runsc -i ... immutable Codex Hand
  -> framed stdout/stderr/stdin over the UDS back to Hermes
```

The Hermes service account is **not** in the Docker group and receives no sudo rule. Access to the bridge is controlled by the Unix-socket group. The bridge validates every launch before touching Docker.

The bridge permits only:

- `codex --version`;
- `codex app-server` (and explicit `--stdio`);
- app-server JSON-schema/TypeScript generation with output inside the pinned probation workspace.

It rejects `codex exec`, login, MCP administration and arbitrary CLI commands.

## Workspace scope

`FORGE_CODEX_WORKSPACE` is one exact task workspace, for example:

```text
/var/lib/forge/workspaces/forge/probation-001
```

The bridge rejects a CWD outside that directory. The workspace is bind-mounted at the **same absolute path** inside the Hand so app-server `cwd` values created by Hermes remain valid. No sibling project/workspace is mounted.

## Network shape

The Codex Hand joins only `forge-codex-internal`, a Docker `internal: true` network. It has no ordinary direct Internet route.

A separate non-root `forge-codex-egress` proxy joins both the internal network and an outbound network. The Hand receives HTTP(S) proxy variables pointing at that service. The proxy:

- accepts only HTTP `CONNECT`;
- permits exact configured hostnames only;
- permits port 443 only;
- rejects IP-literal CONNECT targets;
- resolves the hostname itself;
- rejects loopback, private, link-local, metadata/reserved or otherwise non-global resolved addresses;
- tunnels TLS opaquely and does not receive Codex credentials in proxy headers.

Initial allow-set for the ChatGPT subscription path:

- `chatgpt.com`
- `auth.openai.com`

Do not broaden this list pre-emptively. If a pinned Codex release demonstrates another required endpoint during preflight, record the failed evidence, verify the endpoint from pinned source/official documentation, and change policy explicitly.

## Dedicated Codex identity

Codex uses a dedicated Docker volume `forge-codex-probation-auth` as `CODEX_HOME=/codex-home`. This volume is the only credential-bearing state available to the candidate runtime. It must contain no Forge DB credentials, LiteLLM keys, GitHub credentials, Docker credentials or host-control material.

ChatGPT device-code enrolment is a one-time explicit human authentication gate. The helper prints only the verification URL and user code; Codex persists/refreshes tokens in the dedicated volume.

## Deploy

### 1. Validate/install gVisor

Follow `infra/sandbox/README.md` and run the normal Hand smoke first.

### 2. Build the capability proxy

Set a digest-pinned Python base image and start the proxy/network stack:

```bash
export FORGE_PROXY_BASE_IMAGE='python:3.12-slim@sha256:<digest>'
docker compose -f infra/sandbox/codex-egress.compose.yaml up -d --build
```

Do not publish the proxy port to the host/LAN.

### 3. Build the pinned Codex Hand

Use a Node Debian-family base image pinned by digest and an explicit Codex package version:

```bash
CODEX_IMAGE="$(infra/sandbox/build-codex-hand.sh \
  'node:22-bookworm-slim@sha256:<digest>' \
  '<tested-codex-version>')"
echo "$CODEX_IMAGE"
```

The helper verifies `codex --version` and returns Docker's immutable local image ID.

### 4. Create the exact probation workspace and auth volume

```bash
sudo install -d -o hermes -g hermes -m 0750 \
  /var/lib/forge/workspaces/forge/probation-001
docker volume create forge-codex-probation-auth
```

Adjust the workspace owner to the dedicated Hermes service identity used on the target VM.

### 5. Install the bridge identity and root-owned policy

Use a shared Unix-socket group, while keeping Docker membership exclusive to the trusted bridge identity:

```bash
sudo groupadd --system forge-codex || true
sudo usermod -aG forge-codex hermes
sudo usermod -aG forge-codex forge-sandbox
# forge-sandbox already has the Docker authority used by the Sandbox Broker/bridge.

sudo install -m 0600 infra/sandbox/codex-runtime.env.example \
  /etc/forge/codex-runtime.env
sudoedit /etc/forge/codex-runtime.env
```

Set `FORGE_CODEX_IMAGE` to the immutable ID returned by the build and verify the exact workspace/network/volume/proxy settings. This file contains policy references, not credentials, and must remain root-owned/non-writable to the service accounts.

Install/start the bridge:

```bash
sudo install -m 0644 infra/sandbox/forge-codex-bridge.service \
  /etc/systemd/system/forge-codex-bridge.service
sudo systemctl daemon-reload
sudo systemctl enable --now forge-codex-bridge
```

The service runs as `forge-sandbox`, primary group `forge-codex`, supplementary Docker group. Hermes joins only `forge-codex`, so it can open the bridge socket but cannot open `/var/run/docker.sock`.

### 6. Install the Hermes `codex` shim

```bash
sudo install -d -m 0755 /opt/forge/codex-shim/bin
sudo install -m 0755 integrations/hermes/codex-sandbox-shim.sh \
  /opt/forge/codex-shim/bin/codex
```

Prepend `/opt/forge/codex-shim/bin` to the Hermes gateway/service PATH. Do not replace the host's administrative Codex binary globally. The reviewed Hermes beta runtime resolves a bare `codex` executable, so this service-specific PATH is the intentional integration seam.

### 7. Enrol the dedicated ChatGPT identity

```bash
sudo infra/sandbox/codex-device-login.sh
```

Complete the displayed device URL/code in a normal browser. Do not copy auth files into project workspaces.

### 8. Run preflight from the exact probation workspace

```bash
cd /var/lib/forge/workspaces/forge/probation-001
PATH="/opt/forge/codex-shim/bin:$PATH" \
  python /path/to/repo/integrations/hermes/codex-probation-preflight.py
```

Schema generation intentionally occurs below the current workspace so the bridge never needs to mount host `/tmp`.

## Mandatory live evidence before enabling the Hermes runtime

Record Reality Anchors for:

1. normal no-network Hand compromise smoke;
2. Codex shim `--version` through the UDS bridge/runsc;
3. app-server schema generation through the shim;
4. successful device login/account state without token disclosure;
5. direct Internet and metadata access denied from the Codex Hand when proxy variables are removed;
6. proxy rejects an unapproved hostname and IP-literal target;
7. proxy permits the pinned Codex release's required ChatGPT/auth flows only;
8. sibling workspace, Docker socket, containerd socket and Forge secret access denied;
9. bridge disconnect/timeout removes the disposable container;
10. rollback to `model.openai_runtime=auto` without losing the Task Capsule/workspace.

Only after those pass should one engineering lane switch to `model.openai_runtime=codex_app_server` for the two real probation workloads.
