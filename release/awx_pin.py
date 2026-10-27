#!/usr/bin/env python3
"""Propose a pin of upstream AWX devel for the operator.

The cluster pull is ``ghcr.io/ansible/awx@sha256:...``. ``devel`` is only the
git branch and the floating image tag we resolve. Stable semver tags are not
candidates. This writes a review pull request's files. It does not tag a release.

The commit list in ``release/notes/PROPOSED-awx.md`` is the changelog. The next
operator release copies the ``## Upstream changes`` section into its notes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import consume_image

UPSTREAM_IMAGE = "ghcr.io/ansible/awx"
IMAGE_TAG = "devel"
GIT_REPOSITORY = "https://github.com/ansible/awx.git"
NOTES = "release/notes/PROPOSED-awx.md"
PINS = consume_image.PINS

# image_version on the line after `image: ghcr.io/ansible/awx`.
VERSION_FILES = (
    "roles/platform/defaults/main.yml",
    "charts/awx-platform-operator/values.yaml",
    "charts/awx-platform-operator/examples/platform-kind.yaml",
    "hack/kind/samples/awx-controller.yaml",
    "playbooks/reconcile-controller-standalone.yml",
)
# controller.image_version with no adjacent image line. Gateway stays put.
PLATFORM_SAMPLE = "config/samples/awx_v1beta1_awxplatform.yaml"
KIND_CONTROLLER = consume_image.KIND_CONTROLLER

_RELEASE_TAG = re.compile(r"^v?\d+\.\d+(\.\d+)?([-+].+)?$")
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_KIND_IMAGE = re.compile(r"ghcr\.io/ansible/awx(?::devel|@sha256:[0-9a-f]{64})")
GIT_SKIP = {"stable", "latest", "head", "release"}
DEV_BRANCHES = ("devel", "main", "master")

USER_AGENT = "awx-platform-operator-propose-awx-pin"
MANIFEST_ACCEPT = ", ".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
    ]
)


class ProposeResult:
    def __init__(self, changed: bool, commit: str = "", digest: str = ""):
        self.changed = changed
        self.commit = commit
        self.digest = digest


def is_release_tag(ref: str) -> bool:
    return bool(_RELEASE_TAG.match((ref or "").strip()))


def is_full_sha(ref: str) -> bool:
    return bool(_FULL_SHA.fullmatch((ref or "").strip()))


def is_digest(value: str) -> bool:
    return bool(_DIGEST.fullmatch((value or "").strip()))


def tracking_ref_candidates(configured: str | None) -> list[str]:
    """Development branch first. A semver tag or raw commit is not a branch."""
    ref = (configured or "").strip()
    ordered: list[str] = []
    if ref and not is_release_tag(ref) and ref.lower() not in GIT_SKIP and not is_full_sha(ref):
        ordered.append(ref)
    for name in DEV_BRANCHES:
        if name not in ordered:
            ordered.append(name)
    return ordered


def parse_github_repo(repo_url: str) -> tuple[str, str]:
    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", repo_url or "")
    if not match:
        raise ValueError(f"Not a GitHub URL: {repo_url}")
    return match.group(1), match.group(2)


def github_api(url: str, token: str | None) -> dict | list:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"GitHub {exc.code} for {url}: {body}") from exc


def resolve_commit(owner: str, repo: str, ref: str, token: str | None, api) -> str:
    quoted = urllib.parse.quote(ref, safe="")
    data = api(f"https://api.github.com/repos/{owner}/{repo}/commits/{quoted}", token)
    if isinstance(data, dict) and data.get("sha"):
        sha = str(data["sha"])
        if is_full_sha(sha):
            return sha
    raise RuntimeError(f"Could not resolve {owner}/{repo}@{ref}")


def select_tracking_ref(owner: str, repo: str, configured: str | None, token: str | None, api) -> tuple[str, str]:
    errors: list[str] = []
    for candidate in tracking_ref_candidates(configured):
        try:
            return candidate, resolve_commit(owner, repo, candidate, token, api)
        except Exception as exc:
            errors.append(f"{candidate}: {exc}")
    detail = "; ".join(errors) if errors else "no branch candidates"
    raise RuntimeError(f"Could not resolve a development branch for {owner}/{repo} ({detail})")


def _registry_token(repository: str) -> str:
    url = f"https://ghcr.io/token?service=ghcr.io&scope=repository:{repository}:pull"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode())
    token = payload.get("token") or payload.get("access_token")
    if not token:
        raise RuntimeError(f"no registry token for {repository}")
    return str(token)


def manifest_digest(image_name: str, tag: str) -> str:
    if not image_name.startswith("ghcr.io/"):
        raise RuntimeError(f"only ghcr.io images are resolved, got {image_name}")
    repository = image_name[len("ghcr.io/") :]
    token = _registry_token(repository)
    quoted = urllib.parse.quote(tag, safe="")
    req = urllib.request.Request(
        f"https://ghcr.io/v2/{repository}/manifests/{quoted}",
        method="GET",
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", MANIFEST_ACCEPT)
    req.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            digest = resp.headers.get("Docker-Content-Digest") or ""
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{image_name}:{tag} HTTP {exc.code}") from exc
    if not is_digest(digest):
        raise RuntimeError(f"no digest for {image_name}:{tag}")
    return digest


def normalize_commit(item: dict) -> dict:
    commit = item.get("commit") or {}
    message = (commit.get("message") or "").replace("\r\n", "\n").strip()
    subject = message.splitlines()[0].strip() if message else "(no subject)"
    subject = subject.replace("`", "'")
    if len(subject) > 160:
        subject = subject[:157] + "..."
    date = (((commit.get("author") or {}).get("date")) or "")[:10]
    return {"sha": item.get("sha") or "", "date": date, "subject": subject}


def _walk_commits(owner, repo, base, head, token, cap, api) -> tuple[list[dict], bool]:
    collected: list[dict] = []
    reached = False
    page = 1
    while len(collected) < cap and page <= 15:
        quoted = urllib.parse.quote(head, safe="")
        batch = api(
            f"https://api.github.com/repos/{owner}/{repo}/commits"
            f"?sha={quoted}&per_page=100&page={page}",
            token,
        )
        if not isinstance(batch, list):
            raise RuntimeError(f"unexpected commits payload for {owner}/{repo}")
        if not batch:
            break
        for item in batch:
            sha = str(item.get("sha") or "")
            if base and (sha == base or (len(base) >= 7 and sha.startswith(base))):
                reached = True
                break
            collected.append(normalize_commit(item))
            if len(collected) >= cap:
                break
        if reached or len(batch) < 100 or len(collected) >= cap:
            break
        page += 1
    collected.reverse()
    return collected, reached


def commits_since(owner, repo, base, head, token, api, limit: int = 150) -> dict:
    """Commits on ``head`` after ``base``, oldest first.

    A pin with no previous commit keeps the newest 40 commits and says so.
    A very long range keeps the newest ``limit`` commits and a compare link.
    """
    base = (base or "").strip()
    head = (head or "").strip()
    if base and head and base == head:
        return {
            "commits": [],
            "truncated": False,
            "reached_base": True,
            "no_base": False,
            "error": None,
        }

    no_base = not base
    if not no_base:
        base_q = urllib.parse.quote(base, safe="")
        head_q = urllib.parse.quote(head, safe="")
        try:
            data = api(
                f"https://api.github.com/repos/{owner}/{repo}/compare/{base_q}...{head_q}",
                token,
            )
        except Exception:
            data = None
        if isinstance(data, dict) and isinstance(data.get("commits"), list):
            commits = [normalize_commit(item) for item in data["commits"]]
            total = int(data.get("total_commits") or len(commits))
            if total <= len(commits) and len(commits) <= limit:
                return {
                    "commits": commits,
                    "truncated": False,
                    "reached_base": True,
                    "no_base": False,
                    "error": None,
                }
            newest, reached = _walk_commits(owner, repo, base, head, token, limit, api)
            return {
                "commits": newest,
                "truncated": True,
                "reached_base": reached,
                "no_base": False,
                "error": None,
            }

    cap = 40 if no_base else limit
    collected, reached = _walk_commits(owner, repo, base, head, token, cap, api)
    truncated = len(collected) >= cap if no_base else not reached
    return {
        "commits": collected,
        "truncated": truncated,
        "reached_base": reached,
        "no_base": no_base,
        "error": None,
    }


def format_commit_log(branch: str, old: str, new: str, info: dict, repo: str) -> list[str]:
    lines = [f"### `awx` (`{branch}`)", ""]
    if info.get("error"):
        lines += [f"Could not list upstream commits: {info['error']}", ""]
        return lines
    commits = info.get("commits") or []
    compare = ""
    if repo and len(old) >= 7 and len(new) >= 7:
        compare = f" [compare](https://github.com/{repo}/compare/{old}...{new})"
    if not commits:
        lines += [f"No new upstream commits.{compare}", ""]
        return lines
    if info.get("no_base"):
        extra = " No previous commit; showing the latest commits on the development branch."
    elif info.get("truncated") and not info.get("reached_base"):
        extra = " Previous pin is outside this window; showing the latest development-branch commits."
    elif info.get("truncated"):
        extra = " List truncated."
    else:
        extra = ""
    old_s = old[:12] if old else "none"
    lines += [f"`{old_s}` → `{new[:12]}` — {len(commits)} commits.{extra}{compare}", ""]
    for commit in commits:
        sha = commit.get("sha") or ""
        short = sha[:12]
        if repo and sha:
            shown = f"[`{short}`](https://github.com/{repo}/commit/{sha})"
        else:
            shown = f"`{short}`"
        date = commit.get("date") or ""
        subject = commit.get("subject") or ""
        lines.append(f"- {shown} {date} {subject}".rstrip())
    lines.append("")
    return lines


def _read_pin(text: str) -> dict[str, str]:
    path = ("images", "awx")
    return {
        "repository": consume_image.read_leaf(text, path, "repository").strip(),
        "tag": consume_image.read_leaf(text, path, "tag").strip(),
        "digest": consume_image.read_leaf(text, path, "digest").strip(),
        "git_repository": consume_image.read_leaf(text, path, "git_repository").strip(),
        "git_ref": consume_image.read_leaf(text, path, "git_ref").strip(),
        "git_commit": consume_image.read_leaf(text, path, "git_commit").strip(),
    }


def _defaults_match(root: Path, digest: str) -> bool:
    quoted = f'image_version: "{digest}"'
    for relative in VERSION_FILES:
        if quoted not in (root / relative).read_text(encoding="utf-8"):
            return False
    if quoted not in (root / PLATFORM_SAMPLE).read_text(encoding="utf-8"):
        return False
    kind = (root / KIND_CONTROLLER).read_text(encoding="utf-8")
    return f"{UPSTREAM_IMAGE}@{digest}" in kind


def _set_kind(text: str, digest: str) -> str:
    replacement = f"{UPSTREAM_IMAGE}@{digest}"
    updated, count = _KIND_IMAGE.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"{KIND_CONTROLLER} has no {UPSTREAM_IMAGE}:devel or digest pin")
    leftover = updated.replace(replacement, "", 1)
    if _KIND_IMAGE.search(leftover):
        raise RuntimeError(f"{KIND_CONTROLLER} still has another upstream awx image")
    return updated


def _set_sample(text: str, digest: str) -> str:
    """Set image_version inside the controller block. Leave gateway alone."""
    lines = text.splitlines()
    count = 0
    block_re = re.compile(r"^(\s*)controller:\s*$")
    for index, line in enumerate(lines):
        match = block_re.match(line)
        if not match:
            continue
        indent = len(match.group(1))
        for follow in range(index + 1, len(lines)):
            current = lines[follow]
            if not current.strip():
                continue
            current_indent = len(current) - len(current.lstrip())
            if current_indent <= indent:
                break
            if current.strip().startswith("image_version:"):
                pad = current[:current_indent]
                lines[follow] = f'{pad}image_version: "{digest}"'
                count += 1
                break
    if count != 1:
        raise RuntimeError(f"{PLATFORM_SAMPLE} controller image_version count is {count}")
    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(lines) + suffix


def _render_notes(
    *,
    old_commit: str,
    new_commit: str,
    old_digest: str,
    new_digest: str,
    branch: str,
    info: dict,
    repo: str,
    when: str,
) -> str:
    old_pull = f"{UPSTREAM_IMAGE}@{old_digest}" if old_digest else f"{UPSTREAM_IMAGE}:{IMAGE_TAG}"
    new_pull = f"{UPSTREAM_IMAGE}@{new_digest}"
    old_commit_s = f"`{old_commit[:12]}`" if old_commit else "`none`"
    log = "\n".join(format_commit_log(branch, old_commit, new_commit, info, repo)).rstrip()
    return f"""# Proposed AWX controller pin

Resolved `{when}` from `{branch}` on `{repo}`. The image tag `{IMAGE_TAG}` is only
how the digest is looked up. Clusters pull `{new_pull}`.

**Review before merge.** Merging updates the defaults the next operator release
ships. This pull request does not tag an operator release.

Stable and semver upstream tags are not used.

## Pin

| | Previous | Proposed |
|---|---|---|
| Commit | {old_commit_s} | `{new_commit[:12]}` |
| Digest | `{old_digest or "—"}` | `{new_digest}` |
| Pull | `{old_pull}` | `{new_pull}` |

## Upstream changes

{log}
"""


def propose(
    root: Path,
    *,
    token: str | None = None,
    now: str | None = None,
    github_api_fn=None,
    manifest_digest_fn=None,
) -> ProposeResult:
    api = github_api_fn or github_api
    digest_of = manifest_digest_fn or manifest_digest
    pins_path = root / PINS
    pins = pins_path.read_text(encoding="utf-8")
    current = _read_pin(pins)
    if current["repository"] != UPSTREAM_IMAGE:
        raise RuntimeError(
            f"images.awx.repository is {current['repository']}. "
            "This pipeline pins ghcr.io/ansible/awx only. A built awx-v* image "
            "is applied by images-released."
        )
    git_url = current["git_repository"] or GIT_REPOSITORY
    owner, repo = parse_github_repo(git_url)
    branch, commit = select_tracking_ref(owner, repo, current["git_ref"] or IMAGE_TAG, token, api)
    digest = digest_of(UPSTREAM_IMAGE, IMAGE_TAG)
    if not is_digest(digest):
        raise RuntimeError(f"digest for {UPSTREAM_IMAGE}:{IMAGE_TAG} is not sha256")
    if (
        current["git_commit"] == commit
        and current["digest"] == digest
        and current["git_ref"] == branch
        and _defaults_match(root, digest)
    ):
        return ProposeResult(False, commit, digest)

    old_commit = current["git_commit"]
    try:
        info = commits_since(owner, repo, old_commit, commit, token, api)
    except Exception as exc:
        info = {
            "error": str(exc),
            "commits": [],
            "truncated": False,
            "reached_base": False,
            "no_base": not old_commit,
        }

    when = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated = pins
    updated = consume_image.set_leaf(updated, (), "updated", when)
    image_path = ("images", "awx")
    updated = consume_image.set_leaf(updated, image_path, "tag", IMAGE_TAG)
    updated = consume_image.set_leaf(updated, image_path, "digest", digest)
    updated = consume_image.set_leaf(updated, image_path, "git_repository", git_url)
    updated = consume_image.set_leaf(updated, image_path, "git_ref", branch)
    updated = consume_image.set_leaf(updated, image_path, "git_commit", commit)
    pins_path.write_text(updated, encoding="utf-8")

    for relative in VERSION_FILES:
        path = root / relative
        text, count = consume_image.set_following(path.read_text(encoding="utf-8"), UPSTREAM_IMAGE, "image_version", digest)
        if count != 1:
            raise RuntimeError(f"{relative} image_version updates: {count}")
        path.write_text(text, encoding="utf-8")

    sample = root / PLATFORM_SAMPLE
    sample.write_text(_set_sample(sample.read_text(encoding="utf-8"), digest), encoding="utf-8")
    kind = root / KIND_CONTROLLER
    kind.write_text(_set_kind(kind.read_text(encoding="utf-8"), digest), encoding="utf-8")

    notes = root / NOTES
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text(
        _render_notes(
            old_commit=old_commit,
            new_commit=commit,
            old_digest=current["digest"],
            new_digest=digest,
            branch=branch,
            info=info,
            repo=f"{owner}/{repo}",
            when=when,
        ),
        encoding="utf-8",
    )
    return ProposeResult(True, commit, digest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--github-token", default="")
    args = parser.parse_args()
    try:
        result = propose(args.root, token=args.github_token or None)
    except (RuntimeError, ValueError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(
        f"changed={str(result.changed).lower()} commit={result.commit[:12]} digest={result.digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
