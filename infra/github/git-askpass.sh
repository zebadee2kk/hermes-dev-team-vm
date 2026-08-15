#!/usr/bin/env bash
set -euo pipefail

prompt="${1:-}"
case "$prompt" in
  *Username*|*username*)
    printf '%s\n' 'x-access-token'
    ;;
  *Password*|*password*)
    : "${FORGE_GITHUB_INSTALLATION_TOKEN:?missing request-scoped installation token}"
    printf '%s\n' "$FORGE_GITHUB_INSTALLATION_TOKEN"
    ;;
  *)
    exit 1
    ;;
esac
