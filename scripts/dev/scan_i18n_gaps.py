# -*- coding: utf-8 -*-
"""Scan product code for user-visible Chinese not yet behind i18n.

Writes:
  docs/i18n/gaps/scan-raw.json
  docs/i18n/gaps/MISSING.md          — inventory for engineers
  docs/i18n/sheets/source-missing.md — translator sheet (proposed keys)

Run from repo root:
  python scripts/dev/scan_i18n_gaps.py
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CN = re.compile(r"[\u4e00-\u9fff]")
STR_DQ = re.compile(r'"((?:\\.|[^"\\])*)"')
STR_SQ = re.compile(r"'((?:\\.|[^'\\])*)'")
STR_BT = re.compile(r"`([^`]*)`")

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    "target",
    "dist",
    "CNB-GIT-RELEASE",
    "docs",
    "__pycache__",
    "Runtime",
    "models",
    "assets",
    ".venv",
    "venv",
    "cargo-target",
    "bundle",
    "reference-screenshots",
}


def should_skip(p: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in p.parts):
        return True
    if p.name.endswith((".d.ts", ".map", ".lock", ".pyc")):
        return True
    return False


def normalize_template(s: str) -> str:
    """Turn JS `${expr}` / Rust `{}` style into translator-friendly {p0}…"""
    s = s.replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\$\{[^}]+\}", lambda m, c=iter(range(20)): f"{{p{next(c)}}}", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def looks_user_facing(s: str) -> bool:
    if not CN.search(s):
        return False
    s2 = s.strip()
    if len(s2) < 2:
        return False
    if re.match(r"^[A-Za-z0-9_./\\:-]+$", s2):
        return False
    if "http://" in s2 or "https://" in s2:
        return False
    if len(s2) > 400:
        return False
    # pure code / type fragments
    if s2.startswith("#[") or s2.startswith("@"):
        return False
    # almost only interpolation (e.g. `${m} 分`) still OK if has CN
    # drop if after strip of ${} almost no Chinese letters left and length tiny
    plain = re.sub(r"\$\{[^}]+\}", "", s2)
    plain = re.sub(r"\{[^}]+\}", "", plain)
    if not CN.search(plain) and len(plain.strip()) < 2:
        return False
    return True


def is_comment_line(line: str, lang: str) -> bool:
    s = line.strip()
    if lang in ("ts", "tsx", "rs", "js"):
        return s.startswith("//") or s.startswith("*") or s.startswith("/*")
    if lang == "py":
        return s.startswith("#")
    return False


def extract_line_strings(line: str) -> list[str]:
    out: list[str] = []
    for rx in (STR_DQ, STR_SQ, STR_BT):
        for m in rx.finditer(line):
            out.append(m.group(1))
    return out


def extract_file(path: Path, lang: str) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    found: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if is_comment_line(line, lang):
            continue
        if re.match(r"^\s*(import |from |use |#\[|//!|///|export type |type )", line):
            continue
        for s in extract_line_strings(line):
            if not looks_user_facing(s):
                continue
            ctx = line.strip()[:200]
            # skip i18n key-only lines: t("s.xxx") without other CN
            outside = re.sub(r"\bi18n::t\s*\([^)]*\)", "", ctx)
            outside = re.sub(r"\bt\s*\([^)]*\)", "", outside)
            outside = re.sub(r"\btStatic\s*\([^)]*\)", "", outside)
            outside = re.sub(r"\btMsg\s*\([^)]*\)", "", outside)
            # if Chinese only appears inside already-removed t() calls, drop
            if not CN.search(outside) and ("t(" in ctx or "i18n::t" in ctx):
                # still keep if the string itself IS the chinese (format! "中文")
                # which appears as a literal in format!/Err
                if not re.search(
                    r'(format!|anyhow!|bail!|Err\(|error!|warn!|println!|eprintln!|setMsg|setBusy|setUpdate|setLegacy|setGpu|setVb|message:|notes:|label:|title:|desc:|throw |return ")',
                    ctx,
                ):
                    # check: is this chinese the value of t()? then skip
                    if re.search(r'\bt\(\s*["\'][^"\']*["\']', ctx) and s not in re.findall(
                        r'["\']([^"\']*[\u4e00-\u9fff][^"\']*)["\']', ctx
                    ):
                        continue
            raw = s.replace("\n", " ").strip()
            found.append(
                {
                    "file": path.relative_to(ROOT).as_posix(),
                    "line": lineno,
                    "text": normalize_template(raw),
                    "text_raw": raw,
                    "ctx": ctx,
                }
            )
    return found


def classify_frontend_hit(hit: dict) -> str:
    ctx = hit["ctx"]
    text = hit["text"]
    if re.search(r"set(Msg|Busy|Update|Legacy|Gpu|Vb|Error|Line)\(", ctx):
        return "ui_status_error"
    if re.search(r"(title|label|desc|placeholder|children|aria-)", ctx, re.I):
        return "ui_label"
    if "`" in ctx or "format" in ctx.lower():
        return "ui_template"
    if "console." in ctx or "ui_log" in ctx:
        return "dev_log"
    if len(text) <= 4 and text in ("是", "否", "无", "有"):
        return "short_token"
    return "ui_literal"


def classify_rust_hit(hit: dict) -> str:
    ctx = hit["ctx"]
    if "shell_log!" in ctx or "eprintln!" in ctx or "println!" in ctx:
        return "dev_log"
    if "format!" in ctx or "Err(" in ctx or "return Err" in ctx:
        return "user_error"
    if "message" in ctx.lower() or "notes" in ctx:
        return "user_message"
    if "tray" in ctx.lower() or "menu" in ctx.lower():
        return "tray_menu"
    return "rust_literal"


def propose_key(text: str) -> str:
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"s.{h}"


def load_existing_values() -> set[str]:
    """All zh-CN values already in locale pack (leaf strings)."""
    path = ROOT / "app" / "i18n" / "locales" / "zh-CN.json"
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    out: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and CN.search(o):
            out.add(o)

    walk(data)
    return out


def main() -> None:
    existing = load_existing_values()

    areas: dict[str, list[dict]] = {
        "frontend": [],
        "rust": [],
        "engine_py": [],
    }

    for p in (ROOT / "app" / "src").rglob("*"):
        if p.suffix not in (".ts", ".tsx") or should_skip(p):
            continue
        lang = "tsx" if p.suffix == ".tsx" else "ts"
        areas["frontend"].extend(extract_file(p, lang))

    for p in (ROOT / "app" / "src-tauri" / "src").rglob("*.rs"):
        if should_skip(p):
            continue
        areas["rust"].extend(extract_file(p, "rs"))

    for eng in ("gui_v1.py", "infer", "tools", "i18n"):
        # product engine tree if present at root or under engine-payload
        for base in (ROOT, ROOT / "app" / "src-tauri" / "engine-payload", ROOT / "resources"):
            root = base / eng if eng != "gui_v1.py" else base / "gui_v1.py"
            if eng == "gui_v1.py":
                if root.is_file():
                    areas["engine_py"].extend(extract_file(root, "py"))
                continue
            if root.is_dir():
                for p in root.rglob("*.py"):
                    if should_skip(p):
                        continue
                    areas["engine_py"].extend(extract_file(p, "py"))

    # also configs help if any
    for p in ROOT.glob("*.py"):
        if p.name.startswith("gui") or p.name in ("app.py", "webui.py"):
            areas["engine_py"].extend(extract_file(p, "py"))

    # dedupe + classify + filter already-i18n identical values that are only
    # used as fallback display of known keys — keep for location reporting
    for area, hits in areas.items():
        uniq = []
        seen = set()
        for h in hits:
            key = (h["file"], h["line"], h["text"])
            if key in seen:
                continue
            seen.add(key)
            if area == "frontend":
                h["class"] = classify_frontend_hit(h)
            elif area == "rust":
                h["class"] = classify_rust_hit(h)
            else:
                h["class"] = "engine"
            h["already_in_zh_cn_pack"] = h["text"] in existing
            h["proposed_key"] = propose_key(h["text"])
            uniq.append(h)
        areas[area] = uniq

    # drop pure dev_log from "must i18n" but keep in raw
    must: dict[str, list[dict]] = {}
    for area, hits in areas.items():
        must[area] = [h for h in hits if h["class"] not in ("dev_log",)]

    # unique texts for translator sheet (frontend+rust user-facing only first)
    sheet_rows: list[dict] = []
    seen_text: set[str] = set()
    for area in ("frontend", "rust"):
        for h in must[area]:
            t = h["text"]
            if t in seen_text:
                continue
            # skip if exact text already in pack AND only appears inside known
            # catalog-like short names? still need wiring — keep if not already_in
            if h["already_in_zh_cn_pack"] and h["class"] in ("short_token",):
                continue
            seen_text.add(t)
            sheet_rows.append(
                {
                    "key": h["proposed_key"],
                    "zh-CN": t,
                    "area": area,
                    "class": h["class"],
                    "sample": f"{h['file']}:{h['line']}",
                    "already_in_pack": h["already_in_zh_cn_pack"],
                }
            )

    # engine unique (separate section — large)
    engine_rows = []
    eng_seen = set()
    for h in must.get("engine_py", []):
        t = h["text"]
        if t in eng_seen:
            continue
        eng_seen.add(t)
        engine_rows.append(
            {
                "key": propose_key(t),
                "zh-CN": t,
                "sample": f"{h['file']}:{h['line']}",
            }
        )

    gaps_dir = ROOT / "docs" / "i18n" / "gaps"
    sheets_dir = ROOT / "docs" / "i18n" / "sheets"
    gaps_dir.mkdir(parents=True, exist_ok=True)
    sheets_dir.mkdir(parents=True, exist_ok=True)

    raw_path = gaps_dir / "scan-raw.json"
    raw_path.write_text(
        json.dumps(
            {
                "generated": date.today().isoformat(),
                "counts": {k: len(v) for k, v in areas.items()},
                "must_counts": {k: len(v) for k, v in must.items()},
                "unique_shell_strings": len(sheet_rows),
                "unique_engine_strings": len(engine_rows),
                "areas": areas,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # MISSING.md inventory
    lines = [
        f"# i18n 缺口清单（扫描日 {date.today().isoformat()}）",
        "",
        "> 由 `python scripts/dev/scan_i18n_gaps.py` 生成。",
        "> **目标**：壳层（React + Rust host）用户可见文案 100% 走 `t()` / `i18n::t`；",
        "> 引擎 Python / 远端 catalog 另列。",
        "",
        "## 统计",
        "",
        "| 区域 | 命中（含日志） | 建议纳入 i18n | 去重原文 |",
        "|---|---:|---:|---:|",
    ]
    for area in ("frontend", "rust", "engine_py"):
        lines.append(
            f"| {area} | {len(areas[area])} | {len(must[area])} | "
            f"{len({h['text'] for h in must[area]})} |"
        )
    lines += [
        "",
        f"- 壳层待补去重串：**{len(sheet_rows)}**（见 `sheets/source-missing.md`）",
        f"- 引擎 Python 去重串：**{len(engine_rows)}**（见 `gaps/engine-missing.md`）",
        f"- 其中原文已出现在 zh-CN 包、但代码仍硬编码：**"
        f"{sum(1 for r in sheet_rows if r['already_in_pack'])}**（只需接线，不必重译）",
        "",
        "## 优先级",
        "",
        "| 优先级 | 类别 | 说明 |",
        "|---|---|---|",
        "| P0 | `ui_status_error` / `user_error` / `user_message` | 用户直接看到的失败/状态 |",
        "| P1 | `ui_label` / `ui_template` / `ui_literal` | 界面标签、模板拼接 |",
        "| P2 | `tray_menu` | 托盘（若尚未走 tray.*） |",
        "| P3 | `engine` | 引擎 Gradio/worker 文案（大更新才动） |",
        "| — | `dev_log` | 开发日志，**不要求** i18n |",
        "",
        "## 壳层明细（按文件）",
        "",
    ]

    by_file: dict[str, list[dict]] = defaultdict(list)
    for area in ("frontend", "rust"):
        for h in must[area]:
            by_file[h["file"]].append(h)

    for fpath in sorted(by_file.keys()):
        hits = by_file[fpath]
        lines.append(f"### `{fpath}`（{len(hits)}）")
        lines.append("")
        lines.append("| 行 | 类 | 已有包 | 原文 |")
        lines.append("|---:|---|:---:|---|")
        for h in sorted(hits, key=lambda x: x["line"])[:80]:
            flag = "Y" if h["already_in_zh_cn_pack"] else ""
            text = h["text"].replace("|", "\\|")
            if len(text) > 80:
                text = text[:77] + "…"
            lines.append(
                f"| {h['line']} | {h['class']} | {flag} | {text} |"
            )
        if len(hits) > 80:
            lines.append(f"| … | | | *另有 {len(hits) - 80} 条，见 scan-raw.json* |")
        lines.append("")

    lines += [
        "## 远端 / 清单（扫描器不覆盖，人工登记）",
        "",
        "| 来源 | 现状 | 建议 |",
        "|---|---|---|",
        "| `CNB-GIT-RELEASE/catalog-src/changelog.yaml` | 仅中文 | 增 `notes_en`/`notes_ja` 或客户端按 locale 选 |",
        "| `catalog-src/plaza.yaml` 投放 | 仅中文 | 同上 |",
        "| `catalog-src/extras/*.yaml` label/notes | 中文源；壳层已有 `extras.items.*` 覆盖层 | 保持 YAML 中文权威，UI 优先 locale |",
        "| `catalog-src/voices/*` tag/desc | 中文；name_* 已部分多语言 | tag/desc 补 `tag_ja`/`desc_en` 等 |",
        "| 社区第三方音色元数据 | 作者自填 | 显示规则：有多语言字段用字段，否则原文 |",
        "",
        "## 下一步（工程）",
        "",
        "1. 按 `sheets/source-missing.md` 让翻译 AI 补译文（已有包内串可跳过 translation）。",
        "2. 接线：硬编码 → `t(\"s.xxx\")` / `i18n::t`；禁止模块级 `t()`。",
        "3. `python scripts/dev/scan_i18n_gaps.py` 复查至壳层 must≈0。",
        "4. 引擎与 catalog 分里程碑，勿与壳层 OTA 绑死。",
        "",
    ]
    (gaps_dir / "MISSING.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # engine-missing.md (summary only if huge)
    eng_lines = [
        f"# 引擎 Python 文案缺口（{date.today().isoformat()}）",
        "",
        f"共 **{len(engine_rows)}** 条去重中文串。引擎走大更新包，不必与壳层同 PR。",
        "",
        "| key（建议） | zh-CN | 样例位置 |",
        "|---|---|---|",
    ]
    for r in engine_rows[:500]:
        z = r["zh-CN"].replace("|", "\\|")
        if len(z) > 60:
            z = z[:57] + "…"
        eng_lines.append(f"| `{r['key']}` | {z} | `{r['sample']}` |")
    if len(engine_rows) > 500:
        eng_lines.append(f"| … | *另有 {len(engine_rows) - 500} 条* | scan-raw.json |")
    eng_lines.append("")
    (gaps_dir / "engine-missing.md").write_text("\n".join(eng_lines) + "\n", encoding="utf-8")

    # Split: need_translate vs wire_only (already in pack)
    need_tr = [r for r in sheet_rows if not r["already_in_pack"]]
    wire_only = [r for r in sheet_rows if r["already_in_pack"]]

    def sheet_table(rows: list[dict], title: str, intro: str) -> str:
        lines = [
            title,
            "",
            intro,
            "",
            "| key | zh-CN | translation | area | sample |",
            "|---|---|---|---|---|",
        ]
        for r in rows:
            z = r["zh-CN"].replace("|", "\\|").replace("\n", "<br>")
            lines.append(
                f"| `{r['key']}` | {z} |  | {r['area']} | `{r['sample']}` |"
            )
        lines.append("")
        return "\n".join(lines)

    sheet_body = "\n".join(
        [
            "# locale: (fill by translator)",
            "# source: zh-CN",
            "# batch: missing-shell-after-1.4.1",
            "",
            "本表仅含**代码中仍硬编码**的壳层中文（`scan_i18n_gaps.py` 生成）。",
            "规则见 `docs/i18n/给翻译AI.md`。",
            "",
            f"- **需翻译**：{len(need_tr)} 条（zh-CN 包尚无同文）",
            f"- **仅接线**：{len(wire_only)} 条（包内已有同文，translation 可留空，工程对 key）",
            "",
            "模板里的 `{p0}` `{p1}` … 对应代码里的插值，**译文中必须保留相同占位符**。",
            "",
            sheet_table(
                need_tr,
                "## A. 需翻译（优先）",
                "请填写 **translation** 列。key 由扫描生成，工程 merge 时入库。",
            ),
            sheet_table(
                wire_only,
                "## B. 仅接线（可不译）",
                "原文已在 `zh-CN.json`；工程应改为 `t(已有key)`，本表 key 仅作对照。",
            ),
        ]
    )
    (sheets_dir / "source-missing.md").write_text(sheet_body + "\n", encoding="utf-8")

    # compact engineer checklist: P0 errors only
    p0 = [
        h
        for area in ("frontend", "rust")
        for h in must[area]
        if h["class"] in ("ui_status_error", "user_error", "user_message")
    ]
    p0_lines = [
        f"# P0 用户错误/状态硬编码（{date.today().isoformat()}）",
        "",
        f"共 {len(p0)} 处。优先改这些，用户切语言后最敏感。",
        "",
        "| 文件:行 | 类 | 原文 |",
        "|---|---|---|",
    ]
    for h in sorted(p0, key=lambda x: (x["file"], x["line"])):
        z = h["text"].replace("|", "\\|")
        if len(z) > 70:
            z = z[:67] + "…"
        p0_lines.append(f"| `{h['file']}:{h['line']}` | {h['class']} | {z} |")
    p0_lines.append("")
    (gaps_dir / "P0-errors.md").write_text("\n".join(p0_lines) + "\n", encoding="utf-8")

    print("frontend", len(areas["frontend"]), "must", len(must["frontend"]))
    print("rust", len(areas["rust"]), "must", len(must["rust"]))
    print("engine", len(areas["engine_py"]), "must", len(must["engine_py"]))
    print("sheet_rows", len(sheet_rows), "engine_rows", len(engine_rows))
    print("wrote", raw_path)
    print("wrote", gaps_dir / "MISSING.md")
    print("wrote", gaps_dir / "engine-missing.md")
    print("wrote", sheets_dir / "source-missing.md")


if __name__ == "__main__":
    main()
