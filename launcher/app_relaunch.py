# -*- coding: utf-8 -*-
"""Schedule a delayed relaunch of the main shell (post gui_patch).

Frozen builds hold a single-instance mutex; a child started *before* we exit
would see the mutex and quit. We therefore start a detached ``cmd`` that waits
briefly, then ``start``s the exe after this process has exited and released
the mutex (and MEI tree).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from launcher.paths import ROOT, is_frozen


# CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
_WIN_DETACHED = 0x08000000 | 0x00000008 | 0x00000200


def delayed_start_cmd(target: Path, *, delay_s: float = 1.5) -> list[str]:
    """Return argv for a detached delayed start of *target* (Windows)."""
    path = str(Path(target).resolve())
    # ping -n N ≈ N-1 seconds; keep at least ~1.5s
    n = max(3, int(delay_s) + 2)
    # start "" "path" — empty title required when path is quoted
    inner = f'ping 127.0.0.1 -n {n} >nul & start "" "{path}"'
    return ["cmd.exe", "/c", inner]


def resolve_main_app_target() -> Path:
    """Executable or entry script to relaunch."""
    if is_frozen():
        return Path(sys.executable).resolve()
    vbs = ROOT / "OpenApp.vbs"
    if vbs.is_file():
        return vbs
    bat = ROOT / "start_app.bat"
    if bat.is_file():
        return bat
    return (ROOT / "launcher" / "main_app.py").resolve()


def schedule_self_relaunch(*, delay_s: float = 1.5, target: Optional[Path] = None) -> Path:
    """Spawn delayed relaunch process. Returns the path that will be started.

    Caller must then exit this process promptly (e.g. ``_on_close(force_exit=True)``).
    """
    path = Path(target or resolve_main_app_target()).resolve()
    if not path.exists() and path.suffix.lower() != ".py":
        raise FileNotFoundError(f"找不到可重启目标：{path}")

    if path.suffix.lower() == ".py":
        # Dev: delay then python -m / script
        n = max(3, int(delay_s) + 2)
        py = sys.executable
        inner = (
            f'ping 127.0.0.1 -n {n} >nul & '
            f'start "" "{py}" "{path}"'
        )
        argv = ["cmd.exe", "/c", inner]
        cwd = str(ROOT)
    elif path.suffix.lower() == ".vbs":
        n = max(3, int(delay_s) + 2)
        inner = (
            f'ping 127.0.0.1 -n {n} >nul & '
            f'wscript.exe //B "{path}"'
        )
        argv = ["cmd.exe", "/c", inner]
        cwd = str(ROOT)
    else:
        argv = delayed_start_cmd(path, delay_s=delay_s)
        cwd = str(path.parent)

    kwargs: dict = {
        "cwd": cwd,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = _WIN_DETACHED
        # Avoid flashing a console if DETACHED fails on some hosts
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            kwargs["startupinfo"] = si
        except Exception:
            pass

    subprocess.Popen(argv, **kwargs)
    return path
