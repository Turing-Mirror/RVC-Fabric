# -*- coding: utf-8 -*-
"""Unit tests for download skip / min-size helpers (no network)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dl():
    path = ROOT / "tools" / "download_models.py"
    spec = importlib.util.spec_from_file_location("tm_download_models", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Avoid executing network-heavy imports side effects beyond requests import
    spec.loader.exec_module(mod)
    return mod


class MinSizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dl = _load_dl()

    def test_incomplete_small_file_not_complete(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "hubert_base.pt"
            p.write_bytes(b"tiny")
            self.assertFalse(self.dl._is_complete(p, "hubert_base.pt"))

    def test_large_enough_is_complete(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "hubert_base.pt"
            p.write_bytes(b"x" * 1_000_001)
            self.assertTrue(self.dl._is_complete(p, "hubert_base.pt"))

    def test_min_size_map(self):
        self.assertGreaterEqual(self.dl._min_size("hubert_base.pt"), 1_000_000)
        self.assertGreaterEqual(self.dl._min_size("rmvpe.pt"), 1_000_000)
        self.assertGreaterEqual(self.dl._min_size("rmvpe.onnx"), 100_000)


if __name__ == "__main__":
    unittest.main()
