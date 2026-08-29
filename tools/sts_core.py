# -*- coding: utf-8 -*-
"""离线语音转换的共用内核。

两条路都走这里：

* 冷路径 ``tools/sts_worker.py`` —— 独立进程，从盘上把 hubert / net_g / rmvpe
  全读一遍。没有实时 worker 在跑的时候用它。
* 热路径 ``gui_v1`` 的 ``convert`` 命令 —— 实时 worker 进程里，直接拿常驻的
  那几个模型对象干活，一个字节都不读盘。
* 文字合成第二步 ``tools/infer_cli.py`` —— SAPI 念完之后的单文件 RVC，同样
  是冷路径，走 ``convert_one_with_cpu_fallback``。

两条路唯一的差别是「模型从哪来」和「进度往哪发」，转换循环本身必须是同一份，
不然批量跳过、OOM 重试、进度加权这些行为会在两条路上慢慢长歪。

除了 ``convert_one`` / ``run_batch`` 需要 torch 以外，本模块其余部分是纯
stdlib + 惰性 numpy，可以在没有 Runtime 的机器上导入和单测。
"""

from __future__ import annotations

import os
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}

# 单文件内各阶段在该文件进度份额中的起止（0..1）。
STAGE_SPAN = {
    "read": (0.00, 0.08),
    "hubert": (0.08, 0.16),
    "f0": (0.16, 0.48),
    "infer": (0.48, 0.92),
    "write": (0.92, 1.00),
}

# 这些 step 是状态跃迁，不受节流限制，必须发出去。
_BOUNDARY_STEPS = frozenset(
    {"file_start", "file_done", "file_skip", "load_config", "load_model",
     "load_hubert", "load_rmvpe", "write"}
)


class ConversionCancelled(BaseException):
    """用户中途取消。

    故意继承 ``BaseException`` 而不是 ``Exception``：pipeline、rmvpe、vc_single
    里的进度回调全被 ``except Exception: pass`` 包着，普通异常传不出来，只能等
    当前这个文件跑完才停得下来。继承 BaseException 才能从回调里一路穿出去，
    长音频点取消当场就停。

    代价是可能在半路留下几块显存没释放，调用方收到之后清一次缓存即可。
    """


# ---------------------------------------------------------------------------
# 错误与参数归一
# ---------------------------------------------------------------------------


def friendly_error(exc: BaseException | str) -> str:
    """把 torch / CUDA 的长 traceback 收成用户能照着做的中文提示。

    vc_single 失败时会把整段 traceback 塞进 info 字符串，所以参数既可能是
    Exception 也可能是那串文本。
    """
    text = str(exc) if not isinstance(exc, BaseException) else (str(exc) or type(exc).__name__)
    low = text.lower()
    if "out of memory" in low or "cuda out of memory" in low:
        return (
            "显存不够（CUDA OOM）。常见原因：实时变声还在跑、音频太长、或显卡显存较小（如 3GB）。\n"
            "请先在主界面停止变声，关闭其他占 GPU 的程序后重试；"
            "仍失败可把音高算法改成 harvest 或 pm（更省显存），或把长音频切短再转。"
        )
    if "显存不够" in text or "缺少 hubert" in text:
        return text
    if is_dml_backend_error(text):
        # 整段 traceback 对用户没有意义，收成一句话 + 最后那行真正的报错。
        return (
            "显卡后端（DirectML）不支持这一步用到的算子，没法在显卡上完成转换。\n"
            "可以在系统环境变量里设 TM_USE_DML=0 改用 CPU 后端后重启软件（会慢一些）。\n"
            f"原始报错：{last_error_line(text)}"
        )
    # 规格书 1.3 兜底：正文 = 最后一行真实报错，完整 traceback 留给「详情」。
    # 认不出的错误以前原样整段丢给界面，第一行永远是 Traceback (most recent
    # call last):，26.8.22/4 截图里用户看到的就是这个。
    if looks_like_traceback(text):
        last = last_error_line(text)
        if last and last != text:
            return f"{last}\n{text}"
    return text


def is_oom(text: str) -> bool:
    low = (text or "").lower()
    return "显存不够" in (text or "") or "out of memory" in low


# DirectML（privateuseone）后端缺算子时抛出来的那几种。字样取自实测报错：
#
#   RuntimeError: new(): expected key in DispatchKeySet(...) but got: PrivateUse1
#   RuntimeError: don't know how to restore data location of
#                 torch.storage.UntypedStorage (tagged with privateuseone:0)
#
# 前一句是 fairseq 的 GradMultiply，后一句是 torchcrepe 装权重。两处都已单独修
# （infer/lib/dml_compat），这里是兜底：DirectML 的算子缺口以后还会有新的，撞上
# 了宁可慢慢用 CPU 转出来，也不能整批失败。
DML_ERROR_MARKERS = ("privateuse1", "privateuseone", "directml", "dml backend")


def is_dml_backend_error(text) -> bool:
    low = str(text or "").lower()
    return any(m in low for m in DML_ERROR_MARKERS)


def _vc_is_dml(vc) -> bool:
    pipe = getattr(vc, "pipeline", None)
    return "privateuseone" in str(getattr(pipe, "device", "") or "")


def is_dml_runtime_failure(exc, vc) -> bool:
    """DirectML 上这次失败算不算「该退 CPU」。``exc`` 可以是异常对象，
    也可以是 ``friendly_error`` 之后的文本。

    带字样的报错（GradMultiply / torchcrepe 那类）`is_dml_backend_error`
    直接认；但没有字样的裸 ``RuntimeError`` 也得认 —— torch-directml 撞
    显存/后端失败时抛的就是一个空消息的 RuntimeError
    （26.8.29/113756：Arc 130T 上 41 秒段死在 ResBlock conv1d，
    ``RuntimeError`` 后面一个字都没有），关键词匹配永远接不住。

    注意 ``convert_one`` 会把底层异常统一包成 ``RuntimeError(友好文本)``
    再抛出来，异常类型到调用方这层没有信息量，判定只能看文本：空消息
    过完 ``friendly_error`` 只剩一行光秃秃的 ``RuntimeError``，带消息的
    是消息本身。所以「带消息但没关键词」的失败不重试 —— 那多半是坏文件，
    退 CPU 也一样炸，别拖着整批陪跑。非 DML 设备整个规则不适用。
    """
    if is_dml_backend_error(exc):
        return True
    if not _vc_is_dml(vc):
        return False
    if isinstance(exc, BaseException):
        text = str(exc) or type(exc).__name__
    else:
        text = str(exc or "")
    return last_error_line(text) == "RuntimeError"


def looks_like_traceback(text) -> bool:
    s = str(text or "").lstrip()
    return s.startswith("Traceback") or "\n  File " in s or "\nFile " in s


def last_error_line(text) -> str:
    """从一整段 traceback 里取最后那句真正的报错。

    vc_single 把整段 traceback 塞进 info 字符串，界面原样贴出来就是几十行路径，
    用户根本看不出发生了什么（26.8.20 的反馈截图里就是这样一堵字）。
    """
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    for ln in reversed(lines):
        if ln.startswith("File ") or ln.startswith("Traceback"):
            continue
        return ln
    return lines[-1]


def _module_device(model):
    """nn.Module.to() 是原地搬的，失败时要靠这个把已经搬走的搬回去。"""
    if model is None:
        return None
    dev = getattr(model, "device", None)
    if dev is not None:
        return dev
    try:
        return next(model.parameters()).device
    except Exception:
        return None


def move_models_to_cpu(vc) -> bool:
    """把这份 VC 的模型整体挪到 CPU，返回是否挪成功。

    只有自己拥有模型的调用方能用（冷路径 worker）。热路径复用的是实时引擎的常驻
    张量，`vc.net_g` 就是 `rvc.net_g` 本人，挪走等于把实时变声一起废了——那边传
    ``allow_cpu_fallback=False``，改走「热路径不可用」让壳退到冷路径。

    ``Module.to()`` 原地改设备。net_g 搬走之后 hubert 再失败，不能把一半 CPU、
    一半 DirectML 的组合留给后面的文件——那种错不再像算子缺口，CPU 重试也
    不会再走。
    """
    net_g = getattr(vc, "net_g", None)
    hubert = getattr(vc, "hubert_model", None)
    pipe = getattr(vc, "pipeline", None)
    if net_g is None and hubert is None and pipe is None:
        return False

    net_dev = _module_device(net_g)
    hub_dev = _module_device(hubert)
    pipe_dev = getattr(pipe, "device", None) if pipe is not None else None
    pipe_half = bool(getattr(pipe, "is_half", False)) if pipe is not None else False
    rmvpe = getattr(pipe, "model_rmvpe", None) if pipe is not None else None
    had_rmvpe = pipe is not None and hasattr(pipe, "model_rmvpe")
    moved_net = moved_hub = moved_pipe = False

    def _restore():
        if moved_net and net_g is not None and net_dev is not None:
            vc.net_g = net_g.to(net_dev)
        if moved_hub and hubert is not None and hub_dev is not None:
            vc.hubert_model = hubert.to(hub_dev)
        if moved_pipe and pipe is not None:
            if pipe_dev is not None:
                pipe.device = pipe_dev
            pipe.is_half = pipe_half
            if had_rmvpe and rmvpe is not None:
                pipe.model_rmvpe = rmvpe

    try:
        if net_g is not None:
            vc.net_g = net_g.float().to("cpu")
            moved_net = True
        if hubert is not None:
            vc.hubert_model = hubert.float().to("cpu")
            moved_hub = True
        if pipe is not None:
            pipe.device = "cpu"
            pipe.is_half = False
            # rmvpe 在 privateuseone 上是 onnxruntime 的 DML EP，扔掉让 CPU 重建。
            if had_rmvpe:
                del pipe.model_rmvpe
            moved_pipe = True
        config = getattr(vc, "config", None)
        if config is not None:
            config.device = "cpu"
            config.is_half = False
    except Exception:
        traceback.print_exc()
        try:
            _restore()
        except Exception:
            traceback.print_exc()
        return False

    cuda_empty_cache()
    return True


def normalize_f0method(name: str) -> tuple[str, str | None]:
    """离线 pipeline 只实现了实时那套音高算法的一个子集。

    实时界面给了 ``fcpe``，离线 ``get_f0`` 没有。设置项是两边共用的，直接映射
    到 rmvpe，别让一个共享配置把整批转换炸掉。
    """
    m = (name or "rmvpe").strip().lower() or "rmvpe"
    if m == "fcpe":
        return "rmvpe", "离线转换不支持 fcpe，已改用 rmvpe"
    if m not in ("rmvpe", "harvest", "pm", "crepe"):
        return "rmvpe", f"未知音高算法 {name!r}，已改用 rmvpe"
    return m, None


def cuda_empty_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 输入收集
# ---------------------------------------------------------------------------


def collect_inputs(path: str) -> list[tuple[Path, Path]]:
    """返回 (源文件, 相对路径)。

    相对路径决定输出落在哪：文件夹输入时按原目录层级还原到输出目录，
    不然 `A/vocal.wav` 和 `B/vocal.wav` 会被铺平成 `vocal_rvc.wav` 和
    `vocal_rvc_1.wav`，谁是谁分不出来。
    """
    p = Path(path)
    if p.is_file():
        return [(p, Path(p.name))]
    if not p.is_dir():
        return []
    files: list[tuple[Path, Path]] = []
    for f in sorted(p.rglob("*")):
        if f.is_file() and f.suffix.lower() in AUDIO_EXT:
            try:
                rel = f.relative_to(p)
            except ValueError:
                rel = Path(f.name)
            files.append((f, rel))
    return files


def file_weights(paths: Iterable[Path]) -> list[float]:
    """多文件进度按体积加权。读时长要解码，批量扫目录太贵；体积够用。"""
    out: list[float] = []
    for p in paths:
        try:
            out.append(float(max(1, p.stat().st_size)))
        except OSError:
            out.append(1.0)
    return out


_AUDIO_OUT = ("wav", "flac", "mp3", "m4a")


def normalize_format(name: str) -> str:
    ext = (name or "wav").strip().lstrip(".").lower()
    return ext if ext in _AUDIO_OUT else "wav"


def unique_dest(out_dir: Path, rel: Path, stem: str, ext: str = "wav") -> Path:
    """输出路径，保持输入的目录层级，重名加序号。"""
    ext = normalize_format(ext)
    sub = out_dir / rel.parent
    sub.mkdir(parents=True, exist_ok=True)
    dest = sub / f"{stem}_rvc.{ext}"
    n = 1
    while dest.exists():
        dest = sub / f"{stem}_rvc_{n}.{ext}"
        n += 1
    return dest


def write_audio(wavfile, dest: Path, sr, audio, fmt: str = "wav") -> None:
    """wav 直接写；flac/mp3/m4a 走原版 wav2。"""
    fmt = normalize_format(fmt)
    if fmt == "wav":
        wavfile.write(str(dest), sr, audio)
        return
    from infer.lib.audio import wav2

    tmp = dest.with_name(dest.stem + ".__tmp.wav")
    wavfile.write(str(tmp), sr, audio)
    try:
        wav2(str(tmp), str(dest), fmt)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# 进度
# ---------------------------------------------------------------------------


class StsProgress:
    """把「加载模型 + 每个文件的子步骤」映射成 0–100 的整体进度。

    单文件时 done/total 只有 0→1，转换可能跑几分钟界面却一直 0%——所以必须
    再发 ``pct`` 和分步 ``message``。

    多文件时按体积加权：10 秒小文件不该和 5 分钟长歌各占 1/N 进度条。

    ``emit`` 由调用方注入：冷路径写 stdout 的 JSON 行，热路径写 sts.json。
    """

    # 加载/预热占前 12%，其余 88% 按文件权重分。热路径没有加载阶段，
    # 由调用方传 load_end=0 把这一段压掉。
    LOAD_END = 12.0
    STAGE_SPAN = STAGE_SPAN
    # 分块进度节流：同 step 下至少隔这么久，或 pct 至少涨 1。
    _MIN_INTERVAL = 0.12

    def __init__(
        self,
        total_files: int,
        f0method: str = "rmvpe",
        weights: Sequence[float] | None = None,
        emit: Callable[..., None] | None = None,
        load_end: float | None = None,
    ):
        self.total = max(1, int(total_files))
        self.f0method = (f0method or "rmvpe").strip() or "rmvpe"
        self._emit = emit or (lambda **_kw: None)
        if load_end is not None:
            self.LOAD_END = max(0.0, min(100.0, float(load_end)))
        if weights and len(weights) == self.total:
            self._weights = [max(1.0, float(w)) for w in weights]
        else:
            self._weights = [1.0] * self.total
        wsum = sum(self._weights) or float(self.total)
        # cum[i] = 前 i 个文件权重占比（0..1），cum[total]=1
        self._cum: list[float] = [0.0]
        acc = 0.0
        for w in self._weights:
            acc += w
            self._cum.append(acc / wsum)

        self._last_pct = -1
        self._last_msg = ""
        self._last_step = ""
        self._last_emit_t = 0.0
        self._file_i = 0  # 0-based，当前正在处理的文件
        self._file_name = ""
        self.ok_count = 0
        self.skip_count = 0

    # -- 内部 ---------------------------------------------------------------

    def _push(
        self,
        done_files: int,
        pct: float,
        message: str,
        step: str = "",
        *,
        force: bool = False,
        phase: str = "run",
    ) -> None:
        pct_i = int(max(0, min(100, round(pct))))
        now = time.monotonic()
        if not force:
            if pct_i == self._last_pct and message == self._last_msg:
                return
            boundary = step in _BOUNDARY_STEPS or step.startswith("load_")
            # 同一步骤内节流，批量长任务时少打爆管道；pct 涨了仍放行。
            if (
                not boundary
                and step == self._last_step
                and (now - self._last_emit_t) < self._MIN_INTERVAL
                and pct_i <= self._last_pct
            ):
                return

        self._last_pct = pct_i
        self._last_msg = message
        self._last_step = step
        self._last_emit_t = now
        current = self._file_i + 1 if self._file_name else 0
        self._emit(
            phase=phase,
            done=max(0, int(done_files)),
            total=self.total,
            pct=pct_i,
            step=step,
            current=current,
            ok=self.ok_count,
            skip=self.skip_count,
            file=self._file_name or "",
            message=message,
        )

    def _file_bounds(self, file_i: int) -> tuple[float, float]:
        i = max(0, min(int(file_i), self.total - 1))
        span = 100.0 - self.LOAD_END
        start = self.LOAD_END + span * self._cum[i]
        end = self.LOAD_END + span * self._cum[i + 1]
        return start, end

    # -- 对外 ---------------------------------------------------------------

    def load(self, phase: str, frac: float = 0.0) -> None:
        """phase: config | model | hubert | rmvpe；frac 0..1。"""
        if self.LOAD_END <= 0:
            return
        frac = max(0.0, min(1.0, float(frac)))
        # 预热段：config 20% / model 35% / hubert 23% / rmvpe 22% of LOAD_END
        bands = {
            "config": (0.00, 0.20, "正在初始化引擎…"),
            "model": (0.20, 0.55, "正在加载音色模型…"),
            "hubert": (0.55, 0.78, "正在预热特征模型（hubert）…"),
            "rmvpe": (0.78, 1.00, f"正在预热音高模型（{self.f0method}）…"),
        }
        a, b, msg = bands.get(phase, (0.0, 1.0, "准备中…"))
        pct = self.LOAD_END * (a + (b - a) * frac)
        self._push(0, pct, msg, step=f"load_{phase}", force=True)

    def begin_file(self, index: int, name: str) -> None:
        """index 为 1-based 序号。"""
        self._file_i = max(0, int(index) - 1)
        self._file_name = name
        start, _ = self._file_bounds(self._file_i)
        if self.total == 1:
            msg = f"开始转换 {name}"
        else:
            msg = (
                f"[{index}/{self.total}] {name} · 开始"
                f"（已完成 {self.ok_count}，跳过 {self.skip_count}）"
            )
        self._push(self._file_i, start, msg, step="file_start", force=True)

    def stage(self, stage: str, frac: float = 0.0) -> None:
        """文件内子步骤。stage: read/hubert/f0/infer/write；frac 0..1。"""
        frac = max(0.0, min(1.0, float(frac)))
        a, b = self.STAGE_SPAN.get(stage, (0.0, 1.0))
        start, end = self._file_bounds(self._file_i)
        pct = start + (end - start) * (a + (b - a) * frac)
        name = self._file_name or "音频"
        prefix = f"[{self._file_i + 1}/{self.total}] {name} · " if self.total > 1 else ""
        if stage == "read":
            msg = f"{prefix}读取音频…"
        elif stage == "hubert":
            msg = f"{prefix}提取特征（hubert）…"
        elif stage == "f0":
            if frac <= 0.02:
                msg = f"{prefix}提取音高（{self.f0method}）…"
            else:
                msg = f"{prefix}提取音高（{self.f0method}）… {int(frac * 100)}%"
        elif stage == "infer":
            if frac <= 0.0:
                msg = f"{prefix}音色转换中…"
            else:
                msg = f"{prefix}音色转换中… {int(frac * 100)}%"
        elif stage == "write":
            msg = f"{prefix}写入输出文件…"
        else:
            msg = f"{prefix}处理中…"
        self._push(self._file_i, pct, msg, step=stage)

    def file_done(self, index: int, name: str, ok: bool = True) -> None:
        _, end = self._file_bounds(max(0, int(index) - 1))
        if ok:
            self.ok_count += 1
            head, step = "完成", "file_done"
        else:
            self.skip_count += 1
            head, step = "跳过", "file_skip"
        if self.total == 1:
            msg = f"{head} {name}"
        else:
            msg = (
                f"[{index}/{self.total}] {head} {name}"
                f"（成功 {self.ok_count}，跳过 {self.skip_count}）"
            )
        self._push(index, end, msg, step=step, force=True)

    @property
    def last_pct(self) -> int:
        return self._last_pct if self._last_pct >= 0 else 0


# ---------------------------------------------------------------------------
# 转换
# ---------------------------------------------------------------------------


def convert_one(
    vc,
    src: Path,
    dest: Path,
    *,
    pitch,
    f0method,
    index_path,
    index_rate,
    filter_radius,
    resample_sr,
    rms_mix_rate,
    protect,
    on_stage,
    wavfile,
    fmt="wav",
    sid=0,
    f0_file=None,
) -> None:
    """跑一次 vc_single 并写盘。第一次 CUDA OOM 就缩小 rmvpe 分片再试一次。"""
    attempts = 2
    last_err: Exception | None = None
    for attempt in range(attempts):
        try:
            info, wav_opt = vc.vc_single(
                int(sid or 0),
                str(src),
                pitch,
                f0_file,
                f0method,
                index_path,
                None,
                index_rate,
                filter_radius,
                resample_sr,
                rms_mix_rate,
                protect,
                progress_cb=on_stage,
            )
            if wav_opt is None or wav_opt[0] is None:
                raise RuntimeError(friendly_error(info or "未知错误"))
            on_stage("write", 0.0)
            write_audio(wavfile, dest, wav_opt[0], wav_opt[1], fmt)
            on_stage("write", 1.0)
            return
        except Exception as e:
            last_err = e
            reason = friendly_error(e)
            if attempt + 1 < attempts and is_oom(reason):
                # 分片改小 + 归还显存，再试一次。
                os.environ["TM_RMVPE_MAX_FRAMES"] = "512"
                os.environ["TM_VC_X_MAX"] = "4"
                pipe = getattr(vc, "pipeline", None)
                shrink = getattr(pipe, "shrink_windows", None) if pipe is not None else None
                if callable(shrink):
                    try:
                        shrink()
                    except Exception:
                        traceback.print_exc()
                cuda_empty_cache()
                on_stage("f0", 0.0)
                continue
            raise RuntimeError(reason) from e
    if last_err is not None:
        raise RuntimeError(friendly_error(last_err)) from last_err


def convert_one_with_cpu_fallback(
    vc,
    src: Path,
    dest: Path,
    *,
    allow_cpu_fallback: bool = True,
    on_fallback: Callable[[Exception], None] | None = None,
    **kwargs,
) -> bool:
    """跑 ``convert_one``；DirectML 撞算子缺口时把模型挪到 CPU 再试一次。

    返回是否用了 CPU 兜底。STS 批量走 ``run_batch``（自带同一份逻辑）；TTS
    的 ``infer_cli`` 是单文件冷路径，以前漏了 —— 26.8.21 用户日志就是
    GradMultiply ``PrivateUse1``，SAPI 念完之后整次换音色失败。
    """
    try:
        convert_one(vc, src, dest, **kwargs)
        return False
    except Exception as first:
        if (
            allow_cpu_fallback
            and is_dml_runtime_failure(first, vc)
            and move_models_to_cpu(vc)
        ):
            if on_fallback is not None:
                try:
                    on_fallback(first)
                except Exception:
                    traceback.print_exc()
            convert_one(vc, src, dest, **kwargs)
            return True
        raise


def preload_side_models(vc, config, f0method: str, prog: StsProgress) -> None:
    """批量前一次性拉起 hubert / rmvpe，避免摊在第一个文件里看不出预热。"""
    try:
        if getattr(vc, "hubert_model", None) is None:
            prog.load("hubert", 0.0)
            from infer.modules.vc.utils import load_hubert

            vc.hubert_model = load_hubert(config)
        prog.load("hubert", 1.0)
    except Exception:
        # 预热失败不挡主流程；真正转换时还会再试并给出错误。
        traceback.print_exc()
        prog.load("hubert", 1.0)

    if f0method.lower() != "rmvpe":
        return
    try:
        pipe = getattr(vc, "pipeline", None)
        if pipe is None:
            return
        if hasattr(pipe, "model_rmvpe"):
            prog.load("rmvpe", 1.0)
            return
        prog.load("rmvpe", 0.0)
        from infer.lib.rmvpe import RMVPE

        root = os.environ.get("rmvpe_root") or "assets/rmvpe"
        pipe.model_rmvpe = RMVPE(
            os.path.join(root, "rmvpe.pt"),
            is_half=pipe.is_half,
            device=pipe.device,
        )
        prog.load("rmvpe", 1.0)
    except Exception:
        traceback.print_exc()
        prog.load("rmvpe", 1.0)


def run_batch(
    vc,
    files: Sequence[tuple[Path, Path]],
    out_dir: str | Path,
    params: dict[str, Any],
    prog: StsProgress,
    emit: Callable[..., None],
    should_cancel: Callable[[], bool] | None = None,
    allow_cpu_fallback: bool = True,
) -> tuple[list[str], list[dict], bool]:
    """转一批文件。返回 (成功清单, 跳过清单, 是否被取消)。

    单个文件坏掉不该毁掉整批：记下来接着跑，最后一起报。批量转 50 个，第 3 个
    是段损坏的 mp3，剩下 47 个照样得转出来。

    ``allow_cpu_fallback``：撞上 DirectML 算子缺口时，把模型挪到 CPU 重试一次，
    这一批剩下的文件也留在 CPU 上。慢，但能转出来。热路径必须传 False，那边的
    模型是实时引擎的（见 move_models_to_cpu）。
    """
    from scipy.io import wavfile

    from infer.lib.torch_runtime import empty_cache_if_needed, inference_context

    out_root = Path(out_dir)
    total = len(files)
    out_files: list[str] = []
    skipped: list[dict] = []
    cancelled = False
    cpu_fallback_done = False
    index_path = params.get("index_path") or None
    # 批量：尽量不 empty_cache；OOM 或显存吃紧时才清。末尾清一次即可。
    cache_every = 8

    def _cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    try:
        with inference_context():
            for i, (src, rel) in enumerate(files, start=1):
                if _cancelled():
                    cancelled = True
                    break
                prog.begin_file(i, src.name)

                def on_stage(stage: str, frac: float = 0.0, _i=i, _name=src.name) -> None:
                    # 闭包默认参数钉死当前文件，避免循环变量晚绑定。
                    if _cancelled():
                        raise ConversionCancelled()
                    prog._file_i = _i - 1
                    prog._file_name = _name
                    prog.stage(stage, frac)

                hit_oom = False
                try:
                    dest = unique_dest(
                        out_root, rel, src.stem, params.get("format") or "wav"
                    )
                    kwargs = dict(
                        pitch=params["pitch"],
                        f0method=params["f0method"],
                        index_path=index_path,
                        index_rate=params["index_rate"],
                        filter_radius=params["filter_radius"],
                        resample_sr=params["resample_sr"],
                        rms_mix_rate=params["rms_mix_rate"],
                        protect=params["protect"],
                        on_stage=on_stage,
                        wavfile=wavfile,
                        fmt=params.get("format") or "wav",
                        sid=params.get("sid") or 0,
                        f0_file=params.get("f0_file"),
                    )
                    # ConversionCancelled 继承 BaseException，不会被这里接住。
                    try:
                        convert_one(vc, src, dest, **kwargs)
                    except Exception as first:
                        if (
                            allow_cpu_fallback
                            and not cpu_fallback_done
                            and is_dml_runtime_failure(first, vc)
                            and move_models_to_cpu(vc)
                        ):
                            # 显卡这条路走不通了，别让整批陪葬。挪到 CPU 重来一次，
                            # 后面的文件也留在 CPU 上（模型已经不在显卡上了）。
                            cpu_fallback_done = True
                            traceback.print_exc()
                            emit(
                                phase="run",
                                done=i - 1,
                                total=total,
                                pct=prog.last_pct,
                                current=i,
                                ok=prog.ok_count,
                                skip=prog.skip_count,
                                file=src.name,
                                message="显卡后端（DirectML）不支持这一步，已改用 CPU 重试（会慢一些）",
                            )
                            on_stage("read", 0.0)
                            convert_one(vc, src, dest, **kwargs)
                        else:
                            raise
                    out_files.append(str(dest))
                    prog.file_done(i, src.name, ok=True)
                except Exception as e:
                    traceback.print_exc()
                    reason = friendly_error(e)
                    hit_oom = is_oom(reason)
                    skipped.append({"file": str(src), "name": src.name, "reason": reason})
                    prog.file_done(i, src.name, ok=False)
                    # reason 单独字段，界面列表不要再叠一层「跳过 name：」。
                    emit(
                        phase="skip",
                        done=i,
                        total=total,
                        pct=prog.last_pct,
                        current=i,
                        ok=prog.ok_count,
                        skip=prog.skip_count,
                        file=src.name,
                        reason=reason,
                        message=f"跳过 {src.name}：{reason}",
                    )
                finally:
                    if hit_oom:
                        cuda_empty_cache()
                    elif i == total or (total > 1 and i % cache_every == 0):
                        empty_cache_if_needed(min_free_mb=512)
                    # 单文件结束时若显存仍充裕就不动，交给进程退出回收。
    except ConversionCancelled:
        # 从进度回调里一路穿出来的：可能停在 pipeline 中段，清一次显存。
        cancelled = True
        cuda_empty_cache()

    return out_files, skipped, cancelled
