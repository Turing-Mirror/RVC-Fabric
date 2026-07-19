# -*- coding: utf-8 -*-
"""Unit tests for online catalog / packages (no network)."""

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

from launcher.online.catalog import OnlineCatalog, compare_versions, load_bundled_catalog
from launcher.online.downloader import is_github_url, normalize_github_url
from launcher.online.gui_update import apply_gui_patch_zip, check_gui_update
from launcher.online.package_spec import (
    PKG_FULL,
    PKG_GUI_PATCH,
    PKG_VOICE_PACK,
    detect_zip_package_type,
    normalize_package_type,
)
from launcher.online.voice_install import install_voice_pack_zip


class VersionTests(unittest.TestCase):
    def test_compare(self):
        self.assertEqual(compare_versions("1.0.0", "1.0.1"), -1)
        self.assertEqual(compare_versions("1.1.0", "1.0.9"), 1)
        self.assertEqual(compare_versions("1.1.0", "1.1.0"), 0)


class CatalogTests(unittest.TestCase):
    def test_bundled_loads(self):
        cat = load_bundled_catalog()
        self.assertIsInstance(cat, OnlineCatalog)

    def test_from_dict_voices_pack_or_pth(self):
        data = {
            "schema": 1,
            "app": {
                "version": "2.0.0",
                "gui": {
                    "package_type": "gui_patch",
                    "version": "2.0.0",
                    "url": "https://x/a.zip",
                },
            },
            "voices": [
                {"id": "a", "name": "A", "pack_url": "https://x/a.zip"},
                {"id": "b", "name": "B", "pth_url": "https://x/b.pth"},
                {"id": "c", "name": "C"},  # no url
            ],
        }
        cat = OnlineCatalog.from_dict(data, source="test")
        self.assertEqual(len(cat.voices), 2)
        st = check_gui_update(cat, local_version="1.0.0")
        self.assertTrue(st["available"])
        self.assertEqual(st["package_type"], PKG_GUI_PATCH)
        self.assertEqual(st["action"], "apply_patch")

    def test_full_package_action(self):
        data = {
            "app": {
                "version": "3.0.0",
                "gui": {
                    "package_type": "full_package",
                    "version": "3.0.0",
                    "url": "https://sharepoint/full",
                },
            }
        }
        cat = OnlineCatalog.from_dict(data)
        st = check_gui_update(cat, local_version="1.0.0")
        self.assertTrue(st["available"])
        self.assertEqual(st["action"], "external")
        self.assertEqual(st["package_type"], PKG_FULL)


class GithubUrlTests(unittest.TestCase):
    def test_blob_to_raw(self):
        u = normalize_github_url(
            "https://github.com/org/repo/blob/main/path/file.pth"
        )
        self.assertIn("raw.githubusercontent.com", u)

    def test_is_github(self):
        self.assertTrue(is_github_url("https://github.com/a/b"))
        self.assertFalse(is_github_url("https://example.com/x"))


class PackageDetectTests(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(normalize_package_type("incremental"), PKG_GUI_PATCH)
        self.assertEqual(normalize_package_type("full"), PKG_FULL)
        self.assertEqual(normalize_package_type("voice_zip"), PKG_VOICE_PACK)

    def test_detect_gui_and_full(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            gui_z = root / "gui.zip"
            with zipfile.ZipFile(gui_z, "w") as zf:
                zf.writestr(
                    "tm_package.json",
                    json.dumps({"package_type": "gui_patch", "version": "1"}),
                )
                zf.writestr("launcher/x.py", "print(1)\n")
            self.assertEqual(detect_zip_package_type(gui_z), PKG_GUI_PATCH)

            full_z = root / "full.zip"
            with zipfile.ZipFile(full_z, "w") as zf:
                zf.writestr("Runtime/python.exe", b"fake")
                zf.writestr("launcher/x.py", "x")
            self.assertEqual(detect_zip_package_type(full_z), PKG_FULL)

    def test_apply_patch_blocks_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            zpath = root / "p.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr(
                    "tm_package.json",
                    json.dumps({"package_type": "gui_patch", "version": "9.9.9"}),
                )
                zf.writestr("launcher/hello_test.txt", "ok")
                zf.writestr("Runtime/evil.bin", "nope")
            result = apply_gui_patch_zip(zpath, root=root)
            self.assertIn("launcher/hello_test.txt", result["written"])
            self.assertFalse((root / "Runtime" / "evil.bin").is_file())

    def test_apply_rejects_full(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            zpath = root / "full.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr(
                    "tm_package.json",
                    json.dumps({"package_type": "full_package"}),
                )
                zf.writestr("Runtime/python.exe", b"x")
            with self.assertRaises(Exception) as ctx:
                apply_gui_patch_zip(zpath, root=root)
            self.assertIn("全量", str(ctx.exception))


class VoicePackTests(unittest.TestCase):
    def test_install_voice_zip(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            models = td_path / "models"
            zpath = td_path / "v.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr(
                    "tm_package.json",
                    json.dumps(
                        {
                            "package_type": "voice_pack",
                            "voice_id": "demo",
                            "name": "Demo",
                        }
                    ),
                )
                zf.writestr("demo.pth", b"x" * 60_000)
                zf.writestr("cover.png", b"\x89PNG" + b"\x00" * 600)
                zf.writestr(
                    "config.json",
                    json.dumps({"name": "DemoVoice", "tag": "测试"}),
                )
            info = install_voice_pack_zip(
                zpath, voice_id="demo", models_root=models
            )
            self.assertTrue(Path(info["path"]).is_file())
            self.assertTrue((models / "demo" / "config.json").is_file())
            cfg = json.loads((models / "demo" / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(cfg["name"], "DemoVoice")


if __name__ == "__main__":
    unittest.main()
