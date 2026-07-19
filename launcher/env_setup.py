# -*- coding: utf-8 -*-
"""环境检测与可选下载。

分层（对齐大众用户 vs 训练/WebUI 进阶）：

- **core**：日常实时变声必需（Python / Hubert / RMVPE / torch / 声卡库）
- **soft**：建议有、但可后补（音色模型、rmvpe.onnx）
- **training**：仅训练 / 翻唱 WebUI / 伴奏分离需要（预训练底模、UVR、Gradio、Faiss）

状态栏「环境正常」只看 **core**。训练相关缺失不自动下载，由用户确认后再下。
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from launcher.paths import HUBERT, RMVPE, ROOT, WEIGHTS, ensure_dirs, find_python
from launcher.win_util import CREATE_NO_WINDOW

# core | soft | training
KIND_CORE = "core"
KIND_SOFT = "soft"
KIND_TRAINING = "training"


@dataclass
class CheckItem:
    name: str
    ok: bool
    detail: str
    kind: str = KIND_CORE  # core | soft | training
    note: str = ""


def check_environment(*, heavy: bool = False) -> list[CheckItem]:
    """File/path checks are cheap. Package import (torch) is optional/slow.

    heavy=False: safe for UI startup (no multi-second torch import freeze).
    """
    from launcher.paths import MODELS_DIR

    ensure_dirs()
    items: list[CheckItem] = []
    py = find_python(False)
    py_ok = bool(py) and (py in ("python", "pythonw") or os.path.isfile(str(py)))
    items.append(
        CheckItem(
            "Python / Runtime",
            py_ok,
            str(py),
            KIND_CORE,
            "日常变声与启动必需",
        )
    )

    items.append(
        CheckItem(
            "Hubert 模型",
            HUBERT.is_file() and HUBERT.stat().st_size > 1_000_000,
            str(HUBERT),
            KIND_CORE,
            "实时变声推理必需",
        )
    )
    items.append(
        CheckItem(
            "RMVPE 模型",
            RMVPE.is_file() and RMVPE.stat().st_size > 1_000_000,
            str(RMVPE),
            KIND_CORE,
            "实时变声音高提取",
        )
    )
    rmvpe_onnx = ROOT / "assets" / "rmvpe" / "rmvpe.onnx"
    items.append(
        CheckItem(
            "RMVPE.onnx",
            rmvpe_onnx.is_file() and rmvpe_onnx.stat().st_size > 100_000,
            str(rmvpe_onnx),
            KIND_SOFT,
            "A 卡 DirectML 音高推荐；N 卡可用 .pt",
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
            KIND_SOFT,
            "可在主界面导入；空目录不影响「环境就绪」",
        )
    )

    # Detect site-packages without importing torch (fast)
    py_path = Path(py) if py and os.path.isfile(str(py)) else None
    site = None
    if py_path is not None:
        cand = py_path.parent / "Lib" / "site-packages"
        if cand.is_dir():
            site = cand
    for folder, label, kind, note in (
        ("torch", "PyTorch", KIND_CORE, "推理引擎"),
        ("_sounddevice_data", "SoundDevice", KIND_CORE, "实时音频输入输出"),
        ("gradio", "Gradio", KIND_TRAINING, "训练/翻唱 WebUI 用，日常变声不需要"),
        ("faiss", "Faiss", KIND_TRAINING, "特征索引/训练相关；无 index 也可变声"),
    ):
        ok = bool(site and (site / folder).exists())
        items.append(
            CheckItem(
                label,
                ok,
                "Runtime 已含" if ok else "Runtime 中未找到",
                kind,
                note,
            )
        )

    # Training bottom models (sample key files)
    pre_v2 = ROOT / "assets" / "pretrained_v2" / "f0G40k.pth"
    pre_v1 = ROOT / "assets" / "pretrained" / "f0G40k.pth"
    n_pre = 0
    for d in (ROOT / "assets" / "pretrained", ROOT / "assets" / "pretrained_v2"):
        if d.is_dir():
            n_pre += sum(1 for p in d.glob("*.pth") if p.stat().st_size > 1_000_000)
    items.append(
        CheckItem(
            "训练底模 (pretrained)",
            (pre_v2.is_file() or pre_v1.is_file()) and n_pre >= 1,
            f"已发现约 {n_pre} 个 .pth",
            KIND_TRAINING,
            "仅「训练自己的音色」需要；日常用别人 .pth 变声不需要",
        )
    )

    uvr_dir = ROOT / "assets" / "uvr5_weights"
    n_uvr = 0
    if uvr_dir.is_dir():
        n_uvr = sum(
            1
            for p in uvr_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in (".pth", ".onnx") and p.stat().st_size > 100_000
        )
    items.append(
        CheckItem(
            "伴奏分离 UVR",
            n_uvr >= 1,
            f"已发现 {n_uvr} 个分离权重",
            KIND_TRAINING,
            "仅 WebUI 人声/伴奏分离需要",
        )
    )

    if heavy:
        for mod, label, kind in (
            ("torch", "PyTorch-import", KIND_CORE),
            ("gradio", "Gradio-import", KIND_TRAINING),
        ):
            try:
                __import__(mod)
                items.append(CheckItem(label, True, "import ok", kind, ""))
            except Exception as e:
                items.append(CheckItem(label, False, str(e)[:80], kind, ""))

    return items


def missing_items(
    items: Optional[Iterable[CheckItem]] = None,
    *,
    kinds: Optional[set[str]] = None,
) -> list[CheckItem]:
    items = list(items if items is not None else check_environment())
    out = [i for i in items if not i.ok]
    if kinds is not None:
        out = [i for i in out if i.kind in kinds]
    return out


def core_ready(items: Optional[Iterable[CheckItem]] = None) -> bool:
    return not missing_items(items, kinds={KIND_CORE})


def format_check_report(items: Optional[Iterable[CheckItem]] = None) -> str:
    items = list(items if items is not None else check_environment())
    sections = [
        (KIND_CORE, "【日常变声 · 必需】"),
        (KIND_SOFT, "【建议 · 可后补】"),
        (KIND_TRAINING, "【训练 / WebUI · 可选】"),
    ]
    lines: list[str] = []
    for kind, title in sections:
        group = [i for i in items if i.kind == kind]
        if not group:
            continue
        lines.append(title)
        for i in group:
            mark = "OK" if i.ok else "缺"
            note = f" — {i.note}" if i.note else ""
            lines.append(f"  [{mark}] {i.name}: {i.detail}{note}")
        lines.append("")
    if core_ready(items):
        lines.append("结论：日常变声环境已就绪。")
    else:
        miss = "、".join(i.name for i in missing_items(items, kinds={KIND_CORE}))
        lines.append(f"结论：日常变声还缺：{miss}")
    train_miss = missing_items(items, kinds={KIND_TRAINING})
    if train_miss:
        lines.append(
            "训练/分离相关缺失不影响开黑变声；需要时再选下载（体积较大）。"
        )
    return "\n".join(lines).strip()


def download_pretrained(
    log_cb=None,
    *,
    scope: str = "core",
) -> tuple[bool, str]:
    """调用 tools/download_models.py。

    scope:
      - core: hubert + rmvpe（日常变声）
      - training: 训练底模 pretrained / v2
      - uvr: 伴奏分离
      - all: 全部（旧行为）
    """
    py = find_python(False)
    script = ROOT / "tools" / "download_models.py"
    if not script.is_file():
        return False, "缺少 tools/download_models.py"

    scope = (scope or "core").strip().lower()
    if scope not in ("core", "training", "uvr", "all"):
        scope = "core"

    def log(msg: str) -> None:
        if log_cb:
            log_cb(msg)

    labels = {
        "core": "日常变声必需（Hubert / RMVPE）",
        "training": "训练底模（体积大，日常不需要）",
        "uvr": "伴奏分离 UVR",
        "all": "全部预训练与分离资源",
    }
    log(f"开始下载：{labels.get(scope, scope)}…")
    try:
        kw: dict = {
            "cwd": str(ROOT),
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if sys.platform == "win32":
            kw["creationflags"] = CREATE_NO_WINDOW
        p = subprocess.run([str(py), str(script), "--scope", scope], **kw)
        out = (p.stdout or "") + (p.stderr or "")
        if out:
            log(out[-1500:])
        if p.returncode == 0:
            return True, f"下载完成（{labels.get(scope, scope)}；已存在的会跳过）。"
        return False, f"下载结束码 {p.returncode}，请检查网络。"
    except Exception as e:
        return False, str(e)
