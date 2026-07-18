# -*- coding: utf-8 -*-
"""虚拟声卡（VB-Cable）安装辅助。

官方 VB-Audio Virtual Cable 为捐赠软件；本目录仅做下载引导与安装启动，
不捆绑破解。用户也可自行放入 Setup 程序到 VBCABLE 文件夹。
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from launcher.paths import VBCABLE_DIR, ensure_dirs
from launcher.win_util import open_path

# VB-Audio 官方下载页（用户从官网获取合法安装包）
VB_CABLE_URL = "https://vb-audio.com/Cable/"
# 常见文件名
SETUP_NAMES = (
    "VBCABLE_Setup_x64.exe",
    "VBCABLE_Setup.exe",
    "VBCable_Setup_x64.exe",
    "setup.exe",
)


def find_setup() -> Path | None:
    ensure_dirs()
    for name in SETUP_NAMES:
        p = VBCABLE_DIR / name
        if p.is_file():
            return p
    # 任意 exe
    for p in VBCABLE_DIR.glob("*.exe"):
        return p
    return None


def install_vbcable() -> tuple[bool, str]:
    """尝试启动安装程序；没有则打开官网并打开文件夹。"""
    ensure_dirs()
    setup = find_setup()
    if setup:
        try:
            if sys.platform == "win32":
                # 需要管理员时由 UAC 提示
                os.startfile(str(setup))  # type: ignore[attr-defined]
            else:
                subprocess.Popen([str(setup)])
            return True, f"已启动安装程序：{setup.name}\n请在弹出的窗口点击 Install。"
        except Exception as e:
            return False, f"无法启动安装程序：{e}"
    # 写说明 + 打开官网
    readme = VBCABLE_DIR / "请先下载VB-Cable安装包.txt"
    if not readme.is_file():
        readme.write_text(
            "请从官网下载 VB-Audio Virtual Cable：\n"
            f"{VB_CABLE_URL}\n\n"
            "下载后把 VBCABLE_Setup_x64.exe 放到本文件夹，\n"
            "再回到启动器点击「安装虚拟声卡」。\n",
            encoding="utf-8",
        )
    open_path(VBCABLE_DIR)
    webbrowser.open(VB_CABLE_URL)
    return (
        False,
        "未找到安装包。已打开 VBCABLE 文件夹与官网，\n"
        "请下载后把 Setup 放进 VBCABLE 再点一次安装。",
    )
