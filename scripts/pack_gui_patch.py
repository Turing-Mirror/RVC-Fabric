# -*- coding: utf-8 -*-
"""Build a gui_patch (incremental) zip for in-app updates.

Example::

    python scripts/pack_gui_patch.py --version 1.2.0 --out dist/gui_patch_1.2.0.zip

Includes launcher/, selected tools, configs/online_catalog.json, version.py path, etc.
Never packs Runtime/ or User_Data/.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from launcher.online.package_spec import PKG_GUI_PATCH, TM_PACKAGE_JSON, tm_package_template

# Relative paths or globs under ROOT
DEFAULT_PATHS = [
    "launcher",
    "configs/online_catalog.json",
    "tools/realtime_worker.py",
    "tools/dsp_fx.py",
    "tools/download_models.py",
    "gui_v1.py",
]


def _add_path(zf: zipfile.ZipFile, root: Path, rel: Path) -> int:
    full = root / rel
    n = 0
    if full.is_file():
        zf.write(full, rel.as_posix())
        return 1
    if full.is_dir():
        for f in full.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix == ".pyc" or "__pycache__" in f.parts:
                continue
            arc = f.relative_to(root).as_posix()
            zf.write(f, arc)
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Pack gui_patch zip")
    ap.add_argument("--version", required=True, help="Patch version e.g. 1.2.0")
    ap.add_argument("--out", required=True, help="Output zip path")
    ap.add_argument("--min-app-version", default="", help="Optional min APP_VERSION")
    ap.add_argument("--notes", default="", help="Changelog / notes")
    ap.add_argument(
        "--extra",
        action="append",
        default=[],
        help="Extra relative path to include (repeatable)",
    )
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    paths = list(DEFAULT_PATHS) + list(args.extra or [])

    meta = tm_package_template(
        PKG_GUI_PATCH,
        name="Turing Mirror GUI Patch",
        version=args.version,
        min_app_version=args.min_app_version,
        notes=args.notes or f"GUI patch {args.version}",
    )

    count = 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            TM_PACKAGE_JSON,
            json.dumps(meta, ensure_ascii=False, indent=2),
        )
        for p in paths:
            count += _add_path(zf, ROOT, Path(p))

    print(f"Wrote {out} ({count} files + {TM_PACKAGE_JSON})")
    print(f"package_type={PKG_GUI_PATCH} version={args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
