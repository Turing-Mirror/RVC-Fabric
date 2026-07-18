# -*- coding: utf-8 -*-
"""懒人环境检测与一键补齐（模型权重等）。"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass

from pathlib import Path

from launcher.paths import HUBERT, RMVPE, ROOT, WEIGHTS, ensure_dirs, find_python
from launcher.win_util import CREATE_NO_WINDOW


@dataclass
class CheckItem:
    name: str
    ok: bool
    detail: str


def check_environment(*, heavy: bool = False) -> list[CheckItem]:
    """File/path checks are cheap. Package import (torch) is optional/slow.

    heavy=False: safe for UI startup (no multi-second torch import freeze).
    """
    from launcher.paths import MODELS_DIR

    ensure_dirs()
    items = []
    py = find_python(False)
    py_ok = bool(py) and (py in ("python", "pythonw") or os.path.isfile(str(py)))
    items.append(CheckItem("Python", py_ok, str(py)))

    items.append(
        CheckItem(
            "Hubert 模型",
            HUBERT.is_file() and HUBERT.stat().st_size > 1_000_000,
            str(HUBERT),
        )
    )
    items.append(
        CheckItem(
            "RMVPE 模型",
            RMVPE.is_file() and RMVPE.stat().st_size > 1_000_000,
            str(RMVPE),
        )
    )
    n_legacy = len(list(WEIGHTS.glob("*.pth"))) if WEIGHTS.is_dir() else 0
    n_user = 0
    if MODELS_DIR.is_dir():
        n_user = sum(1 for _ in MODELS_DIR.glob("*/*.pth"))
    n = n_legacy + n_user
    items.append(
        CheckItem(
            "音色模型",
            n > 0,
            f"{n_user} 个于 User_Data/models, {n_legacy} 个于 assets/weights",
        )
    )

    # Detect site-packages without importing torch (fast)
    py_path = Path(py) if py and os.path.isfile(str(py)) else None
    site = None
    if py_path is not None:
        cand = py_path.parent / "Lib" / "site-packages"
        if cand.is_dir():
            site = cand
    for folder, label in (
        ("torch", "PyTorch"),
        ("gradio", "Gradio"),
        ("_sounddevice_data", "SoundDevice"),
        ("faiss", "Faiss"),
    ):
        ok = bool(site and (site / folder).exists())
        items.append(
            CheckItem(label, ok, "Runtime 已含" if ok else "Runtime 中未找到")
        )

    if heavy:
        for mod, label in (
            ("torch", "PyTorch-import"),
            ("gradio", "Gradio-import"),
        ):
            try:
                __import__(mod)
                items.append(CheckItem(label, True, "import ok"))
            except Exception as e:
                items.append(CheckItem(label, False, str(e)[:80]))

    return items


def download_pretrained(log_cb=None) -> tuple[bool, str]:
    """调用 tools/download_models.py。"""
    py = find_python(False)
    script = ROOT / "tools" / "download_models.py"
    if not script.is_file():
        return False, "缺少 tools/download_models.py"

    def log(msg: str) -> None:
        if log_cb:
            log_cb(msg)

    log("开始下载预训练模型…")
    try:
        kw = {
            "cwd": str(ROOT),
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if sys.platform == "win32":
            kw["creationflags"] = CREATE_NO_WINDOW
        p = subprocess.run([py, str(script)], **kw)
        out = (p.stdout or "") + (p.stderr or "")
        if out:
            log(out[-1500:])
        if p.returncode == 0:
            return True, "预训练模型已就绪（或已跳过已存在文件）。"
        return False, f"下载结束码 {p.returncode}，请检查网络。"
    except Exception as e:
        return False, str(e)
