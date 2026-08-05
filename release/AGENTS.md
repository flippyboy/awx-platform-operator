# Agent instructions: operator + chart releases

Companion: **awx-platform-images** owns component pin selection (`pins.yaml`, weekly proposals).

## Your job in this repo

1. **Consume** published component digests from an images release (`images-v*`).
2. Update `release/pins.consumer.yaml` and Helm defaults if needed.
3. Draft operator/chart release notes under `release/notes/vX.Y.Z.md`.
4. Recommend git tag `vX.Y.Z` for the operator (aligned chart version `X.Y.Z`).

## Hard rules

- Do not vendor AWX/Jewel/UI source here.
- Prefer digests over floating tags for release defaults.
- Do not push tags unless the user explicitly asks.

## Checklist

```text
[ ] images release published (notes + GHCR tags)
[ ] pins.consumer.yaml updated
[ ] helm lint clean
[ ] chart examples point at released images
[ ] release/notes/vX.Y.Z.md written (operator changes + pin table)
[ ] user approved → tag vX.Y.Z
```

## Note template sections

1. Operator / role / CRD changes  
2. Helm chart changes  
3. Component pin table (from images release)  
4. Upgrade notes / breaking changes  
