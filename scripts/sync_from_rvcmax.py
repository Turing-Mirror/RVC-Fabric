# -*- coding: utf-8 -*-
"""
Pull release-critical files from local RVCMAX pack into this repo for:
  - bat/dev testing without system Python install
  - build_release sources (hubert/rmvpe/ffmpeg/models/VBCABLE)

By default Runtime is **junction-linked** (no multi-GB copy). Use --copy-runtime to robocopy.

Safe sources: only local RVCMAX tree under this repo (no network).

Variant (official multi-pack)::

    --variant nvidia     RVCMAX_Nvidia_xiaoyuan   (CUDA)
    --variant amd        RVCMAX_AMD_xiaoyuan      (DirectML)
    --variant nvidia50   RVCMAX_Nvidia50x0_xiaoyuan (50-series CUDA)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RVCMAX_ROOT = REPO / "RVCMAX"

# Align with scripts/build_release.py VARIANTS.prefer_dir
VARIANT_PACKS: dict[str, str] = {
    "nvidia": "RVCMAX_Nvidia_xiaoyuan",
    "amd": "RVCMAX_AMD_xiaoyuan",
    "nvidia50": "RVCMAX_Nvidia50x0_xiaoyuan",
}


def log(msg: str) -> None:
    print(msg, flush=True)


def must_exist(p: Path, label: str) -> None:
    if not p.exists():
        raise FileNotFoundError(
            f"missing {label}: {p}\n"
            f"Place RVCMAX packs under: {RVCMAX_ROOT}"
        )


def pack_root(variant: str) -> Path:
    name = VARIANT_PACKS.get(variant, VARIANT_PACKS["nvidia"])
    return RVCMAX_ROOT / name


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_file() and dst.stat().st_size == src.stat().st_size:
        log(f"  skip (same size): {dst.relative_to(REPO)}")
        return
    shutil.copy2(src, dst)
    log(f"  copy: {src.name} -> {dst.relative_to(REPO)} ({src.stat().st_size // 1024} KB)")


def _core_for_weights(primary: Path) -> Path:
    """Use primary pack RVC_Core; fall back to other variants for hubert/rmvpe."""
    c = primary / "RVC_Core"
    if c.is_dir():
        return c
    for v in ("nvidia", "amd", "nvidia50"):
        alt = pack_root(v) / "RVC_Core"
        if alt.is_dir():
            return alt
    return c


def sync_engine_weights(variant: str) -> None:
    core = _core_for_weights(pack_root(variant))
    log(f"[assets] hubert / rmvpe from {core}")
    hubert = core / "assets" / "hubert" / "hubert_base.pt"
    rmvpe_pt = core / "assets" / "rmvpe" / "rmvpe.pt"
    if hubert.is_file():
        copy_file(hubert, REPO / "assets" / "hubert" / "hubert_base.pt")
    else:
        log(f"  missing hubert: {hubert}")
    for name in ("rmvpe.pt", "rmvpe.onnx", "rmvpe_inputs.pth"):
        src = core / "assets" / "rmvpe" / name
        if src.is_file():
            copy_file(src, REPO / "assets" / "rmvpe" / name)
    if not rmvpe_pt.is_file():
        log("  warning: rmvpe.pt missing")


def sync_ffmpeg(variant: str) -> None:
    core = _core_for_weights(pack_root(variant))
    log(f"[ffmpeg] from {core.parent.name}")
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        src = core / name
        if src.is_file():
            copy_file(src, REPO / name)
        else:
            log(f"  missing optional: {name}")


def sync_models(variant: str) -> None:
    models = pack_root(variant) / "User_Data" / "models"
    log(f"[models] User_Data/models from {pack_root(variant).name}")
    if not models.is_dir():
        # fall back to nvidia pack models
        models = pack_root("nvidia") / "User_Data" / "models"
        log(f"  fallback models: {models}")
    if not models.is_dir():
        log("  no models dir, skip")
        return
    dst = REPO / "User_Data" / "models"
    dst.mkdir(parents=True, exist_ok=True)
    for child in models.iterdir():
        if not child.is_dir():
            continue
        target = dst / child.name
        if target.exists():
            if not any(target.glob("*.pth")):
                shutil.rmtree(target)
            else:
                log(f"  keep existing: models/{child.name}")
                continue
        shutil.copytree(child, target)
        log(f"  model folder: {child.name}")


def sync_vbcable(variant: str) -> None:
    src = pack_root(variant) / "VBCABLE"
    if not src.is_dir() or not any(src.glob("*.exe")):
        src = pack_root("nvidia") / "VBCABLE"
    log(f"[VBCABLE] from {src}")
    if not src.is_dir():
        log("  missing VBCABLE")
        return
    dst = REPO / "VBCABLE"
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.is_file():
            copy_file(f, dst / f.name)


def _remove_runtime_dst(dst: Path) -> None:
    if not (dst.is_dir() or dst.is_symlink() or dst.is_junction()):
        return
    log(f"[Runtime] remove existing: {dst}")
    if dst.is_junction() or dst.is_symlink():
        dst.unlink()
    else:
        # Real directory — only remove if empty placeholder or forced later
        shutil.rmtree(dst)


def link_or_copy_runtime(variant: str, *, copy: bool, force: bool) -> None:
    ref_rt = pack_root(variant) / "Runtime"
    must_exist(ref_rt / "python.exe", f"{variant} Runtime/python.exe")
    dst = REPO / "Runtime"

    if (dst / "python.exe").is_file() and not force and not copy:
        # Re-point junction if force not set: still allow refresh when force
        log(f"[Runtime] already present: {dst} (use --force-runtime to re-link)")
        return

    if dst.is_dir() or dst.is_symlink() or dst.is_junction():
        _remove_runtime_dst(dst)

    if copy:
        log(f"[Runtime] robocopy {ref_rt} -> {dst} (large)")
        dst.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            rc = subprocess.call(
                [
                    "robocopy",
                    str(ref_rt),
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
            shutil.copytree(ref_rt, dst)
    else:
        log(f"[Runtime] junction {dst} -> {ref_rt}")
        if sys.platform != "win32":
            os.symlink(ref_rt, dst, target_is_directory=True)
        else:
            rc = subprocess.call(
                ["cmd", "/c", "mklink", "/J", str(dst), str(ref_rt)],
                shell=False,
            )
            if rc != 0 or not (dst / "python.exe").is_file():
                raise RuntimeError(
                    "mklink /J failed (need admin? or path). "
                    "Retry with --copy-runtime"
                )
    log(f"  ok python: {(dst / 'python.exe').is_file()}")


def write_dev_variant(variant: str) -> None:
    """Remember selected pack for scripts/dev/_env.bat."""
    ud = REPO / "User_Data"
    ud.mkdir(parents=True, exist_ok=True)
    path = ud / "dev_variant.txt"
    path.write_text(variant.strip() + "\n", encoding="utf-8")
    log(f"[dev] wrote {path.relative_to(REPO)} = {variant}")


def verify() -> list[str]:
    needed = [
        REPO / "Runtime" / "python.exe",
        REPO / "Runtime" / "pythonw.exe",
        REPO / "assets" / "hubert" / "hubert_base.pt",
        REPO / "assets" / "rmvpe" / "rmvpe.pt",
        REPO / "ffmpeg.exe",
    ]
    missing = [str(p) for p in needed if not p.is_file()]
    # rmvpe.onnx strongly recommended for AMD/DML
    if not (REPO / "assets" / "rmvpe" / "rmvpe.onnx").is_file():
        missing.append("assets/rmvpe/rmvpe.onnx (recommended for AMD/DML F0)")
    models = (
        list((REPO / "User_Data" / "models").glob("*/*.pth"))
        if (REPO / "User_Data" / "models").is_dir()
        else []
    )
    if not models:
        missing.append("User_Data/models/*/*.pth (no voice model)")
    return missing


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Sync hubert/rmvpe/Runtime junction from local RVCMAX packs"
    )
    ap.add_argument(
        "--variant",
        choices=list(VARIANT_PACKS.keys()),
        default="nvidia",
        help="Which RVCMAX pack Runtime to junction (default: nvidia)",
    )
    ap.add_argument(
        "--copy-runtime",
        action="store_true",
        help="full copy Runtime instead of junction (for shipping offline copy)",
    )
    ap.add_argument(
        "--force-runtime",
        action="store_true",
        help="re-create Runtime junction even if already present",
    )
    ap.add_argument("--skip-runtime", action="store_true")
    ap.add_argument("--skip-models", action="store_true")
    args = ap.parse_args()
    variant = str(args.variant or "nvidia")

    root = pack_root(variant)
    must_exist(root, f"RVCMAX pack ({variant})")
    log(f"=== sync variant={variant} pack={root.name} ===")

    sync_engine_weights(variant)
    sync_ffmpeg(variant)
    if not args.skip_models:
        sync_models(variant)
    sync_vbcable(variant)
    if not args.skip_runtime:
        link_or_copy_runtime(
            variant, copy=args.copy_runtime, force=args.force_runtime
        )
    write_dev_variant(variant)

    missing = verify()
    # treat rmvpe.onnx as soft if only that missing for nvidia (still warn)
    hard = [m for m in missing if "rmvpe.onnx" not in m]
    if hard:
        log("[verify] MISSING:")
        for m in hard:
            log(f"  - {m}")
        for m in missing:
            if m not in hard:
                log(f"  (soft) {m}")
        return 1
    for m in missing:
        log(f"[verify] soft: {m}")
    log("[verify] OK — bat can use Runtime\\python.exe without system install")
    log(f"  variant={variant}  try: start.bat  or  scripts\\dev\\go-web.bat")
    if variant == "amd":
        log("  AMD: use scripts\\dev\\go-web-dml.bat / go-realtime-gui-dml.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
