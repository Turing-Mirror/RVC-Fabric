# -*- coding: utf-8 -*-
"""Release package identity (official-style multi-pack: Nvidia / AMD / …).

Official RVC is NOT “one Runtime + flip a flag”. Windows A/I support is:

1. A **different environment** (requirements-dml / AMD_Intel 7z Runtime)
   - torch + **torch-directml**
   - **onnxruntime-directml** (and rmvpe.onnx for pitch on DML)
2. Launch with **--dml** so Config uses torch_directml.device() and swaps ORT

``package_meta.json`` at package root records which full pack this is, so the
app defaults to the correct backend and UI can tell users which download they have.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from launcher.paths import ROOT

META_NAME = "package_meta.json"

# Known shipping variants (build_release --variant)
VARIANT_DEFAULTS: dict[str, dict[str, Any]] = {
    "nvidia": {
        "variant": "nvidia",
        "label": "NVIDIA CUDA",
        "accel_default": "cuda",
        "use_dml": False,
        "summary": "官方 N 卡路径：CUDA 版 Runtime + 默认启动（非 --dml）",
    },
    "amd": {
        "variant": "amd",
        "label": "AMD/Intel DirectML",
        "accel_default": "dml",
        "use_dml": True,
        "summary": "官方 A/I 卡路径：DirectML Runtime + 启动走 --dml / torch_directml",
    },
    "nvidia50": {
        "variant": "nvidia50",
        "label": "NVIDIA 50 系 CUDA",
        "accel_default": "cuda",
        "use_dml": False,
        "summary": "RVCMAX 等对 50 系适配的 CUDA Runtime（与旧 N 卡包可能不同 CUDA/torch）",
    },
}


def meta_path(root: Path | None = None) -> Path:
    return (root or ROOT) / META_NAME


def load_package_meta(root: Path | None = None) -> dict[str, Any]:
    p = meta_path(root)
    if not p.is_file():
        # Dev tree / untagged pack → treat as nvidia-oriented dual-capable Runtime
        return dict(VARIANT_DEFAULTS["nvidia"], tagged=False)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(VARIANT_DEFAULTS["nvidia"], tagged=False)
        var = str(data.get("variant") or "nvidia").lower()
        base = dict(VARIANT_DEFAULTS.get(var, VARIANT_DEFAULTS["nvidia"]))
        base.update(data)
        base["tagged"] = True
        return base
    except Exception:
        return dict(VARIANT_DEFAULTS["nvidia"], tagged=False)


def write_package_meta(root: Path, variant: str, **extra: Any) -> Path:
    var = str(variant or "nvidia").lower()
    data = dict(VARIANT_DEFAULTS.get(var, VARIANT_DEFAULTS["nvidia"]))
    data["variant"] = var
    data.update(extra)
    data["tagged"] = True
    path = root / META_NAME
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def default_accel_for_package(root: Path | None = None) -> str:
    meta = load_package_meta(root)
    return str(meta.get("accel_default") or "auto")
