# -*- coding: utf-8 -*-
"""虚拟声卡（VB-Cable）安装辅助。

VB-Cable 安装程序必须：
  1. 从**已解压**的完整目录运行（不能从 zip 预览窗口内直接双击）
  2. 工作目录 = VBCABLE 文件夹（同目录需有 .inf / .sys / .cat）
  3. 以管理员权限启动（UAC 提示）

官方 VB-Audio Virtual Cable 为捐赠软件；本目录仅做安装启动与引导。
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from launcher.paths import ROOT, VBCABLE_DIR, ensure_dirs
from launcher.win_util import CREATE_NO_WINDOW, open_path

VB_CABLE_URL = "https://vb-audio.com/Cable/"
SETUP_NAMES = (
    "VBCABLE_Setup_x64.exe",
    "VBCABLE_Setup.exe",
    "VBCable_Setup_x64.exe",
)
_DRIVER_GLOBS = ("*.inf", "*.sys", "*.cat")


def find_setup() -> Path | None:
    ensure_dirs()
    for name in SETUP_NAMES:
        p = VBCABLE_DIR / name
        if p.is_file() and p.stat().st_size > 50_000:
            return p
    for p in sorted(VBCABLE_DIR.glob("*.exe")):
        n = p.name.lower()
        if "control" in n or "panel" in n:
            continue
        if "setup" in n and p.stat().st_size > 50_000:
            return p
    return None


def _has_driver_files(folder: Path) -> bool:
    for pat in _DRIVER_GLOBS:
        if any(folder.glob(pat)):
            return True
    return False


def _looks_like_zip_or_temp_path(path: Path) -> bool:
    """True only for clear zip-preview / system temp extract paths.

    Do **not** treat ``%LocalAppData%\\RVC Fabric`` as temp (Inno default install).
    """
    s = str(path).replace("/", "\\").lower()
    # Explicit fragile locations only
    markers = (
        "\\appdata\\local\\temp\\",
        "\\appdata\\local\\tmp\\",
        "\\windows\\temp\\",
        "\\windows\\tmp\\",
        ".zip\\",
        ".zip/",
        "\\inetcache\\",
        "\\temporary internet files\\",
        "\\iNetCache\\".lower(),
        "\\_mei",  # pyinstaller onefile extract (should not be ROOT)
    )
    return any(m in s for m in markers)


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _run_elevated(setup: Path) -> None:
    """Start installer with UAC + working directory = VBCABLE (required for INF/SYS)."""
    setup = setup.resolve()
    work = str(setup.parent)
    if sys.platform != "win32":
        subprocess.Popen([str(setup)], cwd=work)
        return

    # PowerShell Start-Process -Verb RunAs is the most reliable elevated launch
    # (ShellExecuteW often fails silently or leaves UAC behind other windows).
    ps = (
        "Start-Process -FilePath {fp} -WorkingDirectory {wd} -Verb RunAs"
    ).format(fp=_ps_quote(str(setup)), wd=_ps_quote(work))
    kw: dict = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if sys.platform == "win32":
        kw["creationflags"] = CREATE_NO_WINDOW
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps,
        ],
        **kw,
    )
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip() or f"exit={r.returncode}"
        # Fallback 1: ShellExecute runas
        try:
            import ctypes

            rc = int(
                ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    str(setup),
                    None,
                    work,
                    1,  # SW_SHOWNORMAL
                )
            )
            if rc > 32:
                return
            err = f"{err}; ShellExecute={rc}"
        except Exception as e2:
            err = f"{err}; ShellExecute: {e2}"
        # Fallback 2: plain start with cwd (user may need to approve later)
        try:
            subprocess.Popen(
                [str(setup)],
                cwd=work,
                shell=False,
            )
            return
        except Exception as e3:
            raise OSError(f"无法启动安装程序：{err}; Popen: {e3}") from e3


def install_vbcable() -> tuple[bool, str]:
    """启动 VB-Cable 安装 UI（UAC + 安装窗口）。"""
    ensure_dirs()
    setup = find_setup()

    if setup is None:
        readme = VBCABLE_DIR / "请先准备VB-Cable安装包.txt"
        if not readme.is_file():
            readme.write_text(
                "请确认本文件夹内有：\n"
                "  VBCABLE_Setup_x64.exe\n"
                "  以及 .inf / .sys / .cat 驱动文件\n\n"
                f"官网：{VB_CABLE_URL}\n"
                "请先把软件完整安装/解压到硬盘，不要从压缩包窗口直接运行。\n",
                encoding="utf-8",
            )
        open_path(VBCABLE_DIR)
        webbrowser.open(VB_CABLE_URL)
        return (
            False,
            "未找到安装程序。\n"
            "请确认安装目录下 VBCABLE 文件夹内有 Setup 与驱动文件。\n"
            "已打开该文件夹与官网。",
        )

    if _looks_like_zip_or_temp_path(ROOT) or _looks_like_zip_or_temp_path(setup):
        open_path(VBCABLE_DIR)
        return (
            False,
            "当前程序像是在临时目录/压缩包内运行。\n"
            "虚拟声卡必须从已解压（或 Inno 安装）的完整目录启动。\n\n"
            f"当前路径：\n{ROOT}\n\n"
            "请先完整安装/解压软件，再点「安装虚拟声卡」。",
        )

    if not _has_driver_files(VBCABLE_DIR):
        open_path(VBCABLE_DIR)
        return (
            False,
            "VBCABLE 目录缺少驱动文件（.inf / .sys / .cat）。\n"
            "请使用完整 Setup 安装包（会带上全部驱动）。\n\n"
            f"目录：{VBCABLE_DIR}",
        )

    try:
        _run_elevated(setup)
        return (
            True,
            f"已启动安装程序：{setup.name}\n\n"
            "接下来请：\n"
            "1. 若弹出 UAC（用户账户控制），点「是」\n"
            "2. 在 VB-Cable 安装窗口中点 Install / 安装\n"
            "3. 完成后在 Windows「声音」设置中应能看到 CABLE\n\n"
            "若没看到窗口：请看任务栏是否闪烁，或 Alt+Tab 切换窗口。",
        )
    except Exception as e:
        open_path(VBCABLE_DIR)
        return (
            False,
            f"自动启动失败：{e}\n\n"
            f"请在打开的文件夹中右键「{setup.name}」\n"
            "→「以管理员身份运行」。",
        )
