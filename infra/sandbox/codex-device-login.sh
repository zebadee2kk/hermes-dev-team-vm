#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this one-time Codex device login helper as root." >&2
  exit 2
fi

CONFIG=/etc/forge/codex-runtime.env
if [[ ! -f "$CONFIG" ]]; then
  echo "Missing $CONFIG" >&2
  exit 2
fi

# The file is root-owned deployment configuration and contains no secret. shellcheck disable=SC1090
source "$CONFIG"

: "${FORGE_CODEX_IMAGE:?missing FORGE_CODEX_IMAGE}"
: "${FORGE_CODEX_NETWORK:?missing FORGE_CODEX_NETWORK}"
: "${FORGE_CODEX_AUTH_VOLUME:?missing FORGE_CODEX_AUTH_VOLUME}"
: "${FORGE_CODEX_PROXY_URL:?missing FORGE_CODEX_PROXY_URL}"

if [[ ! "$FORGE_CODEX_IMAGE" =~ ^(sha256:[0-9a-f]{64}|.+@sha256:[0-9a-f]{64})$ ]]; then
  echo "FORGE_CODEX_IMAGE must be content-addressed." >&2
  exit 2
fi

# The user completes the verification URL/code in a normal browser. Tokens stay inside
# the dedicated Codex volume and are never printed by the helper.
docker run --rm -i \
  --runtime runsc \
  --network "$FORGE_CODEX_NETWORK" \
  --ipc none \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 128 \
  --memory 1024m \
  --cpus 1 \
  --user 65532:65532 \
  --mount "type=volume,src=$FORGE_CODEX_AUTH_VOLUME,dst=/codex-home,rw" \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
  --env CODEX_HOME=/codex-home \
  --env HOME=/tmp/home \
  --env "HTTP_PROXY=$FORGE_CODEX_PROXY_URL" \
  --env "HTTPS_PROXY=$FORGE_CODEX_PROXY_URL" \
  --env "http_proxy=$FORGE_CODEX_PROXY_URL" \
  --env "https_proxy=$FORGE_CODEX_PROXY_URL" \
  --env NO_PROXY=localhost,127.0.0.1,::1 \
  --env no_proxy=localhost,127.0.0.1,::1 \
  "$FORGE_CODEX_IMAGE" \
  python3 /opt/forge/codex-device-login.py
