# -*- coding: utf-8 -*-
"""Tk-free download scheduling state for the community dialog.

Tracks per-voice download state (active percent / FIFO wait queue) with a
max-active cap, so the store page can run several installs concurrently and
label each row's button 下载安装 / 待下载 / NN% / 重新下载.

Not thread-safe by design: all mutations must happen on the Tk main thread
(worker threads marshal via root.after), matching store_page's existing
progress plumbing.
"""

from __future__ import annotations

STATE_IDLE = "idle"
STATE_QUEUED = "queued"
STATE_ACTIVE = "active"


class DownloadQueue:
    """Max-N concurrent slots + FIFO wait queue, keyed by voice id."""

    def __init__(self, max_active: int = 2) -> None:
        self.max_active = max(1, int(max_active))
        self._active: dict[str, int] = {}  # id -> percent 0-100 (-1 = unknown)
        self._waiting: list[str] = []

    def state(self, vid: str) -> str:
        if vid in self._active:
            return STATE_ACTIVE
        if vid in self._waiting:
            return STATE_QUEUED
        return STATE_IDLE

    def percent(self, vid: str) -> int:
        return self._active.get(vid, 0)

    def has_work(self) -> bool:
        return bool(self._active or self._waiting)

    def request(self, vid: str) -> str:
        """Ask to download vid. Returns "start" | "wait" | "busy" (already tracked)."""
        if vid in self._active or vid in self._waiting:
            return "busy"
        if len(self._active) < self.max_active:
            self._active[vid] = -1
            return "start"
        self._waiting.append(vid)
        return "wait"

    def set_percent(self, vid: str, pct: int) -> None:
        if vid in self._active:
            self._active[vid] = max(-1, min(100, int(pct)))

    def finish(self, vid: str) -> list[str]:
        """Mark vid done (success or error) and return ids promoted to active."""
        self._active.pop(vid, None)
        try:
            self._waiting.remove(vid)
        except ValueError:
            pass
        promoted: list[str] = []
        while self._waiting and len(self._active) < self.max_active:
            nxt = self._waiting.pop(0)
            self._active[nxt] = -1
            promoted.append(nxt)
        return promoted
