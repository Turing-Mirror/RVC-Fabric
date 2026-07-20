# -*- coding: utf-8 -*-
"""Monitor-output device heuristics (pure; no Tk).

Picking the self-monitor endpoint (headphones) while avoiding the CABLE /
virtual / Steam-streaming sinks was buried in main_app. Extracted so the rule
is testable and reusable (the 「监听自己」 bug in 2026-07 came from picking a
virtual sink).
"""

from __future__ import annotations

_VIRTUAL_MONITOR_KEYS: tuple[str, ...] = (
    "cable",
    "voicemeeter",
    "mapper",
    "steam streaming",
    "steam streaming speakers",
    "virtual",
    "vb-audio",
    "vb audio",
    "nvidia high definition",
    "nvidia broadcast",
    "网易虚拟",
    "fxsound",
    "discord",
    "obs virtual",
    "stereo mix",
    "主声音驱动",
    "primary sound",
)

_HEADPHONE_HINTS: tuple[str, ...] = ("headphone", "headset", "earphone")


def is_virtual_monitor_name(name: str) -> bool:
    """True for empty names and known virtual/loopback endpoints (not real speakers)."""
    low = (name or "").lower()
    if not low:
        return True
    return any(k in low for k in _VIRTUAL_MONITOR_KEYS)


def prefer_monitor_device(outs: list, current: str = "", main_out: str = "") -> str:
    """Pick real headphones/speakers, avoiding CABLE / Steam / virtual endpoints.

    * ``outs``: available output device names.
    * ``current``: currently chosen monitor device (kept if still usable).
    * ``main_out``: the main voice output (usually CABLE Input) — never monitor
      onto it, and if it is a CABLE, avoid other CABLE endpoints too.
    """
    if not outs:
        return current or ""
    main_out = main_out or ""

    def usable(n: str) -> bool:
        if not n or n == main_out:
            return False
        if is_virtual_monitor_name(n):
            return False
        if main_out and "cable" in main_out.lower() and "cable" in n.lower():
            return False
        return True

    if current and current in outs and usable(current):
        return current
    for n in outs:  # prefer things that look like headphones
        low = n.lower()
        if usable(n) and ("耳机" in n or any(h in low for h in _HEADPHONE_HINTS)):
            return n
    for n in outs:
        if usable(n):
            return n
    return current if current in outs else outs[0]
