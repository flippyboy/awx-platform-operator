import re
import shutil
import unittest
from datetime import date
from pathlib import Path

import consume_image

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 10, 26)
DIGEST = "sha256:" + "ab" * 32
COPIES = (
    "release/pins.consumer.yaml",
    "charts/awx-platform-operator/Chart.yaml",
    "charts/awx-platform-operator/values.yaml",
    "charts/awx-platform-operator/examples/platform-kind.yaml",
    "charts/awx-platform-operator/examples/awx-gateway-only.yaml",
    "roles/gateway/defaults/main.yml",
    "roles/platform/defaults/main.yml",
    "hack/kind/controller-smoke/controller.yaml",
)


def _pin(relative: str, name: str, key: str = "tag") -> str:
    """Value in the real tree before a test changes its copy."""
    text = (ROOT / relative).read_text(encoding="utf-8")
    return consume_image.read_leaf(text, ("images", name), key)


def _controller_version(text: str) -> str:
    """image_version on the line after the upstream controller image."""
    match = re.search(
        rf"image: {re.escape(consume_image.UPSTREAM_AWX_IMAGE)}\n\s+image_version: (.+)",
        text,
    )
    assert match, "no upstream controller image_version"
    return match.group(1)


def _tree(tmp: Path) -> Path:
    for relative in COPIES:
        destination = tmp / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / relative, destination)
    (tmp / "release" / "notes").mkdir(parents=True, exist_ok=True)
    return tmp


class ConsumeImageTest(unittest.TestCase):
    def test_jewel_release_bumps_operator_and_gateway_defaults(self):
        import tempfile

        hold = tempfile.TemporaryDirectory()
        self.addCleanup(hold.cleanup)
        tree = _tree(Path(hold.name))
        values_path = tree / "charts/awx-platform-operator/values.yaml"
        controller_before = _controller_version(values_path.read_text(encoding="utf-8"))
        platform_ui_before = _pin(consume_image.PINS, "platform-ui")
        result = consume_image.apply(
            tree,
            component="jewel-with-ui",
            version="2026.10.26",
            digest=DIGEST,
            git_tag="jewel-with-ui-v2026.10.26",
            today=DAY,
        )
        self.assertFalse(result.skipped)
        self.assertEqual(result.operator_version, "2026.10.26")
        pins = (tree / consume_image.PINS).read_text(encoding="utf-8")
        self.assertEqual(
            consume_image.read_leaf(pins, ("images", "jewel-with-ui"), "tag"),
            "2026.10.26",
        )
        self.assertEqual(
            consume_image.read_leaf(pins, ("images", "jewel-with-ui"), "digest"),
            DIGEST,
        )
        self.assertEqual(
            consume_image.read_leaf(pins, ("images", "platform-ui"), "tag"),
            platform_ui_before,
        )
        self.assertEqual(
            consume_image.read_leaf(pins, ("images", "awx-operator"), "tag"),
            "2026.10.26",
        )
        gateway = (tree / "roles/gateway/defaults/main.yml").read_text(encoding="utf-8")
        self.assertIn('image_version: "2026.10.26"', gateway)
        values = (tree / "charts/awx-platform-operator/values.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn('tag: "2026.10.26"', values)
        self.assertEqual(values.count('image_version: "2026.10.26"'), 2)
        # The controller pin belongs to propose-awx-pin, not to image releases.
        self.assertEqual(_controller_version(values), controller_before)
        chart = (tree / consume_image.CHART).read_text(encoding="utf-8")
        self.assertIn("version: 2026.10.26\n", chart)
        self.assertIn('appVersion: "2026.10.26"', chart)
        self.assertTrue((tree / "release/notes/v2026.10.26.md").is_file())

        again = consume_image.apply(
            tree,
            component="jewel-with-ui",
            version="2026.10.26",
            digest=DIGEST,
            git_tag="jewel-with-ui-v2026.10.26",
            today=DAY,
        )
        self.assertTrue(again.skipped)
        self.assertEqual(again.operator_version, "2026.10.26")

    def test_platform_ui_does_not_change_gateway_image(self):
        import tempfile

        with tempfile.TemporaryDirectory() as hold:
            tree = _tree(Path(hold))
            before = (tree / "roles/gateway/defaults/main.yml").read_text(encoding="utf-8")
            jewel_before = _pin(consume_image.PINS, "jewel-with-ui")
            consume_image.apply(
                tree,
                component="platform-ui",
                version="2026.10.26",
                digest=DIGEST,
                git_tag="platform-ui-v2026.10.26",
                today=DAY,
            )
            after = (tree / "roles/gateway/defaults/main.yml").read_text(encoding="utf-8")
            self.assertEqual(before, after)
            pins = (tree / consume_image.PINS).read_text(encoding="utf-8")
            self.assertEqual(
                consume_image.read_leaf(pins, ("images", "platform-ui"), "tag"),
                "2026.10.26",
            )
            self.assertEqual(
                consume_image.read_leaf(pins, ("images", "jewel-with-ui"), "tag"),
                jewel_before,
            )

    def test_awx_build_switches_off_upstream_devel(self):
        import tempfile

        with tempfile.TemporaryDirectory() as hold:
            tree = _tree(Path(hold))
            consume_image.apply(
                tree,
                component="awx",
                version="2026.10.26-1",
                digest=DIGEST,
                git_tag="awx-v2026.10.26-1",
                today=DAY,
            )
            pins = (tree / consume_image.PINS).read_text(encoding="utf-8")
            self.assertEqual(
                consume_image.read_leaf(pins, ("images", "awx"), "repository"),
                consume_image.OUR_AWX_IMAGE,
            )
            self.assertEqual(
                consume_image.read_leaf(pins, ("images", "awx"), "tag"),
                "2026.10.26-1",
            )
            values = (tree / "charts/awx-platform-operator/values.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn(f"image: {consume_image.OUR_AWX_IMAGE}", values)
            self.assertNotIn(f"image: {consume_image.UPSTREAM_AWX_IMAGE}\n", values)
            kind = (tree / consume_image.KIND_CONTROLLER).read_text(encoding="utf-8")
            self.assertIn(f"image: {consume_image.OUR_AWX_IMAGE}:2026.10.26-1", kind)
            self.assertNotIn("ghcr.io/ansible/awx:devel", kind)

    def test_same_day_operator_micro(self):
        import tempfile

        with tempfile.TemporaryDirectory() as hold:
            tree = _tree(Path(hold))
            consume_image.apply(
                tree,
                component="platform-ui",
                version="2026.10.26",
                digest=DIGEST,
                git_tag="platform-ui-v2026.10.26",
                today=DAY,
            )
            second = "sha256:" + "cd" * 32
            result = consume_image.apply(
                tree,
                component="jewel-with-ui",
                version="2026.10.26",
                digest=second,
                git_tag="jewel-with-ui-v2026.10.26",
                today=DAY,
            )
            self.assertEqual(result.operator_version, "2026.10.26-1")

    def test_notes_include_awx_upstream_commits(self):
        import tempfile

        with tempfile.TemporaryDirectory() as hold:
            tree = _tree(Path(hold))
            proposal = tree / "release" / "notes" / "PROPOSED-awx.md"
            proposal.write_text(
                "# Proposed AWX controller pin\n\nReview before merge.\n\n"
                "## Upstream changes\n\n"
                "### `awx` (`devel`)\n\n"
                "- [`abcdefabcdef`](https://github.com/ansible/awx/commit/abcdef) 2026-10-27 fixed the scheduler\n",
                encoding="utf-8",
            )
            consume_image.apply(
                tree,
                component="platform-ui",
                version="2026.10.26",
                digest=DIGEST,
                git_tag="platform-ui-v2026.10.26",
                today=DAY,
            )
            notes = (tree / "release/notes/v2026.10.26.md").read_text(encoding="utf-8")
            self.assertIn("## Upstream AWX", notes)
            self.assertIn("fixed the scheduler", notes)
            self.assertNotIn("Review before merge", notes)

    def test_awx_build_replaces_a_digest_pin(self):
        import tempfile

        with tempfile.TemporaryDirectory() as hold:
            tree = _tree(Path(hold))
            kind = tree / consume_image.KIND_CONTROLLER
            pinned = "sha256:" + "ef" * 32
            kind.write_text(
                kind.read_text(encoding="utf-8").replace(
                    "ghcr.io/ansible/awx:devel",
                    f"ghcr.io/ansible/awx@{pinned}",
                ),
                encoding="utf-8",
            )
            consume_image.apply(
                tree,
                component="awx",
                version="2026.10.26",
                digest=DIGEST,
                git_tag="awx-v2026.10.26",
                today=DAY,
            )
            text = kind.read_text(encoding="utf-8")
            self.assertIn(f"image: {consume_image.OUR_AWX_IMAGE}:2026.10.26", text)
            self.assertNotIn(pinned, text)

    def test_notes_list_operator_commits_since_the_last_tag(self):
        import subprocess
        import tempfile

        def git(*args):
            subprocess.run(["git", "-C", hold, *args], check=True, capture_output=True)

        with tempfile.TemporaryDirectory() as hold:
            git("init", "-q")
            git("config", "user.email", "test@example.com")
            git("config", "user.name", "test")
            git("commit", "-q", "--allow-empty", "-m", "release: v0.1.13")
            git("tag", "v0.1.13")
            git("commit", "-q", "--allow-empty", "-m", "fix: rebuild ansible-operator")
            changes = consume_image.operator_changes(Path(hold))
            self.assertIn("Commits since `v0.1.13`", changes)
            self.assertIn("fix: rebuild ansible-operator", changes)
            self.assertNotIn("release: v0.1.13", changes)

            git("tag", "v2026.10.29")
            self.assertEqual(
                consume_image.operator_changes(Path(hold)), "No operator code changes."
            )

    def test_rejects_bad_digest(self):
        import tempfile

        with tempfile.TemporaryDirectory() as hold:
            tree = _tree(Path(hold))
            with self.assertRaises(ValueError):
                consume_image.apply(
                    tree,
                    component="platform-ui",
                    version="2026.10.26",
                    digest="latest",
                    git_tag="platform-ui-v2026.10.26",
                    today=DAY,
                )


if __name__ == "__main__":
    unittest.main()
