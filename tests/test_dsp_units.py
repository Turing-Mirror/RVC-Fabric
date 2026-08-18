# -*- coding: utf-8 -*-
"""效果器参数标的单位，得真的是那个单位。

写这一份的由来：`vibrato.depth` 标的是「音分」，但换算式里漏了 rate，于是那个
数字只在某一个转速下才对得上号。外星人预设写 `depth: 6`，实际只有 4.7 音分，
四天里根本听不出在抖。老者 3.4 音分、水下 1.5 音分，同样是哑的。

当时的 DSP 测试一条都没拦住，因为它们查的全是配置：预设不能全是默认值、参数
不能越界、环调 mix 不能太高。在那些测试眼里，写 6 和写 50 没有区别 ——
**没有一条测试听过声音。**

所以这一份只干一件事：把信号灌进去，量出来，和标称值比。标 12 半音就得升一个
八度，标 180ms 就得 180ms 之后有回声，标 8 bit 就得有 256 个电平。

不查听感好不好（那是 Kara 拍板的事），只查数字有没有说谎。
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import numpy as np

    _HAS_NP = True
except ImportError:  # 冻结的壳侧环境没有 numpy
    _HAS_NP = False

SR = 48000
# 和引擎默认 block_time=0.22 一致。块长会影响 PitchShifter 的储备量，
# 拿一整段长音频一次喂进去它会永远停在预热、一路放干声 —— 那是测法错，
# 不是代码错，别再踩一次。
BLOCK = int(SR * 0.22)


def _skip_without_numpy(fn):
    return unittest.skipUnless(_HAS_NP, "需要 numpy")(fn)


def _make(effect: str, **kw):
    from tools.dsp_voice import EFFECT_SPECS, _FACTORIES

    params = dict(EFFECT_SPECS[effect]["params"])
    params.update(kw)
    return _FACTORIES[effect](params)


def _run(fx, sig):
    """按引擎的块长喂，模拟真实调用。"""
    out = [
        np.asarray(fx.process(sig[i : i + BLOCK].copy(), SR), dtype=np.float64)
        for i in range(0, len(sig) - BLOCK + 1, BLOCK)
    ]
    return np.concatenate(out)


def _tone(freq, secs=3.0):
    t = np.arange(int(SR * secs)) / SR
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


def _dominant(y, lo=50.0, hi=8000.0):
    """主频，用抛物线插值到 cent 级精度。"""
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    freqs = np.fft.rfftfreq(len(y), 1.0 / SR)
    band = (freqs > lo) & (freqs < hi)
    idx = np.arange(len(freqs))[band][np.argmax(spec[band])]
    if 0 < idx < len(spec) - 1:
        a, b, c = spec[idx - 1], spec[idx], spec[idx + 1]
        idx = idx + 0.5 * (a - c) / (a - 2 * b + c + 1e-30)
    return idx * SR / len(y)


def _pitch_swing_cents(y, f0, skip):
    """瞬时频率的峰谷，换算成相对 f0 的音分摆幅（单边）。"""
    n = len(y)
    h = np.zeros(n)
    h[0] = 1
    h[1 : n // 2] = 2
    h[n // 2] = 1
    z = np.fft.ifft(np.fft.fft(y) * h)
    f = np.diff(np.unwrap(np.angle(z))) * SR / (2 * np.pi)
    f = f[skip : -SR // 4]
    return (1200 * np.log2(f.max() / f0) - 1200 * np.log2(f.min() / f0)) / 2


class UnitAccuracyTests(unittest.TestCase):
    @_skip_without_numpy
    def test_pitch_semitones_are_semitones(self):
        for st in (-12.0, -5.0, 3.0, 7.0, 12.0):
            y = _run(_make("pitch", semitones=st), _tone(220.0))
            got = 12 * np.log2(_dominant(y[SR:]) / 220.0)
            self.assertAlmostEqual(got, st, delta=0.25, msg=f"标 {st} 半音，实测 {got:.2f}")

    @_skip_without_numpy
    def test_vibrato_depth_is_cents_at_any_rate(self):
        """关键是 **at any rate**。

        旧式子 `sweep = (depth/100)*(sr*0.0012)` 里没有 rate，而延迟线给出的音高
        偏移正比于 rate×sweep。所以它在某一个转速下能蒙对，换个转速就不是那个
        单位了。这里横跨 1.6–9.5Hz，就是为了钉住这一点。
        """
        for rate, depth in ((6.0, 50.0), (9.5, 17.0), (1.6, 35.0), (4.0, 20.0)):
            y = _run(_make("vibrato", rate=rate, depth=depth), _tone(440.0))
            got = _pitch_swing_cents(y, 440.0, SR // 2)
            self.assertAlmostEqual(
                got, depth, delta=depth * 0.15 + 2,
                msg=f"{rate}Hz 下标 {depth} 音分，实测 {got:.1f}",
            )

    @_skip_without_numpy
    def test_tremolo_depth_is_peak_gain_reduction(self):
        """depth 的定义是增益摆到 [1-depth, 1]，不是调制指数。"""
        dc = np.ones(SR * 3, dtype=np.float32)
        for depth in (0.08, 0.32, 0.6):
            g = _run(_make("tremolo", rate=6.0, depth=depth), dc)[SR:]
            self.assertAlmostEqual(float(g.max()), 1.0, delta=0.01)
            self.assertAlmostEqual(float(g.min()), 1.0 - depth, delta=0.01)

    @_skip_without_numpy
    def test_echo_time_ms_is_milliseconds(self):
        for ms in (90.0, 180.0, 300.0):
            imp = np.zeros(SR * 2, dtype=np.float32)
            imp[100] = 1.0
            y = _run(_make("echo", time_ms=ms, feedback=0.3, mix=0.9), imp)
            guard = int(SR * 0.02)
            got = (np.argmax(np.abs(y[100 + guard :])) + guard) / SR * 1000
            self.assertAlmostEqual(got, ms, delta=8.0, msg=f"标 {ms}ms，实测 {got:.0f}ms")

    @_skip_without_numpy
    def test_ring_freq_is_the_sideband_spacing(self):
        for freq in (30.0, 50.0, 90.0):
            y = _run(_make("ring", freq=freq, mix=1.0), _tone(1000.0))[SR:]
            spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
            fr = np.fft.rfftfreq(len(y), 1.0 / SR)
            band = (fr > 1000 + freq * 0.4) & (fr < 1000 + freq * 2.5)
            got = fr[band][np.argmax(spec[band])] - 1000.0
            self.assertAlmostEqual(got, freq, delta=max(3.0, freq * 0.08))

    @_skip_without_numpy
    def test_bitcrush_bits_are_bits(self):
        """必须拿噪声测。

        48000/300 整除，正弦一个周期只走 160 个采样点、每周期重复同样的值，
        于是不管位深多高都只数得出约 160 个电平 —— 拿正弦测会误判 12bit 是 6bit。
        """
        rng = np.random.default_rng(3)
        noise = rng.uniform(-1.0, 1.0, SR * 3).astype(np.float32)
        for bits in (4, 8, 12):
            y = _run(_make("bitcrush", bits=bits, downsample=1), noise)[SR:]
            levels = len(np.unique(np.round(y, 9)))
            self.assertAlmostEqual(
                math.log2(levels), bits, delta=0.2,
                msg=f"标 {bits}bit，实测 {levels} 个电平",
            )

    @_skip_without_numpy
    def test_bitcrush_at_full_bits_is_a_passthrough(self):
        rng = np.random.default_rng(4)
        noise = rng.uniform(-1.0, 1.0, BLOCK * 4).astype(np.float32)
        y = _run(_make("bitcrush", bits=16, downsample=1), noise)
        np.testing.assert_allclose(y, noise[: len(y)], atol=1e-6)

    @_skip_without_numpy
    def test_radio_low_high_are_the_minus_3db_corners(self):
        """标称值是那两个 biquad 自己的拐点。

        整条链在这两个频率上读到的是约 -8dB，不是 -3dB —— 因为中间还挂着一个
        **有意加的 +6dB 中频提升**（`_ensure` 里那行 peak），它把峰值抬高了。
        所以量的是滤波器本身，不是整条链的响应；拿整条链去量会误判成「标称
        300Hz 实际 610Hz」。
        """
        from tools.dsp_voice import _highpass_sos, _lowpass_sos

        def mag_db(sos, f):
            b0, b1, b2, _, a1, a2 = sos
            z = np.exp(-2j * np.pi * f / SR)
            return 20 * np.log10(abs((b0 + b1 * z + b2 * z * z) / (1 + a1 * z + a2 * z * z)))

        for lo, hi in ((70.0, 1000.0), (300.0, 3400.0), (400.0, 2600.0)):
            self.assertAlmostEqual(mag_db(_highpass_sos(SR, lo), lo), -3.0, delta=0.15)
            self.assertAlmostEqual(mag_db(_lowpass_sos(SR, hi), hi), -3.0, delta=0.15)


class PresetAudibilityTests(unittest.TestCase):
    """内置预设里用到颤音的，摆幅得真的听得见。

    人耳能察觉的音高变化大约 5–10 音分。外星人当初写的 6 折合 4.7 音分，
    正好卡在阈值下面 —— 参数看着「填了个数」，声音上等于没填。
    """

    AUDIBLE_CENTS = 12.0

    @_skip_without_numpy
    def test_every_preset_vibrato_is_audible(self):
        from tools.dsp_presets import BUILTIN

        used = [(p["id"], p["params"]["vibrato"]) for p in BUILTIN if "vibrato" in p["params"]]
        self.assertTrue(used, "没有预设用颤音？那这条测试该删了")
        for pid, v in used:
            rate = float(v.get("rate", 5.0))
            depth = float(v.get("depth", 0.0))
            y = _run(_make("vibrato", rate=rate, depth=depth), _tone(440.0))
            got = _pitch_swing_cents(y, 440.0, SR // 2)
            self.assertGreaterEqual(
                got, self.AUDIBLE_CENTS,
                msg=f"{pid} 的颤音只有 {got:.1f} 音分，听不出来",
            )

    @_skip_without_numpy
    def test_every_preset_tremolo_is_audible(self):
        from tools.dsp_presets import BUILTIN

        dc = np.ones(SR * 3, dtype=np.float32)
        for p in BUILTIN:
            v = p["params"].get("tremolo")
            if not v:
                continue
            g = _run(_make("tremolo", rate=float(v.get("rate", 6.0)),
                           depth=float(v.get("depth", 0.0))), dc)[SR:]
            swing_db = 20 * math.log10(float(g.max()) / max(float(g.min()), 1e-9))
            # 1dB 是响度变化的大致可闻阈
            self.assertGreaterEqual(
                swing_db, 1.0,
                msg=f"{p['id']} 的振幅颤音只摆了 {swing_db:.2f}dB，听不出来",
            )


if __name__ == "__main__":
    unittest.main()
