#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LANE_MANIFEST="${FORGE_LANE_MANIFEST:-$ROOT_DIR/config/worker-lanes.yaml}"
FORGE_INTERNAL_URL="${FORGE_INTERNAL_URL:-http://127.0.0.1:8080}"
FORGE_KNOWLEDGE_ROOT="${FORGE_KNOWLEDGE_ROOT:-$ROOT_DIR/knowledge}"

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
if [[ ! -d "$FORGE_KNOWLEDGE_ROOT/wiki" ]]; then
  echo "Forge knowledge root is invalid: $FORGE_KNOWLEDGE_ROOT" >&2
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

  # The MCP process receives only non-secret local paths/URLs. It does not receive
  # DATABASE_URL, provider keys, the LiteLLM master key, or Sandbox Broker credentials.
  hermes -p "$lane" mcp remove forge-assurance >/dev/null 2>&1 || true
  hermes -p "$lane" mcp add forge-assurance \
    --command env \
    --args "FORGE_INTERNAL_URL=$FORGE_INTERNAL_URL" \
      "FORGE_KNOWLEDGE_ROOT=$FORGE_KNOWLEDGE_ROOT" \
      python -m forge_controller.mcp_server >/dev/null

  config_path="$(hermes -p "$lane" config path)"
  profile_dir="$(dirname "$config_path")"
  skills_dir="$profile_dir/skills"
  mkdir -p "$skills_dir"
  for skill_path in "$ROOT_DIR"/integrations/hermes/skills/*; do
    [[ -d "$skill_path" ]] || continue
    skill_name="$(basename "$skill_path")"
    mkdir -p "$skills_dir/$skill_name"
    cp "$skill_path/SKILL.md" "$skills_dir/$skill_name/SKILL.md"
  done
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

if [[ "${FORGE_ENABLE_KNOWLEDGE_CRON:-false}" == "true" ]]; then
  FORGE_REPO_ROOT="$ROOT_DIR" \
  FORGE_KNOWLEDGE_ROOT="$FORGE_KNOWLEDGE_ROOT" \
    bash "$ROOT_DIR/integrations/hermes/configure-knowledge-cron.sh"
else
  echo "Knowledge cron remains disabled. Set FORGE_ENABLE_KNOWLEDGE_CRON=true during bootstrap to create the supported Hermes maintenance/radar jobs."
fi

echo "Hermes Forge lanes configured from $LANE_MANIFEST. Export FORGE_GATEWAY_KEY in the Hermes gateway service environment before starting the gateway."
echo "Compiled knowledge exposed read-only from $FORGE_KNOWLEDGE_ROOT through forge-assurance MCP."
echo "Next: hermes gateway restart && hermes kanban init"
