# -*- coding: utf-8 -*-
"""Unit tests for tools.dsp_fx (no audio device)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import numpy as np
    from tools.dsp_fx import (
        EQ_PRESETS,
        Compressor,
        GraphicEQ,
        NoiseGate,
        RealtimeFxChain,
        extract_fx_config,
    )

    _HAS_NP = True
except ImportError:
    _HAS_NP = False


@unittest.skipUnless(_HAS_NP, "numpy / Runtime required for DSP tests")
class _DspRequireNumpy(unittest.TestCase):
    pass


class NoiseGateTests(_DspRequireNumpy):
    def test_silence_attenuated(self):
        g = NoiseGate(threshold_db=-40, range_db=40, release_ms=5, hold_ms=0)
        sr = 16000
        # warm-up then silence
        loud = (np.random.randn(sr // 10) * 0.3).astype(np.float32)
        quiet = (np.random.randn(sr // 4) * 0.0001).astype(np.float32)
        g.process(loud, sr)
        out = g.process(quiet, sr)
        self.assertLess(float(np.sqrt(np.mean(out**2))), 0.01)


class CompressorTests(_DspRequireNumpy):
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


class EQTests(_DspRequireNumpy):
    def test_flat_near_unity(self):
        eq = GraphicEQ([0, 0, 0, 0, 0])
        sr = 48000
        t = np.arange(2048) / sr
        x = (0.2 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
        y = eq.process(x, sr)
        # flat peaking filters are bypass
        np.testing.assert_allclose(y, x, rtol=1e-5, atol=1e-5)

    def test_presets_defined(self):
        self.assertIn("flat", EQ_PRESETS)
        self.assertEqual(len(EQ_PRESETS["vocal_front"]), 5)
        eq = GraphicEQ()
        eq.apply_preset("bright")
        self.assertNotEqual(eq.gains_db, [0.0] * 5)


class ChainTests(_DspRequireNumpy):
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

    def test_extract_fx_config(self):
        d = extract_fx_config({"fx_enabled": True, "pitch": 12})
        self.assertTrue(d["fx_enabled"])
        self.assertIn("fx_eq_gains", d)


if __name__ == "__main__":
    unittest.main()
