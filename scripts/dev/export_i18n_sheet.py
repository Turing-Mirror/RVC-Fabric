# -*- coding: utf-8 -*-
"""从 zh-CN.json 导出给翻译 AI 的 Markdown 源文表。

输出（gitignore 目录）::

    docs/i18n/sheets/source.md

列：key | zh-CN | translation（translation 留空，由译者填）

用法::

    python scripts/dev/export_i18n_sheet.py
    python scripts/dev/export_i18n_sheet.py --out docs/i18n/sheets/source.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ZH = ROOT / "app" / "i18n" / "locales" / "zh-CN.json"
DEFAULT_OUT = ROOT / "docs" / "i18n" / "sheets" / "source.md"


def walk(obj, prefix: str = "") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            rows.extend(walk(v, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{prefix}[{i}]"
            rows.extend(walk(v, p))
    elif isinstance(obj, str):
        rows.append((prefix, obj))
    elif obj is None or isinstance(obj, (int, float, bool)):
        rows.append((prefix, json.dumps(obj, ensure_ascii=False)))
    return rows


def md_cell(s: str) -> str:
    return (
        s.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("|", "\\|")
        .replace("\n", "<br>")
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    data = json.loads(ZH.read_text(encoding="utf-8"))
    rows = walk(data)

    lines = [
        "# locale: (fill by translator)",
        "# source: zh-CN",
        "",
        "翻译请复制本表，把文件另存为 `docs/i18n/sheets/<locale>.md`，",
        "文首改成 `# locale: en-US`，并填写 **translation** 列。规则见 `docs/i18n/给翻译AI.md`。",
        "",
        "| key | zh-CN | translation |",
        "|---|---|---|",
    ]
    for key, zh in rows:
        lines.append(f"| `{key}` | {md_cell(zh)} |  |")
    lines.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"已写出 {args.out.relative_to(ROOT)}（{len(rows)} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
