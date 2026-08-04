# -*- coding: utf-8 -*-
"""从 extract 结果生成 key 草案（docs/i18n/keys-draft.*）。

语义化 key 写在 app/i18n/locales/*.json；本脚本把尚未迁入语义包的原文
编成稳定 hash key，方便翻译排期与对账。

用法::

    python scripts/dev/extract_i18n_strings.py
    python scripts/dev/build_i18n_catalog.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

# reuse extractors
from extract_i18n_strings import (  # type: ignore
    FRONTEND_SECTIONS,
    PYTHON_PATHS,
    RUST_SECTIONS,
    extract_frontend,
    extract_python,
    extract_rust,
)

OUT_DIR = ROOT / "docs" / "i18n"
LOCALE_ZH = ROOT / "app" / "i18n" / "locales" / "zh-CN.json"
CJK = re.compile(r"[\u4e00-\u9fff]")


def flat_strings(obj, prefix="") -> set[str]:
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else k
            out |= flat_strings(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out |= flat_strings(v, f"{prefix}[{i}]")
    elif isinstance(obj, str) and CJK.search(obj):
        out.add(obj)
    return out


def slug_key(layer: str, section: str, text: str) -> str:
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    sec = re.sub(r"[^a-zA-Z0-9_]+", "_", section)[:40].strip("_").lower() or "x"
    return f"auto.{layer}.{sec}.{h}"


def main() -> int:
    covered: set[str] = set()
    if LOCALE_ZH.is_file():
        covered = flat_strings(json.loads(LOCALE_ZH.read_text(encoding="utf-8")))

    draft: dict[str, dict] = {}
    remaining = 0

    def add(layer: str, section: str, file: str, line: int, text: str) -> None:
        nonlocal remaining
        if text in covered:
            return
        key = slug_key(layer, section, text)
        if key in draft:
            draft[key]["sources"].append(f"{file}:{line}")
            return
        draft[key] = {
            "zh-CN": text,
            "en-US": "",  # translator fills
            "section": section,
            "sources": [f"{file}:{line}"],
        }
        remaining += 1

    src = ROOT / "app" / "src"
    for rel, title in FRONTEND_SECTIONS:
        p = src / rel
        if not p.is_file():
            continue
        for line, s in extract_frontend(p):
            add("frontend", title, f"app/src/{rel}", line, s)

    rsrc = ROOT / "app" / "src-tauri" / "src"
    known = {r for r, _ in RUST_SECTIONS}
    for rel, title in RUST_SECTIONS:
        p = rsrc / rel
        if not p.is_file():
            continue
        for line, s in extract_rust(p):
            add("rust", title, f"app/src-tauri/src/{rel}", line, s)
    for p in sorted(rsrc.rglob("*.rs")):
        rel = p.relative_to(rsrc).as_posix()
        if rel in known:
            continue
        for line, s in extract_rust(p):
            add("rust", rel, f"app/src-tauri/src/{rel}", line, s)

    for rel, title in PYTHON_PATHS:
        p = ROOT / rel
        if not p.is_file():
            continue
        for line, s in extract_python(p):
            add("python", title, rel, line, s)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "keys-draft.json"
    out_json.write_text(
        json.dumps(draft, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Markdown index for translators
    lines = [
        "# i18n key 草案（未迁入语义包）",
        "",
        f"已在 `app/i18n/locales/zh-CN.json` 语义化的原文：**{len(covered)}** 条（含子串级字符串）。",
        f"本表剩余待迁/待译：**{len(draft)}** 条。",
        "",
        "生成：`python scripts/dev/build_i18n_catalog.py`",
        "",
        "| key | zh-CN | en-US | 出处 |",
        "|---|---|---|---|",
    ]
    for key, row in sorted(draft.items(), key=lambda x: x[0]):
        zh = row["zh-CN"].replace("|", "\\|").replace("\n", "<br>")
        src0 = row["sources"][0]
        extra = f" +{len(row['sources'])-1}" if len(row["sources"]) > 1 else ""
        lines.append(f"| `{key}` | {zh} |  | `{src0}`{extra} |")
    lines.append("")
    (OUT_DIR / "keys-draft.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"语义包已覆盖字符串约 {len(covered)} 条")
    print(f"草案 {len(draft)} 条 → {out_json.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
