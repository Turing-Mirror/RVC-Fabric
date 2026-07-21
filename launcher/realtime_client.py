# -*- coding: utf-8 -*-
"""Client for headless realtime_worker (start/stop/set/list_devices).

Critical: only ONE worker process must exist. Track via status.json / worker.pid.
Never kill main_app / bootstrap when sweeping orphans.
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
    read_status,
    read_worker_pid_file,
    write_command,
    write_status,
    write_worker_pid_file,
    clear_worker_pid_file,
)
from launcher.win_util import (
    CREATE_NEW_PROCESS_GROUP,
    _env_for_runtime_python,
    run_gui_process,
)

_worker_launcher: Optional[subprocess.Popen] = None

# Never kill these when sweeping Runtime processes
_KEEP_CMDLINE = (
    "main_app.py",
    "bootstrap.py",
    "rvc_launcher.py",
    "infer-web.py",
)


def worker_log_path() -> Path:
    return USER_LOGS / "realtime_worker.log"


def _pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, int(pid))
            if not handle:
                return False
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            kernel32.CloseHandle(handle)
            if not ok:
                return False
            return int(code.value) == STILL_ACTIVE
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_worker_pid() -> int:
    """Live worker PID from pid file then status.json."""
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
                creationflags=0x08000000,
            )
        except Exception:
            pass
    else:
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def _should_keep_process(cmdline: str) -> bool:
    cl = (cmdline or "").lower().replace("/", "\\")
    for keep in _KEEP_CMDLINE:
        if keep.lower() in cl:
            return True
    return False


def kill_orphan_runtime_workers(
    *, include_worker: bool = True, scan_timeout_s: float = 60.0
) -> int:
    """Kill worker + harvest children under project Runtime.

    Does NOT kill main_app / bootstrap / webui.
    ``scan_timeout_s`` caps the PowerShell process sweep (use a short value on app exit).
    """
    killed = 0
    if include_worker:
        pid = get_worker_pid()
        if pid:
            kill_process_tree(pid)
            killed += 1
        # Also kill status pid even if OpenProcess lied
        st_pid = int(read_status().get("pid") or 0)
        if st_pid and st_pid != pid:
            kill_process_tree(st_pid)
            killed += 1

    if sys.platform != "win32":
        clear_worker_pid_file()
        return killed

    # Full CIM scan is slow; allow callers (app close) to skip or use a tight timeout
    if scan_timeout_s and scan_timeout_s > 0:
        root_s = str(ROOT).replace("'", "''")
        try:
            ps = f"""
$root = '{root_s}'
Get-CimInstance Win32_Process | Where-Object {{
  $_.Name -match '^(python|pythonw)\\.exe$' -and $_.CommandLine
}} | ForEach-Object {{
  $cl = $_.CommandLine
  $keep = $false
  foreach ($k in @('main_app.py','bootstrap.py','rvc_launcher.py','infer-web.py')) {{
    if ($cl -like ('*' + $k + '*')) {{ $keep = $true }}
  }}
  if ($keep) {{ return }}
  $isOurs = (
    $cl -like ('*' + $root + '*Runtime*') -or
    $cl -like '*realtime_worker*' -or
    ($cl -like '*gui_v1.py*' -and $cl -like ('*' + $root + '*')) -or
    ($cl -like '*spawn_main*' -and $cl -like ('*' + $root + '*'))
  )
  if ($isOurs) {{
    try {{
      taskkill /F /T /PID $_.ProcessId 2>$null | Out-Null
      $_.ProcessId
    }} catch {{}}
  }}
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
                timeout=max(0.5, float(scan_timeout_s)),
                creationflags=0x08000000,
            )
            lines = [
                x.strip()
                for x in (r.stdout or "").splitlines()
                if x.strip().isdigit()
            ]
            killed = max(killed, len(lines))
        except Exception:
            pass

    clear_worker_pid_file()
    try:
        write_status(
            state="idle",
            pid=0,
            message="orphans cleared",
            error="",
            delay_ms=0,
            infer_ms=0,
        )
    except Exception:
        pass
    return killed


def kill_all_project_workers() -> int:
    """Public alias used by UI emergency button."""
    return kill_orphan_runtime_workers(include_worker=True)


def start_worker_process(*, clean_orphans: bool = True) -> None:
    """Launch tools/realtime_worker.py under Runtime if not already running."""
    global _worker_launcher
    ensure_control_dir()

    existing = get_worker_pid()
    if existing:
        return

    if clean_orphans:
        # Dead parent often leaves harvest children holding GPU / devices
        kill_orphan_runtime_workers(include_worker=True)
        time.sleep(0.4)

    script = ROOT / "tools" / "realtime_worker.py"
    if not script.is_file():
        raise FileNotFoundError(f"找不到实时 worker: {script}")

    log_path = worker_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8", errors="replace") as lf:
        lf.write(f"\n===== launch {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        lf.write(f"ROOT={ROOT}\nfrozen={getattr(sys, 'frozen', False)}\n")

    write_status(state="starting", message="launching worker…", error="", pid=0)

    rt_pyw = ROOT / "Runtime" / "pythonw.exe"
    rt_py = ROOT / "Runtime" / "python.exe"
    if rt_pyw.is_file():
        pyw = str(rt_pyw)
    elif rt_py.is_file():
        pyw = str(rt_py)
    else:
        pyw = find_python(prefer_windowed=True)

    env = _env_for_runtime_python()
    env["TM_REALTIME_WORKER"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    # Reuse parent GPU env when already set — avoid a second probe process
    try:
        from launcher.config_store import load_config
        from launcher.gpu_backend import apply_backend_env, detect_full

        if env.get("TM_ACCEL_RESOLVED") or os.environ.get("TM_ACCEL_RESOLVED"):
            for k in ("TM_USE_DML", "TM_ACCEL", "TM_ACCEL_RESOLVED"):
                if os.environ.get(k) is not None:
                    env[k] = os.environ[k]
            with open(log_path, "a", encoding="utf-8", errors="replace") as lf:
                lf.write(
                    f"accel from parent resolved={env.get('TM_ACCEL_RESOLVED')} "
                    f"dml={env.get('TM_USE_DML')}\n"
                )
        else:
            pref = str(load_config().get("accel_backend") or "auto")
            resolved = detect_full(ROOT, pref)
            env = apply_backend_env(env, resolved)
            with open(log_path, "a", encoding="utf-8", errors="replace") as lf:
                lf.write(
                    f"accel pref={pref} resolved={resolved.get('backend')} "
                    f"dml={env.get('TM_USE_DML')} detail={resolved.get('detail')}\n"
                )
    except Exception as e:
        with open(log_path, "a", encoding="utf-8", errors="replace") as lf:
            lf.write(f"accel detect skip: {e}\n")
    # Never start worker with console python.exe
    if Path(pyw).name.lower() == "python.exe" and rt_pyw.is_file():
        pyw = str(rt_pyw)
    with open(log_path, "a", encoding="utf-8", errors="replace") as lf:
        lf.write(f"via direct: {pyw} {script}\n")

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
        # pythonw = no black console; stdout still redirected to log by run_gui_process
        if rt_pyw.is_file():
            pyw = str(rt_pyw)
        elif rt_py.is_file():
            # Fallback: python.exe with CREATE_NO_WINDOW (no black box)
            pyw = str(rt_py)
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
        # Worker died mid-command
        if not is_worker_alive() and str(st.get("state")) not in ("",):
            break
        time.sleep(0.1)
    return seq


def ensure_worker_and_devices(timeout_s: float = 90.0) -> dict[str, Any]:
    if not is_worker_alive():
        start_worker_process(clean_orphans=True)
    st = wait_worker_ready(timeout_s=timeout_s)
    if str(st.get("state")) == "error" and st.get("error"):
        return st
    if str(st.get("state")) == "running":
        return st
    send_command("list_devices")
    deadline = time.time() + 30.0
    while time.time() < deadline:
        st = read_status()
        if st.get("input_devices") is not None and st.get("hostapis"):
            return st
        if not is_worker_alive():
            return {"state": "error", "error": "worker died during list_devices"}
        time.sleep(0.2)
    return read_status()


def start_vc_remote() -> int:
    if not is_worker_alive():
        start_worker_process(clean_orphans=True)
        wait_worker_ready(timeout_s=100)
    return send_command("start", wait_seq=False)


def wait_vc_running(timeout_s: float = 180.0) -> dict[str, Any]:
    """Wait until VC is running, or return error if worker dies / reports error."""
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    saw_starting = False
    while time.time() < deadline:
        last = read_status()
        state = str(last.get("state") or "")
        if state == "running":
            return last
        if state == "error":
            return last
        if state == "starting":
            saw_starting = True
        # Worker process vanished while starting
        if saw_starting and not is_worker_alive():
            # Sweep orphans left by crashed parent
            kill_orphan_runtime_workers(include_worker=True)
            return {
                "state": "error",
                "error": (
                    "变声引擎进程意外退出（常见：显存不足、声卡被占用、降噪加重负载）。"
                    "已清理残留进程，请再试一次；若仍失败可先关掉输入/输出降噪。"
                ),
                "message": "worker died during start",
            }
        if not is_worker_alive() and state not in ("starting", "running"):
            # Never came up
            pass
        time.sleep(0.35)
    if not is_worker_alive():
        kill_orphan_runtime_workers(include_worker=True)
        return {
            "state": "error",
            "error": "启动超时且引擎已退出，请查看 User_Data/logs/realtime_worker.log",
        }
    return last or {"state": "error", "error": "启动超时"}


def stop_vc_remote(force: bool = True, timeout_s: float = 15.0) -> None:
    """Stop conversion; force-kill tree if soft stop fails or leaves orphans."""
    pid = get_worker_pid()
    if not pid:
        if force:
            kill_orphan_runtime_workers(include_worker=True)
        return
    try:
        send_command("stop")
    except Exception:
        pass
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not _pid_alive(pid):
            # Parent gone — kill harvest orphans
            kill_orphan_runtime_workers(include_worker=True)
            return
        st = read_status()
        if str(st.get("state") or "") != "running":
            return
        time.sleep(0.2)
    if force:
        kill_process_tree(pid)
        kill_orphan_runtime_workers(include_worker=True)


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
    if force:
        kill_orphan_runtime_workers(include_worker=True)
    clear_worker_pid_file()
    try:
        write_status(state="idle", pid=0, message="quit", error="", delay_ms=0)
    except Exception:
        pass
    _worker_launcher = None


def shutdown_workers_for_exit(
    *, soft_wait_s: float = 0.35, scan_timeout_s: float = 1.5
) -> None:
    """Fast cleanup when the main window is closing.

    Avoids multi-second stop/quit polls that freeze the UI on exit.
    Soft-quit briefly, then kill known PIDs and a short orphan scan.
    """
    global _worker_launcher
    pid = get_worker_pid() or 0
    try:
        st_pid = int(read_status().get("pid") or 0)
    except Exception:
        st_pid = 0

    try:
        if pid or st_pid:
            try:
                send_command("stop")
            except Exception:
                pass
            try:
                send_command("quit")
            except Exception:
                pass
    except Exception:
        pass

    # Brief grace for clean stream teardown (do not wait many seconds)
    deadline = time.time() + max(0.0, float(soft_wait_s))
    while time.time() < deadline:
        still = False
        if pid and _pid_alive(pid):
            still = True
        if st_pid and st_pid != pid and _pid_alive(st_pid):
            still = True
        if not still:
            break
        time.sleep(0.04)

    for p in {pid, st_pid}:
        if p and _pid_alive(p):
            try:
                kill_process_tree(p)
            except Exception:
                pass

    try:
        kill_orphan_runtime_workers(
            include_worker=True, scan_timeout_s=float(scan_timeout_s)
        )
    except Exception:
        try:
            clear_worker_pid_file()
        except Exception:
            pass

    try:
        write_status(state="idle", pid=0, message="exit", error="", delay_ms=0)
    except Exception:
        pass
    _worker_launcher = None


def poll_status() -> dict[str, Any]:
    return read_status()
