"""Shared PortAudio selection and reversible device exclusions."""
import ctypes.util
import importlib
import json
import os
import sys


def load_sounddevice():
    dll = os.environ.get("TM_PORTAUDIO_DLL", "")
    if not dll or sys.platform != "win32":
        return importlib.import_module("sounddevice")
    if "sounddevice" in sys.modules:
        sd = sys.modules["sounddevice"]
        if os.path.normcase(getattr(sd, "_libname", "")) != os.path.normcase(dll):
            raise RuntimeError("PortAudio backend changed; restart the audio worker")
        return sd
    # Fail before sounddevice's automatic ASIO fallback if the chosen DLL is bad.
    native = ctypes.WinDLL(dll)
    original = ctypes.util.find_library
    try:
        ctypes.util.find_library = lambda name: dll if name == "portaudio" else original(name)
        sd = importlib.import_module("sounddevice")
        sd._fabric_native_library = native
        return sd
    finally:
        ctypes.util.find_library = original


def filter_devices(devices, hostapis, ignored=None):
    if ignored is None:
        try:
            ignored = json.loads(os.environ.get("TM_AUDIO_IGNORED", "[]"))
        except ValueError:
            ignored = []
    result = [dict(d) for d in devices]
    for index, device in enumerate(result):
        api = hostapis[device["hostapi"]]["name"]
        device.setdefault("index", index)
        for item in ignored:
            if item.get("name") == device["name"] and item.get("hostapi") == api:
                direction = item.get("direction")
                if direction in ("input", "output"):
                    device[f"max_{direction}_channels"] = 0
    return result


def check_selected(sd, cfg):
    """Open only selected endpoints; never mark untested devices as broken."""
    devices, apis = sd.query_devices(), sd.query_hostapis()
    failed = []
    for direction in ("input", "output"):
        name = cfg.get(f"sg_{direction}_device", "")
        api = cfg.get("sg_hostapi", "")
        if not name or not api:
            continue
        matches = [(i, d) for i, d in enumerate(devices)
                   if d["name"] == name and apis[d["hostapi"]]["name"] == api
                   and d[f"max_{direction}_channels"] > 0]
        if not matches:
            failed.append({"name": name, "hostapi": api, "direction": direction})
            continue
        index, device = matches[0]
        try:
            cls = sd.RawInputStream if direction == "input" else sd.RawOutputStream
            stream = cls(device=index, channels=min(2, device[f"max_{direction}_channels"]), samplerate=device["default_samplerate"], dtype="float32")
            stream.close()
        except Exception:
            failed.append({"name": name, "hostapi": api, "direction": direction})
    return failed
