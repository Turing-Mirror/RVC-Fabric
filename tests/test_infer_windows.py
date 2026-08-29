# -*- coding: utf-8 -*-
"""离线切窗参数的守卫（不含 torch，开发解释器可直接跑）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.infer_windows import (  # noqa: E402
    DML_WINDOWS,
    clamp_windows_for_dml,
    infer_window_profile,
)


class ClampWindowsForDmlTests(unittest.TestCase):
    """26.8.29/113756：41s 的段在 DirectML 上必炸（空报错），得提前收小。"""

    def test_non_dml_untouched(self):
        for dev in ("cuda:0", "cpu", "privateuseone:1 之外的东西"):
            got = clamp_windows_for_dml(3, 10, 60, 65, False)
            self.assertEqual(got, (3, 10, 60, 65, False), dev)

    def test_dml_clamps_to_safe_profile(self):
        got = clamp_windows_for_dml(1, 6, 38, 41, True)
        self.assertEqual(got, (*DML_WINDOWS, True))
        self.assertLessEqual(DML_WINDOWS[3], 12)

    def test_user_forced_x_max_wins(self):
        # TM_VC_X_MAX 是明确的意思表示，不覆盖；真炸了还有 CPU 兜底。
        got = clamp_windows_for_dml(1, 6, 38, 41, True, forced_x_max=30)
        self.assertEqual(got, (1, 6, 38, 41, False))


class InferWindowProfileTests(unittest.TestCase):
    def test_profiles_stay_sane(self):
        for mem in (None, 2, 3, 4, 8, 24):
            for half in (False, True):
                x_pad, x_query, x_center, x_max = infer_window_profile(mem, half)
                self.assertLess(x_center, x_max)
                self.assertGreaterEqual(x_pad, 1)
                self.assertGreaterEqual(x_query, 2)


if __name__ == "__main__":
    unittest.main()
