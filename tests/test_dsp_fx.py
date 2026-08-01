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
class ShellContractTests(unittest.TestCase):
    """壳层必须认得引擎的每一个 fx 键。

    加这个是因为迁到 Tauri 的时候整条 DSP 链掉了：引擎侧一直支持 EQ、压缩器、
    噪声门，`gui_v1._worker_apply_hot` 也一直在热更新它们，但新壳的 HOT_KEYS
    里一个 fx 键都没有 —— 于是设置写进去了、永远推不到 worker，界面上索性没有
    这一节。静态看两边都「正常」，只有对着列表比才看得出来。
    """

    def _rust_hot_keys(self) -> set[str]:
        src = (ROOT / "app" / "src-tauri" / "src" / "config.rs").read_text(
            encoding="utf-8"
        )
        head = "pub const HOT_KEYS: &[&str] = &["
        start = src.index(head) + len(head)
        body = src[start : src.index("];", start)]
        return {
            part.split('"')[1]
            for part in body.splitlines()
            if part.count('"') >= 2
        }

    def test_every_engine_fx_key_is_a_shell_hot_key(self):
        rust = self._rust_hot_keys()
        missing = sorted(k for k in DEFAULT_FX_CONFIG if k not in rust)
        self.assertEqual(missing, [], f"壳层 HOT_KEYS 缺这些 fx 键：{missing}")

    def test_shell_has_no_fx_key_the_engine_ignores(self):
        # 反向也要成立：壳里多写一个键，用户会看到一个调了没反应的开关。
        rust_fx = {k for k in self._rust_hot_keys() if k.startswith("fx_")}
        extra = sorted(rust_fx - set(DEFAULT_FX_CONFIG))
        self.assertEqual(extra, [], f"壳层多了引擎不认的 fx 键：{extra}")

    def test_shell_defaults_match_the_engine_defaults(self):
        # 默认值不一致 = 用户没动过任何开关，声音却和引擎预期的不一样。
        src = (ROOT / "app" / "src-tauri" / "src" / "config.rs").read_text(
            encoding="utf-8"
        )
        for key, want in DEFAULT_FX_CONFIG.items():
            if key == "fx_eq_gains":
                continue  # 数组单独看
            line = [ln for ln in src.splitlines() if f'"{key}".into()' in ln]
            self.assertTrue(line, f"config.rs defaults() 里没有 {key}")
            got = line[0].split("json!(")[1].strip().rstrip(";").rstrip(")").strip()
            if isinstance(want, bool):
                self.assertEqual(got, "true" if want else "false", key)
            elif isinstance(want, str):
                self.assertEqual(got.strip('"'), want, key)
            else:
                self.assertAlmostEqual(float(got), float(want), places=6, msg=key)


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
