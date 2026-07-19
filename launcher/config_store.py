# -*- coding: utf-8 -*-
"""用户配置（User_Data/app_config.json）+ 实时引擎配置同步。"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Optional

from launcher.paths import CONFIG_PATH, ROOT, USER_DATA, ensure_dirs

logger = logging.getLogger(__name__)

# Full set aligned with gui_v1 GUIConfig / configs/inuse/config.json
DEFAULTS: dict[str, Any] = {
    "pitch": 0,
    "formant": 0.0,
    # 0 = no FAISS index required (most catalog models ship without .index)
    "index_rate": 0.0,
    "rms_mix_rate": 0.0,
    "threhold": -60,
    "f0method": "fcpe",
    "block_time": 0.25,
    "crossfade_length": 0.05,
    "extra_time": 2.5,
    "n_cpu": 4,
    "sr_type": "sr_model",
    "sg_hostapi": "MME",
    "sg_wasapi_exclusive": False,
    "sg_input_device": "",
    "sg_output_device": "",
    "input_device": "",  # legacy alias
    "output_device": "",
    "monitor_device": "",  # headphones to hear yourself while VC runs
    "monitor_enabled": False,  # 边变声边听自己
    "I_noise_reduce": False,
    "O_noise_reduce": False,
    "input_noise_reduce": False,  # legacy alias → I_noise_reduce
    "output_noise_reduce": False,
    "use_pv": False,
    "function": "vc",  # vc | im
    # GPU: auto | cuda | dml | cpu  (official RVC: CUDA vs --dml DirectML)
    "accel_backend": "auto",
    "last_model": "",
    "last_model_name": "",
    "last_model_path": "",
    "desktop_shortcut_done": False,
    "vbcable_hint_done": False,
}

# gui_v1.py / realtime_worker read this file on launch / start
GUI_CONFIG_PATH = ROOT / "configs" / "inuse" / "config.json"
GUI_CONFIG_TEMPLATE = ROOT / "configs" / "config.json"


def _normalize_cfg(data: dict[str, Any]) -> dict[str, Any]:
    """Merge defaults and resolve legacy key aliases."""
    out = dict(DEFAULTS)
    out.update(data or {})
    # Legacy noise keys
    if data.get("input_noise_reduce") is not None and "I_noise_reduce" not in data:
        out["I_noise_reduce"] = bool(data.get("input_noise_reduce"))
    if data.get("output_noise_reduce") is not None and "O_noise_reduce" not in data:
        out["O_noise_reduce"] = bool(data.get("output_noise_reduce"))
    # Legacy device keys
    if not out.get("sg_input_device") and out.get("input_device"):
        out["sg_input_device"] = out["input_device"]
    if not out.get("sg_output_device") and out.get("output_device"):
        out["sg_output_device"] = out["output_device"]
    out["input_noise_reduce"] = bool(out.get("I_noise_reduce"))
    out["output_noise_reduce"] = bool(out.get("O_noise_reduce"))
    out["input_device"] = str(out.get("sg_input_device") or "")
    out["output_device"] = str(out.get("sg_output_device") or "")
    return out


def load_config() -> dict[str, Any]:
    ensure_dirs()
    if not CONFIG_PATH.is_file():
        return dict(DEFAULTS)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(DEFAULTS)
        return _normalize_cfg(data)
    except Exception:
        return dict(DEFAULTS)


def save_config(cfg: dict[str, Any]) -> None:
    ensure_dirs()
    merged = _normalize_cfg(cfg)
    CONFIG_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically so readers never see a truncated empty file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _load_gui_json() -> dict[str, Any]:
    GUI_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not GUI_CONFIG_PATH.is_file() or GUI_CONFIG_PATH.stat().st_size == 0:
        # Empty/corrupt file is common after a crash mid-write — repair
        if GUI_CONFIG_TEMPLATE.is_file():
            try:
                shutil.copy(GUI_CONFIG_TEMPLATE, GUI_CONFIG_PATH)
            except Exception:
                GUI_CONFIG_PATH.write_text("{}", encoding="utf-8")
        else:
            GUI_CONFIG_PATH.write_text("{}", encoding="utf-8")
    try:
        raw = GUI_CONFIG_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            raise ValueError("empty config")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        # Last resort: rewrite empty object so next read works
        try:
            GUI_CONFIG_PATH.write_text("{}", encoding="utf-8")
        except Exception:
            pass
        return {}


def _prefer_cable_devices(data: dict[str, Any]) -> None:
    """Light cleanup of stale device strings; real matching is in engine."""
    for key in ("sg_input_device", "sg_output_device"):
        val = str(data.get(key) or "")
        if val and len(val) < 4:
            data[key] = ""
    if not data.get("sg_hostapi"):
        data["sg_hostapi"] = "MME"


def app_cfg_to_engine_settings(cfg: dict[str, Any]) -> dict[str, Any]:
    """Map app_config fields to configs/inuse/config.json shape."""
    c = _normalize_cfg(cfg)
    return {
        "pitch": float(c.get("pitch") or 0),
        "formant": float(c.get("formant") or 0),
        "index_rate": float(c.get("index_rate") or 0),
        "rms_mix_rate": float(c.get("rms_mix_rate") or 0),
        "threhold": int(c.get("threhold") if c.get("threhold") is not None else -60),
        "f0method": str(c.get("f0method") or "fcpe"),
        "block_time": float(c.get("block_time") or 0.25),
        "crossfade_length": float(c.get("crossfade_length") or 0.05),
        "extra_time": float(c.get("extra_time") or 2.5),
        "n_cpu": int(c.get("n_cpu") or 4),
        "sr_type": str(c.get("sr_type") or "sr_model"),
        "sg_hostapi": str(c.get("sg_hostapi") or "MME"),
        "sg_wasapi_exclusive": bool(c.get("sg_wasapi_exclusive")),
        "sg_input_device": str(c.get("sg_input_device") or ""),
        "sg_output_device": str(c.get("sg_output_device") or ""),
        "monitor_device": str(c.get("monitor_device") or ""),
        "monitor_enabled": bool(c.get("monitor_enabled")),
        "use_pv": bool(c.get("use_pv")),
        "I_noise_reduce": bool(c.get("I_noise_reduce")),
        "O_noise_reduce": bool(c.get("O_noise_reduce")),
        "use_jit": False,
        "function": str(c.get("function") or "vc"),
    }


def sync_realtime_gui_model(
    pth_path: str,
    index_path: str = "",
    *,
    pitch: Optional[float] = None,
    formant: Optional[float] = None,
    index_rate: Optional[float] = None,
    f0method: Optional[str] = None,
    rms_mix_rate: Optional[float] = None,
    app_cfg: Optional[dict[str, Any]] = None,
    **extra: Any,
) -> Path:
    """Write selected model + settings into configs/inuse/config.json.

    Used by legacy gui_v1 and by realtime_worker start.
    """
    data = _load_gui_json()
    if app_cfg:
        data.update(app_cfg_to_engine_settings(app_cfg))

    pth = str(Path(pth_path).resolve()) if pth_path else ""
    data["pth_path"] = pth
    idx = ""
    if index_path:
        ip = Path(index_path)
        if ip.is_file():
            idx = str(ip.resolve())
    data["index_path"] = idx

    if pitch is not None:
        data["pitch"] = float(pitch)
    if formant is not None:
        data["formant"] = float(formant)
    if not idx:
        data["index_rate"] = 0.0
    elif index_rate is not None:
        data["index_rate"] = float(index_rate)
    if f0method:
        data["f0method"] = str(f0method)
    if rms_mix_rate is not None:
        data["rms_mix_rate"] = float(rms_mix_rate)

    for k, v in extra.items():
        if v is not None:
            data[k] = v

    data.setdefault("sr_type", "sr_model")
    data.setdefault("threhold", -60)
    data.setdefault("block_time", 0.25)
    data.setdefault("crossfade_length", 0.05)
    data.setdefault("extra_time", 2.5)
    data.setdefault("n_cpu", 4)
    data.setdefault("use_jit", False)
    data.setdefault("use_pv", False)
    data.setdefault("sg_wasapi_exclusive", False)
    data.setdefault("I_noise_reduce", False)
    data.setdefault("O_noise_reduce", False)
    _prefer_cable_devices(data)

    atomic_write_json(GUI_CONFIG_PATH, data)
    logger.info("Synced realtime engine config -> %s", pth)
    return GUI_CONFIG_PATH


def sync_full_config(cfg: dict[str, Any], pth_path: str = "", index_path: str = "") -> Path:
    """Save app config and mirror everything to inuse/config.json."""
    save_config(cfg)
    pth = pth_path or str(cfg.get("last_model_path") or "")
    idx = index_path
    return sync_realtime_gui_model(pth, idx, app_cfg=cfg)
