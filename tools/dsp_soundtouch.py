# -*- coding: utf-8 -*-
"""Official SoundTouch DLL wrapper (LGPL 2.1, dynamic link).

Speech settings match what Clownfish's APO calls:
  USE_QUICKSEEK=0, USE_AA_FILTER=1, SEQUENCE=40, SEEKWINDOW=15, OVERLAP=8.
"""

from __future__ import annotations

import ctypes
from ctypes import POINTER, c_char_p, c_float, c_int, c_uint, c_void_p
from pathlib import Path
from typing import Any, Optional

SETTING_USE_AA_FILTER = 0
SETTING_AA_FILTER_LENGTH = 1
SETTING_USE_QUICKSEEK = 2
SETTING_SEQUENCE_MS = 3
SETTING_SEEKWINDOW_MS = 4
SETTING_OVERLAP_MS = 5

_DLL_DIR = Path(__file__).resolve().parent / "soundtouch"
_LIB: Any = None
_LIB_ERROR: Optional[str] = None


def _bind(lib: Any) -> None:
    lib.soundtouch_createInstance.restype = c_void_p
    lib.soundtouch_createInstance.argtypes = []
    lib.soundtouch_destroyInstance.restype = None
    lib.soundtouch_destroyInstance.argtypes = [c_void_p]
    lib.soundtouch_setPitchSemiTones.restype = None
    lib.soundtouch_setPitchSemiTones.argtypes = [c_void_p, c_float]
    lib.soundtouch_setChannels.restype = c_int
    lib.soundtouch_setChannels.argtypes = [c_void_p, c_uint]
    lib.soundtouch_setSampleRate.restype = c_int
    lib.soundtouch_setSampleRate.argtypes = [c_void_p, c_uint]
    lib.soundtouch_putSamples.restype = c_int
    lib.soundtouch_putSamples.argtypes = [c_void_p, POINTER(c_float), c_uint]
    lib.soundtouch_receiveSamples.restype = c_uint
    lib.soundtouch_receiveSamples.argtypes = [c_void_p, POINTER(c_float), c_uint]
    lib.soundtouch_numSamples.restype = c_uint
    lib.soundtouch_numSamples.argtypes = [c_void_p]
    lib.soundtouch_clear.restype = None
    lib.soundtouch_clear.argtypes = [c_void_p]
    lib.soundtouch_setSetting.restype = c_int
    lib.soundtouch_setSetting.argtypes = [c_void_p, c_int, c_int]
    lib.soundtouch_getVersionString.restype = c_char_p
    lib.soundtouch_getVersionString.argtypes = []


def load_library() -> Any:
    """Load the official DLL once. Raises OSError if it is missing or wrong arch."""
    global _LIB, _LIB_ERROR
    if _LIB is not None:
        return _LIB
    if _LIB_ERROR is not None:
        raise OSError(_LIB_ERROR)
    path = _DLL_DIR / "SoundTouch.dll"
    try:
        lib = ctypes.CDLL(str(path))
        _bind(lib)
        _LIB = lib
        return lib
    except Exception as exc:
        _LIB_ERROR = f"SoundTouch.dll 加载失败（{path}）：{exc}"
        raise OSError(_LIB_ERROR) from exc


def available() -> bool:
    try:
        load_library()
        return True
    except OSError:
        return False


class SoundTouch:
    """One mono processor. Not thread-safe; the audio thread owns it."""

    def __init__(self, sample_rate: int) -> None:
        lib = load_library()
        handle = lib.soundtouch_createInstance()
        if not handle:
            raise OSError("soundtouch_createInstance returned NULL")
        self._lib = lib
        self._h = handle
        if lib.soundtouch_setChannels(handle, 1) == 0:
            self.close()
            raise OSError("soundtouch_setChannels failed")
        if lib.soundtouch_setSampleRate(handle, int(sample_rate)) == 0:
            self.close()
            raise OSError("soundtouch_setSampleRate failed")
        # Clownfish APO: speech preset, quality seek, AA on.
        lib.soundtouch_setSetting(handle, SETTING_USE_QUICKSEEK, 0)
        lib.soundtouch_setSetting(handle, SETTING_USE_AA_FILTER, 1)
        lib.soundtouch_setSetting(handle, SETTING_SEQUENCE_MS, 40)
        lib.soundtouch_setSetting(handle, SETTING_SEEKWINDOW_MS, 15)
        lib.soundtouch_setSetting(handle, SETTING_OVERLAP_MS, 8)
        self._pitch = 0.0

    def close(self) -> None:
        h = getattr(self, "_h", None)
        if h:
            try:
                self._lib.soundtouch_destroyInstance(h)
            except Exception:
                pass
            self._h = None

    def __del__(self) -> None:
        self.close()

    def set_pitch_semitones(self, semitones: float) -> None:
        v = float(semitones)
        if v == self._pitch:
            return
        self._lib.soundtouch_setPitchSemiTones(self._h, c_float(v))
        self._pitch = v

    def clear(self) -> None:
        self._lib.soundtouch_clear(self._h)

    def put(self, samples: Any) -> None:
        import numpy as np

        x = np.ascontiguousarray(samples, dtype=np.float32).reshape(-1)
        if x.size == 0:
            return
        self._lib.soundtouch_putSamples(
            self._h, x.ctypes.data_as(POINTER(c_float)), c_uint(x.size)
        )

    def receive(self, max_frames: int) -> Any:
        import numpy as np

        n = int(max_frames)
        if n <= 0:
            return np.zeros(0, dtype=np.float32)
        buf = np.empty(n, dtype=np.float32)
        got = int(
            self._lib.soundtouch_receiveSamples(
                self._h, buf.ctypes.data_as(POINTER(c_float)), c_uint(n)
            )
        )
        if got <= 0:
            return np.zeros(0, dtype=np.float32)
        if got >= n:
            return buf
        return buf[:got].copy()

    def num_samples(self) -> int:
        return int(self._lib.soundtouch_numSamples(self._h))
