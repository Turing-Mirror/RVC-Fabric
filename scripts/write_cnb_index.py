# -*- coding: utf-8 -*-
"""Sync product online catalog → CNB-GIT-RELEASE/index.json + ch-banner.

Also writes catalog/online_catalog.snippet.json (compat).

Usage (repo root)::

    python scripts/write_cnb_index.py
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
CNB = REPO / "CNB-GIT-RELEASE"
CATALOG = REPO / "configs" / "online_catalog.json"
INDEX = CNB / "index.json"
BANNER = CNB / "ch-banner"
SNIPPET = CNB / "catalog" / "online_catalog.snippet.json"
RAW = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main"
LFS = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/lfs"


def _yymmdd(raw: Any) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    if len(digits) == 8:
        return digits[2:]
    if len(digits) == 6:
        return digits
    return ""


def _copy_banner(vid: str) -> str:
    """Copy User_Data/models/<id>/cover.* → ch-banner/<id>.jpg; return relative path."""
    BANNER.mkdir(parents=True, exist_ok=True)
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        src = REPO / "User_Data" / "models" / vid / f"cover{ext}"
        if not src.is_file():
            continue
        dst = BANNER / f"{vid}.jpg"
        if ext.lower() in (".jpg", ".jpeg"):
            shutil.copy2(src, dst)
        else:
            try:
                from PIL import Image

                Image.open(src).convert("RGB").save(dst, quality=90)
            except Exception:
                shutil.copy2(src, BANNER / f"{vid}{ext}")
                return f"ch-banner/{vid}{ext}"
        print("cover", dst.name)
        return f"ch-banner/{vid}.jpg"
    for p in sorted(BANNER.glob(f"{vid}.*")):
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            return f"ch-banner/{p.name}"
    return f"ch-banner/{vid}.jpg"


def _voice_item(v: dict, default_day: str) -> dict[str, Any]:
    vid = str(v.get("id") or "").strip()
    cover_rel = _copy_banner(vid)
    day = (
        _yymmdd(v.get("date") or v.get("released") or v.get("yymmdd"))
        or default_day
    )
    item = dict(v)
    item["id"] = vid
    item["name"] = str(v.get("name") or vid)
    item["author"] = str(
        v.get("author") or v.get("publisher") or "RVC Fabric"
    ).strip()
    item["author_url"] = str(
        v.get("author_url") or v.get("author_link") or "https://cnb.cool/Turing-Mirror"
    ).strip()
    item["date"] = day
    item["released"] = day
    item["cover"] = cover_rel
    item["cover_url"] = f"{RAW}/{cover_rel}"
    item.setdefault("package_type", "voice_pack")
    item.setdefault("publisher", "rvc_fabric")
    item.setdefault("fabric_official", True)
    return item


def _runtime_packages(runtimes: dict, default_day: str) -> list[dict]:
    out: list[dict] = []
    for key, rt in (runtimes or {}).items():
        if not isinstance(rt, dict):
            continue
        variant = str(rt.get("variant") or key)
        day = _yymmdd(rt.get("released") or rt.get("version")) or default_day
        parts = rt.get("parts") or []
        part = parts[0] if parts and isinstance(parts[0], dict) else {}
        name = str(part.get("name") or f"runtime-{variant}.tar")
        urls = part.get("urls") or []
        sha_urls = part.get("sha256_urls") or []
        out.append(
            {
                "id": f"runtime-{variant}-{day}",
                "variant": variant,
                "released": day,
                "date": day,
                "version": str(rt.get("version") or day),
                "channel": str(rt.get("channel") or "lfs"),
                "name": name,
                "url": str(urls[0] if urls else ""),
                "sha256": str(part.get("sha256") or ""),
                "sha256_url": str(sha_urls[0] if sha_urls else ""),
                "size_bytes": int(
                    part.get("size_bytes") or rt.get("size_bytes") or 0
                ),
            }
        )
    return out


def main() -> int:
    if not CATALOG.is_file():
        print("missing", CATALOG)
        return 1
    CNB.mkdir(parents=True, exist_ok=True)
    BANNER.mkdir(parents=True, exist_ok=True)
    (CNB / "catalog").mkdir(parents=True, exist_ok=True)

    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    old: dict[str, Any] = {}
    if INDEX.is_file():
        try:
            old = json.loads(INDEX.read_text(encoding="utf-8"))
            if not isinstance(old, dict):
                old = {}
        except Exception:
            old = {}

    today = datetime.now().strftime("%y%m%d")
    voices_out = []
    for v in cat.get("voices") or []:
        if not isinstance(v, dict) or not v.get("id"):
            continue
        voices_out.append(_voice_item(v, today))

    # packages: keep existing setup/gui; refresh runtime from runtimes
    packages = {
        "setup": list((old.get("packages") or {}).get("setup") or []),
        "gui_patch": list((old.get("packages") or {}).get("gui_patch") or []),
        "runtime": list((old.get("packages") or {}).get("runtime") or []),
    }
    runtimes = cat.get("runtimes") or old.get("runtimes") or {}
    if not packages["runtime"] and runtimes:
        packages["runtime"] = _runtime_packages(runtimes, today)
    if not packages["setup"] and (old.get("packages") or {}).get("setup"):
        packages["setup"] = (old.get("packages") or {}).get("setup") or []

    # default empty setup slot named by date if none
    if not packages["setup"]:
        packages["setup"] = [
            {
                "id": f"setup-{today}",
                "name": "RVC Fabric Setup",
                "kind": "setup",
                "package_type": "full_package",
                "released": today,
                "date": today,
                "version": str(
                    (cat.get("app") or {}).get("version") or "1.0.0"
                ),
                "file": "setup/RVC_Fabric_Setup.exe",
                "url": "",
                "sha256": "",
                "size_bytes": 0,
                "notes": "Inno 安装器。上传 Setup 后填 url/sha256。",
            }
        ]

    index: dict[str, Any] = {
        "schema": 2,
        "format": "rvc_fabric_index",
        "product": "RVC Fabric",
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "released": today,
        "cnb_repo": "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases",
        "cnb_git": "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases.git",
        "raw_base": RAW,
        "lfs_base": LFS,
        "ch_banner_dir": "ch-banner",
        "note": (
            "软件自动读取本 index.json。"
            "packages 按发布时间 YYMMDD 命名；"
            "音色含 name/author/author_url/date/cover（ch-banner）。"
        ),
        "packages": packages,
        "app": cat.get("app") or old.get("app") or {},
        "community": cat.get("community") or old.get("community") or {},
        "voices": voices_out,
        "runtime_release_tag": cat.get("runtime_release_tag")
        or old.get("runtime_release_tag")
        or "RVC-runtime",
        "runtimes": runtimes,
        "manifest_urls": [
            f"{RAW}/index.json",
            f"{RAW}/catalog/online_catalog.snippet.json",
        ],
    }

    INDEX.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("wrote", INDEX)

    # Compat snippet: app + community + voices + runtimes (no full packages block required)
    snippet = {
        "schema": 1,
        "note": "兼容清单；主索引请用根目录 index.json",
        "cnb_repo": index["cnb_repo"],
        "raw_base": RAW,
        "lfs_base": LFS,
        "manifest_urls": index["manifest_urls"],
        "app": index["app"],
        "community": index["community"],
        "voices": voices_out,
        "runtime_release_tag": index["runtime_release_tag"],
        "runtimes": runtimes,
    }
    SNIPPET.write_text(
        json.dumps(snippet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("wrote", SNIPPET)
    print("voices", len(voices_out), "banners", list(BANNER.glob("*.*")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
