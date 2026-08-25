# -*- coding: utf-8 -*-
"""Lightweight realtime DSP worker. No torch, no RVC.

Same file protocol as ``realtime_worker.py`` / ``gui_v1.py``:

    User_Data/runtime_control/command.json
    User_Data/runtime_control/status.json

Start is seconds, not tens of seconds: numpy + sounddevice + AudioIoProcess
only. The shell must spawn this script when the user picked a DSP preset.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from collections import deque
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["TM_REALTIME_WORKER"] = "1"
os.environ["TM_WORKER_KIND"] = "dsp"
os.environ.setdefault("TM_VOICE_ROOT", str(ROOT))


def _log(msg: str, *args) -> None:
    if args:
        msg = msg % args
    print(msg, flush=True)


def main() -> None:
    try:
        from tools.win_realtime import boost_current_process

        boost_current_process()
    except Exception:
        pass
    try:
        from tools.worker_protocol import prepare_headless_windows

        prepare_headless_windows()
    except Exception:
        pass

    import numpy as np
    import sounddevice as sd

    from tools.audio_io_process import AudioIoProcess
    from tools.delay_metric import ema as _delay_ema
    from tools.delay_metric import frames_until_block_start
    from tools.delay_metric import live_delay_sec
    from tools.device_pick import fill_missing_devices, resolve_device_name
    from tools.dsp_fx import RealtimeFxChain
    from tools.dsp_presets import get_preset
    from tools.dsp_voice import VoiceChain
    from tools.msg_codes import (
        DEV_LIST_FAILED,
        DEV_REFRESHED,
        ENGINE_LOOP_ERROR,
        ENGINE_QUIT,
        ENGINE_READY,
        ENGINE_STOPPED,
        VC_BAD_SETTINGS,
        VC_NEED_MODEL,
        VC_OPENING_STREAM,
        VC_PARAMS_APPLIED,
        VC_RUNNING,
        VC_START_FAILED,
        VC_STOP_FAILED,
        VC_UNKNOWN_CMD,
        status_fields,
    )
    from tools.worker_protocol import (
        clear_worker_pid_file,
        default_status,
        read_command,
        read_status,
        write_status,
        write_worker_pid_file,
    )

    write_worker_pid_file(os.getpid())

    flag = {"vc": False}
    hostapis: list = []
    input_devices: list = []
    output_devices: list = []
    input_indices: list = []
    output_indices: list = []
    sg_hostapi = ""
    sg_input = ""
    sg_output = ""
    monitor_device = ""
    monitor_enabled = False
    wasapi_exclusive = False
    block_time = 0.22
    threhold = -60.0
    in_gain_db = 0.0
    samplerate = 48000
    channels = 2
    block_frame = 0
    dsp_preset = ""
    dsp_params: dict = {}
    fx_cfg: dict = {}
    voice_chain: VoiceChain | None = None
    fx_chain: RealtimeFxChain | None = None
    audio_proc = None
    in_mem = out_mem = None
    in_buf = out_buf = None
    in_ptr = out_ptr = play_ptr = None
    in_evt = stop_evt = None
    last_infer_ms = 0
    last_input_db = -90.0
    delay_time = 0.0
    queue_frames = 0.0
    infer_ema = 0.0
    monitor_stream = None
    monitor_q = None
    monitor_channels = 2
    monitor_sr = 0
    monitor_src_sr = 0
    rms_hold = 0.0

    def _sf(code: str, **params):
        return status_fields(code, params or None)

    def _payload():
        return {
            "worker_kind": "dsp",
            "dsp_only": True,
            "function": "fx",
            "hostapis": list(hostapis),
            "input_devices": list(input_devices),
            "output_devices": list(output_devices),
            "sg_hostapi": sg_hostapi,
            "sg_input_device": sg_input,
            "sg_output_device": sg_output,
        }

    def _write(**fields):
        fields.setdefault("worker_kind", "dsp")
        fields.setdefault("dsp_only", True)
        fields.setdefault("function", "fx")
        fields.setdefault("pid", os.getpid())
        write_status(**fields)

    def update_devices(hostapi_name=None):
        nonlocal hostapis, input_devices, output_devices
        nonlocal input_indices, output_indices, sg_hostapi
        stop_stream()
        sd._terminate()
        sd._initialize()
        devices = sd.query_devices()
        apis = sd.query_hostapis()
        for api in apis:
            for idx in api["devices"]:
                devices[idx]["hostapi_name"] = api["name"]
        hostapis = [a["name"] for a in apis]
        if hostapi_name not in hostapis:
            hostapi_name = "MME" if "MME" in hostapis else (hostapis[0] if hostapis else "")
        sg_hostapi = hostapi_name
        input_devices = [
            d["name"]
            for d in devices
            if d["max_input_channels"] > 0 and d.get("hostapi_name") == hostapi_name
        ]
        output_devices = [
            d["name"]
            for d in devices
            if d["max_output_channels"] > 0 and d.get("hostapi_name") == hostapi_name
        ]
        input_indices = [
            d.get("index", d["name"])
            for d in devices
            if d["max_input_channels"] > 0 and d.get("hostapi_name") == hostapi_name
        ]
        output_indices = [
            d.get("index", d["name"])
            for d in devices
            if d["max_output_channels"] > 0 and d.get("hostapi_name") == hostapi_name
        ]

    def set_devices(inp: str, out: str) -> None:
        nonlocal sg_input, sg_output
        in_name = resolve_device_name(inp or "", input_devices)
        out_name = resolve_device_name(out or "", output_devices)
        if in_name is None:
            raise ValueError("input %r" % (inp,))
        if out_name is None:
            raise ValueError("output %r" % (out,))
        sd.default.device[0] = input_indices[input_devices.index(in_name)]
        sd.default.device[1] = output_indices[output_devices.index(out_name)]
        sg_input, sg_output = in_name, out_name

    def _read_inuse() -> dict:
        path = ROOT / "configs" / "inuse" / "config.json"
        if not path.is_file() or path.stat().st_size <= 0:
            return {}
        try:
            raw = path.read_text(encoding="utf-8").strip()
            data = json.loads(raw) if raw else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _resolve_params(preset: str, params) -> dict:
        if not isinstance(params, dict):
            params = {}
        if preset and not params:
            got = get_preset(preset)
            if got and isinstance(got.get("params"), dict):
                params = got["params"]
        return params

    def _rebuild_chains():
        nonlocal voice_chain, fx_chain
        params = _resolve_params(dsp_preset, dsp_params)
        if not params:
            voice_chain = None
        elif voice_chain is None:
            voice_chain = VoiceChain(params)
        else:
            voice_chain.apply(params)
        try:
            if fx_chain is None:
                fx_chain = RealtimeFxChain(fx_cfg)
            else:
                fx_chain.apply_config(fx_cfg)
        except Exception:
            traceback.print_exc()
            fx_chain = None

    def _is_virtual_play(name: str) -> bool:
        low = (name or "").lower()
        if not low:
            return True
        keys = (
            "cable",
            "voicemeeter",
            "mapper",
            "steam streaming",
            "virtual cable",
            "vb-audio",
            "vb audio",
            "nvidia broadcast",
            "obs virtual",
            "stereo mix",
            "primary sound driver",
            "主声音驱动",
        )
        return any(k in low for k in keys)

    def _pick_monitor(preferred: str = "") -> str:
        outs = list(output_devices)
        if not outs:
            return preferred or ""

        def usable(n: str) -> bool:
            if not n or n == sg_output:
                return False
            if _is_virtual_play(n):
                return False
            if sg_output and (
                n.startswith(sg_output[:20]) or sg_output.startswith(n[:20])
            ):
                if "cable" in sg_output.lower() and "cable" not in n.lower():
                    return True
                if "cable" in n.lower():
                    return False
            return True

        if preferred:
            hit = resolve_device_name(preferred, outs)
            if hit and usable(hit):
                return hit
        for n in outs:
            low = n.lower()
            if usable(n) and ("耳机" in n or "headphone" in low or "headset" in low):
                return n
        for n in outs:
            if usable(n):
                return n
        return preferred if preferred in outs else (outs[0] if outs else "")

    def _close_monitor():
        nonlocal monitor_stream, monitor_q
        stream = monitor_stream
        monitor_stream = None
        monitor_q = None
        if stream is None:
            return
        try:
            stream.stop()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass

    def _open_monitor():
        nonlocal monitor_stream, monitor_q, monitor_channels, monitor_sr
        nonlocal monitor_src_sr, monitor_device
        _close_monitor()
        if not monitor_enabled:
            return
        name = (monitor_device or "").strip()
        if (not name) or _is_virtual_play(name):
            better = _pick_monitor("")
            if better:
                name = better
                monitor_device = better
        if not name or name == sg_output:
            return
        if "cable" in (sg_output or "").lower() and "cable" in name.lower():
            return
        resolved = resolve_device_name(name, output_devices)
        if resolved is None:
            better = _pick_monitor("")
            if not better:
                return
            name = better
            monitor_device = better
            resolved = resolve_device_name(name, output_devices)
        if resolved is None:
            return
        idx = output_indices[output_devices.index(resolved)]
        try:
            info = sd.query_devices(idx)
            ch = min(int(channels or 2), int(info.get("max_output_channels") or 2), 2)
            ch = max(1, ch)
            dev_sr = int(float(info.get("default_samplerate") or 0) or 0)
            sr = dev_sr if dev_sr > 0 else int(samplerate or 48000)
            q = deque(maxlen=64)
            monitor_q = q
            monitor_channels = ch
            monitor_sr = sr
            monitor_src_sr = int(samplerate or sr)

            def _cb(outdata, frames, _t, _s):
                need, pos = frames, 0
                outdata.fill(0)
                while need > 0 and q:
                    chunk = q[0]
                    take = min(need, chunk.shape[0])
                    outdata[pos : pos + take] = chunk[:take]
                    if take < chunk.shape[0]:
                        q[0] = chunk[take:]
                    else:
                        q.popleft()
                    pos += take
                    need -= take

            stream = sd.OutputStream(
                device=idx,
                samplerate=sr,
                channels=ch,
                dtype=np.float32,
                latency="high",
                blocksize=max(256, int(sr * 0.02)),
                callback=_cb,
            )
            stream.start()
            monitor_stream = stream
            _log("dsp monitor open: %s sr=%s", name, sr)
        except Exception:
            traceback.print_exc()
            monitor_stream = None
            monitor_q = None

    def _write_monitor(outdata: np.ndarray) -> None:
        q = monitor_q
        if q is None or monitor_stream is None or outdata is None:
            return
        try:
            data = np.ascontiguousarray(outdata, dtype=np.float32)
            if data.ndim == 1:
                data = data.reshape(-1, 1)
            want = int(monitor_channels or data.shape[1])
            if data.shape[1] != want:
                if want == 1:
                    data = data.mean(axis=1, keepdims=True).astype(np.float32)
                elif data.shape[1] == 1:
                    data = np.repeat(data, want, axis=1)
                else:
                    data = data[:, :want].copy()
            src_sr = int(monitor_src_sr or 0)
            dst_sr = int(monitor_sr or 0)
            if src_sr > 0 and dst_sr > 0 and src_sr != dst_sr and data.shape[0] > 1:
                n_out = max(1, int(round(data.shape[0] * float(dst_sr) / src_sr)))
                x_old = np.linspace(0.0, 1.0, data.shape[0], endpoint=False)
                x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
                cols = [
                    np.interp(x_new, x_old, data[:, c]).astype(np.float32)
                    for c in range(data.shape[1])
                ]
                data = np.stack(cols, axis=1)
            y = data - (data * data * data) * 0.15
            np.clip(y, -0.97, 0.97, out=y)
            q.append(y)
        except Exception:
            pass

    def stop_stream() -> None:
        nonlocal audio_proc, in_mem, out_mem, in_buf, out_buf
        nonlocal in_ptr, out_ptr, play_ptr, in_evt, stop_evt
        nonlocal queue_frames, infer_ema
        flag["vc"] = False
        _close_monitor()
        proc = audio_proc
        if proc is None:
            return
        _log("dsp stop_stream")
        try:
            if stop_evt is not None:
                stop_evt.set()
            if in_evt is not None:
                in_evt.set()
            if in_mem is not None:
                in_mem.close()
            if out_mem is not None:
                out_mem.close()
            if proc.is_alive():
                proc.join(timeout=3.0)
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2.0)
            if proc.is_alive():
                proc.kill()
        except Exception:
            traceback.print_exc()
        finally:
            audio_proc = None
            in_mem = out_mem = None
            in_buf = out_buf = None
            in_ptr = out_ptr = play_ptr = None
            in_evt = stop_evt = None
            queue_frames = 0.0
            infer_ema = 0.0

    def _live_ms() -> int:
        lat = 0.0
        if audio_proc is not None:
            try:
                v = float(audio_proc.get_latency())
                if 0.0 <= v < 5.0:
                    lat = v
            except Exception:
                pass
        sr = float(samplerate or 0) or 1.0
        blk = (
            float(block_frame) / sr
            if block_frame
            else float(block_time or 0.0)
        )
        return int(
            round(
                1000.0
                * live_delay_sec(
                    device=lat,
                    block=blk,
                    queued=queue_frames / sr,
                    infer=infer_ema,
                )
            )
        )

    def audio_loop():
        nonlocal last_infer_ms, last_input_db, rms_hold, queue_frames, infer_ema
        buf_size = int(block_frame) << 1
        while flag["vc"]:
            try:
                if in_evt is None or in_buf is None or out_buf is None:
                    break
                got = in_evt.wait(timeout=0.5)
                if not flag["vc"]:
                    return
                if not got or in_ptr is None or out_ptr is None:
                    continue
                rptr = int(in_ptr.value)
                in_evt.clear()
                t0 = time.perf_counter()
                rend = rptr + block_frame
                chunk = np.copy(in_buf[rptr:rend])
                if chunk.ndim == 2:
                    indata = chunk.mean(axis=1).astype(np.float32)
                else:
                    indata = np.asarray(chunk, dtype=np.float32).reshape(-1)
                if abs(in_gain_db) >= 0.05:
                    indata = indata * np.float32(10.0 ** (in_gain_db / 20.0))
                    np.clip(indata, -1.0, 1.0, out=indata)
                rms = float(np.sqrt(np.mean(np.square(indata))) + 1e-9)
                last_input_db = float(max(-90.0, 20.0 * np.log10(rms)))
                if threhold > -60:
                    db = last_input_db
                    if db < threhold:
                        rms_hold = max(0.0, rms_hold - 0.35)
                    else:
                        rms_hold = 1.0
                    if rms_hold <= 0.0:
                        indata = np.zeros_like(indata)
                    elif rms_hold < 1.0:
                        indata = indata * np.float32(rms_hold)
                y = indata
                if voice_chain is not None:
                    y = voice_chain.process(y, int(samplerate))
                if fx_chain is not None and getattr(fx_chain, "enabled", False):
                    y = fx_chain.process(y, int(samplerate))
                y = np.asarray(y, dtype=np.float32).reshape(-1)
                if y.shape[0] != block_frame:
                    out = np.zeros(block_frame, dtype=np.float32)
                    n = min(block_frame, int(y.shape[0]))
                    if n > 0:
                        out[:n] = y[:n]
                    y = out
                y = y - (y * y * y) * 0.15
                np.clip(y, -0.97, 0.97, out=y)
                if channels <= 1:
                    outdata = y.reshape(-1, 1)
                else:
                    outdata = np.repeat(y.reshape(-1, 1), int(channels), axis=1)
                _write_monitor(outdata)
                if out_buf is None or not flag["vc"] or out_ptr is None or play_ptr is None:
                    return
                start = int(out_ptr.value)
                play_pos = int(play_ptr.value)
                delta = (start - play_pos + buf_size) % buf_size
                write_pos = play_pos if delta < block_frame else (start + block_frame) % buf_size
                end = (write_pos + block_frame) % buf_size
                if end > write_pos:
                    out_buf[write_pos:end] = outdata
                else:
                    first = buf_size - write_pos
                    out_buf[write_pos:] = outdata[:first]
                    out_buf[:end] = outdata[first:]
                out_ptr.value = write_pos
                last_infer_ms = int((time.perf_counter() - t0) * 1000)
                wait = frames_until_block_start(
                    write_pos, play_pos, int(block_frame), int(buf_size)
                )
                queue_frames = _delay_ema(queue_frames, float(wait))
                if last_infer_ms > 8:
                    infer_ema = _delay_ema(infer_ema, last_infer_ms / 1000.0)
            except Exception:
                traceback.print_exc()
                break

    def start_stream() -> None:
        nonlocal audio_proc, in_mem, out_mem, in_buf, out_buf
        nonlocal in_ptr, out_ptr, play_ptr, in_evt, stop_evt, delay_time
        if flag["vc"]:
            return
        flag["vc"] = True
        exclusive = bool(wasapi_exclusive and "WASAPI" in (sg_hostapi or ""))
        audio_proc = AudioIoProcess(
            input_device=sd.default.device[0],
            output_device=sd.default.device[1],
            input_audio_block_size=block_frame,
            sample_rate=int(samplerate),
            channel_num=int(channels),
            is_input_wasapi_exclusive=exclusive,
            is_output_wasapi_exclusive=exclusive,
            is_device_combined=True,
        )
        in_mem = SharedMemory(name=audio_proc.get_in_mem_name())
        out_mem = SharedMemory(name=audio_proc.get_out_mem_name())
        in_buf = np.ndarray(
            audio_proc.get_np_shape(),
            dtype=audio_proc.get_np_dtype(),
            buffer=in_mem.buf,
            order="C",
        )
        out_buf = np.ndarray(
            audio_proc.get_np_shape(),
            dtype=audio_proc.get_np_dtype(),
            buffer=out_mem.buf,
            order="C",
        )
        in_ptr, out_ptr, play_ptr, in_evt, stop_evt = audio_proc.get_ptrs_and_events()
        audio_proc.start()
        try:
            _open_monitor()
        except Exception:
            traceback.print_exc()
        threading.Thread(target=audio_loop, name="dsp-audio", daemon=True).start()
        delay_time = float(block_time) + 0.01
        if audio_proc is not None:
            for _ in range(20):
                lat = float(audio_proc.get_latency())
                if 0 <= lat < 5.0:
                    delay_time = lat + float(block_time) + 0.01
                    break
                time.sleep(0.05)

    def apply_cfg(data: dict) -> None:
        nonlocal sg_hostapi, wasapi_exclusive, monitor_device, monitor_enabled
        nonlocal block_time, threhold, in_gain_db, dsp_preset, dsp_params, fx_cfg
        host = str(data.get("sg_hostapi") or sg_hostapi or "")
        try:
            update_devices(host or None)
        except Exception:
            traceback.print_exc()
        inn, out, notes = fill_missing_devices(
            str(data.get("sg_input_device") or ""),
            str(data.get("sg_output_device") or ""),
            input_devices,
            output_devices,
        )
        for n in notes:
            _log("device pick: %s", n)
        set_devices(inn or "", out or "")
        wasapi_exclusive = bool(data.get("sg_wasapi_exclusive"))
        monitor_device = str(data.get("monitor_device") or "")
        monitor_enabled = bool(data.get("monitor_enabled") or data.get("monitor_self"))
        block_time = float(data.get("block_time") or 0.22)
        threhold = float(data.get("threhold") if data.get("threhold") is not None else -60)
        in_gain_db = float(data.get("in_gain_db") or 0.0)
        dsp_preset = str(data.get("dsp_preset") or "").strip()
        dsp_params = data.get("dsp_params") if isinstance(data.get("dsp_params"), dict) else {}
        fx_cfg = {
            "fx_enabled": bool(data.get("fx_enabled")),
            "fx_gate_enabled": bool(data.get("fx_gate_enabled", True)),
            "fx_gate_threshold_db": float(data.get("fx_gate_threshold_db", -50)),
            "fx_gate_release_ms": float(data.get("fx_gate_release_ms", 50)),
            "fx_gate_hold_ms": float(data.get("fx_gate_hold_ms", 20)),
            "fx_gate_range_db": float(data.get("fx_gate_range_db", 20)),
            "fx_comp_enabled": bool(data.get("fx_comp_enabled", True)),
            "fx_comp_threshold_db": float(data.get("fx_comp_threshold_db", -20)),
            "fx_comp_ratio": float(data.get("fx_comp_ratio", 4)),
            "fx_comp_attack_ms": float(data.get("fx_comp_attack_ms", 5)),
            "fx_comp_release_ms": float(data.get("fx_comp_release_ms", 100)),
            "fx_comp_makeup_db": float(data.get("fx_comp_makeup_db", 0)),
            "fx_eq_enabled": bool(data.get("fx_eq_enabled", True)),
            "fx_eq_gains": data.get("fx_eq_gains") or [0, 0, 0, 0, 0],
            "fx_eq_preset": str(data.get("fx_eq_preset") or "flat"),
            "fx_out_gain_db": float(data.get("fx_out_gain_db") or 0),
        }

    def start_vc(cmd=None) -> None:
        nonlocal samplerate, channels, block_frame, dsp_preset, dsp_params
        stop_stream()
        data = _read_inuse()
        if isinstance(cmd, dict):
            for k in ("dsp_enabled", "dsp_preset", "dsp_params", "function"):
                if k in cmd and cmd.get(k) is not None:
                    data[k] = cmd[k]
        _write(
            state="starting",
            error="",
            progress=40,
            **_payload(),
            **_sf(VC_OPENING_STREAM),
        )
        apply_cfg(data)
        dsp_preset = str(data.get("dsp_preset") or dsp_preset or "").strip()
        dsp_params = _resolve_params(
            dsp_preset,
            data.get("dsp_params") if isinstance(data.get("dsp_params"), dict) else dsp_params,
        )
        if not dsp_params:
            _write(state="error", error="请先选用一个 DSP 预设", **_sf(VC_NEED_MODEL))
            return
        _rebuild_chains()
        if voice_chain is None:
            _write(state="error", error="请先选用一个 DSP 预设", **_sf(VC_BAD_SETTINGS))
            return
        if voice_chain is not None:
            voice_chain.reset()
        if fx_chain is not None:
            try:
                fx_chain.reset()
            except Exception:
                pass
        samplerate = int(sd.query_devices(device=sd.default.device[0])["default_samplerate"])
        max_in = int(sd.query_devices(device=sd.default.device[0])["max_input_channels"])
        max_out = int(sd.query_devices(device=sd.default.device[1])["max_output_channels"])
        channels = min(max_in, max_out, 2)
        zc = max(1, samplerate // 100)
        block_frame = int(np.round(block_time * samplerate / zc)) * zc
        _log(
            "dsp start preset=%s sr=%s block=%s effects=%s",
            dsp_preset or "-",
            samplerate,
            block_frame,
            ",".join(voice_chain.active()) if voice_chain else "-",
        )
        start_stream()
        live = _live_ms()
        _write(
            state="running",
            error="",
            progress=100,
            delay_ms=live,
            real_delay_ms=live,
            infer_ms=0,
            samplerate=int(samplerate),
            **_payload(),
            **_sf(VC_RUNNING),
        )

    def apply_hot(payload: dict) -> None:
        nonlocal threhold, in_gain_db, dsp_preset, dsp_params, monitor_enabled
        nonlocal monitor_device, block_time
        if payload.get("threhold") is not None:
            threhold = float(payload["threhold"])
        if payload.get("in_gain_db") is not None:
            in_gain_db = float(payload["in_gain_db"])
        if payload.get("block_time") is not None:
            block_time = float(payload["block_time"])
        mon_changed = False
        if "monitor_enabled" in payload or "monitor_self" in payload:
            new_en = bool(payload.get("monitor_enabled", payload.get("monitor_self")))
            if new_en != monitor_enabled:
                mon_changed = True
            monitor_enabled = new_en
        if payload.get("monitor_device") is not None:
            new_dev = str(payload.get("monitor_device") or "")
            if new_dev != monitor_device:
                mon_changed = True
            monitor_device = new_dev
        if mon_changed and flag["vc"]:
            try:
                if monitor_enabled:
                    _open_monitor()
                else:
                    _close_monitor()
            except Exception:
                traceback.print_exc()
        fx_keys = (
            "fx_enabled",
            "fx_gate_enabled",
            "fx_gate_threshold_db",
            "fx_gate_release_ms",
            "fx_gate_hold_ms",
            "fx_gate_range_db",
            "fx_comp_enabled",
            "fx_comp_threshold_db",
            "fx_comp_ratio",
            "fx_comp_attack_ms",
            "fx_comp_release_ms",
            "fx_comp_makeup_db",
            "fx_eq_enabled",
            "fx_eq_gains",
            "fx_eq_preset",
            "fx_out_gain_db",
        )
        if any(k in payload for k in fx_keys):
            for k in fx_keys:
                if k in payload and payload[k] is not None:
                    fx_cfg[k] = payload[k]
            _rebuild_chains()
        if any(k in payload for k in ("dsp_enabled", "dsp_preset", "dsp_params")):
            if payload.get("dsp_preset") is not None:
                dsp_preset = str(payload.get("dsp_preset") or "")
            if isinstance(payload.get("dsp_params"), dict):
                dsp_params = payload["dsp_params"]
            if payload.get("dsp_enabled") is False:
                # Shell is leaving DSP. Keep the stream as dry until they
                # restart on the RVC worker — do not invent a torch path here.
                pass
            _rebuild_chains()

    def list_devices(host=None) -> None:
        try:
            update_devices(host or sg_hostapi or None)
            _write(
                state="running" if flag["vc"] else "idle",
                error="",
                **_payload(),
                **_sf(DEV_REFRESHED),
            )
        except Exception as e:
            traceback.print_exc()
            _write(state="error", error="list_devices: %s" % e, **_sf(DEV_LIST_FAILED))

    # ---- boot ----
    try:
        data = _read_inuse()
        apply_cfg(data)
    except Exception as e:
        _log("dsp boot devices: %s", e)
        try:
            update_devices(None)
        except Exception:
            traceback.print_exc()

    base = default_status()
    base.update(_payload())
    base["state"] = "idle"
    base["pid"] = os.getpid()
    base["progress"] = 100
    base.update(_sf(ENGINE_READY))
    write_status(**base)
    _log("dsp worker ready pid=%s", os.getpid())

    try:
        boot_ts = float((read_status() or {}).get("worker_boot_ts") or time.time())
        prev = read_command()
        last_seq = int(prev.get("seq") or 0)
        cmd_ts = float(prev.get("ts") or 0.0)
        if last_seq > 0 and boot_ts > 0 and cmd_ts >= boot_ts - 1.0:
            last_seq = last_seq - 1
    except Exception:
        last_seq = 0

    running = True
    try:
        while running:
            try:
                cmd = read_command()
                seq = int(cmd.get("seq") or 0)
                if seq > last_seq and cmd.get("cmd"):
                    last_seq = seq
                    action = str(cmd.get("cmd") or "").strip().lower()
                    _log("dsp cmd seq=%s action=%s", seq, action)
                    _write(last_cmd_seq=seq)
                    if action == "quit":
                        stop_stream()
                        _write(state="idle", pid=0, **_sf(ENGINE_QUIT))
                        running = False
                        break
                    if action == "list_devices":
                        list_devices(cmd.get("sg_hostapi") or cmd.get("hostapi"))
                    elif action == "start":
                        try:
                            start_vc(cmd)
                        except Exception as e:
                            traceback.print_exc()
                            stop_stream()
                            _write(
                                state="error",
                                error="%s: %s" % (type(e).__name__, e),
                                **_sf(VC_START_FAILED),
                            )
                    elif action == "stop":
                        try:
                            stop_stream()
                            _write(
                                state="idle",
                                error="",
                                delay_ms=0,
                                real_delay_ms=0,
                                infer_ms=0,
                                progress=100,
                                **_payload(),
                                **_sf(ENGINE_STOPPED),
                            )
                        except Exception as e:
                            traceback.print_exc()
                            _write(
                                state="error",
                                error="stop: %s" % e,
                                **_sf(VC_STOP_FAILED),
                            )
                    elif action == "set":
                        params = (
                            cmd.get("params")
                            if isinstance(cmd.get("params"), dict)
                            else cmd
                        )
                        apply_hot(params)
                        if flag["vc"]:
                            live = _live_ms()
                            _write(
                                state="running",
                                progress=100,
                                delay_ms=live,
                                real_delay_ms=live,
                                infer_ms=last_infer_ms,
                                **_payload(),
                                **_sf(VC_PARAMS_APPLIED),
                            )
                    elif action in ("convert", "sts_cancel"):
                        _write(
                            **_sf(VC_UNKNOWN_CMD, action=action),
                            last_cmd_seq=seq,
                        )
                    else:
                        _write(**_sf(VC_UNKNOWN_CMD, action=action), last_cmd_seq=seq)
                if flag["vc"]:
                    if audio_proc is not None:
                        lat = float(audio_proc.get_latency())
                        if 0 <= lat < 5.0:
                            delay_time = lat + float(block_time) + 0.01
                    live = _live_ms()
                    _write(
                        state="running",
                        delay_ms=live,
                        real_delay_ms=live,
                        infer_ms=last_infer_ms,
                        input_db=round(float(last_input_db), 1),
                        samplerate=int(samplerate or 0),
                        progress=100,
                        **_payload(),
                    )
            except Exception as e:
                traceback.print_exc()
                _write(
                    state="error",
                    error="loop: %s: %s" % (type(e).__name__, e),
                    **_sf(ENGINE_LOOP_ERROR),
                )
            time.sleep(0.08)
    finally:
        try:
            stop_stream()
        except Exception:
            pass
        clear_worker_pid_file()
        _log("dsp worker exit pid=%s", os.getpid())


if __name__ == "__main__":
    try:
        from tools.worker_protocol import write_status as _boot
        from tools.msg_codes import ENGINE_DSP_STARTING, status_fields as _boot_sf

        _boot(
            state="starting",
            progress=10,
            worker_kind="dsp",
            dsp_only=True,
            function="fx",
            pid=os.getpid(),
            worker_boot_ts=time.time(),
            **_boot_sf(ENGINE_DSP_STARTING),
        )
    except Exception:
        pass
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        tb = traceback.format_exc()
        print("DSP WORKER FATAL:\n" + tb, flush=True)
        try:
            from tools.worker_protocol import write_status
            from tools.msg_codes import ENGINE_CRASH_LOAD, status_fields

            write_status(
                state="error",
                error="dsp worker crashed",
                worker_kind="dsp",
                **status_fields(ENGINE_CRASH_LOAD),
            )
        except Exception:
            pass
        raise
