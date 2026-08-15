#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This installer supports Linux hosts only." >&2
  exit 2
fi

case "$(uname -m)" in
  x86_64|aarch64) ;;
  *) echo "Unsupported architecture: $(uname -m)" >&2; exit 2 ;;
esac

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker must be installed before gVisor." >&2
  exit 2
fi

sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates curl gnupg

tmp_key="$(mktemp)"
trap 'rm -f "$tmp_key"' EXIT
curl -fsSL https://gvisor.dev/archive.key | gpg --dearmor >"$tmp_key"
sudo install -m 0644 "$tmp_key" /usr/share/keyrings/gvisor-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" \
  | sudo tee /etc/apt/sources.list.d/gvisor.list >/dev/null

sudo apt-get update
sudo apt-get install -y runsc

if ! docker info --format '{{json .Runtimes}}' | grep -q '"runsc"'; then
  sudo runsc install
  sudo systemctl restart docker
fi

runsc --version
docker version --format '{{.Server.Version}}'
docker info --format '{{json .Runtimes}}'

if ! docker info --format '{{json .Runtimes}}' | grep -q '"runsc"'; then
  echo "runsc is installed but is not registered with Docker." >&2
  exit 2
fi

echo "gVisor runsc is installed and registered. Run forge-sandbox-smoke with a content-addressed Hand image for the security proof."
