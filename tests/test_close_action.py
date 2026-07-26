# -*- coding: utf-8 -*-
"""close_action（关闭主窗口行为）配置连接测试（无 Tk）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.config_store import DEFAULTS, _normalize_cfg


class CloseActionTests(unittest.TestCase):
    def test_default_is_ask(self):
        self.assertEqual(DEFAULTS.get("close_action"), "ask")

    def test_valid_values_kept(self):
        for v in ("ask", "tray", "exit"):
            self.assertEqual(_normalize_cfg({"close_action": v})["close_action"], v)

    def test_invalid_value_falls_back_to_ask(self):
        for v in ("", None, "minimize", 123):
            self.assertEqual(_normalize_cfg({"close_action": v})["close_action"], "ask")


if __name__ == "__main__":
    unittest.main()
