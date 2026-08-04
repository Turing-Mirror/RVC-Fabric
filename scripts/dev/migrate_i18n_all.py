# -*- coding: utf-8 -*-
"""全量把用户可见中文接入 i18n（不做翻译）。

做三件事：
1. 扫描前端 / Rust 用户可见字符串，写入 locale 的 ``s.<hash>`` 扁平区
2. 改写前端 .ts/.tsx：字面量 → ``t("s.xxx")``，JSX 文本 → ``{t("s.xxx")}``
3. 改写 Rust .rs：用户可见 ``"中文"`` → ``crate::i18n::t("s.xxx")``

语义 key（nav/dock/…）保留；``en-US`` 的 ``s`` 区留空，运行时回退 zh-CN。

用法::

    python scripts/dev/migrate_i18n_all.py           # 写语言包 + 改源码
    python scripts/dev/migrate_i18n_all.py --dry-run  # 只统计
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "app" / "src"
RUST = ROOT / "app" / "src-tauri" / "src"
LOCALE_DIR = ROOT / "app" / "i18n" / "locales"
ZH_PATH = LOCALE_DIR / "zh-CN.json"
EN_PATH = LOCALE_DIR / "en-US.json"

CJK = re.compile(r"[\u4e00-\u9fff]")

# 前端不改这些路径（语言包本体 / 已是 i18n 层）
SKIP_FE = {
    "i18n/dict.ts",
    "i18n/types.ts",
    "i18n/glossary.ts",
    "i18n/index.tsx",
    "i18n/t.ts",
    "vite-env.d.ts",
}

# Rust 不改 i18n 模块自身与 bin
SKIP_RS = {"i18n.rs"}

# 看起来不像 UI 文案（路径、日志内部、纯标点）
SKIP_TEXT = re.compile(
    r"^(https?://|file:|[A-Za-z]:\\|\\\\|\./|\.\./|User_Data|Runtime|configs/|"
    r"tools/|infer/|app/|src/|%|\{0\}|%s|%d|%f)"
)


def content_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def key_for(text: str) -> str:
    return f"s.{content_hash(text)}"


def blank_line_comments(text: str, prefixes: tuple[str, ...]) -> str:
    out = []
    for ln in text.split("\n"):
        st = ln.lstrip()
        if any(st.startswith(p) for p in prefixes):
            out.append("")
        else:
            out.append(ln)
    return "\n".join(out)


def blank_block_comments(text: str) -> str:
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j < 0:
                out.append("\n" * text[i:].count("\n"))
                break
            out.append("\n" * text[i : j + 2].count("\n"))
            i = j + 2
            continue
        nxt = text.find("/*", i)
        if nxt < 0:
            out.append(text[i:])
            break
        out.append(text[i:nxt])
        i = nxt
    return "".join(out)


def should_take(s: str) -> bool:
    s = s.strip()
    if not s or not CJK.search(s):
        return False
    if len(s) > 800:
        return False
    if SKIP_TEXT.search(s):
        return False
    # 纯代码碎片
    if re.fullmatch(r"[\w./\\:-]+", s) and not CJK.search(s.replace("_", "")):
        return False
    return True


def normalize_template(raw: str) -> tuple[str, list[str]]:
    """`hello ${foo.bar}` → (`hello {v0}`, ['foo.bar'])  for simple ${id} only."""
    vars_: list[str] = []

    def repl(m: re.Match) -> str:
        expr = m.group(1).strip()
        # only simple identifiers / dotted for safety
        if not re.fullmatch(r"[A-Za-z_$][\w.$]*", expr):
            return m.group(0)  # keep as-is → won't migrate this string
        idx = len(vars_)
        vars_.append(expr)
        return "{" + f"v{idx}" + "}"

    out = re.sub(r"\$\{([^}]+)\}", repl, raw)
    return out, vars_


# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------


def scan_ts_strings(path: Path) -> list[tuple[str, str]]:
    """Return list of (raw_literal_content, normalized_catalog_text)."""
    raw = path.read_text(encoding="utf-8")
    text = blank_line_comments(blank_block_comments(raw), ("//",))
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    # '...' "..." `...`  (no triple)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "'\"`":
            q = ch
            j = i + 1
            buf: list[str] = []
            while j < n:
                c = text[j]
                if c == "\\" and j + 1 < n:
                    buf.append(text[j : j + 2])
                    j += 2
                    continue
                if c == q:
                    content = "".join(buf)
                    # unescape lightly for catalog
                    cat = (
                        content.replace("\\n", "\n")
                        .replace("\\t", "\t")
                        .replace('\\"', '"')
                        .replace("\\'", "'")
                        .replace("\\\\", "\\")
                    )
                    if q == "`":
                        cat2, _vars = normalize_template(cat)
                        if "${" in cat2:  # complex template, skip catalog
                            pass
                        elif should_take(cat2) and cat2 not in seen:
                            seen.add(cat2)
                            found.append((content, cat2))
                    else:
                        if should_take(cat) and cat not in seen:
                            seen.add(cat)
                            found.append((content, cat))
                    i = j + 1
                    break
                if c == "\n" and q != "`":
                    i = j
                    break
                buf.append(c)
                j += 1
            else:
                break
            continue
        i += 1

    # JSX text >... <
    for m in re.finditer(r">([^<>{}]+)<", text):
        body = " ".join(m.group(1).split())
        if should_take(body) and body not in seen:
            if re.search(r"[;=]|=>", body):
                continue
            seen.add(body)
            found.append((body, body))
    return found


def scan_rs_strings(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8")
    text = blank_line_comments(blank_block_comments(raw), ("//",))
    found: list[str] = []
    seen: set[str] = set()
    i, n = 0, len(text)
    while i < n:
        # raw r#"..."#
        if text[i] in "rR":
            j = i + 1
            hashes = 0
            while j < n and text[j] == "#":
                hashes += 1
                j += 1
            if j < n and text[j] == '"':
                j += 1
                k = text.find('"' + "#" * hashes, j)
                if k < 0:
                    break
                cat = text[j:k]
                if should_take(cat) and cat not in seen:
                    seen.add(cat)
                    found.append(cat)
                i = k + 1 + hashes
                continue
        if text[i] == '"':
            j = i + 1
            buf: list[str] = []
            while j < n:
                c = text[j]
                if c == "\\" and j + 1 < n:
                    buf.append(text[j : j + 2])
                    j += 2
                    continue
                if c == '"':
                    cat = (
                        "".join(buf)
                        .replace("\\n", "\n")
                        .replace("\\t", "\t")
                        .replace('\\"', '"')
                        .replace("\\\\", "\\")
                    )
                    if should_take(cat) and cat not in seen:
                        seen.add(cat)
                        found.append(cat)
                    i = j + 1
                    break
                if c == "\n":
                    i = j
                    break
                buf.append(c)
                j += 1
            else:
                break
            continue
        i += 1
    return found


def collect_all() -> dict[str, str]:
    """key -> zh text"""
    catalog: dict[str, str] = {}

    for p in sorted(SRC.rglob("*.ts*")):
        if p.suffix not in (".ts", ".tsx"):
            continue
        rel = p.relative_to(SRC).as_posix()
        if rel in SKIP_FE or rel.startswith("i18n/"):
            continue
        for _raw, cat in scan_ts_strings(p):
            catalog[key_for(cat)] = cat

    for p in sorted(RUST.rglob("*.rs")):
        rel = p.relative_to(RUST).as_posix()
        if rel in SKIP_RS or rel.startswith("bin/"):
            continue
        for cat in scan_rs_strings(p):
            catalog[key_for(cat)] = cat

    return catalog


def merge_locales(catalog: dict[str, str]) -> tuple[dict, dict]:
    zh = json.loads(ZH_PATH.read_text(encoding="utf-8"))
    en = json.loads(EN_PATH.read_text(encoding="utf-8"))
    # flat s map
    s_zh = zh.get("s") if isinstance(zh.get("s"), dict) else {}
    s_en = en.get("s") if isinstance(en.get("s"), dict) else {}
    for k, text in catalog.items():
        # k is "s.abcdef" — store under s.abcdef key without double s
        short = k[2:] if k.startswith("s.") else k
        s_zh[short] = text
        # en: keep existing translation if any; else omit (fallback zh)
        if short not in s_en:
            pass
    zh["s"] = dict(sorted(s_zh.items(), key=lambda x: x[0]))
    en["s"] = dict(sorted(s_en.items(), key=lambda x: x[0]))
    return zh, en


# ---------------------------------------------------------------------------
# Rewrite frontend
# ---------------------------------------------------------------------------


def rel_import(from_file: Path) -> str:
    """Relative import path to app/src/i18n/t (no extension)."""
    import os

    target = SRC / "i18n" / "t"
    s = os.path.relpath(str(target), str(from_file.parent)).replace("\\", "/")
    if not s.startswith("."):
        s = "./" + s
    return s


def ensure_t_import(src: str, file: Path) -> str:
    # already has t from somewhere
    if re.search(
        r"""import\s*\{[^}]*\bt\b[^}]*\}\s*from\s*['\"][^'\"]*i18n""",
        src,
    ):
        return src
    # has tStatic from i18n — add t alias
    m = re.search(
        r"""import\s*\{([^}]+)\}\s*from\s*['\"]([^'\"]*i18n[^'\"]*)['\"]""",
        src,
    )
    if m:
        inner = m.group(1)
        path = m.group(2)
        if "tStatic" in inner and "as t" not in inner:
            inner2 = inner.replace("tStatic", "tStatic as t, tStatic", 1)
            return (
                src[: m.start()]
                + f'import {{ {inner2} }} from "{path}"'
                + src[m.end() :]
            )
        if "tStatic as t" in inner:
            return src
        return (
            src[: m.start()]
            + f'import {{ t, {inner.strip()} }} from "{path}"'
            + src[m.end() :]
        )
    imp = f'import {{ t }} from "{rel_import(file)}";'
    lines = src.split("\n")
    last_imp = -1
    for i, ln in enumerate(lines):
        if ln.startswith("import ") or ln.startswith("import\t"):
            last_imp = i
    if last_imp >= 0:
        lines.insert(last_imp + 1, imp)
        return "\n".join(lines)
    return imp + "\n" + src


def rewrite_frontend_file(path: Path, dry: bool) -> int:
    raw = path.read_text(encoding="utf-8")
    if "i18n/" in path.as_posix().replace("\\", "/") and path.name in (
        "dict.ts",
        "types.ts",
        "glossary.ts",
        "index.tsx",
        "t.ts",
    ):
        return 0

    text = raw
    count = 0

    # Work on a masked version for finding strings, apply on original carefully
    # Strategy: find string ranges in original with same scanner as collect

    replacements: list[tuple[int, int, str]] = []  # start, end, new

    def plan_string(start: int, end: int, quote: str, content: str) -> None:
        nonlocal count
        if quote == "`":
            cat, vars_ = normalize_template(
                content.replace("\\n", "\n")
                .replace("\\t", "\t")
                .replace("\\`", "`")
                .replace("\\\\", "\\")
            )
            if "${" in cat or not should_take(cat):
                return
            k = key_for(cat)
            if vars_:
                # t("s.xx", { v0: expr0, v1: expr1 })
                pairs = ", ".join(f"v{i}: {expr}" for i, expr in enumerate(vars_))
                new = f't("{k}", {{ {pairs} }})'
            else:
                new = f't("{k}")'
            replacements.append((start, end, new))
            count += 1
            return
        cat = (
            content.replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace('\\"', '"')
            .replace("\\'", "'")
            .replace("\\\\", "\\")
        )
        if not should_take(cat):
            return
        # already t("...") argument
        before = text[max(0, start - 20) : start]
        if re.search(r"""\bt\s*\(\s*$""", before) or re.search(
            r"""\btStatic\s*\(\s*$""", before
        ):
            return
        k = key_for(cat)
        # JSX attribute: title="中文" → title={t("s…")}
        before = text[max(0, start - 48) : start]
        if re.search(r"""[=\s]['"]$""", before) or (
            start > 0
            and text[start] in "'\""
            and re.search(r"""\w+\s*=\s*$""", text[max(0, start - 40) : start])
        ):
            # replace including quotes → {t("…")}
            replacements.append((start, end, f'{{t("{k}")}}'))
        else:
            replacements.append((start, end, f't("{k}")'))
        count += 1

    # scan original (with comments stripped only for detection — positions must match original)
    # Use original text but skip comment regions by building a mask
    mask = list(blank_line_comments(blank_block_comments(text), ("//",)))
    # blank_line_comments returns string
    masked = blank_line_comments(blank_block_comments(text), ("//",))
    # positions of non-comment code equal only if we blanked comments to same length —
    # block blank keeps newlines; line blank keeps empty lines. Character positions
    # for strings outside comments should align if we only blank comments to spaces?
    # Safer: scan original and skip if inside line comment.

    i, n = 0, len(text)
    while i < n:
        # skip // comments
        if text[i] == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if text[i] == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        ch = text[i]
        if ch in "'\"`":
            q = ch
            j = i + 1
            buf: list[str] = []
            while j < n:
                c = text[j]
                if c == "\\" and j + 1 < n:
                    buf.append(c)
                    buf.append(text[j + 1])
                    j += 2
                    continue
                if c == q:
                    content = "".join(buf)
                    plan_string(i, j + 1, q, content)
                    i = j + 1
                    break
                if c == "\n" and q != "`":
                    i = j
                    break
                buf.append(c)
                j += 1
            else:
                break
            continue
        i += 1

    # JSX text nodes
    for m in re.finditer(r">([^<>{}]+)<", text):
        body_raw = m.group(1)
        body = " ".join(body_raw.split())
        if not should_take(body) or re.search(r"[;=]|=>", body):
            continue
        # skip if only whitespace difference and already {t(...)}
        inner_start = m.start(1)
        # check not inside comment
        line_start = text.rfind("\n", 0, inner_start) + 1
        line_prefix = text[line_start:inner_start].lstrip()
        if line_prefix.startswith("//"):
            continue
        k = key_for(body)
        # replace the text inside > <
        replacements.append(
            (m.start(1), m.end(1), f'{{t("{k}")}}')
        )
        count += 1

    if not replacements:
        return 0

    # sort reverse and apply
    replacements.sort(key=lambda x: x[0], reverse=True)
    # drop overlapping (keep later/longer)
    applied: list[tuple[int, int, str]] = []
    for s, e, nw in replacements:
        if any(not (e <= a or s >= b) for a, b, _ in applied):
            continue
        applied.append((s, e, nw))

    out = text
    for s, e, nw in applied:
        out = out[:s] + nw + out[e:]

    out = ensure_t_import(out, path)
    if not dry and out != raw:
        path.write_text(out, encoding="utf-8")
    return len(applied)


# ---------------------------------------------------------------------------
# Rewrite Rust
# ---------------------------------------------------------------------------


def rewrite_rust_file(path: Path, dry: bool) -> int:
    if path.name == "i18n.rs":
        return 0
    raw = path.read_text(encoding="utf-8")
    text = raw
    count = 0
    replacements: list[tuple[int, int, str]] = []

    i, n = 0, len(text)
    while i < n:
        if text[i] == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if text[i] == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if text[i] == '"':
            j = i + 1
            buf: list[str] = []
            while j < n:
                c = text[j]
                if c == "\\" and j + 1 < n:
                    buf.append(text[j : j + 2])
                    j += 2
                    continue
                if c == '"':
                    cat = (
                        "".join(buf)
                        .replace("\\n", "\n")
                        .replace("\\t", "\t")
                        .replace('\\"', '"')
                        .replace("\\\\", "\\")
                    )
                    if should_take(cat):
                        before = text[max(0, i - 40) : i]
                        # skip include_str! and already i18n::t(
                        if "include_str!" in before[-20:]:
                            pass
                        elif re.search(r"i18n::t(?:_vars)?\s*\(\s*$", before):
                            pass
                        elif re.search(r"concat!\s*\(\s*$", before):
                            pass
                        else:
                            k = key_for(cat)
                            # format!("...{}", x) is hard — only plain strings
                            # If string has {} placeholders, use t() still (placeholders stay in catalog)
                            # Caller must use format after t for dynamic parts — leave format! alone if has { and not doubled
                            if re.search(r"\{[^{]", cat) and "format!" in before:
                                # leave complex format! for manual
                                pass
                            else:
                                replacements.append(
                                    (i, j + 1, f'crate::i18n::t("{k}")')
                                )
                                count += 1
                    i = j + 1
                    break
                if c == "\n":
                    i = j
                    break
                buf.append(c)
                j += 1
            else:
                break
            continue
        i += 1

    if not replacements:
        return 0
    replacements.sort(key=lambda x: x[0], reverse=True)
    out = text
    for s, e, nw in replacements:
        out = out[:s] + nw + out[e:]
    if not dry and out != raw:
        path.write_text(out, encoding="utf-8")
    return len(replacements)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--catalog-only", action="store_true", help="只写语言包不改源码")
    args = ap.parse_args()

    catalog = collect_all()
    print(f"收集到 {len(catalog)} 条唯一中文用户串")

    zh, en = merge_locales(catalog)
    if not args.dry_run:
        ZH_PATH.write_text(
            json.dumps(zh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        EN_PATH.write_text(
            json.dumps(en, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"已写入 {ZH_PATH.relative_to(ROOT)} / en-US（s 区 {len(zh.get('s', {}))} 条）")

    if args.catalog_only:
        return 0

    fe_n = 0
    for p in sorted(SRC.rglob("*.ts*")):
        if p.suffix not in (".ts", ".tsx"):
            continue
        rel = p.relative_to(SRC).as_posix()
        if rel in SKIP_FE or rel.startswith("i18n/"):
            continue
        fe_n += rewrite_frontend_file(p, args.dry_run)
    print(f"前端替换约 {fe_n} 处")

    rs_n = 0
    for p in sorted(RUST.rglob("*.rs")):
        rel = p.relative_to(RUST).as_posix()
        if rel in SKIP_RS or rel.startswith("bin/"):
            continue
        rs_n += rewrite_rust_file(p, args.dry_run)
    print(f"Rust 替换约 {rs_n} 处")

    if args.dry_run:
        print("(dry-run，未写盘)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
