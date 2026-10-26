# Operator + chart releases

## Cadence

| Track | When | What ships |
|-------|------|------------|
| Operator / chart | On demand, from commits on `main` | `awx-platform-operator` image and Helm chart |
| Component images | Independent trains in **awx-platform-images** | `platform-ui-v*`, `jewel-with-ui-v*`, optional `awx-v*` |

The operator pins each component on its own (`release/pins.consumer.yaml`). Bump only the image that moved.

## Tag scheme

New releases are calendar versions. `YYYY.MM.DD` is the UTC date of the cut. A second cut that day is `YYYY.MM.DD-1`.

| Artifact | Calver | Last semver |
|----------|--------|-------------|
| Git tag | `v2026.10.26` | `v0.1.13` |
| Operator image | `ghcr.io/flippyboy/awx/awx-platform-operator:2026.10.26` | `:0.1.13` |
| Helm OCI | `oci://ghcr.io/flippyboy/awx/awx-platform-operator-helm` version `2026.10.26` | `0.1.13` |

The chart package name is `Chart.yaml` `name: awx-platform-operator-helm`, so the Helm push does not share the operator image package. Image tags and chart versions omit the leading `v`. `v0.1.13` stays the last semver release. Do not add `0.1.14`.

Component images from the images repo use the same calendar scheme (`platform-ui-v2026.10.26`, image tag `2026.10.26`). Pins already published as `0.1.x` stay as they are until that component is cut again.

`release/calver.py` picks the next version. `.github/workflows/release.yml` builds a `v*` tag, still accepts a legacy `v0.1.x` tag, and writes the version without `v` into the image tag and the chart.

## Grok

Same connection as **awx-platform-images**. Grok watches this repository and wakes up on a pull request. Grok reads the diff, comments, and can open the release pull request. GitHub Actions do not install or call Grok.

Dependabot and other pull requests are the trigger. Review instructions are `release/AGENTS.md`. A release stays a pull request on `release/calver-<version>` until you ask for the tag. Pushing `vYYYY.MM.DD` starts `release.yml`, which builds the image, pushes the Helm chart, and opens the GitHub Release from `release/notes/v<version>.md`.

## Manual checklist

- [ ] `python3 hack/scripts/check-dependabot-coverage.py`
- [ ] `helm lint charts/awx-platform-operator`
- [ ] Kind smoke green against the target component images
- [ ] CRDs synced: `./hack/scripts/helm-sync-crds.sh`
- [ ] Release notes list operator and chart changes and the component pin table
