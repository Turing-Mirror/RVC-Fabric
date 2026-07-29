# -*- coding: utf-8 -*-
"""Unit tests for tools.dsp_fx (no audio device).

Constants (EQ_*) must import without numpy — the frozen shell has no numpy.
Audio-processing tests require numpy (Runtime).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.dsp_fx import (  # noqa: E402 — path setup above
    DEFAULT_FX_CONFIG,
    EQ_LABELS,
    EQ_PRESET_LABELS,
    EQ_PRESETS,
    Compressor,
    GraphicEQ,
    NoiseGate,
    RealtimeFxChain,
    extract_fx_config,
)

try:
    import numpy as np

    _HAS_NP = True
except ImportError:
    _HAS_NP = False


class ConstantsWithoutNumpyTests(unittest.TestCase):
    """Shell UI imports these; must never require numpy at module load."""

    def test_eq_labels(self):
        self.assertEqual(len(EQ_LABELS), 5)
        self.assertEqual(EQ_LABELS[0], "60Hz")

    def test_presets_defined(self):
        self.assertIn("flat", EQ_PRESETS)
        self.assertEqual(len(EQ_PRESETS["vocal_front"]), 5)
        self.assertEqual(set(EQ_PRESETS), set(EQ_PRESET_LABELS))

    def test_extract_fx_config(self):
        d = extract_fx_config({"fx_enabled": True, "pitch": 12})
        self.assertTrue(d["fx_enabled"])
        self.assertIn("fx_eq_gains", d)
        self.assertEqual(len(d["fx_eq_gains"]), 5)

    def test_default_fx_config_keys(self):
        self.assertIn("fx_enabled", DEFAULT_FX_CONFIG)
        self.assertFalse(DEFAULT_FX_CONFIG["fx_enabled"])

    def test_graphic_eq_preset_without_numpy(self):
        eq = GraphicEQ()
        eq.apply_preset("bright")
        self.assertNotEqual(eq.gains_db, [0.0] * 5)


@unittest.skipUnless(_HAS_NP, "numpy / Runtime required for DSP tests")
class NoiseGateTests(unittest.TestCase):
    def test_silence_attenuated(self):
        g = NoiseGate(threshold_db=-40, range_db=40, release_ms=5, hold_ms=0)
        sr = 16000
        # warm-up then silence
        loud = (np.random.randn(sr // 10) * 0.3).astype(np.float32)
        quiet = (np.random.randn(sr // 4) * 0.0001).astype(np.float32)
        g.process(loud, sr)
        out = g.process(quiet, sr)
        self.assertLess(float(np.sqrt(np.mean(out**2))), 0.01)


@unittest.skipUnless(_HAS_NP, "numpy / Runtime required for DSP tests")
class CompressorTests(unittest.TestCase):
    def test_peaks_reduced(self):
        c = Compressor(
            threshold_db=-12, ratio=8, attack_ms=1, release_ms=50, makeup_db=0
        )
        sr = 16000
        # loud sine
        t = np.arange(sr // 2) / sr
        x = (0.9 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        # warm envelope
        c.process(x[:200], sr)
        out = c.process(x, sr)
        self.assertLess(float(np.max(np.abs(out))), float(np.max(np.abs(x))) * 0.95)


@unittest.skipUnless(_HAS_NP, "numpy / Runtime required for DSP tests")
class EQTests(unittest.TestCase):
    def test_flat_near_unity(self):
        eq = GraphicEQ([0, 0, 0, 0, 0])
        sr = 48000
        t = np.arange(2048) / sr
        x = (0.2 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
        y = eq.process(x, sr)
        # flat peaking filters are bypass
        np.testing.assert_allclose(y, x, rtol=1e-5, atol=1e-5)

    def test_set_gains_noop_keeps_filter_state(self):
        """Hot re-push of identical gains must not force redesign (review #37)."""
        eq = GraphicEQ([1.0, 0, 0, 0, 0])
        eq.process(np.zeros(64, dtype=np.float32), 48000)
        self.assertNotEqual(eq._sr, 0)
        sr_before = eq._sr
        filters_before = eq._filters
        eq.set_gains([1.0, 0, 0, 0, 0])
        self.assertEqual(eq._sr, sr_before)
        self.assertIs(eq._filters, filters_before)
        eq.set_gains([2.0, 0, 0, 0, 0])
        self.assertEqual(eq._sr, 0)


@unittest.skipUnless(_HAS_NP, "numpy / Runtime required for DSP tests")
class ChainTests(unittest.TestCase):
    def test_disabled_is_passthrough(self):
        ch = RealtimeFxChain({"fx_enabled": False})
        x = np.random.randn(1024).astype(np.float32) * 0.1
        y = ch.process(x, 48000)
        np.testing.assert_array_equal(y, x.astype(np.float32))

    def test_enabled_runs(self):
        ch = RealtimeFxChain(
            {
                "fx_enabled": True,
                "fx_gate_enabled": True,
                "fx_gate_threshold_db": -60,
                "fx_comp_enabled": True,
                "fx_eq_enabled": True,
                "fx_eq_preset": "vocal_front",
            }
        )
        x = (np.random.randn(2048) * 0.2).astype(np.float32)
        y = ch.process(x, 48000)
        self.assertEqual(y.shape, x.shape)
        self.assertTrue(np.all(np.isfinite(y)))


@unittest.skipUnless(_HAS_NP, "numpy / Runtime required for performance tests")
class PerformanceTests(unittest.TestCase):
    """Verify FX chain meets realtime budget on a realistic block.

    Block size 10560 samples = 48000 Hz * 0.22s (matches the AMD test report).
    Budget: block_time is 220ms; FX must finish in a small fraction of that
    so it never causes an overrun. Target < 30ms (was 200-500ms+ before
    vectorization, with 4125ms peaks reported in the field).
    """

    def test_full_chain_under_30ms(self):
        import time

        ch = RealtimeFxChain(
            {
                "fx_enabled": True,
                "fx_gate_enabled": True,
                "fx_gate_threshold_db": -50,
                "fx_comp_enabled": True,
                "fx_comp_threshold_db": -20,
                "fx_comp_ratio": 4.0,
                "fx_eq_enabled": True,
                "fx_eq_preset": "bright",
            }
        )
        sr = 48000
        block = 10560  # 0.22s @ 48k — matches AMD perf report
        # voiced-like signal so gate/comp actually do work
        t = np.arange(block) / sr
        x = (0.3 * np.sin(2 * np.pi * 220 * t) + 0.05 * np.random.randn(block)).astype(
            np.float32
        )
        # warm up state + JIT
        ch.process(x, sr)
        # measure 5 runs, take median
        times = []
        for _ in range(5):
            t0 = time.perf_counter()
            ch.process(x, sr)
            times.append((time.perf_counter() - t0) * 1000.0)
        median_ms = sorted(times)[2]
        self.assertLess(
            median_ms,
            30.0,
            f"FX chain too slow: {median_ms:.1f}ms (budget 30ms for 220ms block)",
        )


if __name__ == "__main__":
    unittest.main()
