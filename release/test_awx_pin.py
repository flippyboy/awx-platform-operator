import shutil
import unittest
from pathlib import Path

import awx_pin
import consume_image

ROOT = Path(__file__).resolve().parents[1]
COMMIT_A = "a" * 40
COMMIT_B = "b" * 40
COMMIT_C = "c" * 40
DIGEST = "sha256:" + "ab" * 32
DIGEST_B = "sha256:" + "cd" * 32
WHEN = "2026-10-27T12:00:00Z"

COPIES = (
    "release/pins.consumer.yaml",
    "roles/platform/defaults/main.yml",
    "charts/awx-platform-operator/values.yaml",
    "charts/awx-platform-operator/examples/platform-kind.yaml",
    "hack/kind/samples/awx-controller.yaml",
    "hack/kind/controller-smoke/controller.yaml",
    "playbooks/reconcile-controller-standalone.yml",
    "config/samples/awx_v1beta1_awxplatform.yaml",
)


def _commit(sha: str, subject: str, day: str) -> dict:
    return {
        "sha": sha,
        "commit": {"message": subject, "author": {"date": f"{day}T00:00:00Z"}},
    }


class FakeUpstream:
    def __init__(self, tip: str, digest: str, listing: list[dict], compare: list[dict]):
        self.tip = tip
        self.digest = digest
        self.listing = listing
        self.compare = compare
        self.urls: list[str] = []
        self.image_tags: list[str] = []

    def github_api(self, url: str, token):
        self.urls.append(url)
        if "/compare/" in url:
            return {"total_commits": len(self.compare), "commits": self.compare}
        if "/commits?" in url:
            return self.listing
        if url.rstrip("/").endswith("/commits/devel"):
            return {"sha": self.tip}
        raise RuntimeError(f"unexpected {url}")

    def manifest_digest(self, image: str, tag: str) -> str:
        self.image_tags.append(f"{image}:{tag}")
        if image != awx_pin.UPSTREAM_IMAGE or tag != "devel":
            raise RuntimeError(f"refused {image}:{tag}")
        return self.digest


def _tree(tmp: Path) -> Path:
    for relative in COPIES:
        destination = tmp / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / relative, destination)
    (tmp / "release" / "notes").mkdir(parents=True, exist_ok=True)
    return tmp


class AwxPinTest(unittest.TestCase):
    def test_tracking_skips_semver(self):
        self.assertNotIn("24.6.1", awx_pin.tracking_ref_candidates("24.6.1"))
        self.assertEqual(awx_pin.tracking_ref_candidates("24.6.1")[0], "devel")
        self.assertFalse(awx_pin.is_release_tag("devel"))
        self.assertTrue(awx_pin.is_release_tag("24.6.1"))
        self.assertTrue(awx_pin.is_release_tag("v2.4.0"))

    def _propose(self, tree: Path, fake: FakeUpstream):
        return awx_pin.propose(
            tree,
            token=None,
            now=WHEN,
            github_api_fn=fake.github_api,
            manifest_digest_fn=fake.manifest_digest,
        )

    def test_first_pin_lists_latest_commits_and_leaves_other_images(self):
        import tempfile

        fake = FakeUpstream(
            COMMIT_A,
            DIGEST,
            listing=[
                _commit(COMMIT_A, "newer subject", "2026-10-27"),
                _commit(COMMIT_C, "older subject", "2026-10-20"),
            ],
            compare=[],
        )
        with tempfile.TemporaryDirectory() as hold:
            tree = _tree(Path(hold))
            result = self._propose(tree, fake)
            self.assertTrue(result.changed)
            self.assertEqual(fake.image_tags, [f"{awx_pin.UPSTREAM_IMAGE}:devel"])
            self.assertFalse(any("/compare/" in url for url in fake.urls))
            pins = (tree / awx_pin.PINS).read_text(encoding="utf-8")
            self.assertEqual(consume_image.read_leaf(pins, ("images", "awx"), "digest"), DIGEST)
            self.assertEqual(consume_image.read_leaf(pins, ("images", "awx"), "git_commit"), COMMIT_A)
            self.assertEqual(consume_image.read_leaf(pins, ("images", "awx"), "git_ref"), "devel")
            self.assertEqual(consume_image.read_leaf(pins, ("images", "awx"), "tag"), "devel")
            self.assertEqual(consume_image.read_leaf(pins, ("images", "awx"), "repository"), awx_pin.UPSTREAM_IMAGE)
            self.assertEqual(consume_image.read_leaf(pins, ("images", "jewel-with-ui"), "tag"), "0.1.2")
            self.assertEqual(consume_image.read_leaf(pins, ("images", "platform-ui"), "tag"), "0.1.2")
            self.assertEqual(consume_image.read_leaf(pins, ("images", "awx-operator"), "tag"), "0.1.13")
            self.assertEqual(consume_image.read_leaf(pins, ("source_releases",), "awx"), "")

            values = (tree / "charts/awx-platform-operator/values.yaml").read_text(encoding="utf-8")
            self.assertIn(f'image_version: "{DIGEST}"', values)
            self.assertNotIn("image_version: devel", values)
            self.assertIn('image_version: "0.1.2"', values)
            self.assertIn('tag: "0.1.13"', values)
            self.assertIn(f"image: {awx_pin.UPSTREAM_IMAGE}\n", values)
            self.assertNotIn(f"image: {consume_image.OUR_AWX_IMAGE}\n", values)

            sample = (tree / awx_pin.PLATFORM_SAMPLE).read_text(encoding="utf-8")
            self.assertIn(f'image_version: "{DIGEST}"', sample)
            self.assertIn("image_version: latest", sample)
            kind = (tree / awx_pin.KIND_CONTROLLER).read_text(encoding="utf-8")
            self.assertIn(f"image: {awx_pin.UPSTREAM_IMAGE}@{DIGEST}", kind)
            self.assertNotIn("ghcr.io/ansible/awx:devel", kind)
            for relative in (
                "roles/platform/defaults/main.yml",
                "playbooks/reconcile-controller-standalone.yml",
                "hack/kind/samples/awx-controller.yaml",
                "charts/awx-platform-operator/examples/platform-kind.yaml",
            ):
                text = (tree / relative).read_text(encoding="utf-8")
                self.assertIn(f'image_version: "{DIGEST}"', text, relative)
                self.assertNotIn("image_version: devel", text, relative)

            notes = (tree / awx_pin.NOTES).read_text(encoding="utf-8")
            self.assertIn("No previous commit", notes)
            self.assertIn("older subject", notes)
            self.assertIn("newer subject", notes)
            self.assertLess(notes.index("older subject"), notes.index("newer subject"))
            self.assertIn("does not tag an operator release", notes)
            self.assertIn("## Upstream changes", notes)
            self.assertIn(DIGEST, notes)
            self.assertNotIn("/compare/", notes)

            again = self._propose(tree, fake)
            self.assertFalse(again.changed)
            self.assertEqual((tree / awx_pin.NOTES).read_text(encoding="utf-8"), notes)

    def test_moved_pin_replaces_digest_and_links_compare(self):
        import tempfile

        fake = FakeUpstream(
            COMMIT_A,
            DIGEST,
            listing=[_commit(COMMIT_A, "first", "2026-10-27")],
            compare=[],
        )
        with tempfile.TemporaryDirectory() as hold:
            tree = _tree(Path(hold))
            self._propose(tree, fake)
            fake.tip = COMMIT_B
            fake.digest = DIGEST_B
            fake.compare = [_commit(COMMIT_B, "fixed the scheduler", "2026-10-28")]
            fake.urls.clear()
            result = self._propose(tree, fake)
            self.assertTrue(result.changed)
            self.assertTrue(any("/compare/" in url for url in fake.urls))
            pins = (tree / awx_pin.PINS).read_text(encoding="utf-8")
            self.assertEqual(consume_image.read_leaf(pins, ("images", "awx"), "git_commit"), COMMIT_B)
            self.assertEqual(consume_image.read_leaf(pins, ("images", "awx"), "digest"), DIGEST_B)
            kind = (tree / awx_pin.KIND_CONTROLLER).read_text(encoding="utf-8")
            self.assertIn(f"@{DIGEST_B}", kind)
            self.assertNotIn(DIGEST, kind)
            notes = (tree / awx_pin.NOTES).read_text(encoding="utf-8")
            self.assertIn("fixed the scheduler", notes)
            self.assertIn(f"https://github.com/ansible/awx/compare/{COMMIT_A}...{COMMIT_B}", notes)
            self.assertIn(f"`{COMMIT_A[:12]}` → `{COMMIT_B[:12]}`", notes)
            self.assertNotIn("No previous commit", notes)

    def test_repairs_defaults_when_the_pin_file_already_matches(self):
        import tempfile

        fake = FakeUpstream(
            COMMIT_A,
            DIGEST,
            listing=[_commit(COMMIT_A, "first", "2026-10-27")],
            compare=[],
        )
        with tempfile.TemporaryDirectory() as hold:
            tree = _tree(Path(hold))
            self._propose(tree, fake)
            kind = tree / awx_pin.KIND_CONTROLLER
            kind.write_text(
                kind.read_text(encoding="utf-8").replace(
                    f"{awx_pin.UPSTREAM_IMAGE}@{DIGEST}",
                    f"{awx_pin.UPSTREAM_IMAGE}:devel",
                ),
                encoding="utf-8",
            )
            result = self._propose(tree, fake)
            self.assertTrue(result.changed)
            self.assertIn(
                f"image: {awx_pin.UPSTREAM_IMAGE}@{DIGEST}",
                kind.read_text(encoding="utf-8"),
            )

    def test_refuses_a_rebuilt_awx_image(self):
        import tempfile

        fake = FakeUpstream(COMMIT_A, DIGEST, listing=[], compare=[])
        with tempfile.TemporaryDirectory() as hold:
            tree = _tree(Path(hold))
            pins_path = tree / awx_pin.PINS
            pins_path.write_text(
                consume_image.set_leaf(
                    pins_path.read_text(encoding="utf-8"),
                    ("images", "awx"),
                    "repository",
                    consume_image.OUR_AWX_IMAGE,
                ),
                encoding="utf-8",
            )
            before = (tree / "roles/platform/defaults/main.yml").read_text(encoding="utf-8")
            with self.assertRaises(RuntimeError):
                self._propose(tree, fake)
            self.assertEqual(fake.urls, [])
            self.assertEqual(
                (tree / "roles/platform/defaults/main.yml").read_text(encoding="utf-8"),
                before,
            )

    def test_configured_semver_ref_still_tracks_devel(self):
        import tempfile

        fake = FakeUpstream(
            COMMIT_A,
            DIGEST,
            listing=[_commit(COMMIT_A, "from devel", "2026-10-27")],
            compare=[],
        )
        with tempfile.TemporaryDirectory() as hold:
            tree = _tree(Path(hold))
            pins_path = tree / awx_pin.PINS
            pins_path.write_text(
                consume_image.set_leaf(
                    pins_path.read_text(encoding="utf-8"),
                    ("images", "awx"),
                    "git_ref",
                    "24.6.1",
                ),
                encoding="utf-8",
            )
            self._propose(tree, fake)
            pins = pins_path.read_text(encoding="utf-8")
            self.assertEqual(consume_image.read_leaf(pins, ("images", "awx"), "git_ref"), "devel")
            self.assertFalse(any("24.6.1" in url for url in fake.urls))
            notes = (tree / awx_pin.NOTES).read_text(encoding="utf-8")
            self.assertIn("from devel", notes)


if __name__ == "__main__":
    unittest.main()
