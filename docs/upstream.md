# Upstream provenance

| Component | Upstream | How we use it |
|-----------|----------|----------------|
| Operator base | [ansible/awx-operator](https://github.com/ansible/awx-operator) | This repo is a soft-fork / evolution (gateway + platform roles) |
| Helm chart base | [ansible-community/awx-operator-helm](https://github.com/ansible-community/awx-operator-helm) | Chart forked as `charts/awx-platform-operator` |
| Controller image | [ansible/awx](https://github.com/ansible/awx) | **Not vendored** — built in awx-platform-images or public GHCR |
| Jewel image | [ansible/jewel](https://github.com/ansible/jewel) | **Not vendored** — built in awx-platform-images |
| Platform UI | [ansible/ansible-ui](https://github.com/ansible/ansible-ui) | **Not vendored** — build-time patches in images repo only |

When syncing improvements from upstream awx-operator, prefer small cherry-picks into `roles/installer` rather than wholesale re-vendoring.
