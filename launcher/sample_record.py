# -*- coding: utf-8 -*-
"""Short mic / line-in capture for consult-pack samples.

Uses sounddevice (same stack as device list + realtime engine). Pure of Tk so
the UI can drive start/stop and unit tests can mock the stream.

Roles:
  * ``dry``  — original voice; prefers the app's configured input mic
  * ``wet``  — converted voice; prefers CABLE Output (what games hear) while VC runs

Writes 16-bit mono WAV under ``User_Data/consult_samples/``.
"""

from __future__ import annotations

import os
import threading
import time
import wave
from typing import Callable, Optional

DEFAULT_SR = 48000
MAX_SECONDS = 45
MIN_SECONDS = 1.0

_CABLE_OUT_HINTS = (
    "cable output",
    "cable out",
    "vb-audio virtual cable",
    "vb-audio point",
)


class SampleRecordError(RuntimeError):
    """User-facing capture failure."""


def samples_dir(user_data: str) -> str:
    d = os.path.join(user_data, "consult_samples")
    os.makedirs(d, exist_ok=True)
    return d


def resolve_device_name(role: str, cfg: Optional[dict] = None) -> str:
    """Pick a device name for dry/wet capture (empty = system default)."""
    cfg = cfg or {}
    if role == "dry":
        return str(cfg.get("sg_input_device") or cfg.get("input_device") or "").strip()
    # wet: prefer virtual cable capture side
    preferred = str(cfg.get("consult_wet_device") or "").strip()
    if preferred:
        return preferred
    # probe sounddevice for CABLE Output
    try:
        import sounddevice as sd

        for d in sd.query_devices():
            if int(d.get("max_input_channels") or 0) <= 0:
                continue
            name = str(d.get("name") or "")
            low = name.lower()
            if any(h in low for h in _CABLE_OUT_HINTS):
                return name
    except Exception:
        pass
    # last resort: same as dry (user may still browse/import a file)
    return str(cfg.get("sg_input_device") or cfg.get("input_device") or "").strip()


def _device_index(name: str) -> Optional[int]:
    if not name:
        return None
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        # exact then substring
        for i, d in enumerate(devices):
            if str(d.get("name") or "") == name and int(d.get("max_input_channels") or 0) > 0:
                return i
        low = name.lower()
        for i, d in enumerate(devices):
            if low in str(d.get("name") or "").lower() and int(
                d.get("max_input_channels") or 0
            ) > 0:
                return i
    except Exception:
        return None
    return None


def write_wav_int16(path: str, samples, samplerate: int) -> None:
    """``samples``: 1-D sequence of float in [-1, 1] or int16."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        import numpy as np

        arr = np.asarray(samples)
        if arr.ndim > 1:
            arr = arr.reshape(-1, arr.shape[-1]).mean(axis=1)
        if arr.dtype != np.int16:
            arr = np.clip(arr.astype(np.float64), -1.0, 1.0)
            arr = (arr * 32767.0).astype(np.int16)
        pcm = arr.tobytes()
        nframes = int(arr.shape[0])
    except Exception:
        # stdlib fallback: assume iterable of float
        import array
        import struct

        buf = array.array("h")
        for x in samples:
            try:
                v = float(x)
            except (TypeError, ValueError):
                v = 0.0
            if v > 1.0:
                v = 1.0
            elif v < -1.0:
                v = -1.0
            buf.append(int(v * 32767.0))
        pcm = buf.tobytes()
        nframes = len(buf)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(samplerate))
        wf.writeframes(pcm)


class SampleRecorder:
    """Start/stop capture on a background sounddevice stream."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stream = None
        self._chunks: list = []
        self._sr = DEFAULT_SR
        self._started_at = 0.0
        self._role = ""
        self._path = ""
        self._on_auto_stop: Optional[Callable[[str], None]] = None
        self._timer: Optional[threading.Timer] = None
        self._error = ""

    @property
    def recording(self) -> bool:
        with self._lock:
            return self._stream is not None

    @property
    def role(self) -> str:
        return self._role

    @property
    def elapsed(self) -> float:
        if not self._started_at:
            return 0.0
        return max(0.0, time.time() - self._started_at)

    def start(
        self,
        path: str,
        *,
        role: str = "dry",
        device_name: str = "",
        samplerate: int = DEFAULT_SR,
        max_seconds: float = MAX_SECONDS,
        on_auto_stop: Optional[Callable[[str], None]] = None,
    ) -> None:
        if self.recording:
            raise SampleRecordError("已经在录音中，请先停止。")
        try:
            import sounddevice as sd
            import numpy as np  # noqa: F401 — required by sounddevice callbacks
        except Exception as e:
            raise SampleRecordError(
                "本机无法录音（缺少 sounddevice/numpy）。\n"
                "可改用「浏览」选择已有音频文件。\n详情：%s" % e
            ) from e

        dev = _device_index(device_name)
        self._chunks = []
        self._sr = int(samplerate or DEFAULT_SR)
        self._role = role
        self._path = path
        self._error = ""
        self._on_auto_stop = on_auto_stop

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            if status:
                pass
            with self._lock:
                self._chunks.append(indata.copy())

        try:
            stream = sd.InputStream(
                device=dev,
                channels=1,
                samplerate=self._sr,
                dtype="float32",
                callback=callback,
            )
            stream.start()
        except Exception as e:
            raise SampleRecordError(
                "打不开录音设备「%s」。\n"
                "原声请选真实麦克风；变声后请选 CABLE Output（或先浏览文件）。\n"
                "详情：%s" % (device_name or "系统默认", e)
            ) from e

        with self._lock:
            self._stream = stream
            self._started_at = time.time()

        if max_seconds and max_seconds > 0:
            self._timer = threading.Timer(float(max_seconds), self._auto_stop)
            self._timer.daemon = True
            self._timer.start()

    def _auto_stop(self) -> None:
        cb = self._on_auto_stop
        try:
            path = self.stop(save=True)
            if cb and path:
                cb(path)
        except Exception:
            # Still notify UI so the button leaves 停止 (review #30)
            if cb:
                try:
                    cb("")
                except Exception:
                    pass

    def stop(self, save: bool = True) -> str:
        """Stop capture; write WAV when *save* is True. Returns path or ""."""
        with self._lock:
            stream = self._stream
            self._stream = None
            chunks = list(self._chunks)
            self._chunks = []
            path = self._path
            sr = self._sr
            started = self._started_at
        if self._timer is not None:
            try:
                self._timer.cancel()
            except Exception:
                pass
            self._timer = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self._started_at = 0.0
        self._role = ""
        if not save:
            # Discard without writing (review #31 cancel path)
            if path:
                try:
                    if os.path.isfile(path):
                        os.unlink(path)
                except OSError:
                    pass
            return ""
        if not path:
            raise SampleRecordError("内部错误：未设置保存路径。")
        elapsed = time.time() - started if started else 0.0
        if elapsed < MIN_SECONDS and not chunks:
            raise SampleRecordError("录音太短，请再说一会儿。")
        if not chunks:
            raise SampleRecordError("没有录到声音，请检查麦克风/线路。")
        try:
            import numpy as np

            data = np.concatenate(chunks, axis=0).reshape(-1)
        except Exception:
            flat = []
            for c in chunks:
                try:
                    flat.extend(float(x) for x in c.reshape(-1))
                except Exception:
                    pass
            data = flat
        write_wav_int16(path, data, sr)
        return path

    def cancel(self) -> None:
        """Stop without saving; discard any in-progress sample (review #31)."""
        try:
            if self.recording:
                self.stop(save=False)
        except Exception:
            pass
        with self._lock:
            self._stream = None
            self._chunks = []
            self._started_at = 0.0
            self._role = ""
