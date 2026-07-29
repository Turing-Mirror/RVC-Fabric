# -*- coding: utf-8 -*-
"""File-based control protocol between main_app and realtime_worker.

User_Data/runtime_control/
  command.json  — main writes {seq, cmd, ...}
  status.json   — worker writes state / devices / metrics
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

from launcher.paths import USER_DATA, ensure_dirs

CONTROL_DIR = USER_DATA / "runtime_control"
COMMAND_PATH = CONTROL_DIR / "command.json"
STATUS_PATH = CONTROL_DIR / "status.json"
SEQ_PATH = CONTROL_DIR / "command.seq"
PID_PATH = CONTROL_DIR / "worker.pid"

# Windows readers holding status.json open make Path.replace raise WinError 5/32.
# Shell + worker both write status; concurrent .tmp clobber was common in field logs.
_WRITE_RETRIES = 8
_WRITE_RETRY_BASE_S = 0.01

# Hot-updatable keys (match gui_v1 event_handler)
HOT_KEYS = frozenset(
    {
        "pitch",
        "formant",
        "index_rate",
        "rms_mix_rate",
        "threhold",
        "in_gain_db",  # 麦克风增益（dB），门限/电平表之前
        "f0method",
        "I_noise_reduce",
        "O_noise_reduce",
        "use_pv",
        "function",  # "vc" | "im"
    }
)

# Changing these while running requires stop + start
COLD_KEYS = frozenset(
    {
        "pth_path",
        "index_path",
        "sg_hostapi",
        "sg_wasapi_exclusive",
        "sg_input_device",
        "sg_output_device",
        "sr_type",
        "block_time",
        "crossfade_length",
        "extra_time",
        "n_cpu",
    }
)


def ensure_control_dir() -> Path:
    ensure_dirs()
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
    """Atomic JSON write with unique temp name + retries (Windows-safe).

    Field diag (diag_20260727_151048) showed::

        PermissionError: [WinError 5] Access is denied:
          '...\\status.json.tmp' -> '...\\status.json'

    Causes: (1) shell and worker both write status.json; fixed basename .tmp
    races; (2) concurrent readers keep the destination open during replace.
    """
    ensure_control_dir()
    text = json.dumps(data, ensure_ascii=False, indent=2)
    unique = f".{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
    tmp = path.with_name(path.name + unique)
    tmp.write_text(text, encoding="utf-8")
    last_err: Optional[BaseException] = None
    for attempt in range(_WRITE_RETRIES):
        try:
            os.replace(str(tmp), str(path))
            return
        except OSError as e:
            last_err = e
            if not _is_retryable_replace_error(e):
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
                raise
            time.sleep(_WRITE_RETRY_BASE_S * (attempt + 1))
    # Last resort: non-atomic overwrite so status is not stuck forever
    try:
        path.write_text(text, encoding="utf-8")
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        if last_err is not None:
            raise last_err
        raise
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass


def next_seq() -> int:
    ensure_control_dir()
    try:
        cur = int(SEQ_PATH.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        cur = 0
    cur += 1
    SEQ_PATH.write_text(str(cur), encoding="utf-8")
    return cur


def write_command(cmd: str, **payload: Any) -> int:
    """Write a new command; returns seq number."""
    seq = next_seq()
    data: dict[str, Any] = {
        "seq": seq,
        "cmd": str(cmd),
        "ts": time.time(),
    }
    data.update(payload)
    _write_json(COMMAND_PATH, data)
    return seq


def read_command() -> dict[str, Any]:
    return _read_json(COMMAND_PATH)


def write_status(**fields: Any) -> None:
    cur = _read_json(STATUS_PATH)
    cur.update(fields)
    cur["ts"] = time.time()
    _write_json(STATUS_PATH, cur)


def read_status() -> dict[str, Any]:
    return _read_json(STATUS_PATH)


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


def clear_command_queue() -> None:
    """Optional: reset seq so a fresh worker does not re-run old start."""
    ensure_control_dir()
    if COMMAND_PATH.is_file():
        try:
            COMMAND_PATH.unlink()
        except Exception:
            pass


def write_worker_pid_file(pid: int) -> None:
    ensure_control_dir()
    PID_PATH.write_text(str(int(pid)), encoding="utf-8")


def clear_worker_pid_file() -> None:
    try:
        if PID_PATH.is_file():
            PID_PATH.unlink()
    except Exception:
        pass


def read_worker_pid_file() -> int:
    try:
        if PID_PATH.is_file():
            return int(PID_PATH.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        pass
    return 0
