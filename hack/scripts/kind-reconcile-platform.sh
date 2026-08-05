#!/usr/bin/env bash
# Full platform path: external PG (+ optional external Redis) → gateway → AWX CR controller → trust → optional Ingress.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
NS="${GATEWAY_NS:-awx-platform}"
PLATFORM="${PLATFORM_NAME:-demo}"
GW_NAME="${GATEWAY_NAME:-demo-gateway}"
CTRL_NAME="${CONTROLLER_NAME:-demo-controller}"
CLUSTER_NAME="${CLUSTER_NAME:-awx-platform}"
INSTALL_INGRESS="${INSTALL_INGRESS:-false}"
INGRESS_HOST="${INGRESS_HOST:-awx.localtest.me}"

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo "!! kind cluster missing — run ./scripts/kind-up.sh"
  exit 1
fi

echo "=== 1) Shared external Postgres secret (unmanaged) ==="
kubectl -n "$NS" create secret generic platform-pg \
  --from-literal=host=postgres \
  --from-literal=port=5432 \
  --from-literal=database=awx \
  --from-literal=username=awx \
  --from-literal=password=awx \
  --from-literal=type=unmanaged \
  --from-literal=sslmode=prefer \
  --dry-run=client -o yaml | kubectl apply -f -

# Per-component secrets (same external instance; gateway uses separate DB name in role)
kubectl -n "$NS" create secret generic "${GW_NAME}-pg" \
  --from-literal=host=postgres \
  --from-literal=port=5432 \
  --from-literal=database=awx \
  --from-literal=username=awx \
  --from-literal=password=awx \
  --from-literal=type=unmanaged \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NS" create secret generic "${CTRL_NAME}-pg" \
  --from-literal=host=postgres \
  --from-literal=port=5432 \
  --from-literal=database=awx \
  --from-literal=username=awx \
  --from-literal=password=awx \
  --from-literal=type=unmanaged \
  --dry-run=client -o yaml | kubectl apply -f -

if [ "${USE_EXTERNAL_REDIS:-false}" = "true" ]; then
  echo "=== Optional external Redis secret (redis-jewel Service as external) ==="
  kubectl -n "$NS" create secret generic platform-redis \
    --from-literal=url=redis://redis-jewel:6379/0 \
    --from-literal=host=redis-jewel \
    --from-literal=port=6379 \
    --dry-run=client -o yaml | kubectl apply -f -
  export REDIS_CONFIGURATION_SECRET=platform-redis
fi

if [ "$INSTALL_INGRESS" = "true" ]; then
  echo "=== Install ingress-nginx (kind) ==="
  kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
  kubectl -n ingress-nginx wait --for=condition=ready pod -l app.kubernetes.io/component=controller --timeout=300s || true
fi

echo "=== 2) Patch AWXPlatform sample ==="
kubectl -n "$NS" patch awxplatform "$PLATFORM" --type merge -p "
{
  \"spec\": {
    \"postgres_configuration_secret\": \"platform-pg\",
    \"redis_configuration_secret\": \"${REDIS_CONFIGURATION_SECRET:-}\",
    \"admin_password_secret\": \"${GW_NAME}-admin-password\",
    \"controller\": {\"create\": true, \"name\": \"${CTRL_NAME}\"},
    \"gateway\": {\"create\": true, \"name\": \"${GW_NAME}\", \"image\": \"awx-compose/jewel\", \"image_version\": \"local\", \"ui_mode\": \"baked\"},
    \"ingress\": {
      \"type\": \"$([ \"$INSTALL_INGRESS\" = true ] && echo ingress || echo none)\",
      \"ingress_class_name\": \"nginx\",
      \"hosts\": [{\"hostname\": \"${INGRESS_HOST}\"}]
    },
    \"open_source_defaults\": true
  }
}" 2>/dev/null || kubectl apply -f hack/kind/samples/awxplatform.yaml

echo "=== 3) Gateway (Jewel + Envoy + trust secret) ==="
if [ -n "${REDIS_CONFIGURATION_SECRET:-}" ]; then
  # Pass through env for reconcile playbook generation
  export GATEWAY_REDIS_SECRET="$REDIS_CONFIGURATION_SECRET"
fi
if [ "$INSTALL_INGRESS" = "true" ]; then
  export GATEWAY_INGRESS_TYPE=ingress
  export GATEWAY_INGRESS_HOST="$INGRESS_HOST"
fi
./scripts/kind-reconcile-gateway.sh

echo "=== 4) Controller via AWX CR + installer ==="
./scripts/kind-reconcile-controller.sh

echo "=== 5) Platform status ==="
kubectl -n "$NS" get awxplatform,awxgateway,awx,ingress 2>/dev/null || true
echo ">> Done. Preferred path is AWX CR (${CTRL_NAME}), not controller-smoke."
echo "   JWT: port-forward svc/${GW_NAME}-envoy 9080:9080"
if [ "$INSTALL_INGRESS" = "true" ]; then
  echo "   Ingress host: https://${INGRESS_HOST}/ (map DNS or /etc/hosts to kind node)"
fi
