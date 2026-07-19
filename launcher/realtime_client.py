# -*- coding: utf-8 -*-
"""Client for headless realtime_worker (start/stop/set/list_devices).

Critical: only ONE worker process must exist. VBS launches detach immediately,
so we track the real worker via status.json / worker.pid, not the wscript Popen.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from launcher.paths import ROOT, USER_LOGS, find_python
from launcher.realtime_protocol import (
    ensure_control_dir,
    read_command,
    read_status,
    read_worker_pid_file,
    write_command,
    write_status,
    write_worker_pid_file,
    clear_worker_pid_file,
    PID_PATH,
)
from launcher.win_util import (
    CREATE_NEW_PROCESS_GROUP,
    _env_for_runtime_python,
    run_gui_process,
)

_worker_launcher: Optional[subprocess.Popen] = None


def worker_log_path() -> Path:
    return USER_LOGS / "realtime_worker.log"


def _pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            # Windows: OpenProcess + GetExitCode or use ctypes
            import ctypes

            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, int(pid))
            if not handle:
                return False
            kernel32.CloseHandle(handle)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_worker_pid() -> int:
    """Best-effort live worker PID from pid file then status.json."""
    for pid in (read_worker_pid_file(), int(read_status().get("pid") or 0)):
        if pid and _pid_alive(pid):
            return int(pid)
    return 0


def is_worker_alive() -> bool:
    return get_worker_pid() > 0


def kill_process_tree(pid: int) -> None:
    if not pid or pid <= 0:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(int(pid))],
                capture_output=True,
                timeout=15,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
        except Exception:
            pass
    else:
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def kill_all_project_workers() -> int:
    """Kill every Runtime python(w) that looks like our worker / its children.

    Used when stop fails or multiple orphans accumulated.
    """
    killed = 0
    # Prefer known pid first
    pid = get_worker_pid()
    if pid:
        kill_process_tree(pid)
        killed += 1
    if sys.platform != "win32":
        clear_worker_pid_file()
        return killed
    try:
        # WMI: find processes whose command line references our worker or Runtime under ROOT
        root_s = str(ROOT).replace("'", "''")
        ps = f"""
$root = '{root_s}'
Get-CimInstance Win32_Process | Where-Object {{
  $_.Name -match '^(python|pythonw)\\.exe$' -and $_.CommandLine -and (
    $_.CommandLine -like ('*' + $root + '*Runtime*') -or
    $_.CommandLine -like '*realtime_worker*' -or
    ($_.CommandLine -like '*gui_v1.py*' -and $_.CommandLine -like ('*' + $root + '*'))
  )
}} | ForEach-Object {{
  try {{ taskkill /F /T /PID $_.ProcessId 2>$null | Out-Null; $_.ProcessId }} catch {{}}
}}
"""
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
        lines = [x.strip() for x in (r.stdout or "").splitlines() if x.strip().isdigit()]
        killed = max(killed, len(lines))
    except Exception:
        pass
    clear_worker_pid_file()
    try:
        write_status(state="idle", pid=0, message="force killed", error="", delay_ms=0, infer_ms=0)
    except Exception:
        pass
    return killed


def start_worker_process() -> None:
    """Launch tools/realtime_worker.py under Runtime if not already running."""
    global _worker_launcher
    ensure_control_dir()

    existing = get_worker_pid()
    if existing:
        # Already have a live worker — do not spawn another
        return

    script = ROOT / "tools" / "realtime_worker.py"
    if not script.is_file():
        raise FileNotFoundError(f"找不到实时 worker: {script}")

    log_path = worker_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8", errors="replace") as lf:
        lf.write(f"\n===== launch {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        lf.write(f"ROOT={ROOT}\nfrozen={getattr(sys, 'frozen', False)}\n")

    write_status(state="starting", message="launching worker…", error="", pid=0)

    # Prefer direct Runtime pythonw — VBS parent exits so Popen cannot track life
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
    # If find_python returned system python, still prefer project Runtime
    rt_pyw = ROOT / "Runtime" / "pythonw.exe"
    rt_py = ROOT / "Runtime" / "python.exe"
    if rt_pyw.is_file():
        pyw = str(rt_pyw)
    elif rt_py.is_file():
        pyw = str(rt_py)

    env = _env_for_runtime_python()
    env["TM_REALTIME_WORKER"] = "1"
    with open(log_path, "a", encoding="utf-8", errors="replace") as lf:
        lf.write(f"via direct: {pyw} {script}\n")

    # Frozen parent: VBS is more reliable for env scrubbing; still track via pid file
    use_vbs = getattr(sys, "frozen", False) and sys.platform == "win32"
    vbs = ROOT / "launcher" / "OpenRealtimeWorker.vbs"
    if use_vbs and vbs.is_file():
        wscript = (
            Path(os.environ.get("SystemRoot", r"C:\Windows"))
            / "System32"
            / "wscript.exe"
        )
        with open(log_path, "a", encoding="utf-8", errors="replace") as lf:
            lf.write(f"via VBS: {vbs}\n")
        _worker_launcher = subprocess.Popen(
            [str(wscript), "//nologo", str(vbs)],
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
    else:
        _worker_launcher = run_gui_process(
            [pyw, str(script)], cwd=ROOT, env=env, log_path=log_path
        )


def wait_worker_ready(timeout_s: float = 90.0) -> dict[str, Any]:
    """Wait until a live worker reports idle/running/error with pid."""
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = read_status()
        pid = int(last.get("pid") or 0) or read_worker_pid_file()
        st = str(last.get("state") or "")
        if pid and _pid_alive(pid) and st in ("idle", "running", "error"):
            write_worker_pid_file(pid)
            return last
        # hostapis present + live pid
        if pid and _pid_alive(pid) and last.get("hostapis"):
            write_worker_pid_file(pid)
            return last
        time.sleep(0.25)
    return last or {"state": "error", "error": "worker ready timeout"}


def send_command(
    cmd: str, wait_seq: bool = False, timeout_s: float = 120.0, **payload: Any
) -> int:
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
    """Start single worker if needed, list devices, return status."""
    if not is_worker_alive():
        start_worker_process()
    st = wait_worker_ready(timeout_s=timeout_s)
    if str(st.get("state")) == "error" and st.get("error"):
        return st
    # Don't list_devices while VC running — that stops the stream
    if str(st.get("state")) == "running":
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
    if not is_worker_alive():
        start_worker_process()
        wait_worker_ready(timeout_s=100)
    return send_command("start", wait_seq=False)


def stop_vc_remote(force: bool = True, timeout_s: float = 15.0) -> None:
    """Stop conversion; if stream still reports running, force-kill tree.

    Soft stop keeps the worker process (faster next start). Force kill is only
    used when the stream does not become idle — avoids orphan audio loops.
    """
    pid = get_worker_pid()
    if not pid:
        if force:
            kill_all_project_workers()
        return
    try:
        send_command("stop")
    except Exception:
        pass
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not _pid_alive(pid):
            clear_worker_pid_file()
            write_status(state="idle", pid=0, message="worker exited", delay_ms=0)
            return
        st = read_status()
        if str(st.get("state") or "") != "running":
            # Stream stopped; worker may remain idle for reuse
            return
        time.sleep(0.2)
    if force and str(read_status().get("state") or "") == "running":
        kill_process_tree(pid)
        # Harvest children may outlive main briefly — sweep Runtime workers
        kill_all_project_workers()
        clear_worker_pid_file()
        write_status(
            state="idle",
            pid=0,
            message="force stopped",
            error="",
            delay_ms=0,
            infer_ms=0,
        )


def set_params_remote(**params: Any) -> int:
    if not is_worker_alive():
        return 0
    return send_command("set", **params)


def quit_worker(force: bool = True) -> None:
    global _worker_launcher
    pid = get_worker_pid()
    try:
        if pid:
            send_command("quit")
            deadline = time.time() + 8
            while time.time() < deadline and _pid_alive(pid):
                time.sleep(0.2)
    except Exception:
        pass
    if pid and _pid_alive(pid) and force:
        kill_process_tree(pid)
    if force:
        # Sweep any leftover harvest/worker children from this project Runtime
        kill_all_project_workers()
    clear_worker_pid_file()
    try:
        write_status(state="idle", pid=0, message="quit", error="", delay_ms=0)
    except Exception:
        pass
    _worker_launcher = None


def poll_status() -> dict[str, Any]:
    return read_status()
