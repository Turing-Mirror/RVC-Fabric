# -*- coding: utf-8 -*-
"""Headless realtime VC worker entry.

Runs the same engine as gui_v1.py without FreeSimpleGUI window.
Main app controls it via User_Data/runtime_control/*.json.

Usage (from package root, Runtime python)::

    set TM_REALTIME_WORKER=1
    Runtime\\pythonw.exe tools\\realtime_worker.py
"""

from __future__ import annotations

import os
import runpy
import sys
import time
import traceback
import warnings
from datetime import datetime
from pathlib import Path

# torch 2.0 prints this on every TypedStorage touch. A single start_vc can
# dump hundreds of KB and the diagnostics packer used to keep only the tail,
# so the actual start_vc / delay lines disappeared.
warnings.filterwarnings(
    "ignore",
    message=r".*TypedStorage is deprecated.*",
    category=UserWarning,
)


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def _worker_log_path(root: Path) -> Path:
    """Daily file under User_Data/logs/worker/ — same layout as the shell."""
    day = datetime.now().strftime("%Y-%m-%d")
    log_dir = root / "User_Data" / "logs" / "worker"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{day}.log"


def _append_log(root: Path, text: str) -> None:
    try:
        path = _worker_log_path(root)
        with open(path, "a", encoding="utf-8", errors="replace") as f:
            f.write(text)
            if not text.endswith("\n"):
                f.write("\n")
    except Exception:
        pass


def _tee_stdio(root: Path) -> None:
    """Mirror print/traceback into the daily worker log (pythonw has no console)."""
    try:
        path = _worker_log_path(root)
        # line-buffered text file
        stream = open(path, "a", encoding="utf-8", errors="replace", buffering=1)

        class _Tee:
            def __init__(self, primary, secondary):
                self._p = primary
                self._s = secondary

            def write(self, data):
                text = data if isinstance(data, str) else str(data)
                if "TypedStorage is deprecated" in text or "untyped_storage()" in text:
                    return
                try:
                    if self._p is not None:
                        self._p.write(data)
                except Exception:
                    pass
                try:
                    self._s.write(data)
                    self._s.flush()
                except Exception:
                    pass

            def flush(self):
                try:
                    if self._p is not None:
                        self._p.flush()
                except Exception:
                    pass
                try:
                    self._s.flush()
                except Exception:
                    pass

            def isatty(self):
                return False

        sys.stdout = _Tee(getattr(sys, "stdout", None), stream)
        sys.stderr = _Tee(getattr(sys, "stderr", None), stream)
    except Exception:
        pass


def _write_status_early(root: Path, **fields) -> None:
    """Best-effort status before heavy imports (so shell is not stuck on starting)."""
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from tools.worker_protocol import write_status, write_worker_pid_file

        pid = os.getpid()
        write_worker_pid_file(pid)
        write_status(pid=pid, **fields)
    except Exception as e:
        _append_log(root, f"early status write failed: {e}")


def main() -> None:
    root = _root()
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.environ["TM_REALTIME_WORKER"] = "1"
    os.environ.setdefault("TM_VOICE_ROOT", str(root))
    try:
        from tools.win_realtime import boost_current_process

        boost_current_process()
    except Exception:
        pass

    _tee_stdio(root)
    _append_log(
        root,
        f"\n===== worker process {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====\n"
        f"pid={os.getpid()} exe={sys.executable}\n"
        f"root={root}\n"
        f"TM_ACCEL={os.environ.get('TM_ACCEL')} "
        f"TM_ACCEL_RESOLVED={os.environ.get('TM_ACCEL_RESOLVED')} "
        f"TM_USE_DML={os.environ.get('TM_USE_DML')}\n",
    )
    try:
        from tools.msg_codes import ENGINE_STARTING, status_fields
    except Exception:
        ENGINE_STARTING = "engine.starting"

        def status_fields(code, **extra):  # type: ignore[misc]
            return {"message_code": code, "message": "引擎进程已启动，正在加载…", **extra}

    boot_ts = time.time()
    _write_status_early(
        root,
        state="starting",
        error="",
        progress=8,
        worker_boot_ts=boot_ts,
        **status_fields(ENGINE_STARTING),
    )

    gui = root / "gui_v1.py"
    if not gui.is_file():
        msg = f"gui_v1.py not found: {gui}"
        _append_log(root, msg)
        try:
            from tools.msg_codes import ENGINE_MISSING_GUI, status_fields as _sf
        except Exception:
            ENGINE_MISSING_GUI = "engine.missing_gui"

            def _sf(code, **extra):  # type: ignore[misc]
                return {
                    "message_code": code,
                    "message": "安装不完整：缺少引擎主程序",
                    **extra,
                }

        _write_status_early(root, state="error", error=msg, **_sf(ENGINE_MISSING_GUI))
        raise SystemExit(msg)

    try:
        try:
            from tools.msg_codes import ENGINE_IMPORTING, status_fields as _sf_imp

            _write_status_early(
                root,
                state="starting",
                error="",
                progress=14,
                worker_boot_ts=boot_ts,
                **_sf_imp(ENGINE_IMPORTING),
            )
        except Exception:
            _write_status_early(
                root,
                state="starting",
                error="",
                progress=14,
                worker_boot_ts=boot_ts,
                message_code="engine.importing",
                message="正在导入推理库（可能需要十几秒）…",
            )
        runpy.run_path(str(gui), run_name="__main__")
    except SystemExit:
        raise
    except BaseException as e:
        tb = traceback.format_exc()
        _append_log(root, "WORKER FATAL:\n" + tb)
        try:
            from tools.worker_protocol import write_status
            from tools.msg_codes import ENGINE_CRASH_LOAD, status_fields as _sf2

            write_status(
                state="error",
                error=f"{type(e).__name__}: {e}"[:200],
                pid=0,
                **_sf2(ENGINE_CRASH_LOAD),
            )
        except Exception:
            try:
                from tools.worker_protocol import write_status

                write_status(
                    state="error",
                    error=f"{type(e).__name__}: {e}"[:200],
                    message="引擎加载时崩溃，详见日志",
                    message_code="engine.crash_load",
                    pid=0,
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    main()
