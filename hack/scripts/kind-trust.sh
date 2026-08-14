#!/usr/bin/env bash
# Establish Jewel↔Controller trust on kind (compose `make trust` equivalent).
#
# Prerequisites:
#   - Gateway Ready (demo-gateway from kind-reconcile-gateway.sh)
#   - Optional: Controller Service DNS (CONTROLLER_SVC) for real routing
#
# Always registers the controller ServiceAPIRoute (needed for
# generate_service_secret) and creates Secret
# ${GW_NAME}-controller-service-secret (key: secret) for AWX
# gateway_service_secret_secret field.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
NS="${GATEWAY_NS:-awx-platform}"
GW_NAME="${GATEWAY_NAME:-demo-gateway}"
CTRL_SVC="${CONTROLLER_SVC:-}"   # e.g. awx-demo-service or empty
CTRL_PORT="${CONTROLLER_PORT:-80}"  # Service port (→ targetPort 8052)
CTRL_HTTPS="${CONTROLLER_HTTPS:-false}"
FORCE_ROTATE="${FORCE_ROTATE:-false}"

echo ">> Trust bootstrap for gateway=$GW_NAME ns=$NS"

# Wait for jewel pod
kubectl -n "$NS" wait --for=condition=available "deploy/${GW_NAME}" --timeout=300s

POD=$(kubectl -n "$NS" get pods -l "app.kubernetes.io/name=${GW_NAME}" -o jsonpath='{.items[0].metadata.name}')
echo ">> Jewel pod: $POD"

# Admin credentials
ADMIN_USER=$(kubectl -n "$NS" get secret "${GW_NAME}-admin-password" -o jsonpath='{.data.username}' 2>/dev/null | base64 -d || echo admin)
ADMIN_PASS=$(kubectl -n "$NS" get secret "${GW_NAME}-admin-password" -o jsonpath='{.data.password}' | base64 -d)
echo ">> Admin user: $ADMIN_USER"

# Port-forward gateway for host-side REST registration
kubectl -n "$NS" port-forward "svc/${GW_NAME}" 18080:8000 >/tmp/kind-trust-pf.log 2>&1 &
PF=$!
cleanup() { kill "$PF" 2>/dev/null || true; }
trap cleanup EXIT
sleep 2
export JEWEL_URL="https://127.0.0.1:18080"

python3 - <<PY
import base64, json, os, ssl, time, urllib.request, urllib.error

jewel = os.environ.get("JEWEL_URL", "https://127.0.0.1:18080").rstrip("/")
user = """${ADMIN_USER}"""
pw = """${ADMIN_PASS}"""
ctrl_svc = """${CTRL_SVC}"""
ctrl_port = int("""${CTRL_PORT}""")
ctrl_https = """${CTRL_HTTPS}""".lower() in ("1", "true", "yes")
gw = """${GW_NAME}"""

ctx = ssl._create_unverified_context()
auth = base64.b64encode(f"{user}:{pw}".encode()).decode()

def http(method, url, data=None):
    headers = {"Authorization": f"Basic {auth}", "Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
            raw = r.read().decode() or "{}"
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        try:
            return e.code, json.loads(raw) if raw else {}
        except Exception:
            return e.code, raw

def list_results(path):
    code, body = http("GET", f"{jewel}{path}")
    if code != 200:
        print(f"GET {path} -> {code} {body}")
        return []
    if isinstance(body, dict):
        return body.get("results", [])
    return body if isinstance(body, list) else []

def find(path, name):
    for i in list_results(path):
        if i.get("name") == name:
            return i
    return None

def ensure(path, name, payload, update_keys=None):
    """Create if missing; optionally PATCH listed fields when already present."""
    ex = find(path, name)
    if ex:
        if update_keys:
            patch = {k: payload[k] for k in update_keys if k in payload and ex.get(k) != payload[k]}
            if patch:
                code, body = http("PATCH", f"{jewel}{path}{ex['id']}/", patch)
                print(f"  updated {name} id={ex.get('id')} keys={list(patch)} ({code})")
                if code in (200, 201) and isinstance(body, dict):
                    return body
            else:
                print(f"  exists {name} id={ex.get('id')} (no update needed)")
        else:
            print(f"  exists {name} id={ex.get('id')}")
        return ex
    code, body = http("POST", f"{jewel}{path}", payload)
    if code in (200, 201) and isinstance(body, dict) and body.get("id"):
        print(f"  created {name} id={body['id']}")
        return body
    ex = find(path, name)
    if ex:
        print(f"  found after post {name} id={ex.get('id')} ({code})")
        return ex
    print(f"  FAILED {name} HTTP {code}: {body}")
    return None

for _ in range(60):
    code, _ = http("GET", f"{jewel}/api/")
    if code == 200:
        break
    time.sleep(3)
else:
    raise SystemExit("gateway /api/ not ready")

print("--- http_ports ---")
port = ensure("/api/gateway/v1/http_ports/", "API Port", {
    "name": "API Port", "number": 9080, "use_https": True, "is_api_port": True,
})

print("--- service types ---")
for st in ("gateway", "controller"):
    ensure("/api/gateway/v1/service_types/", st, {"name": st})

gw_type = find("/api/gateway/v1/service_types/", "gateway")
ctrl_type = find("/api/gateway/v1/service_types/", "controller")

print("--- clusters ---")
gw_c = ensure("/api/gateway/v1/service_clusters/", "gateway", {
    "name": "gateway", "service_type": gw_type["id"], "health_checks_enabled": True,
})
ctrl_c = ensure("/api/gateway/v1/service_clusters/", "controller", {
    "name": "controller", "service_type": ctrl_type["id"], "health_checks_enabled": True,
})

print("--- nodes ---")
ensure("/api/gateway/v1/service_nodes/", "Gateway Node 1", {
    "name": "Gateway Node 1", "service_cluster": gw_c["id"], "address": gw,
}, update_keys=["address"])
# Always register controller node (placeholder until Controller Service exists)
ensure("/api/gateway/v1/service_nodes/", "Controller Node", {
    "name": "Controller Node",
    "service_cluster": ctrl_c["id"],
    "address": ctrl_svc or "controller-pending",
}, update_keys=["address"])

print("--- services ---")
if port and gw_c:
    ensure("/api/gateway/v1/services/", "Gateway API", {
        "name": "Gateway API",
        "description": "Proxy to the gateway",
        "api_slug": "gateway",
        "http_port": port["id"],
        "service_cluster": gw_c["id"],
        "is_service_https": True,
        "service_path": "/",
        "service_port": 8000,
        "order": 100,
        "enable_gateway_auth": False,
    })
# Controller ServiceAPIRoute is required for generate_service_secret controller
if port and ctrl_c:
    ensure("/api/gateway/v1/services/", "Controller API", {
        "name": "Controller API",
        "description": "Proxy to the Controller",
        "api_slug": "controller",
        "http_port": port["id"],
        "service_cluster": ctrl_c["id"],
        "is_service_https": ctrl_https,
        "service_path": "/api/",
        "service_port": ctrl_port,
        "order": 2,
        "enable_gateway_auth": True,
    }, update_keys=["is_service_https", "service_port", "service_path", "enable_gateway_auth"])

print("registration done")
PY

SECRET_NAME="${GW_NAME}-controller-service-secret"
EXISTING=$(kubectl -n "$NS" get secret "$SECRET_NAME" -o jsonpath='{.data.secret}' 2>/dev/null || true)
if [ -n "$EXISTING" ] && [ "$FORCE_ROTATE" != "true" ]; then
  DECODED=$(printf '%s' "$EXISTING" | base64 -d 2>/dev/null || true)
  # Reject poisoned secrets from earlier broken runs (error text, not real keys)
  if [ "${#DECODED}" -ge 20 ] && ! printf '%s' "$DECODED" | grep -qiE 'failed|error|usage:|invalid choice|traceback'; then
    echo ">> Secret $SECRET_NAME already present (len=${#DECODED}); set FORCE_ROTATE=true to regenerate"
  else
    echo ">> Existing secret looks invalid; regenerating..."
    EXISTING=""
  fi
fi

if [ -z "${EXISTING:-}" ] || [ "$FORCE_ROTATE" = "true" ]; then
  echo ">> generate controller service secret (django API inside jewel pod)"
  # Jewel prints a colorama warning on stdout before any app code; keep only the last non-empty line.
  SECRET=$(kubectl -n "$NS" exec "$POD" -c jewel -- python3 -c '
import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aap_gateway_api.settings")
import django
django.setup()
from aap_gateway_api.models import ServiceAPIRoute
route = ServiceAPIRoute.objects.filter(api_slug="controller").first()
if route is None:
    sys.stderr.write("no ServiceAPIRoute with api_slug=controller — registration failed\n")
    sys.exit(2)
key = route.service_cluster.generate_key()
# Print marker so we can extract cleanly past colorama noise on stdout
print("SECRET_BEGIN")
print(key.secret)
print("SECRET_END")
' 2>/tmp/kind-trust-gen.err | awk '/^SECRET_BEGIN$/{p=1;next} /^SECRET_END$/{p=0} p' | tr -d '\r\n')

  if [ -z "$SECRET" ] || [ "${#SECRET}" -lt 20 ]; then
    echo "!! generate_service_secret failed:"
    cat /tmp/kind-trust-gen.err || true
    exit 1
  fi
  if printf '%s' "$SECRET" | grep -qiE 'failed|error|usage:|invalid choice|colorama|SECRET_'; then
    echo "!! secret output looks like an error message: $SECRET"
    exit 1
  fi

  echo ">> service secret length=${#SECRET}"
  kubectl -n "$NS" create secret generic "$SECRET_NAME" \
    --from-literal=secret="$SECRET" \
    --dry-run=client -o yaml | kubectl apply -f -
fi

# Optional ServiceID link if controller pod exists (smoke or AWX installer)
CTRL_POD=$(kubectl -n "$NS" get pods -l app.kubernetes.io/name=controller-web -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -z "${CTRL_POD:-}" ]; then
  CTRL_POD=$(kubectl -n "$NS" get pods -l 'app.kubernetes.io/name=demo-controller-web' -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
fi
if [ -z "${CTRL_POD:-}" ]; then
  CTRL_POD=$(kubectl -n "$NS" get pods -l 'app.kubernetes.io/component=awx' -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
fi
CTRL_CONTAINER=""
if [ -n "${CTRL_POD:-}" ]; then
  # Prefer the AWX app container (not redis/rsyslog sidecars)
  CTRL_CONTAINER=$(kubectl -n "$NS" get pod "$CTRL_POD" -o jsonpath='{range .spec.containers[*]}{.name}{"\n"}{end}' 2>/dev/null \
    | grep -E 'web$|controller|awx' | head -1 || true)
  if [ -z "${CTRL_CONTAINER}" ]; then
    CTRL_CONTAINER=$(kubectl -n "$NS" get pod "$CTRL_POD" -o jsonpath='{.spec.containers[0].name}' 2>/dev/null || true)
  fi
fi
if [ -n "${CTRL_POD:-}" ]; then
  echo ">> Linking Controller ServiceID from pod $CTRL_POD (container ${CTRL_CONTAINER:-default})"
  SID=$(kubectl -n "$NS" exec "$CTRL_POD" ${CTRL_CONTAINER:+-c "$CTRL_CONTAINER"} -- \
    awx-manage shell -c 'from ansible_base.resource_registry.models.service_identifier import ServiceID; print(ServiceID.objects.first().id)' \
    2>/dev/null | tr -d '\r' | grep -E '^[0-9a-f-]{36}$' | tail -1 || true)
  if [ -n "$SID" ]; then
    echo ">> ServiceID=$SID"
    kubectl -n "$NS" exec "$POD" -c jewel -- python3 -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aap_gateway_api.settings')
django.setup()
from aap_gateway_api.models import ServiceCluster
sc = ServiceCluster.objects.get(name='controller')
sc.service_id = '$SID'
sc.save()
print('linked', sc.service_id)
"
  fi
else
  echo ">> No controller pod; skip ServiceID link"
fi

echo ">> Trust artifacts:"
kubectl -n "$NS" get secret "$SECRET_NAME" -o custom-columns=NAME:.metadata.name,BYTES:.data.secret --no-headers
# Verify not error text
VERIFY=$(kubectl -n "$NS" get secret "$SECRET_NAME" -o jsonpath='{.data.secret}' | base64 -d)
if printf '%s' "$VERIFY" | grep -qiE 'failed|error|usage:'; then
  echo "!! Secret still looks invalid"
  exit 1
fi
echo ">> secret looks valid (len=${#VERIFY})"
echo ">> Done. For AWX CR set: gateway_service_secret_secret: $SECRET_NAME"
echo "   gateway_url: https://${GW_NAME}.${NS}.svc:8000"
