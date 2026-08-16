# -*- coding: utf-8 -*-
"""STS 输入目录实时录音，兼设置页的麦克风测试。

用 Runtime 里的 sounddevice 打开设置页同一个输入设备，把人声写成 wav，
存到语音转换的输入文件夹。不是变声，也不占 GPU。

`probe` 模式只开设备读电平，**不写任何文件** —— 那是「测一下麦有没有声」，
用户没打算留下一个录音，往他的输入目录里扔个 wav 是多做事。

用法::

    Runtime\\python.exe tools/record_worker.py <请求.json>

请求::

    {
      "output": "绝对路径.wav",
      "device": "设置里的输入设备名（可截断）",
      "hostapi": "MME",
      "stop_file": "出现此文件则停",
      "max_sec": 1800,
      "probe": false
    }

stdout 每行一条 JSON::

    {"phase":"start","device":"...","sr":44100,"message":"..."}
    {"phase":"level","db":-18.2,"peak":-9.4,"sec":1.25}
    {"phase":"done","file":"...","sec":12.0}
    {"phase":"error","message":"...","code":"busy"}

`code` 是给壳做多语言用的稳定标识，`message` 是中文兜底（旧壳和日志读）。
"""

from __future__ import annotations

import contextlib
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


def peak_db(samples) -> float:
    """峰值电平（dBFS）。

    RMS 是平均能量，说话的瞬间峰值比它高 10 dB 以上是常事。判断「这只麦到底
    有没有在收声」看峰值更准 —— 只看 RMS 的话，用户正常音量说一句话也可能
    停在 -40 dB 上，读起来像没声音。
    """
    try:
        import numpy as np

        arr = np.asarray(samples, dtype=np.float64).reshape(-1)
        if arr.size == 0:
            return -90.0
        peak = float(np.max(np.abs(arr)))
    except Exception:
        vals = [abs(float(x)) for x in samples]
        if not vals:
            return -90.0
        peak = max(vals)
    if peak < 1e-9:
        return -90.0
    return 20.0 * math.log10(peak)


def _open_error_code(exc: BaseException) -> str:
    """打不开设备 → 稳定标识。壳按标识出多语言文案。"""
    low = (str(exc) or type(exc).__name__).lower()
    if (
        "unanticipated host error" in low
        or "device unavailable" in low
        or "invalid device" in low
        or "error opening" in low
        or "portaudio" in low
    ):
        return "busy"
    return "open"


def _friendly_open_error(exc: BaseException) -> str:
    if _open_error_code(exc) == "busy":
        return (
            "打不开麦克风。常见原因：实时变声正在用这块设备（尤其开了 WASAPI 独占），"
            "或别的软件占着输入。请先在主界面停止变声后再试。"
        )
    return str(exc) or type(exc).__name__


def record(req: dict) -> int:
    out = str(req.get("output") or "").strip()
    stop_file = Path(str(req.get("stop_file") or "").strip())
    device_name = str(req.get("device") or "").strip()
    hostapi = str(req.get("hostapi") or "").strip()
    probe = bool(req.get("probe"))
    try:
        max_sec = float(req.get("max_sec") or DEFAULT_MAX_SEC)
    except (TypeError, ValueError):
        max_sec = float(DEFAULT_MAX_SEC)
    max_sec = max(1.0, min(max_sec, float(DEFAULT_MAX_SEC)))

    dest = None
    if not probe:
        if not out:
            emit(phase="error", message="缺少输出路径", code="nopath")
            return 2
        dest = Path(out)
        dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        import numpy as np
        import sounddevice as sd
    except Exception as e:
        emit(phase="error", message=f"录音组件不可用：{e}", code="nolib")
        return 1

    try:
        idx, resolved = pick_device(device_name, hostapi)
    except Exception as e:
        emit(phase="error", message=f"枚举输入设备失败：{e}", code="enum")
        return 1

    if device_name and not resolved:
        emit(phase="error", message=f"找不到输入设备：{device_name}", code="notfound")
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
        message=f"正在测试（{label}）" if probe else f"正在录音（{label}）",
    )

    frames = 0
    top = -90.0
    t0 = time.monotonic()
    last_emit = 0.0
    try:
        # `probe` 不落盘：contextlib.nullcontext 让下面那段循环两种模式共用一份，
        # 不用为了少写一个 wav 头再抄一遍读流的逻辑。
        writer = (
            contextlib.nullcontext() if probe else wave.open(str(dest), "wb")
        )
        with sd.InputStream(**kwargs) as stream, writer as wf:
            if wf is not None:
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
                if wf is not None:
                    pcm = np.clip(mono * 32767.0, -32768, 32767).astype(np.int16)
                    wf.writeframes(pcm.tobytes())
                frames += int(mono.shape[0])
                pk = peak_db(mono)
                if pk > top:
                    top = pk
                now = time.monotonic()
                if now - last_emit >= 0.08:
                    last_emit = now
                    emit(
                        phase="level",
                        db=round(rms_db(mono), 1),
                        peak=round(pk, 1),
                        sec=round(now - t0, 2),
                    )
    except Exception as e:
        traceback.print_exc()
        emit(phase="error", message=_friendly_open_error(e), code=_open_error_code(e))
        return 1

    sec = frames / float(kwargs["samplerate"] or 1)
    if probe:
        # 测试没有「失败」这一说：一个字节都没读到才算打不开，读到了但全是
        # 静音是**结果**，得让壳照实说「没听到声音」，而不是报错。
        if frames <= 0:
            emit(phase="error", message="没有读到任何输入", code="silent")
            return 1
        emit(phase="done", peak=round(top, 1), sec=round(sec, 2), device=label)
        return 0

    if frames <= 0:
        try:
            if dest is not None:
                dest.unlink(missing_ok=True)
        except OSError:
            pass
        emit(phase="error", message="没有录到声音", code="silent")
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
