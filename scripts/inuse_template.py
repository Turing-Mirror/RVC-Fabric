# -*- coding: utf-8 -*-
"""Keep configs/inuse/config.json free of foreign absolute paths.

Setup must never ship developer machine paths (e.g. L:\\My project\\...).
Runtime also repairs polluted files on first launch / load.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

# Packaging-side only; no product-shell import.
ROOT = Path(__file__).resolve().parents[1]

# Default shape for release + repair (relative paths only; empty model ok)
CLEAN_INUSE: dict[str, Any] = {
    "pth_path": "",
    "index_path": "",
    "sg_hostapi": "MME",
    "sg_wasapi_exclusive": False,
    "sg_input_device": "",
    "sg_output_device": "",
    "sr_type": "sr_model",
    "threhold": -48,
    "pitch": 0,
    "formant": 0.0,
    "rms_mix_rate": 0.25,
    "index_rate": 0.0,
    "block_time": 0.22,
    "crossfade_length": 0.05,
    "extra_time": 2.5,
    "n_cpu": 4,
    "use_jit": False,
    "use_pv": False,
    "f0method": "fcpe",
    "monitor_device": "",
    "monitor_enabled": False,
    "I_noise_reduce": False,
    "O_noise_reduce": False,
    "function": "vc",
    "fx_enabled": False,
    # Mic pre-gain (dB); plain float — must survive sanitize (review #8)
    "in_gain_db": 0.0,
}

_ABS_WIN = re.compile(r"^[A-Za-z]:[\\/]")
_ABS_UNC = re.compile(r"^\\\\")


def inuse_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "configs" / "inuse" / "config.json"


def is_absolute_path_str(s: str) -> bool:
    t = (s or "").strip()
    if not t:
        return False
    if _ABS_WIN.match(t) or _ABS_UNC.match(t):
        return True
    # POSIX absolute (unlikely on Windows installs)
    if t.startswith("/") and not t.startswith("//"):
        return True
    return False


def path_belongs_to_root(path_str: str, root: Path) -> bool:
    """True if path is empty, relative, or under *root* and exists or is under root."""
    t = (path_str or "").strip()
    if not t:
        return True
    try:
        root_r = root.resolve()
        p = Path(t)
        if not p.is_absolute():
            # relative to package root is fine
            return True
        try:
            p.resolve().relative_to(root_r)
            return True
        except ValueError:
            return False
    except Exception:
        return False


def sanitize_inuse_dict(data: dict[str, Any], root: Path | None = None) -> tuple[dict[str, Any], list[str]]:
    """Return cleaned dict + list of fix notes."""
    base = root or ROOT
    notes: list[str] = []
    out = dict(CLEAN_INUSE)
    if isinstance(data, dict):
        # keep known keys from user data when safe
        for k, v in data.items():
            if k in CLEAN_INUSE or k.startswith("fx_"):
                out[k] = v

    for key in ("pth_path", "index_path"):
        val = str(out.get(key) or "")
        if not val:
            continue
        if is_absolute_path_str(val) and not path_belongs_to_root(val, base):
            notes.append(f"cleared foreign absolute {key}: {val}")
            out[key] = ""
            continue
        if is_absolute_path_str(val) and not os.path.isfile(val):
            notes.append(f"cleared missing absolute {key}: {val}")
            out[key] = ""
            continue
        if not is_absolute_path_str(val):
            # relative — drop if missing under root
            cand = base / val.replace("/", os.sep)
            if not cand.is_file() and not (base / val).is_file():
                # empty relative is ok for pth until user picks model
                if key == "pth_path" and val:
                    # keep relative name if user may add later; only clear obvious dead abs
                    pass
    return out, notes


def write_clean_inuse(root: Path | None = None) -> Path:
    p = inuse_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(CLEAN_INUSE, ensure_ascii=False, indent=2) + "\n"
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)
    return p


def ensure_clean_inuse_config(root: Path | None = None) -> list[str]:
    """Repair configs/inuse/config.json. Safe to call on every startup.

    Returns human-readable fix notes (empty if already clean).
    """
    base = Path(root or ROOT)
    p = inuse_path(base)
    notes: list[str] = []
    p.parent.mkdir(parents=True, exist_ok=True)

    if not p.is_file() or p.stat().st_size == 0:
        write_clean_inuse(base)
        return ["created clean configs/inuse/config.json"]

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            write_clean_inuse(base)
            return ["replaced non-object inuse config"]
    except Exception:
        write_clean_inuse(base)
        return ["replaced corrupt inuse config"]

    cleaned, fix = sanitize_inuse_dict(data, base)
    notes.extend(fix)
    if fix or cleaned != data:
        try:
            text = json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n"
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(p)
            if not notes:
                notes.append("normalized inuse config")
        except OSError as e:
            notes.append(f"could not write inuse config: {e}")
    return notes
