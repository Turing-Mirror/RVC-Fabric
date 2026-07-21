# -*- coding: utf-8 -*-
"""Local realtime performance reports.

Collects per-block inference wall times during a voice-conversion session and
writes a small JSON report to ``User_Data/perf_reports/`` when the stream
stops. Reports are local-only — nothing is uploaded; users share the file by
hand (e.g. attach to feedback / QQ). This is how we gather timing data from
GPUs we do not own.

Pure stdlib on purpose: importable and testable without torch.
"""

from __future__ import annotations

import json
import os
import time

# Bounded memory: ~4 blocks/s * 8 bytes ≈ 1.6 MB at the cap (≈14 h of audio)
_MAX_SAMPLES = 200_000
_KEEP_REPORTS = 30
# "Occasional" sampling policy: at most one report per interval, and ignore
# sessions too short to be meaningful (instant start/stop clicks)
MIN_REPORT_INTERVAL_S = 1800
MIN_SESSION_SAMPLES = 40


def should_save(dir_path: str, min_interval_s: float = MIN_REPORT_INTERVAL_S, now: float | None = None) -> bool:
    """True when enough time has passed since the newest existing report."""
    try:
        newest = max(
            (
                os.path.getmtime(os.path.join(dir_path, n))
                for n in os.listdir(dir_path)
                if n.startswith("perf_") and n.endswith(".json")
            ),
            default=0.0,
        )
    except OSError:
        return True
    if now is None:
        now = time.time()
    return (now - newest) >= min_interval_s


class PerfCollector:
    """Accumulates per-block seconds; never raises from the audio thread."""

    def __init__(self, meta: dict | None = None):
        self._meta = dict(meta or {})
        self._samples: list[float] = []
        self._dropped = 0

    def add(self, seconds: float) -> None:
        if len(self._samples) < _MAX_SAMPLES:
            self._samples.append(float(seconds))
        else:
            self._dropped += 1

    def summary(self) -> dict:
        n = len(self._samples)
        if n == 0:
            return {"n": 0}
        ms = sorted(s * 1000.0 for s in self._samples)

        def pct(p: float) -> float:
            i = min(n - 1, max(0, int(round(p / 100.0 * (n - 1)))))
            return ms[i]

        block_ms = float(self._meta.get("block_time") or 0.0) * 1000.0
        over = sum(1 for v in ms if block_ms and v > block_ms)
        return {
            "n": n,
            "dropped": self._dropped,
            "mean_ms": round(sum(ms) / n, 2),
            "p50_ms": round(pct(50), 2),
            "p95_ms": round(pct(95), 2),
            "max_ms": round(ms[-1], 2),
            "block_ms": round(block_ms, 1),
            "over_budget_blocks": over,
            "worst10_ms": [round(v, 1) for v in ms[-10:]],
        }

    def save(self, dir_path: str) -> str:
        """Write the report; returns the file path ('' when nothing to save)."""
        if not self._samples:
            return ""
        os.makedirs(dir_path, exist_ok=True)
        path = os.path.join(
            dir_path, time.strftime("perf_%Y%m%d_%H%M%S.json")
        )
        payload = {"meta": self._meta, "summary": self.summary()}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        _prune(dir_path)
        return path


def load_latest(dir_path: str) -> dict | None:
    """Newest saved perf report as a dict, or None when there are none."""
    try:
        files = sorted(
            n
            for n in os.listdir(dir_path)
            if n.startswith("perf_") and n.endswith(".json")
        )
    except OSError:
        return None
    if not files:
        return None
    try:
        with open(os.path.join(dir_path, files[-1]), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _prune(dir_path: str, keep: int = _KEEP_REPORTS) -> None:
    try:
        names = sorted(
            n
            for n in os.listdir(dir_path)
            if n.startswith("perf_") and n.endswith(".json")
        )
        for n in names[:-keep]:
            os.remove(os.path.join(dir_path, n))
    except OSError:
        pass
