# Proposed AWX controller pin

Resolved `2026-11-16T19:26:02Z` from `devel` on `ansible/awx`. The image tag `devel` is only
how the digest is looked up. Clusters pull `ghcr.io/ansible/awx@sha256:5201477a711d3623fb982d1fcaff3e2f010b9cebee79ac835db08cf8d37d8851`.

**Review before merge.** Merging updates the defaults the next operator release
ships. This pull request does not tag an operator release.

Stable and semver upstream tags are not used.

## Pin

| | Previous | Proposed |
|---|---|---|
| Commit | `edabe5d6eb7d` | `7de482b075ef` |
| Digest | `sha256:e37096528788f78fb8f9ebe1255c8f16fda1b4f0929180a83d40ec6be9319680` | `sha256:5201477a711d3623fb982d1fcaff3e2f010b9cebee79ac835db08cf8d37d8851` |
| Pull | `ghcr.io/ansible/awx@sha256:e37096528788f78fb8f9ebe1255c8f16fda1b4f0929180a83d40ec6be9319680` | `ghcr.io/ansible/awx@sha256:5201477a711d3623fb982d1fcaff3e2f010b9cebee79ac835db08cf8d37d8851` |

## Upstream changes

### `awx` (`devel`)

`edabe5d6eb7d` → `7de482b075ef` — 19 commits. [compare](https://github.com/ansible/awx/compare/edabe5d6eb7d89c87a933dbd51fa28dcc7ca3a0e...7de482b075ef78add0f49b04b26f24bf0fd5a14b)

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
- [`f1bf5721718b`](https://github.com/ansible/awx/commit/f1bf5721718b4213145e66bc81f9a376e0053483) 2026-11-10 [Devel] [AAP-96816] Add New Deprecation Mechanisms To Existing Deprectations (#16771)
- [`b970bf20255b`](https://github.com/ansible/awx/commit/b970bf20255b6782fc4daccf81e7ee6d4a4dd174) 2026-11-12 [Devel] Add Deprecation Detail In Browsable API Banner (#16777)
- [`798f71b7f9ce`](https://github.com/ansible/awx/commit/798f71b7f9cefbe5c4e27bfe47cbec6b610f1915) 2026-11-13 AAP-91965 Add approval label authorization caller workflow (#16762)
- [`c5c89639aa3a`](https://github.com/ansible/awx/commit/c5c89639aa3a992efe2f2e103f5a114f925334df) 2026-11-13 fix: update aiohttp version (#16802)
- [`5be49a25ea4a`](https://github.com/ansible/awx/commit/5be49a25ea4a1d39bd3324f664dd34aafd9f529a) 2026-11-13 [AAP-99520] Fix: Insights project sync failing to copy playbooks to job execution (#16793)
- [`89e2163cfc10`](https://github.com/ansible/awx/commit/89e2163cfc10100fe77810e895e3ca2051691822) 2026-11-16 [AAP-96820] Make job adoption testable and cover its failure scenarios (#16728)
- [`7de482b075ef`](https://github.com/ansible/awx/commit/7de482b075ef78add0f49b04b26f24bf0fd5a14b) 2026-11-16 Bump sqlparse to 0.6.1 (#16798)
