#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LANE_MANIFEST="${FORGE_LANE_MANIFEST:-$ROOT_DIR/config/worker-lanes.yaml}"
FORGE_INTERNAL_URL="${FORGE_INTERNAL_URL:-http://127.0.0.1:8080}"

if ! command -v hermes >/dev/null 2>&1; then
  echo "hermes CLI is required" >&2
  exit 1
fi
python -c 'import forge_controller, mcp, yaml' >/dev/null 2>&1 || {
  echo "Install this Forge package (including MCP and YAML dependencies) into the Hermes host Python environment." >&2
  exit 1
}
if [[ ! -f "$LANE_MANIFEST" ]]; then
  echo "Forge lane manifest not found: $LANE_MANIFEST" >&2
  exit 1
fi

manifest_value() {
  python - "$LANE_MANIFEST" "$1" <<'PY'
import sys
from pathlib import Path

import yaml

manifest = yaml.safe_load(Path(sys.argv[1]).read_text())
value = manifest
for part in sys.argv[2].split("."):
    value = value[part]
if isinstance(value, bool):
    print(str(value).lower())
else:
    print(value)
PY
}

FORGE_BASE_URL="${FORGE_BASE_URL:-$(manifest_value hermes.base_url)}"
HERMES_PROVIDER="$(manifest_value hermes.provider)"
HERMES_API_MODE="$(manifest_value hermes.api_mode)"
HERMES_API_KEY_REF="$(manifest_value hermes.api_key_ref)"
DISABLE_DIRECT_FALLBACKS="$(manifest_value hermes.disable_direct_provider_fallbacks)"
KANBAN_DISPATCH="$(manifest_value hermes.kanban.dispatch_in_gateway)"
KANBAN_ORCHESTRATOR="$(manifest_value hermes.kanban.orchestrator_profile)"
KANBAN_DEFAULT_ASSIGNEE="$(manifest_value hermes.kanban.default_assignee)"

while IFS=$'\t' read -r lane model description; do
  [[ -n "$lane" ]] || continue

  if ! hermes profile show "$lane" >/dev/null 2>&1; then
    hermes profile create "$lane" --no-skills --description "$description"
  else
    hermes profile describe "$lane" --text "$description" >/dev/null
  fi

  hermes -p "$lane" config set model.provider "$HERMES_PROVIDER" >/dev/null
  hermes -p "$lane" config set model.default "$model" >/dev/null
  hermes -p "$lane" config set model.base_url "$FORGE_BASE_URL" >/dev/null
  hermes -p "$lane" config set model.api_mode "$HERMES_API_MODE" >/dev/null
  hermes -p "$lane" config set model.api_key "$HERMES_API_KEY_REF" >/dev/null
  if [[ "$DISABLE_DIRECT_FALLBACKS" == "true" ]]; then
    hermes -p "$lane" config set fallback_providers '[]' >/dev/null
    hermes -p "$lane" config set fallback_model '' >/dev/null
  fi

  # The MCP process receives only a non-secret loopback Forge URL. It does not receive
  # DATABASE_URL, provider keys, or LiteLLM credentials.
  hermes -p "$lane" mcp remove forge-assurance >/dev/null 2>&1 || true
  hermes -p "$lane" mcp add forge-assurance \
    --command env \
    --args "FORGE_INTERNAL_URL=$FORGE_INTERNAL_URL" python -m forge_controller.mcp_server >/dev/null

  config_path="$(hermes -p "$lane" config path)"
  profile_dir="$(dirname "$config_path")"
  mkdir -p "$profile_dir/skills/forge-task-contract" "$profile_dir/skills/forge-reality-anchor"
  cp "$ROOT_DIR/integrations/hermes/skills/forge-task-contract/SKILL.md" \
    "$profile_dir/skills/forge-task-contract/SKILL.md"
  cp "$ROOT_DIR/integrations/hermes/skills/forge-reality-anchor/SKILL.md" \
    "$profile_dir/skills/forge-reality-anchor/SKILL.md"
done < <(
  python - "$LANE_MANIFEST" <<'PY'
import sys
from pathlib import Path

import yaml

manifest = yaml.safe_load(Path(sys.argv[1]).read_text())
for lane, config in manifest["lanes"].items():
    if not config.get("durable", False):
        continue
    model = config["model"]
    description = config["description"].replace("\t", " ").replace("\n", " ")
    print(f"{lane}\t{model}\t{description}")
PY
)

# Configure the active/base profile's Kanban dispatcher. Worker profiles are selected by
# task assignee; Forge never creates a parallel worker queue.
hermes config set kanban.dispatch_in_gateway "$KANBAN_DISPATCH" >/dev/null
hermes config set kanban.orchestrator_profile "$KANBAN_ORCHESTRATOR" >/dev/null
hermes config set kanban.default_assignee "$KANBAN_DEFAULT_ASSIGNEE" >/dev/null

echo "Hermes Forge lanes configured from $LANE_MANIFEST. Export FORGE_GATEWAY_KEY in the Hermes gateway service environment before starting the gateway."
echo "Next: hermes gateway restart && hermes kanban init"
