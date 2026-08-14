#!/usr/bin/env bash
# Install cert-manager into the current kube-context (used by kind-up / gateway TLS).
set -euo pipefail
CM_VERSION="${CERT_MANAGER_VERSION:-v1.16.2}"
NS=cert-manager

if kubectl get ns "$NS" >/dev/null 2>&1 && kubectl -n "$NS" get deploy cert-manager >/dev/null 2>&1; then
  echo ">> cert-manager already present in $NS"
else
  echo ">> Installing cert-manager ${CM_VERSION}"
  kubectl apply -f "https://github.com/cert-manager/cert-manager/releases/download/${CM_VERSION}/cert-manager.yaml"
fi

echo ">> Waiting for cert-manager webhook..."
kubectl -n "$NS" wait --for=condition=Available deploy/cert-manager --timeout=180s
kubectl -n "$NS" wait --for=condition=Available deploy/cert-manager-webhook --timeout=180s
kubectl -n "$NS" wait --for=condition=Available deploy/cert-manager-cainjector --timeout=180s
echo ">> cert-manager ready"
