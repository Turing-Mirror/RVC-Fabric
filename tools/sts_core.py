# -*- coding: utf-8 -*-
"""离线语音转换的共用内核。

两条路都走这里：

* 冷路径 ``tools/sts_worker.py`` —— 独立进程，从盘上把 hubert / net_g / rmvpe
  全读一遍。没有实时 worker 在跑的时候用它。
* 热路径 ``gui_v1`` 的 ``convert`` 命令 —— 实时 worker 进程里，直接拿常驻的
  那几个模型对象干活，一个字节都不读盘。

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
    return text


def is_oom(text: str) -> bool:
    low = (text or "").lower()
    return "显存不够" in (text or "") or "out of memory" in low


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
                cuda_empty_cache()
                on_stage("f0", 0.0)
                continue
            raise RuntimeError(reason) from e
    if last_err is not None:
        raise RuntimeError(friendly_error(last_err)) from last_err


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
) -> tuple[list[str], list[dict], bool]:
    """转一批文件。返回 (成功清单, 跳过清单, 是否被取消)。

    单个文件坏掉不该毁掉整批：记下来接着跑，最后一起报。批量转 50 个，第 3 个
    是段损坏的 mp3，剩下 47 个照样得转出来。
    """
    from scipy.io import wavfile

    from infer.lib.torch_runtime import empty_cache_if_needed, inference_context

    out_root = Path(out_dir)
    total = len(files)
    out_files: list[str] = []
    skipped: list[dict] = []
    cancelled = False
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
                    convert_one(
                        vc,
                        src,
                        dest,
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
