# -*- coding: utf-8 -*-
"""无模型 DSP 变声：不用 RVC、不用显卡、不用 torch。

Clownfish 那一票梗声（高音、机器人、无线电、外星人…）本质就是几个便宜的
时域/频域效果器串起来。这里把它们做全，并且补上 Clownfish 做不到的那件事：
**变调和共振峰可以分开调**。

Clownfish 只有一个「变调」，升调时共振峰跟着一起搬，所以必然「花栗鼠」，
降调必然「巨人」。分开之后：

* 只动 pitch → 花栗鼠（梗声要的就是这个，保留）
* pitch 和 formant 反向配平 → 干净的男女声互换，没有塑料味
* 只动 formant → 音高不变、音色变粗变细

依赖只有 numpy，scipy 可选（滤波走 sosfilt 会快一个量级，没有就退回纯
Python 双二阶）。跟 tools/dsp_fx 一样，numpy 是惰性导入的——冻结的主程序壳
要 import 这里的常量来画界面，但壳里没有 numpy。

每个效果器都是块间保持状态的：相位、延迟线、重叠缓冲都留在实例上，
`process(x, sr)` 可以一块一块地喂。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

if TYPE_CHECKING:
    import numpy as np

# ---------------------------------------------------------------------------
# 效果器清单 —— 壳按这个画界面，顺序就是信号链顺序
# ---------------------------------------------------------------------------

# id, 中文名, 默认参数
EFFECT_SPECS: Dict[str, Dict[str, Any]] = {
    "pitch": {
        "label": "变调",
        "params": {"semitones": 0.0},
        "ranges": {"semitones": (-24.0, 24.0)},
    },
    "formant": {
        "label": "共振峰",
        "params": {"shift": 0.0},
        "ranges": {"shift": (-12.0, 12.0)},
    },
    "whisper": {
        "label": "耳语",
        "params": {"amount": 0.0},
        "ranges": {"amount": (0.0, 1.0)},
    },
    "ring": {
        "label": "环形调制",
        "params": {"freq": 50.0, "mix": 0.0},
        "ranges": {"freq": (5.0, 2000.0), "mix": (0.0, 1.0)},
    },
    "vibrato": {
        "label": "颤音",
        "params": {"rate": 5.0, "depth": 0.0},
        "ranges": {"rate": (0.1, 20.0), "depth": (0.0, 30.0)},
    },
    "chorus": {
        "label": "合唱",
        "params": {"depth": 0.0, "rate": 0.7, "voices": 2},
        "ranges": {"depth": (0.0, 1.0), "rate": (0.05, 5.0), "voices": (2, 3)},
    },
    "bitcrush": {
        "label": "位深压缩",
        "params": {"bits": 16, "downsample": 1},
        "ranges": {"bits": (2, 16), "downsample": (1, 32)},
    },
    "drive": {
        "label": "过载",
        "params": {"amount": 0.0},
        "ranges": {"amount": (0.0, 1.0)},
    },
    "radio": {
        "label": "限带",
        "params": {"low": 300.0, "high": 3400.0, "mix": 0.0, "noise": 0.0},
        "ranges": {
            "low": (50.0, 2000.0),
            "high": (1000.0, 12000.0),
            "mix": (0.0, 1.0),
            "noise": (0.0, 0.5),
        },
    },
    "echo": {
        "label": "回声",
        "params": {"time_ms": 180.0, "feedback": 0.3, "mix": 0.0},
        "ranges": {"time_ms": (10.0, 1000.0), "feedback": (0.0, 0.9), "mix": (0.0, 1.0)},
    },
    "reverb": {
        "label": "混响",
        "params": {"size": 0.5, "mix": 0.0},
        "ranges": {"size": (0.0, 1.0), "mix": (0.0, 1.0)},
    },
}

# 信号链顺序。变调/共振峰在最前（它们决定音色），空间效果在最后。
CHAIN_ORDER: tuple[str, ...] = (
    "pitch",
    "formant",
    "whisper",
    "ring",
    "vibrato",
    "chorus",
    "bitcrush",
    "drive",
    "radio",
    "echo",
    "reverb",
)


def default_chain() -> Dict[str, Dict[str, Any]]:
    """全部效果器的默认参数（等于「什么都不做」）。"""
    return {k: dict(v["params"]) for k, v in EFFECT_SPECS.items()}


def clamp_params(effect: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """按 EFFECT_SPECS 的范围钳住参数。预设是可以手写/下载的，不能信。"""
    spec = EFFECT_SPECS.get(effect)
    if not spec:
        return {}
    out = dict(spec["params"])
    ranges = spec.get("ranges", {})
    for k, default in spec["params"].items():
        if k not in params:
            continue
        try:
            v = float(params[k])
        except (TypeError, ValueError):
            continue
        if not math.isfinite(v):
            continue
        lo, hi = ranges.get(k, (float("-inf"), float("inf")))
        v = min(max(v, lo), hi)
        out[k] = int(round(v)) if isinstance(default, int) else v
    return out


def _numpy():
    import numpy as np

    return np


_UNSET = object()
_SOSFILT_CACHE: Any = _UNSET


def _sosfilt():
    global _SOSFILT_CACHE
    if _SOSFILT_CACHE is _UNSET:
        try:
            from scipy.signal import sosfilt

            _SOSFILT_CACHE = sosfilt
        except Exception:
            _SOSFILT_CACHE = None
    return _SOSFILT_CACHE


def semitones_to_ratio(st: float) -> float:
    return float(2.0 ** (float(st) / 12.0))


# ---------------------------------------------------------------------------
# 基础件
# ---------------------------------------------------------------------------


class _Tail:
    """块间的历史缓冲。延迟线、变调器、重叠窗都靠它跨块取到前面的样本。"""

    def __init__(self, size: int) -> None:
        self.size = max(1, int(size))
        self._buf: Any = None

    def reset(self) -> None:
        self._buf = None

    def resize(self, size: int) -> None:
        size = max(1, int(size))
        if size == self.size:
            return
        self.size = size
        self._buf = None

    def extend(self, x: "np.ndarray") -> "np.ndarray":
        """返回 [历史, x]，并把新的尾巴存下来。"""
        np = _numpy()
        if self._buf is None or self._buf.shape[0] != self.size:
            self._buf = np.zeros(self.size, dtype=np.float64)
        joined = np.concatenate([self._buf, np.asarray(x, dtype=np.float64)])
        self._buf = joined[-self.size :].copy()
        return joined


class PitchShifter:
    """WSOLA 时间伸缩 + 重采样。

    先按 r 倍把时间拉长（音高不变），再按 r 倍加速播放（音高 ×r、时长还原）。

    最初写的是「两个读指针相差半个窗、sin/cos 交叉淡化」那套廉价延迟线变调器
    —— Clownfish 那一类用的就是它。实测在持续音上会**整段归零**：两个抽头差
    半个窗，遇上窗长恰好是半周期奇数倍的音就是反相抵消，梳状零点，听感是持续
    元音一顿一顿的。两个抽头各自都要覆盖大半个周期，这个抵消绕不开。

    WSOLA 多做一件事就解决了：拼接前先在一个搜索范围里找互相关最大的位置，
    保证重叠的两段波形同相。代价是每帧一次相关，块预算里够。
    """

    FRAME_MS = 21.0      # 帧长，约 1024 点 @48k
    SEARCH_MS = 5.0      # 相关搜索半径

    def __init__(self, semitones: float = 0.0) -> None:
        self.semitones = float(semitones)
        self._sr = 0
        self._frame = 0
        self._hop_s = 0
        self._search = 0
        self._win: Any = None
        self._in_buf: Any = None     # 输入历史（含还没分析到的前瞻）
        self._ana = 0                # 下一帧的名义分析位置，_in_buf 上的下标
        self._out_buf: Any = None    # 已拉伸、待重采样读出的样本
        self._out_valid = 0          # _out_buf 里已定稿的长度
        self._read_pos = 0.0         # 重采样读指针（浮点）
        self._prev_tail: Any = None  # 上一帧尾巴，用来做相关对齐
        self._primed = False         # 储备够了没

    def reset(self) -> None:
        self._in_buf = None
        self._ana = 0
        self._out_buf = None
        self._out_valid = 0
        self._read_pos = 0.0
        self._prev_tail = None
        self._primed = False

    def _ensure(self, sr: int) -> None:
        np = _numpy()
        if sr == self._sr and self._win is not None:
            return
        self._sr = sr
        self._frame = max(128, int(sr * self.FRAME_MS * 0.001) // 2 * 2)
        self._hop_s = self._frame // 2
        self._hop_eff = self._hop_s
        self._search = max(8, int(sr * self.SEARCH_MS * 0.001))
        self._win = np.hanning(self._frame + 1)[: self._frame].astype(np.float64)
        self.reset()

    def _stretch_more(self, ratio: float) -> None:
        """有多少前瞻就拉伸多少帧。

        这里用的是「绝对分析指针 _ana」而不是「从 _in_buf 头上切掉已消费部分」。
        切头那种写法把「还剩多少没分析」和「还剩多少前瞻」混成了一个数，于是
        每帧都要求缓冲里有 frame + 2*search 个**未消费**样本；而稳态下每块进
        多少就消耗多少，缓冲一旦落在这个门槛之下就再也攒不够——读指针被钳住，
        输出退化成同一个样本重复（听感是一声长嗡），512 点块长下必现。

        分开之后：_ana 每帧前进 hop_a，每块推进 n（因为要产 n*ratio 个输出、
        每帧产 hop_s、hop_a = hop_s/ratio），跟输入增长速度天然相等，
        前瞻余量恒定，没有死区。
        """
        np = _numpy()
        frame, search = self._frame, self._search
        # 合成跳距默认取半帧（Hann 在半帧重叠下窗和恒为 1，直接叠加即可）。
        #
        # 但降调时分析跳距 hop_a = hop_s / ratio 会被拉长，ratio 小到一定程度
        # 就超过帧长，前后两帧根本不重叠、中间还漏掉一段输入 —— -24 半音
        # （ratio=0.25，hop_a=2016 > 帧长 1008）实测出来是 905Hz，跟目标的
        # 50Hz 毫无关系。所以极端降调要把合成跳距一起调小，保证 hop_a 始终
        # 落在帧内、帧与帧还有重叠。
        hop_s = self._hop_s
        if ratio < 1.0:
            hop_s = max(64, min(hop_s, int(frame * ratio * 0.75)))
        hop_a = max(1, int(round(hop_s / ratio)))
        # 跳距不再是半帧时 Hann 的窗和不等于 1，要补回去，否则音量随设置变。
        gain = 2.0 * hop_s / frame
        self._hop_eff = hop_s
        n_in = self._in_buf.shape[0]
        # 有多少前瞻就产多少，不设产量上限。
        #
        # 之前给 _out_valid 加过一个 frame*6 的天花板，结果是产量被卡住、分析
        # 指针跟不上输入速度，_in_buf 只涨不落（-5 半音跑 30 秒能堆到 36 万个
        # float64）。产量本来就该等于「输入 × ratio」，而下游每块正好消耗
        # n × ratio，两边天然相等；卡住产量等于人为制造失衡。
        # _out_buf 的长度由 process 末尾那次搬移单独兜着，不靠这个天花板。
        while self._ana + frame + search <= n_in:
            start = self._ana
            tail = self._prev_tail
            if tail is not None and tail.size:
                lo = max(0, self._ana - search)
                hi = min(n_in - frame, self._ana + search)
                if hi >= lo:
                    seg = self._in_buf[lo : hi + tail.size]
                    if seg.shape[0] >= tail.size:
                        corr = np.correlate(seg, tail, mode="valid")
                        if corr.size:
                            start = lo + int(np.argmax(corr))
            start = max(0, min(start, n_in - frame))
            end = self._out_valid + frame
            if self._out_buf.shape[0] < end:
                grown = np.zeros(end * 2, dtype=np.float64)
                grown[: self._out_buf.shape[0]] = self._out_buf
                self._out_buf = grown
            self._out_buf[self._out_valid : end] += (
                self._in_buf[start : start + frame] * self._win * gain
            )
            # 重叠一半，所以这一帧只有前 hop_s 个是定稿的
            self._out_valid += hop_s
            self._prev_tail = self._in_buf[start + hop_s : start + hop_s * 2].copy()
            # 名义分析位置只按 hop_a 走，**不**从搜出来的 start 接着往下走。
            #
            # 接着 start 走的话，相关搜索的偏移会一路累积。周期信号上尤其明显：
            # 互相关的峰在基音周期的整数倍上，搜索窗一宽，start 就被吸到最近的
            # 周期倍数，于是每帧的实际前进量被量化成周期的倍数，伸缩比不再是
            # hop_s/hop_a。累积下来音高就飘了 —— 实测 -5 半音在 512 点块长下
            # 落到 100Hz（应为 149.8Hz），而 1024 点块长恰好没飘，正是因为
            # 两者的累积相位不同。
            #
            # 名义位置独立推进，每帧只在它附近 ±search 找对齐点，平均前进量就
            # 严格等于 hop_a，单帧的吸附只影响波形拼接、不影响整体速率。
            self._ana += hop_a

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        self._ensure(sr)
        ratio = semitones_to_ratio(self.semitones)
        n = int(np.size(x))
        if n == 0 or abs(ratio - 1.0) < 1e-6:
            return np.asarray(x, dtype=np.float32)

        xs = np.asarray(x, dtype=np.float64)
        if self._in_buf is None:
            self._in_buf = xs.copy()
            self._out_buf = np.zeros(self._frame * 8, dtype=np.float64)
            self._out_valid = 0
            self._read_pos = 0.0
            self._ana = 0
        else:
            self._in_buf = np.concatenate([self._in_buf, xs])

        self._stretch_more(ratio)

        # 分析指针走远了就把前面的历史丢掉，指针跟着往回挪。保留 search 的余量，
        # 相关搜索还要往回看一点。
        drop = self._ana - self._search
        if drop > self._frame * 4:
            self._in_buf = self._in_buf[drop:].copy()
            self._ana -= drop

        # 储备量：先攒够这些再出声。要跟着块长走 —— 固定值时 512 点块长降调会
        # 周期性欠载，而欠载曾经会退回预热放干声，实测输出里同时有 150Hz
        # （变调后）和 196Hz（干声），听感是变调和原声交替出现。
        #
        # 降调时每帧的分析指针比一块输入走得还快（hop_a > n），要好几块才攒得
        # 出一帧，产量天生一阵一阵的，储备就是用来吸收这个抖动。
        reserve = self._frame * 3 + int(n * ratio * 2)

        # 积压上限。读指针落后太多说明下游一时没跟上，直接跳过陈旧的部分：
        # 既是内存上限，也是延迟上限——变声器攒一秒的「以前的声音」没有意义。
        #
        # 必须比 reserve 大。反过来的话 _out_valid 会被这里按住在 max_lag，
        # 永远够不到 reserve，于是永远停在预热、一直放干声。
        max_lag = reserve + self._frame * 2
        if self._out_valid - self._read_pos > max_lag:
            self._read_pos = float(self._out_valid - max_lag)

        # 预热：先攒够储备再出声，只在最开头做一次。
        #
        # 不留储备的话，每块读指针都会一路顶到 _out_valid，然后压缩把整个缓冲
        # 清空，下一块又从零开始追。储备是用来吸收「帧是离散的、块也是离散的」
        # 这点抖动的：降调时每帧的分析指针比输入走得快（hop_a > 块长），
        # 所以要好几块才攒得出一帧，产量天然是一阵一阵的。
        #
        if not self._primed:
            if self._out_valid < reserve:
                # 只有开头这一次放干声：算法本身有固有延迟，与其静音一下，
                # 不如让用户听到没变调的原声，几十毫秒后自然接上。
                self._compact()
                return np.asarray(x, dtype=np.float32)
            self._primed = True

        pos = self._read_pos + np.arange(n, dtype=np.float64) * ratio
        if pos[-1] + 1.0 >= self._out_valid:
            # 欠载：钳在已定稿区间内（相当于把最后一个样本拖一下）。
            # **不**退回预热 —— 那会把干声混进来，比拖一下难听得多。
            np.clip(pos, 0.0, float(max(1, self._out_valid) - 1), out=pos)
        i0 = pos.astype(np.int64)
        frac = pos - i0
        y = self._out_buf[i0] * (1.0 - frac) + self._out_buf[i0 + 1] * frac
        self._read_pos = float(pos[-1]) + ratio
        self._compact()
        return y.astype(np.float32)

    def _compact(self) -> None:
        """把读过的部分挪走。必须每块都跑，包括预热那条早退路径。

        早退时不压缩的话，那一块产出的样本没人消费，_out_valid 就被顶高一截；
        欠载会周期性地把状态打回预热，于是每次都再顶高一点 —— _stretch_more
        按 end*2 扩容，容量随之翻倍上去，-5 半音跑 30 秒能到 36 万个 float64。

        只搬 [shift, _out_valid + frame) 这一段，不能把整条尾巴照搬，
        否则容量同样只涨不落。有效数据从来只有这么多。
        """
        np = _numpy()
        shift = int(self._read_pos)
        if shift <= 0 or self._out_buf is None:
            return
        live_end = min(self._out_valid + self._frame, self._out_buf.shape[0])
        if shift > live_end:
            return
        keep = self._out_buf[shift:live_end].copy()
        cap = max(self._frame * 8, keep.shape[0] + self._frame)
        self._out_buf = np.zeros(cap, dtype=np.float64)
        self._out_buf[: keep.shape[0]] = keep
        self._out_valid = max(0, self._out_valid - shift)
        self._read_pos -= shift



class _StftEffect:
    """按 hop 对齐的 STFT 重叠相加骨架。

    子类只要实现 `_transform(spec, bins)` 返回改过的频谱即可。

    为什么要 FIFO 而不是「每块自己算几帧、尾巴留到下一块」：块长不是 hop 的
    整数倍时（比如 480 对 128），帧网格和块边界永远对不齐，末尾那截输入既进不
    了这一块的帧、下一块又按新的 pad 去切，结果是每块丢掉几十个样本 —— 实测
    480 点块长下 97% 的样本都跟 1024 点块长对不上。用输入/输出两个 FIFO 把
    「块长」和「hop」彻底解耦，块长爱是多少是多少。

    代价是固定 N_FFT - HOP 个样本的算法延迟（512/128 @48k = 8ms），
    这本来就是 STFT 该付的。
    """

    N_FFT = 512
    HOP = 128

    def __init__(self) -> None:
        self._sr = 0
        self._win: Any = None
        self._in_fifo: Any = None    # 还没进过帧的输入
        self._accum: Any = None      # 正在重叠相加的窗口
        self._out_fifo: Any = None   # 已定稿、等着输出的样本
        self._bins = self.N_FFT // 2 + 1

    def reset(self) -> None:
        self._in_fifo = None
        self._accum = None
        self._out_fifo = None

    def _ensure(self, sr: int) -> None:
        np = _numpy()
        if sr == self._sr and self._win is not None:
            return
        self._sr = sr
        # Hann 的平方和在 hop = N/4 时恒定，直接重叠相加不用再除归一化
        self._win = np.hanning(self.N_FFT + 1)[: self.N_FFT].astype(np.float64)
        self.reset()

    def _bypass(self) -> bool:
        return True

    def _transform(self, spec, bins):
        return spec

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        self._ensure(sr)
        n = int(np.size(x))
        if n == 0 or self._bypass():
            return np.asarray(x, dtype=np.float32)

        if self._in_fifo is None:
            self._in_fifo = np.zeros(0, dtype=np.float64)
            self._accum = np.zeros(self.N_FFT, dtype=np.float64)
            # 预填 N_FFT 个零 —— 这就是这套算法的固有延迟。
            #
            # 不能只填 N_FFT - HOP：每次调用产出的是 HOP 的整数倍，跟请求的 n
            # 不一定对得上，累计缺口最坏能到 (N_FFT - HOP) + (HOP - 1)。填少了
            # 第一次调用就欠载，补零 + 清空 FIFO 之后对齐永久错位 —— 实测
            # 480 / 333 这种非 HOP 整数倍的块长从第 400 个样本起就跟 1024 分岔。
            self._out_fifo = np.zeros(self.N_FFT, dtype=np.float64)
        self._in_fifo = np.concatenate([self._in_fifo, np.asarray(x, dtype=np.float64)])

        produced = []
        while self._in_fifo.shape[0] >= self.N_FFT:
            seg = self._in_fifo[: self.N_FFT] * self._win
            spec = np.fft.rfft(seg)
            frame = np.fft.irfft(self._transform(spec, self._bins), n=self.N_FFT)
            self._accum += frame * self._win
            produced.append(self._accum[: self.HOP].copy())
            # 窗口左移一个 hop，尾部补零等下一帧叠上来
            self._accum = np.concatenate(
                [self._accum[self.HOP :], np.zeros(self.HOP, dtype=np.float64)]
            )
            self._in_fifo = self._in_fifo[self.HOP :]
        if produced:
            self._out_fifo = np.concatenate([self._out_fifo] + produced)

        if self._out_fifo.shape[0] >= n:
            y = self._out_fifo[:n]
            self._out_fifo = self._out_fifo[n:].copy()
        else:
            # 只会发生在最开头
            y = np.zeros(n, dtype=np.float64)
            y[: self._out_fifo.shape[0]] = self._out_fifo
            self._out_fifo = np.zeros(0, dtype=np.float64)
        return y.astype(np.float32)


class FormantShifter(_StftEffect):
    """独立共振峰搬移：STFT → 实倒谱取包络 → 沿频率轴拉伸 → 还原。

    Clownfish 没有这个。分开之后，「升八度但嗓子还是原来那把」才做得出来。
    """

    # 倒谱里前多少个系数算「包络」。24 对应约 4ms 的谱平滑，够把共振峰和基频分开。
    LIFTER = 24

    def __init__(self, shift_semitones: float = 0.0) -> None:
        super().__init__()
        self.shift_semitones = float(shift_semitones)
        self._map: Any = None
        self._map_key = None

    def _bypass(self) -> bool:
        return abs(semitones_to_ratio(self.shift_semitones) - 1.0) < 1e-6

    def _warp_map(self, bins: int):
        """频率轴上的重采样映射：新包络[k] = 旧包络[k/alpha]。alpha 不变就复用。"""
        np = _numpy()
        alpha = semitones_to_ratio(self.shift_semitones)
        key = (bins, round(alpha, 9))
        if key != self._map_key:
            src = np.arange(bins, dtype=np.float64) / alpha
            np.clip(src, 0, bins - 1, out=src)
            i0 = src.astype(np.int64)
            self._map = (i0, np.minimum(i0 + 1, bins - 1), src - i0)
            self._map_key = key
        return self._map

    def _transform(self, spec, bins):
        np = _numpy()
        i0, i1, frac = self._warp_map(bins)
        log_mag = np.log(np.abs(spec) + 1e-10)
        # 实倒谱的低阶部分就是谱包络
        cep = np.fft.irfft(log_mag, n=self.N_FFT)
        cep[self.LIFTER : self.N_FFT - self.LIFTER + 1] = 0.0
        env = np.exp(np.fft.rfft(cep).real)
        warped = env[i0] * (1.0 - frac) + env[i1] * frac
        gain = warped / (env + 1e-10)
        np.clip(gain, 0.0, 8.0, out=gain)
        return spec * gain


class Whisper(_StftEffect):
    """把激励换成噪声、保留谱包络。amount 是干湿比。"""

    def __init__(self, amount: float = 0.0) -> None:
        super().__init__()
        self.amount = float(amount)
        self._rng: Any = None

    def _bypass(self) -> bool:
        return min(max(self.amount, 0.0), 1.0) <= 1e-6

    def _transform(self, spec, bins):
        np = _numpy()
        if self._rng is None:
            self._rng = np.random.default_rng(0xA17E)
        amt = min(max(self.amount, 0.0), 1.0)
        # 幅度保留、相位换成随机 —— 谐波结构没了，共振峰还在
        phase = self._rng.uniform(-np.pi, np.pi, size=bins)
        noisy = np.abs(spec) * (np.cos(phase) + 1j * np.sin(phase))
        return spec * (1.0 - amt) + noisy * amt


class RingMod:
    """环形调制。相位跨块连续，不然每块开头都有一下咔哒。"""

    def __init__(self, freq: float = 50.0, mix: float = 0.0) -> None:
        self.freq = float(freq)
        self.mix = float(mix)
        self._phase = 0.0

    def reset(self) -> None:
        self._phase = 0.0

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        mix = min(max(self.mix, 0.0), 1.0)
        if mix <= 1e-6:
            return np.asarray(x, dtype=np.float32)
        n = int(np.size(x))
        if n == 0:
            return np.asarray(x, dtype=np.float32)
        w = 2.0 * np.pi * float(self.freq) / float(sr)
        ph = self._phase + w * np.arange(n, dtype=np.float64)
        self._phase = float((self._phase + w * n) % (2.0 * np.pi))
        x_arr = np.asarray(x, dtype=np.float64)
        return (x_arr * (1.0 - mix) + x_arr * np.cos(ph) * mix).astype(np.float32)


class Vibrato:
    """音高颤音：延迟线随 LFO 起伏，读出来就是周期性的音高摆动。"""

    MAX_DELAY_MS = 12.0

    def __init__(self, rate: float = 5.0, depth: float = 0.0) -> None:
        self.rate = float(rate)
        self.depth = float(depth)  # 音分
        self._sr = 0
        self._tail = _Tail(1)
        self._phase = 0.0

    def reset(self) -> None:
        self._tail.reset()
        self._phase = 0.0

    def _ensure(self, sr: int) -> None:
        if sr == self._sr:
            return
        self._sr = sr
        self._tail.resize(int(sr * self.MAX_DELAY_MS * 0.001) + 4)

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        self._ensure(sr)
        depth = max(0.0, float(self.depth))
        if depth <= 1e-6:
            return np.asarray(x, dtype=np.float32)
        n = int(np.size(x))
        if n == 0:
            return np.asarray(x, dtype=np.float32)
        hist = self._tail.size
        buf = self._tail.extend(x)
        w = 2.0 * np.pi * float(self.rate) / float(sr)
        ph = self._phase + w * np.arange(n, dtype=np.float64)
        self._phase = float((self._phase + w * n) % (2.0 * np.pi))
        # depth 是音分；换算成延迟摆幅（经验系数，够用就行）
        sweep = (depth / 100.0) * (sr * 0.0012)
        center = hist * 0.5
        d = center + sweep * np.sin(ph)
        np.clip(d, 1.0, hist - 2.0, out=d)
        pos = np.arange(n, dtype=np.float64) + hist - d
        i0 = pos.astype(np.int64)
        frac = pos - i0
        y = buf[i0] * (1.0 - frac) + buf[i0 + 1] * frac
        return y.astype(np.float32)


class Chorus:
    """两三个轻微失谐的延迟拷贝叠在一起，一个人唱成一群。"""

    MAX_DELAY_MS = 40.0

    def __init__(self, depth: float = 0.0, rate: float = 0.7, voices: int = 2) -> None:
        self.depth = float(depth)
        self.rate = float(rate)
        self.voices = int(voices)
        self._sr = 0
        self._tail = _Tail(1)
        self._phase = 0.0

    def reset(self) -> None:
        self._tail.reset()
        self._phase = 0.0

    def _ensure(self, sr: int) -> None:
        if sr == self._sr:
            return
        self._sr = sr
        self._tail.resize(int(sr * self.MAX_DELAY_MS * 0.001) + 4)

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        self._ensure(sr)
        depth = min(max(self.depth, 0.0), 1.0)
        if depth <= 1e-6:
            return np.asarray(x, dtype=np.float32)
        n = int(np.size(x))
        if n == 0:
            return np.asarray(x, dtype=np.float32)
        hist = self._tail.size
        buf = self._tail.extend(x)
        w = 2.0 * np.pi * float(self.rate) / float(sr)
        t = np.arange(n, dtype=np.float64)
        self_ph = self._phase
        self._phase = float((self._phase + w * n) % (2.0 * np.pi))
        base = np.arange(n, dtype=np.float64) + hist
        voices = max(2, min(3, self.voices))
        acc = np.asarray(x, dtype=np.float64) * (1.0 - depth * 0.5)
        span = hist * 0.35
        for v in range(voices):
            off = 2.0 * np.pi * v / voices
            d = hist * 0.5 + span * depth * np.sin(self_ph + w * t + off)
            np.clip(d, 1.0, hist - 2.0, out=d)
            pos = base - d
            i0 = pos.astype(np.int64)
            frac = pos - i0
            acc += (buf[i0] * (1.0 - frac) + buf[i0 + 1] * frac) * (depth / voices)
        return acc.astype(np.float32)


class BitCrush:
    """量化 + 采样保持。8-bit 游戏机那味。"""

    def __init__(self, bits: int = 16, downsample: int = 1) -> None:
        self.bits = int(bits)
        self.downsample = int(downsample)
        self._held = 0.0
        self._count = 0

    def reset(self) -> None:
        self._held = 0.0
        self._count = 0

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        bits = int(min(max(self.bits, 2), 16))
        ds = int(min(max(self.downsample, 1), 32))
        if bits >= 16 and ds <= 1:
            return np.asarray(x, dtype=np.float32)
        y = np.asarray(x, dtype=np.float64)
        n = y.shape[0]
        if n == 0:
            return np.asarray(x, dtype=np.float32)
        if ds > 1:
            # 采样保持：跨块要接着上一块的相位，不然块边界会多一次跳变。
            offset = (-self._count) % ds
            keep_idx = np.arange(offset, n, ds)
            src = np.empty(n, dtype=np.float64)
            if offset > 0:
                src[:offset] = self._held
            if keep_idx.size:
                held_vals = y[keep_idx]
                # 每个保持点覆盖到下一个保持点之前
                edges = np.concatenate([keep_idx, [n]])
                for k in range(keep_idx.size):
                    src[edges[k] : edges[k + 1]] = held_vals[k]
                self._held = float(held_vals[-1])
            elif offset >= n:
                src[:] = self._held
            self._count = (self._count + n) % ds
            y = src
        if bits < 16:
            levels = float(2 ** (bits - 1))
            y = np.round(y * levels) / levels
        return y.astype(np.float32)


class Drive:
    """软过载。amount 0→1 对应从干净到明显失真。"""

    def __init__(self, amount: float = 0.0) -> None:
        self.amount = float(amount)

    def reset(self) -> None:
        pass

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        amt = min(max(self.amount, 0.0), 1.0)
        if amt <= 1e-6:
            return np.asarray(x, dtype=np.float32)
        gain = 1.0 + amt * 24.0
        y = np.tanh(np.asarray(x, dtype=np.float64) * gain)
        # 补偿增益，别一开过载音量就窜上去
        return (y / math.tanh(gain)).astype(np.float32)


class BandLimit:
    """限带 + 底噪：对讲机 / 老收音机。"""

    def __init__(
        self,
        low: float = 300.0,
        high: float = 3400.0,
        mix: float = 0.0,
        noise: float = 0.0,
    ) -> None:
        self.low = float(low)
        self.high = float(high)
        self.mix = float(mix)
        self.noise = float(noise)
        self._sr = 0
        self._key: tuple = ()
        self._sos: Any = None
        self._zi: Any = None
        self._biquads: List[Any] = []
        self._rng: Any = None

    def reset(self) -> None:
        if self._zi is not None:
            self._zi[:] = 0.0
        for b in self._biquads:
            b.reset()

    def _ensure(self, sr: int) -> None:
        np = _numpy()
        key = (sr, round(self.low, 3), round(self.high, 3))
        if key == self._key:
            return
        self._key = key
        self._sr = sr
        nyq = sr * 0.5
        lo = min(max(self.low, 20.0), nyq * 0.9)
        hi = min(max(self.high, lo * 1.5), nyq * 0.95)
        rows = [
            _highpass_sos(sr, lo),
            _lowpass_sos(sr, hi),
            # 中频抬一块，才像话筒不像蒙了层布
            _peak_sos(sr, math.sqrt(lo * hi), 6.0, 0.9),
        ]
        self._sos = np.asarray(rows, dtype=np.float64)
        self._zi = np.zeros((len(rows), 2), dtype=np.float64)
        self._biquads = [_BiquadState(r) for r in rows]
        if self._rng is None:
            self._rng = np.random.default_rng(0xB4D10)

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        mix = min(max(self.mix, 0.0), 1.0)
        if mix <= 1e-6:
            return np.asarray(x, dtype=np.float32)
        self._ensure(sr)
        dry = np.asarray(x, dtype=np.float64)
        if dry.shape[0] == 0:
            return np.asarray(x, dtype=np.float32)
        sosfilt = _sosfilt()
        if sosfilt is not None:
            wet, self._zi = sosfilt(self._sos, dry, zi=self._zi)
        else:
            wet = dry
            for b in self._biquads:
                wet = b.run(wet)
        noise = max(0.0, min(self.noise, 0.5))
        if noise > 1e-6:
            wet = wet + self._rng.standard_normal(dry.shape[0]) * noise * 0.05
        return (dry * (1.0 - mix) + wet * mix).astype(np.float32)


class Echo:
    """带反馈的延迟线。"""

    def __init__(self, time_ms: float = 180.0, feedback: float = 0.3, mix: float = 0.0):
        self.time_ms = float(time_ms)
        self.feedback = float(feedback)
        self.mix = float(mix)
        self._sr = 0
        self._buf: Any = None
        self._w = 0

    def reset(self) -> None:
        self._buf = None
        self._w = 0

    def _ensure(self, sr: int) -> None:
        np = _numpy()
        size = max(16, int(sr * min(max(self.time_ms, 1.0), 1000.0) * 0.001))
        if self._buf is not None and self._buf.shape[0] == size and sr == self._sr:
            return
        self._sr = sr
        self._buf = np.zeros(size, dtype=np.float64)
        self._w = 0

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        mix = min(max(self.mix, 0.0), 1.0)
        if mix <= 1e-6:
            return np.asarray(x, dtype=np.float32)
        self._ensure(sr)
        dry = np.asarray(x, dtype=np.float64)
        n = dry.shape[0]
        if n == 0:
            return np.asarray(x, dtype=np.float32)
        buf = self._buf
        size = buf.shape[0]
        fb = min(max(self.feedback, 0.0), 0.9)
        wet = np.empty(n, dtype=np.float64)
        w = self._w
        # 反馈让延迟线自我引用，这一段绕不开逐样本；size 通常几千，块只有一千，
        # 所以按「不跨越写指针环绕」的段落切开，段内可以整段读写。
        i = 0
        while i < n:
            room = min(n - i, size - w)
            seg = dry[i : i + room]
            delayed = buf[w : w + room].copy()
            wet[i : i + room] = delayed
            buf[w : w + room] = seg + delayed * fb
            w = (w + room) % size
            i += room
        self._w = w
        return (dry * (1.0 - mix) + wet * mix).astype(np.float32)


class Reverb:
    """Schroeder 混响：四个梳状滤波器并联，再串两级全通。"""

    COMB_MS = (29.7, 37.1, 41.1, 43.7)
    ALLPASS_MS = (5.0, 1.7)

    def __init__(self, size: float = 0.5, mix: float = 0.0) -> None:
        self.size = float(size)
        self.mix = float(mix)
        self._sr = 0
        self._combs: List[_DelayLine] = []
        self._aps: List[_DelayLine] = []

    def reset(self) -> None:
        for d in self._combs + self._aps:
            d.reset()

    def _ensure(self, sr: int) -> None:
        if sr == self._sr and self._combs:
            return
        self._sr = sr
        self._combs = [_DelayLine(int(sr * ms * 0.001)) for ms in self.COMB_MS]
        self._aps = [_DelayLine(int(sr * ms * 0.001)) for ms in self.ALLPASS_MS]

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        mix = min(max(self.mix, 0.0), 1.0)
        if mix <= 1e-6:
            return np.asarray(x, dtype=np.float32)
        self._ensure(sr)
        dry = np.asarray(x, dtype=np.float64)
        if dry.shape[0] == 0:
            return np.asarray(x, dtype=np.float32)
        size = min(max(self.size, 0.0), 1.0)
        fb = 0.70 + 0.28 * size
        wet = np.zeros_like(dry)
        for c in self._combs:
            wet += c.comb(dry, fb)
        wet /= len(self._combs)
        for a in self._aps:
            wet = a.allpass(wet, 0.5)
        return (dry * (1.0 - mix) + wet * mix).astype(np.float32)


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


class _DelayLine:
    """定长延迟线，提供梳状与全通两种接法。"""

    def __init__(self, size: int) -> None:
        self.size = max(4, int(size))
        self._buf: Any = None
        self._w = 0

    def reset(self) -> None:
        self._buf = None
        self._w = 0

    def _ensure(self) -> None:
        np = _numpy()
        if self._buf is None or self._buf.shape[0] != self.size:
            self._buf = np.zeros(self.size, dtype=np.float64)
            self._w = 0

    def comb(self, x: "np.ndarray", fb: float) -> "np.ndarray":
        np = _numpy()
        self._ensure()
        n = x.shape[0]
        out = np.empty(n, dtype=np.float64)
        w = self._w
        i = 0
        while i < n:
            room = min(n - i, self.size - w)
            delayed = self._buf[w : w + room].copy()
            out[i : i + room] = delayed
            self._buf[w : w + room] = x[i : i + room] + delayed * fb
            w = (w + room) % self.size
            i += room
        self._w = w
        return out

    def allpass(self, x: "np.ndarray", g: float) -> "np.ndarray":
        np = _numpy()
        self._ensure()
        n = x.shape[0]
        out = np.empty(n, dtype=np.float64)
        w = self._w
        i = 0
        while i < n:
            room = min(n - i, self.size - w)
            delayed = self._buf[w : w + room].copy()
            seg = x[i : i + room]
            out[i : i + room] = delayed - g * seg
            self._buf[w : w + room] = seg + delayed * g
            w = (w + room) % self.size
            i += room
        self._w = w
        return out


class _BiquadState:
    """没有 scipy 时用的双二阶。系数是 [b0,b1,b2,1,a1,a2]。"""

    def __init__(self, row: Sequence[float]) -> None:
        self.b0, self.b1, self.b2, _a0, self.a1, self.a2 = [float(v) for v in row]
        self.z1 = 0.0
        self.z2 = 0.0

    def reset(self) -> None:
        self.z1 = 0.0
        self.z2 = 0.0

    def run(self, x: "np.ndarray") -> "np.ndarray":
        np = _numpy()
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
        return np.asarray(ys, dtype=np.float64)


def _rbj(sr: int, freq: float, q: float):
    freq = float(min(max(freq, 10.0), 0.45 * sr))
    w0 = 2.0 * math.pi * freq / sr
    return math.cos(w0), math.sin(w0) / (2.0 * max(q, 0.05))


def _highpass_sos(sr: int, freq: float, q: float = 0.707) -> List[float]:
    cos_w, alpha = _rbj(sr, freq, q)
    b0 = (1.0 + cos_w) / 2.0
    b1 = -(1.0 + cos_w)
    b2 = b0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w
    a2 = 1.0 - alpha
    return [b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]


def _lowpass_sos(sr: int, freq: float, q: float = 0.707) -> List[float]:
    cos_w, alpha = _rbj(sr, freq, q)
    b1 = 1.0 - cos_w
    b0 = b1 / 2.0
    b2 = b0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w
    a2 = 1.0 - alpha
    return [b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]


def _peak_sos(sr: int, freq: float, gain_db: float, q: float = 1.0) -> List[float]:
    A = 10.0 ** (float(gain_db) / 40.0)
    cos_w, alpha = _rbj(sr, freq, q)
    b0 = 1.0 + alpha * A
    b1 = -2.0 * cos_w
    b2 = 1.0 - alpha * A
    a0 = 1.0 + alpha / A
    a1 = -2.0 * cos_w
    a2 = 1.0 - alpha / A
    return [b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]


# ---------------------------------------------------------------------------
# 整条链
# ---------------------------------------------------------------------------


_FACTORIES = {
    "pitch": lambda p: PitchShifter(p.get("semitones", 0.0)),
    "formant": lambda p: FormantShifter(p.get("shift", 0.0)),
    "whisper": lambda p: Whisper(p.get("amount", 0.0)),
    "ring": lambda p: RingMod(p.get("freq", 50.0), p.get("mix", 0.0)),
    "vibrato": lambda p: Vibrato(p.get("rate", 5.0), p.get("depth", 0.0)),
    "chorus": lambda p: Chorus(
        p.get("depth", 0.0), p.get("rate", 0.7), int(p.get("voices", 2))
    ),
    "bitcrush": lambda p: BitCrush(int(p.get("bits", 16)), int(p.get("downsample", 1))),
    "drive": lambda p: Drive(p.get("amount", 0.0)),
    "radio": lambda p: BandLimit(
        p.get("low", 300.0), p.get("high", 3400.0), p.get("mix", 0.0), p.get("noise", 0.0)
    ),
    "echo": lambda p: Echo(
        p.get("time_ms", 180.0), p.get("feedback", 0.3), p.get("mix", 0.0)
    ),
    "reverb": lambda p: Reverb(p.get("size", 0.5), p.get("mix", 0.0)),
}

# 参数名 → 实例属性名（大多同名，个别不同）
_PARAM_ATTR = {
    ("pitch", "semitones"): "semitones",
    ("formant", "shift"): "shift_semitones",
}


class VoiceChain:
    """一串效果器。参数可以热改，不重建实例，所以拖滑条不会断音。"""

    def __init__(self, params: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self._params: Dict[str, Dict[str, Any]] = default_chain()
        self._fx: Dict[str, Any] = {}
        for name in CHAIN_ORDER:
            self._fx[name] = _FACTORIES[name](self._params[name])
        if params:
            self.apply(params)

    @property
    def params(self) -> Dict[str, Dict[str, Any]]:
        return {k: dict(v) for k, v in self._params.items()}

    def apply(self, params: Dict[str, Dict[str, Any]]) -> None:
        """按预设更新参数。只改属性，不重建效果器——重建会清掉延迟线状态。"""
        for name in CHAIN_ORDER:
            incoming = params.get(name)
            if not isinstance(incoming, dict):
                continue
            clean = clamp_params(name, incoming)
            self._params[name] = clean
            fx = self._fx[name]
            for key, value in clean.items():
                setattr(fx, _PARAM_ATTR.get((name, key), key), value)

    def reset(self) -> None:
        for fx in self._fx.values():
            fx.reset()

    def active(self) -> List[str]:
        """当前真正在干活的效果器（参数不等于默认值的）。"""
        out = []
        for name in CHAIN_ORDER:
            if self._params[name] != EFFECT_SPECS[name]["params"]:
                out.append(name)
        return out

    def process(self, x: "np.ndarray", sr: int) -> "np.ndarray":
        np = _numpy()
        y = np.asarray(x, dtype=np.float32).reshape(-1)
        if y.size == 0:
            return y
        for name in CHAIN_ORDER:
            y = self._fx[name].process(y, sr)
        # 软限幅，任何一档拉满都不该爆
        return np.tanh(y.astype(np.float64)).astype(np.float32)
