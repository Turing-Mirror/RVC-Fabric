# -*- coding: utf-8 -*-
"""Small torch helpers for offline inference (STS / CLI).

Keep this free of product UI deps. Realtime path does not have to import it.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager, nullcontext

logger = logging.getLogger(__name__)

# Thread knobs can only be set once per process. After the interop thread pool
# has started (e.g. Config() imports fairseq/torch deeper), a second
# set_num_interop_threads() call is a NATIVE crash (STATUS_STACK_BUFFER_OVERRUN,
# exit 0xC0000409) on torch 2.0 Windows — no Python exception, so try/except
# cannot catch it. sts_worker calls tune_for_inference twice (before and after
# Config), so guard the thread section with this flag.
_THREADS_TUNED = False


# cudnn.benchmark 只有摊得平的时候才划算，见 tune_for_inference。
BENCHMARK_MIN_SECONDS = 60.0
BENCHMARK_MIN_FILES = 3


def want_cudnn_benchmark(total_seconds: float = 0.0, total_files: int = 1) -> bool:
    """这批活值不值得开 cudnn.benchmark。

    benchmark 的做法是「每遇到一个没见过的张量形状，就把所有卷积算法各跑一遍
    挑最快的」。批量长音频里这笔调优费摊得平；转一条 5 秒语音就是纯亏——调优
    跑完，活也干完了，挑出来的算法一次都没复用上。实测这一项能占掉短任务好几秒。

    环境变量 ``TM_CUDNN_BENCHMARK`` 可强制 1/0。
    """
    forced = (os.environ.get("TM_CUDNN_BENCHMARK") or "").strip()
    if forced in ("1", "true", "on", "yes"):
        return True
    if forced in ("0", "false", "off", "no"):
        return False
    if int(total_files or 0) >= BENCHMARK_MIN_FILES:
        return True
    return float(total_seconds or 0.0) >= BENCHMARK_MIN_SECONDS


def tune_for_inference(total_seconds: float = 0.0, total_files: int = 1) -> None:
    """One-shot knobs that speed offline conversion without changing model math.

    Safe to call multiple times. Thread knobs are applied only on the first
    call; CUDA switches are reapplied (idempotent). Failures are ignored
    (missing CUDA, old torch, …).

    ``total_seconds`` / ``total_files`` 描述这批活有多大，只用来决定
    cudnn.benchmark 开不开（见 want_cudnn_benchmark）。不传就按小任务处理。
    """
    global _THREADS_TUNED

    try:
        import torch
    except Exception:
        return

    try:
        torch.set_grad_enabled(False)
    except Exception:
        pass

    if not _THREADS_TUNED:
        # Intra-op threads: ffmpeg / numpy / torch CPU ops. Cap so we don't
        # thrash on 16+ core machines while the GPU is the bottleneck.
        try:
            n = int(os.environ.get("TM_TORCH_NUM_THREADS") or 0)
            if n <= 0:
                n = max(1, min(8, (os.cpu_count() or 4)))
            torch.set_num_threads(n)
        except Exception:
            pass
        try:
            torch.set_num_interop_threads(1)
        except Exception:
            pass
        _THREADS_TUNED = True

    if not torch.cuda.is_available():
        return

    try:
        # 只有够大的批次才开；短任务上这是净亏。
        torch.backends.cudnn.benchmark = want_cudnn_benchmark(total_seconds, total_files)
    except Exception:
        pass
    try:
        # Ampere+: TF32 is free speed on matmul; not used on Pascal (1060).
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
    except Exception:
        pass
    try:
        torch.set_float32_matmul_precision("high")
    except Exception:
        pass


def empty_cache_if_needed(min_free_mb: int = 384) -> bool:
    """Release the CUDA caching allocator only when free VRAM is tight.

    Calling ``empty_cache`` after every segment / mel chunk forces a device sync
    and throws away reusable blocks — fine for Gradio demos, terrible for
    offline batch conversion. Return True if we actually emptied.
    """
    try:
        import torch

        if not torch.cuda.is_available():
            return False
        try:
            free_b, _total_b = torch.cuda.mem_get_info()
        except Exception:
            # Older torch / non-primary device: fall back to never (prefer speed).
            return False
        if free_b < max(1, int(min_free_mb)) * 1024 * 1024:
            torch.cuda.empty_cache()
            return True
    except Exception:
        return False
    return False


def _align32(n: int, minimum: int = 256) -> int:
    """UNet / context (128) both need multiples of 32; floor to that grid."""
    n = max(int(minimum), int(n))
    return n // 32 * 32


def rmvpe_max_mel_frames(is_half: bool, device) -> int:
    """Pick RMVPE mel-chunk length by VRAM. Larger = fewer launches = faster.

    Always a multiple of 32 so it lines up with the 128-frame overlap context
    (see RMVPE.mel2hidden). Override with env ``TM_RMVPE_MAX_FRAMES`` (e.g. OOM
    retry shrinks to 512).
    """
    # Forced override (STS OOM retry / power users).
    try:
        forced = int((os.environ.get("TM_RMVPE_MAX_FRAMES") or "").strip() or "0")
        if forced > 0:
            return _align32(forced, minimum=256)
    except Exception:
        pass

    # Default matches the OOM-safe value we ship for 3–4 GB cards.
    base = 1024
    try:
        import torch

        if not torch.cuda.is_available() or "cuda" not in str(device):
            return base
        total = int(torch.cuda.get_device_properties(0).total_memory)
        gb = total / (1024**3)
        if gb >= 10:
            return _align32(4096 if is_half else 3072)
        if gb >= 6:
            return _align32(3072 if is_half else 2048)
        if gb >= 4.5:
            return _align32(2048 if is_half else 1536)
        # ≤4 GB: keep conservative; fp32 (1060) is hungrier.
        if not is_half and gb <= 3.5:
            return _align32(768)
        return base
    except Exception:
        return base


@contextmanager
def inference_context():
    """推理期间关掉 autograd。**故意用 no_grad，不用 inference_mode。**

    `torch.inference_mode()` 里新建的张量会被打上 inference 标记。这个标记跟着
    张量走，出了这个块也不会掉。而离线转换这条路上会**顺手建长命对象**：
    `Pipeline.get_f0` 第一次跑 rmvpe 时才现场 new 一个 `RMVPE`，它的
    `mel_basis` 是 `register_buffer` 存下来的;`MelSpectrogram.hann_window`
    和 `RMVPE.resample_kernel` 也是普通 dict 缓存。这些东西一旦生在
    inference_mode 里，之后在别处再用就是：

        RuntimeError: Cannot set version_counter for inference tensor
        （新版 torch 措辞变成 "Inference tensors cannot be saved for backward"）

    26.8.18 有用户就这么炸的，栈底停在 `rmvpe.py` 的
    `torch.matmul(self.mel_basis, magnitude)`。

    `no_grad` 省的显存和时间跟 `inference_mode` 基本一样（差在版本计数器那点
    记账，这个负载上不到 1%），但它建出来的是普通张量，怎么传都不会炸。这点
    速度不值得拿一整类崩溃去换。

    另外：try 只包 import，不包 yield。以前是整段包在 `except Exception: pass`
    里，块里抛任何异常都会被吞掉、然后生成器第二次 yield，contextlib 抛一句
    "generator didn't stop after throw()"，真正的错误就此消失。
    """
    try:
        import torch
    except Exception:
        # 没有 torch 就没有推理，空转即可（单测环境走这条）。
        with nullcontext():
            yield
        return

    with torch.no_grad():
        yield
