# -*- coding: utf-8 -*-
"""虚拟声卡（VB-Cable）安装辅助。

安装包**不内置**在 Setup 里：Runtime 就绪后从 CNB LFS 下载 zip，
解压到 ``VBCABLE/``，再以管理员身份启动官方 Setup。

VB-Cable 安装程序必须：
  1. 从**已解压**的完整目录运行（不能从 zip 预览窗口内直接双击）
  2. 工作目录 = VBCABLE 文件夹（同目录需有 .inf / .sys / .cat）
  3. 以管理员权限启动（UAC 提示）

官方 VB-Audio Virtual Cable 为捐赠软件；本模块仅做下载与启动引导。
"""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Callable, Optional

from launcher.paths import ROOT, USER_DATA, VBCABLE_DIR, ensure_dirs
from launcher.win_util import open_path

VB_CABLE_URL = "https://vb-audio.com/Cable/"
SETUP_NAMES = (
    "VBCABLE_Setup_x64.exe",
    "VBCABLE_Setup.exe",
    "VBCable_Setup_x64.exe",
)
_DRIVER_GLOBS = ("*.inf", "*.sys", "*.cat")

ProgressCb = Callable[[int, int], None]
LogCb = Callable[[str], None]


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


def vbcable_pack_ready() -> bool:
    """本地是否已有可启动的完整安装包（Setup + 驱动）。"""
    return find_setup() is not None and _has_driver_files(VBCABLE_DIR)


def _looks_like_zip_or_temp_path(path: Path) -> bool:
    """True only for clear zip-preview / system temp extract paths.

    Do **not** treat ``%LocalAppData%\\RVC Fabric`` as temp (Inno default install).
    """
    s = str(path).replace("/", "\\").lower()
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
        "\\_mei",
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

    errors: list[str] = []

    # ShellExecuteW return: >32 success; SE_ERR_ACCESSDENIED=5 often = UAC cancel
    SE_ERR_ACCESSDENIED = 5
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
        errors.append(f"ShellExecute={rc}")
        if rc == SE_ERR_ACCESSDENIED:
            # User declined UAC — do NOT fall back to unelevated install (review #34)
            raise PermissionError("需要管理员权限安装 VB-Cable（已取消 UAC）")
    except PermissionError:
        raise
    except Exception as e:
        errors.append(f"ShellExecute: {e}")

    ps = (
        "Start-Process -FilePath {fp} -WorkingDirectory {wd} -Verb RunAs"
    ).format(fp=_ps_quote(str(setup)), wd=_ps_quote(work))
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-Command",
                ps,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode == 0:
            return
        err = (r.stderr or r.stdout or "").strip() or f"exit={r.returncode}"
        errors.append(f"PowerShell: {err}")
        # 1223 = ERROR_CANCELLED (user declined elevation)
        if r.returncode in (1223, 5) or "canceled" in err.lower() or "cancelled" in err.lower():
            raise PermissionError("需要管理员权限安装 VB-Cable（已取消 UAC）")
    except PermissionError:
        raise
    except Exception as e:
        errors.append(f"PowerShell: {e}")

    # Do not launch Setup unelevated after UAC denial — that used to report success
    # while the driver never installed (review #34).
    raise OSError(
        "无法以管理员身份启动 VB-Cable 安装程序（需要管理员权限）。"
        + ((" 详情：" + "; ".join(errors)) if errors else "")
    )


def _log(cb: Optional[LogCb], msg: str) -> None:
    if cb:
        try:
            cb(msg)
        except Exception:
            pass


def ensure_vbcable_pack(
    *,
    force: bool = False,
    progress: Optional[ProgressCb] = None,
    log: Optional[LogCb] = None,
) -> tuple[bool, str]:
    """从 CNB 下载并解压 VB-Cable 安装包到 ``VBCABLE/``（不启动安装器）。

    在 Runtime 补全之后调用；也可在用户点「安装虚拟声卡」时按需触发。
    """
    ensure_dirs()
    if vbcable_pack_ready() and not force:
        return True, "本地已有 VB-Cable 安装包"

    try:
        from launcher.cnb_sources import resolve_vbcable_spec
        from launcher.online.downloader import download_file
        from launcher.online.safe_zip import safe_extract_zip
    except Exception as e:
        return False, f"无法加载下载模块：{e}"

    try:
        spec = resolve_vbcable_spec(prefer_remote=True)
    except Exception as e:
        return False, f"无法解析 VB-Cable 下载地址：{e}"

    if not spec.urls or not spec.sha256:
        return False, "CNB 清单中缺少 VB-Cable 下载信息"

    cache = USER_DATA / "update_cache" / "vbcable"
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / (spec.name or "vbcable-setup.zip")

    size_hint = (
        f"约 {spec.size_bytes // 1024} KB"
        if spec.size_bytes
        else "约 1–2 MB"
    )
    _log(log, f"下载虚拟声卡安装包…（{size_hint}）")
    last_err: Exception | None = None
    ok_dl = False
    for i, url in enumerate(spec.urls):
        try:
            _log(log, f"下载 ({i + 1}/{len(spec.urls)})：{url[:96]}")
            # progress may be (done,total) or (phase,done,total)
            def _prog(done: int, total: int) -> None:
                if not progress:
                    return
                try:
                    progress(done, total)  # type: ignore[misc]
                except TypeError:
                    try:
                        progress("download", done, total)  # type: ignore[misc]
                    except Exception:
                        pass

            download_file(
                url,
                dest,
                progress=_prog if progress else None,
                retries=3,
                timeout=600,
                expected_sha256=spec.sha256,
                resume=True,
            )
            ok_dl = True
            break
        except Exception as e:
            last_err = e
            _log(log, f"  失败：{e}")
            # Keep .part for resume; only drop broken final dest
            try:
                if dest.is_file() and dest.stat().st_size < 1000:
                    dest.unlink()
            except OSError:
                pass
    if not ok_dl:
        return False, f"下载 VB-Cable 失败：{last_err}"

    _log(log, "解压到 VBCABLE 目录…")
    try:
        VBCABLE_DIR.mkdir(parents=True, exist_ok=True)
        # Clear old driver/setup fragments (keep any user notes)
        for pat in ("*.exe", "*.inf", "*.sys", "*.cat", "*.ico"):
            for p in VBCABLE_DIR.glob(pat):
                try:
                    p.unlink()
                except OSError:
                    pass
        written = safe_extract_zip(dest, VBCABLE_DIR)
        # If zip had a single top-level VBCABLE/ folder, hoist contents
        nested = VBCABLE_DIR / "VBCABLE"
        if nested.is_dir() and not find_setup():
            for child in nested.iterdir():
                target = VBCABLE_DIR / child.name
                if child.is_file():
                    if target.exists():
                        try:
                            target.unlink()
                        except OSError:
                            pass
                    child.replace(target)
                elif child.is_dir():
                    # rare
                    pass
            try:
                nested.rmdir()
            except OSError:
                pass
        _log(log, f"已解压 {len(written)} 个文件")
    except Exception as e:
        return False, f"解压 VB-Cable 失败：{e}"

    if not vbcable_pack_ready():
        return (
            False,
            "下载完成但未找到 Setup 或驱动文件。\n"
            f"请检查目录：{VBCABLE_DIR}",
        )

    note = VBCABLE_DIR / "来自CNB下载说明.txt"
    try:
        note.write_text(
            "本目录由启动器从 CNB 下载解压（vbcable-setup.zip）。\n"
            "点启动器「安装虚拟声卡」会以管理员身份运行 Setup。\n"
            f"官网：{VB_CABLE_URL}\n",
            encoding="utf-8",
        )
    except OSError:
        pass

    return True, f"已下载 VB-Cable 安装包到\n{VBCABLE_DIR}"


def install_vbcable(
    *,
    download_if_missing: bool = True,
    log: Optional[LogCb] = None,
) -> tuple[bool, str]:
    """确保本地有安装包后启动 VB-Cable 安装 UI（UAC + 安装窗口）。"""
    ensure_dirs()

    if not vbcable_pack_ready() and download_if_missing:
        ok, msg = ensure_vbcable_pack(log=log)
        if not ok:
            open_path(VBCABLE_DIR)
            webbrowser.open(VB_CABLE_URL)
            return False, msg + "\n\n已打开 VBCABLE 目录与官网，可手动放置安装包。"

    setup = find_setup()
    if setup is None:
        readme = VBCABLE_DIR / "请先准备VB-Cable安装包.txt"
        if not readme.is_file():
            readme.write_text(
                "请先在启动器完成「补全运行环境」（会顺带下载虚拟声卡包），\n"
                "或手动把完整 VB-Cable 解压到本文件夹（含 Setup 与 .inf/.sys）。\n\n"
                f"官网：{VB_CABLE_URL}\n",
                encoding="utf-8",
            )
        open_path(VBCABLE_DIR)
        webbrowser.open(VB_CABLE_URL)
        return (
            False,
            "未找到安装程序。\n"
            "请先补全 Runtime（会自动下载虚拟声卡包），\n"
            "或手动把 Setup 与驱动放入 VBCABLE 文件夹。",
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
        if download_if_missing:
            ok, msg = ensure_vbcable_pack(force=True, log=log)
            if not ok or not _has_driver_files(VBCABLE_DIR):
                open_path(VBCABLE_DIR)
                return False, msg if not ok else (
                    "VBCABLE 目录仍缺少驱动文件（.inf / .sys / .cat）。\n"
                    f"目录：{VBCABLE_DIR}"
                )
            setup = find_setup() or setup
        else:
            open_path(VBCABLE_DIR)
            return (
                False,
                "VBCABLE 目录缺少驱动文件（.inf / .sys / .cat）。\n"
                f"目录：{VBCABLE_DIR}",
            )

    try:
        _run_elevated(setup)
        return (
            True,
            f"已启动 {setup.name} — 请处理前台的 UAC / 安装窗口 "
            "（UAC 点「是」，安装窗点 Install）。"
            "若被挡住请看任务栏闪烁或 Alt+Tab。",
        )
    except Exception as e:
        open_path(VBCABLE_DIR)
        return (
            False,
            f"自动启动失败：{e}\n\n"
            f"请在打开的文件夹中右键「{setup.name}」\n"
            "→「以管理员身份运行」。",
        )
