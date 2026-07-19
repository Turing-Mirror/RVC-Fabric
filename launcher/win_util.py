# -*- coding: utf-8 -*-
"""Windows: no-console launch, desktop shortcut, open folder.

Release prefers *.exe; dev falls back to pythonw + scripts.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from launcher.paths import (
    ROOT,
    SHORTCUT_NAME,
    USER_LOGS,
    desktop_dir,
    find_python,
    find_release_exe,
)


CREATE_NO_WINDOW = 0x08000000
# GUI child processes must NOT use CREATE_NO_WINDOW — it can suppress or
# delay window creation for FreeSimpleGUI / tk under some Windows sessions.
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def run_no_console(
    args: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
) -> subprocess.Popen:
    kw: dict = {
        "cwd": str(cwd or ROOT),
        "env": env or os.environ.copy(),
    }
    if sys.platform == "win32":
        kw["creationflags"] = CREATE_NO_WINDOW
        kw["stdin"] = subprocess.DEVNULL
        kw["stdout"] = subprocess.DEVNULL
        kw["stderr"] = subprocess.DEVNULL
    return subprocess.Popen(args, **kw)


def run_gui_process(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict | None = None,
    log_path: Path | None = None,
    hide_console: bool = False,
) -> subprocess.Popen:
    """Start a windowed GUI process (pythonw / FreeSimpleGUI / tk).

    pythonw already has no console. For python.exe workers, pass
    hide_console=True to avoid a black cmd window (CREATE_NO_WINDOW).
    """
    cwd = cwd or ROOT
    env = env or os.environ.copy()
    kw: dict = {
        "cwd": str(cwd),
        "env": env,
        "stdin": subprocess.DEVNULL,
    }
    log_f = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_f = open(log_path, "a", encoding="utf-8", errors="replace")
        log_f.write(f"\n===== launch {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        log_f.write("cmd: " + " ".join(args) + "\n")
        log_f.flush()
        kw["stdout"] = log_f
        kw["stderr"] = subprocess.STDOUT
    else:
        kw["stdout"] = subprocess.DEVNULL
        kw["stderr"] = subprocess.DEVNULL
    if sys.platform == "win32":
        flags = CREATE_NEW_PROCESS_GROUP
        # Hide console only when requested (headless worker via python.exe).
        # Do not use CREATE_NO_WINDOW for FreeSimpleGUI/tk windows.
        exe0 = str(args[0]).lower() if args else ""
        if hide_console or exe0.endswith("python.exe"):
            if "pythonw" not in exe0:
                flags |= CREATE_NO_WINDOW
        kw["creationflags"] = flags
    proc = subprocess.Popen(args, **kw)
    # Popen keeps the file handle open for the child; do not close log_f here
    proc._tm_log_file = log_f  # type: ignore[attr-defined]
    return proc


def focus_window_by_title(title_substr: str, timeout_s: float = 45.0) -> bool:
    """Bring first visible window whose title contains title_substr to front."""
    if sys.platform != "win32":
        return False
    import ctypes

    user32 = ctypes.windll.user32
    found_hwnd = ctypes.c_void_p(0)

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _enum(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if title_substr.lower() in (buf.value or "").lower():
            found_hwnd.value = hwnd
            return False
        return True

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        found_hwnd.value = 0
        user32.EnumWindows(_enum, 0)
        if found_hwnd.value:
            hwnd = found_hwnd.value
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            return True
        time.sleep(0.5)
    return False


def read_tail(path: Path, max_chars: int = 1200) -> str:
    try:
        if not path.is_file():
            return ""
        data = path.read_text(encoding="utf-8", errors="replace")
        return data[-max_chars:] if len(data) > max_chars else data
    except Exception:
        return ""


def open_path(path: Path | str) -> None:
    path = str(path)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def open_windows_sound_panel() -> None:
    """Open classic Windows Sound control panel (Playback + Recording devices).

    This is ``mmsys.cpl`` — not Device Manager, not the simplified Settings page.
    """
    if sys.platform != "win32":
        raise OSError("仅支持 Windows 打开系统声音面板")
    # control.exe mmsys.cpl → 播放 / 录制 / 声音 / 通讯 四个选项卡
    subprocess.Popen(
        ["control.exe", "mmsys.cpl"],
        cwd=os.environ.get("SystemRoot", r"C:\Windows"),
        creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def _env_with_root() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("no_proxy", "localhost,127.0.0.1,::1")
    env.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
    # Help frozen/child processes find package root
    env["TM_VOICE_ROOT"] = str(ROOT)
    return env


def _env_for_runtime_python() -> dict:
    """Env for embedded Runtime\\python(w).exe — strip PyInstaller host pollution.

    Frozen TM_Voice.exe is built with host Python 3.13 while Runtime is 3.9.
    Inherited PYTHONHOME / _MEIPASS / host site-packages on PYTHONPATH can make
    the child exit immediately (no process left in Task Manager).
    """
    env = os.environ.copy()
    for k in list(env.keys()):
        ku = k.upper()
        if ku.startswith("PYTHON") or ku in {
            "_MEIPASS",
            "TCL_LIBRARY",
            "TK_LIBRARY",
            "TIX_LIBRARY",
        }:
            del env[k]
    rt = str((ROOT / "Runtime").resolve()) if (ROOT / "Runtime").is_dir() else str(ROOT)
    path_parts: list[str] = [rt, str(ROOT)]
    for p in env.get("PATH", "").split(os.pathsep):
        if not p:
            continue
        pl = p.replace("/", "\\").lower()
        if "_mei" in pl:
            continue
        path_parts.append(p)
    env["PATH"] = os.pathsep.join(path_parts)
    env["PYTHONPATH"] = str(ROOT)
    env["TM_VOICE_ROOT"] = str(ROOT)
    env.setdefault("no_proxy", "localhost,127.0.0.1,::1")
    env.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
    # Avoid user site overriding Runtime packages
    env["PYTHONNOUSERSITE"] = "1"
    # Preserve auto-start flag from parent main_app
    if os.environ.get("TM_AUTO_START_VC"):
        env["TM_AUTO_START_VC"] = os.environ["TM_AUTO_START_VC"]
    # GPU backend (CUDA / DirectML) — set by main_app via apply_backend_env
    for k in ("TM_USE_DML", "TM_ACCEL", "TM_ACCEL_RESOLVED"):
        if os.environ.get(k) is not None:
            env[k] = os.environ[k]
    return env


def create_desktop_shortcut(
    target_script: Path | None = None,
    name: str = SHORTCUT_NAME,
) -> Path:
    """Desktop shortcut → release 变声器.exe when present, else windowed script."""
    desk = desktop_dir()
    desk.mkdir(parents=True, exist_ok=True)
    lnk = desk / name

    app_exe = find_release_exe("app")
    script = target_script or (ROOT / "launcher" / "main_app.py")
    pyw = find_python(prefer_windowed=True)
    vbs = ROOT / "launcher" / "run_hidden.vbs"

    if sys.platform != "win32":
        sh = desk / "TuringMirror-Voice.sh"
        sh.write_text(
            f"#!/bin/sh\ncd '{ROOT}'\n'{pyw}' '{script}'\n",
            encoding="utf-8",
        )
        os.chmod(sh, 0o755)
        return sh

    if app_exe is not None and target_script is None:
        target_path = str(app_exe)
        arguments = ""
        workdir = str(ROOT)
        icon_path = target_path
    elif vbs.is_file() and target_script is None:
        target_path = r"C:\Windows\System32\wscript.exe"
        arguments = f'//nologo "{vbs}" app'
        workdir = str(ROOT)
        icon_path = target_path
    else:
        target_path = pyw
        arguments = f'"{script}"'
        workdir = str(ROOT)
        icon_path = pyw

    def _esc(s: str) -> str:
        return s.replace("'", "''")

    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut('{_esc(str(lnk))}')
$sc.TargetPath = '{_esc(target_path)}'
$sc.Arguments = '{_esc(arguments)}'
$sc.WorkingDirectory = '{_esc(workdir)}'
$sc.WindowStyle = 7
$sc.Description = 'Turing Mirror 变声器'
$sc.IconLocation = '{_esc(icon_path)},0'
$sc.Save()
"""
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps,
        ],
        check=False,
        creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if not lnk.is_file():
        if app_exe is not None:
            # copy a tiny launcher bat as last resort
            bat = desk / "TuringMirror-Voice.bat"
            bat.write_text(
                f'@echo off\ncd /d "{ROOT}"\nstart "" "{app_exe}"\n',
                encoding="gbk",
                errors="replace",
            )
            return bat
        if vbs.is_file():
            dest = desk / "TuringMirror-Voice.vbs"
            dest.write_text(
                vbs.read_text(encoding="utf-8", errors="replace"), encoding="utf-8"
            )
            return dest
        bat = desk / "TuringMirror-Voice.bat"
        bat.write_text(
            f'@echo off\ncd /d "{ROOT}"\nstart "" "{pyw}" "{script}"\n',
            encoding="gbk",
            errors="replace",
        )
        return bat
    return lnk


def start_main_app() -> subprocess.Popen:
    env = _env_with_root()
    app_exe = find_release_exe("app")
    if app_exe is not None:
        return run_no_console([str(app_exe)], env=env)
    pyw = find_python(prefer_windowed=True)
    script = ROOT / "launcher" / "main_app.py"
    return run_no_console([pyw, str(script)], env=env)


def start_bootstrap() -> subprocess.Popen:
    env = _env_with_root()
    boot = find_release_exe("bootstrap")
    if boot is not None:
        return run_no_console([str(boot)], env=env)
    pyw = find_python(prefer_windowed=True)
    script = ROOT / "launcher" / "bootstrap.py"
    return run_no_console([pyw, str(script)], env=env)


def start_webui(port: int = 7897) -> subprocess.Popen:
    py = find_python(prefer_windowed=False)
    pyw = find_python(prefer_windowed=True)
    script = ROOT / "infer-web.py"
    env = _env_for_runtime_python()
    args = [pyw, str(script), "--pycmd", py, "--port", str(port), "--noautoopen"]
    # Official AMD/Intel: infer-web.py --dml
    if os.environ.get("TM_USE_DML", "").strip().lower() in ("1", "true", "yes"):
        args.append("--dml")
    return run_no_console(args, env=env)


def start_legacy_realtime_gui() -> subprocess.Popen:
    """Launch advanced realtime panel (gui_v1 FreeSimpleGUI).

    Release/frozen path: prefer OpenRealtime.vbs (same style as OpenApp.vbs / bat).
    Direct pythonw Popen from a PyInstaller exe often leaves no child process.

    Cold start often needs 20–40s (torch/CUDA).
    Logs: User_Data/logs/realtime_gui.log and realtime_gui_vbs.log
    """
    script = ROOT / "gui_v1.py"
    if not script.is_file():
        raise FileNotFoundError(f"找不到实时面板脚本: {script}")

    log_path = USER_LOGS / "realtime_gui.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8", errors="replace") as lf:
        lf.write(f"\n===== launch {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        lf.write(f"ROOT={ROOT}\nfrozen={getattr(sys, 'frozen', False)}\n")
        lf.write(f"executable={sys.executable}\n")

    # 1) VBS route — matches working dev bat / OpenApp.vbs behavior
    vbs_candidates = [
        ROOT / "launcher" / "OpenRealtime.vbs",
        ROOT / "OpenRealtime.vbs",
    ]
    vbs = next((p for p in vbs_candidates if p.is_file()), None)
    if vbs is not None and sys.platform == "win32":
        wscript = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wscript.exe"
        if not wscript.is_file():
            wscript = Path(r"C:\Windows\System32\wscript.exe")
        env = _env_for_runtime_python()
        with open(log_path, "a", encoding="utf-8", errors="replace") as lf:
            lf.write(f"via VBS: {vbs}\n")
        # Do not use CREATE_NO_WINDOW on wscript — child GUI must be allowed
        proc = subprocess.Popen(
            [str(wscript), "//nologo", str(vbs)],
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        return proc

    # 2) Direct Runtime pythonw with cleaned env
    pyw = find_python(prefer_windowed=True)
    # Never re-exec the frozen TM_Voice.exe as "python"
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
                    f"发布版找不到 Runtime\\pythonw.exe（当前解释器候选是 {pyw}）"
                )
    env = _env_for_runtime_python()
    with open(log_path, "a", encoding="utf-8", errors="replace") as lf:
        lf.write(f"via direct: {pyw} {script}\n")
    return run_gui_process([pyw, str(script)], cwd=ROOT, env=env, log_path=log_path)


def realtime_gui_log_path() -> Path:
    return USER_LOGS / "realtime_gui.log"
