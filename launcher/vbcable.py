# -*- coding: utf-8 -*-
"""虚拟声卡（VB-Cable）安装辅助。

VB-Cable 安装程序必须：
  1. 从**已解压**的完整目录运行（不能从 zip 预览/压缩包内直接双击）
  2. 工作目录 = VBCABLE 文件夹（同目录需有 .inf / .sys / .cat）
  3. 以管理员权限启动（UAC）

官方 VB-Audio Virtual Cable 为捐赠软件；本目录仅做安装启动与引导。
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from launcher.paths import ROOT, VBCABLE_DIR, ensure_dirs
from launcher.win_util import open_path

# VB-Audio 官方下载页
VB_CABLE_URL = "https://vb-audio.com/Cable/"
SETUP_NAMES = (
    "VBCABLE_Setup_x64.exe",
    "VBCABLE_Setup.exe",
    "VBCable_Setup_x64.exe",
    "setup.exe",
)
# 驱动配套文件（安装包解压后应与 Setup 同目录）
_DRIVER_GLOBS = ("*.inf", "*.sys", "*.cat")


def find_setup() -> Path | None:
    ensure_dirs()
    for name in SETUP_NAMES:
        p = VBCABLE_DIR / name
        if p.is_file() and p.stat().st_size > 50_000:
            return p
    for p in VBCABLE_DIR.glob("*.exe"):
        # 控制面板不是安装器
        if "control" in p.name.lower() or "panel" in p.name.lower():
            continue
        if p.stat().st_size > 50_000:
            return p
    return None


def _has_driver_files(folder: Path) -> bool:
    for pat in _DRIVER_GLOBS:
        if any(folder.glob(pat)):
            return True
    return False


def _looks_like_zip_or_temp_path(path: Path) -> bool:
    """True if install is running from a zip preview / temp extract (fragile)."""
    s = str(path).replace("/", "\\").lower()
    bad = (
        "\\appdata\\local\\temp\\",
        "\\temp\\",
        "\\tmp\\",
        ".zip\\",
        ".zip/",
        "\\iNetCache\\",
        "\\temporary internet files\\",
        "\\windows\\inetcache\\",
    )
    return any(b in s for b in bad)


def _run_elevated(setup: Path) -> None:
    """Start installer with UAC elevation and working dir = VBCABLE folder."""
    setup = setup.resolve()
    work = str(setup.parent)
    if sys.platform != "win32":
        subprocess.Popen([str(setup)], cwd=work)
        return
    # ShellExecute "runas" → UAC; lpDirectory = work so INF/SYS resolve
    try:
        import ctypes

        # SW_SHOWNORMAL = 1
        rc = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            str(setup),
            None,
            work,
            1,
        )
        # >32 means success for ShellExecute
        if rc <= 32:
            raise OSError(f"ShellExecute failed code={rc}")
    except Exception:
        # Fallback: startfile (may lack admin / wrong cwd on some systems)
        os.startfile(str(setup))  # type: ignore[attr-defined]


def install_vbcable() -> tuple[bool, str]:
    """尝试以管理员 + 正确工作目录启动 VB-Cable 安装程序。"""
    ensure_dirs()
    setup = find_setup()

    # 未解压到本地完整目录
    if setup is None:
        readme = VBCABLE_DIR / "请先下载VB-Cable安装包.txt"
        if not readme.is_file():
            readme.write_text(
                "请将完整 VB-Cable 安装包解压到本文件夹（含 Setup 与 .inf/.sys）。\n"
                f"官网：{VB_CABLE_URL}\n\n"
                "不要从压缩包窗口里直接双击安装，请先解压到磁盘。\n"
                "再回到启动器点击「安装虚拟声卡」。\n",
                encoding="utf-8",
            )
        open_path(VBCABLE_DIR)
        webbrowser.open(VB_CABLE_URL)
        return (
            False,
            "未找到安装程序。\n"
            "请先把软件完整解压到硬盘，确认 VBCABLE 文件夹内有\n"
            "VBCABLE_Setup_x64.exe 以及 .inf / .sys 驱动文件。\n"
            "已打开 VBCABLE 目录与官网。",
        )

    root_s = str(ROOT.resolve()).lower()
    if _looks_like_zip_or_temp_path(ROOT) or _looks_like_zip_or_temp_path(setup):
        open_path(VBCABLE_DIR)
        return (
            False,
            "当前像是从压缩包/临时目录运行。\n"
            "虚拟声卡安装程序必须从已解压的完整文件夹启动，\n"
            "且与 .inf / .sys 驱动在同一目录。\n\n"
            "请：\n"
            "1. 将整个软件解压到英文路径（如 D:\\RVC-Fabric）\n"
            "2. 再打开解压后的启动器 →「安装虚拟声卡」\n\n"
            f"当前路径：\n{ROOT}",
        )

    if not _has_driver_files(VBCABLE_DIR):
        open_path(VBCABLE_DIR)
        return (
            False,
            "VBCABLE 文件夹里只有安装器 exe，缺少驱动文件（.inf / .sys / .cat）。\n"
            "请使用完整安装包（Setup 打包时会带上全部驱动），\n"
            "或从官网下载后整包解压到 VBCABLE 再试。\n\n"
            f"目录：{VBCABLE_DIR}",
        )

    try:
        _run_elevated(setup)
        return (
            True,
            f"已请求管理员权限启动：{setup.name}\n"
            "请在 UAC 点「是」，再在安装窗口点 Install。\n"
            "安装完成后可在 Windows 声音设置中看到 CABLE Input / Output。",
        )
    except Exception as e:
        return False, f"无法启动安装程序：{e}\n请右键 {setup.name} → 以管理员身份运行。"
