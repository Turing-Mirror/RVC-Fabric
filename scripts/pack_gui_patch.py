# -*- coding: utf-8 -*-
"""Build a gui_patch (incremental) zip for in-app updates.

Example::

    python scripts/pack_gui_patch.py --version 1.2.3-hotfix1 --out dist/gui_patch_1.2.3-hotfix1.zip

Stable ``--version`` must be ``X.Y.Z`` or ``X.Y.Z-hotfixN`` (see docs/在线更新与音色库.md).
Optional ``--build-id`` is metadata only (not used for update ordering).

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
from launcher.version import (
    HOTFIX_SUGGEST_THRESHOLD,
    should_suggest_base_bump,
    validate_stable_shell_version,
)

# Relative paths or globs under ROOT
DEFAULT_PATHS = [
    "launcher",
    "configs/online_catalog.json",
    "tools/realtime_worker.py",
    "tools/dsp_fx.py",
    "tools/download_models.py",
    # diagnostics bundle deps: more_page loads collect_diagnostics from disk,
    # perf_bench runs benchmark_realtime in the Runtime, perf_report is
    # imported by the shell for 自动优化性能 — patches must ship all three
    "tools/collect_diagnostics.py",
    "tools/benchmark_realtime.py",
    "tools/perf_report.py",
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
    ap.add_argument(
        "--version",
        required=True,
        help="Full shell version: X.Y.Z or X.Y.Z-hotfixN",
    )
    ap.add_argument("--out", required=True, help="Output zip path")
    ap.add_argument("--min-app-version", default="", help="Optional min APP_VERSION")
    ap.add_argument("--notes", default="", help="Changelog / notes")
    ap.add_argument(
        "--build-id",
        default="",
        help="Optional build stamp for support (metadata only, not compared)",
    )
    ap.add_argument(
        "--extra",
        action="append",
        default=[],
        help="Extra relative path to include (repeatable)",
    )
    args = ap.parse_args()

    try:
        version = validate_stable_shell_version(args.version)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if should_suggest_base_bump(version):
        print(
            f"note: {version} 已达热修建议上限 "
            f"({HOTFIX_SUGGEST_THRESHOLD})，下次优先发 X.Y.(Z+1) 正式基线。",
            file=sys.stderr,
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    paths = list(DEFAULT_PATHS) + list(args.extra or [])

    meta = tm_package_template(
        PKG_GUI_PATCH,
        name="Turing Mirror GUI Patch",
        version=version,
        min_app_version=args.min_app_version,
        notes=args.notes or f"GUI patch {version}",
        build_id=str(args.build_id or "").strip(),
    )

    count = 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            TM_PACKAGE_JSON,
            json.dumps(meta, ensure_ascii=False, indent=2),
        )
        for p in paths:
            count += _add_path(zf, ROOT, Path(p))

    # sha256 for catalog (required for in-app apply)
    import hashlib

    h = hashlib.sha256()
    with open(out, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    digest = h.hexdigest()
    print(f"Wrote {out} ({count} files + {TM_PACKAGE_JSON})")
    print(f"package_type={PKG_GUI_PATCH} version={version}")
    if meta.get("build_id"):
        print(f"build_id={meta['build_id']}")
    print(f"sha256={digest}")
    print(
        "Put this sha256 into CNB-GIT-RELEASE/catalog-src/app.yaml "
        "(gui.sha256); keep version/gui.version = this Full version."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
