# Operator + chart releases

## Cadence (suggested)

| Track | Frequency | What ships |
|-------|-----------|------------|
| Operator / chart | ~biweekly or on demand | `awx-operator` image + Helm chart |
| Component images | Steady cadence via **images repo** | jewel-with-ui, platform-ui, optional awx |

Operator releases **pin** component image digests/tags from the latest images-repo release (or known-good pins).

## Tag scheme

- Operator git tag: `v0.1.0`
- Image: `ghcr.io/<org>/awx-operator:v0.1.0`
- Chart version: `0.1.0` (aligned with operator semver without `v`)

## Agent-assisted release (recommended flow)

1. In **awx-platform-images**, run the release agent to refresh `pins.yaml` and produce notes (see that repo’s `release/AGENTS.md`).
2. Publish image tags/digests.
3. In **this** repo, open a PR:
   - Bump chart `values.yaml` / examples default image refs
   - Bump `Chart.yaml` `version` / `appVersion`
   - Attach release notes (`release/notes/v0.1.0.md`)
4. Merge + tag `v0.1.0` → GitHub Actions builds operator image + packages chart.

## Manual checklist

- [ ] `helm lint charts/awx-platform-operator`
- [ ] Kind smoke green against target component images
- [ ] CRDs synced: `./hack/scripts/helm-sync-crds.sh`
- [ ] Release notes list operator/chart changes **and** component pin table
