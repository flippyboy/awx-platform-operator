#!/usr/bin/env bash
# Reconcile AWXGateway role against kind (without building operator image).
#
# Uses the locally built jewel-with-UI image by default:
#   JEWEL_IMAGE=awx-compose/jewel:local  (make build-jewel)
# Override with e.g. JEWEL_IMAGE=ghcr.io/ansible/jewel:latest for public API-only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
NS="${GATEWAY_NS:-awx-platform}"
# Avoid clashing with environment NAME (often hostname on some systems)
GW_NAME="${GATEWAY_NAME:-demo-gateway}"
CLUSTER_NAME="${CLUSTER_NAME:-awx-platform}"
JEWEL_IMAGE="${JEWEL_IMAGE:-awx-compose/jewel:local}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

# shellcheck source=kind-load-image.sh
source "$ROOT/hack/scripts/kind-load-image.sh"

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo "!! kind cluster '$CLUSTER_NAME' not found — run ./scripts/kind-up.sh first"
  exit 1
fi

VENV="$ROOT/.venv-operator"
if [ -x "$VENV/bin/ansible-playbook" ]; then
  APB="$VENV/bin/ansible-playbook"
  AG="$VENV/bin/ansible-galaxy"
  export PATH="$VENV/bin:$PATH"
elif command -v ansible-playbook >/dev/null; then
  APB=ansible-playbook
  AG=ansible-galaxy
else
  echo "ansible-playbook required. Create venv: python3 -m venv .venv-operator && .venv-operator/bin/pip install ansible kubernetes kubernetes"
  exit 1
fi

# Ensure kubernetes collection
"$AG" collection install kubernetes.core 2>/dev/null || true

# Resolve jewel image (local with UI preferred)
if ! docker image inspect "$JEWEL_IMAGE" >/dev/null 2>&1; then
  if [ "${BUILD_JEWEL:-false}" = "true" ]; then
    echo ">> Building $JEWEL_IMAGE"
    make build-jewel
  else
    echo "!! Missing $JEWEL_IMAGE — run: make build-jewel"
    echo "   Or set JEWEL_IMAGE=ghcr.io/ansible/jewel:latest for public API-only image"
    exit 1
  fi
fi
read -r JEWEL_REPO JEWEL_TAG <<<"$(kind_image_parts "$JEWEL_IMAGE")"
echo ">> Jewel image: ${JEWEL_REPO}:${JEWEL_TAG} (from JEWEL_IMAGE=$JEWEL_IMAGE)"
kind_load_image "$JEWEL_IMAGE"

# Postgres secret in AWX shape (host/port/database/username/password)
kubectl -n "$NS" create secret generic "${GW_NAME}-pg" \
  --from-literal=host=postgres \
  --from-literal=port=5432 \
  --from-literal=database=awx \
  --from-literal=username=awx \
  --from-literal=password=awx \
  --dry-run=client -o yaml | kubectl apply -f -

# Point gateway CR at local jewel image + postgres secret
kubectl -n "$NS" patch awxgateway "$GW_NAME" --type merge -p \
  "{\"spec\":{\"image\":\"${JEWEL_REPO}\",\"image_version\":\"${JEWEL_TAG}\",\"ui_mode\":\"baked\",\"image_pull_policy\":\"IfNotPresent\",\"postgres_configuration_secret\":\"${GW_NAME}-pg\",\"admin_password_secret\":\"${GW_NAME}-admin-password\"}}" \
  2>/dev/null || true

CTRL_SVC=""
if kubectl -n "$NS" get svc demo-controller-service >/dev/null 2>&1; then
  CTRL_SVC=demo-controller-service
elif kubectl -n "$NS" get svc controller-web >/dev/null 2>&1; then
  CTRL_SVC=controller-web
fi

# External Redis (optional): GATEWAY_REDIS_SECRET or redis_url
REDIS_SECRET_VAR=""
REDIS_URL_VAR=""
REDIS_MANAGED=true
if [ -n "${GATEWAY_REDIS_SECRET:-}" ]; then
  REDIS_SECRET_VAR="${GATEWAY_REDIS_SECRET}"
  REDIS_MANAGED=false
elif [ -n "${GATEWAY_REDIS_URL:-}" ]; then
  REDIS_URL_VAR="${GATEWAY_REDIS_URL}"
  REDIS_MANAGED=false
fi

INGRESS_TYPE="${GATEWAY_INGRESS_TYPE:-none}"
INGRESS_HOST="${GATEWAY_INGRESS_HOST:-awx.localtest.me}"
FRONT_END="${GATEWAY_FRONT_END_URL:-https://localhost:8443}"
if [ "$INGRESS_TYPE" = "ingress" ]; then
  FRONT_END="https://${INGRESS_HOST}"
fi

PLAY="$ROOT/playbooks/reconcile-gateway-standalone.yml"
cat > "$PLAY" <<EOF
---
- hosts: localhost
  connection: local
  gather_facts: false
  collections:
    - kubernetes.core
  vars:
    ansible_operator_meta:
      name: ${GW_NAME}
      namespace: ${NS}
    api_version: awx.ansible.com/v1beta1
    kind: AWXGateway
    image: ${JEWEL_REPO}
    image_version: ${JEWEL_TAG}
    image_pull_policy: IfNotPresent
    image_pull_secrets: []
    replicas: 1
    admin_user: admin
    admin_password_secret: ${GW_NAME}-admin-password
    secret_key_secret: ${GW_NAME}-secret-key
    postgres_configuration_secret: ${GW_NAME}-pg
    # Unique DB per gateway instance so SECRET_KEY rotations do not collide
    database_name: gateway_${GW_NAME//-/_}
    ui_mode: baked
    redis_image: mirror.gcr.io/library/redis
    redis_image_version: "7.4"
    redis_managed: ${REDIS_MANAGED}
    redis_url: "${REDIS_URL_VAR}"
    redis_configuration_secret: "${REDIS_SECRET_VAR}"
    envoy_enabled: true
    envoy_image: mirror.gcr.io/envoyproxy/envoy
    envoy_image_version: v1.36.6
    ingress_type: ${INGRESS_TYPE}
    ingress_class_name: nginx
    ingress_hosts:
      - hostname: ${INGRESS_HOST}
    front_end_url: ${FRONT_END}
    service_type: ClusterIP
    resource_requirements: {}
    set_self_labels: true
    csrf_trusted_origins:
      - https://localhost
      - https://localhost:8443
      - https://${INGRESS_HOST}
    run_register_job: true
    controller_service: "${CTRL_SVC}"
    controller_service_port: "8052"
    controller_service_https: false
  roles:
    - role: gateway
EOF

ANSIBLE_ROLES_PATH="$ROOT/roles" \
ANSIBLE_CONFIG="$ROOT/ansible-kind.cfg" \
  "$APB" -i localhost, "$PLAY" -v

echo ">> Gateway reconcile finished"
kubectl -n "$NS" get deploy,svc -l app.kubernetes.io/managed-by=awx-operator
echo ">> Jewel container image on ${GW_NAME}:"
kubectl -n "$NS" get deploy "$GW_NAME" -o jsonpath='{.spec.template.spec.containers[?(@.name=="jewel")].image}{"\n"}' 2>/dev/null || true
