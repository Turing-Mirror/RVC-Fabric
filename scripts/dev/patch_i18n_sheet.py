# -*- coding: utf-8 -*-
"""Patch existing locale JSON with translations from MD (does NOT wipe existing keys).

    python scripts/dev/patch_i18n_sheet.py --locale en-US --md docs/i18n/sheets/en-US.md
    python scripts/dev/patch_i18n_sheet.py --all
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCALE_DIR = ROOT / "app" / "i18n" / "locales"
ZH_PATH = LOCALE_DIR / "zh-CN.json"
SHEETS = ROOT / "docs" / "i18n" / "sheets"

ROW = re.compile(r"^\|\s*`?([^|`]+?)`?\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$")
LOCALES = ["en-US", "ja-JP", "ko-KR", "zh-TW", "es-ES", "fr-FR", "ru-RU"]


def parse_md(text: str) -> dict[str, str]:
    trans: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        if re.match(r"^\|\s*---", line):
            continue
        m = ROW.match(line.strip())
        if not m:
            continue
        key = m.group(1).strip()
        tr = m.group(3).strip()
        if key.lower() == "key":
            continue
        tr = tr.replace("\\|", "|").replace("<br>", "\n").replace("<br/>", "\n")
        if tr:
            trans[key] = tr
    return trans


def set_path(root: dict | list, path: str, value: str) -> bool:
    parts: list[str | int] = []
    buf = ""
    i = 0
    while i < len(path):
        c = path[i]
        if c == ".":
            if buf:
                parts.append(buf)
                buf = ""
            i += 1
            continue
        if c == "[":
            if buf:
                parts.append(buf)
                buf = ""
            j = path.find("]", i)
            if j < 0:
                return False
            parts.append(int(path[i + 1 : j]))
            i = j + 1
            continue
        buf += c
        i += 1
    if buf:
        parts.append(buf)

    cur: dict | list = root  # type: ignore
    for p in parts[:-1]:
        if isinstance(p, int):
            if not isinstance(cur, list):
                return False
            while len(cur) <= p:
                cur.append({})
            cur = cur[p]  # type: ignore
        else:
            if not isinstance(cur, dict):
                return False
            if p not in cur or not isinstance(cur[p], (dict, list)):
                cur[p] = {}
            cur = cur[p]  # type: ignore
    last = parts[-1]
    if isinstance(last, int):
        if not isinstance(cur, list):
            return False
        while len(cur) <= last:
            cur.append("")
        cur[last] = value
    else:
        if not isinstance(cur, dict):
            return False
        cur[last] = value
    return True


def merge_structure(dst, src):
    """Ensure dst has all keys from src; keep non-empty dst leaf strings."""
    if isinstance(src, dict):
        if not isinstance(dst, dict):
            return deepcopy(src)
        out = dict(dst)
        for k, v in src.items():
            if k not in out:
                out[k] = deepcopy(v)
            else:
                out[k] = merge_structure(out[k], v)
        return out
    if isinstance(src, list):
        if not isinstance(dst, list):
            return deepcopy(src)
        out = list(dst)
        for i, v in enumerate(src):
            if i >= len(out):
                out.append(deepcopy(v))
            else:
                out[i] = merge_structure(out[i], v)
        return out
    if isinstance(dst, str) and dst.strip():
        return dst
    return src


def patch_one(locale: str, md_path: Path) -> int:
    zh = json.loads(ZH_PATH.read_text(encoding="utf-8"))
    existing = json.loads((LOCALE_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    trans = parse_md(md_path.read_text(encoding="utf-8"))
    merged = merge_structure(existing, zh)
    if isinstance(merged.get("meta"), dict):
        merged["meta"]["code"] = locale
    applied = 0
    failed: list[str] = []
    for key, val in trans.items():
        if set_path(merged, key, val):
            applied += 1
        else:
            failed.append(key)
    out = LOCALE_DIR / f"{locale}.json"
    out.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{locale}: patched {applied}/{len(trans)} from {md_path.name}")
    if failed:
        print(f"  failed paths: {failed[:10]}")
    dock = merged.get("dock") or {}
    print(f"  dock.start={dock.get('start')!r}")
    s = merged.get("s") or {}
    print(f"  s.7ccca92d5e={s.get('7ccca92d5e')!r}")
    return 0 if not failed else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--locale")
    ap.add_argument("--md", type=Path)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if args.all:
        for loc in LOCALES:
            md = SHEETS / f"{loc}.md"
            if not md.is_file():
                print(f"skip {loc}: no {md}")
                continue
            patch_one(loc, md)
        return 0
    if not args.locale or not args.md:
        print("need --locale and --md, or --all", file=sys.stderr)
        return 1
    return patch_one(args.locale, args.md)


if __name__ == "__main__":
    raise SystemExit(main())
