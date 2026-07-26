# -*- coding: utf-8 -*-
"""Unit tests for HiDPI scaling helpers (theme.px / win_util DPI, no GUI)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher import theme
from launcher.win_util import enable_dpi_awareness, get_window_dpi


class PxScaleTests(unittest.TestCase):
    def tearDown(self):
        theme.set_scale_from_dpi(96)

    def test_identity_at_96dpi(self):
        theme.set_scale_from_dpi(96)
        self.assertEqual(theme.scale(), 1.0)
        for n in (0, 1, 7, 8, 68, 168, 180, 268, 640, 1320):
            self.assertEqual(theme.px(n), n)

    def test_scales_at_144dpi(self):
        theme.set_scale_from_dpi(144)
        self.assertEqual(theme.scale(), 1.5)
        self.assertEqual(theme.px(0), 0)
        self.assertEqual(theme.px(68), 102)
        self.assertEqual(theme.px(168), 252)
        self.assertEqual(theme.px(1320), 1980)

    def test_scales_at_120dpi(self):
        theme.set_scale_from_dpi(120)
        self.assertEqual(theme.scale(), 1.25)
        self.assertEqual(theme.px(640), 800)

    def test_never_downscales(self):
        theme.set_scale_from_dpi(72)
        self.assertEqual(theme.scale(), 1.0)
        self.assertEqual(theme.px(100), 100)

    def test_bad_dpi_is_safe(self):
        theme.set_scale_from_dpi(None)  # type: ignore[arg-type]
        self.assertEqual(theme.scale(), 1.0)


class MetaFontTests(unittest.TestCase):
    def test_ascii_stays_mono(self):
        f = theme.meta_font("IVF256_Flat")
        self.assertEqual(f[0], "Cascadia Mono")

    def test_cjk_goes_sans(self):
        f = theme.meta_font("少女音")
        self.assertEqual(f[0], "Microsoft YaHei UI")

    def test_mixed_goes_sans(self):
        f = theme.meta_font("作者 · Moon")
        self.assertEqual(f[0], "Microsoft YaHei UI")

    def test_empty_is_safe(self):
        self.assertEqual(theme.meta_font("")[0], "Cascadia Mono")
        self.assertEqual(theme.meta_font(None)[0], "Cascadia Mono")  # type: ignore[arg-type]


class FontFactoryShapeTests(unittest.TestCase):
    """Lock factory signatures — px()/meta_font call sites depend on them."""

    def test_mono(self):
        self.assertEqual(theme.mono_font(8), ("Cascadia Mono", 8))

    def test_sans_bold_triple(self):
        self.assertEqual(theme.sans_font(9, "bold"), ("Microsoft YaHei UI", 9, "bold"))

    def test_title_default_bold(self):
        self.assertEqual(theme.title_font(10), ("Microsoft YaHei UI", 10, "bold"))


class DpiAwarenessTests(unittest.TestCase):
    def test_enable_is_safe_and_repeatable(self):
        first = enable_dpi_awareness()
        second = enable_dpi_awareness()
        allowed = {"pmv2", "pm", "system", None}
        self.assertIn(first, allowed)
        self.assertIn(second, allowed)
        if sys.platform != "win32":
            self.assertIsNone(first)
        else:
            # Second call must not regress to failure once awareness is set
            self.assertIsNotNone(second)

    def test_get_window_dpi_plausible(self):
        dpi = get_window_dpi()
        self.assertIsInstance(dpi, int)
        self.assertGreaterEqual(dpi, 96)
        self.assertLessEqual(dpi, 480)

    def test_get_window_dpi_bad_hwnd(self):
        dpi = get_window_dpi(0xDEAD)
        self.assertGreaterEqual(dpi, 96)


if __name__ == "__main__":
    unittest.main()
