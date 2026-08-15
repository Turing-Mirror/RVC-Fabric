# -*- coding: utf-8 -*-
"""Build a gui_patch (incremental) zip for in-app updates.

Example::

    python scripts/pack_gui_patch.py --version 1.2.3-hotfix1 --out dist/gui_patch_1.2.3-hotfix1.zip

Stable ``--version`` must be ``X.Y.Z`` (see docs/项目白皮书.md §5.1; legacy -hotfixN only for old clients).
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

from pack_spec import PKG_GUI_PATCH, TM_PACKAGE_JSON, tm_package_template
from shell_version import (
    HOTFIX_SUGGEST_THRESHOLD,
    should_suggest_base_bump,
    validate_stable_shell_version,
)

# 打包的是 app/frontend/ 里的**内容**，直接放在 zip 根目录。
#
# 这是壳里 update::apply_gui_patch 唯一认的形状：它把 zip 解到暂存目录，
# 检查根部（或唯一的顶层目录）有没有 index.html，然后整个替换掉安装目录
# 下的 frontend/。所以：
#
#   ✅  index.html / assets/... / tm_package.json  在 zip 根
#   ❌  app/frontend/index.html                    —— 根部没有 index.html，
#                                                     壳会直接拒绝这个包
#
# 之前这里打的是旧 Python 壳那套布局（launcher/ + gui_v1.py + tools/*.py，
# 各自带路径），靠 Tk 壳按白名单合并。launcher/ 已经删了，Tauri 壳只换
# frontend/ 一个目录 —— **引擎侧的 .py 换不了，Rust 侧也换不了，那些改动
# 只能重发安装包**。别再往这个包里塞它们，塞了也会被丢掉。
FRONTEND_DIR = ROOT / "app" / "frontend"

# 留着给 --extra 用：真要额外塞点什么进 frontend/ 的时候。
DEFAULT_PATHS: list[str] = [
    # 空。历史上这里列过 launcher/ 和 tools/*.py，见上面的注释。
]

_LEGACY_PATHS = [
    "app/frontend",
    "launcher",
    "configs/online_catalog.json",
    "tools/realtime_worker.py",
    "tools/dsp_fx.py",
    # 无模型 DSP 变声：效果器、预设读写、内置预设本体。
    # 少打其中任何一个，DSP 模式在补丁包升级上来的机器上就是半残的。
    "tools/dsp_voice.py",
    "tools/dsp_presets.py",
    "configs/dsp_presets",
    "tools/download_models.py",
    # diagnostics bundle deps: more_page loads collect_diagnostics from disk,
    # perf_bench runs benchmark_realtime in the Runtime, perf_report is
    # imported by the shell for 自动优化性能 — patches must ship all three
    "tools/collect_diagnostics.py",
    "tools/benchmark_realtime.py",
    "tools/perf_report.py",
    "gui_v1.py",
    # Window / Start Menu / chrome marks (wordmark + app.ico + logo_nav)
    "assets/brand",
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

    if not (FRONTEND_DIR / "index.html").is_file():
        print(
            f"error: 找不到 {FRONTEND_DIR}/index.html —— 先在 app/ 里跑一次"
            " `npm run build`。",
            file=sys.stderr,
        )
        return 2

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
        # frontend/ 的内容平铺到 zip 根，不带 app/frontend 前缀。
        for f in sorted(FRONTEND_DIR.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix == ".map":
                continue  # sourcemap 不发给用户，见 vite.config.ts
            zf.write(f, f.relative_to(FRONTEND_DIR).as_posix())
            count += 1
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
