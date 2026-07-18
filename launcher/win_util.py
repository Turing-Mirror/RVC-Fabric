# -*- coding: utf-8 -*-
"""Windows: no-console launch, desktop shortcut, open folder.

Release prefers *.exe; dev falls back to pythonw + scripts.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from launcher.paths import (
    ROOT,
    SHORTCUT_NAME,
    desktop_dir,
    find_python,
    find_release_exe,
)


CREATE_NO_WINDOW = 0x08000000


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


def open_path(path: Path | str) -> None:
    path = str(path)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def _env_with_root() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("no_proxy", "localhost,127.0.0.1,::1")
    env.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
    # Help frozen/child processes find package root
    env["TM_VOICE_ROOT"] = str(ROOT)
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
    env = _env_with_root()
    return run_no_console(
        [pyw, str(script), "--pycmd", py, "--port", str(port), "--noautoopen"],
        env=env,
    )


def start_legacy_realtime_gui() -> subprocess.Popen:
    pyw = find_python(prefer_windowed=True)
    script = ROOT / "gui_v1.py"
    env = _env_with_root()
    return run_no_console([pyw, str(script)], env=env)
