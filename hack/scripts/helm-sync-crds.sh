#!/usr/bin/env bash
# Sync operator CRDs into the Helm chart.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/config/crd/bases"
DST="$ROOT/charts/awx-platform-operator/crds"
mkdir -p "$DST"
rm -f "$DST"/*.yaml 2>/dev/null || true
for f in "$SRC"/*.yaml; do
  name=$(basename "$f")
  plural=$(echo "$name" | sed 's/awx\.ansible\.com_//;s/\.yaml$//')
  out="$DST/customresourcedefinition-${plural}.awx.ansible.com.yaml"
  cp "$f" "$out"
  echo "  $out"
done
echo ">> Synced CRDs into charts/awx-platform-operator/crds/"
