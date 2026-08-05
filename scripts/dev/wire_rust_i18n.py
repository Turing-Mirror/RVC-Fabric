# -*- coding: utf-8 -*-
"""Wire Rust user-facing Chinese format!/Err via i18n::te / t2 / t.

Handles:
  format!("…{e}")              # implicit capture (Rust 2021)
  format!("…{}", x)
  format!("…{}…{}", a, b)
  format!("plain")
  "中文".into() / .to_string()

  python scripts/dev/wire_rust_i18n.py
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RS = ROOT / "app" / "src-tauri" / "src"
LOCALES = ROOT / "app" / "i18n" / "locales"
CODES = [
    "zh-CN",
    "zh-TW",
    "en-US",
    "ja-JP",
    "ko-KR",
    "es-ES",
    "fr-FR",
    "ru-RU",
]
CN = re.compile(r"[\u4e00-\u9fff]")


def key_of(zh: str) -> str:
    return "s." + hashlib.sha1(zh.encode("utf-8")).hexdigest()[:10]


def load_packs():
    return {
        c: json.loads((LOCALES / f"{c}.json").read_text(encoding="utf-8"))
        for c in CODES
    }


def save_packs(packs):
    for c, d in packs.items():
        (LOCALES / f"{c}.json").write_text(
            json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def ensure_key(packs, zh: str) -> str:
    s = packs["zh-CN"].setdefault("s", {})
    for k, v in s.items():
        if v == zh:
            return f"s.{k}"
    name = key_of(zh)[2:]
    for p in packs.values():
        p.setdefault("s", {})[name] = zh
    return f"s.{name}"


def unesc(lit: str) -> str:
    body = lit[1:-1]
    return (
        body.replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\r", "\r")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


def is_log_line(line: str) -> bool:
    s = line.strip()
    return any(
        x in s
        for x in ("shell_log!", "println!", "eprintln!", "debug!", "trace!", "log::")
    ) or s.startswith("//")


# format!("text") no extra args
RE_FMT_0 = re.compile(r'format!\s*\(\s*("(?:\\.|[^"\\])*")\s*\)')

# format!("text {name}") single named, no extra args (implicit capture)
RE_FMT_NAMED0 = re.compile(
    r'format!\s*\(\s*("(?:\\.|[^"\\])*")\s*\)'
)

# format!("…", arg) single arg
RE_FMT_1 = re.compile(
    r'format!\s*\(\s*("(?:\\.|[^"\\])*")\s*,\s*([^)]+)\)'
)


def placeholders(fmt: str) -> list[str]:
    return re.findall(r"\{([^{}:]*)(?::[^{}]*)?\}", fmt)


def process_line(line: str, packs: dict) -> tuple[str, int]:
    if is_log_line(line) or not CN.search(line) or "format!" not in line and "into()" not in line and ".to_string()" not in line:
        # still handle into/to_string without format
        n = 0
        if CN.search(line) and not is_log_line(line):

            def into_sub(m):
                nonlocal n
                s = unesc(m.group(1))
                if not CN.search(s) or "{" in s:
                    return m.group(0)
                k = ensure_key(packs, s)
                n += 1
                return f'crate::i18n::t("{k}").into()'

            line2 = re.sub(
                r'("(?:\\.|[^"\\])*")\s*\.into\s*\(\s*\)', into_sub, line
            )
            return line2, n
        return line, 0

    n = 0

    # Try format! with args first (greedy enough)
    def fmt1(m):
        nonlocal n
        lit, args = m.group(1), m.group(2).strip()
        fmt = unesc(lit)
        if not CN.search(fmt):
            return m.group(0)
        ph = placeholders(fmt)
        # split args by top-level comma
        parts = split_args(args)
        if len(ph) == 1 and len(parts) == 1:
            name = ph[0]
            if ":" in name:
                return m.group(0)
            if name == "":
                tmpl = re.sub(r"\{\}", "{a0}", fmt, count=1)
            elif name in ("e", "a0"):
                tmpl = fmt
            else:
                # {exp} -> {a0}
                tmpl = fmt.replace("{" + name + "}", "{a0}")
            k = ensure_key(packs, tmpl)
            n += 1
            a = parts[0]
            if not a.startswith("&"):
                a = f"&({a})"
            return f'crate::i18n::te("{k}", {a})'
        if len(ph) == 2 and len(parts) == 2:
            if any(":" in p for p in ph):
                return m.group(0)
            tmpl = fmt
            # map each placeholder to a0/a1
            for i, name in enumerate(ph):
                token = "{a%d}" % i
                if name == "":
                    tmpl = re.sub(r"\{\}", token, tmpl, count=1)
                else:
                    tmpl = tmpl.replace("{" + name + "}", token)
            k = ensure_key(packs, tmpl)
            n += 1
            a0, a1 = parts[0], parts[1]
            if not a0.startswith("&"):
                a0 = f"&({a0})"
            if not a1.startswith("&"):
                a1 = f"&({a1})"
            return f'crate::i18n::t2("{k}", {a0}, {a1})'
        return m.group(0)

    line2 = RE_FMT_1.sub(fmt1, line)

    # format!("…{e}") no args — implicit
    def fmt0(m):
        nonlocal n
        fmt = unesc(m.group(1))
        if not CN.search(fmt):
            return m.group(0)
        ph = placeholders(fmt)
        if not ph:
            k = ensure_key(packs, fmt)
            n += 1
            return f'crate::i18n::t("{k}")'
        if len(ph) == 1 and ph[0] and not ph[0][0].isdigit():
            # implicit capture name
            name = ph[0].split(":")[0] if ":" in ph[0] else ph[0]
            if ":" in (ph[0] or ""):
                return m.group(0)  # format specs — skip
            k = ensure_key(packs, fmt)
            n += 1
            return f'crate::i18n::te("{k}", &({name}))'
        return m.group(0)

    line2 = RE_FMT_0.sub(fmt0, line2)

    def into_sub(m):
        nonlocal n
        s = unesc(m.group(1))
        if not CN.search(s) or "{" in s:
            return m.group(0)
        k = ensure_key(packs, s)
        n += 1
        return f'crate::i18n::t("{k}").into()'

    line2 = re.sub(r'("(?:\\.|[^"\\])*")\s*\.into\s*\(\s*\)', into_sub, line2)
    return line2, n


def split_args(s: str) -> list[str]:
    parts = []
    depth = 0
    cur = []
    for ch in s:
        if ch in "([{":
            depth += 1
            cur.append(ch)
        elif ch in ")]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return [p for p in parts if p]


def process_file(text: str, packs: dict) -> tuple[str, int]:
    total = 0
    out = []
    for line in text.splitlines(keepends=True):
        # strip keepends for processing
        ending = ""
        body = line
        if line.endswith("\r\n"):
            ending = "\r\n"
            body = line[:-2]
        elif line.endswith("\n"):
            ending = "\n"
            body = line[:-1]
        new, n = process_line(body, packs)
        total += n
        out.append(new + ending)
    return "".join(out), total


def main():
    packs = load_packs()
    total = 0
    for path in sorted(RS.rglob("*.rs")):
        if path.name == "i18n.rs":
            continue
        text = path.read_text(encoding="utf-8")
        new, n = process_file(text, packs)
        if n:
            path.write_text(new, encoding="utf-8")
            print(f"{path.relative_to(ROOT)}: {n}")
            total += n
    save_packs(packs)
    print("total", total)


if __name__ == "__main__":
    main()
