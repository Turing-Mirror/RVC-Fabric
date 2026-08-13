# -*- coding: utf-8 -*-
"""Unit tests for STS record_worker helpers (no microphone required)."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.record_worker import resolve_device_name, rms_db  # noqa: E402


class ResolveDeviceNameTests(unittest.TestCase):
    NAMES = [
        "麦克风 (Realtek High Definition Audio)",
        "立体声混音 (Realtek High Definition Audio)",
        "CABLE Output (VB-Audio Virtual Cable)",
    ]

    def test_exact(self):
        self.assertEqual(
            resolve_device_name(self.NAMES[0], self.NAMES),
            self.NAMES[0],
        )

    def test_truncated_saved_name(self):
        # app_config 里经常是被截断的 MME 名
        got = resolve_device_name("麦克风 (Realtek High Definition Au", self.NAMES)
        self.assertEqual(got, self.NAMES[0])

    def test_empty_or_missing(self):
        self.assertIsNone(resolve_device_name("", self.NAMES))
        self.assertIsNone(resolve_device_name("不存在的设备", self.NAMES))
        self.assertIsNone(resolve_device_name("麦克风", []))


class RmsDbTests(unittest.TestCase):
    def test_silence_is_floor(self):
        self.assertLessEqual(rms_db([0.0] * 64), -80.0)

    def test_full_scale_near_zero(self):
        db = rms_db([1.0] * 64)
        self.assertGreater(db, -0.1)
        self.assertLessEqual(db, 0.1)

    def test_half_scale(self):
        db = rms_db([0.5] * 128)
        self.assertTrue(math.isfinite(db))
        self.assertAlmostEqual(db, 20.0 * math.log10(0.5), places=4)


if __name__ == "__main__":
    unittest.main()
