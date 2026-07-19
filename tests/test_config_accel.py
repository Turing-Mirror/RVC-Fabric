# -*- coding: utf-8 -*-
"""Unit tests: app_config accel defaults from package_meta."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.package_meta import write_package_meta
import launcher.config_store as config_store


class ConfigAccelDefaultTests(unittest.TestCase):
    def test_amd_pack_seeds_dml_when_no_config(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_package_meta(root, "amd")
            cfg_path = root / "User_Data" / "app_config.json"
            cfg_path.parent.mkdir(parents=True)

            with mock.patch.object(config_store, "CONFIG_PATH", cfg_path), mock.patch(
                "launcher.package_meta.default_accel_for_package",
                return_value="dml",
            ), mock.patch.object(config_store, "ensure_dirs", lambda: None):
                cfg = config_store.load_config()
            self.assertEqual(cfg.get("accel_backend"), "dml")

    def test_nvidia50_pack_seeds_cuda(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_package_meta(root, "nvidia50")
            cfg_path = root / "app_config.json"

            with mock.patch.object(config_store, "CONFIG_PATH", cfg_path), mock.patch(
                "launcher.package_meta.default_accel_for_package",
                return_value="cuda",
            ), mock.patch.object(config_store, "ensure_dirs", lambda: None):
                cfg = config_store.load_config()
            self.assertEqual(cfg.get("accel_backend"), "cuda")

    def test_existing_accel_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg_path = root / "app_config.json"
            cfg_path.write_text(
                '{"accel_backend": "cpu", "pitch": 1}', encoding="utf-8"
            )
            with mock.patch.object(config_store, "CONFIG_PATH", cfg_path), mock.patch(
                "launcher.package_meta.default_accel_for_package",
                return_value="dml",
            ), mock.patch.object(config_store, "ensure_dirs", lambda: None):
                cfg = config_store.load_config()
            self.assertEqual(cfg.get("accel_backend"), "cpu")


if __name__ == "__main__":
    unittest.main()
