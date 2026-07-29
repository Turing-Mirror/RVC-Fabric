# -*- coding: utf-8 -*-
"""Single-instance guard for frozen shell exes (PyInstaller onefile).

Prevents a second 变声器.exe / 启动器.exe from unpacking another ``_MEI*``
tree while the first still holds ``python313.dll`` — a common cause of::

    Failed to load Python DLL '...\\_MEI...\\python313.dll'
    LoadLibrary: The process cannot access the file because it is
    being used by another process.

Dev (non-frozen) always allows multiple instances.

Tray caveat
-----------
When the main window is *withdrawn* to the tray it is **not**
``IsWindowVisible``. The first version of this guard only enumerated
visible windows, so a second desktop click found the mutex, found no
window, and ``os._exit``'d — user sees "nothing starts, no process".
We now restore hidden / iconic windows too.
"""

from __future__ import annotations

import sys
from typing import Optional

# Win32 named mutex — Local\ scope is per user session
_MUTEX_VOICE = "Local\\RVCFabric_MainApp_v1"
_MUTEX_BOOTSTRAP = "Local\\RVCFabric_Bootstrap_v1"

_held_mutex = None  # keep alive for process lifetime

# Titles we own (main app / bootstrap / legacy)
_TITLE_HINTS = (
    "RVC Fabric",
    "图灵镜",
    "启动器",
    "变声器",
)


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def acquire_single_instance(*, kind: str = "voice") -> bool:
    """Return True if this process is the sole instance; False if another owns it.

    On False, caller should try to focus the existing window and exit.
    """
    global _held_mutex
    if not _is_frozen():
        return True
    if sys.platform != "win32":
        return True

    name = _MUTEX_BOOTSTRAP if kind == "bootstrap" else _MUTEX_VOICE
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.GetLastError.restype = wintypes.DWORD

        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            return True  # fail open — better start twice than not at all
        ERROR_ALREADY_EXISTS = 183
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            try:
                kernel32.CloseHandle(handle)
            except Exception:
                pass
            return False
        _held_mutex = handle
        return True
    except Exception:
        return True


def focus_existing_main_window(title_substr: str = "RVC Fabric") -> bool:
    """Bring an existing main/bootstrap window to the foreground (best-effort).

    Includes **hidden / tray-withdrawn / minimized** windows — critical when
    the user re-clicks the desktop shortcut while the app is in the tray.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found: list = []

        EnumWindowsProc = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        hints = list(_TITLE_HINTS)
        if title_substr and title_substr not in hints:
            hints.insert(0, title_substr)

        def _cb(hwnd, _lparam):
            # Do NOT require IsWindowVisible — tray withdraw hides the root.
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            title = buf.value or ""
            if not title:
                return True
            for h in hints:
                if h and h in title:
                    found.append(hwnd)
                    break
            return True

        user32.EnumWindows(EnumWindowsProc(_cb), 0)
        if not found:
            return False

        # Prefer a visible window if any; else first match (tray-hidden)
        hwnd = found[0]
        for h in found:
            if user32.IsWindowVisible(h):
                hwnd = h
                break

        SW_RESTORE = 9
        SW_SHOW = 5
        # Restore from minimized / re-show from tray-hidden
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.SetForegroundWindow(hwnd)
        # Nudge: some Windows builds ignore SetForegroundWindow without this
        try:
            user32.BringWindowToTop(hwnd)
        except Exception:
            pass
        return True
    except Exception:
        return False


def ensure_single_instance_or_exit(*, kind: str = "voice") -> None:
    """If another instance is running, focus it and terminate this process.

    If the mutex is held but no window can be found (crashed UI / stuck tray),
    show a short message so the user is not left with a silent no-op click.
    """
    if acquire_single_instance(kind=kind):
        return
    title = "启动器" if kind == "bootstrap" else "RVC Fabric"
    ok = focus_existing_main_window(title)
    if not ok:
        # Mutex held, no window — tell the user what to do (frozen shell only)
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                (
                    "RVC Fabric 似乎已在运行（可能在右下角托盘），但找不到窗口。\n\n"
                    "请尝试：\n"
                    "1. 点任务栏 / 托盘区的 RVC Fabric 图标恢复窗口\n"
                    "2. 或打开任务管理器结束「变声器.exe / 启动器.exe」后再开\n\n"
                    "（安装版进程名不是 python.exe）"
                ),
                "RVC Fabric 已在运行",
                0x00000030,  # MB_ICONWARNING
            )
        except Exception:
            pass
    # Hard exit — do not unpack further / touch MEI longer than needed
    try:
        sys.exit(0)
    except SystemExit:
        raise
    finally:
        # Belt and suspenders for frozen bootloader
        import os

        os._exit(0)
