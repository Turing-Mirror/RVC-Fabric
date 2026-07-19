# -*- coding: utf-8 -*-
"""Unit tests for online catalog / version / zip apply (no network)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.online.catalog import (
    OnlineCatalog,
    VoiceEntry,
    compare_versions,
    load_bundled_catalog,
)
from launcher.online.downloader import is_github_url, normalize_github_url
from launcher.online.gui_update import apply_gui_zip, check_gui_update
from launcher.version import APP_VERSION


class VersionTests(unittest.TestCase):
    def test_compare(self):
        self.assertEqual(compare_versions("1.0.0", "1.0.1"), -1)
        self.assertEqual(compare_versions("1.1.0", "1.0.9"), 1)
        self.assertEqual(compare_versions("1.1.0", "1.1.0"), 0)


class CatalogTests(unittest.TestCase):
    def test_bundled_loads(self):
        cat = load_bundled_catalog()
        self.assertIsInstance(cat, OnlineCatalog)
        self.assertTrue(cat.full_package_note)

    def test_from_dict_voices(self):
        data = {
            "schema": 1,
            "app": {"version": "2.0.0", "gui": {"version": "2.0.0", "url": "https://x/a.zip"}},
            "voices": [
                {"id": "a", "name": "A", "pth_url": "https://x/a.pth"},
                {"id": "b", "name": "B"},  # no url → skip
            ],
            "community": {"qq_group": "123", "sharepoint_full": "https://sp/x"},
        }
        cat = OnlineCatalog.from_dict(data, source="test")
        self.assertEqual(len(cat.voices), 1)
        self.assertEqual(cat.voices[0].id, "a")
        self.assertEqual(cat.qq_group, "123")
        st = check_gui_update(cat, local_version="1.0.0")
        self.assertTrue(st["available"])
        st2 = check_gui_update(cat, local_version="2.0.0")
        self.assertFalse(st2["available"])


class GithubUrlTests(unittest.TestCase):
    def test_blob_to_raw(self):
        u = normalize_github_url(
            "https://github.com/org/repo/blob/main/path/file.pth"
        )
        self.assertIn("raw.githubusercontent.com", u)
        self.assertIn("org/repo/main/path/file.pth", u)

    def test_is_github(self):
        self.assertTrue(is_github_url("https://github.com/a/b"))
        self.assertFalse(is_github_url("https://example.com/x"))


class GuiZipTests(unittest.TestCase):
    def test_apply_allowlist(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            zpath = root / "p.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("launcher/hello_test.txt", "ok")
                zf.writestr("Runtime/evil.bin", "nope")
                zf.writestr("User_Data/secrets.json", "nope")
                zf.writestr("../escape.txt", "nope")
            written = apply_gui_zip(zpath, root=root)
            self.assertEqual(written, ["launcher/hello_test.txt"])
            self.assertTrue((root / "launcher" / "hello_test.txt").is_file())
            self.assertFalse((root / "Runtime" / "evil.bin").is_file())


if __name__ == "__main__":
    unittest.main()
