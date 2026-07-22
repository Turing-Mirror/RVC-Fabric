# -*- coding: utf-8 -*-
"""Build thin Setup package (shell + Setup/启动器/主界面 exe, NO Runtime).

Output::

    dist/RVC_Fabric_Setup/
      RVC Fabric Setup.exe   # installer wizard
      Setup.exe              # alias
      启动器.exe / TM_Setup.exe
      变声器.exe / TM_Voice.exe
      launcher/ … engine …
      使用说明-Setup.txt

Optional copy into CNB staging::

    python scripts/build_setup.py --copy-cnb

User path: unzip → run Setup.exe → pick folder + GPU → 启动器 downloads Runtime
from CNB Release; voices later via in-app LFS.
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
DEFAULT_OUT = REPO / "dist" / "RVC_Fabric_Setup"
CNB_SETUP = REPO / "CNB-GIT-RELEASE" / "setup"

# Reuse engine copy rules from full release packer
sys.path.insert(0, str(REPO / "scripts"))
from build_release import (  # noqa: E402
    ENGINE_DIRS,
    ENGINE_FILES,
    copy_engine,
    ensure_pyinstaller,
    log,
    run,
)


def build_setup_exes(out: Path) -> None:
    ensure_pyinstaller()
    work = REPO / "build" / "setup_work"
    work.mkdir(parents=True, exist_ok=True)

    specs = [
        ("RVC_Fabric_Setup", REPO / "launcher" / "setup_app.py", "RVC Fabric Setup.exe"),
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
        alias_path = out / alias
        shutil.copy2(exe, alias_path)
        log(f"  alias: {alias_path.name}")
        if name == "RVC_Fabric_Setup":
            shutil.copy2(exe, out / "Setup.exe")
            log("  alias: Setup.exe")


def write_setup_readme(out: Path) -> None:
    text = """RVC Fabric · Setup 安装包（薄包，不含 Runtime）
========================================

【用户路径】
1. 解压本文件夹到任意位置（建议英文路径）
2. 双击「RVC Fabric Setup.exe」或 Setup.exe
3. 选择安装目录 + 显卡分版（NVIDIA / AMD·Intel / 50 系）
4. 安装完成后打开「启动器」——自动从 CNB Release 下载 Runtime
5. 进入主界面：新手指引 → 社区下载音色 → 变声使用

【制品来源】
- 仓库：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases
- Runtime：CNB Release 附件（标签 RVC-runtime）
- 音色包：CNB Git LFS（…/-/lfs/<sha256>）

【注意】
- 本包不含数 GB 的 Runtime；首次启动需联网补全
- 完整绿色环境也可由打包机用 scripts/build_release.py 打全量包
"""
    (out / "使用说明-Setup.txt").write_text(text, encoding="utf-8")


def write_setup_meta(out: Path) -> None:
    meta = {
        "product": "RVC Fabric",
        "package_kind": "setup_shell",
        "includes_runtime": False,
        "runtime_channel": "cnb_release",
        "runtime_release_tag": "RVC-runtime",
        "cnb_repo": "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases",
        "note": "启动器按 package_meta.variant 从 Release 拉 Runtime",
    }
    (out / "setup_package.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # default variant tag (user overrides in Setup wizard)
    try:
        sys.path.insert(0, str(REPO))
        from launcher.package_meta import write_package_meta

        write_package_meta(out, "nvidia", install_via="setup_shell", tagged=False)
    except Exception as e:
        log(f"[meta] skip package_meta: {e}")


def copy_to_cnb(out: Path) -> None:
    CNB_SETUP.mkdir(parents=True, exist_ok=True)
    # zip for LFS-friendly single artifact
    zip_path = CNB_SETUP / "RVC_Fabric_Setup.zip"
    if zip_path.is_file():
        zip_path.unlink()
    log(f"[cnb] zipping {out} -> {zip_path}")
    shutil.make_archive(
        str(zip_path.with_suffix("")),
        "zip",
        root_dir=str(out),
    )
    # also leave a README pointer
    (CNB_SETUP / "README.txt").write_text(
        "RVC_Fabric_Setup.zip = 薄安装包（无 Runtime）。\n"
        "用户解压后运行 Setup.exe / RVC Fabric Setup.exe。\n"
        "推送到 CNB：见 CNB-GIT-RELEASE/SYNC_COMMANDS.txt\n",
        encoding="utf-8",
    )
    log(f"[cnb] done: {zip_path} ({zip_path.stat().st_size // 1024} KB)")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build RVC Fabric thin Setup package")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--skip-exe", action="store_true")
    p.add_argument("--clean", action="store_true")
    p.add_argument(
        "--copy-cnb",
        action="store_true",
        help="zip output into CNB-GIT-RELEASE/setup/",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out = args.out.resolve()
    log(f"=== build Setup (thin, no Runtime) -> {out} ===")
    if args.clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # engine shell (same as release but we never copy Runtime)
    copy_engine(out)
    # empty User_Data / VBCABLE dirs
    (out / "User_Data" / "models").mkdir(parents=True, exist_ok=True)
    (out / "VBCABLE").mkdir(parents=True, exist_ok=True)
    vb_src = REPO / "VBCABLE"
    if vb_src.is_dir():
        for f in vb_src.iterdir():
            if f.is_file() and f.suffix.lower() in (".exe", ".txt", ".md"):
                shutil.copy2(f, out / "VBCABLE" / f.name)

    write_setup_meta(out)
    write_setup_readme(out)

    if not args.skip_exe:
        try:
            build_setup_exes(out)
        except Exception as e:
            log(f"[exe] FAILED: {e}")
            return 1
    else:
        log("[exe] skipped")

    if args.copy_cnb:
        try:
            copy_to_cnb(out)
        except Exception as e:
            log(f"[cnb] FAILED: {e}")
            return 1

    log("=== done ===")
    log(f"Output: {out}")
    log("User: unzip -> RVC Fabric Setup.exe -> 启动器 auto Runtime from CNB Release")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
