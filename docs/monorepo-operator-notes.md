# Operator worktree (Option B)

This directory holds a **working clone** of [ansible/awx-operator](https://github.com/ansible/awx-operator)
with community patches for the modern platform architecture.

See [docs/OPERATOR.md](../docs/OPERATOR.md) for findings and decisions.

## What landed so far

| Phase | Status | Changes |
|-------|--------|---------|
| **1** Gateway consumer on `AWX` | **Done** | CRD fields, settings, secret mounts, sample |
| **2** `AWXGateway` deploy | **Done** | Jewel + managed/external Redis + Envoy; external Postgres |
| **3** Ingress flip | **Partial** | Ingress → Envoy template; `INSTALL_INGRESS=true` on kind |
| **4** UI modes | **Partial** | `baked` via local jewel image; `init_copy` CR field reserved |
| **5** Platform + **AWX CR controller** | **Mostly done** | `kind-reconcile-controller.sh` runs `roles/installer`; platform creates children |
| **6** Hardening | **Partial** | External PG/Redis documented; HA/backup deferred |

### Phase 1 fields on `kind: AWX`

- `gateway_url`
- `gateway_validate_certs`
- `gateway_service_secret_secret` (Secret key `secret`)
- `gateway_jwt_key` (optional override)
- `open_source_defaults` (default true)

Settings emitted into Controller ConfigMap: `ANSIBLE_BASE_JWT_KEY`, `RESOURCE_SERVER` (when secret file present), open-license compliant helper.

## Layout

```text
operator/
  README.md                 ← this file
  awx-operator/             ← git clone (local modifications)
```

## Kind tests

From repo root:

```bash
make build-jewel                         # awx-compose/jewel:local (+ UI)
./scripts/kind-up.sh
./scripts/kind-reconcile-platform.sh     # preferred: PG secrets + gateway + AWX CR
# or:
./scripts/kind-reconcile-gateway.sh
./scripts/kind-reconcile-controller.sh   # AWX CR + installer (not controller-smoke)
./scripts/kind-test.sh
./scripts/kind-down.sh
```

- **Controller:** `kind: AWX` / `roles/installer` with **external** Postgres (`type=unmanaged`).
- **Gateway Redis:** managed by default; set `USE_EXTERNAL_REDIS=true` or `GATEWAY_REDIS_URL`.
- **Jewel image:** `JEWEL_IMAGE=awx-compose/jewel:local` by default.
- **Legacy smoke:** `kind-deploy-controller.sh` still exists but is not the intended path.

## Helm chart

Fork of [awx-operator-helm](https://github.com/ansible-community/awx-operator-helm):

```bash
./scripts/helm-sync-crds.sh
helm upgrade --install awx-platform charts/awx-platform-operator \
  -n awx-platform --create-namespace \
  -f charts/awx-platform-operator/examples/platform-kind.yaml
```

See `charts/awx-platform-operator/README.md`.

Trust Secret for Controller: `demo-gateway-controller-service-secret` (key `secret`).
Set on AWX: `gateway_service_secret_secret` + `gateway_url: https://demo-gateway.awx-platform.svc:8000`.

Image load tip: multi-arch AWX images may fail `kind load docker-image`; the deploy script uses
`ctr images import --no-unpack` on the kind node instead.

## Upstream contribution

Commits here are local until opened as PRs against `ansible/awx-operator`. Prefer small Phase 1 PR first.
