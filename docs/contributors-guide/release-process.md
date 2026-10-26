# Release Process

This fork does not use the upstream Stage and Promote workflows. Operator releases are calendar versions (`vYYYY.MM.DD`). `v0.1.13` is the last semver tag. See [Operator + chart releases](../release.md) and `release/AGENTS.md`.

The upstream process below applies to ansible/awx-operator, not to this repository.

The first step is to create a draft release. Typically this will happen in the [Stage Release](https://github.com/ansible/awx/blob/devel/.github/workflows/stage.yml) workflow for AWX and you don't need to do it as a separate step.

If you need to do an independent release of the operator, you can run the [Stage Release](https://github.com/ansible/awx-operator/blob/devel/.github/workflows/stage.yml) in the awx-operator repo. Both of these workflows will run smoke tests, so there is no need to do this manually.

After the draft release is created, publish it and the [Promote AWX Operator image](https://github.com/ansible/awx-operator/blob/devel/.github/workflows/promote.yaml) will run, which will:

- Publish image to Quay
- Release Helm chart
