# -*- coding: utf-8 -*-
"""Client for headless realtime_worker (start/stop/set/list_devices)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from launcher.paths import ROOT, USER_LOGS, find_python
from launcher.realtime_protocol import (
    CONTROL_DIR,
    ensure_control_dir,
    read_status,
    write_command,
    write_status,
)
from launcher.win_util import (
    CREATE_NEW_PROCESS_GROUP,
    _env_for_runtime_python,
    run_gui_process,
)

_worker_proc: Optional[subprocess.Popen] = None


def worker_log_path() -> Path:
    return USER_LOGS / "realtime_worker.log"


def is_worker_alive(proc: Optional[subprocess.Popen] = None) -> bool:
    p = proc if proc is not None else _worker_proc
    if p is None:
        return False
    return p.poll() is None


def get_worker_proc() -> Optional[subprocess.Popen]:
    return _worker_proc


def start_worker_process() -> subprocess.Popen:
    """Launch tools/realtime_worker.py under Runtime (prefer VBS when frozen)."""
    global _worker_proc
    if is_worker_alive(_worker_proc):
        return _worker_proc  # type: ignore[return-value]

    ensure_control_dir()
    script = ROOT / "tools" / "realtime_worker.py"
    if not script.is_file():
        raise FileNotFoundError(f"找不到实时 worker: {script}")

    log_path = worker_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8", errors="replace") as lf:
        lf.write(f"\n===== launch {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        lf.write(f"ROOT={ROOT}\nfrozen={getattr(sys, 'frozen', False)}\n")

    # Mark status as starting so UI can show progress before pid appears
    write_status(state="starting", message="launching worker…", error="", pid=0)

    vbs_candidates = [
        ROOT / "launcher" / "OpenRealtimeWorker.vbs",
        ROOT / "OpenRealtimeWorker.vbs",
    ]
    vbs = next((p for p in vbs_candidates if p.is_file()), None)
    if vbs is not None and sys.platform == "win32":
        wscript = (
            Path(os.environ.get("SystemRoot", r"C:\Windows"))
            / "System32"
            / "wscript.exe"
        )
        if not wscript.is_file():
            wscript = Path(r"C:\Windows\System32\wscript.exe")
        env = _env_for_runtime_python()
        env["TM_REALTIME_WORKER"] = "1"
        with open(log_path, "a", encoding="utf-8", errors="replace") as lf:
            lf.write(f"via VBS: {vbs}\n")
        proc = subprocess.Popen(
            [str(wscript), "//nologo", str(vbs)],
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        _worker_proc = proc
        return proc

    pyw = find_python(prefer_windowed=True)
    if getattr(sys, "frozen", False):
        exe_name = Path(pyw).name.lower()
        if exe_name.endswith(".exe") and "python" not in exe_name:
            rt_pyw = ROOT / "Runtime" / "pythonw.exe"
            rt_py = ROOT / "Runtime" / "python.exe"
            if rt_pyw.is_file():
                pyw = str(rt_pyw)
            elif rt_py.is_file():
                pyw = str(rt_py)
            else:
                raise FileNotFoundError(
                    f"发布版找不到 Runtime\\pythonw.exe（候选 {pyw}）"
                )
    env = _env_for_runtime_python()
    env["TM_REALTIME_WORKER"] = "1"
    with open(log_path, "a", encoding="utf-8", errors="replace") as lf:
        lf.write(f"via direct: {pyw} {script}\n")
    proc = run_gui_process([pyw, str(script)], cwd=ROOT, env=env, log_path=log_path)
    _worker_proc = proc
    return proc


def wait_worker_ready(timeout_s: float = 90.0) -> dict[str, Any]:
    """Wait until status has pid or state idle/running/error after launch."""
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = read_status()
        st = str(last.get("state") or "")
        if st in ("idle", "running", "error") and (
            int(last.get("pid") or 0) > 0 or st == "error"
        ):
            return last
        # devices list also means ready
        if last.get("hostapis") or last.get("input_devices"):
            return last
        time.sleep(0.25)
    return last or {"state": "error", "error": "worker ready timeout"}


def send_command(cmd: str, wait_seq: bool = False, timeout_s: float = 120.0, **payload: Any) -> int:
    seq = write_command(cmd, **payload)
    if not wait_seq:
        return seq
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        st = read_status()
        if int(st.get("last_cmd_seq") or 0) >= seq:
            return seq
        time.sleep(0.1)
    return seq


def ensure_worker_and_devices(timeout_s: float = 90.0) -> dict[str, Any]:
    """Start worker if needed, list devices, return status."""
    start_worker_process()
    st = wait_worker_ready(timeout_s=timeout_s)
    if str(st.get("state")) == "error" and st.get("error"):
        return st
    send_command("list_devices")
    deadline = time.time() + 30.0
    while time.time() < deadline:
        st = read_status()
        if st.get("input_devices") is not None and st.get("hostapis"):
            return st
        time.sleep(0.2)
    return read_status()


def start_vc_remote() -> int:
    return send_command("start")


def stop_vc_remote() -> int:
    return send_command("stop")


def set_params_remote(**params: Any) -> int:
    return send_command("set", **params)


def quit_worker() -> None:
    global _worker_proc
    try:
        send_command("quit")
    except Exception:
        pass
    p = _worker_proc
    if p is not None and p.poll() is None:
        try:
            p.wait(timeout=5)
        except Exception:
            try:
                p.terminate()
            except Exception:
                pass
    _worker_proc = None


def poll_status() -> dict[str, Any]:
    return read_status()
