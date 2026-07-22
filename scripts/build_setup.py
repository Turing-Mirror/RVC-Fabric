# -*- coding: utf-8 -*-
"""Build RVC Fabric Setup using **Inno Setup** (industry standard), not a custom UI.

Pipeline::

  1. Assemble thin payload (shell + 启动器.exe + 变声器.exe, NO Runtime)
     — reuses scripts/build_release.py PyInstaller targets
  2. Compile installer/RVC_Fabric_Setup.iss with ISCC.exe
  3. Output dist/RVC_Fabric_Setup.exe  (+ optional copy to CNB-GIT-RELEASE/setup/)

Requires Inno Setup 6 on the build machine::

  https://jrsoftware.org/isinfo.php

  Default: C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe

Usage::

  python scripts/build_setup.py --clean
  python scripts/build_setup.py --copy-cnb
  python scripts/build_setup.py --payload-only   # skip ISCC (CI / no Inno yet)

User path: download Setup.exe → install dir + GPU task → 启动器补全 Runtime。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAYLOAD_DEFAULT = REPO / "dist" / "RVC_Fabric_Setup_payload"
DIST_DEFAULT = REPO / "dist"
ISS_FILE = REPO / "installer" / "RVC_Fabric_Setup.iss"
CNB_SETUP = REPO / "CNB-GIT-RELEASE" / "setup"
SETUP_EXE_NAME = "RVC_Fabric_Setup.exe"

sys.path.insert(0, str(REPO / "scripts"))
from build_release import (  # noqa: E402
    copy_engine,
    ensure_pyinstaller,
    log,
    run,
)


def find_iscc() -> Path | None:
    env = os.environ.get("ISCC") or os.environ.get("INNO_SETUP_ISCC")
    if env and Path(env).is_file():
        return Path(env)
    which = shutil.which("ISCC") or shutil.which("ISCC.exe")
    if which:
        return Path(which)
    candidates = (
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Inno Setup 6"
        / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Inno Setup 6"
        / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe"),
    )
    for p in candidates:
        if p.is_file():
            return p
    return None


def build_payload_exes(out: Path) -> None:
    """Same shell exes as full release: 启动器 = bootstrap, 变声器 = main_app."""
    ensure_pyinstaller()
    work = REPO / "build" / "setup_work"
    work.mkdir(parents=True, exist_ok=True)

    specs = [
        ("TM_Setup", REPO / "launcher" / "bootstrap.py", "启动器.exe"),
        ("TM_Voice", REPO / "launcher" / "main_app.py", "变声器.exe"),
    ]
    for name, script, alias in specs:
        log(f"[exe] building {name}.exe from {script.name}")
        run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--clean",
                "--onefile",
                "--windowed",
                "--name",
                name,
                "--distpath",
                str(out),
                "--workpath",
                str(work / name),
                "--specpath",
                str(work / "spec"),
                "--paths",
                str(REPO),
                "--hidden-import",
                "requests",
                str(script),
            ]
        )
        exe = out / f"{name}.exe"
        if not exe.is_file():
            raise FileNotFoundError(f"expected {exe}")
        log(f"  ok: {exe} ({exe.stat().st_size // 1024} KB)")
        shutil.copy2(exe, out / alias)
        log(f"  alias: {alias}")


def write_payload_readme(out: Path) -> None:
    text = """RVC Fabric · 安装内容（由 Inno Setup 安装器部署）
========================================

本目录是「薄包 payload」，不含 Runtime。
用户应运行 dist\\RVC_Fabric_Setup.exe（Inno Setup 生成）。

安装后：
1. 启动器自动从 CNB Release 下载 Runtime
2. 主界面 → 新手指引 → 社区音色（LFS）→ 变声

制品：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases
"""
    (out / "使用说明.txt").write_text(text, encoding="utf-8")


def assemble_payload(out: Path, *, skip_exe: bool) -> None:
    log(f"[payload] assemble -> {out}")
    out.mkdir(parents=True, exist_ok=True)
    copy_engine(out)
    (out / "User_Data" / "models").mkdir(parents=True, exist_ok=True)
    (out / "VBCABLE").mkdir(parents=True, exist_ok=True)
    vb_src = REPO / "VBCABLE"
    if vb_src.is_dir():
        for f in vb_src.iterdir():
            if f.is_file() and f.suffix.lower() in (".exe", ".txt", ".md"):
                shutil.copy2(f, out / "VBCABLE" / f.name)

    meta = {
        "product": "RVC Fabric",
        "package_kind": "setup_payload",
        "includes_runtime": False,
        "runtime_channel": "cnb_release",
        "runtime_release_tag": "RVC-runtime",
        "cnb_repo": "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases",
        "installer": "inno_setup",
        "iss": "installer/RVC_Fabric_Setup.iss",
    }
    (out / "setup_package.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_payload_readme(out)

    if skip_exe:
        log("[exe] skipped")
        return
    build_payload_exes(out)
    if not (out / "启动器.exe").is_file():
        raise FileNotFoundError("payload missing 启动器.exe")
    if not (out / "变声器.exe").is_file():
        raise FileNotFoundError("payload missing 变声器.exe")


def compile_inno(payload: Path, output_dir: Path) -> Path:
    iscc = find_iscc()
    if iscc is None:
        raise FileNotFoundError(
            "未找到 Inno Setup 编译器 ISCC.exe。\n"
            "请安装 Inno Setup 6：https://jrsoftware.org/isinfo.php\n"
            "或设置环境变量 ISCC=C:\\Path\\to\\ISCC.exe\n"
            "仅准备 payload 可加参数：--payload-only"
        )
    if not ISS_FILE.is_file():
        raise FileNotFoundError(f"missing {ISS_FILE}")

    output_dir.mkdir(parents=True, exist_ok=True)
    # Inno #define overrides via /D
    cmd = [
        str(iscc),
        f"/DPayloadDir={payload}",
        f"/DOutputDir={output_dir}",
        f"/DOutputBase=RVC_Fabric_Setup",
        str(ISS_FILE),
    ]
    log("[inno] $ " + " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(REPO))
    setup = output_dir / SETUP_EXE_NAME
    if not setup.is_file():
        # some ISCC versions may not add .exe in path check race
        raise FileNotFoundError(f"ISCC finished but missing {setup}")
    log(f"[inno] ok: {setup} ({setup.stat().st_size // 1024} KB)")
    # convenient alias
    alias = output_dir / "Setup.exe"
    shutil.copy2(setup, alias)
    log(f"[inno] alias: {alias}")
    return setup


def copy_to_cnb(setup_exe: Path) -> None:
    CNB_SETUP.mkdir(parents=True, exist_ok=True)
    dest = CNB_SETUP / SETUP_EXE_NAME
    shutil.copy2(setup_exe, dest)
    (CNB_SETUP / "README.txt").write_text(
        "RVC_Fabric_Setup.exe = Inno Setup 安装器（薄包，无 Runtime）。\n"
        "用户双击安装 → 启动器从 CNB Release 补全 Runtime。\n"
        "推送到 CNB：见 CNB-GIT-RELEASE/SYNC_COMMANDS.txt（cnb CLI / skill）。\n"
        "构建：产品仓 python scripts/build_setup.py --copy-cnb\n"
        "安装器脚本：installer/RVC_Fabric_Setup.iss\n",
        encoding="utf-8",
    )
    log(f"[cnb] copied {dest} ({dest.stat().st_size // 1024} KB)")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build RVC Fabric Setup with Inno Setup (not custom Tk installer)"
    )
    p.add_argument("--payload", type=Path, default=PAYLOAD_DEFAULT, help="payload dir")
    p.add_argument("--out", type=Path, default=DIST_DEFAULT, help="ISCC output dir")
    p.add_argument("--skip-exe", action="store_true", help="payload without PyInstaller")
    p.add_argument("--payload-only", action="store_true", help="skip Inno compile")
    p.add_argument("--clean", action="store_true")
    p.add_argument(
        "--copy-cnb",
        action="store_true",
        help="copy Setup.exe into CNB-GIT-RELEASE/setup/",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    payload = args.payload.resolve()
    out_dir = args.out.resolve()

    log("=== RVC Fabric Setup (Inno Setup) ===")
    log("  installer tech: Inno Setup 6 (.iss), not launcher/setup_app.py")

    if args.clean:
        if payload.exists():
            log(f"[clean] {payload}")
            shutil.rmtree(payload)
        old = out_dir / SETUP_EXE_NAME
        if old.is_file():
            old.unlink()

    try:
        assemble_payload(payload, skip_exe=args.skip_exe)
    except Exception as e:
        log(f"[payload] FAILED: {e}")
        return 1

    setup_exe: Path | None = None
    if args.payload_only:
        log("[inno] skipped (--payload-only)")
        log(f"Payload ready: {payload}")
        log("Install Inno Setup 6 then re-run without --payload-only")
    else:
        try:
            setup_exe = compile_inno(payload, out_dir)
        except FileNotFoundError as e:
            log(f"[inno] {e}")
            log(f"Payload is ready at: {payload}")
            return 2
        except subprocess.CalledProcessError as e:
            log(f"[inno] ISCC failed: {e}")
            return 1

    if args.copy_cnb:
        if setup_exe is None or not setup_exe.is_file():
            log("[cnb] no Setup.exe to copy (compile Inno first)")
            return 1
        try:
            copy_to_cnb(setup_exe)
        except Exception as e:
            log(f"[cnb] FAILED: {e}")
            return 1

    log("=== done ===")
    if setup_exe:
        log(f"User Setup: {setup_exe}")
    log("After install: 启动器.exe auto-downloads Runtime from CNB Release")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
