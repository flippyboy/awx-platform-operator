# Proposed AWX controller pin

Resolved `2026-11-09T19:39:07Z` from `devel` on `ansible/awx`. The image tag `devel` is only
how the digest is looked up. Clusters pull `ghcr.io/ansible/awx@sha256:27c9bf689f057a40101289033d71dfb863968dbc0eff045da83c396abcdf820c`.

**Review before merge.** Merging updates the defaults the next operator release
ships. This pull request does not tag an operator release.

Stable and semver upstream tags are not used.

## Pin

| | Previous | Proposed |
|---|---|---|
| Commit | `edabe5d6eb7d` | `d4159cab745d` |
| Digest | `sha256:e37096528788f78fb8f9ebe1255c8f16fda1b4f0929180a83d40ec6be9319680` | `sha256:27c9bf689f057a40101289033d71dfb863968dbc0eff045da83c396abcdf820c` |
| Pull | `ghcr.io/ansible/awx@sha256:e37096528788f78fb8f9ebe1255c8f16fda1b4f0929180a83d40ec6be9319680` | `ghcr.io/ansible/awx@sha256:27c9bf689f057a40101289033d71dfb863968dbc0eff045da83c396abcdf820c` |

## Upstream changes

### `awx` (`devel`)

`edabe5d6eb7d` → `d4159cab745d` — 12 commits. [compare](https://github.com/ansible/awx/compare/edabe5d6eb7d89c87a933dbd51fa28dcc7ca3a0e...d4159cab745d1fa6e2247bf3cf7aae4b0546f1b3)

- [`5333d0d1f993`](https://github.com/ansible/awx/commit/5333d0d1f9930e4d40ae63e38643e674ff740d4b) 2026-10-27 Bump PyJWT to address CVE-2026-102268 (#16748)
- [`53ee6a4a527c`](https://github.com/ansible/awx/commit/53ee6a4a527c69eb7eb33be49fbb287f3ec56665) 2026-10-27 [AAP-76923] Honor AWX_TASK_ENV on job pods and ansible-runner event flags (#16720)
- [`b6a16ac82aa0`](https://github.com/ansible/awx/commit/b6a16ac82aa052425d2cffda70ab6cc2c3cd7987) 2026-10-27 Bump Brotli to address CVE-2026-111497 (#16759)
- [`8565291e43e1`](https://github.com/ansible/awx/commit/8565291e43e17cd1ee5333e82e57aeb230e6574e) 2026-10-28 Fix awxkit config monkeypatching under pytest 9.2 (#16763)
- [`ac5bfc720955`](https://github.com/ansible/awx/commit/ac5bfc720955f52dbdd95f5439ab49df25d586a6) 2026-11-03 fix: define asyncio_default_fixture_loop_scope to avoid failing in re… (#16776)
- [`a49831067591`](https://github.com/ansible/awx/commit/a498310675911e8f8f4588a09f9ccb1263e27e12) 2026-11-03 fix: update gitpython to 3.2.1 (#16769)
- [`85ad07ed6e3f`](https://github.com/ansible/awx/commit/85ad07ed6e3f2252e7f58c785268206d4b187545) 2026-11-04 fix: bump urllib3 to 2.8.0 (#16775)
- [`fe6cd9d45a7e`](https://github.com/ansible/awx/commit/fe6cd9d45a7e977e2b78c8e8e5e69cc24d7eeaaa) 2026-11-05 Fix EDITABLE_DEPENDENCIES=true make docker-compose (#16767)
- [`5054397c26b9`](https://github.com/ansible/awx/commit/5054397c26b924868063ed3f62d8d4cd359f77a4) 2026-11-09 AAP-90162 Run SQLite-backed tests on a current SQLite via sqlean.py (#16784)
- [`c02e6a751318`](https://github.com/ansible/awx/commit/c02e6a751318c04eb36da5377030bf895561cf5c) 2026-11-09 fix: make receptor work-unit reapers resilient to per-unit failures (AAP-97861) (#16774)
- [`cac2ca78cb9f`](https://github.com/ansible/awx/commit/cac2ca78cb9fd06b5750ff95ea6f80dbd86dc981) 2026-11-09 fix: tear down receptor results stream before work release (AAP-97861) (#16773)
- [`d4159cab745d`](https://github.com/ansible/awx/commit/d4159cab745d1fa6e2247bf3cf7aae4b0546f1b3) 2026-11-09 fix: centralize CI Python version in .github/python-version (#16786)
