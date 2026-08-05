#!/usr/bin/env bash
# Reconcile kind: AWX CR via roles/installer (external Postgres + gateway trust).
# Replaces controller-smoke as the preferred Controller path.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
NS="${GATEWAY_NS:-awx-platform}"
CTRL_NAME="${CONTROLLER_NAME:-demo-controller}"
GW_NAME="${GATEWAY_NAME:-demo-gateway}"
CLUSTER_NAME="${CLUSTER_NAME:-awx-platform}"
AWX_IMAGE="${AWX_IMAGE:-ghcr.io/ansible/awx:devel}"
EE_IMAGE="${EE_IMAGE:-quay.io/ansible/awx-ee:latest}"
REDIS_IMAGE="${REDIS_IMAGE:-mirror.gcr.io/library/redis:7.4}"
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
else
  APB=ansible-playbook
  AG=ansible-galaxy
fi
"$AG" collection install kubernetes.core 2>/dev/null || true

read -r AWX_REPO AWX_TAG <<<"$(kind_image_parts "$AWX_IMAGE")"
read -r REDIS_REPO REDIS_TAG <<<"$(kind_image_parts "$REDIS_IMAGE")"

echo ">> Ensure gateway trust secret exists"
if ! kubectl -n "$NS" get secret "${GW_NAME}-controller-service-secret" >/dev/null 2>&1; then
  echo "!! Missing ${GW_NAME}-controller-service-secret — run ./scripts/kind-reconcile-gateway.sh first"
  exit 1
fi

echo ">> Load images into kind"
for img in "$AWX_IMAGE" "$EE_IMAGE" "$REDIS_IMAGE"; do
  if ! docker image inspect "$img" >/dev/null 2>&1; then
    echo ">> Pulling $img"
    docker pull "$img"
  fi
  kind_load_image "$img" || true
done
# CentOS stream9 used as init projects image by installer defaults
INIT_PROJ="${INIT_PROJECTS_IMAGE:-quay.io/centos/centos:stream9}"
if docker image inspect "$INIT_PROJ" >/dev/null 2>&1 || docker pull "$INIT_PROJ"; then
  kind_load_image "$INIT_PROJ" || true
fi

# External Postgres secret (AWX shape: host/port/database/username/password; type!=managed)
echo ">> Ensure external Postgres secret ${CTRL_NAME}-pg"
kubectl -n "$NS" create secret generic "${CTRL_NAME}-pg" \
  --from-literal=host=postgres \
  --from-literal=port=5432 \
  --from-literal=database=awx \
  --from-literal=username=awx \
  --from-literal=password=awx \
  --from-literal=type=unmanaged \
  --from-literal=sslmode=prefer \
  --dry-run=client -o yaml | kubectl apply -f -

# Shared admin password with gateway if present
if kubectl -n "$NS" get secret "${GW_NAME}-admin-password" >/dev/null 2>&1; then
  ADMIN_SECRET="${GW_NAME}-admin-password"
else
  ADMIN_SECRET="${CTRL_NAME}-admin-password"
  if ! kubectl -n "$NS" get secret "$ADMIN_SECRET" >/dev/null 2>&1; then
    kubectl -n "$NS" create secret generic "$ADMIN_SECRET" \
      --from-literal=password=admin \
      --from-literal=username=admin
  fi
fi

echo ">> Apply AWX CR sample (gateway consumer + external PG)"
kubectl apply -f hack/kind/samples/awx-controller.yaml
kubectl -n "$NS" patch awx "$CTRL_NAME" --type merge -p \
  "{\"spec\":{\"image\":\"${AWX_REPO}\",\"image_version\":\"${AWX_TAG}\",\"postgres_configuration_secret\":\"${CTRL_NAME}-pg\",\"admin_password_secret\":\"${ADMIN_SECRET}\",\"gateway_url\":\"https://${GW_NAME}.${NS}.svc:8000\",\"gateway_service_secret_secret\":\"${GW_NAME}-controller-service-secret\",\"control_plane_ee_image\":\"${EE_IMAGE}\",\"redis_image\":\"${REDIS_REPO}\",\"redis_image_version\":\"${REDIS_TAG}\"}}"

# Installer needs the CR to exist when it labels itself
PLAY="$ROOT/playbooks/reconcile-controller-standalone.yml"
cat > "$PLAY" <<EOF
---
- hosts: localhost
  connection: local
  gather_facts: true
  collections:
    - kubernetes.core
  vars:
    ansible_operator_meta:
      name: ${CTRL_NAME}
      namespace: ${NS}
    api_version: awx.ansible.com/v1beta1
    kind: AWX
    deployment_type: awx
    auto_upgrade: true
    no_log: false
    set_self_labels: true
    update_status: true
    # Images
    image: ${AWX_REPO}
    image_version: ${AWX_TAG}
    image_pull_policy: IfNotPresent
    redis_image: ${REDIS_REPO}
    redis_image_version: ${REDIS_TAG}
    control_plane_ee_image: ${EE_IMAGE}
    ee_images:
      - name: AWX EE
        image: ${EE_IMAGE}
    init_projects_container_image: ${INIT_PROJ}
    # External Postgres
    postgres_configuration_secret: ${CTRL_NAME}-pg
    # Admin
    admin_user: admin
    admin_password_secret: ${ADMIN_SECRET}
    # Platform / gateway
    service_type: ClusterIP
    ingress_type: none
    gateway_url: https://${GW_NAME}.${NS}.svc:8000
    gateway_validate_certs: false
    gateway_service_secret_secret: ${GW_NAME}-controller-service-secret
    open_source_defaults: true
    projects_persistence: false
    create_preload_data: false
    # Kind-friendly resources
    web_resource_requirements:
      requests: {cpu: 50m, memory: 128Mi}
    task_resource_requirements:
      requests: {cpu: 50m, memory: 128Mi}
    ee_resource_requirements:
      requests: {cpu: 20m, memory: 64Mi}
    redis_resource_requirements:
      requests: {cpu: 20m, memory: 32Mi}
    # Cluster type facts (common role expects these)
    is_openshift: false
    is_k8s: true
    additional_labels: []
    gating_version: ""
    idle_deployment: false
  roles:
    - role: installer
EOF

echo ">> Running installer role for AWX ${CTRL_NAME}"
export OPERATOR_VERSION="${OPERATOR_VERSION:-kind-local}"
ANSIBLE_ROLES_PATH="$ROOT/roles" \
ANSIBLE_CONFIG="$ROOT/ansible-kind.cfg" \
  "$APB" -i localhost, "$PLAY" -v || {
  echo "!! installer reconcile failed — check pods/events"
  kubectl -n "$NS" get pods,deploy,job -l "app.kubernetes.io/part-of=${CTRL_NAME}" 2>/dev/null || true
  kubectl -n "$NS" get pods | head -40
  exit 1
}

echo ">> Wait for web deployment"
kubectl -n "$NS" rollout status "deploy/${CTRL_NAME}-web" --timeout=600s || true
kubectl -n "$NS" rollout status "deploy/${CTRL_NAME}-task" --timeout=600s || true

# Point gateway at controller service (installer names service ${name}-service on port 80 → 8052)
CTRL_SVC="${CTRL_NAME}-service"
if kubectl -n "$NS" get svc "$CTRL_SVC" >/dev/null 2>&1; then
  echo ">> Re-trust with CONTROLLER_SVC=$CTRL_SVC:80"
  CONTROLLER_SVC="$CTRL_SVC" CONTROLLER_PORT=80 CONTROLLER_HTTPS=false \
    ./scripts/kind-trust.sh || true
fi
# Ensure migrations finished if installer exited early after deploy
if kubectl -n "$NS" get deploy "${CTRL_NAME}-web" >/dev/null 2>&1; then
  WEB_C=$(kubectl -n "$NS" get deploy "${CTRL_NAME}-web" -o jsonpath='{.spec.template.spec.containers[*].name}' | tr ' ' '\n' | grep -E 'web$' | head -1)
  kubectl -n "$NS" exec "deploy/${CTRL_NAME}-web" -c "${WEB_C}" -- awx-manage migrate --noinput 2>/dev/null || true
fi

echo ">> Controller reconcile finished"
kubectl -n "$NS" get awx,deploy,svc -l "app.kubernetes.io/name=${CTRL_NAME}-web" 2>/dev/null || \
  kubectl -n "$NS" get awx,deploy,svc | grep -E "NAME|${CTRL_NAME}" || true
