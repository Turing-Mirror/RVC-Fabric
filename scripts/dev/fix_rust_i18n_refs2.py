# -*- coding: utf-8 -*-
"""修回过度加 & 的 i18n::t 调用。"""

from __future__ import annotations

import re
from pathlib import Path

RUST = Path(__file__).resolve().parents[2] / "app" / "src-tauri" / "src"


def fix(text: str) -> str:
    # &crate::i18n::t("...").to_string()  → crate::i18n::t("...")  (已是 String)
    text = re.sub(
        r'&crate::i18n::t\(("s\.[a-f0-9]+")\)\.to_string\(\)',
        r"crate::i18n::t(\1)",
        text,
    )
    text = re.sub(
        r'crate::i18n::t\(("s\.[a-f0-9]+")\)\.to_string\(\)',
        r"crate::i18n::t(\1)",
        text,
    )
    # .ok_or_else(|| &crate::i18n::t(...)) → owned
    text = re.sub(
        r'\.ok_or_else\(\|\|\s*&crate::i18n::t\(("s\.[a-f0-9]+")\)\)',
        r".ok_or_else(|| crate::i18n::t(\1))",
        text,
    )
    text = re.sub(
        r'\.ok_or\(\s*&crate::i18n::t\(("s\.[a-f0-9]+")\)\s*\)',
        r".ok_or(crate::i18n::t(\1))",
        text,
    )
    # Err(&crate::i18n::t(...)) / Ok(&...)
    text = re.sub(
        r'\bErr\(\s*&crate::i18n::t\(("s\.[a-f0-9]+")\)\s*\)',
        r"Err(crate::i18n::t(\1))",
        text,
    )
    text = re.sub(
        r'\bOk\(\s*&crate::i18n::t\(("s\.[a-f0-9]+")\)\s*\)',
        r"Ok(crate::i18n::t(\1))",
        text,
    )
    # return Err(&...)
    text = re.sub(
        r'return Err\(\s*&crate::i18n::t\(("s\.[a-f0-9]+")\)\s*\)',
        r"return Err(crate::i18n::t(\1))",
        text,
    )
    # map_err(|_| &crate::i18n::t(...))
    text = re.sub(
        r'\.map_err\(\|_|\|e\|\s*&crate::i18n::t\(("s\.[a-f0-9]+")\)\)',
        lambda m: m.group(0).replace("&crate::i18n::t", "crate::i18n::t"),
        text,
    )
    text = re.sub(
        r'map_err\(\|[^)]*\|[^)]*&crate::i18n::t\(',
        lambda m: m.group(0).replace("&crate::i18n::t(", "crate::i18n::t("),
        text,
    )
    # format! / json! with &String is fine; leave those
    # e.to_string() style
    text = re.sub(
        r'\|\|\s*&crate::i18n::t\(("s\.[a-f0-9]+")\)\s*\.into\(\)',
        r"|| crate::i18n::t(\1)",
        text,
    )
    return text


def main() -> None:
    for p in RUST.rglob("*.rs"):
        if p.name == "i18n.rs":
            continue
        raw = p.read_text(encoding="utf-8")
        new = fix(raw)
        if new != raw:
            p.write_text(new, encoding="utf-8")
            print("fixed", p.name)


if __name__ == "__main__":
    main()
