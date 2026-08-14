# -*- coding: utf-8 -*-
"""STS 输入目录实时录音。

用 Runtime 里的 sounddevice 打开设置页同一个输入设备，把人声写成 wav，
存到语音转换的输入文件夹。不是变声，也不占 GPU。

用法::

    Runtime\\python.exe tools/record_worker.py <请求.json>

请求::

    {
      "output": "绝对路径.wav",
      "device": "设置里的输入设备名（可截断）",
      "hostapi": "MME",
      "stop_file": "出现此文件则停",
      "max_sec": 1800
    }

stdout 每行一条 JSON::

    {"phase":"start","device":"...","sr":44100,"message":"..."}
    {"phase":"level","db":-18.2,"sec":1.25}
    {"phase":"done","file":"...","sec":12.0}
    {"phase":"error","message":"..."}
"""

from __future__ import annotations

import json
import math
import sys
import time
import traceback
import wave
from pathlib import Path

AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}
DEFAULT_MAX_SEC = 30 * 60
BLOCK = 1024


def _ensure_stdio_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def emit(**kw) -> None:
    line = json.dumps(kw, ensure_ascii=False) + "\n"
    try:
        sys.stdout.write(line)
        sys.stdout.flush()
    except (OSError, UnicodeEncodeError):
        try:
            sys.stdout.buffer.write(line.encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
        except Exception:
            pass


def resolve_device_name(name: str, names: list[str]) -> str | None:
    """Exact or prefix match. Saved names are often truncated by UI/JSON."""
    if not name or not names:
        return None
    if name in names:
        return name
    for n in names:
        if n.startswith(name) or name.startswith(n[: max(8, len(name) - 2)]):
            return n
    head = name[:24].lower()
    for n in names:
        if n[:24].lower() == head or head in n.lower():
            return n
    return None


def list_input_devices(hostapi_name: str = "") -> list[tuple[object, str]]:
    """[(index, name), ...] for capture devices, optionally filtered by hostapi.

    Index 的取法跟 gui_v1.update_devices 一致：优先 d["index"]，没有就用名字。
    """
    import sounddevice as sd

    sd._initialize()
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    for hostapi in hostapis:
        hname = str(hostapi.get("name") or "")
        for device_idx in hostapi.get("devices") or []:
            try:
                devices[device_idx]["hostapi_name"] = hname
            except Exception:
                pass

    want = (hostapi_name or "").strip()
    out: list[tuple[object, str]] = []
    for d in devices:
        if int(d.get("max_input_channels") or 0) <= 0:
            continue
        if want and d.get("hostapi_name") != want:
            continue
        idx = d["index"] if "index" in d else d.get("name")
        out.append((idx, str(d.get("name") or "")))
    if not out and want:
        # Hostapi 对不上就放宽，总比打不开麦好。
        return list_input_devices("")
    return out


def pick_device(name: str, hostapi_name: str = "") -> tuple[object | None, str]:
    """Return (device_index, resolved_name). index is None → default device."""
    pairs = list_input_devices(hostapi_name)
    names = [n for _, n in pairs]
    resolved = resolve_device_name((name or "").strip(), names)
    if resolved is None:
        if not (name or "").strip():
            return None, ""
        # 再扫一遍全部 hostapi
        if hostapi_name:
            pairs = list_input_devices("")
            names = [n for _, n in pairs]
            resolved = resolve_device_name(name.strip(), names)
        if resolved is None:
            return None, ""
    for idx, n in pairs:
        if n == resolved:
            return idx, n
    return None, resolved


def rms_db(samples) -> float:
    """RMS 电平（dBFS）。

    录音时每秒调十几次、每次一整块 1024 帧，纯 Python 逐帧平方是白扔的开销，
    有 numpy 就走向量化。单元测试传的是普通 list，留一条回退路。
    """
    try:
        import numpy as np

        arr = np.asarray(samples, dtype=np.float64).reshape(-1)
        if arr.size == 0:
            return -90.0
        rms = float(np.sqrt(np.mean(arr * arr)))
    except Exception:
        vals = [float(x) for x in samples]
        if not vals:
            return -90.0
        rms = math.sqrt(sum(v * v for v in vals) / len(vals))
    if rms < 1e-9:
        return -90.0
    return 20.0 * math.log10(rms)


def _friendly_open_error(exc: BaseException) -> str:
    text = str(exc) or type(exc).__name__
    low = text.lower()
    if (
        "unanticipated host error" in low
        or "device unavailable" in low
        or "invalid device" in low
        or "error opening" in low
        or "portaudio" in low
    ):
        return (
            "打不开麦克风。常见原因：实时变声正在用这块设备（尤其开了 WASAPI 独占），"
            "或别的软件占着输入。请先在主界面停止变声后再试。"
        )
    return text


def record(req: dict) -> int:
    out = str(req.get("output") or "").strip()
    stop_file = Path(str(req.get("stop_file") or "").strip())
    device_name = str(req.get("device") or "").strip()
    hostapi = str(req.get("hostapi") or "").strip()
    try:
        max_sec = float(req.get("max_sec") or DEFAULT_MAX_SEC)
    except (TypeError, ValueError):
        max_sec = float(DEFAULT_MAX_SEC)
    max_sec = max(1.0, min(max_sec, float(DEFAULT_MAX_SEC)))

    if not out:
        emit(phase="error", message="缺少输出路径")
        return 2

    dest = Path(out)
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        import numpy as np
        import sounddevice as sd
    except Exception as e:
        emit(phase="error", message=f"录音组件不可用：{e}")
        return 1

    try:
        idx, resolved = pick_device(device_name, hostapi)
    except Exception as e:
        emit(phase="error", message=f"枚举输入设备失败：{e}")
        return 1

    if device_name and not resolved:
        emit(phase="error", message=f"找不到输入设备：{device_name}")
        return 1

    kwargs: dict = {"channels": 1, "dtype": "float32", "blocksize": BLOCK}
    if idx is not None:
        kwargs["device"] = idx
    try:
        info = sd.query_devices(idx if idx is not None else None, "input")
        sr = int(info.get("default_samplerate") or 44100)
        kwargs["samplerate"] = sr
        # 始终按单声道开；多声道设备由 PortAudio 自己降混。
    except Exception:
        sr = 44100
        kwargs["samplerate"] = sr

    label = resolved or device_name or "系统默认"
    emit(
        phase="start",
        device=label,
        sr=int(kwargs["samplerate"]),
        message=f"正在录音（{label}）",
    )

    frames = 0
    t0 = time.monotonic()
    last_emit = 0.0
    try:
        with sd.InputStream(**kwargs) as stream, wave.open(str(dest), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(int(kwargs["samplerate"]))
            while True:
                if stop_file.exists():
                    break
                elapsed = time.monotonic() - t0
                if elapsed >= max_sec:
                    break
                block, _overflow = stream.read(BLOCK)
                mono = np.asarray(block, dtype=np.float32)
                if mono.ndim > 1:
                    mono = mono.mean(axis=1)
                pcm = np.clip(mono * 32767.0, -32768, 32767).astype(np.int16)
                wf.writeframes(pcm.tobytes())
                frames += int(mono.shape[0])
                now = time.monotonic()
                if now - last_emit >= 0.08:
                    last_emit = now
                    emit(
                        phase="level",
                        db=round(rms_db(mono), 1),
                        sec=round(now - t0, 2),
                    )
    except Exception as e:
        traceback.print_exc()
        emit(phase="error", message=_friendly_open_error(e))
        return 1

    sec = frames / float(kwargs["samplerate"] or 1)
    if frames <= 0:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        emit(phase="error", message="没有录到声音")
        return 1

    emit(phase="done", file=str(dest), sec=round(sec, 2), device=label)
    return 0


def main(argv: list[str]) -> int:
    _ensure_stdio_utf8()
    if len(argv) < 2:
        emit(phase="error", message="缺请求文件参数")
        return 2
    try:
        req = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    except Exception as e:
        emit(phase="error", message=f"请求文件读不了：{e}")
        return 2
    return record(req)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except SystemExit:
        raise
    except Exception as e:
        traceback.print_exc()
        emit(phase="error", message=str(e))
        raise SystemExit(1)
