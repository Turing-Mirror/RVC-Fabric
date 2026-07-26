# -*- coding: utf-8 -*-
"""麦克风增益（in_gain_db）launcher 侧连接测试（无 Tk / 无 torch）。

引擎侧行为（gui_v1 audio_infer 前置增益）需要 Runtime，见实机验收。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.config_store import DEFAULTS, app_cfg_to_engine_settings
from launcher.realtime_protocol import COLD_KEYS, HOT_KEYS


class InputGainWiringTests(unittest.TestCase):
    def test_hot_key_registered(self):
        self.assertIn("in_gain_db", HOT_KEYS)
        self.assertNotIn("in_gain_db", COLD_KEYS)

    def test_default_zero(self):
        self.assertEqual(DEFAULTS.get("in_gain_db"), 0.0)

    def test_engine_settings_mapping(self):
        out = app_cfg_to_engine_settings({"in_gain_db": "6"})
        self.assertEqual(out["in_gain_db"], 6.0)
        self.assertIsInstance(out["in_gain_db"], float)

    def test_engine_settings_missing_defaults_zero(self):
        out = app_cfg_to_engine_settings({})
        self.assertEqual(out["in_gain_db"], 0.0)

    def test_engine_settings_negative(self):
        out = app_cfg_to_engine_settings({"in_gain_db": -12.5})
        self.assertEqual(out["in_gain_db"], -12.5)


if __name__ == "__main__":
    unittest.main()
