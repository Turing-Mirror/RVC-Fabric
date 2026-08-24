# -*- coding: utf-8 -*-
"""Live voice-delay metric (no fixed algorithm formula).

The old dock number was ``device + block + crossfade + 10ms`` — a constant
once the stream was up. ``real_delay_ms`` then tried to be live by adding
``block + ring_delta/sr``, but ``ring_delta = (out_ptr - play_ptr) % buf``
wraps the empty half of the double-buffer in when play is already inside
the last written block. Diag 26.8.24 (MME, block=0.25, device=91ms):

    delay_ms (formula) = 431
    logged q = 11k–20k frames at 44100 Hz  →  250–475 ms of wrap garbage
    real_delay_ms stuck at 794 after stop
    Infer time was ~0–76 ms (cuda graph), not 300 ms of extra hardware

What we actually want: if I make a sound *now*, when does it start playing?

    device latency
  + one capture block (must fill a slice)
  + time until the last committed block *starts* (0 if it already started)
  + recent infer time (silence/skip blocks do not pull this down)

Crossfade / extra_time are lookback, not extra output delay — same as the
existing extra_time rule.
"""

from __future__ import annotations


def frames_until_block_start(
    out_ptr: int, play_ptr: int, block_frame: int, buf_size: int
) -> int:
    """Frames until play reaches the start of the last-written block.

    ``out_ptr`` is the *start* of that block (see ``_commit_output``).
    Returns 0 if play is already inside it — the start has been heard.
    """
    if buf_size <= 0 or block_frame <= 0:
        return 0
    out_ptr = int(out_ptr) % buf_size
    play_ptr = int(play_ptr) % buf_size
    into = (play_ptr - out_ptr + buf_size) % buf_size
    if into < block_frame:
        return 0
    return (out_ptr - play_ptr + buf_size) % buf_size


def ema(prev: float, sample: float, alpha: float = 0.15) -> float:
    """One-pole smoother. First sample (prev<=0) is taken as-is."""
    if prev <= 0.0:
        return float(sample)
    a = min(1.0, max(0.0, float(alpha)))
    return (1.0 - a) * float(prev) + a * float(sample)


def live_delay_sec(
    *,
    device: float,
    block: float,
    queued: float,
    infer: float,
) -> float:
    """End-to-end delay in seconds from the four live parts."""
    total = (
        max(0.0, float(device) or 0.0)
        + max(0.0, float(block) or 0.0)
        + max(0.0, float(queued) or 0.0)
        + max(0.0, float(infer) or 0.0)
    )
    if total > 8.0:
        return 8.0
    return total
