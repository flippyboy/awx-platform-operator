#!/usr/bin/env bash
# Create kind cluster and apply CRDs + platform smoke stack.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-awx-platform}"
# Prefer compose-built jewel-with-UI (make build-jewel) over public API-only image
JEWEL_IMAGE="${JEWEL_IMAGE:-awx-compose/jewel:local}"
BUILD_JEWEL="${BUILD_JEWEL:-false}"

cd "$ROOT"
# shellcheck source=kind-load-image.sh
source "$ROOT/hack/scripts/kind-load-image.sh"

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo ">> Creating kind cluster $CLUSTER_NAME"
  kind create cluster --config hack/kind/cluster.yaml
else
  echo ">> Kind cluster $CLUSTER_NAME already exists"
  kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null
fi

echo ">> Sync CRDs from operator tree into hack/kind/crds/"
cp -f config/crd/bases/*.yaml hack/kind/crds/

echo ">> Applying CRDs first"
kubectl apply -k hack/kind/crds/
kubectl wait --for=condition=Established crd/awxs.awx.ansible.com --timeout=60s
kubectl wait --for=condition=Established crd/awxgateways.awx.ansible.com --timeout=60s
kubectl wait --for=condition=Established crd/awxplatforms.awx.ansible.com --timeout=60s

# Gateway TLS (Jewel+Envoy) defaults to cert-manager Certificates
if [ "${INSTALL_CERT_MANAGER:-true}" = "true" ]; then
  "$ROOT/hack/scripts/kind-install-cert-manager.sh"
fi

# Ensure local jewel-with-UI is available inside kind before applying Deployments
if ! docker image inspect "$JEWEL_IMAGE" >/dev/null 2>&1; then
  if [ "$BUILD_JEWEL" = "true" ] || [ "${1:-}" = "--build" ]; then
    echo ">> Building $JEWEL_IMAGE (make build-jewel)"
    make build-jewel
  else
    echo "!! Missing docker image: $JEWEL_IMAGE"
    echo "   Build with: make build-jewel"
    echo "   Or: BUILD_JEWEL=true ./scripts/kind-up.sh"
    echo "   Or override: JEWEL_IMAGE=ghcr.io/ansible/jewel:latest ./scripts/kind-up.sh"
    exit 1
  fi
fi
echo ">> Loading Jewel image into kind: $JEWEL_IMAGE"
kind_load_image "$JEWEL_IMAGE"

echo ">> Applying full kind kustomize"
kubectl apply -k hack/kind/

# Align smoke + sample CRs with the image we loaded (kustomize defaults may differ)
read -r JEWEL_REPO JEWEL_TAG <<<"$(kind_image_parts "$JEWEL_IMAGE")"
kubectl -n awx-platform set image deploy/jewel "jewel=${JEWEL_IMAGE}" 2>/dev/null || true
kubectl -n awx-platform patch awxgateway demo-gateway --type merge -p \
  "{\"spec\":{\"image\":\"${JEWEL_REPO}\",\"image_version\":\"${JEWEL_TAG}\",\"ui_mode\":\"baked\"}}" \
  2>/dev/null || true

echo ">> Waiting for postgres..."
kubectl -n awx-platform rollout status deploy/postgres --timeout=180s
echo ">> Waiting for postgres-init job..."
kubectl -n awx-platform wait --for=condition=complete job/postgres-init-gateway-db --timeout=180s || true
echo ">> Waiting for redis-jewel..."
kubectl -n awx-platform rollout status deploy/redis-jewel --timeout=120s
echo ">> Waiting for jewel..."
kubectl -n awx-platform rollout status deploy/jewel --timeout=600s || {
  echo "!! jewel rollout not ready"
  kubectl -n awx-platform get pods -o wide
  kubectl -n awx-platform logs deploy/jewel --tail=80 || true
  exit 1
}
echo ">> Waiting for envoy..."
kubectl -n awx-platform rollout status deploy/envoy --timeout=180s || true

echo ">> Cluster ready. Run: ./scripts/kind-test.sh"
