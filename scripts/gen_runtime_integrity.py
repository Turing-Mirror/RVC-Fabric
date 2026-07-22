# -*- coding: utf-8 -*-
"""Generate Runtime integrity JSON for CNB (Steam-like file list + import list).

Example::

    python scripts/gen_runtime_integrity.py ^
      --runtime RVCMAX/RVCMAX_Nvidia_xiaoyuan/Runtime ^
      --variant nvidia --version 2026.07.21 ^
      --out CNB-GIT-RELEASE/runtime/nvidia/integrity-2026.07.21.json

Also writes integrity.json (latest alias) next to the versioned file when --alias.

Upload the JSON to CNB git (small text, no LFS). Launcher fetches::

    …/raw/main/runtime/<variant>/integrity-<version>.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Critical relative paths under Runtime/ (size always; sha256 if <= max_hash_mb)
CRITICAL = [
    "python.exe",
    "pythonw.exe",
    "python39.dll",
    "python3.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "Lib/site-packages/torch/__init__.py",
    "Lib/site-packages/torch/version.py",
    "Lib/site-packages/numpy/__init__.py",
    "Lib/site-packages/sounddevice/__init__.py",
    "Lib/site-packages/librosa/__init__.py",
    "Lib/site-packages/FreeSimpleGUI/__init__.py",
    "Lib/site-packages/faiss/__init__.py",
    "Lib/site-packages/cv2/__init__.py",
    "Lib/site-packages/torchaudio/__init__.py",
]

# Optional CUDA-ish binaries — size only if present
OPTIONAL_GLOBS = [
    "Lib/site-packages/torch/lib/torch_cuda*.dll",
    "Lib/site-packages/torch/lib/c10_cuda.dll",
    "Lib/site-packages/torch/lib/cudnn*.dll",
    "Lib/site-packages/torch_directml/**/*.pyd",
]

IMPORTS = [
    "torch",
    "numpy",
    "sounddevice",
    "librosa",
    "FreeSimpleGUI",
    "faiss",
    "torchaudio",
]


def _sha256(path: Path, limit: int) -> str | None:
    if path.stat().st_size > limit:
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _add_file(rt: Path, rel: str, files: list, *, max_hash: int, seen: set) -> None:
    rel_n = rel.replace("\\", "/")
    if rel_n in seen:
        return
    p = rt / Path(rel)
    if not p.is_file():
        return
    seen.add(rel_n)
    rec = {"path": rel_n, "size": int(p.stat().st_size), "required": True}
    dig = _sha256(p, max_hash)
    if dig:
        rec["sha256"] = dig
    files.append(rec)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate Runtime integrity JSON for CNB")
    ap.add_argument("--runtime", required=True, help="Path to Runtime directory")
    ap.add_argument("--variant", required=True, choices=("nvidia", "amd", "nvidia50"))
    ap.add_argument("--version", required=True, help="e.g. 2026.07.21")
    ap.add_argument("--out", required=True, help="Output JSON path")
    ap.add_argument("--alias", action="store_true", help="Also write integrity.json")
    ap.add_argument(
        "--max-hash-mb",
        type=int,
        default=8,
        help="Only sha256 files smaller than this (default 8MB)",
    )
    args = ap.parse_args()

    rt = Path(args.runtime)
    if not rt.is_dir():
        print(f"Runtime not found: {rt}", file=sys.stderr)
        return 1
    if not (rt / "python.exe").is_file():
        print(f"python.exe missing under {rt}", file=sys.stderr)
        return 1

    max_hash = int(args.max_hash_mb) * 1024 * 1024
    files: list[dict] = []
    seen: set[str] = set()
    for rel in CRITICAL:
        _add_file(rt, rel, files, max_hash=max_hash, seen=seen)

    # optional globs
    for pattern in OPTIONAL_GLOBS:
        for p in rt.glob(pattern):
            if p.is_file():
                rel = p.relative_to(rt).as_posix()
                if rel in seen:
                    continue
                seen.add(rel)
                rec = {
                    "path": rel,
                    "size": int(p.stat().st_size),
                    "required": False,
                }
                dig = _sha256(p, max_hash)
                if dig:
                    rec["sha256"] = dig
                files.append(rec)

    files.sort(key=lambda x: x["path"])
    doc = {
        "schema": 1,
        "format": "rvc_fabric_runtime_integrity",
        "variant": args.variant,
        "runtime_version": args.version,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "product": "RVC Fabric",
        "notes": "Launcher compares local Runtime files + import smoke test",
        "files": files,
        "imports": IMPORTS,
        "expect_cuda": args.variant in ("nvidia", "nvidia50"),
        "expect_dml": args.variant == "amd",
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(files)} files)")

    if args.alias:
        alias = out.parent / "integrity.json"
        alias.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Wrote {alias}")

    # optional copy into product configs for offline fallback
    bundled = REPO / "configs" / "runtime_integrity" / f"{args.variant}.json"
    bundled.parent.mkdir(parents=True, exist_ok=True)
    bundled.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Bundled fallback: {bundled}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
