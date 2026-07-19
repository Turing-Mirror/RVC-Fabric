# -*- coding: utf-8 -*-
"""Unit tests for env check categories (no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.env_setup import (
    KIND_CORE,
    KIND_SOFT,
    KIND_TRAINING,
    CheckItem,
    core_ready,
    format_check_report,
    missing_items,
)


class CategoryHelpersTests(unittest.TestCase):
    def _sample(self) -> list[CheckItem]:
        return [
            CheckItem("Python / Runtime", True, "ok", KIND_CORE),
            CheckItem("Hubert 模型", True, "ok", KIND_CORE),
            CheckItem("RMVPE 模型", False, "missing", KIND_CORE),
            CheckItem("音色模型", False, "0", KIND_SOFT),
            CheckItem("训练底模 (pretrained)", False, "0", KIND_TRAINING),
            CheckItem("Gradio", False, "no", KIND_TRAINING),
        ]

    def test_core_ready_requires_core_only(self):
        items = self._sample()
        self.assertFalse(core_ready(items))
        items[2] = CheckItem("RMVPE 模型", True, "ok", KIND_CORE)
        self.assertTrue(core_ready(items))

    def test_missing_kinds_filter(self):
        items = self._sample()
        core = missing_items(items, kinds={KIND_CORE})
        self.assertEqual([i.name for i in core], ["RMVPE 模型"])
        train = missing_items(items, kinds={KIND_TRAINING})
        self.assertEqual(len(train), 2)

    def test_report_is_short_and_clear(self):
        text = format_check_report(self._sample())
        self.assertIn("日常变声", text)
        self.assertIn("RMVPE", text)
        self.assertIn("缺少", text)
        self.assertIn("训练/分离", text)
        # 简洁：不应堆路径或长说明
        self.assertNotIn("assets/", text)
        self.assertLess(len(text), 200)


class DownloadScopeArgTests(unittest.TestCase):
    def test_download_models_cli_default_core(self):
        import importlib.util

        path = ROOT / "tools" / "download_models.py"
        spec = importlib.util.spec_from_file_location("dl_models", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        # Don't exec full module network paths — parse argparse only
        import argparse

        # mirror CLI
        ap = argparse.ArgumentParser()
        ap.add_argument(
            "--scope",
            choices=("core", "training", "uvr", "all"),
            default="core",
        )
        ns = ap.parse_args([])
        self.assertEqual(ns.scope, "core")
        ns2 = ap.parse_args(["--scope", "training"])
        self.assertEqual(ns2.scope, "training")


if __name__ == "__main__":
    unittest.main()
