#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${FORGE_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
KNOWLEDGE_ROOT="${FORGE_KNOWLEDGE_ROOT:-$ROOT_DIR/knowledge}"

count_files() {
  local path="$1"
  local pattern="$2"
  if [[ ! -d "$path" ]]; then
    echo 0
    return
  fi
  find "$path" -type f -name "$pattern" | wc -l | tr -d ' '
}

PROPOSALS="$(count_files "$KNOWLEDGE_ROOT/proposals" '*.yaml')"
CANDIDATES="$(count_files "$KNOWLEDGE_ROOT/candidates" '*.yaml')"
EVALS="$(count_files "$KNOWLEDGE_ROOT/evals" '*.yaml')"
PAGES="$(count_files "$KNOWLEDGE_ROOT/wiki" '*.md')"

set +e
LINT="$(forge-knowledge --root "$KNOWLEDGE_ROOT" lint 2>/dev/null)"
LINT_STATUS=$?
set -e

if [[ "$LINT_STATUS" -eq 0 ]]; then
  HEALTH="clean"
else
  HEALTH="attention-needed"
fi

printf 'Forge knowledge digest\n'
printf 'health: %s\n' "$HEALTH"
printf 'compiled_markdown_files: %s\n' "$PAGES"
printf 'compile_proposals: %s\n' "$PROPOSALS"
printf 'technology_candidates: %s\n' "$CANDIDATES"
printf 'candidate_evaluations: %s\n' "$EVALS"
if [[ "$HEALTH" != "clean" ]]; then
  printf 'lint: %s\n' "$LINT"
fi
