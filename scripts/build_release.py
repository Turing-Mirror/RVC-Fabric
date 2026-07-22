# -*- coding: utf-8 -*-
"""
One-click release packer for RVC Fabric.

Builds a RVCMAX-style tree::

    dist/TuringMirror_Voice/   # pack folder name (legacy script id)
      启动器.exe          first-run helper (exe)
      变声器.exe          daily app (UI title: RVC Fabric)
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
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "dist" / "TuringMirror_Voice"
REF = REPO / "RVCMAX" / "RVCMAX_Nvidia_xiaoyuan"
RVCMAX_ROOT = REPO / "RVCMAX"

# Official-style multi-pack: each variant = full tree + its own Runtime
# prefer_dir = local RVCMAX folder name (exact). name_keys = fallback scan.
# exclude_keys = directory names that must NOT match (nvidia vs nvidia50).
VARIANTS: dict[str, dict] = {
    "nvidia": {
        "out_name": "TuringMirror_Voice_Nvidia",
        "accel_default": "cuda",
        "label": "NVIDIA CUDA",
        "name_keys": ("nvidia", "n卡", "cuda"),
        "prefer_dir": "RVCMAX_Nvidia_xiaoyuan",
        "exclude_keys": ("50", "5xxx", "50x0", "blackwell"),
    },
    "amd": {
        "out_name": "TuringMirror_Voice_AMD",
        "accel_default": "dml",
        "label": "AMD/Intel DirectML",
        "name_keys": ("amd", "dml", "a卡", "intel", "directml"),
        "prefer_dir": "RVCMAX_AMD_xiaoyuan",
        "exclude_keys": (),
    },
    "nvidia50": {
        "out_name": "TuringMirror_Voice_Nvidia50",
        "accel_default": "cuda",
        "label": "NVIDIA 50-series CUDA",
        "name_keys": ("50", "5xxx", "rtx50", "50x0", "blackwell"),
        "prefer_dir": "RVCMAX_Nvidia50x0_xiaoyuan",
        "exclude_keys": (),
    },
}

# Substrings that mark a 50-series pack (shared helper for tests)
SERIES50_KEYS = ("50", "5xxx", "50x0", "rtx50", "blackwell")

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


def ensure_shell_download_deps() -> None:
    """打包机安装壳层联网/封面依赖，打进 启动器.exe / 变声器.exe。

    用户机无需系统 Python。缺 requests → 补全 Runtime 失败；缺 Pillow → 社区封面空白。
    """
    need: list[str] = []
    try:
        import requests  # noqa: F401
        import certifi  # noqa: F401
    except ImportError:
        need.extend(["requests", "certifi"])
    try:
        import PIL  # noqa: F401
    except ImportError:
        need.append("Pillow")
    if need:
        log(f"[deps] pip install {' '.join(need)} (for frozen shell exes)")
        run([sys.executable, "-m", "pip", "install", "-U", *need])
    else:
        log("[deps] requests/certifi/Pillow ok (will bundle into shell exes)")


def build_exes(out: Path) -> None:
    ensure_pyinstaller()
    ensure_shell_download_deps()
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
                "--hidden-import",
                "requests",
                "--hidden-import",
                "urllib3",
                "--hidden-import",
                "certifi",
                "--hidden-import",
                "charset_normalizer",
                "--hidden-import",
                "idna",
                "--hidden-import",
                "launcher.online.downloader",
                "--hidden-import",
                "launcher.runtime_provision",
                "--hidden-import",
                "launcher.cnb_sources",
                "--hidden-import",
                "PIL",
                "--hidden-import",
                "PIL.Image",
                "--hidden-import",
                "PIL.ImageTk",
                "--collect-all",
                "certifi",
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


def _rvc_core_candidates() -> list[Path]:
    """Prefer N-card core, then AMD / 50-series cores for hubert/rmvpe/ffmpeg."""
    cores: list[Path] = []
    for name in (
        "RVCMAX_Nvidia_xiaoyuan",
        "RVCMAX_AMD_xiaoyuan",
        "RVCMAX_Nvidia50x0_xiaoyuan",
    ):
        p = RVCMAX_ROOT / name / "RVC_Core"
        if p.is_dir():
            cores.append(p)
    return cores


def merge_rvcmax_engine_bits(out: Path) -> None:
    """Fill hubert/rmvpe/ffmpeg from local RVCMAX packs (no network).

    Always try to ship both rmvpe.pt and rmvpe.onnx (AMD/DML needs onnx for F0).
    """
    cores = _rvc_core_candidates()
    if not cores:
        log("[merge] no RVCMAX RVC_Core — ensure hubert/rmvpe already in out/assets")
        return
    log("[merge] hubert / rmvpe / ffmpeg from RVCMAX (multi-core fallback)")

    def _cf_first(rel: str, dst: Path) -> None:
        for core in cores:
            src = core / rel
            if not src.is_file():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.is_file() and dst.stat().st_size == src.stat().st_size:
                log(f"  skip: {dst.relative_to(out)}")
                return
            shutil.copy2(src, dst)
            log(f"  + {dst.relative_to(out)} ({src.stat().st_size // 1024 // 1024} MB) from {core.parent.name}")
            return
        log(f"  missing: {rel}")

    _cf_first("assets/hubert/hubert_base.pt", out / "assets" / "hubert" / "hubert_base.pt")
    for n in ("rmvpe.pt", "rmvpe.onnx"):
        _cf_first(f"assets/rmvpe/{n}", out / "assets" / "rmvpe" / n)
    for n in ("ffmpeg.exe", "ffprobe.exe"):
        _cf_first(n, out / n)


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


def write_readme(out: Path, *, variant: str = "nvidia", label: str = "NVIDIA CUDA") -> None:
    accel_line = {
        "nvidia": "本包为 NVIDIA CUDA（对齐官方 N 卡整合包）。",
        "amd": (
            "本包为 AMD/Intel DirectML（对齐官方 A/I 卡整合包 + --dml）。\n"
            "请勿与 N 卡 Runtime 混用。默认走 DirectML，勿强行改 cuda。"
        ),
        "nvidia50": "本包为 NVIDIA 50 系适配 CUDA Runtime（参考 RVCMAX 50 系包）。",
    }.get(variant, f"加速变体：{label}")
    text = f"""RVC Fabric — 发行版（{label}）
================================

【用户只需要】
1. 解压到英文路径（推荐 D:\\RVC_Fabric\\）
2. 双击「启动器.exe」（或 TM_Setup.exe）
3. 点「发送快捷方式」「安装虚拟声卡」
4. 之后双击桌面图标或主界面「变声器.exe」（界面标题为 RVC Fabric）

【显卡说明 — 与官方 RVC 一致】
{accel_line}
官方 Windows：
  · N 卡 = 单独 CUDA 环境（requirements / Nvidia 7z）
  · A/I 卡 = 单独 DirectML 环境（requirements-dml / AMD_Intel 7z）+ 启动 --dml
不是「同一个 Runtime 只加一个参数」；参数只在正确环境里切换设备。

【已内置】
- Runtime\\     本变体专用绿色 Python（无需自装 Python）
- package_meta.json  标记本包变体与默认加速
- User_Data\\models\\  预置音色（若打包时带了）
- VBCABLE\\     虚拟声卡安装包
- 引擎与界面（含 rmvpe.pt / rmvpe.onnx）

【不要用】
- tools\\dev\\ 下的 .bat 仅供开发调试
- 不要把 N 卡包 Runtime 拷进 A 卡包混用

打包时间: {time.strftime("%Y-%m-%d %H:%M:%S")}
变体: {variant}
"""
    (out / "使用说明.txt").write_text(text, encoding="utf-8")
    log("[doc] 使用说明.txt")


def pack_dir_matches(
    dir_name: str,
    *,
    name_keys: tuple[str, ...],
    exclude_keys: tuple[str, ...] = (),
) -> bool:
    """Return True if folder name matches include keys and none of exclude keys."""
    name = (dir_name or "").lower()
    if not name:
        return False
    keys = tuple(k.lower() for k in name_keys if k)
    excludes = tuple(k.lower() for k in exclude_keys if k)
    if excludes and any(ex in name for ex in excludes):
        return False
    if not keys:
        return False
    return any(k in name for k in keys)


def find_rvcmax_pack_dir(
    name_keys: tuple[str, ...],
    prefer_dir: str = "",
    *,
    exclude_keys: tuple[str, ...] = (),
    rvcmax_root: Path | None = None,
) -> Path | None:
    """Find RVCMAX/<pack>/ that matches keywords and has Runtime/python.exe.

    Order: prefer_dir (exact) → scan by name_keys with exclude_keys filter.
    ``rvcmax_root`` is injectable for unit tests.
    """
    root = rvcmax_root if rvcmax_root is not None else RVCMAX_ROOT
    if prefer_dir:
        p = root / prefer_dir
        if (p / "Runtime" / "python.exe").is_file():
            return p
    if not root.is_dir():
        return None
    for child in sorted(root.iterdir(), key=lambda x: x.name.lower()):
        if not child.is_dir():
            continue
        if not pack_dir_matches(
            child.name, name_keys=name_keys, exclude_keys=exclude_keys
        ):
            continue
        if (child / "Runtime" / "python.exe").is_file():
            return child
    return None


def find_pack_for_variant(
    variant: str, *, rvcmax_root: Path | None = None
) -> Path | None:
    """Resolve RVCMAX pack directory for a shipping variant."""
    info = VARIANTS.get(variant, VARIANTS["nvidia"])
    return find_rvcmax_pack_dir(
        tuple(info.get("name_keys") or ()),
        str(info.get("prefer_dir") or ""),
        exclude_keys=tuple(info.get("exclude_keys") or ()),
        rvcmax_root=rvcmax_root,
    )


def default_runtime(variant: str = "nvidia") -> Path | None:
    env = os.environ.get("TM_RUNTIME_SRC", "")
    if env and (Path(env) / "python.exe").is_file():
        return Path(env)
    pack = find_pack_for_variant(variant)
    if pack and (pack / "Runtime" / "python.exe").is_file():
        return pack / "Runtime"
    # Do NOT fall back to REPO/Runtime: dev trees often junction AMD/50 Runtime there.
    # Only accept the canonical prefer_dir pack or REF for nvidia.
    if variant == "nvidia":
        ref_rt = REF / "Runtime"
        if (ref_rt / "python.exe").is_file():
            return ref_rt
    return None


def default_models(variant: str = "nvidia") -> Path | None:
    env = os.environ.get("TM_MODELS_SRC", "")
    if env and Path(env).is_dir():
        return Path(env)
    pack = find_pack_for_variant(variant)
    if pack and (pack / "User_Data" / "models").is_dir():
        return pack / "User_Data" / "models"
    for p in (REF / "User_Data" / "models", REPO / "User_Data" / "models"):
        if p.is_dir():
            return p
    return None


def default_vbcable(variant: str = "nvidia") -> Path | None:
    pack = find_pack_for_variant(variant)
    if pack and (pack / "VBCABLE").is_dir() and any((pack / "VBCABLE").glob("*.exe")):
        return pack / "VBCABLE"
    for p in (REF / "VBCABLE", REPO / "VBCABLE"):
        if p.is_dir() and any(p.glob("*.exe")):
            return p
    return REPO / "VBCABLE" if (REPO / "VBCABLE").is_dir() else None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build Turing Mirror Voice release pack (official multi-pack ready)"
    )
    p.add_argument(
        "--variant",
        choices=list(VARIANTS.keys()),
        default="nvidia",
        help="nvidia | amd | nvidia50 — full separate packs like official RVC",
    )
    p.add_argument("--out", type=Path, default=None, help="output directory")
    p.add_argument("--runtime", type=Path, default=None, help="Runtime source dir")
    p.add_argument("--models", type=Path, default=None, help="models source dir")
    p.add_argument("--vbcable", type=Path, default=None, help="VBCABLE source dir")
    p.add_argument("--skip-exe", action="store_true", help="do not run PyInstaller")
    p.add_argument("--skip-runtime", action="store_true", help="do not copy Runtime")
    p.add_argument("--clean", action="store_true", help="wipe out dir first")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    variant = str(args.variant or "nvidia")
    vinfo = VARIANTS[variant]
    if args.out is None:
        out = (REPO / "dist" / vinfo["out_name"]).resolve()
    else:
        out = args.out.resolve()
    log(f"=== build release variant={variant} -> {out} ===")
    log(f"    label={vinfo['label']} accel_default={vinfo['accel_default']}")

    if args.clean and out.exists():
        log("[clean] remove old out")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # 1) engine
    copy_engine(out)

    # 2) runtime (full pack must ship correct green env — not flag-only)
    if args.skip_runtime:
        copy_runtime(out, None)
    else:
        rt = args.runtime or default_runtime(variant)
        if rt is None:
            log(
                f"[runtime] WARNING: no Runtime for variant={variant}. "
                "Put RVCMAX pack under RVCMAX/ or pass --runtime PATH."
            )
            if variant != "nvidia":
                log(
                    "[runtime] AMD/50-series pack CANNOT be faked by only setting --dml. "
                    "Need the matching Runtime (official AMD_Intel / RVCMAX A-card pack)."
                )
            copy_runtime(out, None)
        else:
            copy_runtime(out, rt)

    # 3) models
    copy_models(out, args.models or default_models(variant))

    # 4) vbcable
    copy_vbcable(out, args.vbcable or default_vbcable(variant))

    # 5) package identity (official multi-pack)
    try:
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from launcher.package_meta import write_package_meta

        write_package_meta(
            out,
            variant,
            label=vinfo["label"],
            accel_default=vinfo["accel_default"],
            use_dml=bool(vinfo["accel_default"] == "dml"),
        )
        log(f"[meta] package_meta.json variant={variant}")
    except Exception as e:
        # Fallback: write meta without importing launcher (path issues)
        log(f"[meta] import write_package_meta failed ({e}); writing JSON fallback")
        meta = {
            "variant": variant,
            "label": vinfo["label"],
            "accel_default": vinfo["accel_default"],
            "use_dml": bool(vinfo["accel_default"] == "dml"),
            "tagged": True,
        }
        (out / "package_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"[meta] package_meta.json variant={variant} (fallback)")

    # Seed default app config accel for first launch
    try:
        ud = out / "User_Data"
        ud.mkdir(parents=True, exist_ok=True)
        cfg_path = ud / "app_config.json"
        if not cfg_path.is_file():
            seed = {
                "accel_backend": vinfo["accel_default"],
                "pitch": 0,
                "f0method": "fcpe",
            }
            cfg_path.write_text(
                json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            log(f"[meta] seed User_Data/app_config.json accel={vinfo['accel_default']}")
    except Exception as e:
        log(f"[meta] seed config skip: {e}")

    # 6) exes into out root
    if not args.skip_exe:
        try:
            build_exes(out)
        except Exception as e:
            log(f"[exe] FAILED: {e}")
            log("  You can re-run without --skip-exe after fixing PyInstaller.")
            return 1
    else:
        log("[exe] skipped")

    write_readme(out, variant=variant, label=str(vinfo["label"]))

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
        "package_meta.json",
    ):
        p = out / name
        mark = "OK" if (p.is_file() or p.is_dir()) else "MISSING"
        log(f"  [{mark}] {name}")
    if not (out / "Runtime" / "python.exe").is_file():
        log("[WARN] Runtime incomplete — do not ship this folder to users yet.")
    log("User path: unzip -> double-click 启动器.exe or TM_Setup.exe (no bat).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
