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

from tools.record_worker import (  # noqa: E402
    _open_error_code,
    peak_db,
    resolve_device_name,
    rms_db,
)


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


class PeakDbTests(unittest.TestCase):
    """麦克风测试判「有没有听到」看的是峰值，不是 RMS。"""

    def test_silence_is_floor(self):
        self.assertLessEqual(peak_db([0.0] * 64), -80.0)

    def test_full_scale_is_zero(self):
        self.assertAlmostEqual(peak_db([0.0, -1.0, 0.0]), 0.0, places=4)

    def test_peak_ignores_sign(self):
        self.assertAlmostEqual(peak_db([-0.5, 0.1]), peak_db([0.5, 0.1]), places=6)

    def test_a_single_loud_sample_lifts_the_peak_but_not_the_rms(self):
        # 说话是断续的：一整块里只有几个采样是响的。只看 RMS 的话，正常音量
        # 说一句话会停在 -40 dB 左右，读起来像「没听到」。
        block = [0.0] * 1023 + [0.8]
        self.assertGreater(peak_db(block), -2.0)
        self.assertLess(rms_db(block), -30.0)


class OpenErrorCodeTests(unittest.TestCase):
    """设备被占用要能跟其他打不开的原因分开 —— 前者的解法是「先停变声」。"""

    def test_portaudio_busy_errors(self):
        for text in (
            "Error opening InputStream: Unanticipated host error",
            "PortAudio Error: Device unavailable",
            "Invalid device",
        ):
            self.assertEqual(_open_error_code(RuntimeError(text)), "busy", text)

    def test_anything_else_is_generic(self):
        self.assertEqual(_open_error_code(ValueError("boom")), "open")


if __name__ == "__main__":
    unittest.main()
