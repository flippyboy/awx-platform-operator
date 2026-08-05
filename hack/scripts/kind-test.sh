#!/usr/bin/env bash
# Smoke tests against kind cluster (CRDs + jewel gateway + trust artifacts).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
NS=awx-platform
GW_NAME="${GATEWAY_NAME:-demo-gateway}"
PASS=0
FAIL=0

check() {
  local name="$1"
  shift
  if "$@"; then
    echo "  PASS  $name"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $name"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Kind AWX Platform smoke tests ==="

check "namespace exists" kubectl get ns "$NS"
check "AWX CRD" kubectl get crd awxs.awx.ansible.com
check "AWXGateway CRD" kubectl get crd awxgateways.awx.ansible.com
check "AWXPlatform CRD" kubectl get crd awxplatforms.awx.ansible.com
check "AWXPlatform sample" kubectl -n "$NS" get awxplatform demo
check "AWXGateway sample" kubectl -n "$NS" get awxgateway "$GW_NAME"
check "postgres ready" bash -c "kubectl -n $NS get deploy postgres -o jsonpath='{.status.readyReplicas}' | grep -q 1"
check "redis-jewel ready" bash -c "kubectl -n $NS get deploy redis-jewel -o jsonpath='{.status.readyReplicas}' | grep -q 1"
check "jewel ready" bash -c "kubectl -n $NS get deploy jewel -o jsonpath='{.status.readyReplicas}' | grep -q 1"
# Operator-managed gateway (after ./scripts/kind-reconcile-gateway.sh)
if kubectl -n "$NS" get deploy "$GW_NAME" >/dev/null 2>&1; then
  check "operator ${GW_NAME} ready" bash -c "kubectl -n $NS get deploy $GW_NAME -o jsonpath='{.status.readyReplicas}' | grep -q 1"
  check "operator ${GW_NAME}-redis ready" bash -c "kubectl -n $NS get deploy ${GW_NAME}-redis -o jsonpath='{.status.readyReplicas}' | grep -q 1"
  check "operator ${GW_NAME}-envoy ready" bash -c "kubectl -n $NS get deploy ${GW_NAME}-envoy -o jsonpath='{.status.readyReplicas}' | grep -q 1"
  check "register job complete or absent" bash -c \
    "j=\$(kubectl -n $NS get job ${GW_NAME}-register -o jsonpath='{.status.succeeded}' 2>/dev/null || echo skip); [ \"\$j\" = skip ] || [ \"\$j\" = 1 ]"
  # Default JEWEL_IMAGE is local UI build; fail if still on public API-only unless overridden
  EXPECTED_JEWEL="${JEWEL_IMAGE:-awx-compose/jewel:local}"
  ACTUAL_JEWEL=$(kubectl -n "$NS" get deploy "$GW_NAME" -o jsonpath='{.spec.template.spec.containers[?(@.name=="jewel")].image}' 2>/dev/null || true)
  if [ -n "$ACTUAL_JEWEL" ]; then
    if [ "$ACTUAL_JEWEL" = "$EXPECTED_JEWEL" ]; then
      echo "  PASS  operator gateway uses JEWEL_IMAGE ($ACTUAL_JEWEL)"
      PASS=$((PASS + 1))
    elif [ "${ALLOW_PUBLIC_JEWEL:-false}" = "true" ]; then
      echo "  SKIP  gateway image is $ACTUAL_JEWEL (ALLOW_PUBLIC_JEWEL=true; expected $EXPECTED_JEWEL)"
    else
      echo "  FAIL  operator gateway image is $ACTUAL_JEWEL (expected $EXPECTED_JEWEL)"
      echo "        Rebuild/load local UI image: make build-jewel && ./scripts/kind-reconcile-gateway.sh"
      FAIL=$((FAIL + 1))
    fi
  fi
fi

# Smoke jewel (platform-smoke) should also use local image when present
if kubectl -n "$NS" get deploy jewel >/dev/null 2>&1; then
  SMOKE_JEWEL=$(kubectl -n "$NS" get deploy jewel -o jsonpath='{.spec.template.spec.containers[?(@.name=="jewel")].image}' 2>/dev/null || true)
  EXPECTED_JEWEL="${JEWEL_IMAGE:-awx-compose/jewel:local}"
  if [ -n "$SMOKE_JEWEL" ] && [ "$SMOKE_JEWEL" = "$EXPECTED_JEWEL" ]; then
    echo "  PASS  smoke jewel uses JEWEL_IMAGE ($SMOKE_JEWEL)"
    PASS=$((PASS + 1))
  elif [ -n "$SMOKE_JEWEL" ] && [ "${ALLOW_PUBLIC_JEWEL:-false}" != "true" ] && [[ "$SMOKE_JEWEL" == ghcr.io/ansible/jewel* ]]; then
    echo "  FAIL  smoke jewel still on public image: $SMOKE_JEWEL"
    FAIL=$((FAIL + 1))
  fi
fi

# Trust artifacts (after reconcile with generate secret, or kind-trust.sh)
if kubectl -n "$NS" get secret "${GW_NAME}-controller-service-secret" >/dev/null 2>&1; then
  check "controller service secret exists" true
  check "controller service secret is not error text" bash -c "
    s=\$(kubectl -n $NS get secret ${GW_NAME}-controller-service-secret -o jsonpath='{.data.secret}' | base64 -d)
    [ \${#s} -ge 20 ] && ! printf '%s' \"\$s\" | grep -qiE 'failed|error|usage:|invalid choice'
  "
else
  echo "  SKIP  controller service secret (run kind-reconcile-gateway.sh or kind-trust.sh)"
fi

echo ">> Probing Jewel /api/ via port-forward..."
kubectl -n "$NS" port-forward "svc/${GW_NAME}" 18000:8000 >/tmp/kind-pf-jewel.log 2>&1 &
PF=$!
# Prefer operator-managed gateway if present; fall back to smoke jewel
if ! kubectl -n "$NS" get svc "$GW_NAME" >/dev/null 2>&1; then
  kill "$PF" 2>/dev/null || true
  kubectl -n "$NS" port-forward svc/jewel 18000:8000 >/tmp/kind-pf-jewel.log 2>&1 &
  PF=$!
fi
cleanup() { kill "$PF" 2>/dev/null || true; }
trap cleanup EXIT
sleep 3

if curl -sk --connect-timeout 5 "https://127.0.0.1:18000/api/" | grep -q gateway; then
  echo "  PASS  jewel /api/ returns gateway index"
  PASS=$((PASS + 1))
else
  echo "  FAIL  jewel /api/"
  curl -sk "https://127.0.0.1:18000/api/" || true
  cat /tmp/kind-pf-jewel.log || true
  FAIL=$((FAIL + 1))
fi

if curl -sk --connect-timeout 5 "https://127.0.0.1:18000/api/gateway/v1/jwt_key/" | grep -q "BEGIN PUBLIC KEY"; then
  echo "  PASS  jwt_key PEM available"
  PASS=$((PASS + 1))
else
  echo "  FAIL  jwt_key"
  FAIL=$((FAIL + 1))
fi

# Authenticated checks when admin secret present
if kubectl -n "$NS" get secret "${GW_NAME}-admin-password" >/dev/null 2>&1; then
  ADMIN_USER=$(kubectl -n "$NS" get secret "${GW_NAME}-admin-password" -o jsonpath='{.data.username}' 2>/dev/null | base64 -d || echo admin)
  ADMIN_PASS=$(kubectl -n "$NS" get secret "${GW_NAME}-admin-password" -o jsonpath='{.data.password}' | base64 -d)
  AUTH=$(printf '%s:%s' "$ADMIN_USER" "$ADMIN_PASS" | base64 -w0 2>/dev/null || printf '%s:%s' "$ADMIN_USER" "$ADMIN_PASS" | base64)
  SVCS=$(curl -sk -H "Authorization: Basic $AUTH" "https://127.0.0.1:18000/api/gateway/v1/services/")
  if echo "$SVCS" | grep -q '"api_slug":"controller"\|"api_slug": "controller"'; then
    echo "  PASS  controller service registered (api_slug)"
    PASS=$((PASS + 1))
  else
    # JSON may compact differently
    if echo "$SVCS" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert any(r.get("api_slug")=="controller" for r in d.get("results",[]))' 2>/dev/null; then
      echo "  PASS  controller service registered (api_slug)"
      PASS=$((PASS + 1))
    else
      echo "  FAIL  controller service not registered"
      echo "    $SVCS" | head -c 400
      echo
      FAIL=$((FAIL + 1))
    fi
  fi
  if echo "$SVCS" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert any(r.get("api_slug")=="gateway" for r in d.get("results",[]))' 2>/dev/null; then
    echo "  PASS  gateway service registered (api_slug)"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  gateway service not registered"
    FAIL=$((FAIL + 1))
  fi
fi

if python3 - <<'PY'
from pathlib import Path
p = Path("roles/installer/templates/configmaps/config.yaml.j2")
t = p.read_text()
assert "ANSIBLE_BASE_JWT_KEY" in t
assert "open_source_defaults" in t
assert "RESOURCE_SERVER" in t
PY
then
  echo "  PASS  Phase1 settings jinja snippet sanity"
  PASS=$((PASS + 1))
else
  echo "  FAIL  Phase1 settings"
  FAIL=$((FAIL + 1))
fi

if python3 - <<'PY'
from pathlib import Path
t = Path("roles/gateway/tasks/main.yml").read_text()
assert "controller-service-secret" in t
assert "generate_key" in t or "generate_controller_service_secret" in t
assert "ServiceAPIRoute" in t or "controller-service-secret" in t
PY
then
  echo "  PASS  gateway role trust tasks present"
  PASS=$((PASS + 1))
else
  echo "  FAIL  gateway role trust tasks"
  FAIL=$((FAIL + 1))
fi

# Controller: prefer AWX CR installer (demo-controller-web); fallback smoke controller-web
if kubectl -n "$NS" get deploy demo-controller-web >/dev/null 2>&1; then
  check "AWX CR demo-controller-web ready" bash -c "kubectl -n $NS get deploy demo-controller-web -o jsonpath='{.status.readyReplicas}' | grep -q 1"
  check "AWX CR exists" kubectl -n "$NS" get awx demo-controller
elif kubectl -n "$NS" get deploy controller-web >/dev/null 2>&1; then
  check "controller-web ready (smoke fallback)" bash -c "kubectl -n $NS get deploy controller-web -o jsonpath='{.status.readyReplicas}' | grep -q 1"
  check "redis-awx ready" bash -c "kubectl -n $NS get deploy redis-awx -o jsonpath='{.status.readyReplicas}' | grep -q 1"
fi

if kubectl -n "$NS" get deploy demo-controller-web >/dev/null 2>&1 || kubectl -n "$NS" get deploy controller-web >/dev/null 2>&1; then
  # pick exec target for JWT checks
  if kubectl -n "$NS" get deploy demo-controller-web >/dev/null 2>&1; then
    CTRL_DEPLOY=demo-controller-web
    CTRL_C=demo-controller-web
  else
    CTRL_DEPLOY=controller-web
    CTRL_C=controller-web
  fi
  # In-cluster JWT path: Envoy → Controller (config proves JWT; /me/ may 400 on resource-sync lock)
  GW_ADMIN_PASS=$(kubectl -n "$NS" get secret "${GW_NAME}-admin-password" -o jsonpath='{.data.password}' | base64 -d)
  if kubectl -n "$NS" exec "deploy/${CTRL_DEPLOY}" -c "$CTRL_C" -- env "GW_PASS=$GW_ADMIN_PASS" python3 -c '
import ssl, urllib.request, base64, json, os
ctx = ssl._create_unverified_context()
with urllib.request.urlopen("https://demo-gateway-envoy:9080/api/controller/v2/ping/", context=ctx, timeout=20) as r:
    assert r.status == 200
pw = os.environ["GW_PASS"]
auth = base64.b64encode(("admin:" + pw).encode()).decode()
req = urllib.request.Request(
    "https://demo-gateway-envoy:9080/api/controller/v2/config/",
    headers={"Authorization": "Basic " + auth},
)
with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
    d = json.loads(r.read())
    lic = d.get("license_info") or {}
    assert lic.get("compliant") is True or lic.get("license_type") == "open", lic
print("ok")
' >/tmp/kind-jwt-test.out 2>&1; then
    echo "  PASS  envoy→controller JWT path (ping + config)"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  envoy→controller JWT path"
    cat /tmp/kind-jwt-test.out | tail -20 || true
    FAIL=$((FAIL + 1))
  fi
else
  echo "  SKIP  controller (run ./scripts/kind-reconcile-controller.sh)"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
