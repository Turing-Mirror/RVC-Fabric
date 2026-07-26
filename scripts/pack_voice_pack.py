# -*- coding: utf-8 -*-
"""Build a voice_pack zip for the online voice library / RVC Fabric releases.

Zip always contains ``config.json`` with identity fields the app reads::

    name, author, author_url, date (YYMMDD), cover

Example::

    python scripts/pack_voice_pack.py --id kiki --name 浅夏 ^
        --author "某作者" --author-url "https://example.com" --date 260722 ^
        --pth path\\to\\model.pth --index path\\to\\a.index --cover cover.jpg ^
        --out dist\\kiki_voice.zip
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from launcher.online.package_spec import (
    PKG_VOICE_PACK,
    TM_PACKAGE_JSON,
    normalize_yymmdd,
    tm_package_template,
    voice_meta_template,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Pack voice_pack zip with identity config.json")
    ap.add_argument("--id", required=True, help="Stable voice id (folder name)")
    ap.add_argument("--name", default="", help="Display name")
    ap.add_argument("--author", default="RVC Fabric", help="Author display name")
    ap.add_argument("--author-url", default="", dest="author_url", help="Author homepage URL")
    ap.add_argument(
        "--date",
        default="",
        help="Release date YYMMDD (default: today)",
    )
    ap.add_argument("--tag", default="音色")
    ap.add_argument(
        "--series",
        default="",
        help="系列包名（如 Mygo / VOCALOID）；社区下载按此分组显示",
    )
    ap.add_argument("--version", default="1")
    ap.add_argument("--pth", required=True, type=Path, help="Path to .pth")
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--cover", type=Path, default=None)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--notes", default="")
    ap.add_argument(
        "--author-url-default",
        default="https://cnb.cool/Turing-Mirror",
        help="Fallback author_url when --author-url empty",
    )
    args = ap.parse_args()

    pth = Path(args.pth)
    if not pth.is_file() or pth.suffix.lower() != ".pth":
        print("ERROR: --pth must be an existing .pth file", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    name = (args.name or args.id).strip()
    author = (args.author or "RVC Fabric").strip()
    author_url = (args.author_url or args.author_url_default or "").strip()
    date = normalize_yymmdd(args.date) or datetime.now().strftime("%y%m%d")

    cover_arc = "cover.jpg"
    if args.cover and Path(args.cover).is_file():
        ext = Path(args.cover).suffix.lower() or ".jpg"
        if ext == ".jpeg":
            ext = ".jpg"
        cover_arc = f"cover{ext}"

    meta = tm_package_template(
        PKG_VOICE_PACK,
        name=name,
        version=args.version,
        voice_id=args.id,
        tag=args.tag,
        notes=args.notes,
        author=author,
        author_url=author_url,
        date=date,
        cover=cover_arc,
        publisher="rvc_fabric",
        fabric_official=True,
    )
    cfg = voice_meta_template(
        name=name,
        author=author,
        author_url=author_url,
        date=date,
        cover=cover_arc,
        tag=args.tag,
        version=args.version,
        file=pth.name,
        publisher="rvc_fabric",
        fabric_official=True,
        online_id=args.id,
        released=date,
    )
    series = (args.series or "").strip()
    if series:
        meta["series"] = series
        cfg["series"] = series

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(TM_PACKAGE_JSON, json.dumps(meta, ensure_ascii=False, indent=2))
        zf.writestr("config.json", json.dumps(cfg, ensure_ascii=False, indent=2))
        zf.write(pth, pth.name)
        if args.index and Path(args.index).is_file():
            zf.write(Path(args.index), Path(args.index).name)
        if args.cover and Path(args.cover).is_file():
            zf.write(Path(args.cover), cover_arc)

    print(f"Wrote {out}")
    print(f"package_type={PKG_VOICE_PACK} id={args.id}")
    print(f"config: name={name!r} author={author!r} date={date} cover={cover_arc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
