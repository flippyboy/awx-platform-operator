# Operator + chart releases

## Cadence

| Track | When | What ships |
|-------|------|------------|
| Operator / chart | After an images-repo publish, and on demand for operator code | `awx-platform-operator` image and Helm chart |
| Component images | Independent trains in **awx-platform-images** | `platform-ui-v*`, `jewel-with-ui-v*`, optional `awx-v*` |

The operator pins each component on its own (`release/pins.consumer.yaml`). An image publish in **awx-platform-images** dispatches `images-released`. `consume-image-release.yml` bumps only that image, commits the pin, and pushes `vYYYY.MM.DD`. That tag starts `release.yml`. Dependabot and operator-code pull requests do not choose component image tags.

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

Dependabot and operator-code pull requests are the trigger for changes in this repo. Review instructions are `release/AGENTS.md`. A release of those changes stays a pull request on `release/calver-<version>` until you ask for the tag.

A component image release is the other trigger. `awx-platform-images` dispatches `images-released` after the image push. This repo then tags `vYYYY.MM.DD` without a review pull request, because the image tag and digest are already published. Pushing that tag starts `release.yml`, which builds the operator image, pushes the Helm chart, and opens the GitHub Release from `release/notes/v<version>.md`.

The controller image is not built here. `.github/workflows/propose-awx-pin.yml` runs weekly and on demand. It resolves `devel` on `ansible/awx` and the digest of `ghcr.io/ansible/awx:devel`, then opens a pull request. The pull request writes that digest into controller `image_version` and lists the upstream commits in `release/notes/PROPOSED-awx.md`. Merging it does not tag a release. The next operator release copies that commit list into `release/notes/v<version>.md`. The installer pulls `image@digest` when `image_version` is a `sha256` digest, and `image:tag` otherwise. Do not pin an upstream semver tag. See `docs/awx-image.md` in awx-platform-images.

## Manual checklist

- [ ] `python3 hack/scripts/check-dependabot-coverage.py`
- [ ] `helm lint charts/awx-platform-operator`
- [ ] Kind smoke green against the target component images
- [ ] CRDs synced: `./hack/scripts/helm-sync-crds.sh`
- [ ] Release notes list operator and chart changes, the component pin table, and the upstream AWX commits from `release/notes/PROPOSED-awx.md`
