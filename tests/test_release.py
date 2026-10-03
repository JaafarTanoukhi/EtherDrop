import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.prepare_release import next_version, prepare_release


class ReleaseTests(unittest.TestCase):
    def test_first_release_is_1_0_0(self):
        self.assertEqual(next_version("1.0.0", None), "1.0.0")

    def test_patch_increments_and_explicit_minor_major(self):
        self.assertEqual(next_version("1.0.5", "v1.0.5"), "1.0.6")
        self.assertEqual(next_version("1.0.0", "v1.0.9"), "1.0.10")
        self.assertEqual(next_version("1.1.0", "v1.0.5"), "1.1.0")
        self.assertEqual(next_version("2.0.0", "v1.1.5"), "2.0.0")

    def test_source_manifest_and_notes_match_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "etherdrop.py").write_text('APP_VERSION = "1.0.9"\n', encoding="utf-8")
            (root / "EtherDrop.manifest").write_text('<assemblyIdentity version="1.0.9.0" />', encoding="utf-8")
            (root / "RELEASE_NOTES.md").write_text("Previous notes\n", encoding="utf-8")
            with patch("scripts.prepare_release.git", side_effect=["v1.0.2\nv1.0.9", "Previous notes", "Improve transfer progress"]):
                self.assertEqual(prepare_release(root), "1.0.10")
            self.assertIn('APP_VERSION = "1.0.10"', (root / "etherdrop.py").read_text())
            self.assertIn('version="1.0.10.0"', (root / "EtherDrop.manifest").read_text())
            self.assertIn("Improve transfer progress", (root / "RELEASE_NOTES.md").read_text())

    def test_custom_release_notes_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "etherdrop.py").write_text('APP_VERSION = "1.1.0"\n', encoding="utf-8")
            (root / "EtherDrop.manifest").write_text('<assemblyIdentity version="1.0.0.0" />', encoding="utf-8")
            (root / "RELEASE_NOTES.md").write_text("New features for friends\n", encoding="utf-8")
            with patch("scripts.prepare_release.git", side_effect=["v1.0.0", "Previous notes"]):
                self.assertEqual(prepare_release(root), "1.1.0")
            self.assertEqual((root / "RELEASE_NOTES.md").read_text(), "New features for friends\n")
