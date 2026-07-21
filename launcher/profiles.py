# -*- coding: utf-8 -*-
"""Voice-config profiles (.tmvp) — a model can carry many, one active.

A *profile* bundles the full tunable surface (voice params + FX chain + perf)
under a name, stored per model in ``User_Data/models/<name>/profiles/*.tmvp``.
The model's own ``config.json`` inline voice params are the implicit
"default" profile and are never deleted; ``active_profile`` in config.json
points at the chosen profile ("" = default).

Everything here is pure stdlib (no Tk / torch) so the whole profile lifecycle
is unit-tested. The engine/UI wiring lives elsewhere; this module only owns
the on-disk data model, schema validation, and CRUD.

Design note: users can edit every one of these params in the settings page —
the product is fully open. What a paid service sells is the *know-how* to pick
good values, delivered as a .tmvp the user imports; the knobs themselves are
never gated.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any, Optional

from launcher.catalog import VOICE_PARAM_KEYS

PROFILE_SCHEMA_VERSION = 1
PROFILES_DIRNAME = "profiles"
PROFILE_EXT = ".tmvp"
_CONFIG_NAME = "config.json"

# Canonical tunable groups (mirror config_store defaults / catalog voice keys).
VOICE_KEYS: tuple[str, ...] = tuple(VOICE_PARAM_KEYS)
FX_KEYS: tuple[str, ...] = (
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
PERF_KEYS: tuple[str, ...] = ("block_time", "crossfade_length", "extra_time")

_F0_METHODS = frozenset({"pm", "harvest", "crepe", "rmvpe", "fcpe"})
_BOOL_FX = frozenset(
    {"fx_enabled", "fx_gate_enabled", "fx_comp_enabled", "fx_eq_enabled"}
)
_VALID_SOURCES = frozenset({"default", "self", "import", "official"})

# Range clamps match the settings-page sliders so profiles can't push the
# engine outside what the UI allows.
_PERF_RANGE = {
    "block_time": (0.02, 1.5),
    "crossfade_length": (0.01, 0.15),
    "extra_time": (0.05, 5.0),
}


# --------------------------------------------------------------------------
# small json helpers (atomic write; tolerant read)
# --------------------------------------------------------------------------
def _read_json(path: str) -> dict:
    """Tolerant read: missing/corrupt → {} (used for config.json, absent = empty)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_json_strict(path: str) -> Optional[dict]:
    """Strict read: missing/corrupt/non-dict → None (so a profile file that is
    absent or garbage is distinguishable from a real, empty ``{}`` dict)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_json_atomic(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _clampf(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# normalization / validation (tolerant: drop unknown, coerce, clamp)
# --------------------------------------------------------------------------
def normalize_voice(d: Any) -> dict:
    """Keep only known voice keys that are set; coerce types; clamp rates."""
    out: dict[str, Any] = {}
    if not isinstance(d, dict):
        return out
    for k in VOICE_KEYS:
        if k not in d or d[k] is None or d[k] == "":
            continue
        v = d[k]
        if k == "pitch":
            try:
                out[k] = int(round(float(v)))
            except (TypeError, ValueError):
                continue
        elif k == "threhold":
            try:
                out[k] = int(round(float(v)))
            except (TypeError, ValueError):
                continue
        elif k == "f0method":
            s = str(v).lower()
            if s in _F0_METHODS:
                out[k] = s
        elif k in ("index_rate", "rms_mix_rate"):
            out[k] = _clampf(v, 0.0, 1.0, 0.0)
        else:  # formant and any future float
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                continue
    return out


def normalize_fx(d: Any) -> dict:
    out: dict[str, Any] = {}
    if not isinstance(d, dict):
        return out
    for k in FX_KEYS:
        if k not in d or d[k] is None:
            continue
        v = d[k]
        if k in _BOOL_FX:
            out[k] = bool(v)
        elif k == "fx_eq_gains":
            if isinstance(v, (list, tuple)) and len(v) == 5:
                out[k] = [_clampf(g, -24.0, 24.0, 0.0) for g in v]
        elif k == "fx_eq_preset":
            out[k] = str(v)
        else:  # all *_db / *_ms / ratio floats
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                continue
    return out


def normalize_perf(d: Any) -> dict:
    out: dict[str, Any] = {}
    if not isinstance(d, dict):
        return out
    for k in PERF_KEYS:
        if k not in d or d[k] is None or d[k] == "":
            continue
        lo, hi = _PERF_RANGE[k]
        out[k] = _clampf(d[k], lo, hi, lo)
    return out


def new_profile_id() -> str:
    return uuid.uuid4().hex[:12]


def _safe_name(name: str) -> str:
    n = (name or "").strip()
    return n[:60] if n else "未命名档案"


def make_profile(
    name: str,
    *,
    voice: Optional[dict] = None,
    fx: Optional[dict] = None,
    perf: Optional[dict] = None,
    source: str = "self",
    for_model: str = "",
    score: Optional[float] = None,
    profile_id: Optional[str] = None,
) -> dict:
    """Build a validated profile dict ready to save."""
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "id": profile_id or new_profile_id(),
        "name": _safe_name(name),
        "voice": normalize_voice(voice or {}),
        "fx": normalize_fx(fx or {}),
        "perf": normalize_perf(perf or {}),
        "meta": {
            "source": source if source in _VALID_SOURCES else "self",
            "score": score,
            "for_model": str(for_model or ""),
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def validate_profile(data: Any) -> Optional[dict]:
    """Coerce an arbitrary loaded dict into a well-formed profile.

    Returns None only when the input is not a dict at all; otherwise it always
    yields a usable profile (missing/garbage fields fall back), so a hand-made
    or externally-produced .tmvp never crashes the app.
    """
    if not isinstance(data, dict):
        return None
    meta_in = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    src = str(meta_in.get("source") or "import")
    prof = make_profile(
        str(data.get("name") or "未命名档案"),
        voice=data.get("voice"),
        fx=data.get("fx"),
        perf=data.get("perf"),
        source=src if src in _VALID_SOURCES else "import",
        for_model=str(meta_in.get("for_model") or ""),
        score=meta_in.get("score"),
        profile_id=str(data.get("id")) if data.get("id") else None,
    )
    # keep an original creation stamp when present
    if meta_in.get("created"):
        prof["meta"]["created"] = str(meta_in["created"])
    return prof


def is_empty_profile(prof: dict) -> bool:
    """True when a profile sets no actual parameters (nothing to apply)."""
    return not (prof.get("voice") or prof.get("fx") or prof.get("perf"))


# --------------------------------------------------------------------------
# on-disk CRUD
# --------------------------------------------------------------------------
def profiles_dir(model_dir: str) -> str:
    return os.path.join(str(model_dir), PROFILES_DIRNAME)


def profile_path(model_dir: str, profile_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "", str(profile_id)) or "profile"
    return os.path.join(profiles_dir(model_dir), safe + PROFILE_EXT)


def save_profile(model_dir: str, profile: dict) -> str:
    prof = validate_profile(profile) or make_profile("未命名档案")
    path = profile_path(model_dir, prof["id"])
    _write_json_atomic(path, prof)
    return path


def load_profile(model_dir: str, profile_id: str) -> Optional[dict]:
    return validate_profile(_read_json_strict(profile_path(model_dir, profile_id)))


def list_profiles(model_dir: str) -> list[dict]:
    """All saved profiles for a model, validated, newest-created last."""
    d = profiles_dir(model_dir)
    out: list[dict] = []
    try:
        names = [n for n in os.listdir(d) if n.endswith(PROFILE_EXT)]
    except OSError:
        return out
    for n in names:
        prof = validate_profile(_read_json_strict(os.path.join(d, n)))
        if prof is not None:
            out.append(prof)
    out.sort(key=lambda p: (str(p.get("meta", {}).get("created") or ""), p.get("name", "")))
    return out


def delete_profile(model_dir: str, profile_id: str) -> bool:
    try:
        os.remove(profile_path(model_dir, profile_id))
    except OSError:
        return False
    # if it was active, revert to default
    if get_active_profile_id(model_dir) == str(profile_id):
        set_active_profile_id(model_dir, "")
    return True


def rename_profile(model_dir: str, profile_id: str, new_name: str) -> bool:
    prof = load_profile(model_dir, profile_id)
    if prof is None:
        return False
    prof["name"] = _safe_name(new_name)
    save_profile(model_dir, prof)
    return True


# --------------------------------------------------------------------------
# active-profile pointer (stored in the model's config.json, non-destructively)
# --------------------------------------------------------------------------
def _config_path(model_dir: str) -> str:
    return os.path.join(str(model_dir), _CONFIG_NAME)


def get_active_profile_id(model_dir: str) -> str:
    return str(_read_json(_config_path(model_dir)).get("active_profile") or "")


def set_active_profile_id(model_dir: str, profile_id: str) -> None:
    """Set/clear the active profile without clobbering other config.json keys."""
    path = _config_path(model_dir)
    cfg = _read_json(path)
    cfg["active_profile"] = str(profile_id or "")
    _write_json_atomic(path, cfg)


def resolve_active_profile(model_dir: str) -> Optional[dict]:
    """The active profile dict, or None when the model is on its default."""
    pid = get_active_profile_id(model_dir)
    if not pid:
        return None
    return load_profile(model_dir, pid)
