# -*- coding: utf-8 -*-
"""Sync product configs/online_catalog.json voices into CNB-GIT-RELEASE/index.json.

Also copies User_Data/models/<id>/cover.* → ch-banner/<id>.jpg when present.

Usage (repo root)::

    python scripts/write_cnb_index.py
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CNB = REPO / "CNB-GIT-RELEASE"
CATALOG = REPO / "configs" / "online_catalog.json"
INDEX = CNB / "index.json"
BANNER = CNB / "ch-banner"
RAW = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main"


def main() -> int:
    if not CATALOG.is_file():
        print("missing", CATALOG)
        return 1
    CNB.mkdir(parents=True, exist_ok=True)
    BANNER.mkdir(parents=True, exist_ok=True)

    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    voices_out = []
    for v in cat.get("voices") or []:
        if not isinstance(v, dict):
            continue
        vid = str(v.get("id") or "").strip()
        if not vid:
            continue
        # copy cover
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            src = REPO / "User_Data" / "models" / vid / f"cover{ext}"
            if src.is_file():
                dst = BANNER / f"{vid}.jpg"
                if ext.lower() in (".jpg", ".jpeg"):
                    shutil.copy2(src, dst)
                else:
                    try:
                        from PIL import Image

                        Image.open(src).convert("RGB").save(dst, quality=90)
                    except Exception:
                        shutil.copy2(src, BANNER / f"{vid}{ext}")
                        dst = BANNER / f"{vid}{ext}"
                print("cover", dst.name)
                break
        cover_rel = f"ch-banner/{vid}.jpg"
        if not (BANNER / f"{vid}.jpg").is_file():
            for p in BANNER.glob(f"{vid}.*"):
                cover_rel = f"ch-banner/{p.name}"
                break
        item = dict(v)
        item["cover"] = cover_rel
        item["cover_url"] = f"{RAW}/{cover_rel}"
        item.setdefault("author", item.get("publisher") or "RVC Fabric")
        item.setdefault("author_url", "https://cnb.cool/Turing-Mirror")
        item.setdefault(
            "released",
            item.get("date") or item.get("released") or datetime.now().strftime("%y%m%d"),
        )
        item["date"] = item.get("released") or item.get("date") or ""
        voices_out.append(item)

    yymmdd = datetime.now().strftime("%y%m%d")
    index: dict = {
        "schema": 2,
        "format": "rvc_fabric_index",
        "product": "RVC Fabric",
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "released": yymmdd,
        "cnb_repo": "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases",
        "raw_base": RAW,
        "lfs_base": "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/lfs",
        "ch_banner_dir": "ch-banner",
        "note": "软件读取本 index.json。packages 按 YYMMDD 命名；音色含 name/author/author_url/date/cover。",
        "packages": {
            "setup": [],
            "gui_patch": [],
            "runtime": [],
        },
        "app": cat.get("app") or {},
        "community": cat.get("community") or {},
        "voices": voices_out,
        "runtime_release_tag": cat.get("runtime_release_tag") or "RVC-runtime",
        "runtimes": cat.get("runtimes") or {},
        "manifest_urls": [
            f"{RAW}/index.json",
        ],
    }
    # merge existing packages/runtime from previous index if present
    if INDEX.is_file():
        try:
            old = json.loads(INDEX.read_text(encoding="utf-8"))
            if isinstance(old.get("packages"), dict):
                for k, val in old["packages"].items():
                    if val:
                        index["packages"][k] = val
        except Exception:
            pass

    INDEX.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("wrote", INDEX)
    print("voices", len(voices_out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
