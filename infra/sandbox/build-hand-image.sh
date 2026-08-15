#!/usr/bin/env bash
set -euo pipefail

BASE_IMAGE="${1:-}"
TAG="${2:-forge-hand:local}"

if [[ ! "$BASE_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]]; then
  echo "Usage: $0 <base-image@sha256:digest> [tag]" >&2
  echo "The base image must be digest-pinned." >&2
  exit 2
fi

docker build \
  --build-arg "BASE_IMAGE=$BASE_IMAGE" \
  --file docker/hand.Dockerfile \
  --tag "$TAG" \
  .

IMAGE_ID="$(docker image inspect "$TAG" --format '{{.Id}}')"
if [[ ! "$IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "Docker did not return a content-addressed local image id." >&2
  exit 2
fi

printf '%s\n' "$IMAGE_ID"
