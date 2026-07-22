# -*- coding: utf-8 -*-
"""Multi-step provision progress model for 启动器.

Tracks Runtime → engine-core → VB-Cable pipeline so the UI can show
「第 i / n 步」and remaining work.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional


DEFAULT_STEPS: list[tuple[str, str]] = [
    ("runtime_dl", "下载 Runtime"),
    ("runtime_extract", "解压 Runtime"),
    ("engine_dl", "下载引擎资源"),
    ("engine_extract", "解压引擎资源"),
    ("vbcable_dl", "下载虚拟声卡安装包"),
]


@dataclass
class StepState:
    id: str
    title: str
    status: str = "pending"  # pending | active | done | error | skipped


@dataclass
class ProvisionSnapshot:
    step_index: int  # 0-based active (or last)
    total_steps: int
    step_id: str
    step_title: str
    steps: list[StepState]
    remaining_titles: list[str]
    done_bytes: int = 0
    total_bytes: int = 0
    pct: float = 0.0
    speed_bps: float = 0.0
    eta_sec: float = -1.0
    note: str = ""
    phase: str = ""  # download | extract | idle


class ProvisionTracker:
    def __init__(
        self,
        steps: Optional[list[tuple[str, str]]] = None,
        *,
        on_change: Optional[Callable[[ProvisionSnapshot], None]] = None,
    ) -> None:
        raw = steps or list(DEFAULT_STEPS)
        self.steps: list[StepState] = [
            StepState(id=i, title=t) for i, t in raw
        ]
        self._by_id = {s.id: s for s in self.steps}
        self._active_id: str = self.steps[0].id if self.steps else ""
        self.done_bytes = 0
        self.total_bytes = 0
        self.note = ""
        self.phase = "idle"
        self._on_change = on_change
        self._speed_window: list[tuple[float, int]] = []  # (t, done)
        self._speed_bps = 0.0
        self._last_emit = 0.0

    def set_on_change(self, cb: Optional[Callable[[ProvisionSnapshot], None]]) -> None:
        self._on_change = cb

    def set_step(self, step_id: str, *, status: str = "active") -> None:
        if step_id not in self._by_id:
            return
        # mark previous active as done if moving forward
        ids = [s.id for s in self.steps]
        try:
            new_i = ids.index(step_id)
            old_i = ids.index(self._active_id) if self._active_id in ids else -1
        except ValueError:
            new_i, old_i = 0, -1
        if old_i >= 0 and new_i > old_i:
            for s in self.steps[:new_i]:
                if s.status == "active":
                    s.status = "done"
        for s in self.steps:
            if s.id == step_id:
                s.status = status
            elif s.status == "active" and s.id != step_id:
                s.status = "done"
        self._active_id = step_id
        self.done_bytes = 0
        self.total_bytes = 0
        self._speed_window.clear()
        self._speed_bps = 0.0
        if status == "active":
            self.phase = "download" if step_id.endswith("_dl") else (
                "extract" if "extract" in step_id else "idle"
            )
        self._emit(force=True)

    def mark_done(self, step_id: str) -> None:
        s = self._by_id.get(step_id)
        if s:
            s.status = "done"
            self._emit(force=True)

    def mark_skipped(self, step_id: str) -> None:
        s = self._by_id.get(step_id)
        if s:
            s.status = "skipped"
            self._emit(force=True)

    def mark_error(self, step_id: str, note: str = "") -> None:
        s = self._by_id.get(step_id)
        if s:
            s.status = "error"
        if note:
            self.note = note
        self._emit(force=True)

    def set_bytes(self, done: int, total: int) -> None:
        self.done_bytes = max(0, int(done))
        self.total_bytes = max(0, int(total))
        now = time.monotonic()
        self._speed_window.append((now, self.done_bytes))
        # keep ~3s window
        cut = now - 3.0
        self._speed_window = [(t, d) for t, d in self._speed_window if t >= cut]
        if len(self._speed_window) >= 2:
            t0, d0 = self._speed_window[0]
            t1, d1 = self._speed_window[-1]
            dt = t1 - t0
            if dt > 0.2:
                self._speed_bps = max(0.0, (d1 - d0) / dt)
        self.phase = "download"
        self._emit(force=False)

    def set_note(self, note: str) -> None:
        self.note = note or ""
        self._emit(force=True)

    def set_phase(self, phase: str) -> None:
        self.phase = phase or "idle"
        self._emit(force=True)

    def snapshot(self) -> ProvisionSnapshot:
        ids = [s.id for s in self.steps]
        try:
            idx = ids.index(self._active_id)
        except ValueError:
            idx = 0
        active = self.steps[idx] if self.steps else StepState("", "")
        remaining = [
            s.title
            for s in self.steps[idx + 1 :]
            if s.status in ("pending", "active")
        ]
        # also include current if not done
        pct = 0.0
        if self.total_bytes > 0:
            pct = min(100.0, 100.0 * self.done_bytes / self.total_bytes)
        eta = -1.0
        if self._speed_bps > 50_000 and self.total_bytes > self.done_bytes:
            eta = (self.total_bytes - self.done_bytes) / self._speed_bps
        return ProvisionSnapshot(
            step_index=idx,
            total_steps=len(self.steps),
            step_id=active.id,
            step_title=active.title,
            steps=list(self.steps),
            remaining_titles=remaining,
            done_bytes=self.done_bytes,
            total_bytes=self.total_bytes,
            pct=pct,
            speed_bps=self._speed_bps,
            eta_sec=eta,
            note=self.note,
            phase=self.phase,
        )

    def _emit(self, *, force: bool) -> None:
        if not self._on_change:
            return
        now = time.monotonic()
        if not force and (now - self._last_emit) < 0.12:
            return
        self._last_emit = now
        try:
            self._on_change(self.snapshot())
        except Exception:
            pass


def format_bytes(n: int) -> str:
    if n <= 0:
        return "0 B"
    if n >= 1_000_000_000:
        return f"{n / 1e9:.2f} GB"
    if n >= 1_000_000:
        return f"{n / 1e6:.0f} MB"
    if n >= 1_000:
        return f"{n / 1e3:.0f} KB"
    return f"{n} B"


def format_speed(bps: float) -> str:
    if bps < 500:
        return "—"
    if bps >= 1e6:
        return f"{bps / 1e6:.1f} MB/s"
    if bps >= 1e3:
        return f"{bps / 1e3:.0f} KB/s"
    return f"{bps:.0f} B/s"


def format_eta(sec: float) -> str:
    if sec < 0 or sec > 86400 * 2:
        return "—"
    if sec < 60:
        return f"约 {int(sec)} 秒"
    if sec < 3600:
        return f"约 {int(sec // 60)} 分 {int(sec % 60)} 秒"
    return f"约 {int(sec // 3600)} 小时"
