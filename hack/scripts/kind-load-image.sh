#!/usr/bin/env bash
# Load a local docker image into the kind cluster's containerd.
#
# kind load docker-image fails on some multi-arch OCI indexes; ctr import
# --no-unpack is more reliable. Usage:
#   ./scripts/kind-load-image.sh awx-compose/jewel:local
#   source scripts/kind-load-image.sh && kind_load_image awx-compose/jewel:local
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

CLUSTER_NAME="${CLUSTER_NAME:-awx-platform}"

kind_load_image() {
  local image="${1:?image ref required (e.g. awx-compose/jewel:local)}"
  local node="${CLUSTER_NAME}-control-plane"
  local force="${FORCE_IMAGE_LOAD:-false}"

  if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "!! docker image not found: $image" >&2
    return 1
  fi

  if ! docker inspect "$node" >/dev/null 2>&1; then
    echo "!! kind node container not found: $node (cluster $CLUSTER_NAME?)" >&2
    return 1
  fi

  # Re-import local compose images by default so tag rebuilds are picked up.
  if [ "$force" != "true" ] && [[ "$image" != awx-compose/* ]] \
    && docker exec "$node" ctr -n k8s.io images ls -q 2>/dev/null | grep -qF "$image"; then
    echo ">> Image already on kind node: $image"
    return 0
  fi

  echo ">> Loading $image into kind node $node (ctr --no-unpack)"
  docker save "$image" | docker exec -i "$node" ctr -n k8s.io images import --no-unpack -
  echo ">> Loaded $image"
}

# Split image:tag into repo + tag (last colon). No tag → latest.
kind_image_parts() {
  local ref="${1:?}"
  local repo tag
  if [[ "$ref" == *:* ]] && [[ "$ref" != *://* ]]; then
    # Handle registry:port/name:tag by only splitting on the last colon
    repo="${ref%:*}"
    tag="${ref##*:}"
    # If "tag" still has a slash, we likely hit host:port only — treat whole as repo
    if [[ "$tag" == */* ]]; then
      repo="$ref"
      tag="latest"
    fi
  else
    repo="$ref"
    tag="latest"
  fi
  printf '%s %s\n' "$repo" "$tag"
}

# Allow direct execution (skip when sourced)
if [[ "${BASH_SOURCE[0]:-}" == "${0:-}" ]] && [[ -n "${1:-}" ]]; then
  kind_load_image "$@"
fi
