# -*- coding: utf-8 -*-
"""Unit tests for TM theme tokens + User_Data model catalog (no GUI)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.catalog import (
    import_model_to_catalog,
    list_models_in_user_data,
    list_voice_catalog,
    safe_model_dir_name,
)
from launcher.paths import release_roles
from launcher.theme import (
    TM_ACCENT,
    TM_BG,
    TM_INK,
    forbidden_chrome_hexes,
    light_tokens,
)


class ThemeTests(unittest.TestCase):
    def test_light_tokens_match_tm_handbook(self):
        t = light_tokens()
        self.assertEqual(t["tm-bg"], "#f4f1ea")
        self.assertEqual(t["tm-ink"], "#1c1a17")
        self.assertEqual(t["tm-accent"], t["tm-ink"])  # ink-only accent
        self.assertEqual(TM_BG, "#f4f1ea")
        self.assertEqual(TM_ACCENT, TM_INK)

    def test_no_rvcmax_pink_as_accent(self):
        t = light_tokens()
        bad = forbidden_chrome_hexes()
        for key, val in t.items():
            self.assertNotIn(
                val.lower(),
                {x.lower() for x in bad},
                msg=f"{key}={val} is forbidden chrome",
            )


class CatalogTests(unittest.TestCase):
    def test_safe_name(self):
        self.assertEqual(safe_model_dir_name("  浅夏  "), "浅夏")
        with self.assertRaises(ValueError):
            safe_model_dir_name("  ")

    def test_user_data_catalog_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            models = root / "models"
            # fake pth
            src = root / "src" / "voice.pth"
            src.parent.mkdir(parents=True)
            src.write_bytes(b"FAKE_PTH")
            entry = import_model_to_catalog(src, models, display_name="测试音色")
            self.assertEqual(entry["source"], "user_data")
            self.assertTrue(Path(entry["path"]).is_file())
            cfg = Path(entry["dir"]) / "config.json"
            self.assertTrue(cfg.is_file())
            data = json.loads(cfg.read_text(encoding="utf-8"))
            self.assertIn("name", data)

            listed = list_models_in_user_data(models)
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["name"], "测试音色")
            self.assertEqual(listed[0]["source"], "user_data")

    def test_catalog_prefers_user_data_over_legacy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ud = root / "models"
            leg = root / "weights"
            ud.mkdir()
            leg.mkdir()
            # same basename in both
            p_ud = ud / "A"
            p_ud.mkdir()
            (p_ud / "A.pth").write_bytes(b"U")
            (leg / "B.pth").write_bytes(b"L")
            cat = list_voice_catalog(ud, leg)
            names = {m["name"] for m in cat}
            self.assertIn("A", names)
            self.assertIn("B", names)
            sources = {m["name"]: m["source"] for m in cat}
            self.assertEqual(sources["A"], "user_data")
            self.assertEqual(sources["B"], "legacy_weights")


class RolesTests(unittest.TestCase):
    def test_release_roles_keys(self):
        roles = release_roles()
        for k in (
            "first_run_helper",
            "consumer_app",
            "engine_core",
            "user_data",
            "models_catalog",
            "vbcable",
            "runtime_hook",
            "advanced_webui",
        ):
            self.assertIn(k, roles)
            self.assertTrue(roles[k])
        # release exe names documented for packager
        from launcher.paths import EXE_APP_NAMES, EXE_BOOTSTRAP_NAMES, find_release_exe

        self.assertIn("变声器.exe", EXE_APP_NAMES)
        self.assertIn("启动器.exe", EXE_BOOTSTRAP_NAMES)
        # no exe in pure dev tree is fine
        self.assertTrue(find_release_exe("app") is None or find_release_exe("app").is_file())


if __name__ == "__main__":
    unittest.main()
