# -*- coding: utf-8 -*-
"""Unit tests for package_meta (no GPU)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from package_meta import (
    VARIANT_DEFAULTS,
    default_accel_for_package,
    load_package_meta,
    write_package_meta,
)


class PackageMetaTests(unittest.TestCase):
    def test_variant_defaults_official_matrix(self):
        self.assertEqual(VARIANT_DEFAULTS["nvidia"]["accel_default"], "cuda")
        self.assertFalse(VARIANT_DEFAULTS["nvidia"]["use_dml"])
        self.assertEqual(VARIANT_DEFAULTS["amd"]["accel_default"], "dml")
        self.assertTrue(VARIANT_DEFAULTS["amd"]["use_dml"])
        self.assertEqual(VARIANT_DEFAULTS["nvidia50"]["accel_default"], "cuda")
        self.assertFalse(VARIANT_DEFAULTS["nvidia50"]["use_dml"])

    def test_write_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = write_package_meta(root, "amd", label="AMD/Intel DirectML")
            self.assertTrue(path.is_file())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["variant"], "amd")
            self.assertEqual(data["accel_default"], "dml")
            loaded = load_package_meta(root)
            self.assertTrue(loaded.get("tagged"))
            self.assertEqual(loaded["variant"], "amd")
            self.assertEqual(default_accel_for_package(root), "dml")

    def test_missing_meta_defaults_nvidia(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            meta = load_package_meta(root)
            self.assertFalse(meta.get("tagged"))
            self.assertEqual(meta["variant"], "nvidia")
            self.assertEqual(default_accel_for_package(root), "cuda")

    def test_nvidia50_meta(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_package_meta(root, "nvidia50")
            self.assertEqual(default_accel_for_package(root), "cuda")
            self.assertEqual(load_package_meta(root)["variant"], "nvidia50")


if __name__ == "__main__":
    unittest.main()
