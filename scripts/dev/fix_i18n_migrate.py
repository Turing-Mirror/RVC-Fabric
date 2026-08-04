# -*- coding: utf-8 -*-
"""修 migrate_i18n_all 留下的语法伤口。"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "src"


def fix_imports(text: str) -> str:
    # import {\nimport { t } from "...";\n  foo,
    text = re.sub(
        r"import\s*\{\s*\nimport\s*\{\s*t\s*\}\s*from\s*([\"'][^\"']+[\"'])\s*;\s*\n",
        r"import { t } from \1;\nimport {\n",
        text,
    )
    # import {\nimport { t } from "..."\n  (missing semicolon variant)
    text = re.sub(
        r"import\s*\{\s*\nimport\s*\{\s*t\s*\}\s*from\s*([\"'][^\"']+[\"'])\s*\n",
        r"import { t } from \1;\nimport {\n",
        text,
    )
    return text


def fix_jsx_attrs(text: str) -> str:
    # name=t("s.hash") -> name={t("s.hash")}
    text = re.sub(
        r'(?<![\w{])([A-Za-z_][\w]*)=t\(("s\.[a-f0-9]+")\)',
        r"\1={t(\2)}",
        text,
    )
    # name=t("s.hash", { ... one level ... })
    text = re.sub(
        r'(?<![\w{])([A-Za-z_][\w]*)=t\(("s\.[a-f0-9]+")\s*,\s*(\{[^{}]*\})\)',
        r"\1={t(\2, \3)}",
        text,
    )
    return text


def main() -> None:
    n = 0
    for p in list(SRC.rglob("*.tsx")) + list(SRC.rglob("*.ts")):
        if "i18n" in p.parts and p.name in (
            "t.ts",
            "dict.ts",
            "index.tsx",
            "types.ts",
            "glossary.ts",
        ):
            continue
        raw = p.read_text(encoding="utf-8")
        out = fix_imports(raw)
        out = fix_jsx_attrs(out)
        if out != raw:
            p.write_text(out, encoding="utf-8")
            n += 1
            print("fixed", p.relative_to(SRC))
    print(f"{n} files")


if __name__ == "__main__":
    main()
