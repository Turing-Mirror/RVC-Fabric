# -*- coding: utf-8 -*-
"""Unit tests for Setup / CNB Runtime provision (no network download)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.cnb_sources import (
    DEFAULT_RUNTIME_RELEASE_TAG,
    cnb_lfs_url,
    cnb_release_download_url,
    format_size,
    parse_runtime_spec,
    resolve_runtime_spec,
)
from launcher.runtime_provision import runtime_python, runtime_ready
from launcher._setup_shell import _is_shell_tree, copy_shell_tree


class CnbUrlBuildTests(unittest.TestCase):
    def test_release_url(self):
        u = cnb_release_download_url("RVC-runtime", "runtime-nvidia-2026.07.21.tar")
        self.assertIn("/-/releases/download/RVC-runtime/", u)
        self.assertTrue(u.endswith("runtime-nvidia-2026.07.21.tar"))

    def test_lfs_url(self):
        oid = "d76ac4e8140490bda1abac8df2718bfec95f8a696c8a5ba730a5e7e901421d9b"
        u = cnb_lfs_url(oid)
        self.assertEqual(
            u,
            "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/lfs/" + oid,
        )

    def test_format_size(self):
        self.assertIn("GB", format_size(6_000_000_000))
        self.assertIn("MB", format_size(50_000_000))


class RuntimeSpecTests(unittest.TestCase):
    def test_nvidia_uses_release_only(self):
        spec = parse_runtime_spec("nvidia", None)
        self.assertEqual(spec.variant, "nvidia")
        self.assertEqual(spec.channel, "release")
        part = spec.primary
        self.assertEqual(len(part.sha256), 64)
        self.assertTrue(part.urls)
        self.assertIn("/-/releases/download/RVC-runtime/runtime-nvidia-", part.urls[0])
        self.assertNotIn("/-/lfs/", part.urls[0])

    def test_amd_uses_lfs_only(self):
        spec = parse_runtime_spec("amd", None)
        self.assertEqual(spec.channel, "lfs")
        part = spec.primary
        self.assertEqual(
            part.urls[0],
            "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/lfs/"
            "5d5e4437c70ac1cf368232829381170d5a88f457eed20d14d35b1ef155dd0274",
        )
        self.assertFalse(any("/-/releases/download/" in u for u in part.urls))
        self.assertTrue(any("runtime/amd/" in u for u in part.sha256_urls))

    def test_nvidia50_uses_release(self):
        spec = parse_runtime_spec("nvidia50", None)
        self.assertIn(
            "runtime-nvidia50-2026.07.21.tar",
            spec.primary.urls[0],
        )
        self.assertIn("/-/releases/download/", spec.primary.urls[0])

    def test_catalog_override_urls(self):
        data = {
            "runtimes": {
                "amd": {
                    "variant": "amd",
                    "channel": "lfs",
                    "label": "AMD test",
                    "version": "1.0",
                    "size_bytes": 100,
                    "parts": [
                        {
                            "name": "runtime-amd-1.0.tar",
                            "sha256": "a" * 64,
                            "size_bytes": 100,
                            "urls": [
                                "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/lfs/"
                                + "a" * 64
                            ],
                        }
                    ],
                }
            },
        }
        spec = parse_runtime_spec("amd", data)
        self.assertEqual(spec.label, "AMD test")
        self.assertIn("/-/lfs/", spec.primary.urls[0])
        self.assertNotIn("/-/releases/download/", spec.primary.urls[0])

    def test_resolve_bundled_no_network(self):
        with mock.patch(
            "launcher.cnb_sources.fetch_remote_catalog",
            side_effect=RuntimeError("offline"),
        ):
            spec = resolve_runtime_spec("nvidia50", prefer_remote=True)
        self.assertEqual(spec.variant, "nvidia50")
        self.assertTrue(spec.primary.sha256)


class RuntimeReadyTests(unittest.TestCase):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertFalse(runtime_ready(root))
            self.assertIsNone(runtime_python(root))

    def test_present(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            py = root / "Runtime" / "python.exe"
            py.parent.mkdir(parents=True)
            py.write_bytes(b"MZ")
            (root / "Runtime" / "Lib" / "site-packages" / "torch").mkdir(parents=True)
            self.assertTrue(runtime_ready(root))


class ShellCopyTests(unittest.TestCase):
    def test_is_shell_tree(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertFalse(_is_shell_tree(root))
            (root / "launcher").mkdir()
            (root / "gui_v1.py").write_text("#", encoding="utf-8")
            self.assertTrue(_is_shell_tree(root))

    def test_copy_shell_skips_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            dst = Path(td) / "dst"
            (src / "launcher").mkdir(parents=True)
            (src / "launcher" / "x.py").write_text("print(1)\n", encoding="utf-8")
            (src / "gui_v1.py").write_text("#g\n", encoding="utf-8")
            (src / "Runtime" / "python.exe").parent.mkdir(parents=True)
            (src / "Runtime" / "python.exe").write_bytes(b"MZ")
            copy_shell_tree(src, dst)
            self.assertTrue((dst / "launcher" / "x.py").is_file())
            self.assertTrue((dst / "gui_v1.py").is_file())
            self.assertFalse((dst / "Runtime").exists())


if __name__ == "__main__":
    unittest.main()
