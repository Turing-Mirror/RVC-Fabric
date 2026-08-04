# -*- coding: utf-8 -*-
"""shell_log!/format! 需要字面量模板：无参走 t()，有参把中文模板写回字面量。"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUST = ROOT / "app" / "src-tauri" / "src"
ZH = json.loads(
    (ROOT / "app" / "i18n" / "locales" / "zh-CN.json").read_text(encoding="utf-8")
)
S = ZH.get("s", {})

# logging::shell_log!(&crate::i18n::t("s.xxx"));
# logging::shell_log!(&crate::i18n::t("s.xxx"), a, b);
PAT = re.compile(
    r'(logging::shell_log!|crate::logging::shell_log!)\(\s*&?crate::i18n::t\("s\.([a-f0-9]+)"\)\s*([,)])'
)


def rust_string_lit(s: str) -> str:
    esc = (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{esc}"'


def main() -> None:
    for p in RUST.rglob("*.rs"):
        raw = p.read_text(encoding="utf-8")

        def repl(m: re.Match) -> str:
            macro = m.group(1)
            h = m.group(2)
            trail = m.group(3)  # , or )
            text = S.get(h)
            if text is None:
                return m.group(0)
            if trail == ")":
                # no extra args — runtime message ok
                return f'{macro}(crate::i18n::t("s.{h}"))'
            # has args — need literal format template
            return f"{macro}({rust_string_lit(text)}{trail}"

        new = PAT.sub(repl, raw)
        if new != raw:
            p.write_text(new, encoding="utf-8")
            print("fixed", p.relative_to(RUST))


if __name__ == "__main__":
    main()
