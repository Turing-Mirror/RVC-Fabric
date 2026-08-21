# -*- coding: utf-8 -*-
"""Keep realtime audio running when a fullscreen game is in front.

pythonw.exe has no window, so Windows 11 Game Mode / EcoQoS treats the
worker as a background process and throttles it. Inference then misses
the audio deadline and the ring buffer loops the last syllable
(diag 26.8.21/1, also 26.8.19/4).
"""

from __future__ import annotations

import sys
import threading
from typing import Any

_boosted_proc = False
_boosted_thread = threading.local()


def boost_current_process(*, high: bool = False) -> None:
    """Disable EcoQoS and raise this process's scheduling class. No-op off Windows."""
    global _boosted_proc
    if sys.platform != "win32":
        return
    if _boosted_proc:
        return
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = k32.GetCurrentProcess()

        ABOVE_NORMAL = 0x00008000
        HIGH = 0x00000080
        k32.SetPriorityClass(handle, HIGH if high else ABOVE_NORMAL)

        class _Power(ctypes.Structure):
            _fields_ = [
                ("Version", wintypes.ULONG),
                ("ControlMask", wintypes.ULONG),
                ("StateMask", wintypes.ULONG),
            ]

        # ProcessPowerThrottling = 4; ExecutionSpeed bit = 0x1; StateMask 0 = off.
        state = _Power(1, 0x1, 0)
        k32.SetProcessInformation.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        k32.SetProcessInformation.restype = wintypes.BOOL
        k32.SetProcessInformation(handle, 4, ctypes.byref(state), ctypes.sizeof(state))

        # Same GPU as the game: ask the scheduler not to park our compute.
        try:
            gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
            # D3DKMT_SCHEDULINGPRIORITYCLASS_ABOVE_NORMAL = 3
            gdi32.D3DKMTSetProcessSchedulingPriorityClass(handle, 3)
        except Exception:
            pass
        _boosted_proc = True
    except Exception:
        pass


def boost_current_thread_audio() -> None:
    """MMCSS Pro Audio on this thread. For PortAudio callbacks. No-op off Windows."""
    if sys.platform != "win32" or getattr(_boosted_thread, "done", False):
        return
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        THREAD_PRIORITY_TIME_CRITICAL = 15
        k32.SetThreadPriority(k32.GetCurrentThread(), THREAD_PRIORITY_TIME_CRITICAL)

        avrt = ctypes.WinDLL("avrt", use_last_error=True)
        avrt.AvSetMmThreadCharacteristicsW.argtypes = [
            wintypes.LPCWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        avrt.AvSetMmThreadCharacteristicsW.restype = wintypes.HANDLE
        idx = wintypes.DWORD(0)
        avrt.AvSetMmThreadCharacteristicsW("Pro Audio", ctypes.byref(idx))
        _boosted_thread.done = True
    except Exception:
        pass


def begin_timer_period() -> Any:
    """1 ms timer resolution for the audio process. Call timeEndPeriod on exit."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        winmm = ctypes.WinDLL("winmm", use_last_error=True)
        winmm.timeBeginPeriod(1)
        return winmm
    except Exception:
        return None


def end_timer_period(token: Any) -> None:
    if token is None:
        return
    try:
        token.timeEndPeriod(1)
    except Exception:
        pass
