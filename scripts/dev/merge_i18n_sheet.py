# -*- coding: utf-8 -*-
"""把翻译 AI 的 Markdown 对照表合并进语言包 JSON。

读::

    app/i18n/locales/zh-CN.json     骨架
    docs/i18n/sheets/<locale>.md    译文表

写::

    app/i18n/locales/<locale>.json

MD 表格式见 docs/i18n/给翻译AI.md：

    | key | zh-CN | translation |
    | nav.home | 首页 | Home |
    | s.abc | … | … |

用法::

    python scripts/dev/merge_i18n_sheet.py --locale en-US --md docs/i18n/sheets/en-US.md
    python scripts/dev/merge_i18n_sheet.py --locale en-US --md docs/i18n/sheets/en-US.md --check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ZH_PATH = ROOT / "app" / "i18n" / "locales" / "zh-CN.json"
LOCALE_DIR = ROOT / "app" / "i18n" / "locales"

# | key | zh | tr |  or with backticks around key
ROW = re.compile(
    r"^\|\s*`?([^|`]+?)`?\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$"
)
LOCALE_HDR = re.compile(r"^#\s*locale\s*:\s*(\S+)", re.I)


def parse_md(text: str) -> tuple[str | None, dict[str, str]]:
    locale = None
    trans: dict[str, str] = {}
    for line in text.splitlines():
        m = LOCALE_HDR.match(line.strip())
        if m:
            locale = m.group(1).strip()
            continue
        if not line.strip().startswith("|"):
            continue
        if re.match(r"^\|\s*---", line):
            continue
        m = ROW.match(line.strip())
        if not m:
            continue
        key, _zh, tr = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        if key.lower() == "key":
            continue
        # unescape
        tr = tr.replace("\\|", "|").replace("<br>", "\n").replace("<br/>", "\n")
        if tr:
            trans[key] = tr
    return locale, trans


def set_path(root: dict | list, path: str, value: str) -> bool:
    """Set value at dotted/bracket path. Returns False if path missing in skeleton."""
    # tokenize: a.b[0].c
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

    cur: dict | list | str = root
    for p in parts[:-1]:
        if isinstance(p, int):
            if not isinstance(cur, list) or p >= len(cur):
                return False
            cur = cur[p]
        else:
            if not isinstance(cur, dict) or p not in cur:
                return False
            cur = cur[p]
    last = parts[-1]
    if isinstance(last, int):
        if not isinstance(cur, list) or last >= len(cur):
            return False
        # list element must be str leaf
        if isinstance(cur[last], (dict, list)):
            return False
        cur[last] = value
    else:
        if not isinstance(cur, dict) or last not in cur:
            return False
        if isinstance(cur[last], (dict, list)):
            return False
        cur[last] = value
    return True


def collect_string_paths(obj, prefix: str = "") -> set[str]:
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            out |= collect_string_paths(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out |= collect_string_paths(v, f"{prefix}[{i}]")
    elif isinstance(obj, str):
        out.add(prefix)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--locale", required=True, help="如 en-US")
    ap.add_argument("--md", type=Path, required=True, help="翻译 MD 路径")
    ap.add_argument(
        "--check",
        action="store_true",
        help="只报告缺译/多余 key，不写文件",
    )
    args = ap.parse_args()

    if not args.md.is_file():
        print(f"找不到 MD：{args.md}", file=sys.stderr)
        return 1

    zh = json.loads(ZH_PATH.read_text(encoding="utf-8"))
    hdr_locale, trans = parse_md(args.md.read_text(encoding="utf-8"))
    locale = args.locale
    if hdr_locale and hdr_locale != locale:
        print(f"警告：MD 文首 locale={hdr_locale}，命令行 --locale={locale}，以命令行为准")

    # Prefer patching existing locale so prior translations are not wiped.
    # Fall back to zh-CN skeleton only when the target file is missing.
    out_path = LOCALE_DIR / f"{locale}.json"
    if out_path.is_file():
        base = json.loads(out_path.read_text(encoding="utf-8"))
    else:
        base = deepcopy(zh)
    if isinstance(base.get("meta"), dict):
        base["meta"]["code"] = locale

    missing_in_zh: list[str] = []
    applied = 0
    for key, val in trans.items():
        if set_path(base, key, val):
            applied += 1
        else:
            missing_in_zh.append(key)

    all_paths = collect_string_paths(zh)
    untranslated = sorted(p for p in all_paths if p not in trans)

    print(f"MD 译文条数：{len(trans)}")
    print(f"成功写入：{applied}")
    if missing_in_zh:
        print(f"MD 有但无法写入路径（{len(missing_in_zh)}）：")
        for k in missing_in_zh[:20]:
            print(f"  - {k}")
        if len(missing_in_zh) > 20:
            print(f"  … 另 {len(missing_in_zh) - 20} 条")
    if untranslated:
        print(f"中文包有但本次 MD 未覆盖（{len(untranslated)}，保留原译文/中文）：")
        for k in untranslated[:10]:
            print(f"  - {k}")
        if len(untranslated) > 10:
            print(f"  … 另 {len(untranslated) - 10} 条")

    if args.check:
        return 1 if missing_in_zh else 0

    out_path.write_text(
        json.dumps(base, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已写出 {out_path.relative_to(ROOT)}")
    if untranslated:
        print("提示：未译条目已保留中文，运行时也可回退 zh-CN。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
