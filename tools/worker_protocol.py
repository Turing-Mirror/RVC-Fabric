# -*- coding: utf-8 -*-
"""Worker side of the file protocol under ``User_Data/runtime_control/``.

Self-contained on purpose: the engine must not import from the product shell.
The shell used to be ``launcher/`` (Python/Tk) and is now ``app/`` (Tauri/Rust);
``tools/realtime_worker.py`` and ``gui_v1.py`` have to keep working either way.

Only what the worker needs lives here — the reader/commander side is in Rust
(``app/src-tauri/src/protocol.rs``). Both write the same shape:

    command.json   shell → worker   {seq, cmd, ...}
    status.json    worker → shell   state / devices / metrics
    worker.pid     worker → shell   pid for liveness checks

Stdlib only.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths — derived from this file so no shell import is needed.
# tools/worker_protocol.py -> <root>/tools -> <root>
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
USER_DATA = ROOT / "User_Data"
CONTROL_DIR = USER_DATA / "runtime_control"
COMMAND_PATH = CONTROL_DIR / "command.json"
STATUS_PATH = CONTROL_DIR / "status.json"
PID_PATH = CONTROL_DIR / "worker.pid"

# Windows readers holding status.json open make Path.replace raise WinError
# 5/32. Field diagnostics (diag_20260727_151048) showed this happening on every
# slider drag, so writes use a unique temp name plus retries.
_WRITE_RETRIES = 8
_WRITE_RETRY_BASE_S = 0.01


def ensure_control_dir() -> Path:
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    return CONTROL_DIR


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _is_retryable_replace_error(exc: BaseException) -> bool:
    """PermissionError / sharing violation while replacing on Windows NTFS."""
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError):
        winerr = getattr(exc, "winerror", None)
        if winerr in (5, 32):  # ACCESS_DENIED / SHARING_VIOLATION
            return True
        if exc.errno in (13, 11, 16):  # EACCES / EAGAIN / EBUSY
            return True
    return False


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomic JSON write: unique temp name, retries, then a direct write.

    Losing a status update is better than crashing the audio thread, so the
    final fallback writes in place rather than raising.
    """
    ensure_control_dir()
    tmp = path.with_suffix(f".{os.getpid()}.{time.time_ns()}.tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2)
    try:
        tmp.write_text(text, encoding="utf-8")
    except Exception:
        return
    last: BaseException | None = None
    for attempt in range(_WRITE_RETRIES):
        try:
            tmp.replace(path)
            return
        except Exception as e:  # noqa: BLE001 — must never kill the worker
            last = e
            if not _is_retryable_replace_error(e):
                break
            time.sleep(_WRITE_RETRY_BASE_S * (attempt + 1))
    try:
        path.write_text(text, encoding="utf-8")
    except Exception:
        pass
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass
    _ = last


def read_command() -> dict[str, Any]:
    return _read_json(COMMAND_PATH)


def read_status() -> dict[str, Any]:
    return _read_json(STATUS_PATH)


def write_status(**fields: Any) -> None:
    cur = _read_json(STATUS_PATH)
    cur.update(fields)
    cur["ts"] = time.time()
    _write_json(STATUS_PATH, cur)


def write_worker_pid_file(pid: int) -> None:
    ensure_control_dir()
    try:
        PID_PATH.write_text(str(int(pid)), encoding="utf-8")
    except Exception:
        pass


def clear_worker_pid_file() -> None:
    try:
        if PID_PATH.is_file():
            PID_PATH.unlink()
    except Exception:
        pass


def default_status() -> dict[str, Any]:
    return {
        "state": "idle",  # idle | starting | running | stopping | error
        "error": "",
        "delay_ms": 0,
        "infer_ms": 0,
        "samplerate": 0,
        "hostapis": [],
        "input_devices": [],
        "output_devices": [],
        "sg_hostapi": "",
        "sg_input_device": "",
        "sg_output_device": "",
        "pid": 0,
        "last_cmd_seq": 0,
        "message": "",
    }


def force_windowed_multiprocessing() -> str | None:
    """Point multiprocessing children at pythonw.exe.

    Without this the Runtime's ``python.exe`` is used and every child flashes a
    console window at the user. Lives here rather than in the shell because the
    engine must stay importable on its own.
    """
    import sys

    if sys.platform != "win32":
        return None
    try:
        import multiprocessing as mp
    except Exception:
        return None
    try:
        exe = Path(sys.executable).resolve()
    except Exception:
        return None
    for cand in (
        exe.with_name("pythonw.exe"),
        ROOT / "Runtime" / "pythonw.exe",
        ROOT / "runtime" / "pythonw.exe",
    ):
        if cand.is_file():
            try:
                mp.set_executable(str(cand))
                return str(cand)
            except Exception:
                continue
    return None
