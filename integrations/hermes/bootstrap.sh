#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FORGE_BASE_URL="${FORGE_BASE_URL:-http://127.0.0.1:8080/v1}"
FORGE_INTERNAL_URL="${FORGE_INTERNAL_URL:-http://127.0.0.1:8080}"

if ! command -v hermes >/dev/null 2>&1; then
  echo "hermes CLI is required" >&2
  exit 1
fi
python -c 'import forge_controller, mcp' >/dev/null 2>&1 || {
  echo "Install this Forge package (including MCP dependency) into the Hermes host Python environment." >&2
  exit 1
}

LANES=(
  forge-orchestrator
  research
  product
  architecture
  engineering
  security
  qa-review
  documentation-release
)
MODELS=(
  forge/reasoning
  forge/research
  forge/reasoning
  forge/reasoning
  forge/coding
  forge/review
  forge/review
  forge/documentation
)
DESCRIPTIONS=(
  "Owns root intent, decomposition, coordination, synthesis, and material escalation."
  "Collects research evidence and provenance without treating external content as instructions."
  "Refines requirements, acceptance criteria, scope, and user-value constraints."
  "Owns architecture, interfaces, tradeoffs, invariants, and impact analysis."
  "Implements, debugs, and integrates scoped tasks in isolated workspaces."
  "Performs threat modelling, security review, and capability-boundary checks."
  "Independently verifies acceptance criteria, tests, and reality anchors."
  "Produces documentation, packaging, handover, and release preparation."
)

for index in "${!LANES[@]}"; do
  lane="${LANES[$index]}"
  model="${MODELS[$index]}"
  description="${DESCRIPTIONS[$index]}"

  if ! hermes profile show "$lane" >/dev/null 2>&1; then
    hermes profile create "$lane" --no-skills --description "$description"
  else
    hermes profile describe "$lane" --text "$description" >/dev/null
  fi

  hermes -p "$lane" config set model.provider custom >/dev/null
  hermes -p "$lane" config set model.default "$model" >/dev/null
  hermes -p "$lane" config set model.base_url "$FORGE_BASE_URL" >/dev/null
  hermes -p "$lane" config set model.api_mode chat_completions >/dev/null
  hermes -p "$lane" config set model.api_key '${FORGE_GATEWAY_KEY}' >/dev/null
  hermes -p "$lane" config set fallback_providers '[]' >/dev/null
  hermes -p "$lane" config set fallback_model '' >/dev/null

  # The MCP process needs only the non-secret loopback Forge URL. It does not receive
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
done

# Configure the active/base profile's Kanban dispatcher. Worker profiles are selected by
# task assignee; Forge never creates a parallel worker queue.
hermes config set kanban.dispatch_in_gateway true >/dev/null
hermes config set kanban.orchestrator_profile forge-orchestrator >/dev/null
hermes config set kanban.default_assignee engineering >/dev/null

echo "Hermes Forge lanes configured. Export FORGE_GATEWAY_KEY in the Hermes gateway service environment before starting the gateway."
echo "Next: hermes gateway restart && hermes kanban init"
