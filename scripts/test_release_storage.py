"""R2 publication tests use mocked HTTP and Wrangler; no remote writes."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_storage as storage


class R2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.installer = Path(self.temp.name) / "Setup-1.2.3.exe"
        self.installer.write_bytes(b"signed installer")
        self.sha = hashlib.sha256(self.installer.read_bytes()).hexdigest()
        self.size = self.installer.stat().st_size
        self.publisher = storage.R2Publisher("product", "Setup-", "Setup.exe")
        self.keys = ["product/Setup-1.0.0.exe", "product/Setup-1.2.3.exe",
                     "product/Setup.exe", "other/Setup-1.0.0.exe",
                     "product/runtime.zip", "product/nested/Setup-1.0.0.exe",
                     "product/Setup-1.0.0.exe.sha256"]

    def publish(self):
        self.publisher.publish(self.installer, "1.2.3", self.sha, self.size)

    def test_uploads_verify_both_names_before_scoped_cleanup(self):
        events = []
        def download(url):
            events.append(("get", url))
            return None if sum(e == ("get", url) for e in events) == 1 else (self.sha, self.size)
        with patch.object(self.publisher, "list_keys", return_value=self.keys), \
             patch.object(self.publisher, "wrangler", side_effect=lambda *args: events.append(args)), \
             patch.object(storage, "download_identity", side_effect=download):
            self.publish()
        puts = [e for e in events if e[:3] == ("r2", "object", "put")]
        deletes = [e for e in events if e[:3] == ("r2", "object", "delete")]
        self.assertEqual(len(puts), 2)
        self.assertEqual(deletes, [("r2", "object", "delete", "trm-releases/product/Setup-1.0.0.exe", "--remote")])
        self.assertEqual(events[-1], deletes[0])
        self.assertIn("--remote", puts[0])

    def test_size_mismatch_stops_before_fixed_upload_and_cleanup(self):
        with patch.object(self.publisher, "list_keys", return_value=self.keys), \
             patch.object(self.publisher, "wrangler") as wrangler, \
             patch.object(storage, "download_identity", side_effect=[None, (self.sha, self.size + 1)]):
            with self.assertRaisesRegex(ValueError, "hash or size"):
                self.publish()
        self.assertEqual(wrangler.call_count, 1)
        self.assertEqual(wrangler.call_args.args[2], "put")

    def test_matching_existing_installer_is_idempotent(self):
        with patch.object(self.publisher, "list_keys", return_value=[]), \
             patch.object(self.publisher, "wrangler") as wrangler, \
             patch.object(storage, "download_identity", return_value=(self.sha, self.size)):
            self.publish()
        wrangler.assert_not_called()

    def test_different_versioned_bytes_are_not_overwritten(self):
        with patch.object(self.publisher, "list_keys", return_value=[]), \
             patch.object(self.publisher, "wrangler") as wrangler, \
             patch.object(storage, "download_identity", return_value=("f" * 64, self.size)):
            with self.assertRaisesRegex(ValueError, "different bytes"):
                self.publish()
        wrangler.assert_not_called()

    def test_newer_release_prevents_rollback(self):
        with patch.object(self.publisher, "list_keys", return_value=["product/Setup-2.0.0.exe"]), \
             patch.object(self.publisher, "wrangler") as wrangler:
            with self.assertRaisesRegex(ValueError, "newer release"):
                self.publish()
        wrangler.assert_not_called()

    def test_list_all_pages_with_product_prefix(self):
        self.publisher.headers, self.publisher.account = {}, "account"
        pages = [
            {"success": True, "result": [{"key": "product/a"}],
             "result_info": {"is_truncated": True, "cursor": "next"}},
            {"success": True, "result": [{"key": "product/b"}], "result_info": {"is_truncated": False}},
        ]
        with patch.object(storage, "urlopen", side_effect=[io.BytesIO(json.dumps(p).encode()) for p in pages]) as request:
            self.assertEqual(self.publisher.list_keys(), ["product/a", "product/b"])
        self.assertIn("prefix=product%2F", request.call_args_list[0].args[0].full_url)
        self.assertIn("cursor=next", request.call_args_list[1].args[0].full_url)

    def test_download_counts_actual_bytes_and_only_404_means_missing(self):
        with patch.object(storage, "urlopen", return_value=io.BytesIO(b"abc")):
            self.assertEqual(storage.download_identity("https://example.test/a"), (hashlib.sha256(b"abc").hexdigest(), 3))
        for status in (404, 403):
            with patch.object(storage, "urlopen", side_effect=HTTPError("url", status, "", {}, None)):
                if status == 404:
                    self.assertIsNone(storage.download_identity("https://example.test/a"))
                else:
                    with self.assertRaises(HTTPError):
                        storage.download_identity("https://example.test/a")


class ModelScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.installer = Path(self.temp.name) / "Setup-1.2.3.exe"
        self.installer.write_bytes(b"signed installer")
        self.sha = hashlib.sha256(self.installer.read_bytes()).hexdigest()
        self.size = self.installer.stat().st_size
        self.mirror = storage.ModelScopeMirror("owner/repo", "fabric/setup")
        self.url = "https://modelscope.cn/models/owner/repo/resolve/c1/fabric/setup/Setup-1.2.3.exe"

    def entry(self, **change):
        return {"Type": "blob", "Path": "fabric/setup/Setup-1.2.3.exe", "Revision": "c1",
                "Sha256": self.sha, "Size": self.size, **change}

    def publish(self):
        return self.mirror.publish(self.installer, "1.2.3", self.sha, self.size)

    def test_existing_copy_is_reused_without_upload(self):
        with patch.object(self.mirror, "listing", return_value=[self.entry()]), \
             patch.object(storage.subprocess, "run") as run:
            self.assertEqual(self.publish(), self.url)
        run.assert_not_called()

    def test_mismatched_or_unpinned_entries_are_ignored(self):
        for change in ({"Sha256": "0" * 64}, {"Size": self.size + 1}, {"Revision": ""},
                       {"Path": "fabric/setup/Other.exe"}):
            with patch.object(self.mirror, "listing", return_value=[self.entry(**change)]):
                self.assertIsNone(self.mirror.find(self.installer.name, self.sha, self.size))

    def test_upload_then_verify_bytes(self):
        listings = iter([[], [], [self.entry()]])
        with patch.object(self.mirror, "listing", side_effect=lambda: next(listings)), \
             patch.object(storage.shutil, "which", return_value="ms-hub"), \
             patch.object(storage.subprocess, "run") as run, \
             patch.object(storage.time, "sleep"), \
             patch.object(storage, "download_identity", return_value=(self.sha, self.size)):
            self.assertEqual(self.publish(), self.url)
        args = run.call_args.args[0]
        self.assertEqual(args[:4], ["ms-hub", "upload", "owner/repo", str(self.installer)])
        self.assertEqual(args[4], "fabric/setup/Setup-1.2.3.exe")

    def test_wrong_bytes_after_upload_fail(self):
        with patch.object(self.mirror, "listing", side_effect=[[], [self.entry()]]), \
             patch.object(storage.shutil, "which", return_value="ms-hub"), \
             patch.object(storage.subprocess, "run"), \
             patch.object(storage, "download_identity", return_value=("0" * 64, self.size)):
            with self.assertRaises(ValueError):
                self.publish()


if __name__ == "__main__":
    unittest.main()
