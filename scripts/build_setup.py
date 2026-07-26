# -*- coding: utf-8 -*-
"""Build RVC Fabric Setup with Inno Setup 6.

What goes into Setup (payload) — **thin shell** (plan B)::

  - 软件壳：启动器.exe / 变声器.exe / launcher / gui_v1 / infer / configs …
  - **不含** Runtime（CNB Release，按显卡分版）
  - **不含** engine-core（hubert / rmvpe / ffmpeg / ffprobe — CNB LFS 共用包）
  - **不含** VB-Cable（CNB LFS）

安装后启动器顺序：Runtime → engine-core → VB-Cable。

Usage::

  set ISCC=C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe
  python scripts/build_setup.py --clean
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
    assert_pyinstaller_collected_tkinter,
    copy_engine,
    ensure_pyinstaller,
    ensure_shell_download_deps,
    ensure_shell_ui_deps,
    log,
    run,
    shell_pyinstaller_args,
)


def find_iscc() -> Path | None:
    env = os.environ.get("ISCC") or os.environ.get("INNO_SETUP_ISCC")
    if env and Path(env).is_file():
        return Path(env)
    which = shutil.which("ISCC") or shutil.which("ISCC.exe")
    if which:
        return Path(which)
    candidates = (
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Inno Setup 6"
        / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Inno Setup 6"
        / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    )
    for p in candidates:
        if p.is_file():
            return p
    return None


def ensure_no_runtime(out: Path) -> None:
    """Setup 唯一禁止打入的大环境：Runtime/（由 CNB 下载）。"""
    for name in ("Runtime", "runtime"):
        p = out / name
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
            log(f"[payload] removed {name}/ (CNB-only; not in Setup)")
    if (out / "Runtime" / "python.exe").is_file():
        raise RuntimeError("SAFETY: Runtime still present in payload — abort")


def build_payload_exes(out: Path) -> None:
    """启动器 = bootstrap，变声器 = main_app（与全量包相同 PyInstaller 目标）。

    用户机不需要装 Python：exe 自带解释器 + 下载依赖 + tkinter。
    打包机必须用完整 CPython（含 Tcl/Tk），且已装 requests / Pillow。
    """
    ensure_pyinstaller()
    ensure_shell_download_deps()
    ensure_shell_ui_deps()
    work = REPO / "build" / "setup_work"
    work.mkdir(parents=True, exist_ok=True)

    specs = [
        ("TM_Setup", REPO / "launcher" / "bootstrap.py", "启动器.exe"),
        ("TM_Voice", REPO / "launcher" / "main_app.py", "变声器.exe"),
    ]
    for name, script, alias in specs:
        log(f"[exe] building {name}.exe from {script.name}")
        run(
            shell_pyinstaller_args(
                name=name,
                script=script,
                distpath=out,
                workpath=work / name,
                specpath=work / "spec",
            )
        )
        assert_pyinstaller_collected_tkinter(work / name / name, name)
        exe = out / f"{name}.exe"
        if not exe.is_file():
            raise FileNotFoundError(f"expected {exe}")
        log(f"  ok: {exe} ({exe.stat().st_size // 1024} KB)")
        shutil.copy2(exe, out / alias)
        log(f"  alias: {alias}")


def write_payload_readme(out: Path) -> None:
    text = """RVC Fabric · Setup 薄包
========================================

本包含：软件壳（启动器 + 主界面）、引擎源码与配置。
本包不含（安装后由启动器从 CNB 下载）：
  1. Runtime（绿色 Python，按显卡分版）
  2. engine-core（hubert / rmvpe / ffmpeg / ffprobe，全卡共用）
  3. VB-Cable 虚拟声卡安装包

CNB：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases
"""
    (out / "使用说明.txt").write_text(text, encoding="utf-8")


def strip_heavy_from_payload(out: Path) -> None:
    """Remove engine-core weights / ffmpeg and other bulk so Setup stays thin."""
    removed = 0

    def _rm(p: Path) -> None:
        nonlocal removed
        if p.is_file():
            try:
                sz = p.stat().st_size
                p.unlink()
                removed += sz
                log(f"  strip file: {p.relative_to(out)} ({sz // 1024 // 1024} MB)")
            except OSError as e:
                log(f"  strip fail: {p}: {e}")
        elif p.is_dir():
            try:
                shutil.rmtree(p)
                log(f"  strip dir: {p.relative_to(out)}")
            except OSError as e:
                log(f"  strip dir fail: {p}: {e}")

    for rel in (
        "assets/hubert/hubert_base.pt",
        "assets/rmvpe/rmvpe.pt",
        "assets/rmvpe/rmvpe.onnx",
        "ffmpeg.exe",
        "ffprobe.exe",
    ):
        _rm(out / rel)

    # 整个 docs/ 不进用户安装包（含内部开发文档、会话日志、设计计划）。
    # 仅保留 docs/legal/（MIT 协议声明）→ 拷贝到 out/legal 后删除 docs。
    legal_src = out / "docs" / "legal"
    legal_dst = out / "legal"
    if legal_src.is_dir():
        if legal_dst.exists():
            shutil.rmtree(legal_dst, ignore_errors=True)
        shutil.copytree(legal_src, legal_dst)
        log("  keep: docs/legal -> legal/ (MIT 协议声明)")
    _rm(out / "docs")

    for rel in (
        "assets/pretrained",
        "assets/pretrained_v2",
        "assets/uvr5_weights",
        "assets/indices",
    ):
        p = out / rel
        if p.exists():
            _rm(p)

    for name in ("TM_Setup.exe", "TM_Voice.exe"):
        _rm(out / name)

    for d in (
        out / "assets" / "hubert",
        out / "assets" / "rmvpe",
        out / "assets" / "weights",
    ):
        d.mkdir(parents=True, exist_ok=True)
    (out / "assets" / "hubert" / "请由启动器下载engine-core.txt").write_text(
        "hubert_base.pt 由启动器从 CNB engine-core 包下载。\n",
        encoding="utf-8",
    )
    (out / "assets" / "rmvpe" / "请由启动器下载engine-core.txt").write_text(
        "rmvpe.pt / rmvpe.onnx 由启动器从 CNB engine-core 包下载。\n",
        encoding="utf-8",
    )
    log(f"[strip] removed ~{removed // 1024 // 1024} MB heavy assets from payload")


def sanitize_inuse_config(out: Path) -> None:
    """Never ship developer absolute paths in configs/inuse/config.json."""
    sys.path.insert(0, str(REPO))
    from launcher.inuse_config import write_clean_inuse

    write_clean_inuse(out)
    log("[payload] sanitized configs/inuse/config.json (clean template, no absolute paths)")


def assemble_payload(out: Path, *, skip_exe: bool) -> None:
    log(f"[payload] assemble -> {out}")
    out.mkdir(parents=True, exist_ok=True)
    copy_engine(out)
    sanitize_inuse_config(out)
    ensure_no_runtime(out)
    strip_heavy_from_payload(out)
    for dead in (
        out / "launcher" / "setup_app.py",
        out / "launcher" / "_setup_shell.py",
    ):
        if dead.is_file():
            try:
                dead.unlink()
                log(f"  strip deprecated: {dead.name}")
            except OSError:
                pass

    (out / "User_Data" / "models").mkdir(parents=True, exist_ok=True)
    dst_vb = out / "VBCABLE"
    if dst_vb.exists():
        shutil.rmtree(dst_vb, ignore_errors=True)
    dst_vb.mkdir(parents=True, exist_ok=True)
    (dst_vb / "虚拟声卡由启动器下载.txt").write_text(
        "VB-Cable 安装包不随 Setup 安装。\n\n"
        "流程：\n"
        "1. 启动器「补全运行环境」下载 Runtime\n"
        "2. 下载 engine-core（hubert/rmvpe/ffmpeg）\n"
        "3. 下载 VB-Cable 安装包到本目录\n"
        "4. 点「安装虚拟声卡」启动官方安装程序（需 UAC）\n\n"
        "CNB：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases\n",
        encoding="utf-8",
    )
    log("[vbcable] placeholder only")

    meta = {
        "product": "RVC Fabric",
        "package_kind": "setup_payload",
        "includes_runtime": False,
        "includes_vbcable": False,
        "includes_engine_assets": False,
        "includes_engine_core": False,
        "runtime_channel": "cnb_release",
        "runtime_release_tag": "RVC-runtime",
        "engine_core_channel": "cnb_lfs",
        "engine_core_path": "assets/core/engine-core-*.zip",
        "vbcable_channel": "cnb_lfs",
        "cnb_repo": "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases",
        "installer": "inno_setup",
        "iss": "installer/RVC_Fabric_Setup.iss",
        "note": "薄包：壳+源码。Runtime（分版）+ engine-core（共用）+ VB-Cable 均从 CNB 补全",
    }
    (out / "setup_package.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_payload_readme(out)

    if skip_exe:
        log("[exe] skipped")
        return
    build_payload_exes(out)
    ensure_no_runtime(out)
    strip_heavy_from_payload(out)
    for name in ("TM_Setup.exe", "TM_Voice.exe"):
        p = out / name
        if p.is_file():
            try:
                p.unlink()
                log(f"  strip duplicate exe: {name}")
            except OSError:
                pass
    if not (out / "启动器.exe").is_file():
        raise FileNotFoundError("payload missing 启动器.exe")
    if not (out / "变声器.exe").is_file():
        raise FileNotFoundError("payload missing 变声器.exe")


def compile_inno(payload: Path, output_dir: Path) -> Path:
    iscc = find_iscc()
    if iscc is None:
        raise FileNotFoundError(
            "未找到 ISCC.exe。\n"
            "本机路径示例：C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe\n"
            "或设置环境变量 ISCC=完整路径\\ISCC.exe"
        )
    if not ISS_FILE.is_file():
        raise FileNotFoundError(f"missing {ISS_FILE}")

    output_dir.mkdir(parents=True, exist_ok=True)
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
        raise FileNotFoundError(f"ISCC finished but missing {setup}")
    log(f"[inno] ok: {setup} ({setup.stat().st_size // 1024} KB)")
    shutil.copy2(setup, output_dir / "Setup.exe")
    return setup


def copy_to_cnb(setup_exe: Path) -> None:
    CNB_SETUP.mkdir(parents=True, exist_ok=True)
    dest = CNB_SETUP / SETUP_EXE_NAME
    shutil.copy2(setup_exe, dest)
    (CNB_SETUP / "README.txt").write_text(
        "RVC_Fabric_Setup.exe = Inno 薄包（壳层+主界面，不含 Runtime / engine-core）。\n"
        "Runtime：CNB Release（按显卡）。engine-core：assets/core/（LFS 共用）。\n"
        "构建：python scripts/build_setup.py\n",
        encoding="utf-8",
    )
    log(f"[cnb] copied {dest} ({dest.stat().st_size // 1024} KB)")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build RVC Fabric Setup (Inno; no Runtime)")
    p.add_argument("--payload", type=Path, default=PAYLOAD_DEFAULT)
    p.add_argument("--out", type=Path, default=DIST_DEFAULT)
    p.add_argument("--skip-exe", action="store_true")
    p.add_argument("--payload-only", action="store_true")
    p.add_argument("--clean", action="store_true")
    p.add_argument("--copy-cnb", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    payload = args.payload.resolve()
    out_dir = args.out.resolve()

    log("=== RVC Fabric Setup (Inno Setup · thin shell) ===")
    log("  payload: 启动器 + 变声器 + 源码/配置")
    log("  NOT in payload: Runtime / engine-core / VB-Cable (CNB)")

    if args.clean:
        if payload.exists():
            log(f"[clean] {payload}")
            shutil.rmtree(payload)
        for name in (SETUP_EXE_NAME, "Setup.exe"):
            old = out_dir / name
            if old.is_file():
                old.unlink()
                log(f"[clean] {old.name}")

    try:
        assemble_payload(payload, skip_exe=args.skip_exe)
    except Exception as e:
        log(f"[payload] FAILED: {e}")
        return 1

    setup_exe: Path | None = None
    if args.payload_only:
        log("[inno] skipped (--payload-only)")
    else:
        try:
            setup_exe = compile_inno(payload, out_dir)
        except FileNotFoundError as e:
            log(f"[inno] {e}")
            return 2
        except subprocess.CalledProcessError as e:
            log(f"[inno] ISCC failed: {e}")
            return 1

    if args.copy_cnb:
        if setup_exe is None or not setup_exe.is_file():
            log("[cnb] no Setup.exe")
            return 1
        copy_to_cnb(setup_exe)

    log("=== done ===")
    if setup_exe:
        log(f"User Setup: {setup_exe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
