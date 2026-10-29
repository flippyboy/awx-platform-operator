#!/usr/bin/env python3
"""Pin one published component image and cut the next operator version.

awx-platform-images dispatches this after it pushes an image. The operator
release then carries that tag and digest. Other component pins stay put.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import calver

COMPONENTS = ("platform-ui", "jewel-with-ui", "awx")
JEWEL_IMAGE = "ghcr.io/flippyboy/awx/jewel-with-ui"
UPSTREAM_AWX_IMAGE = "ghcr.io/ansible/awx"
OUR_AWX_IMAGE = "ghcr.io/flippyboy/awx/awx"
OPERATOR_IMAGE = "ghcr.io/flippyboy/awx/awx-platform-operator"
PINS = "release/pins.consumer.yaml"
CHART = "charts/awx-platform-operator/Chart.yaml"

JEWEL_VERSION_FILES = (
    "roles/gateway/defaults/main.yml",
    "roles/platform/defaults/main.yml",
    "charts/awx-platform-operator/values.yaml",
    "charts/awx-platform-operator/examples/platform-kind.yaml",
    "charts/awx-platform-operator/examples/awx-gateway-only.yaml",
)
AWX_VERSION_FILES = (
    "roles/platform/defaults/main.yml",
    "charts/awx-platform-operator/values.yaml",
    "charts/awx-platform-operator/examples/platform-kind.yaml",
)
OPERATOR_TAG_FILES = (
    "charts/awx-platform-operator/values.yaml",
    "charts/awx-platform-operator/examples/platform-kind.yaml",
    "charts/awx-platform-operator/examples/awx-gateway-only.yaml",
)
KIND_CONTROLLER = "hack/kind/controller-smoke/controller.yaml"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_LEGACY_RE = re.compile(r"^0\.\d+\.\d+$")
_KEY_RE = re.compile(r"^(\s*)([A-Za-z0-9_-]+):(.*)$")


class ConsumeResult:
    def __init__(self, operator_version: str, skipped: bool):
        self.operator_version = operator_version
        self.skipped = skipped


def _is_image_version(version: str) -> bool:
    return calver.is_calver(version) or _LEGACY_RE.fullmatch(version) is not None


def _leaves(lines: list[str]):
    stack: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _KEY_RE.match(line)
        if not match:
            continue
        indent = len(match.group(1))
        name = match.group(2)
        rest = match.group(3).strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if rest == "" or rest in {">", ">-", "|", "|-"}:
            stack.append((indent, name))
            continue
        yield index, tuple(item[1] for item in stack), name


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def read_leaf(text: str, path: tuple[str, ...], key: str) -> str:
    lines = text.splitlines()
    found = [
        lines[index]
        for index, leaf_path, name in _leaves(lines)
        if leaf_path == path and name == key
    ]
    if len(found) != 1:
        raise RuntimeError(f"expected one {path + (key,)} in pins, found {len(found)}")
    rest = found[0].split(":", 1)[1]
    return _unquote(rest)


def set_leaf(text: str, path: tuple[str, ...], key: str, value: str) -> str:
    lines = text.splitlines()
    hits = [
        index
        for index, leaf_path, name in _leaves(lines)
        if leaf_path == path and name == key
    ]
    if len(hits) != 1:
        raise RuntimeError(f"expected one {path + (key,)} in pins, found {len(hits)}")
    index = hits[0]
    indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
    lines[index] = f'{indent}{key}: "{value}"'
    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(lines) + suffix


def set_following(text: str, image: str, field: str, value: str) -> tuple[str, int]:
    """Set ``field`` on the line after an exact ``image: <image>`` line."""
    lines = text.splitlines()
    count = 0
    rendered = f'"{value}"'
    for index, line in enumerate(lines):
        if line.strip() != f"image: {image}":
            continue
        for follow in range(index + 1, min(index + 4, len(lines))):
            stripped = lines[follow].strip()
            if stripped.startswith(f"{field}:"):
                indent = lines[follow][: len(lines[follow]) - len(lines[follow].lstrip())]
                lines[follow] = f"{indent}{field}: {rendered}"
                count += 1
                break
            if stripped.startswith("image:"):
                break
    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(lines) + suffix, count


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _chart_version(text: str) -> str:
    match = re.search(r"^version:\s*(\S+)\s*$", text, re.M)
    if not match:
        raise RuntimeError("Chart.yaml has no version")
    return match.group(1)


def _set_chart_version(text: str, version: str) -> str:
    text, version_count = re.subn(
        r"^version:.*$", f"version: {version}", text, count=1, flags=re.M
    )
    text, app_count = re.subn(
        r"^appVersion:.*$", f'appVersion: "{version}"', text, count=1, flags=re.M
    )
    if version_count != 1 or app_count != 1:
        raise RuntimeError("Chart.yaml version or appVersion was not updated")
    return text


def operator_changes(root: Path) -> str:
    """Commits on this branch since the last operator tag, newest first."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    try:
        last = git("describe", "--tags", "--abbrev=0", "--match", "v*")
        log = git("log", "--no-merges", "--format=%h %s", f"{last}..HEAD")
    except (OSError, subprocess.CalledProcessError):
        log = ""
        last = ""
    lines = [line for line in log.splitlines() if line.strip()]
    if not lines:
        return "No operator code changes."
    items = "\n".join(f"- `{line[:line.index(' ')]}` {line[line.index(' ') + 1:]}" for line in lines)
    return f"Commits since `{last}`:\n\n{items}"


def awx_changelog(root: Path) -> str:
    """Commit list from the last merged AWX pin proposal, if there is one."""
    path = root / "release" / "notes" / "PROPOSED-awx.md"
    if not path.is_file():
        return (
            "No AWX pin proposal has been merged yet. The controller pull stays "
            "`ghcr.io/ansible/awx:devel` until `propose-awx-pin` records a commit and digest.\n"
        )
    text = path.read_text(encoding="utf-8")
    marker = "## Upstream changes"
    index = text.find(marker)
    if index < 0:
        return "AWX pin notes are in `release/notes/PROPOSED-awx.md`.\n"
    return text[index + len(marker) :].strip() + "\n"


def _notes(
    *,
    operator_version: str,
    component: str,
    version: str,
    digest: str,
    git_tag: str,
    previous: dict[str, tuple[str, str, str, str]],
    repository: str,
    awx_changes: str,
    operator_changes: str,
) -> str:
    rows = []
    for name in ("platform-ui", "jewel-with-ui", "awx"):
        old_tag, old_ref, old_digest, old_repo = previous[name]
        if name == component:
            new = f"`{version}` (`{digest}`)"
            ref = f"`{git_tag}`"
        elif name == "awx" and old_digest:
            new = f"`{old_repo}@{old_digest}` (tracking `{old_tag}`)"
            ref = "—"
        elif name == "awx":
            new = f"`{old_tag}` (no digest yet)"
            ref = "—"
        else:
            new = f"`{old_tag}` (unchanged)"
            ref = f"`{old_ref}`" if old_ref else "—"
        rows.append(f"| {name} | `{old_tag}` | {new} | {ref} |")
    table = "\n".join(rows)
    return f"""# awx-platform-operator v{operator_version}

Consumed `{git_tag}` from awx-platform-images.

## Operator / role / CRD changes

This release records the image published by `{git_tag}`.

{operator_changes}

## Helm chart

- Chart / appVersion `{operator_version}`
- Operator image default `{OPERATOR_IMAGE}:{operator_version}`
- `{component}` pin `{repository}:{version}` (`{digest}`)
- Other component pins are unchanged

## Component pins

| Component | Previous | New | Images-repo tag |
|-----------|----------|-----|-----------------|
{table}

## Upstream AWX

{awx_changes.rstrip()}

## Upgrade notes

Upgrade the operator chart so new installs pull the pinned image. Workloads already running keep their current image until the next reconcile.

## Packages

| Package | Path |
|---------|------|
| Operator | `{OPERATOR_IMAGE}:{operator_version}` |
| Helm | `oci://ghcr.io/flippyboy/awx/awx-platform-operator-helm:{operator_version}` |

```bash
helm upgrade --install awx-platform oci://ghcr.io/flippyboy/awx/awx-platform-operator-helm \\
  --version {operator_version} -n awx-platform --create-namespace
```
"""


def apply(
    root: Path,
    *,
    component: str,
    version: str,
    digest: str,
    git_tag: str,
    today: date | None = None,
) -> ConsumeResult:
    if component not in COMPONENTS:
        raise ValueError(f"component must be one of {', '.join(COMPONENTS)}")
    version = version.strip().lstrip("v")
    if not _is_image_version(version):
        raise ValueError(
            "version must be calver YYYY.MM.DD or YYYY.MM.DD-N, or a legacy 0.x.y tag"
        )
    if not _DIGEST_RE.fullmatch(digest):
        raise ValueError("digest must look like sha256:<64 hex chars>")
    git_tag = git_tag.strip() or f"{component}-v{version}"

    pins_path = root / PINS
    pins = _read(pins_path)
    image_path = ("images", component)
    current_tag = read_leaf(pins, image_path, "tag")
    current_digest = read_leaf(pins, image_path, "digest")
    chart = _read(root / CHART)
    current_operator = _chart_version(chart)
    if current_tag == version and current_digest == digest:
        return ConsumeResult(current_operator, True)

    previous = {}
    for name in COMPONENTS:
        previous[name] = (
            read_leaf(pins, ("images", name), "tag"),
            read_leaf(pins, ("source_releases",), name),
            read_leaf(pins, ("images", name), "digest"),
            read_leaf(pins, ("images", name), "repository"),
        )

    repository = read_leaf(pins, image_path, "repository")
    if component == "awx":
        repository = OUR_AWX_IMAGE

    operator_version = calver.next_version(current_operator, today=today)
    when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pins = set_leaf(pins, (), "updated", when)
    pins = set_leaf(pins, ("source_releases",), component, git_tag)
    pins = set_leaf(pins, image_path, "tag", version)
    pins = set_leaf(pins, image_path, "digest", digest)
    if component == "awx":
        pins = set_leaf(pins, image_path, "repository", repository)
    pins = set_leaf(pins, ("images", "awx-operator"), "tag", operator_version)
    _write(pins_path, pins)

    _write(root / CHART, _set_chart_version(chart, operator_version))

    for relative in OPERATOR_TAG_FILES:
        path = root / relative
        text, count = set_following(_read(path), OPERATOR_IMAGE, "tag", operator_version)
        if count < 1:
            raise RuntimeError(f"no operator tag after {OPERATOR_IMAGE} in {relative}")
        _write(path, text)

    if component == "jewel-with-ui":
        for relative in JEWEL_VERSION_FILES:
            path = root / relative
            text, count = set_following(_read(path), JEWEL_IMAGE, "image_version", version)
            if count < 1:
                raise RuntimeError(f"no image_version after {JEWEL_IMAGE} in {relative}")
            _write(path, text)
    elif component == "awx":
        for relative in AWX_VERSION_FILES:
            path = root / relative
            text, count = set_following(
                _read(path), UPSTREAM_AWX_IMAGE, "image_version", version
            )
            if count < 1:
                raise RuntimeError(
                    f"no image_version after {UPSTREAM_AWX_IMAGE} in {relative}"
                )
            text = text.replace(
                f"image: {UPSTREAM_AWX_IMAGE}\n", f"image: {OUR_AWX_IMAGE}\n"
            )
            _write(path, text)
        kind = root / KIND_CONTROLLER
        kind_text = _read(kind)
        new = f"image: {OUR_AWX_IMAGE}:{version}"
        devel = f"image: {UPSTREAM_AWX_IMAGE}:devel"
        if devel in kind_text:
            kind_text = kind_text.replace(devel, new, 1)
        else:
            kind_text, count = re.subn(
                rf"image: {re.escape(UPSTREAM_AWX_IMAGE)}@sha256:[0-9a-f]{{64}}",
                new,
                kind_text,
                count=1,
            )
            if count != 1:
                raise RuntimeError(f"{KIND_CONTROLLER} has no upstream awx image to retarget")
        _write(kind, kind_text)

    notes = root / "release" / "notes" / f"v{operator_version}.md"
    if notes.exists():
        raise RuntimeError(f"{notes} already exists")
    notes.write_text(
        _notes(
            operator_version=operator_version,
            component=component,
            version=version,
            digest=digest,
            git_tag=git_tag,
            previous=previous,
            repository=repository,
            awx_changes=awx_changelog(root),
            operator_changes=operator_changes(root),
        ),
        encoding="utf-8",
    )
    return ConsumeResult(operator_version, False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--component", required=True, choices=COMPONENTS)
    parser.add_argument("--version", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--git-tag", default="")
    parser.add_argument("--today", default="", help="UTC day YYYY-MM-DD (tests)")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    today = date.fromisoformat(args.today) if args.today else None
    try:
        result = apply(
            args.root,
            component=args.component,
            version=args.version,
            digest=args.digest,
            git_tag=args.git_tag,
            today=today,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(
        f"operator_version={result.operator_version} skipped={str(result.skipped).lower()}"
    )
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"operator_version={result.operator_version}\n")
            handle.write(f"skipped={'true' if result.skipped else 'false'}\n")
            handle.write(f"component={args.component}\n")
            handle.write(f"image_version={args.version.strip().lstrip('v')}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
