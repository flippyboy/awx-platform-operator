# Proposed AWX controller pin

Resolved `2026-11-02T19:20:33Z` from `devel` on `ansible/awx`. The image tag `devel` is only
how the digest is looked up. Clusters pull `ghcr.io/ansible/awx@sha256:db7b4c9b3bd225e6d28c4b210f15c3d4d7799ffb0ab55dc352b5b0b46724a8ab`.

**Review before merge.** Merging updates the defaults the next operator release
ships. This pull request does not tag an operator release.

Stable and semver upstream tags are not used.

## Pin

| | Previous | Proposed |
|---|---|---|
| Commit | `edabe5d6eb7d` | `8565291e43e1` |
| Digest | `sha256:e37096528788f78fb8f9ebe1255c8f16fda1b4f0929180a83d40ec6be9319680` | `sha256:db7b4c9b3bd225e6d28c4b210f15c3d4d7799ffb0ab55dc352b5b0b46724a8ab` |
| Pull | `ghcr.io/ansible/awx@sha256:e37096528788f78fb8f9ebe1255c8f16fda1b4f0929180a83d40ec6be9319680` | `ghcr.io/ansible/awx@sha256:db7b4c9b3bd225e6d28c4b210f15c3d4d7799ffb0ab55dc352b5b0b46724a8ab` |

## Upstream changes

### `awx` (`devel`)

`edabe5d6eb7d` → `8565291e43e1` — 4 commits. [compare](https://github.com/ansible/awx/compare/edabe5d6eb7d89c87a933dbd51fa28dcc7ca3a0e...8565291e43e17cd1ee5333e82e57aeb230e6574e)

- [`5333d0d1f993`](https://github.com/ansible/awx/commit/5333d0d1f9930e4d40ae63e38643e674ff740d4b) 2026-10-27 Bump PyJWT to address CVE-2026-102268 (#16748)
- [`53ee6a4a527c`](https://github.com/ansible/awx/commit/53ee6a4a527c69eb7eb33be49fbb287f3ec56665) 2026-10-27 [AAP-76923] Honor AWX_TASK_ENV on job pods and ansible-runner event flags (#16720)
- [`b6a16ac82aa0`](https://github.com/ansible/awx/commit/b6a16ac82aa052425d2cffda70ab6cc2c3cd7987) 2026-10-27 Bump Brotli to address CVE-2026-111497 (#16759)
- [`8565291e43e1`](https://github.com/ansible/awx/commit/8565291e43e17cd1ee5333e82e57aeb230e6574e) 2026-10-28 Fix awxkit config monkeypatching under pytest 9.2 (#16763)
