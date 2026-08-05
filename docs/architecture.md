# AWX Operator — findings, decisions, and Option B plan

This document records research and **decisions** for evolving
[ansible/awx-operator](https://github.com/ansible/awx-operator) to support the
modern platform architecture (Controller + Jewel + Platform UI + Envoy).

Implementation work lives under `operator/` (fork/worktree of awx-operator) and
`deploy/kind/` (kind smoke tests). Compose remains the behavioral oracle.

---

## Decisions

| ID | Decision | Rationale |
|----|----------|-----------|
| D1 | **Option B**: Platform CR in awx-operator | One community install path; keep classic `AWX` working |
| D2 | New CRs: **`AWXGateway`** + **`AWXPlatform`**; keep **`AWX`** | Clear lifecycles; opt-in platform |
| D3 | Default `AWX` behavior **unchanged** | No breaking existing users |
| D4 | Phase 1 first: Controller as gateway **consumer** | Smallest upstream-friendly PR |
| D5 | Envoy is the external entry when platform mode is on | Matches AAP / our compose |
| D6 | Hub/EDA out of scope for v1 | Register controller only; same pattern later |
| D7 | UI image is external/build-time (not npm in-cluster) | Operator deploys images only |
| D8 | AAP operator will not be forked | Source unavailable |
| D9 | This monorepo holds compose oracle + operator worktree + kind tests | Faster iteration than PR-only |
| D10 | Kind is the CI/dev target before OCP-specific Route features | |
| D11 | **External Postgres is first-class** for platform mode | Matches production; kind uses shared `postgres` Service |
| D12 | **External Redis optional** for gateway | `redis_configuration_secret` / `redis_url`; Controller keeps operator redis sidecars |
| D13 | Platform mode: **Controller has no public Ingress** | Edge is Envoy only |

### CR sketch (target)

```yaml
apiVersion: awx.ansible.com/v1beta1
kind: AWXPlatform
metadata:
  name: demo
spec:
  postgres_configuration_secret: platform-pg   # external / unmanaged
  # redis_configuration_secret: platform-redis  # optional external for gateway
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
    type: ingress
    ingress_class_name: nginx
    hosts: [{hostname: awx.localtest.me}]
  open_source_defaults: true
```

Children: `AWX` + `AWXGateway` (+ Envoy). Trust Job/secret establishes JWT.

### Implementation phases

| Phase | Scope | Status |
|-------|--------|--------|
| 0 | Images/docs + kind harness | **Done** |
| 1 | `AWX` gateway_* consumer fields + settings | **Done** |
| 2 | `AWXGateway` Jewel + Redis + DB | **Done** (managed or external Redis) |
| 3 | Envoy + Ingress flip | **Partial** — Envoy + Ingress template; kind optional install |
| 4 | UI modes (`baked` / `init_copy` / `none`) | **Partial** — `baked` default via local image |
| 5 | `AWXPlatform` + trust + **AWX CR controller** | **Mostly done** — platform children + installer reconcile scripts |
| 6 | Backup/HA/hardening + external service docs | **Partial** — external PG/Redis supported; HA deferred |

---

## External Postgres / Redis

### Postgres secret (shared shape for AWX + gateway)

| Key | Required | Notes |
|-----|----------|--------|
| `host` | yes | e.g. `postgres` Service DNS |
| `port` | yes | `5432` |
| `database` | yes | AWX uses this DB name; gateway role can use `database_name` override |
| `username` / `password` | yes | |
| `type` | recommended | `unmanaged` so installer does **not** deploy managed Postgres |
| `sslmode` | optional | default prefer |

Kind: `platform-pg`, `demo-gateway-pg`, `demo-controller-pg` all point at the
platform-smoke `postgres` Deployment (external to the operator-managed lifecycle).

### Redis

| Component | Default | External |
|-----------|---------|----------|
| Gateway | Managed Deployment `{name}-redis` | `redis_url` or `redis_configuration_secret` (`url` or `host`+`port`) |
| Controller (AWX) | Redis **sidecar** in web/task pods | Not replaced; operator pattern unchanged |

---

## Helm chart (fork)

Path: `charts/awx-platform-operator/` (fork of ansible-community/awx-operator-helm).

```bash
# Sync CRDs from operator tree
./scripts/helm-sync-crds.sh
helm lint charts/awx-platform-operator
helm upgrade --install awx-platform charts/awx-platform-operator \
  -n awx-platform --create-namespace \
  -f charts/awx-platform-operator/examples/platform-kind.yaml
```

Deploys operator controller + optional `AWX` / `AWXGateway` / `AWXPlatform` CRs and
external Postgres/Redis secrets. Default operator image: `awx-compose/awx-operator:local`.

Until that image is built with gateway/platform roles, use kind reconcile scripts for
workload lifecycle; the chart still installs CRDs/RBAC/CRs correctly.

See `charts/awx-platform-operator/README.md`.

## Kind workflow (intended)

```text
make build-jewel
./scripts/kind-up.sh
./scripts/kind-reconcile-platform.sh
# or step-by-step:
./scripts/kind-reconcile-gateway.sh     # AWXGateway + trust secret
./scripts/kind-reconcile-controller.sh  # AWX CR + installer role
./scripts/kind-test.sh

# Optional Phase 3 ingress:
INSTALL_INGRESS=true ./scripts/kind-reconcile-platform.sh
USE_EXTERNAL_REDIS=true ./scripts/kind-reconcile-platform.sh
```

**Controller path:** `kind: AWX` + `roles/installer` (not `controller-smoke`).
Smoke manifests remain as a lightweight fallback only.

**Jewel image:** default `JEWEL_IMAGE=awx-compose/jewel:local` (UI baked).

### Phase 3 Ingress notes

- Template: `roles/gateway/templates/ingress/ingress.yaml.j2` → Service `{gateway}-envoy:9080`
- Enable with `ingress_type: ingress` + `ingress_hosts`
- Kind: `INSTALL_INGRESS=true` installs ingress-nginx (upstream kind recipe)
- Controller `ingress_type` stays `none` in platform mode

### Phase 6 (hardening) remaining

- Full HA for Jewel/Envoy/Postgres
- Backup/Restore awareness of gateway DB + secrets
- NetworkPolicies, PodDisruptionBudgets
- Shared TLS Secret jewel↔Envoy (today separate init-generated PEMs)
- Real operator Deployment image (vs ansible-playbook reconcile on host)

---

## Trust artifacts (JWT)

| Artifact | Purpose |
|----------|---------|
| Register Job `{name}-register` | ServiceAPIRoute `api_slug=controller` |
| Secret `{name}-controller-service-secret` | `generate_key` → AWX `gateway_service_secret_secret` |
| AWX `gateway_url` | `ANSIBLE_BASE_JWT_KEY` |

---

## References

- Compose README / DISCOVERIES  
- Jewel `docs/configuring_envoy.md`  
- Upstream awx-operator molecule kind + ingress-nginx  
