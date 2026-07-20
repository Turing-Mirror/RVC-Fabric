# -*- coding: utf-8 -*-
"""Pure presentation/preset logic pulled out of main_app (no Tk).

Kept dependency-free and unit-tested so the main window stays a thin
orchestrator. See docs/PERF_NOTES.md for how the perf presets map to the
realtime latency/quality tradeoff.
"""

from __future__ import annotations

# block_time, crossfade, extra_time — aligned with the realtime chunk tradeoff.
# Validated against GTX 1060 benchmarks (docs/PERF_NOTES.md §1).
PERF_PRESETS: dict[str, tuple[float, float, float]] = {
    "low_latency": (0.12, 0.04, 1.5),
    "balanced": (0.22, 0.05, 2.5),
    "stable": (0.40, 0.08, 3.5),
}

PERF_PRESET_NAMES: dict[str, str] = {
    "low_latency": "低延迟",
    "balanced": "均衡",
    "stable": "稳定",
}


def perf_preset_values(key: str) -> tuple[float, float, float]:
    """(block_time, crossfade, extra_time) for a preset key; balanced fallback."""
    return PERF_PRESETS.get(key) or PERF_PRESETS["balanced"]


def perf_preset_name(key: str) -> str:
    return PERF_PRESET_NAMES.get(key, key)


def format_latency_line(delay_ms: int, infer_ms: int, fallback: str) -> str:
    """Human-readable metrics line; hides the absurd delayed-sentinel values.

    delay/infer are milliseconds; anything >= 8000 is treated as "not measured
    yet" (the engine's 114514-second sentinel and cold-start spikes).
    """
    parts: list[str] = []
    if 0 < delay_ms < 8000:
        parts.append(f"延迟 {delay_ms} ms")
    elif delay_ms >= 8000:
        parts.append("延迟 测量中…")
    if 0 < infer_ms < 8000:
        parts.append(f"推理 {infer_ms} ms")
    return " · ".join(parts) if parts else fallback
