# awx-platform-operator Helm chart

Fork of [ansible-community/awx-operator-helm](https://github.com/ansible-community/awx-operator-helm)
for this monorepo’s **platform** operator (Controller + Jewel + Envoy).

| Upstream | This fork |
|----------|-----------|
| CRDs: AWX, Backup, Restore, MeshIngress | + **AWXGateway**, **AWXPlatform** (from `operator/awx-operator`) |
| Optional `AWX` instance | + optional **AWXGateway** / **AWXPlatform** |
| AWX external Postgres only | + **shared** `externalPostgres` / `externalRedis` |
| `quay.io/ansible/awx-operator` | Default `awx-compose/awx-operator:local` |

## Install

```bash
# From monorepo root
helm dependency update charts/awx-platform-operator 2>/dev/null || true
helm upgrade --install awx-platform charts/awx-platform-operator \
  -n awx-platform --create-namespace \
  -f charts/awx-platform-operator/examples/platform-kind.yaml
```

Lint / template:

```bash
helm lint charts/awx-platform-operator
helm template awx-platform charts/awx-platform-operator \
  -f charts/awx-platform-operator/examples/platform-kind.yaml
```

## Values overview

| Key | Purpose |
|-----|---------|
| `operator.image` / `operator.tag` | Operator controller image |
| `externalPostgres` | Create unmanaged Postgres secret for children |
| `externalRedis` | Create Redis secret for Jewel (optional) |
| `AWX.enabled` | Deploy classic/consumer `AWX` CR |
| `AWXGateway.enabled` | Deploy `AWXGateway` CR (Jewel + Envoy) |
| `AWXPlatform.enabled` | Deploy umbrella `AWXPlatform` CR |
| `AWXGateway.spec.create_certificate` | cert-manager Certificate for shared Jewel+Envoy TLS (default **true**) |
| `AWXGateway.spec.tls_secret` | Override TLS Secret name (default `{name}-tls`) |
| `certManager.createIssuer` | Optional Helm-managed Issuer (usually the operator creates it) |

**cert-manager** is required when `create_certificate: true` (default). Install first:

```bash
./hack/scripts/kind-install-cert-manager.sh
# or: kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
```

Gateway API `BackendTLSPolicy` example: [`examples/backend-tls-policy.yaml`](./examples/backend-tls-policy.yaml).

See `values.yaml` for full schema.

## Platform example (external Postgres)

```yaml
operator:
  image: awx-compose/awx-operator
  tag: local

externalPostgres:
  enabled: true
  host: postgres
  port: 5432
  dbName: awx
  username: awx
  password: awx
  type: unmanaged

AWXPlatform:
  enabled: true
  name: demo
  spec:
    controller:
      create: true
      name: demo-controller
    gateway:
      create: true
      name: demo-gateway
      image: awx-compose/jewel
      image_version: local
      ui_mode: baked
    ingress:
      type: none
    open_source_defaults: true
```

## Relationship to kind scripts

Until an operator image is built that embeds the gateway/platform roles:

| Concern | Helm chart | Kind scripts |
|---------|------------|--------------|
| CRDs | Yes | `kind-up` / kustomize |
| Operator pod | Yes (needs image) | ansible-playbook reconcile |
| Gateway + trust | Via CR + operator | `kind-reconcile-gateway.sh` |
| Controller | Via AWX CR | `kind-reconcile-controller.sh` |

You can install **CRDs + CRs + secrets** from Helm while still reconciling with the monorepo scripts.

## Sync CRDs from operator tree

```bash
# From monorepo root
for f in operator/awx-operator/config/crd/bases/*.yaml; do
  plural=$(basename "$f" | sed 's/awx\.ansible\.com_//;s/\.yaml$//')
  cp "$f" "charts/awx-platform-operator/crds/customresourcedefinition-${plural}.awx.ansible.com.yaml"
done
```

## Upstream provenance

- Base: ansible-community/awx-operator-helm (chart layout, operator Deployment, secrets helpers)
- CRDs / watches: `operator/awx-operator` (this monorepo)
