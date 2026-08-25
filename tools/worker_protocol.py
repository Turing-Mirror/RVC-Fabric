# -*- coding: utf-8 -*-
"""Worker side of the file protocol under ``User_Data/runtime_control/``.

Self-contained on purpose: the engine must not import from the product shell.
The shell used to be ``launcher/`` (Python/Tk) and is now ``app/`` (Tauri/Rust);
``tools/realtime_worker.py`` and ``gui_v1.py`` have to keep working either way.

Only what the worker needs lives here — the reader/commander side is in Rust
(``app/src-tauri/src/protocol.rs``). Both write the same shape:

    command.json   shell → worker   {seq, cmd, ...}
    status.json    worker → shell   state / devices / metrics
    sts.json       worker → shell   offline conversion progress
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
# 离线转换进度单独一个文件。塞进 status.json 的话，每秒好几条进度都会顺带
# 重写一遍引擎状态，还要跟 write_status 那条「有 message 就清 message_code」
# 的规则打架——转个音频把任务栏上的引擎状态冲掉，不值当。
STS_PATH = CONTROL_DIR / "sts.json"
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
            os.replace(tmp, path)
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
    """Merge fields into status.json.

    ``message_code`` sticks across merges. Early boot writes ``engine.starting``;
    later updates often only set ``message``/``state``. The shell localizes by
    ``message_code`` first, so a leftover code freezes the dock on
    「引擎进程已启动，正在加载…」 forever even when the worker is idle.

    Rule: any write that sets ``message`` or ``state`` without a new
    ``message_code`` clears the old code (empty string). Callers that want a
    code must pass ``message_code`` explicitly (see ``msg_codes.status_fields``).
    """
    cur = _read_json(STATUS_PATH)
    if (
        ("message" in fields or "state" in fields)
        and "message_code" not in fields
        and cur.get("message_code")
    ):
        fields = {**fields, "message_code": ""}
    cur.update(fields)
    cur["ts"] = time.time()
    _write_json(STATUS_PATH, cur)


def read_sts() -> dict[str, Any]:
    return _read_json(STS_PATH)


def write_sts(**fields: Any) -> None:
    """Replace sts.json wholesale.

    与 write_status 不同，这里**不**合并：离线转换是一次性任务，上一轮的
    files / skipped / error 留到下一轮只会让界面读到上次的结果。每次全量写。
    """
    fields["ts"] = time.time()
    _write_json(STS_PATH, fields)


def clear_sts() -> None:
    try:
        if STS_PATH.is_file():
            STS_PATH.unlink()
    except Exception:
        pass


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
        # Explicit empty so a full default write does not keep a stale code.
        "message_code": "",
        # cuda | directml | mps | xpu | cpu。空串 = 引擎还没起来，问不到。
        "compute_backend": "",
        "compute_device": "",
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


CREATE_NO_WINDOW = 0x08000000


def hide_console_subprocesses() -> None:
    """Stop ffmpeg / harvest children flashing a console on Windows.

    ``CREATE_NO_WINDOW`` is per-process. The parent may be pythonw (or python
    with the flag), but ffmpeg-python and multiprocessing still spawn
    ``ffmpeg.exe`` / ``python.exe`` without it — that's the black window every
    time 语音转换 loads a file.
    """
    import subprocess
    import sys

    if sys.platform != "win32":
        return
    if getattr(subprocess.Popen, "_tm_hidden", False):
        return

    _orig = subprocess.Popen

    class _HiddenPopen(_orig):  # type: ignore[valid-type,misc]
        _tm_hidden = True

        def __init__(self, *args, **kwargs):
            flags = kwargs.get("creationflags", 0) or 0
            kwargs["creationflags"] = int(flags) | CREATE_NO_WINDOW
            si = kwargs.get("startupinfo")
            if si is None:
                si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
            kwargs["startupinfo"] = si
            super().__init__(*args, **kwargs)

    subprocess.Popen = _HiddenPopen  # type: ignore[misc]


def prepare_headless_windows() -> None:
    """No console windows from this process or its children on Windows."""
    force_windowed_multiprocessing()
    hide_console_subprocesses()
