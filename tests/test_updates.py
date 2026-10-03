import hashlib
import io
import json
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import etherdrop


class UpdateTests(unittest.TestCase):
    def setUp(self):
        version = patch.object(etherdrop, "APP_VERSION", "1.0.0")
        version.start()
        self.addCleanup(version.stop)

    def release(self, tag="v1.0.1", data=b"MZtest executable"):
        return {
            "tag_name": tag,
            "body": "Improved folder transfers.",
            "assets": [{
                "name": "EtherDrop.exe",
                "browser_download_url": "https://github.com/example/EtherDrop.exe",
                "size": len(data),
                "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
            }],
        }

    def check_release(self, release):
        with patch.object(etherdrop, "urlopen", return_value=io.BytesIO(json.dumps(release).encode())):
            return etherdrop.latest_release()

    def test_numeric_versions_and_rejected_tags(self):
        self.assertGreater(etherdrop.version_tuple("v1.10.0"), etherdrop.version_tuple("v1.9.0"))
        for value in ("v1.0", "v1.0.1-beta", "latest"):
            with self.assertRaises(ValueError):
                etherdrop.version_tuple(value)

    def test_new_release_and_no_downgrades(self):
        self.assertEqual(self.check_release(self.release())["version"], "v1.0.1")
        self.assertEqual(self.check_release(self.release("v1.0.0"))["notes"], "Improved folder transfers.")
        self.assertEqual(self.check_release(self.release("v0.9.0"))["version"], "v0.9.0")

    def test_missing_asset(self):
        with self.assertRaisesRegex(RuntimeError, "does not contain"):
            self.check_release({"tag_name": "v1.0.1", "assets": []})

    def test_no_release_and_network_errors(self):
        for status in (404, 403):
            with patch.object(etherdrop, "urlopen", side_effect=HTTPError("https://api.github.com", status, "error", {}, None)):
                if status == 404:
                    self.assertIsNone(etherdrop.latest_release())
                else:
                    with self.assertRaises(HTTPError):
                        etherdrop.latest_release()

    def test_download_and_cleanup_on_failure(self):
        data = b"MZtest executable"
        release = {"asset": self.release(data=data)["assets"][0]}
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "EtherDrop.exe"
            target.write_bytes(b"old executable")
            with patch.object(etherdrop.sys, "executable", str(target)):
                with patch.object(etherdrop, "urlopen", return_value=io.BytesIO(data)):
                    staging = etherdrop.download_update(release, queue.Queue())
                self.assertEqual((staging / "EtherDrop.exe").read_bytes(), data)
                self.assertEqual(target.read_bytes(), b"old executable")
                etherdrop.shutil.rmtree(staging)
                for bad_data in (b"MZshort", b"XXtest executable", b"MZchanged content"):
                    with patch.object(etherdrop, "urlopen", return_value=io.BytesIO(bad_data)):
                        with self.assertRaises(RuntimeError):
                            etherdrop.download_update(release, queue.Queue())
                    self.assertEqual(list(Path(folder).iterdir()), [target])

    def test_startup_and_manual_check_use_worker_queue(self):
        app = etherdrop.EtherDropApp.__new__(etherdrop.EtherDropApp)
        app.update_busy = False
        app.events = queue.Queue()
        app._set_update_busy = lambda busy, text: setattr(app, "update_busy", busy)
        with patch.object(etherdrop, "latest_release", return_value=None):
            app.check_for_updates(manual=True)
            self.assertEqual(app.events.get(timeout=2), ("update_checked", None, True))
            app.check_for_updates()
            self.assertTrue(app.events.empty())

    def test_manual_no_update_opens_current_notes_without_downgrading(self):
        app = etherdrop.EtherDropApp.__new__(etherdrop.EtherDropApp)
        app.transfer_dialog = None
        app.setup_in_progress = False
        app.release_notes_dialog = None
        app._set_update_busy = lambda *args: None
        with patch.object(app, "_show_release_notes") as show, patch.object(etherdrop, "bundled_release_notes", return_value="Installed notes"):
            app._offer_update(self.check_release(self.release("v1.0.0")), True)
            show.assert_called_with("You're up to date", "Improved folder transfers.")
            app._offer_update(self.check_release(self.release("v0.9.0")), True)
            show.assert_called_with("You're up to date", "Installed notes")
            show.reset_mock()
            app._offer_update(self.check_release(self.release("v1.0.0")), False)
            show.assert_not_called()

    def test_startup_notes_only_once_per_version_and_offline(self):
        app = etherdrop.EtherDropApp.__new__(etherdrop.EtherDropApp)
        app.transfer_dialog = None
        app.setup_in_progress = False
        app.update_state = {"seen_version": "0.9.0"}
        with patch.object(app, "_show_release_notes") as show, patch.object(etherdrop, "bundled_release_notes", return_value="Offline notes"):
            app._show_startup_notes()
            show.assert_called_once_with("EtherDrop updated", "Offline notes")
            app.update_state["seen_version"] = etherdrop.APP_VERSION
            show.reset_mock()
            app._show_startup_notes()
            show.assert_not_called()

    def test_update_state_persistence(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(etherdrop.os.environ, {"LOCALAPPDATA": folder}):
            self.assertEqual(etherdrop.load_update_state(), {})
            etherdrop.save_update_state({"seen_version": "1.0.0"})
            self.assertEqual(etherdrop.load_update_state(), {"seen_version": "1.0.0"})


if __name__ == "__main__":
    unittest.main()
