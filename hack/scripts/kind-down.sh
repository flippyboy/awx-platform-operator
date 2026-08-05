#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-awx-platform}"
echo ">> Deleting kind cluster $CLUSTER_NAME"
kind delete cluster --name "$CLUSTER_NAME"
