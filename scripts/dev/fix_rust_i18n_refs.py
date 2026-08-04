# -*- coding: utf-8 -*-
"""给需要 &str 的调用点补上 &crate::i18n::t(...)。"""

from __future__ import annotations

import re
from pathlib import Path

RUST = Path(__file__).resolve().parents[2] / "app" / "src-tauri" / "src"

# 这些上下文里 String 本来就对
KEEP_OWNED = re.compile(
    r"(Err|Ok|format!|println!|eprintln!|write!|writeln!|json!|to_string|"
    r"push_str|insert|from|into|String::from|bail!|anyhow!)\s*\(?\s*$"
)


def fix(text: str) -> str:
    out = []
    i = 0
    needle = "crate::i18n::t("
    while True:
        j = text.find(needle, i)
        if j < 0:
            out.append(text[i:])
            break
        # already borrowed?
        if j > 0 and text[j - 1] == "&":
            out.append(text[i : j + len(needle)])
            i = j + len(needle)
            continue
        before = text[max(0, j - 48) : j]
        # strip trailing whitespace for match
        if KEEP_OWNED.search(before.rstrip()):
            out.append(text[i : j + len(needle)])
        else:
            out.append(text[i:j] + "&" + needle)
        i = j + len(needle)
    return "".join(out)


def main() -> None:
    n = 0
    for p in RUST.rglob("*.rs"):
        if p.name == "i18n.rs":
            continue
        raw = p.read_text(encoding="utf-8")
        new = fix(raw)
        if new != raw:
            p.write_text(new, encoding="utf-8")
            n += 1
            print("fixed", p.name)
    print(f"{n} files")


if __name__ == "__main__":
    main()
