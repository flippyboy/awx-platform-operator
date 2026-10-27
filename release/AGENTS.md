# Agent instructions: operator + chart releases

Companion: **awx-platform-images**. That repo opens a pull request when component pins move. You review it from Grok, through GitHub. This repo works the same way.

GitHub Actions do not start you. Do not add a workflow that installs the Grok CLI or calls the xAI API. A pull request on this repository is the trigger for operator code and Dependabot. You use GitHub (read the diff, comment, open a pull request, push a tag only when asked).

Component image tags are not chosen from those pull requests. After `awx-platform-images` publishes an image, it dispatches `images-released`. `.github/workflows/consume-image-release.yml` pins that tag and digest and pushes `vYYYY.MM.DD`, which starts `release.yml`. Do not also open a pin pull request for that image.

## Versions

New operator releases are calendar versions. `YYYY.MM.DD` is the UTC date of the cut, with zero-padded month and day. A later cut that same day is `YYYY.MM.DD-N`, and N starts at 1.

| Artifact | Example |
|----------|---------|
| Git tag | `v2026.10.26` |
| Operator image | `ghcr.io/flippyboy/awx/awx-platform-operator:2026.10.26` |
| Chart `version` and `appVersion` | `2026.10.26` |
| Notes | `release/notes/v2026.10.26.md` |

`v0.1.13` is the last semver tag. Do not mint another `0.1.x`. Do not move tags that are already published.

`release/calver.py` `next_version` is the rule. The same UTC day increments `-N`. Any older current version, including `0.1.13`, starts that day with no suffix. Image tags, chart `version`, and `appVersion` omit the leading `v`. `.github/workflows/release.yml` builds a pushed `v*` tag, still accepts a legacy `v0.1.x` tag, and drops the `v` before tagging the image and the chart.

## When a pull request opens

Review that pull request and comment on it. Do not merge. Do not tag.

Dependabot only sees GitHub Actions, the pip locks in `docs/`, `molecule/`, and `hack/ci/`, and the container manifests in `/`, `hack/kind/platform-smoke/`, `hack/kind/controller-smoke/`, and `hack/dependabot/images/`. The catalog lists every other pin. If the diff changes a catalog tag or a kind Redis, Envoy, or Postgres tag, name every consumer that is still on the old tag. `hack/scripts/check-dependabot-coverage.py` is the list.

Leave these alone:

- `ghcr.io/ansible/awx:devel` and jewel `latest`. Do not move them onto a stable semver tag.
- `ghcr.io/flippyboy/awx/*` release tags. They move only when this operator, or the images repo, cuts a release.
- `kubernetes.core` `3.2.0`.
- `hack/ci` `ansible-core` `>=2.16,<2.19`.
- Floating tags: `quay.io/ansible/awx-ee:latest`, `quay.io/ansible/awx:latest`, `quay.io/sclorg/postgresql-15-c9s:latest`, `quay.io/ansible/awx-operator:devel`, `awx-compose/jewel:local`.

Ansible Galaxy has no Dependabot ecosystem. A collection with no `version` is a finding. Do not replace the `3.2.0` pin with a newer Galaxy release.

## When the changes should ship

Cut a release only from commits already on `main`, and only when the user asked or the pull request you are handling is the release itself.

If `git log` since `git describe --tags --abbrev=0 --match 'v*'` is empty, or the only commits are note typos, stop.

Otherwise:

1. Set `charts/awx-platform-operator/Chart.yaml` `version` and `appVersion`, `operator.tag` in the chart values, and `images.awx-operator.tag` in `release/pins.consumer.yaml` to `next_version`. Keep `appVersion` and the tag values quoted. `operator.tag` must stay the only line that is two spaces plus `tag:`.
2. Leave jewel, platform-ui, and the upstream awx pin as they are. Image publishes update those pins through `images-released`. Do not fetch awx-platform-images to move `awx` off `devel`. The controller stays `ghcr.io/ansible/awx` pinned by digest; see awx-platform-images `docs/awx-image.md`.
3. Add `release/notes/v<version>.md`. Do not rewrite `release/notes/v0.1.*.md`. Sections: operator changes, Helm, component pin table, upgrade notes, packages. The Helm example uses `--version` without a leading `v`.
4. Copy any catalog or kind tag that changed onto every consumer the coverage script checks.
5. Run `python3 hack/scripts/check-dependabot-coverage.py` and `python3 -m unittest discover -s release -p 'test_*.py'`.

Open a pull request from `release/calver-<version>`. Do not push it to `main`, and do not push the tag, unless the user explicitly asked to publish. A pushed tag `v<version>` is what starts `release.yml`.

## Hard rules

- Do not vendor AWX, Jewel, or UI source here.
- Prefer digests over floating tags for released component images.
- Do not force-push.

## Checklist

```text
[ ] pull request reviewed (comment only)
[ ] component image pins changed only by images-released, not by this review
[ ] pins.consumer.yaml still matches the last consumed image tag
[ ] catalog and kind image pins copied to every consumer
[ ] release/notes/vYYYY.MM.DD.md written
[ ] user approved a tag
[ ] tag vYYYY.MM.DD
```
