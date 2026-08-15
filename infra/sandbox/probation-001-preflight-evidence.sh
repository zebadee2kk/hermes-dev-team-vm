#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

: "${FORGE_NORMAL_HAND_IMAGE:?set FORGE_NORMAL_HAND_IMAGE to the immutable normal Hand image ID/digest}"

FORGE_PROJECT_ID="${FORGE_PROJECT_ID:-forge}"
FORGE_WORKSPACE_ROOT="${FORGE_WORKSPACE_ROOT:-/var/lib/forge/workspaces}"
FORGE_PROBATION_WORKSPACE="${FORGE_PROBATION_WORKSPACE:-$FORGE_WORKSPACE_ROOT/forge/probation-001}"
FORGE_EVIDENCE_DIR="${FORGE_EVIDENCE_DIR:-/var/lib/forge/evidence/probation-001}"
FORGE_CODEX_SHIM_DIR="${FORGE_CODEX_SHIM_DIR:-/opt/forge/codex-shim/bin}"
FORGE_SANDBOX_TASK_ID="${FORGE_SANDBOX_TASK_ID:-probation-001-normal-hand-smoke}"
FORGE_CODEX_TASK_ID="${FORGE_CODEX_TASK_ID:-probation-001-codex-preflight}"
FORGE_SANDBOX_SMOKE_BIN="${FORGE_SANDBOX_SMOKE_BIN:-forge-sandbox-smoke}"
FORGE_EVIDENCE_BIN="${FORGE_EVIDENCE_BIN:-forge-evidence}"

if [[ ! -d "$FORGE_PROBATION_WORKSPACE" ]]; then
  echo "Probation workspace does not exist: $FORGE_PROBATION_WORKSPACE" >&2
  exit 2
fi
if [[ ! -x "$FORGE_CODEX_SHIM_DIR/codex" ]]; then
  echo "Codex sandbox shim is not executable: $FORGE_CODEX_SHIM_DIR/codex" >&2
  exit 2
fi

mkdir -p "$FORGE_EVIDENCE_DIR"

submit_args=()
if [[ -n "${FORGE_CONTROLLER_URL:-}" ]]; then
  submit_args+=(--submit-url "$FORGE_CONTROLLER_URL")
  if [[ "${FORGE_ALLOW_REMOTE_CONTROLLER:-false}" == "true" ]]; then
    submit_args+=(--allow-remote-controller)
  fi
fi

sandbox_report="$FORGE_EVIDENCE_DIR/normal-hand-smoke.report.json"
sandbox_anchor="$FORGE_EVIDENCE_DIR/normal-hand-smoke.anchor.json"
codex_report="$FORGE_EVIDENCE_DIR/codex-preflight.report.json"
codex_anchor="$FORGE_EVIDENCE_DIR/codex-preflight.anchor.json"

"$FORGE_SANDBOX_SMOKE_BIN" \
  --workspace-root "$FORGE_WORKSPACE_ROOT" \
  --workspace "$FORGE_PROBATION_WORKSPACE" \
  --image "$FORGE_NORMAL_HAND_IMAGE" \
  --project-id "$FORGE_PROJECT_ID" \
  --task-id "$FORGE_SANDBOX_TASK_ID" \
  --evidence-out "$sandbox_report" >/dev/null

"$FORGE_EVIDENCE_BIN" \
  --input "$sandbox_report" \
  --output "$sandbox_anchor" \
  --reproduce "FORGE_NORMAL_HAND_IMAGE=$FORGE_NORMAL_HAND_IMAGE $REPO_ROOT/infra/sandbox/probation-001-preflight-evidence.sh" \
  "${submit_args[@]}" >/dev/null

(
  cd "$FORGE_PROBATION_WORKSPACE"
  PATH="$FORGE_CODEX_SHIM_DIR:$PATH" \
    python "$REPO_ROOT/integrations/hermes/codex-probation-preflight.py" \
      --project-id "$FORGE_PROJECT_ID" \
      --task-id "$FORGE_CODEX_TASK_ID"
) >"$codex_report"

"$FORGE_EVIDENCE_BIN" \
  --input "$codex_report" \
  --output "$codex_anchor" \
  --reproduce "cd $FORGE_PROBATION_WORKSPACE && PATH=$FORGE_CODEX_SHIM_DIR:\$PATH python $REPO_ROOT/integrations/hermes/codex-probation-preflight.py --project-id $FORGE_PROJECT_ID --task-id $FORGE_CODEX_TASK_ID" \
  "${submit_args[@]}" >/dev/null

cat <<EOF
Probation 001 pre-device evidence passed.

Reports:
  $sandbox_report
  $codex_report

Validated Reality Anchors:
  $sandbox_anchor
  $codex_anchor

Next explicit human gate:
  sudo $REPO_ROOT/infra/sandbox/codex-device-login.sh

After device authentication, continue the negative proxy/secret/socket tests in docs/23-codex-capability-egress.md before enabling codex_app_server.
EOF
