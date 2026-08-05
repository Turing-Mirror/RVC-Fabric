# -*- coding: utf-8 -*-
"""审查 sheets → 修格式 → merge 全部 locale JSON。发版前一步跑。"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHEETS = ROOT / "docs" / "i18n" / "sheets"
ZH = ROOT / "app" / "i18n" / "locales" / "zh-CN.json"
MERGE = ROOT / "scripts" / "dev" / "merge_i18n_sheet.py"

LOCALES = ["en-US", "es-ES", "fr-FR", "ja-JP", "ko-KR", "ru-RU", "zh-TW"]

FIX_2633 = {
    "en-US": r'Voice name cannot contain \ / : * ? " < > or similar characters',
    "es-ES": r'El nombre de la voz no puede contener \ / : * ? " < > ni caracteres similares',
    "fr-FR": r'Le nom de la voix ne peut pas contenir \ / : * ? " < > ni caractères similaires',
    "ja-JP": r'音色名に \ / : * ? " < > などの文字は使用できません',
    "ko-KR": r'음색 이름에 \ / : * ? " < > 문자는 포함할 수 없습니다',
    "ru-RU": r'Имя тембра не может содержать символы \ / : * ? " < > и подобные',
    "zh-TW": r'音色名不能含 \ / : * ? " < > 等字元',
}
ZH_2633 = r'音色名不能含 \ / : * ? " < > 等字符'


def fix_sheet(path: Path) -> list[str]:
    notes: list[str] = []
    text = path.read_text(encoding="utf-8")
    orig = text
    locale = path.stem

    # mid-table re-headers
    pat_hdr = re.compile(
        r"\n\| key \| zh-CN \| [^\n|]+ \|\s*\n"
        r"\| ?:?-+:? \| ?:?-+:? \| ?:?-+:? \|\s*\n",
        re.I,
    )
    text, n = pat_hdr.subn("\n", text)
    if n:
        notes.append(f"rm {n} mid-header")

    if locale in FIX_2633 or path.name == "source.md":
        tr = FIX_2633.get(locale, "")
        pat = re.compile(r"^\| `s\.2633fe7d2f` \|.*?\|.*?\|\s*$", re.M)
        if path.name == "source.md":
            repl = f"| `s.2633fe7d2f` | {ZH_2633} |  |"
        else:
            repl = f"| `s.2633fe7d2f` | {ZH_2633} | {tr} |"
        text2, n = pat.subn(repl, text, count=1)
        if n:
            notes.append("fix 2633")
            text = text2

    if text != orig:
        path.write_text(text, encoding="utf-8", newline="\n")
    return notes


def parse_rows(path: Path) -> list[tuple[str, str, str, int]]:
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s.startswith("|"):
            continue
        if re.match(r"^\|\s*:?---", s):
            continue
        if re.search(r"\|\s*key\s*\|", s, re.I):
            continue
        m = re.match(
            r"^\|\s*`?([^|`]+?)`?\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$", s
        )
        if not m:
            continue
        k = m.group(1).strip()
        if k.lower() == "key" or k.startswith(":"):
            continue
        rows.append((k, m.group(2).strip(), m.group(3).strip(), i))
    return rows


def audit(path: Path, src_keys: set[str]) -> dict:
    rows = parse_rows(path)
    keys = [k for k, _, _, _ in rows]
    empty = [(k, i) for k, z, t, i in rows if not t]
    missing = sorted(src_keys - set(keys))
    extra = sorted(set(keys) - src_keys)
    multi = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if s.startswith("|") and s.count("|") > 4 and "key" not in s[:20].lower():
            multi.append(i)
    return {
        "rows": len(rows),
        "empty": empty,
        "missing": missing,
        "extra": extra,
        "multi": multi,
    }


def ensure_locale_meta(data: dict, locale: str, names: dict[str, str]) -> None:
    """Ensure meta + locale.* labels exist for language picker."""
    meta = data.setdefault("meta", {})
    if isinstance(meta, dict):
        meta["code"] = locale
        if locale in names:
            meta["name"] = names[locale]
            meta["englishName"] = {
                "zh-CN": "Simplified Chinese",
                "en-US": "English",
                "es-ES": "Spanish",
                "fr-FR": "French",
                "ja-JP": "Japanese",
                "ko-KR": "Korean",
                "ru-RU": "Russian",
                "zh-TW": "Traditional Chinese",
            }.get(locale, locale)
    loc = data.setdefault("locale", {})
    if isinstance(loc, dict):
        for code, label in names.items():
            loc[code] = label


NAMES = {
    "zh-CN": "简体中文",
    "en-US": "English",
    "es-ES": "Español",
    "fr-FR": "Français",
    "ja-JP": "日本語",
    "ko-KR": "한국어",
    "ru-RU": "Русский",
    "zh-TW": "繁體中文",
}


def main() -> int:
    # fix source + sheets
    if (SHEETS / "source.md").is_file():
        print("source:", fix_sheet(SHEETS / "source.md") or "ok")

    src_keys = {k for k, _, _, _ in parse_rows(SHEETS / "source.md")}
    print(f"source keys: {len(src_keys)}")

    fail = False
    for loc in LOCALES:
        p = SHEETS / f"{loc}.md"
        if not p.is_file():
            print(f"MISSING {p}")
            fail = True
            continue
        notes = fix_sheet(p)
        a = audit(p, src_keys)
        print(
            f"{loc}: rows={a['rows']} empty={len(a['empty'])} "
            f"missing={len(a['missing'])} extra={len(a['extra'])} "
            f"multi={len(a['multi'])} fixes={notes or '-'}"
        )
        if a["empty"] or a["missing"] or a["multi"]:
            fail = True
            if a["empty"][:5]:
                print("  empty sample", a["empty"][:5])
            if a["missing"][:5]:
                print("  missing sample", a["missing"][:5])
            if a["multi"][:3]:
                print("  multipipe lines", a["multi"][:3])

    if fail:
        print("AUDIT FAILED — abort merge")
        return 1

    # merge each
    for loc in LOCALES:
        md = SHEETS / f"{loc}.md"
        r = subprocess.run(
            [
                sys.executable,
                str(MERGE),
                "--locale",
                loc,
                "--md",
                str(md),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        print(r.stdout)
        if r.returncode != 0:
            print(r.stderr)
            print(f"merge failed: {loc}")
            return 1
        # post: ensure locale labels in every pack
        out = ROOT / "app" / "i18n" / "locales" / f"{loc}.json"
        data = json.loads(out.read_text(encoding="utf-8"))
        ensure_locale_meta(data, loc, NAMES)
        out.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    # also patch zh-CN locale.* for all language names
    zh = json.loads(ZH.read_text(encoding="utf-8"))
    ensure_locale_meta(zh, "zh-CN", NAMES)
    # keep 2633 clean
    if isinstance(zh.get("s"), dict) and "2633fe7d2f" in zh["s"]:
        zh["s"]["2633fe7d2f"] = ZH_2633
    ZH.write_text(json.dumps(zh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("zh-CN locale labels updated")

    print("ALL MERGED OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
