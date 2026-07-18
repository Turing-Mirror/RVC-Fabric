# -*- coding: utf-8 -*-
"""用户配置（User_Data/app_config.json）+ 实时面板 gui_v1 配置同步。"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Optional

from launcher.paths import CONFIG_PATH, ROOT, USER_DATA, ensure_dirs

logger = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "pitch": 0,
    "formant": 0.0,
    "index_rate": 0.5,
    "rms_mix_rate": 0.0,
    "f0method": "fcpe",
    "block_time": 0.25,
    "input_device": "",
    "output_device": "",
    "monitor_device": "",
    "last_model": "",
    "last_model_name": "",
    "last_model_path": "",
    "input_noise_reduce": False,
    "output_noise_reduce": False,
    "desktop_shortcut_done": False,
    "vbcable_hint_done": False,
}

# gui_v1.py reads this file on launch
GUI_CONFIG_PATH = ROOT / "configs" / "inuse" / "config.json"
GUI_CONFIG_TEMPLATE = ROOT / "configs" / "config.json"


def load_config() -> dict[str, Any]:
    ensure_dirs()
    if not CONFIG_PATH.is_file():
        return dict(DEFAULTS)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        out = dict(DEFAULTS)
        out.update(data)
        return out
    except Exception:
        return dict(DEFAULTS)


def save_config(cfg: dict[str, Any]) -> None:
    ensure_dirs()
    merged = dict(DEFAULTS)
    merged.update(cfg)
    CONFIG_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_gui_json() -> dict[str, Any]:
    GUI_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not GUI_CONFIG_PATH.is_file():
        if GUI_CONFIG_TEMPLATE.is_file():
            shutil.copy(GUI_CONFIG_TEMPLATE, GUI_CONFIG_PATH)
        else:
            GUI_CONFIG_PATH.write_text("{}", encoding="utf-8")
    try:
        data = json.loads(GUI_CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def sync_realtime_gui_model(
    pth_path: str,
    index_path: str = "",
    *,
    pitch: Optional[float] = None,
    formant: Optional[float] = None,
    index_rate: Optional[float] = None,
    f0method: Optional[str] = None,
    rms_mix_rate: Optional[float] = None,
) -> Path:
    """Write selected model into configs/inuse/config.json for gui_v1.py.

    The advanced realtime panel only reads this file at startup — must update
    before launching it.
    """
    data = _load_gui_json()
    pth = str(Path(pth_path).resolve()) if pth_path else ""
    data["pth_path"] = pth
    if index_path:
        data["index_path"] = str(Path(index_path).resolve())
    elif "index_path" not in data:
        data["index_path"] = ""
    if pitch is not None:
        data["pitch"] = float(pitch)
    if formant is not None:
        data["formant"] = float(formant)
    if index_rate is not None:
        data["index_rate"] = float(index_rate)
    if f0method:
        data["f0method"] = str(f0method)
    if rms_mix_rate is not None:
        data["rms_mix_rate"] = float(rms_mix_rate)
    # Defaults gui_v1 expects
    data.setdefault("sr_type", "sr_model")
    data.setdefault("threhold", -60)
    data.setdefault("block_time", 0.25)
    data.setdefault("crossfade_length", 0.05)
    data.setdefault("extra_time", 2.5)
    data.setdefault("n_cpu", 4)
    data.setdefault("use_jit", False)
    data.setdefault("use_pv", False)
    data.setdefault("sg_wasapi_exclusive", False)

    GUI_CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Synced realtime GUI model -> %s", pth)
    return GUI_CONFIG_PATH
