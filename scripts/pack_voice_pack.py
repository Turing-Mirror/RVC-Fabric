# -*- coding: utf-8 -*-
"""Build a voice_pack zip for the online voice library.

Example::

    python scripts/pack_voice_pack.py --id kiki --name 浅夏 ^
        --pth path\\to\\model.pth --index path\\to\\a.index --cover cover.png ^
        --out dist\\kiki_voice.zip
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from launcher.online.package_spec import PKG_VOICE_PACK, TM_PACKAGE_JSON, tm_package_template


def main() -> int:
    ap = argparse.ArgumentParser(description="Pack voice_pack zip")
    ap.add_argument("--id", required=True, help="Stable voice id (folder name)")
    ap.add_argument("--name", default="", help="Display name")
    ap.add_argument("--tag", default="音色")
    ap.add_argument("--version", default="1")
    ap.add_argument("--pth", required=True, type=Path, help="Path to .pth")
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--cover", type=Path, default=None)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    pth = Path(args.pth)
    if not pth.is_file() or pth.suffix.lower() != ".pth":
        print("ERROR: --pth must be an existing .pth file", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    name = args.name or args.id
    meta = tm_package_template(
        PKG_VOICE_PACK,
        name=name,
        version=args.version,
        voice_id=args.id,
        tag=args.tag,
        notes=args.notes,
    )
    cfg = {
        "name": name,
        "tag": args.tag,
        "version": args.version,
        "file": pth.name,
    }

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(TM_PACKAGE_JSON, json.dumps(meta, ensure_ascii=False, indent=2))
        zf.writestr("config.json", json.dumps(cfg, ensure_ascii=False, indent=2))
        zf.write(pth, pth.name)
        if args.index and Path(args.index).is_file():
            zf.write(Path(args.index), Path(args.index).name)
        if args.cover and Path(args.cover).is_file():
            ext = Path(args.cover).suffix.lower() or ".png"
            zf.write(Path(args.cover), f"cover{ext}")

    print(f"Wrote {out}")
    print(f"package_type={PKG_VOICE_PACK} id={args.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
