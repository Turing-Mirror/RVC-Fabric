# -*- coding: utf-8 -*-
"""
Pull release-critical files from local RVCMAX pack into this repo for:
  - bat/dev testing without system Python install
  - build_release sources (hubert/rmvpe/ffmpeg/models/VBCABLE)

By default Runtime is **junction-linked** (no multi-GB copy). Use --copy-runtime to robocopy.

Safe sources: only local RVCMAX tree under this repo (no network).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REF = REPO / "RVCMAX" / "RVCMAX_Nvidia_xiaoyuan"
REF_CORE = REF / "RVC_Core"
REF_RT = REF / "Runtime"
REF_MODELS = REF / "User_Data" / "models"
REF_VB = REF / "VBCABLE"


def log(msg: str) -> None:
    print(msg, flush=True)


def must_exist(p: Path, label: str) -> None:
    if not p.exists():
        raise FileNotFoundError(
            f"missing {label}: {p}\n"
            f"Place RVCMAX pack at: {REF}"
        )


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_file() and dst.stat().st_size == src.stat().st_size:
        log(f"  skip (same size): {dst.relative_to(REPO)}")
        return
    shutil.copy2(src, dst)
    log(f"  copy: {src.name} -> {dst.relative_to(REPO)} ({src.stat().st_size // 1024} KB)")


def merge_dir_files(src: Path, dst: Path, patterns: tuple[str, ...] = ("*",)) -> None:
    """Copy files from src into dst (non-recursive file patterns via rglob simple)."""
    if not src.is_dir():
        log(f"  missing dir: {src}")
        return
    dst.mkdir(parents=True, exist_ok=True)
    for pat in patterns:
        for f in src.glob(pat):
            if f.is_file():
                copy_file(f, dst / f.name)


def sync_engine_weights() -> None:
    log("[assets] hubert / rmvpe from RVCMAX RVC_Core")
    must_exist(REF_CORE / "assets" / "hubert" / "hubert_base.pt", "hubert_base.pt")
    must_exist(REF_CORE / "assets" / "rmvpe" / "rmvpe.pt", "rmvpe.pt")
    copy_file(
        REF_CORE / "assets" / "hubert" / "hubert_base.pt",
        REPO / "assets" / "hubert" / "hubert_base.pt",
    )
    for name in ("rmvpe.pt", "rmvpe.onnx", "rmvpe_inputs.pth"):
        src = REF_CORE / "assets" / "rmvpe" / name
        if src.is_file():
            copy_file(src, REPO / "assets" / "rmvpe" / name)
    # optional hubert inputs already small


def sync_ffmpeg() -> None:
    log("[ffmpeg] from RVCMAX RVC_Core")
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        src = REF_CORE / name
        if src.is_file():
            copy_file(src, REPO / name)
        else:
            log(f"  missing optional: {name}")


def sync_models() -> None:
    log("[models] User_Data/models from RVCMAX")
    if not REF_MODELS.is_dir():
        log("  no models dir in ref, skip")
        return
    dst = REPO / "User_Data" / "models"
    dst.mkdir(parents=True, exist_ok=True)
    for child in REF_MODELS.iterdir():
        if not child.is_dir():
            continue
        target = dst / child.name
        if target.exists():
            # refresh pth if missing
            if not any(target.glob("*.pth")):
                shutil.rmtree(target)
            else:
                log(f"  keep existing: models/{child.name}")
                continue
        shutil.copytree(child, target)
        log(f"  model folder: {child.name}")


def sync_vbcable() -> None:
    log("[VBCABLE] from RVCMAX")
    if not REF_VB.is_dir():
        log("  missing VBCABLE in ref")
        return
    dst = REPO / "VBCABLE"
    dst.mkdir(parents=True, exist_ok=True)
    for f in REF_VB.iterdir():
        if f.is_file():
            copy_file(f, dst / f.name)


def link_or_copy_runtime(*, copy: bool) -> None:
    must_exist(REF_RT / "python.exe", "Runtime/python.exe")
    dst = REPO / "Runtime"
    if dst.is_dir() or dst.is_symlink() or dst.is_junction():
        # if already valid python, keep
        if (dst / "python.exe").is_file():
            log(f"[Runtime] already present: {dst}")
            return
        log(f"[Runtime] remove incomplete: {dst}")
        if dst.is_junction() or dst.is_symlink():
            dst.unlink()
        else:
            shutil.rmtree(dst)

    if copy:
        log(f"[Runtime] robocopy {REF_RT} -> {dst} (large)")
        dst.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            rc = subprocess.call(
                [
                    "robocopy",
                    str(REF_RT),
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
            )
            if rc >= 8:
                raise RuntimeError(f"robocopy failed {rc}")
        else:
            shutil.copytree(REF_RT, dst)
    else:
        # Junction (Windows): zero extra disk, bat can use Runtime\python.exe
        log(f"[Runtime] junction {dst} -> {REF_RT}")
        if sys.platform != "win32":
            os.symlink(REF_RT, dst, target_is_directory=True)
        else:
            # mklink /J needs cmd
            rc = subprocess.call(
                ["cmd", "/c", "mklink", "/J", str(dst), str(REF_RT)],
                shell=False,
            )
            if rc != 0 or not (dst / "python.exe").is_file():
                raise RuntimeError(
                    "mklink /J failed (need admin? or path). "
                    "Retry with --copy-runtime"
                )
    log(f"  ok python: {(dst / 'python.exe').is_file()}")


def verify() -> list[str]:
    needed = [
        REPO / "Runtime" / "python.exe",
        REPO / "Runtime" / "pythonw.exe",
        REPO / "assets" / "hubert" / "hubert_base.pt",
        REPO / "assets" / "rmvpe" / "rmvpe.pt",
        REPO / "ffmpeg.exe",
    ]
    missing = [str(p) for p in needed if not p.is_file()]
    models = list((REPO / "User_Data" / "models").glob("*/*.pth")) if (
        REPO / "User_Data" / "models"
    ).is_dir() else []
    if not models:
        missing.append("User_Data/models/*/*.pth (no voice model)")
    return missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--copy-runtime",
        action="store_true",
        help="full copy Runtime instead of junction (for shipping offline copy)",
    )
    ap.add_argument("--skip-runtime", action="store_true")
    ap.add_argument("--skip-models", action="store_true")
    args = ap.parse_args()

    must_exist(REF, "RVCMAX pack root")
    must_exist(REF_CORE, "RVCMAX RVC_Core")

    sync_engine_weights()
    sync_ffmpeg()
    if not args.skip_models:
        sync_models()
    sync_vbcable()
    if not args.skip_runtime:
        link_or_copy_runtime(copy=args.copy_runtime)

    missing = verify()
    if missing:
        log("[verify] MISSING:")
        for m in missing:
            log(f"  - {m}")
        return 1
    log("[verify] OK — bat can use Runtime\\python.exe without system install")
    log("  try: start.bat  or  scripts\\dev\\go-web.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
