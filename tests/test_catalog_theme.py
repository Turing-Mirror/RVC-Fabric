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
    get_model_voice_params,
    import_model_to_catalog,
    list_models_in_user_data,
    list_voice_catalog,
    safe_model_dir_name,
    save_model_voice_params,
    voice_params_from_side,
)
from launcher.paths import release_roles
from launcher.theme import (
    TM_ACCENT,
    TM_BG,
    TM_HELP,
    TM_INK,
    TM_INK_MUTED,
    TM_META,
    forbidden_chrome_hexes,
    light_tokens,
)


class ThemeTests(unittest.TestCase):
    def test_light_tokens_complete(self):
        t = light_tokens()
        for key in (
            "tm-bg",
            "tm-surface",
            "tm-ink",
            "tm-accent",
            "tm-accent-ink",
            "tm-ok",
            "tm-warn",
        ):
            self.assertIn(key, t)
            self.assertTrue(str(t[key]).startswith("#"))
        # Accent is independent (may differ from ink) but must not equal forbidden chrome
        self.assertEqual(TM_BG, t["tm-bg"])
        self.assertEqual(TM_ACCENT, t["tm-accent"])

    def test_no_forbidden_chrome_as_token(self):
        t = light_tokens()
        bad = {x.lower() for x in forbidden_chrome_hexes()}
        for key, val in t.items():
            self.assertNotIn(
                val.lower(),
                bad,
                msg=f"{key}={val} is forbidden chrome",
            )
        # Accent is now Schale's BA blue (copied per product direction); the
        # canvas must not be LyricsKara's near-black, and no teal anywhere.
        self.assertEqual(TM_ACCENT.lower(), "#1289f0")
        self.assertNotEqual(TM_BG.lower(), "#050508")
        self.assertNotIn("#2df3e0", {v.lower() for v in t.values()})

    def test_text_contrast_hierarchy(self):
        """Labels/help darker than pure meta; all darker than surface for readability."""
        self.assertIn("tm-help", light_tokens())
        self.assertEqual(TM_HELP, light_tokens()["tm-help"])
        # Simple relative darkness: lower hex ≈ darker on light UI
        def lum(h: str) -> int:
            s = h.lstrip("#")
            r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
            return r + g + b

        self.assertLess(lum(TM_INK), lum(TM_INK_MUTED))
        self.assertLessEqual(lum(TM_INK_MUTED), lum(TM_HELP))
        self.assertLessEqual(lum(TM_HELP), lum(TM_META))
        # Muted labels must not be washed-out gray (~#92968f old meta)
        self.assertLess(lum(TM_INK_MUTED), lum("#707070"))


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

    def test_per_model_voice_params_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            models = root / "models"
            src = root / "src" / "v.pth"
            src.parent.mkdir(parents=True)
            src.write_bytes(b"FAKE")
            entry = import_model_to_catalog(src, models, display_name="高音角色")
            md = Path(entry["dir"])
            save_model_voice_params(
                md,
                {
                    "pitch": 12,
                    "formant": 0.25,
                    "index_rate": 0.4,
                    "rms_mix_rate": 0.1,
                    "threhold": -45,
                    "f0method": "rmvpe",
                },
                display_name="高音角色",
            )
            got = get_model_voice_params(md)
            self.assertEqual(got["pitch"], 12)
            self.assertAlmostEqual(float(got["formant"]), 0.25)
            self.assertEqual(got["f0method"], "rmvpe")
            listed = list_models_in_user_data(models)
            self.assertEqual(listed[0]["pitch"], 12)
            # null keys ignored
            self.assertEqual(
                voice_params_from_side({"pitch": None, "formant": 1.0}),
                {"formant": 1.0},
            )

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
