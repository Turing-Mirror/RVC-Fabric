# -*- coding: utf-8 -*-
"""Undo/redo stack for voice-param snapshots (pure; no Tk).

Pulled out of main_app so the edit-history behaviour is unit-testable and the
window class stops carrying two raw lists plus a limit int.
"""

from __future__ import annotations

from typing import Optional


class VoiceParamHistory:
    """Bounded undo/redo of pitch/formant/threshold/... snapshots.

    Snapshots are plain dicts. push() records the pre-edit state, dedups
    consecutive identical snapshots, and drops the redo stack (a new edit
    forks history). undo()/redo() swap through a caller-supplied "current"
    snapshot so the window never has to juggle the two lists itself.
    """

    def __init__(self, limit: int = 40) -> None:
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._limit = max(1, int(limit))

    def push(self, snap: dict) -> bool:
        """Record a snapshot before a user edit. Returns False if deduped."""
        if self._undo and self._undo[-1] == snap:
            return False
        self._undo.append(dict(snap))
        if len(self._undo) > self._limit:
            self._undo.pop(0)
        self._redo.clear()
        return True

    def undo(self, current: dict) -> Optional[dict]:
        """Pop the previous snapshot (pushing `current` onto redo). None if empty."""
        if not self._undo:
            return None
        self._redo.append(dict(current))
        return self._undo.pop()

    def redo(self, current: dict) -> Optional[dict]:
        """Pop the next snapshot (pushing `current` onto undo). None if empty."""
        if not self._redo:
            return None
        self._undo.append(dict(current))
        return self._redo.pop()

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    @property
    def undo_len(self) -> int:
        return len(self._undo)

    @property
    def redo_len(self) -> int:
        return len(self._redo)
