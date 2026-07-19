# -*- coding: utf-8 -*-
"""
One-click release packer for Turing Mirror 变声器.

Builds a RVCMAX-style tree::

    dist/TuringMirror_Voice/
      启动器.exe          first-run helper (exe)
      变声器.exe          daily app (exe)
      Runtime/            embedded Python (required)
      User_Data/models/   bundled voice models
      VBCABLE/            VB-Cable installers
      assets/ … infer/    engine (from this repo)
      使用说明.txt

Usage (from repo root)::

    python scripts/build_release.py
    python scripts/build_release.py --runtime "D:\\path\\Runtime" --models "D:\\models"
    python scripts/build_release.py --skip-exe          # layout only
    python scripts/build_release.py --skip-runtime      # dev dry-run without copy

Default Runtime/models/VBCABLE sources try the local RVCMAX reference pack if present.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "dist" / "TuringMirror_Voice"
REF = REPO / "RVCMAX" / "RVCMAX_Nvidia_xiaoyuan"

# Engine files/dirs to ship (lean but runnable)
ENGINE_DIRS = (
    "assets",
    "configs",
    "i18n",
    "infer",
    "launcher",
    "tools",
    "docs",
)
ENGINE_FILES = (
    ".env",
    "infer-web.py",
    "gui_v1.py",
    "LICENSE",
    "README.md",
)


def log(msg: str) -> None:
    print(msg, flush=True)


def copy_tree(src: Path, dst: Path, *, ignore=None) -> None:
    if not src.is_dir():
        raise FileNotFoundError(f"missing source dir: {src}")
    if dst.exists():
        shutil.rmtree(dst)
    log(f"  copy dir: {src} -> {dst}")
    shutil.copytree(
        src,
        dst,
        ignore=ignore,
        dirs_exist_ok=False,
    )


def robocopy(src: Path, dst: Path) -> None:
    """Fast Windows copy for large Runtime trees."""
    dst.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        # /MIR mirror; /NFL /NDL quieter; /R:2 retries
        cmd = [
            "robocopy",
            str(src),
            str(dst),
            "/E",
            "/NFL",
            "/NDL",
            "/NJH",
            "/NJS",
            "/nc",
            "/ns",
            "/np",
            "/R:2",
            "/W:2",
        ]
        log(f"  robocopy: {src} -> {dst}")
        rc = subprocess.call(cmd)
        # robocopy 0-7 = success-ish
        if rc >= 8:
            raise RuntimeError(f"robocopy failed code {rc}")
    else:
        copy_tree(src, dst)


def run(cmd: list[str], cwd: Path | None = None) -> None:
    log("  $ " + " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(cwd or REPO))


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "-U", "pyinstaller"])


def build_exes(out: Path) -> None:
    ensure_pyinstaller()
    work = REPO / "build" / "release_work"
    work.mkdir(parents=True, exist_ok=True)

    # ASCII names for PyInstaller (Windows code-page safe); Chinese aliases copied after
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
                str(script),
            ]
        )
        exe = out / f"{name}.exe"
        if not exe.is_file():
            raise FileNotFoundError(f"expected {exe}")
        log(f"  ok: {exe} ({exe.stat().st_size // 1024} KB)")
        # Chinese display name for end users (Python handles Unicode paths)
        alias_path = out / alias
        shutil.copy2(exe, alias_path)
        log(f"  alias: {alias_path.name}")


def copy_engine(out: Path) -> None:
    log("[engine] copy core from repo")

    def _ignore(directory: str, names: list[str]) -> set[str]:
        skip = set()
        base = Path(directory).name
        for n in names:
            if n in (
                "__pycache__",
                ".git",
                ".pytest_cache",
                "build",
                "dist",
                "RVCMAX",
                "TEMP",
                ".venv",
            ):
                skip.add(n)
            if n.endswith(".pyc"):
                skip.add(n)
        # skip huge optional training logs under logs except mute fixtures
        return skip

    for d in ENGINE_DIRS:
        src = REPO / d
        if src.is_dir():
            copy_tree(src, out / d, ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                ".git",
            ))
    for f in ENGINE_FILES:
        src = REPO / f
        if src.is_file():
            shutil.copy2(src, out / f)
            log(f"  file: {f}")

    # dev launchers (not for end-users)
    dev_src = REPO / "scripts" / "dev"
    if dev_src.is_dir():
        copy_tree(dev_src, out / "scripts" / "dev")

    # Merge critical weights/ffmpeg from RVCMAX if repo placeholders are empty
    merge_rvcmax_engine_bits(out)


def merge_rvcmax_engine_bits(out: Path) -> None:
    """Fill hubert/rmvpe/ffmpeg from local RVCMAX pack (no network)."""
    core = REF / "RVC_Core"
    if not core.is_dir():
        log("[merge] RVCMAX RVC_Core not found — ensure hubert/rmvpe already in out/assets")
        return
    log("[merge] hubert / rmvpe / ffmpeg from RVCMAX")

    def _cf(src: Path, dst: Path) -> None:
        if not src.is_file():
            log(f"  missing: {src}")
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_file() and dst.stat().st_size == src.stat().st_size:
            log(f"  skip: {dst.relative_to(out)}")
            return
        shutil.copy2(src, dst)
        log(f"  + {dst.relative_to(out)} ({src.stat().st_size // 1024 // 1024} MB)")

    _cf(core / "assets" / "hubert" / "hubert_base.pt", out / "assets" / "hubert" / "hubert_base.pt")
    for n in ("rmvpe.pt", "rmvpe.onnx"):
        _cf(core / "assets" / "rmvpe" / n, out / "assets" / "rmvpe" / n)
    for n in ("ffmpeg.exe", "ffprobe.exe"):
        _cf(core / n, out / n)


def copy_runtime(out: Path, runtime_src: Path | None) -> None:
    dst = out / "Runtime"
    if runtime_src is None:
        # Keep an existing complete Runtime (incremental rebuild / --skip-runtime)
        if (dst / "python.exe").is_file():
            log(f"[runtime] SKIP — keep existing {dst}")
            # Remove stale placeholder if a real Runtime is present
            ph = dst / "README_PLACE_RUNTIME_HERE.txt"
            if ph.is_file():
                try:
                    ph.unlink()
                except Exception:
                    pass
            return
        log("[runtime] SKIP (--skip-runtime or no source) — writing placeholder")
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "README_PLACE_RUNTIME_HERE.txt").write_text(
            "Put embedded Python Runtime here (python.exe + site-packages).\n"
            "Or re-run: python scripts/build_release.py --runtime <path>\n",
            encoding="utf-8",
        )
        return
    if not runtime_src.is_dir():
        raise FileNotFoundError(f"Runtime source not found: {runtime_src}")
    log(f"[runtime] from {runtime_src}")
    if dst.exists():
        shutil.rmtree(dst)
    robocopy(runtime_src, dst)
    py = dst / "python.exe"
    if not py.is_file():
        raise FileNotFoundError(f"Runtime incomplete: no python.exe in {dst}")


def copy_vbcable(out: Path, src: Path | None) -> None:
    dst = out / "VBCABLE"
    if src is None or not src.is_dir():
        log("[vbcable] using repo VBCABLE + placeholder")
        repo_v = REPO / "VBCABLE"
        if repo_v.is_dir():
            copy_tree(repo_v, dst)
        else:
            dst.mkdir(parents=True, exist_ok=True)
        return
    log(f"[vbcable] from {src}")
    copy_tree(src, dst)


def copy_models(out: Path, models_src: Path | None) -> None:
    dst = out / "User_Data" / "models"
    dst.mkdir(parents=True, exist_ok=True)
    (out / "User_Data" / "logs").mkdir(parents=True, exist_ok=True)
    if models_src and models_src.is_dir():
        log(f"[models] from {models_src}")
        # if models_src is already models/ with numbered folders
        if any(models_src.glob("*/**/*.pth")) or any(models_src.glob("*/*.pth")):
            for child in models_src.iterdir():
                if child.is_dir():
                    target = dst / child.name
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(child, target)
                elif child.suffix.lower() == ".pth":
                    name = child.stem
                    folder = dst / name
                    folder.mkdir(exist_ok=True)
                    shutil.copy2(child, folder / child.name)
        elif any(models_src.glob("*.pth")):
            for pth in models_src.glob("*.pth"):
                folder = dst / pth.stem
                folder.mkdir(exist_ok=True)
                shutil.copy2(pth, folder / pth.name)
        else:
            # copy tree as-is
            for child in models_src.iterdir():
                if child.is_dir():
                    shutil.copytree(child, dst / child.name, dirs_exist_ok=True)
    else:
        log("[models] no source — empty catalog (import in UI later)")
    # also pull any existing User_Data/models from repo
    repo_m = REPO / "User_Data" / "models"
    if repo_m.is_dir():
        for child in repo_m.iterdir():
            if child.is_dir() and any(child.glob("*.pth")):
                t = dst / child.name
                if not t.exists():
                    shutil.copytree(child, t)
                    log(f"  + repo model {child.name}")


def write_readme(out: Path) -> None:
    text = f"""Turing Mirror 变声器 — 发行版
================================

【用户只需要】
1. 解压到英文路径（推荐 D:\\TM_Voice\\）
2. 双击「启动器.exe」（或 TM_Setup.exe）
3. 点「发送快捷方式」「安装虚拟声卡」
4. 之后双击桌面图标或「变声器.exe」（或 TM_Voice.exe）

【已内置】
- Runtime\\     绿色 Python 环境（无需自装 Python）
- User_Data\\models\\  预置音色（若打包时带了）
- VBCABLE\\     虚拟声卡安装包
- 引擎与界面

【不要用】
- tools\\dev\\ 下的 .bat 仅供开发调试
- 不要指望系统里另装 Python

打包时间: {time.strftime("%Y-%m-%d %H:%M:%S")}
"""
    (out / "使用说明.txt").write_text(text, encoding="utf-8")
    log("[doc] 使用说明.txt")


def default_runtime() -> Path | None:
    for p in (
        REF / "Runtime",
        REPO / "Runtime",
        Path(os.environ.get("TM_RUNTIME_SRC", "")),
    ):
        if p and str(p) and (p / "python.exe").is_file():
            return p
    return None


def default_models() -> Path | None:
    for p in (
        REF / "User_Data" / "models",
        REPO / "User_Data" / "models",
        Path(os.environ.get("TM_MODELS_SRC", "")),
    ):
        if p and str(p) and p.is_dir():
            return p
    return None


def default_vbcable() -> Path | None:
    for p in (REF / "VBCABLE", REPO / "VBCABLE"):
        if p.is_dir() and any(p.glob("*.exe")):
            return p
    return REPO / "VBCABLE" if (REPO / "VBCABLE").is_dir() else None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build Turing Mirror Voice release pack")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    p.add_argument("--runtime", type=Path, default=None, help="Runtime source dir")
    p.add_argument("--models", type=Path, default=None, help="models source dir")
    p.add_argument("--vbcable", type=Path, default=None, help="VBCABLE source dir")
    p.add_argument("--skip-exe", action="store_true", help="do not run PyInstaller")
    p.add_argument("--skip-runtime", action="store_true", help="do not copy Runtime")
    p.add_argument("--clean", action="store_true", help="wipe out dir first")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out: Path = args.out.resolve()
    log(f"=== build release -> {out} ===")

    if args.clean and out.exists():
        log("[clean] remove old out")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # 1) engine
    copy_engine(out)

    # 2) runtime
    if args.skip_runtime:
        copy_runtime(out, None)
    else:
        rt = args.runtime or default_runtime()
        if rt is None:
            log(
                "[runtime] WARNING: no Runtime source. "
                "Pass --runtime PATH (e.g. RVCMAX pack Runtime)."
            )
            copy_runtime(out, None)
        else:
            copy_runtime(out, rt)

    # 3) models
    copy_models(out, args.models or default_models())

    # 4) vbcable
    copy_vbcable(out, args.vbcable or default_vbcable())

    # 5) exes into out root
    if not args.skip_exe:
        try:
            build_exes(out)
        except Exception as e:
            log(f"[exe] FAILED: {e}")
            log("  You can re-run without --skip-exe after fixing PyInstaller.")
            return 1
    else:
        log("[exe] skipped")

    write_readme(out)

    # summary
    log("=== done ===")
    log(f"Output: {out}")
    for name in (
        "TM_Setup.exe",
        "TM_Voice.exe",
        "启动器.exe",
        "变声器.exe",
        "Runtime",
        "User_Data",
        "VBCABLE",
    ):
        p = out / name
        mark = "OK" if (p.is_file() or p.is_dir()) else "MISSING"
        log(f"  [{mark}] {name}")
    log("User path: unzip -> double-click 启动器.exe or TM_Setup.exe (no bat).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
