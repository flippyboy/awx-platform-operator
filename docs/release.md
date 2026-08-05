# Operator + chart releases

## Cadence (suggested)

| Track | Frequency | What ships |
|-------|-----------|------------|
| Operator / chart | ~biweekly or on demand | `awx-platform-operator` image + Helm chart |
| Component images | Independent trains in **images repo** | `platform-ui-v*`, `jewel-with-ui-v*`, optional `awx-v*` |

Operator releases **pin** each component image digest/tag independently (only bump images that moved; see `release/pins.consumer.yaml`).

## Tag scheme / GHCR paths

- Operator git tag: `v0.1.0`
- Operator image: `ghcr.io/flippyboy/awx/awx-platform-operator:0.1.0`
- Helm OCI package (separate from the image): `oci://ghcr.io/flippyboy/awx/awx-platform-operator-helm` (chart version `0.1.0`)
- Component images (images repo): `ghcr.io/flippyboy/awx/{platform-ui,jewel-with-ui}:…`

Chart package name comes from `Chart.yaml` `name: awx-platform-operator-helm` so Helm OCI push does not share the operator image package.

## Agent-assisted release (recommended flow)

1. In **awx-platform-images**, run the release agent to refresh `pins.yaml` and produce notes (see that repo’s `release/AGENTS.md`).
2. Publish image tags/digests.
3. In **this** repo, open a PR:
   - Bump chart `values.yaml` / examples default image refs
   - Bump `Chart.yaml` `version` / `appVersion`
   - Attach release notes (`release/notes/v0.1.0.md`)
4. Merge + tag `v0.1.0` → GitHub Actions builds the operator image **and** pushes the Helm chart as its own package.

## Manual checklist

- [ ] `helm lint charts/awx-platform-operator`
- [ ] Kind smoke green against target component images
- [ ] CRDs synced: `./hack/scripts/helm-sync-crds.sh`
- [ ] Release notes list operator/chart changes **and** component pin table
