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

## GHCR packages

All packages live under the `flippyboy/awx` namespace (not the repo root):

| Package | Path |
|---------|------|
| Operator image | `ghcr.io/flippyboy/awx/awx-platform-operator` |
| Helm chart (OCI) | `oci://ghcr.io/flippyboy/awx/awx-platform-operator-helm` |
| Jewel + UI | `ghcr.io/flippyboy/awx/jewel-with-ui` |
| Platform UI | `ghcr.io/flippyboy/awx/platform-ui` |

The Helm chart is a **separate** GHCR package from the operator container image (`Chart.yaml` `name: awx-platform-operator-helm`).

**Gateway TLS** defaults to **cert-manager** (shared Secret for Jewel + Envoy + CA ConfigMap for Gateway API `BackendTLSPolicy`). Install cert-manager before enabling gateway with `create_certificate: true` (default).

## Quick start (cluster with operator image)

Releases through `0.1.13` are semver. Later releases are calendar versions: git tag `v2026.10.26`, image and chart version `2026.10.26`. A second cut the same UTC day is `2026.10.26-1`.

```bash
# From OCI (after a release tag)
helm upgrade --install awx-platform oci://ghcr.io/flippyboy/awx/awx-platform-operator-helm \
  --version 0.1.13 -n awx-platform --create-namespace \
  -f charts/awx-platform-operator/examples/platform-kind.yaml

# Or from a local chart checkout
helm upgrade --install awx-platform charts/awx-platform-operator \
  -n awx-platform --create-namespace \
  -f charts/awx-platform-operator/examples/platform-kind.yaml
```

## Kind without operator image (playbook reconcile)

```bash
# Requires: kind, kubectl, docker images from awx-platform-images (or local compose builds)
export JEWEL_IMAGE=ghcr.io/flippyboy/awx/jewel-with-ui:latest   # or awx-compose/jewel:local
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
| Jewel / UI images | consumed from `images-released` | builds & pushes |
| Upstream AWX pin | `propose-awx-pin` records the devel commit and digest | records the same upstream for its own builds; does not choose the cluster pull |
| Compose stack | — | ✅ testing |

Jewel and platform-ui tags in the chart match the images repo. The controller pull is `ghcr.io/ansible/awx` at the digest `propose-awx-pin` records. `devel` is the branch label, not the tag a cluster pulls.

## Development

```bash
make help
./hack/scripts/helm-sync-crds.sh   # CRDs → charts/.../crds
helm lint charts/awx-platform-operator
```

## License

See `LICENSE` / `COPYING` (upstream operator licensing).
