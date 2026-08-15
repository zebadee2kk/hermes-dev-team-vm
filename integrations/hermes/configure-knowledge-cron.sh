#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${FORGE_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
DELIVER="${FORGE_KNOWLEDGE_DELIVER:-local}"
LINT_SCHEDULE="${FORGE_KNOWLEDGE_LINT_SCHEDULE:-17 6 * * *}"
DIGEST_SCHEDULE="${FORGE_KNOWLEDGE_DIGEST_SCHEDULE:-0 8 * * *}"
RADAR_SCHEDULE="${FORGE_TECH_RADAR_SCHEDULE:-15 7 * * 0}"

if ! command -v hermes >/dev/null 2>&1; then
  echo "hermes CLI is required" >&2
  exit 1
fi

chmod +x "$ROOT_DIR/integrations/hermes/knowledge-maintenance.sh"
chmod +x "$ROOT_DIR/integrations/hermes/knowledge-digest.sh"

job_exists() {
  local name="$1"
  hermes cron list 2>/dev/null | grep -F "$name" >/dev/null 2>&1
}

ensure_script_job() {
  local name="$1"
  local schedule="$2"
  local script="$3"
  if job_exists "$name"; then
    echo "Hermes cron already configured: $name"
    return
  fi
  hermes cron create "$schedule" \
    --no-agent \
    --script "$script" \
    --deliver "$DELIVER" \
    --name "$name" >/dev/null
  echo "Configured Hermes cron: $name"
}

ensure_agent_job() {
  local name="$1"
  local schedule="$2"
  local prompt="$3"
  if job_exists "$name"; then
    echo "Hermes cron already configured: $name"
    return
  fi
  hermes cron create "$schedule" "$prompt" \
    --skill forge-tech-radar \
    --skill forge-knowledge-compiler \
    --workdir "$ROOT_DIR" \
    --deliver "$DELIVER" \
    --name "$name" >/dev/null
  echo "Configured Hermes cron: $name"
}

ensure_script_job \
  "Forge knowledge lint" \
  "$LINT_SCHEDULE" \
  "$ROOT_DIR/integrations/hermes/knowledge-maintenance.sh"

ensure_script_job \
  "Forge knowledge digest" \
  "$DIGEST_SCHEDULE" \
  "$ROOT_DIR/integrations/hermes/knowledge-digest.sh"

RADAR_PROMPT="Run the Forge weekly technology radar. Read config/technology-radar-sources.yaml and use the forge-tech-radar rules. Search only for developments since the previous weekly window. Social posts are discovery pointers only: locate a primary artifact before scoring. Ignore engagement metrics. Do not install, execute, adopt, compile into active knowledge, change policy, or promote anything. For each TEST-tier item with a concrete primary artifact, create or update a Hermes Kanban triage task assigned to research, attach forge-tech-radar and forge-knowledge-compiler skills, and use an idempotency key based on candidate slug plus ISO week. The task must require a Trust Envelope and trusted acquisition into immutable raw storage before any compile proposal. WATCH-tier items belong only in the concise radar output; IGNORE-tier items should not be queued. Keep the final report under 500 words."

ensure_agent_job \
  "Forge weekly technology radar" \
  "$RADAR_SCHEDULE" \
  "$RADAR_PROMPT"

echo "Knowledge cron setup complete. Ensure the Hermes cron platform toolset permits only the web/research and Kanban capabilities needed by the weekly radar; script-only lint/digest jobs use no LLM tokens."
