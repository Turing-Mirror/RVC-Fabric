# -*- coding: utf-8 -*-
"""Realtime post-RVC DSP chain: noise gate → compressor → graphic EQ → out gain.

No new dependencies (numpy only; optional scipy not required).
Designed for block processing with continuous state across calls.

Default: chain master switch off so legacy behaviour is unchanged.

Important: numpy is imported lazily. The frozen main-app shell (PyInstaller)
imports EQ_* constants for the settings UI but does **not** ship numpy —
numpy lives in Runtime (worker). Top-level `import numpy` would crash the
shell after a clean install even when Runtime is ready.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

if TYPE_CHECKING:
    import numpy as np

# 5-band graphic EQ centre frequencies (Hz)
EQ_FREQS: tuple[float, ...] = (60.0, 250.0, 1000.0, 4000.0, 8000.0)
EQ_LABELS: tuple[str, ...] = ("60Hz", "250Hz", "1kHz", "4kHz", "8kHz")

# Preset gains in dB for the five bands
EQ_PRESETS: Dict[str, List[float]] = {
    "flat": [0.0, 0.0, 0.0, 0.0, 0.0],
    "vocal_front": [-2.0, 1.0, 3.0, 2.5, 1.0],  # 人声前倾
    "warm": [2.0, 1.5, 0.0, -1.0, -2.0],  # 温暖饱满
    "bright": [-1.5, 0.0, 1.0, 3.0, 2.5],  # 清晰明亮
    "de_nasal": [0.0, -3.5, -1.0, 1.5, 0.5],  # 消除鼻音
    "thick": [3.0, 1.5, 0.0, -0.5, -1.5],  # 低沉厚实
}

EQ_PRESET_LABELS: Dict[str, str] = {
    "flat": "平直",
    "vocal_front": "人声前倾",
    "warm": "温暖饱满",
    "bright": "清晰明亮",
    "de_nasal": "消除鼻音",
    "thick": "低沉厚实",
}


def _numpy():
    """Import numpy only when audio processing runs (Runtime worker)."""
    import numpy as np

    return np


def _sosfilt():
    """scipy.signal.sosfilt if available, else None.

    scipy 在 Runtime 里（requirements/requirements.txt），但冻结的主程序壳没有，
    而且用户可能拿别的 Python 跑。拿不到就退回纯 Python 的双二阶循环——慢，
    但结果一模一样。
    """
    global _SOSFILT_CACHE
    if _SOSFILT_CACHE is _UNSET:
        try:
            from scipy.signal import sosfilt

            _SOSFILT_CACHE = sosfilt
        except Exception:
            _SOSFILT_CACHE = None
    return _SOSFILT_CACHE


_UNSET = object()
_SOSFILT_CACHE: Any = _UNSET


def _db_to_lin(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def _lin_to_db(x: float, floor: float = 1e-10) -> float:
    return float(20.0 * math.log10(max(abs(x), floor)))


def _ms_to_coef(ms: float, sr: int) -> float:
    """One-pole coefficient for time constant in ms."""
    ms = max(float(ms), 0.05)
    return float(math.exp(-1.0 / (sr * ms * 0.001)))


# ---------------------------------------------------------------------------
# Peaking EQ biquad (RBJ cookbook)
# ---------------------------------------------------------------------------


@dataclass
class BiquadPeak:
    b0: float = 1.0
    b1: float = 0.0
    b2: float = 0.0
    a1: float = 0.0
    a2: float = 0.0
    z1: float = 0.0
    z2: float = 0.0

    @classmethod
    def design(cls, sr: int, freq: float, gain_db: float, q: float = 1.0) -> "BiquadPeak":
        if abs(gain_db) < 1e-6:
            return cls()  # bypass
        freq = float(min(max(freq, 20.0), 0.45 * sr))
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * math.pi * freq / sr
        cos_w = math.cos(w0)
        sin_w = math.sin(w0)
        alpha = sin_w / (2.0 * max(q, 0.1))
        b0 = 1.0 + alpha * A
        b1 = -2.0 * cos_w
        b2 = 1.0 - alpha * A
        a0 = 1.0 + alpha / A
        a1 = -2.0 * cos_w
        a2 = 1.0 - alpha / A
        return cls(
            b0=b0 / a0,
            b1=b1 / a0,
            b2=b2 / a0,
            a1=a1 / a0,
            a2=a2 / a0,
        )

    def is_bypass(self) -> bool:
        return (
            self.b0 == 1.0
            and self.b1 == 0.0
            and self.b2 == 0.0
            and self.a1 == 0.0
            and self.a2 == 0.0
        )

    def sos_row(self) -> list[float]:
        """[b0, b1, b2, 1, a1, a2] —— scipy.signal.sosfilt 的一段。

        系数在 design 里已经除过 a0，所以这里 a0 恒为 1。
        """
        return [self.b0, self.b1, self.b2, 1.0, self.a1, self.a2]

    def process(self, x: "np.ndarray") -> "np.ndarray":
        """没有 scipy 时的回退路径。GraphicEQ 有 scipy 就整条走 sosfilt。

        差分方程是转置直接 II 型，跟 sosfilt 的状态约定一致，两条路结果相同。
        """
        np = _numpy()
        if self.is_bypass():
            return x
        # 逐样本递归没法向量化，但可以别在循环里碰 numpy：标量索引每次约 100ns，
        # Python list 约 20ns。先整块转成 list，算完一次性转回数组。
        xs = np.asarray(x, dtype=np.float64).tolist()
        b0, b1, b2, a1, a2 = self.b0, self.b1, self.b2, self.a1, self.a2
        z1, z2 = self.z1, self.z2
        ys = [0.0] * len(xs)
        for i, xn in enumerate(xs):
            yn = b0 * xn + z1
            z1 = b1 * xn - a1 * yn + z2
            z2 = b2 * xn - a2 * yn
            ys[i] = yn
        self.z1, self.z2 = float(z1), float(z2)
        return np.asarray(ys, dtype=np.float32)

    def reset(self) -> None:
        self.z1 = 0.0
        self.z2 = 0.0


# ---------------------------------------------------------------------------
# Modules
# ---------------------------------------------------------------------------


class NoiseGate:
    """Level noise gate with hold and smooth release."""

    def __init__(
        self,
        threshold_db: float = -50.0,
        release_ms: float = 50.0,
        hold_ms: float = 20.0,
        range_db: float = 20.0,
    ) -> None:
        self.threshold_db = float(threshold_db)
        self.release_ms = float(release_ms)
        self.hold_ms = float(hold_ms)
        self.range_db = float(range_db)
        self._env = 0.0
        self._hold_left = 0
        self._gain = 1.0
        self._sr = 48000

    def configure(self, **kw: Any) -> None:
        for k, v in kw.items():
            if hasattr(self, k) and v is not None:
                setattr(self, k, float(v) if k != "enabled" else v)

    def reset(self) -> None:
        self._env = 0.0
        self._hold_left = 0
        self._gain = 1.0

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        self._sr = sr
        thr = _db_to_lin(self.threshold_db)
        min_g = _db_to_lin(-abs(self.range_db))
        att_c = _ms_to_coef(2.0, sr)  # fast open
        rel_c = _ms_to_coef(self.release_ms, sr)
        hold_n = max(int(sr * self.hold_ms * 0.001), 0)
        x_arr = np.asarray(x, dtype=np.float64)
        # 包络和增益都是逐样本递归、而且系数按数据分支（快开慢关），没法向量化。
        # 试过「快慢两条一阶滤波取 max」的常见近似，实测增益偏差最大 8.2 dB、
        # 均值 2.7 dB —— 那不是同一个门了，不能用。
        # 能做的是别在循环里碰 numpy：整块转 list 再算，算术一模一样，快三倍多。
        levels = np.abs(x_arr).tolist()
        xs = x_arr.tolist()
        env = self._env
        hold = self._hold_left
        g = self._gain
        gains = [0.0] * len(xs)
        for i, level in enumerate(levels):
            if level > env:
                env = att_c * env + (1.0 - att_c) * level
            else:
                env = rel_c * env + (1.0 - rel_c) * level
            if env >= thr:
                hold = hold_n
                target = 1.0
            elif hold > 0:
                hold -= 1
                target = 1.0
            else:
                target = min_g
            # smooth gain
            if target < g:
                g = rel_c * g + (1.0 - rel_c) * target
            else:
                g = att_c * g + (1.0 - att_c) * target
            gains[i] = g
        self._env = float(env)
        self._hold_left = int(hold)
        self._gain = float(g)
        return (x_arr * np.asarray(gains)).astype(np.float32)


class Compressor:
    """Peak compressor with attack/release and makeup gain."""

    def __init__(
        self,
        threshold_db: float = -20.0,
        ratio: float = 4.0,
        attack_ms: float = 5.0,
        release_ms: float = 100.0,
        makeup_db: float = 0.0,
    ) -> None:
        self.threshold_db = float(threshold_db)
        self.ratio = max(float(ratio), 1.0)
        self.attack_ms = float(attack_ms)
        self.release_ms = float(release_ms)
        self.makeup_db = float(makeup_db)
        self._env_db = -100.0

    def configure(self, **kw: Any) -> None:
        for k, v in kw.items():
            if hasattr(self, k) and v is not None:
                setattr(self, k, float(v))
        self.ratio = max(self.ratio, 1.0)

    def reset(self) -> None:
        self._env_db = -100.0

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        thr = self.threshold_db
        ratio = self.ratio
        att = _ms_to_coef(self.attack_ms, sr)
        rel = _ms_to_coef(self.release_ms, sr)
        makeup = _db_to_lin(self.makeup_db)
        env_db = self._env_db
        # log10 一次性向量化算完（1 次 np.log10 替掉一块 1024 次 math.log10），
        # 再转成 Python list 跑那段没法向量化的分支递归 —— 循环里不碰 numpy
        # 标量索引，同样的算术快三倍多。
        x_arr = np.asarray(x, dtype=np.float64)
        levels_db = (20.0 * np.log10(np.abs(x_arr) + 1e-10)).tolist()
        slope = 1.0 - 1.0 / ratio
        gains = [0.0] * len(levels_db)
        for i, level_db in enumerate(levels_db):
            if level_db > env_db:
                env_db = att * env_db + (1.0 - att) * level_db
            else:
                env_db = rel * env_db + (1.0 - rel) * level_db
            if env_db > thr:
                # overshoot compressed
                gains[i] = _db_to_lin(-(env_db - thr) * slope) * makeup
            else:
                gains[i] = makeup
        self._env_db = float(env_db)
        return (x_arr * np.asarray(gains)).astype(np.float32)


class GraphicEQ:
    """Five peaking filters in series."""

    def __init__(self, gains_db: Optional[Sequence[float]] = None) -> None:
        g = list(gains_db) if gains_db is not None else [0.0] * 5
        while len(g) < 5:
            g.append(0.0)
        self.gains_db = [float(x) for x in g[:5]]
        self._filters: List[BiquadPeak] = [BiquadPeak() for _ in range(5)]
        self._sr = 0
        # sosfilt 路径的系数与状态。_sos 为 None 表示这一轮全是直通段。
        self._sos: Any = None
        self._zi: Any = None

    def set_gains(self, gains_db: Sequence[float]) -> None:
        g = [float(x) for x in gains_db[:5]]
        while len(g) < 5:
            g.append(0.0)
        # Hot-param path re-pushes the same gains every slider tick; redesigning
        # zeroes biquad state and causes clicks in live audio (review #37).
        if len(self.gains_db) >= 5 and all(
            abs(float(a) - float(b)) < 1e-6 for a, b in zip(self.gains_db[:5], g)
        ):
            return
        self.gains_db = g
        self._sr = 0  # force redesign

    def apply_preset(self, name: str) -> None:
        key = (name or "flat").strip().lower()
        if key not in EQ_PRESETS:
            # map Chinese labels
            for k, lab in EQ_PRESET_LABELS.items():
                if lab == name or k == key:
                    key = k
                    break
            else:
                key = "flat"
        self.set_gains(EQ_PRESETS[key])

    def _ensure(self, sr: int) -> None:
        if sr == self._sr:
            return
        self._sr = sr
        self._filters = [
            BiquadPeak.design(sr, EQ_FREQS[i], self.gains_db[i], q=1.1)
            for i in range(5)
        ]
        self._sos = None
        self._zi = None
        if _sosfilt() is None:
            return
        rows = [f.sos_row() for f in self._filters if not f.is_bypass()]
        if not rows:
            return
        np = _numpy()
        self._sos = np.asarray(rows, dtype=np.float64)
        self._zi = np.zeros((len(rows), 2), dtype=np.float64)

    def reset(self) -> None:
        for f in self._filters:
            f.reset()
        if self._zi is not None:
            self._zi[:] = 0.0

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        self._ensure(sr)
        # 有 scipy 就整条链一次 sosfilt。差分方程和状态约定跟 BiquadPeak.process
        # 完全一致（都是转置直接 II 型），只是递归跑在 C 里而不是 Python 里。
        # 这一段原本占整条效果链六成开销。
        sosfilt = _sosfilt()
        if sosfilt is not None and self._sos is not None:
            y, self._zi = sosfilt(
                self._sos, np.asarray(x, dtype=np.float64), zi=self._zi
            )
            return y.astype(np.float32)
        if sosfilt is not None:
            # 五段全直通，别白跑一趟。
            return x.astype(np.float32, copy=False)
        y = x.astype(np.float32, copy=False)
        for f in self._filters:
            y = f.process(y)
        return y.astype(np.float32, copy=False)


# ---------------------------------------------------------------------------
# Chain
# ---------------------------------------------------------------------------


DEFAULT_FX_CONFIG: Dict[str, Any] = {
    "fx_enabled": False,
    "fx_gate_enabled": True,
    "fx_gate_threshold_db": -50.0,
    "fx_gate_release_ms": 50.0,
    "fx_gate_hold_ms": 20.0,
    "fx_gate_range_db": 20.0,
    "fx_comp_enabled": True,
    "fx_comp_threshold_db": -20.0,
    "fx_comp_ratio": 4.0,
    "fx_comp_attack_ms": 5.0,
    "fx_comp_release_ms": 100.0,
    "fx_comp_makeup_db": 0.0,
    "fx_eq_enabled": True,
    "fx_eq_gains": [0.0, 0.0, 0.0, 0.0, 0.0],
    "fx_eq_preset": "flat",
    "fx_out_gain_db": 0.0,
}


class RealtimeFxChain:
    """Stateful post-FX chain for realtime VC output."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.gate = NoiseGate()
        self.comp = Compressor()
        self.eq = GraphicEQ()
        self.enabled = False
        self.gate_enabled = True
        self.comp_enabled = True
        self.eq_enabled = True
        self.out_gain_db = 0.0
        self.eq_preset = "flat"
        if config:
            self.apply_config(config)

    def apply_config(self, cfg: Dict[str, Any]) -> None:
        c = {**DEFAULT_FX_CONFIG, **(cfg or {})}
        self.enabled = bool(c.get("fx_enabled"))
        self.gate_enabled = bool(c.get("fx_gate_enabled", True))
        self.comp_enabled = bool(c.get("fx_comp_enabled", True))
        self.eq_enabled = bool(c.get("fx_eq_enabled", True))
        self.out_gain_db = float(c.get("fx_out_gain_db") or 0.0)
        self.eq_preset = str(c.get("fx_eq_preset") or "flat")

        self.gate.configure(
            threshold_db=c.get("fx_gate_threshold_db", -50),
            release_ms=c.get("fx_gate_release_ms", 50),
            hold_ms=c.get("fx_gate_hold_ms", 20),
            range_db=c.get("fx_gate_range_db", 20),
        )
        self.comp.configure(
            threshold_db=c.get("fx_comp_threshold_db", -20),
            ratio=c.get("fx_comp_ratio", 4),
            attack_ms=c.get("fx_comp_attack_ms", 5),
            release_ms=c.get("fx_comp_release_ms", 100),
            makeup_db=c.get("fx_comp_makeup_db", 0),
        )
        gains = c.get("fx_eq_gains")
        if isinstance(gains, (list, tuple)) and len(gains) >= 1:
            self.eq.set_gains(gains)
        else:
            self.eq.apply_preset(self.eq_preset)

    def to_config(self) -> Dict[str, Any]:
        return {
            "fx_enabled": self.enabled,
            "fx_gate_enabled": self.gate_enabled,
            "fx_gate_threshold_db": self.gate.threshold_db,
            "fx_gate_release_ms": self.gate.release_ms,
            "fx_gate_hold_ms": self.gate.hold_ms,
            "fx_gate_range_db": self.gate.range_db,
            "fx_comp_enabled": self.comp_enabled,
            "fx_comp_threshold_db": self.comp.threshold_db,
            "fx_comp_ratio": self.comp.ratio,
            "fx_comp_attack_ms": self.comp.attack_ms,
            "fx_comp_release_ms": self.comp.release_ms,
            "fx_comp_makeup_db": self.comp.makeup_db,
            "fx_eq_enabled": self.eq_enabled,
            "fx_eq_gains": list(self.eq.gains_db),
            "fx_eq_preset": self.eq_preset,
            "fx_out_gain_db": self.out_gain_db,
        }

    def reset(self) -> None:
        self.gate.reset()
        self.comp.reset()
        self.eq.reset()

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        if x is None or x.size == 0:
            return x
        if not self.enabled:
            return x.astype(np.float32, copy=False)
        y = np.asarray(x, dtype=np.float32).reshape(-1)
        if self.gate_enabled:
            y = self.gate.process(y, sr)
        if self.comp_enabled:
            y = self.comp.process(y, sr)
        if self.eq_enabled:
            y = self.eq.process(y, sr)
        if abs(self.out_gain_db) > 1e-6:
            y = (y * np.float32(_db_to_lin(self.out_gain_db))).astype(np.float32)
        # soft clip to ±1
        y = np.tanh(y.astype(np.float64, copy=False)).astype(np.float32)
        return y


def extract_fx_config(d: Dict[str, Any]) -> Dict[str, Any]:
    """Pull fx_* keys from a flat config dict."""
    out = dict(DEFAULT_FX_CONFIG)
    for k in DEFAULT_FX_CONFIG:
        if k in d and d[k] is not None:
            out[k] = d[k]
    # normalize gains
    g = out.get("fx_eq_gains")
    if isinstance(g, (list, tuple)):
        out["fx_eq_gains"] = [float(x) for x in list(g)[:5]] + [0.0] * max(
            0, 5 - len(g)
        )
        out["fx_eq_gains"] = out["fx_eq_gains"][:5]
    return out
