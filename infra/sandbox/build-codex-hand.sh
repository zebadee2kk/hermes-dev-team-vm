#!/usr/bin/env bash
set -euo pipefail

BASE_IMAGE="${1:-}"
CODEX_VERSION="${2:-}"
TAG="${3:-forge-codex-hand:probation}"

if [[ ! "$BASE_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]]; then
  echo "Usage: $0 <node-base@sha256:digest> <codex-version> [tag]" >&2
  echo "The Node base image must be digest-pinned." >&2
  exit 2
fi
if [[ ! "$CODEX_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-.+][A-Za-z0-9.-]+)?$ ]]; then
  echo "Codex version must be explicit, for example 0.142.4." >&2
  exit 2
fi

docker build \
  --build-arg "BASE_IMAGE=$BASE_IMAGE" \
  --build-arg "CODEX_VERSION=$CODEX_VERSION" \
  --file docker/codex-hand.Dockerfile \
  --tag "$TAG" \
  .

REPORTED_VERSION="$(docker run --rm --entrypoint codex "$TAG" --version)"
if [[ "$REPORTED_VERSION" != *"$CODEX_VERSION"* ]]; then
  echo "Built image reports unexpected Codex version: $REPORTED_VERSION" >&2
  exit 2
fi

IMAGE_ID="$(docker image inspect "$TAG" --format '{{.Id}}')"
if [[ ! "$IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "Docker did not return a content-addressed local image id." >&2
  exit 2
fi

printf '%s\n' "$IMAGE_ID"
