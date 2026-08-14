# -*- coding: utf-8 -*-
"""Unit tests for tools.dsp_fx (no audio device).

Constants (EQ_*) must import without numpy — the frozen shell has no numpy.
Audio-processing tests require numpy (Runtime).
"""

from __future__ import annotations

import sys
import time
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


# ---------------------------------------------------------------------------
# 提速改造的守门测试
#
# gate / 压缩 / EQ 三个模块原来都是逐样本 Python 循环，实测占掉 21.3ms 块预算的
# 16.3%，而这还是在 DSP 变声的十来个效果器加进来之前。改造的前提是**听感不能变**，
# 所以这里把原实现按原样抄一份当基准，逐样本比对。
# ---------------------------------------------------------------------------


def _ref_gate(x, sr, gate):
    """NoiseGate.process 的原始逐样本实现，作为回归基准。"""
    from tools.dsp_fx import _db_to_lin, _ms_to_coef

    thr = _db_to_lin(gate.threshold_db)
    min_g = _db_to_lin(-abs(gate.range_db))
    att_c = _ms_to_coef(2.0, sr)
    rel_c = _ms_to_coef(gate.release_ms, sr)
    hold_n = max(int(sr * gate.hold_ms * 0.001), 0)
    x_arr = np.asarray(x, dtype=np.float64)
    levels = np.abs(x_arr)
    env, hold, g = 0.0, 0, 1.0
    out = np.empty_like(x_arr, dtype=np.float32)
    for i in range(x_arr.shape[0]):
        level = levels[i]
        env = att_c * env + (1.0 - att_c) * level if level > env \
            else rel_c * env + (1.0 - rel_c) * level
        if env >= thr:
            hold, target = hold_n, 1.0
        elif hold > 0:
            hold -= 1
            target = 1.0
        else:
            target = min_g
        g = rel_c * g + (1.0 - rel_c) * target if target < g \
            else att_c * g + (1.0 - att_c) * target
        out[i] = np.float32(x_arr[i] * g)
    return out


def _ref_comp(x, sr, comp):
    """Compressor.process 的原始逐样本实现，作为回归基准。"""
    from tools.dsp_fx import _db_to_lin, _ms_to_coef

    thr, ratio = comp.threshold_db, comp.ratio
    att = _ms_to_coef(comp.attack_ms, sr)
    rel = _ms_to_coef(comp.release_ms, sr)
    makeup = _db_to_lin(comp.makeup_db)
    env_db = -100.0
    x_arr = np.asarray(x, dtype=np.float64)
    levels_db = 20.0 * np.log10(np.abs(x_arr) + 1e-10)
    out = np.empty_like(x_arr, dtype=np.float32)
    for i in range(x_arr.shape[0]):
        level_db = float(levels_db[i])
        env_db = att * env_db + (1.0 - att) * level_db if level_db > env_db \
            else rel * env_db + (1.0 - rel) * level_db
        if env_db > thr:
            gain = _db_to_lin(-(env_db - thr) * (1.0 - 1.0 / ratio)) * makeup
        else:
            gain = makeup
        out[i] = np.float32(x_arr[i] * gain)
    return out


def _voice_like(n, sr, seed=7):
    """突发 + 静音 + 瞬态：让 gate 开关、压缩器起落都真的动起来。"""
    rng = np.random.default_rng(seed)
    t = np.arange(n) / sr
    env = (np.sin(2 * np.pi * 1.7 * t) * 0.5 + 0.5) ** 3
    x = (0.3 * np.sin(2 * np.pi * 220 * t) + 0.06 * rng.standard_normal(n)) * env
    x[n // 4 : n // 4 + n // 12] *= 0.0005  # 静音段，gate 关
    x[n // 2 : n // 2 + 64] = 0.95          # 瞬态，压缩器起
    return x.astype(np.float32)


@unittest.skipUnless(_HAS_NP, "needs numpy")
class NoBehaviourChangeTests(unittest.TestCase):
    """提速不许改声音。逐样本比对，允许的偏差只有 float32 舍入。"""

    SR = 48000
    N = 8192

    def test_gate_matches_reference(self):
        x = _voice_like(self.N, self.SR)
        got = NoiseGate().process(x, self.SR)
        want = _ref_gate(x, self.SR, NoiseGate())
        self.assertEqual(got.shape, want.shape)
        np.testing.assert_allclose(got, want, rtol=0, atol=1e-7)

    def test_compressor_matches_reference(self):
        x = _voice_like(self.N, self.SR, seed=11)
        got = Compressor().process(x, self.SR)
        want = _ref_comp(x, self.SR, Compressor())
        np.testing.assert_allclose(got, want, rtol=0, atol=1e-7)

    def test_state_carries_across_blocks(self):
        """整块算一次 == 分四块连着算。块间状态断了就会在接缝处爆音。"""
        x = _voice_like(self.N, self.SR, seed=13)
        whole = Compressor().process(x, self.SR)
        c = Compressor()
        parts = np.concatenate(
            [c.process(x[i : i + 2048], self.SR) for i in range(0, self.N, 2048)]
        )
        np.testing.assert_allclose(parts, whole, rtol=0, atol=1e-7)

        whole_g = NoiseGate().process(x, self.SR)
        g = NoiseGate()
        parts_g = np.concatenate(
            [g.process(x[i : i + 2048], self.SR) for i in range(0, self.N, 2048)]
        )
        np.testing.assert_allclose(parts_g, whole_g, rtol=0, atol=1e-7)


@unittest.skipUnless(_HAS_NP, "needs numpy")
class EqBackendAgreementTests(unittest.TestCase):
    """EQ 有两条实现：scipy sosfilt 和纯 Python 双二阶。必须给出同一个结果。"""

    SR = 48000
    GAINS = [3.0, -2.0, 4.0, -1.0, 2.0]

    def _run(self, use_scipy):
        import tools.dsp_fx as fx

        old = fx._SOSFILT_CACHE
        fx._SOSFILT_CACHE = old if use_scipy else None
        try:
            eq = GraphicEQ(self.GAINS)
            x = _voice_like(4096, self.SR, seed=17)
            return np.concatenate(
                [eq.process(x[i : i + 1024], self.SR) for i in range(0, 4096, 1024)]
            )
        finally:
            fx._SOSFILT_CACHE = old

    def test_backends_agree(self):
        try:
            import scipy.signal  # noqa: F401
        except ImportError:
            self.skipTest("no scipy — only the pure-Python path exists here")
        import tools.dsp_fx as fx

        fx._sosfilt()  # 填好缓存
        np.testing.assert_allclose(
            self._run(True), self._run(False), rtol=1e-4, atol=1e-5
        )

    def test_pure_python_path_still_filters(self):
        """没有 scipy 时也得真的在滤波，不能悄悄变直通。"""
        y = self._run(False)
        x = _voice_like(4096, self.SR, seed=17)
        self.assertGreater(float(np.abs(y - x).max()), 1e-3)

    def test_flat_eq_is_transparent(self):
        eq = GraphicEQ([0.0] * 5)
        x = _voice_like(2048, self.SR, seed=19)
        np.testing.assert_allclose(eq.process(x, self.SR), x, rtol=0, atol=1e-6)


@unittest.skipUnless(_HAS_NP, "needs numpy")
class BlockBudgetTests(unittest.TestCase):
    """整条链必须留够余量给后面要加的十来个 DSP 变声效果器。

    改造前实测 3.49ms / 21.33ms = 16.3%，那时候链上只有三个模块。
    """

    def test_chain_under_15_percent_of_block(self):
        sr = 48000
        n = 1024  # 21.33ms
        budget_ms = n / sr * 1000.0
        ch = RealtimeFxChain(
            {
                "fx_enabled": True,
                "fx_gate_enabled": True,
                "fx_comp_enabled": True,
                "fx_eq_enabled": True,
                "fx_eq_gains": [3.0, -2.0, 4.0, -1.0, 2.0],
            }
        )
        x = _voice_like(n, sr, seed=23)
        for _ in range(5):
            ch.process(x, sr)
        times = []
        for _ in range(21):
            t0 = time.perf_counter()
            ch.process(x, sr)
            times.append((time.perf_counter() - t0) * 1000.0)
        median = sorted(times)[10]
        self.assertLess(
            median,
            budget_ms * 0.15,
            f"效果链占了块预算的 {median / budget_ms * 100:.1f}%"
            f"（{median:.2f}ms / {budget_ms:.2f}ms），上限 15%。"
            "DSP 变声还要往这条链上加十来个效果器，现在就超了后面没法做。",
        )


if __name__ == "__main__":
    unittest.main()
