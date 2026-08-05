# awx-platform-operator

Platform operator for modern AWX (Controller + Jewel gateway + Envoy).

This repository is the **product surface**:

- Operator roles (including `gateway` / `platform`) and CRDs (`AWX`, `AWXGateway`, `AWXPlatform`, …)
- Helm chart (`charts/awx-platform-operator`)
- Kind smoke harness (`hack/kind`, `hack/scripts`)
- Release tooling and GitHub Actions

**Does not** vendor application sources for AWX, Jewel, or ansible-ui.  
Component images are built from upstream pins by [`awx-platform-images`](https://github.com/flippyboy/awx-platform-images) (sibling repo).

Derived from [ansible/awx-operator](https://github.com/ansible/awx-operator) (see `NOTICE` / `docs/upstream.md`).

## Quick start (cluster with operator image)

```bash
# After building/pushing the operator image
helm upgrade --install awx-platform charts/awx-platform-operator \
  -n awx-platform --create-namespace \
  -f charts/awx-platform-operator/examples/platform-kind.yaml
```

## Kind without operator image (playbook reconcile)

```bash
# Requires: kind, kubectl, docker images from awx-platform-images (or local compose builds)
export JEWEL_IMAGE=ghcr.io/flippyboy/jewel-with-ui:latest   # or awx-compose/jewel:local
./hack/scripts/kind-up.sh
./hack/scripts/kind-reconcile-gateway.sh
./hack/scripts/kind-reconcile-controller.sh
./hack/scripts/kind-test.sh
```

## Layout

```text
config/           CRDs, RBAC, manager manifests
roles/            installer, gateway, platform, backup, …
playbooks/        operator + standalone reconcile playbooks
charts/           awx-platform-operator Helm chart
hack/kind/        kind cluster kustomize
hack/scripts/     kind-*.sh, helm-sync-crds.sh
docs/             architecture, release process
.github/workflows CI + release
release/          pins consumers, note templates (see also images repo)
```

## Relationship to awx-platform-images

| Concern | This repo | awx-platform-images |
|---------|-----------|---------------------|
| Operator / Helm | ✅ | — |
| Jewel / UI / AWX images | consumes tags/digests | builds & pushes |
| Compose stack | — | ✅ testing |
| Upstream git pins | documents operator-tested pins | owns pin file + agent release |

Default image tags in the Helm chart should match **released** pins from the images repo.

## Development

```bash
make help
./hack/scripts/helm-sync-crds.sh   # CRDs → charts/.../crds
helm lint charts/awx-platform-operator
```

## License

See `LICENSE` / `COPYING` (upstream operator licensing).
