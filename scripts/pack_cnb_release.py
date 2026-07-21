# -*- coding: utf-8 -*-
"""Pack Runtime / voice artifacts into CNB-GIT-RELEASE for CNB Git LFS push.

Staging root (gitignored in product repo)::

    CNB-GIT-RELEASE/
      runtime/<variant>/runtime-<variant>-<ver>.7z
      voices/<id>/<id>-v<ver>.zip
      catalog/online_catalog.snippet.json
      manifest.json

CNB remote (releases only)::

    https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases

Examples (from product repo root)::

    python scripts/pack_cnb_release.py --init-layout
    python scripts/pack_cnb_release.py --runtime nvidia
    python scripts/pack_cnb_release.py --runtime all
    python scripts/pack_cnb_release.py --voices
    python scripts/pack_cnb_release.py --runtime all --voices --write-manifest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_OUT = ROOT / "CNB-GIT-RELEASE"
RVCMAX = ROOT / "RVCMAX"

# Prefer RVCMAX reference packs; fall back to repo Runtime junction
VARIANT_SOURCES: dict[str, dict[str, Any]] = {
    "nvidia": {
        "prefer": RVCMAX / "RVCMAX_Nvidia_xiaoyuan" / "Runtime",
        "label": "NVIDIA CUDA",
    },
    "amd": {
        "prefer": RVCMAX / "RVCMAX_AMD_xiaoyuan" / "Runtime",
        "label": "AMD/Intel DirectML",
    },
    "nvidia50": {
        "prefer": RVCMAX / "RVCMAX_Nvidia50x0_xiaoyuan" / "Runtime",
        "label": "NVIDIA 50-series CUDA",
    },
}

SEVEN_Z_CANDIDATES = (
    Path(r"C:\Program Files\7-Zip-Zstandard\7z.exe"),
    Path(r"C:\Program Files\7-Zip\7z.exe"),
    Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
)


def log(msg: str) -> None:
    print(msg, flush=True)


def find_7z() -> Path:
    env = os.environ.get("SEVEN_Z") or os.environ.get("SEVENZ")
    if env and Path(env).is_file():
        return Path(env)
    for p in SEVEN_Z_CANDIDATES:
        if p.is_file():
            return p
    which = shutil.which("7z") or shutil.which("7z.exe")
    if which:
        return Path(which)
    raise FileNotFoundError(
        "未找到 7z.exe。请安装 7-Zip，或设置环境变量 SEVEN_Z 指向 7z.exe"
    )


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def write_sha256_sidecar(path: Path) -> str:
    digest = sha256_file(path)
    side = path.with_suffix(path.suffix + ".sha256")
    # format: <hex>  <filename>
    side.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def init_layout(out: Path) -> None:
    for rel in (
        "runtime/nvidia",
        "runtime/amd",
        "runtime/nvidia50",
        "voices",
        "catalog",
        "assets/core",
        "setup",
    ):
        (out / rel).mkdir(parents=True, exist_ok=True)

    readme = out / "README.md"
    if not readme.is_file():
        readme.write_text(
            _README_MD,
            encoding="utf-8",
        )

    sync = out / "SYNC_COMMANDS.txt"
    if not sync.is_file():
        sync.write_text(_SYNC_TXT, encoding="utf-8")

    gitattributes = out / ".gitattributes"
    if not gitattributes.is_file():
        gitattributes.write_text(_GITATTRIBUTES, encoding="utf-8")

    # keep example if present
    example = out / "example.txt"
    if not example.is_file():
        example.write_text(
            "裸库镜像迁移示例见 SYNC_COMMANDS.txt（推荐从本目录直接 push 到 CNB）。\n",
            encoding="utf-8",
        )

    log(f"layout ready: {out}")


def resolve_runtime_dir(variant: str) -> Path:
    meta = VARIANT_SOURCES[variant]
    prefer: Path = meta["prefer"]
    if prefer.is_dir() and (prefer / "python.exe").is_file():
        return prefer
    # junction / local Runtime only valid for current synced variant
    local = ROOT / "Runtime"
    if local.is_dir() and (local / "python.exe").is_file() and variant == "nvidia":
        return local
    raise FileNotFoundError(
        f"找不到 {variant} 的 Runtime（期望 {prefer} 或已 sync 的 Runtime）"
    )


def _split_file(path: Path, volume_bytes: int) -> list[Path]:
    """Split *path* into path.001, path.002, … and remove original."""
    if volume_bytes <= 0 or path.stat().st_size <= volume_bytes:
        return [path]
    parts: list[Path] = []
    idx = 1
    with path.open("rb") as src:
        while True:
            chunk = src.read(volume_bytes)
            if not chunk:
                break
            part = path.with_name(f"{path.name}.{idx:03d}")
            part.write_bytes(chunk)
            parts.append(part)
            idx += 1
    path.unlink(missing_ok=True)
    return parts


def pack_runtime(
    variant: str,
    out: Path,
    *,
    version: str,
    volume_mib: int = 0,
    mx: int = 3,
    fmt: str = "tar",
) -> dict[str, Any]:
    """Pack green Runtime.

    *fmt*:
      - ``tar`` (default): Windows ``tar``/bsdtar — reliable on long paths
      - ``7z``: 7-Zip (may fail on some 7-Zip-Zstandard builds / long paths)
    """
    src = resolve_runtime_dir(variant)
    dest_dir = out / "runtime" / variant
    dest_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"runtime-{variant}-{version}"
    for old in dest_dir.glob(f"{base_name}*"):
        if old.is_file():
            old.unlink()

    parent = src.parent
    folder_name = src.name  # usually "Runtime"
    fmt = (fmt or "tar").strip().lower()
    t0 = time.time()

    if fmt == "7z":
        seven = find_7z()
        archive = dest_dir / f"{base_name}.7z"
        cmd = [
            str(seven),
            "a",
            "-t7z",
            f"-mx={mx}",
            "-mmt=on",
            "-bsp1",
            str(archive),
            folder_name,
        ]
        log(f"[runtime/{variant}] packing {src} -> {archive} (7z mx={mx})")
        r = subprocess.run(cmd, cwd=str(parent), capture_output=False)
        if r.returncode != 0:
            raise RuntimeError(
                f"7z failed for {variant} code={r.returncode}; try --format tar"
            )
        format_label = "7z"
    else:
        # Prefer tar: works with long paths; extract: tar xf xxx.tar → Runtime/
        archive = dest_dir / f"{base_name}.tar"
        tar_exe = shutil.which("tar") or "tar"
        cmd = [tar_exe, "-cf", str(archive), folder_name]
        log(f"[runtime/{variant}] packing {src} -> {archive} (tar)")
        r = subprocess.run(cmd, cwd=str(parent), capture_output=False)
        if r.returncode != 0 or not archive.is_file():
            raise RuntimeError(f"tar failed for {variant} code={r.returncode}")
        format_label = "tar"

    volume_bytes = int(volume_mib) * 1024 * 1024 if volume_mib and volume_mib > 0 else 0
    files = _split_file(archive, volume_bytes) if volume_bytes else [archive]

    parts: list[dict[str, Any]] = []
    for p in files:
        digest = write_sha256_sidecar(p)
        parts.append(
            {
                "name": p.name,
                "path": str(p.relative_to(out)).replace("\\", "/"),
                "size_bytes": p.stat().st_size,
                "sha256": digest,
            }
        )
    total = sum(x["size_bytes"] for x in parts)
    if len(parts) > 1:
        format_label = f"{format_label}.split"

    elapsed = time.time() - t0
    log(
        f"[runtime/{variant}] done in {elapsed/60:.1f} min, "
        f"{total/1e9:.2f} GB, parts={len(parts)}"
    )
    return {
        "variant": variant,
        "label": VARIANT_SOURCES[variant]["label"],
        "version": version,
        "format": format_label,
        "extract_root": "Runtime",
        "extract_hint": "tar xf runtime-*.tar  (yields Runtime/ next to extract cwd)",
        "size_bytes": total,
        "parts": parts,
        "primary": parts[0]["path"],
        "source": str(src),
    }


def _load_voice_config(folder: Path) -> dict[str, Any]:
    cfg_path = folder / "config.json"
    if cfg_path.is_file():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def pack_voice_folder(
    folder: Path,
    out_root: Path,
    *,
    version: str = "1",
) -> Optional[dict[str, Any]]:
    from launcher.online.package_spec import PKG_VOICE_PACK, TM_PACKAGE_JSON, tm_package_template

    pths = list(folder.glob("*.pth"))
    if not pths:
        log(f"[voices] skip (no pth): {folder.name}")
        return None
    pth = pths[0]
    cfg = _load_voice_config(folder)
    vid = str(cfg.get("online_id") or "").strip()
    if not vid:
        # RVCMAX sample folders are often "1"/"2"; prefer stable pth stem
        if folder.name.isdigit() or len(folder.name) <= 2:
            vid = pth.stem
        else:
            vid = folder.name
    # safe-ish id for paths
    vid = "".join(c if c.isalnum() or c in "-_" else "_" for c in vid).strip("_") or pth.stem
    name = str(cfg.get("name") or vid)
    tag = str(cfg.get("tag") or "音色")
    ver = str(cfg.get("version") or version)

    out_dir = out_root / "voices" / vid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_zip = out_dir / f"{vid}-v{ver}.zip"
    if out_zip.is_file():
        out_zip.unlink()

    meta = tm_package_template(
        PKG_VOICE_PACK,
        name=name,
        version=ver,
        voice_id=vid,
        tag=tag,
        notes="CNB LFS voice pack",
    )
    # strip absolute cover paths from shipped config
    ship_cfg = {
        "name": name,
        "tag": tag,
        "version": ver,
        "file": pth.name,
    }
    for k in ("pitch", "formant", "index_rate", "rms_mix_rate", "threhold", "f0method"):
        if k in cfg:
            ship_cfg[k] = cfg[k]

    index = next(iter(folder.glob("*.index")), None)
    cover = None
    for cand in ("cover.png", "cover.jpg", "cover.jpeg", "cover.webp"):
        if (folder / cand).is_file():
            cover = folder / cand
            break
    if cover is None:
        for img in folder.glob("*.jpg"):
            cover = img
            break

    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(TM_PACKAGE_JSON, json.dumps(meta, ensure_ascii=False, indent=2))
        zf.writestr("config.json", json.dumps(ship_cfg, ensure_ascii=False, indent=2))
        zf.write(pth, pth.name)
        if index and index.is_file():
            zf.write(index, index.name)
        if cover and cover.is_file():
            ext = cover.suffix.lower() or ".jpg"
            zf.write(cover, f"cover{ext}")

    digest = write_sha256_sidecar(out_zip)
    rel = str(out_zip.relative_to(out_root)).replace("\\", "/")
    log(f"[voices] {vid} -> {rel} ({out_zip.stat().st_size} bytes)")
    return {
        "id": vid,
        "name": name,
        "tag": tag,
        "version": ver,
        "package_type": PKG_VOICE_PACK,
        "path": rel,
        "file": out_zip.name,
        "size_bytes": out_zip.stat().st_size,
        "sha256": digest,
        "has_index": bool(index and index.is_file()),
    }


def pack_all_voices(out: Path, models_dirs: list[Path]) -> list[dict[str, Any]]:
    (out / "voices").mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_pth: set[str] = set()  # basename of .pth — skip duplicate content
    for models in models_dirs:
        if not models.is_dir():
            continue
        for folder in sorted(models.iterdir()):
            if not folder.is_dir():
                continue
            if folder.name.startswith("."):
                continue
            pths = list(folder.glob("*.pth"))
            if pths and pths[0].name.lower() in seen_pth:
                log(f"[voices] skip duplicate pth {pths[0].name} in {folder}")
                continue
            info = pack_voice_folder(folder, out)
            if not info:
                continue
            if info["id"] in seen_ids:
                log(f"[voices] override duplicate id={info['id']} from {folder}")
                entries = [e for e in entries if e["id"] != info["id"]]
            seen_ids.add(info["id"])
            if pths:
                seen_pth.add(pths[0].name.lower())
            entries.append(info)
    return entries


def write_manifest(
    out: Path,
    *,
    runtimes: list[dict[str, Any]],
    voices: list[dict[str, Any]],
    version: str,
) -> Path:
    data = {
        "schema": 1,
        "product": "RVC-Fabric",
        "channel": "stable",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "bundle_version": version,
        "cnb_repo": "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases",
        "layout": {
            "runtime": "runtime/<variant>/",
            "voices": "voices/<id>/",
            "catalog": "catalog/",
            "setup": "setup/",
            "assets_core": "assets/core/",
        },
        "runtimes": {r["variant"]: r for r in runtimes},
        "voices": voices,
    }
    path = out / "manifest.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"wrote {path}")

    # catalog snippet for product online_catalog merge
    snippet = {
        "schema": 1,
        "note": "Merge into product configs/online_catalog.json or host as remote catalog",
        "cnb_repo": data["cnb_repo"],
        "runtimes": {},
        "voices": [],
    }
    for r in runtimes:
        parts_urls = []
        for p in r.get("parts") or []:
            # placeholder LFS raw/path style — publisher fills real CNB download URLs after push
            rel = p.get("path") or p.get("name")
            parts_urls.append(
                {
                    "name": p["name"],
                    "size_bytes": p["size_bytes"],
                    "sha256": p["sha256"],
                    "urls": [
                        f"https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main/{rel}",
                    ],
                }
            )
        snippet["runtimes"][r["variant"]] = {
            "version": r["version"],
            "variant": r["variant"],
            "label": r.get("label"),
            "format": r.get("format"),
            "size_bytes": r.get("size_bytes"),
            "extract_root": "Runtime",
            "parts": parts_urls,
        }
    for v in voices:
        snippet["voices"].append(
            {
                "id": v["id"],
                "name": v["name"],
                "tag": v.get("tag") or "音色",
                "version": v.get("version") or "1",
                "package_type": "voice_pack",
                "pack_url": f"https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main/{v['path']}",
                "sha256": v["sha256"],
                "size_bytes": v["size_bytes"],
                "description": f"{v['name']}（CNB LFS）",
            }
        )
    cat_path = out / "catalog" / "online_catalog.snippet.json"
    cat_path.parent.mkdir(parents=True, exist_ok=True)
    cat_path.write_text(json.dumps(snippet, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"wrote {cat_path}")
    return path


def load_existing_manifest(out: Path) -> dict[str, Any]:
    p = out / "manifest.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


_README_MD = """# RVC-Fabric-Releases（CNB 制品仓）

产品源码仓与本仓分离：

| 仓 | 用途 |
|----|------|
| 产品源码 | 代码 / 打包脚本 / 文档（不含多 GB Runtime） |
| **本仓** | Setup、Runtime 分卷、音色 zip、catalog 片段 — **Git LFS** |

远程：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases

## 目录

```
runtime/<variant>/     # nvidia | amd | nvidia50  绿色 Runtime tar（或 7z）
voices/<id>/           # 音色 voice_pack zip + .sha256
assets/core/           # hubert / rmvpe 等（可选）
setup/                 # 将来的 setup.exe
catalog/               # online_catalog 片段
manifest.json          # 本仓制品索引
```

解压 Runtime：`tar xf runtime-nvidia-<ver>.tar` → 目录 `Runtime/`。

## 从产品仓生成制品

在 **产品仓库根目录**：

```bat
python scripts/pack_cnb_release.py --init-layout
python scripts/pack_cnb_release.py --runtime all --voices --write-manifest
```

然后进入本目录，按 `SYNC_COMMANDS.txt` 推到 CNB（LFS）。

## 用户动线（产品侧）

Setup 安装壳与启动器 → 启动器按分版下载 Runtime → 进软件 → 新手指引 → 社区下音色 → 变声使用 → …
"""

_SYNC_TXT = """# CNB 制品仓同步命令（在 CNB-GIT-RELEASE 目录执行）
# 远程: https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases

# --- 首次：把本目录初始化为 git 仓并推到 CNB ---
git init
git lfs install
git lfs track "*.7z"
git lfs track "*.7z.*"
git lfs track "*.tar"
git lfs track "*.tar.*"
git lfs track "*.zip"
git lfs track "*.pth"
git lfs track "*.onnx"
git lfs track "*.pt"
git add .gitattributes
git add .
git commit -m "chore: initial runtime and voice artifacts"
git remote add origin https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases.git
git branch -M main
git push -u origin main

# --- 日常更新制品后 ---
git lfs install
git add runtime voices catalog manifest.json setup assets
git commit -m "chore: update release artifacts"
git push

# --- 若从其它 git 裸库整仓迁移到 CNB（官方示例风格）---
# mkdir empty && cd empty
# git clone --bare https://your-git.com/group/name.git .
# git lfs fetch origin --all
# git push --mirror https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases.git

# 说明：
# 1) 大文件必须走 Git LFS，否则 push 会失败或撑爆普通 git
# 2) Runtime 默认 tar：解压 tar xf runtime-xxx.tar → 得到 Runtime/ 目录
# 3) 推送后把 catalog/online_catalog.snippet.json 里的 raw URL 按 CNB 实际直链修正
# 4) 本目录在产品源码仓已 gitignore，勿提交进 RVC-Fabric 源码仓
"""

_GITATTRIBUTES = """# Git LFS — RVC-Fabric-Releases
*.7z filter=lfs diff=lfs merge=lfs -text
*.7z.* filter=lfs diff=lfs merge=lfs -text
*.tar filter=lfs diff=lfs merge=lfs -text
*.tar.* filter=lfs diff=lfs merge=lfs -text
*.zip filter=lfs diff=lfs merge=lfs -text
*.pth filter=lfs diff=lfs merge=lfs -text
*.pt filter=lfs diff=lfs merge=lfs -text
*.onnx filter=lfs diff=lfs merge=lfs -text
*.exe filter=lfs diff=lfs merge=lfs -text
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Pack CNB-GIT-RELEASE artifacts")
    ap.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Staging directory (default: CNB-GIT-RELEASE)",
    )
    ap.add_argument("--init-layout", action="store_true", help="Create folders + README/SYNC")
    ap.add_argument(
        "--runtime",
        default="",
        help="nvidia|amd|nvidia50|all — pack green Runtime 7z",
    )
    ap.add_argument("--voices", action="store_true", help="Pack User_Data/models (+ RVCMAX models)")
    ap.add_argument("--version", default="", help="Artifact version tag (default: date)")
    ap.add_argument(
        "--volume-mib",
        type=int,
        default=0,
        help="If >0, split archive into parts of this many MiB (e.g. 1536). 0=single file",
    )
    ap.add_argument("--mx", type=int, default=3, help="7z compression level 0-9 (only --format 7z)")
    ap.add_argument(
        "--format",
        default="tar",
        choices=("tar", "7z"),
        help="Archive format (default tar; 7z may fail on some Windows 7-Zip builds)",
    )
    ap.add_argument(
        "--write-manifest",
        action="store_true",
        help="Write/merge manifest.json and catalog snippet",
    )
    ap.add_argument(
        "--models-dir",
        action="append",
        default=[],
        help="Extra models dir (repeatable). Default: User_Data/models + RVCMAX nvidia models",
    )
    args = ap.parse_args()
    out = Path(args.out)
    version = (args.version or time.strftime("%Y.%m.%d")).strip()

    if args.init_layout or args.runtime or args.voices or args.write_manifest:
        init_layout(out)
    else:
        ap.print_help()
        return 0

    runtimes: list[dict[str, Any]] = []
    voices: list[dict[str, Any]] = []

    # merge previous manifest entries if only packing subset
    prev = load_existing_manifest(out)
    prev_runtimes = dict(prev.get("runtimes") or {})
    prev_voices = list(prev.get("voices") or [])

    if args.runtime:
        variants: list[str]
        key = args.runtime.strip().lower()
        if key == "all":
            variants = ["nvidia", "amd", "nvidia50"]
        else:
            if key not in VARIANT_SOURCES:
                log(f"unknown variant: {key}")
                return 2
            variants = [key]
        for v in variants:
            try:
                info = pack_runtime(
                    v,
                    out,
                    version=version,
                    volume_mib=int(args.volume_mib or 0),
                    mx=int(args.mx),
                    fmt=str(args.format or "tar"),
                )
                runtimes.append(info)
            except Exception as e:
                log(f"[runtime/{v}] ERROR: {e}")
                return 1

    if args.voices:
        models_dirs = [Path(p) for p in args.models_dir] if args.models_dir else []
        if not models_dirs:
            models_dirs = [
                ROOT / "User_Data" / "models",
                RVCMAX / "RVCMAX_Nvidia_xiaoyuan" / "User_Data" / "models",
            ]
        voices = pack_all_voices(out, models_dirs)

    if args.write_manifest or runtimes or voices:
        # merge
        rmap = dict(prev_runtimes)
        for r in runtimes:
            rmap[r["variant"]] = r
        vmap = {v["id"]: v for v in prev_voices if isinstance(v, dict) and v.get("id")}
        for v in voices:
            vmap[v["id"]] = v
        write_manifest(
            out,
            runtimes=list(rmap.values()),
            voices=list(vmap.values()),
            version=version,
        )

    log("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
