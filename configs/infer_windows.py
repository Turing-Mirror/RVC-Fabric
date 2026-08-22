# -*- coding: utf-8 -*-
"""Offline pipeline cut windows. No torch.

``configs/config.py`` imports torch at the top, so a function left there is
untestable on the dev interpreter. Same split as ``configs/accel.py``.
"""

from __future__ import annotations

import os


def infer_window_profile(gpu_mem, is_half):
    """Offline pipeline cut windows, in seconds.

    ``x_max`` is the longest synthesizer window before the file is split;
    ``x_center`` is the stride between cut points. Hubert + net_g.enc_p are
    transformer-shaped, so cost grows faster than linear in window length.

    Official RVC uses 30/32s on <=4 GB. That is sized for fp16 4 GB cards. A
    3 GB Pascal card is forced to fp32, and a 30s ``net_g.infer`` looks frozen
    at infer ~10% with "normal" GPU usage — the kernel is running, progress
    only ticks at segment boundaries (diag 26.8.22/3).
    """
    try:
        gpu_mem = int(gpu_mem) if gpu_mem is not None else None
    except (TypeError, ValueError):
        gpu_mem = None
    is_half = bool(is_half)

    if is_half:
        x_pad, x_query, x_center, x_max = 3, 10, 60, 65
    else:
        x_pad, x_query, x_center, x_max = 1, 6, 38, 41

    if gpu_mem is not None and gpu_mem <= 4:
        x_pad, x_query, x_center, x_max = 1, 5, 30, 32

    if gpu_mem is not None and gpu_mem <= 3:
        x_pad, x_query, x_center, x_max = 1, 3, 6, 8
    elif gpu_mem is not None and gpu_mem <= 4 and not is_half:
        x_pad, x_query, x_center, x_max = 1, 4, 10, 12

    try:
        forced = int((os.environ.get("TM_VC_X_MAX") or "").strip() or "0")
    except ValueError:
        forced = 0
    if forced > 0:
        x_max = max(4, forced)
        x_center = max(3, x_max - 2)
        x_query = max(2, min(x_query, max(2, x_center // 2)))
        x_pad = 1

    return x_pad, x_query, x_center, x_max
