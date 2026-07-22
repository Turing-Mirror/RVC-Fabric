# -*- coding: utf-8 -*-
"""Thin shell copy helpers (tests / emergency portable). Not the product installer."""

from __future__ import annotations

import shutil
from pathlib import Path

_SHELL_DIRS = (
    "launcher",
    "configs",
    "i18n",
    "infer",
    "tools",
    "docs",
    "assets",
)
_SHELL_FILES = (
    "gui_v1.py",
    "infer-web.py",
    "LICENSE",
    "README.md",
    ".env",
    "OpenApp.vbs",
    "OpenSetup.vbs",
    "package_meta.json",
)
_SHELL_EXES = (
    "启动器.exe",
    "变声器.exe",
    "TM_Setup.exe",
    "TM_Voice.exe",
    "RVC Fabric.exe",
)


def _is_shell_tree(path: Path) -> bool:
    return (path / "launcher").is_dir() and (
        (path / "gui_v1.py").is_file()
        or (path / "变声器.exe").is_file()
        or (path / "TM_Voice.exe").is_file()
    )


def _ignore_copy(directory: str, names: list[str]) -> set[str]:
    skip = {
        "__pycache__",
        ".git",
        ".pytest_cache",
        "RVCMAX",
        "dist",
        "build",
        "TEMP",
        "TEMP_BUILD",
        "CNB-GIT-RELEASE",
        "Runtime",
        "runtime",
        "_local",
    }
    out = {n for n in names if n in skip or n.endswith(".pyc")}
    dlow = directory.replace("\\", "/").lower()
    if dlow.endswith("/assets/hubert") or dlow.endswith("/assets/rmvpe"):
        for n in names:
            if n.endswith((".pt", ".onnx", ".pth")) and n not in out:
                try:
                    p = Path(directory) / n
                    if p.is_file() and p.stat().st_size > 5_000_000:
                        out.add(n)
                except OSError:
                    pass
    return out


def copy_shell_tree(src: Path, dst: Path, *, log=None) -> None:
    """Copy thin product shell src → dst (no Runtime)."""
    if src.resolve() == dst.resolve():
        if log:
            log("安装目录即当前目录，跳过复制。")
        return
    dst.mkdir(parents=True, exist_ok=True)
    for name in _SHELL_DIRS:
        s = src / name
        if not s.is_dir():
            continue
        d = dst / name
        if log:
            log(f"复制 {name}/ …")
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(s, d, ignore=_ignore_copy)
    for name in _SHELL_FILES:
        s = src / name
        if s.is_file():
            shutil.copy2(s, dst / name)
    for name in _SHELL_EXES:
        s = src / name
        if s.is_file():
            shutil.copy2(s, dst / name)
    for rel in (
        "User_Data/models",
        "User_Data/logs",
        "User_Data/indices",
        "User_Data/shared_profiles",
        "VBCABLE",
    ):
        (dst / rel).mkdir(parents=True, exist_ok=True)
    vb = src / "VBCABLE"
    if vb.is_dir():
        for f in vb.iterdir():
            if f.is_file() and f.suffix.lower() in (".exe", ".txt", ".md"):
                shutil.copy2(f, dst / "VBCABLE" / f.name)
