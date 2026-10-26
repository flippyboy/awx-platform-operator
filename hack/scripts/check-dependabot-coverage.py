#!/usr/bin/env python3
"""Fail if a dependency pin is invisible to Dependabot.

Dependabot updates pinned versions in requirements.txt, Dockerfiles,
Kubernetes manifests, and Helm ``image.repository`` / ``image.tag`` blocks.
Ansible defaults, shell scripts, Jinja fallbacks, and scorecard patches are
not manifests. Those pins are copied into hack/dependabot/images/values.yaml,
or they must match the tag Dependabot already sees in a kind manifest.

Ansible Galaxy has no Dependabot ecosystem. Collection versions must still
be explicit so they do not float.

ghcr.io/flippyboy/awx/* tags are our own releases, not dependencies.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEPENDABOT = ROOT / ".github" / "dependabot.yml"
CATALOG = ROOT / "hack" / "dependabot" / "images" / "values.yaml"

SKIP_DIR_PARTS = {
    ".git",
    "vendor",
    "dist",
    "__pycache__",
}
SKIP_PREFIXES = (
    "release/notes/",
    "charts/awx-platform-operator/crds/",
    "config/crd/",
    "hack/kind/crds/",
)
SKIP_FILES = {"CHANGELOG.md"}
SKIP_SUFFIXES = (".md", ".png", ".gz", ".tgz", ".pyc")

# Tags we keep floating on purpose. awx and jewel track upstream development
# images, not a stable tag. controller:latest is an operator-sdk placeholder
# and is ignored because it has no registry.
FLOATING = {
    "quay.io/ansible/awx-ee:latest",
    "ghcr.io/ansible/awx:devel",
    "quay.io/ansible/awx:latest",
    "quay.io/sclorg/postgresql-15-c9s:latest",
    "ghcr.io/ansible/jewel:latest",
    "quay.io/ansible/awx-operator:devel",
    "awx-compose/jewel:local",
}
OWN_PREFIX = "ghcr.io/flippyboy/awx/"

# Registry, then one or more slash-separated name segments, then :tag.
# The host must contain a dot, so prose like "port/name:tag" is not an image.
REF_RE = re.compile(
    r"(?<![\w.@])"
    r"("
    r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?(?::\d+)?"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+"
    r":[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
    r")"
)
JEWEL_LOCAL_RE = re.compile(
    r"(?<![\w.@])awx-compose/jewel:([A-Za-z0-9][A-Za-z0-9._-]*)"
)


def load_dependabot() -> dict[str, list[str]]:
    data = yaml.safe_load(DEPENDABOT.read_text())
    ecosystems: dict[str, list[str]] = {}
    for update in data["updates"]:
        eco = update["package-ecosystem"]
        dirs: list[str] = []
        if "directory" in update:
            dirs.append(update["directory"])
        dirs.extend(update.get("directories") or [])
        ecosystems.setdefault(eco, []).extend(_norm(d) for d in dirs)
    return ecosystems


def _norm(directory: str) -> str:
    return directory.strip().strip("/")


def dir_of(rel: str) -> str:
    parent = str(Path(rel).parent)
    return "" if parent == "." else parent


def iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if set(Path(rel).parts) & SKIP_DIR_PARTS:
            continue
        if rel in SKIP_FILES or rel.endswith(SKIP_SUFFIXES):
            continue
        if rel.startswith(SKIP_PREFIXES):
            continue
        yield rel, path


def catalog_entries(catalog: dict) -> list[dict]:
    entries = []
    for name, body in catalog.items():
        if not isinstance(body, dict) or "image" not in body:
            continue
        image = body["image"]
        entries.append(
            {
                "name": name,
                "repository": str(image["repository"]),
                "tag": str(image["tag"]),
                "consumers": body.get("consumers") or [],
            }
        )
    return entries


def ref_of(entry: dict) -> str:
    return f"{entry['repository']}:{entry['tag']}"


def check_catalog(entries: list[dict], errors: list[str]) -> set[tuple[str, str]]:
    allowed: set[tuple[str, str]] = set()
    tags: dict[str, str] = {}
    catalog_rel = CATALOG.relative_to(ROOT).as_posix()
    for entry in entries:
        tag = entry["tag"]
        if tag in tags:
            errors.append(
                "catalog tags must be unique so Dependabot cannot rewrite the "
                f"wrong image ({tag}: {tags[tag]} and {entry['name']})"
            )
        tags[tag] = entry["name"]
        ref = ref_of(entry)
        allowed.add((catalog_rel, ref))
        if not entry["consumers"]:
            errors.append(f"catalog image {entry['name']} has no consumers")
        for consumer in entry["consumers"]:
            rel = consumer["path"]
            path = ROOT / rel
            if not path.is_file():
                errors.append(f"catalog consumer missing: {rel}")
                continue
            text = path.read_text()
            match = consumer.get("match", "ref")
            if match == "ref":
                if ref not in text:
                    errors.append(f"{rel} does not contain {ref}")
                else:
                    allowed.add((rel, ref))
            elif match == "tag":
                if tag not in text:
                    errors.append(f"{rel} does not contain tag {tag} ({entry['name']})")
            else:
                errors.append(f"unknown consumer match {match!r} for {entry['name']}")
    return allowed


def _host(ref: str) -> str:
    repository, _, _tag = ref.rpartition(":")
    return repository.split("/", 1)[0]


def check_refs(docker_dirs: list[str], allowed: set[tuple[str, str]], errors: list[str]) -> None:
    for rel, path in iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        scanned_here = dir_of(rel) in docker_dirs
        for ref in REF_RE.findall(text):
            if "{{" in ref or "}}" in ref:
                continue
            if "." not in _host(ref).split(":", 1)[0]:
                continue
            if ref.startswith(OWN_PREFIX) or ref in FLOATING:
                continue
            if scanned_here or (rel, ref) in allowed:
                continue
            errors.append(f"unscanned image pin {ref} in {rel}")
        if scanned_here:
            continue
        for tag in JEWEL_LOCAL_RE.findall(text):
            ref = f"awx-compose/jewel:{tag}"
            if ref in FLOATING:
                continue
            errors.append(f"unscanned image pin {ref} in {rel}")


def check_pip(pip_dirs: list[str], errors: list[str]) -> None:
    reqs = [
        rel
        for rel, path in iter_files()
        if path.name in {"requirements.txt", "requirements.in"}
    ]
    for rel in reqs:
        if rel.endswith("requirements.txt") and dir_of(rel) not in pip_dirs:
            errors.append(f"pip manifest {rel} is not in a Dependabot pip directory")
    for rel in reqs:
        if not rel.endswith("requirements.in"):
            continue
        txt_path = ROOT / str(Path(rel).with_name("requirements.txt"))
        if not txt_path.is_file():
            errors.append(f"{rel} has no sibling requirements.txt")
            continue
        pinned = set()
        for line in txt_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^([A-Za-z0-9_.-]+)==", line)
            if match:
                pinned.add(match.group(1).lower().replace("_", "-"))
        for line in (ROOT / rel).read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            match = re.match(r"^([A-Za-z0-9_.-]+)", line)
            if not match:
                continue
            name = match.group(1).lower().replace("_", "-")
            if name not in pinned:
                errors.append(
                    f"{rel} dependency {name} is not pinned with == in "
                    f"{txt_path.relative_to(ROOT).as_posix()}"
                )


def check_actions(ecosystems: dict[str, list[str]], errors: list[str]) -> None:
    if "" not in ecosystems.get("github-actions", []):
        errors.append("github-actions Dependabot entry must use directory /")
    uses = re.compile(r"uses:\s*(\S+)")
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        for line in path.read_text().splitlines():
            match = uses.search(line)
            if not match:
                continue
            ref = match.group(1)
            if ref.startswith("./") or ref.startswith("docker://"):
                errors.append(
                    f"{path.relative_to(ROOT).as_posix()} uses an action Dependabot "
                    f"does not update: {ref}"
                )


def check_galaxy(errors: list[str]) -> None:
    for rel in ("requirements.yml", "molecule/requirements.yml"):
        data = yaml.safe_load((ROOT / rel).read_text())
        for col in data.get("collections") or []:
            if not col.get("version"):
                errors.append(f"{rel} collection {col.get('name')} has no version pin")


def version_scalars(path: Path, key: str) -> set[str]:
    pattern = re.compile(rf"^[ \t]*{re.escape(key)}:\s*[\"']?([^\"'\s#]+)", re.M)
    return set(pattern.findall(path.read_text()))


def tags_in(path: Path, repository: str) -> set[str]:
    return set(
        re.findall(
            re.escape(repository) + r":([A-Za-z0-9][A-Za-z0-9._-]*)",
            path.read_text(),
        )
    )


def check_mirrors(errors: list[str]) -> set[tuple[str, str]]:
    """Kind manifests are the Dependabot source for these images.

    Every other copy of the same repository must use that tag. Role defaults
    that split repository and version are checked by YAML key.
    """
    allowed: set[tuple[str, str]] = set()

    def align(
        repository: str,
        kind_files: list[str],
        version_files: list[tuple[str, str]],
    ) -> None:
        tags: set[str] = set()
        for rel in kind_files:
            tags |= tags_in(ROOT / rel, repository)
        if len(tags) != 1:
            errors.append(f"{repository} kind tags disagree: {sorted(tags)}")
            return
        tag = next(iter(tags))
        ref = f"{repository}:{tag}"
        for rel, key in version_files:
            got = version_scalars(ROOT / rel, key)
            if got != {tag}:
                errors.append(
                    f"{rel} {key}={sorted(got)} does not match kind tag {tag} ({repository})"
                )
        for rel, path in iter_files():
            found = tags_in(path, repository)
            if not found:
                continue
            if found != {tag}:
                errors.append(
                    f"{rel} pins {repository} at {sorted(found)}; kind manifests use {tag}"
                )
            else:
                allowed.add((rel, ref))

    align(
        "mirror.gcr.io/library/redis",
        [
            "hack/kind/controller-smoke/redis.yaml",
            "hack/kind/platform-smoke/redis-jewel.yaml",
        ],
        [
            ("roles/gateway/defaults/main.yml", "redis_image_version"),
            ("roles/installer/defaults/main.yml", "_redis_image_version"),
            ("playbooks/reconcile-controller-standalone.yml", "redis_image_version"),
            ("playbooks/reconcile-gateway-standalone.yml", "redis_image_version"),
            ("hack/scripts/kind-reconcile-gateway.sh", "redis_image_version"),
        ],
    )
    align(
        "mirror.gcr.io/envoyproxy/envoy",
        [
            "hack/kind/platform-smoke/envoy.yaml",
            "hack/kind/platform-smoke/jewel.yaml",
        ],
        [
            ("roles/gateway/defaults/main.yml", "envoy_image_version"),
            ("playbooks/reconcile-gateway-standalone.yml", "envoy_image_version"),
            ("hack/scripts/kind-reconcile-gateway.sh", "envoy_image_version"),
        ],
    )
    align(
        "mirror.gcr.io/library/postgres",
        ["hack/kind/platform-smoke/postgres.yaml"],
        [],
    )
    return allowed


def check_workflow_pip(errors: list[str]) -> None:
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if "pip install" not in line:
                continue
            if "-r " in line or "--requirement" in line:
                continue
            errors.append(
                f"{path.relative_to(ROOT).as_posix()}:{number} installs Python packages "
                f"outside a requirements.txt Dependabot can see: {line.strip()}"
            )


def main() -> int:
    errors: list[str] = []
    ecosystems = load_dependabot()
    allowed = check_catalog(catalog_entries(yaml.safe_load(CATALOG.read_text())), errors)
    allowed |= check_mirrors(errors)
    check_refs(ecosystems.get("docker", []), allowed, errors)
    check_pip(ecosystems.get("pip", []), errors)
    check_actions(ecosystems, errors)
    check_galaxy(errors)
    check_workflow_pip(errors)
    if errors:
        print("Dependabot coverage gaps:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("Dependabot coverage OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
