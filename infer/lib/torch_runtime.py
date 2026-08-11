# -*- coding: utf-8 -*-
"""Small torch helpers for offline inference (STS / CLI).

Keep this free of product UI deps. Realtime path does not have to import it.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager, nullcontext

logger = logging.getLogger(__name__)


def tune_for_inference() -> None:
    """One-shot knobs that speed offline conversion without changing model math.

    Safe to call multiple times. Failures are ignored (already-initialized
    interop threads, missing CUDA, old torch, …).
    """
    try:
        import torch
    except Exception:
        return

    try:
        torch.set_grad_enabled(False)
    except Exception:
        pass

    # Intra-op threads: ffmpeg / numpy / torch CPU ops. Cap so we don't thrash
    # on 16+ core machines while the GPU is the bottleneck.
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

    if not torch.cuda.is_available():
        return

    try:
        # Offline audio lengths vary; benchmark picks algorithms once shapes stabilize.
        torch.backends.cudnn.benchmark = True
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


def rmvpe_max_mel_frames(is_half: bool, device) -> int:
    """Pick RMVPE mel-chunk length by VRAM. Larger = fewer launches = faster."""
    # Default matches the OOM-safe value we ship for 3–4 GB cards.
    base = 1024
    try:
        import torch

        if not torch.cuda.is_available() or "cuda" not in str(device):
            return base
        total = int(torch.cuda.get_device_properties(0).total_memory)
        gb = total / (1024**3)
        if gb >= 10:
            return 4096 if is_half else 3072
        if gb >= 6:
            return 3072 if is_half else 2048
        if gb >= 4.5:
            return 2048 if is_half else 1536
        # ≤4 GB: keep conservative; fp32 (1060) is hungrier.
        if not is_half and gb <= 3.5:
            return 768
        return base
    except Exception:
        return base


@contextmanager
def inference_context():
    """Prefer ``torch.inference_mode``; fall back to ``no_grad`` / null."""
    try:
        import torch

        if hasattr(torch, "inference_mode"):
            with torch.inference_mode():
                yield
            return
        with torch.no_grad():
            yield
            return
    except Exception:
        pass
    with nullcontext():
        yield
