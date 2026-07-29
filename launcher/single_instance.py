# -*- coding: utf-8 -*-
"""Single-instance guard for frozen shell exes (PyInstaller onefile).

Prevents a second 变声器.exe / 启动器.exe from unpacking another ``_MEI*``
tree while the first still holds ``python313.dll`` — a common cause of::

    Failed to load Python DLL '...\\_MEI...\\python313.dll'
    LoadLibrary: The process cannot access the file because it is
    being used by another process.

Dev (non-frozen) always allows multiple instances.
"""

from __future__ import annotations

import sys
from typing import Optional

# Win32 named mutex — Local\ scope is per user session
_MUTEX_VOICE = "Local\\RVCFabric_MainApp_v1"
_MUTEX_BOOTSTRAP = "Local\\RVCFabric_Bootstrap_v1"

_held_mutex = None  # keep alive for process lifetime


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
    """Bring an existing main/bootstrap window to the foreground (best-effort)."""
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

        def _cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            title = buf.value or ""
            if title_substr in title or "图灵镜" in title or "启动器" in title:
                found.append(hwnd)
            return True

        user32.EnumWindows(EnumWindowsProc(_cb), 0)
        if not found:
            return False
        hwnd = found[0]
        # Restore if minimized
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def ensure_single_instance_or_exit(*, kind: str = "voice") -> None:
    """If another instance is running, focus it and terminate this process."""
    if acquire_single_instance(kind=kind):
        return
    title = "启动器" if kind == "bootstrap" else "RVC Fabric"
    focus_existing_main_window(title)
    # Hard exit — do not unpack further / touch MEI longer than needed
    try:
        sys.exit(0)
    except SystemExit:
        raise
    finally:
        # Belt and suspenders for frozen bootloader
        import os

        os._exit(0)
