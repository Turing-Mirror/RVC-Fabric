# -*- coding: utf-8 -*-
"""Percent-encode pack_url / pth_url / index_url path segments in thirdparty YAML."""
from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TP = ROOT / "CNB-GIT-RELEASE" / "catalog-src" / "thirdparty"
KEYS = ("pack_url", "pth_url", "index_url")


def fix_url(url: str) -> str:
    url = url.strip().strip('"').strip("'")
    if not any(h in url for h in ("huggingface.co", "hf-mirror.com", "hf-cdn.sufy.com")):
        return url
    parts = urllib.parse.urlsplit(url)
    segs = []
    for s in parts.path.split("/"):
        if not s:
            segs.append(s)
            continue
        segs.append(urllib.parse.quote(urllib.parse.unquote(s), safe=""))
    path = "/".join(segs)
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, path, parts.query, parts.fragment)
    )


def main() -> None:
    n = 0
    for p in sorted(TP.glob("tp-*.yaml")):
        text = p.read_text(encoding="utf-8")
        orig = text

        def repl(m: re.Match[str]) -> str:
            key = m.group(1)
            return f"{key}: {fix_url(m.group(2))}"

        text = re.sub(
            r"^(pack_url|pth_url|index_url):\s*(.+)$",
            repl,
            text,
            flags=re.M,
        )
        if text != orig:
            p.write_text(text, encoding="utf-8")
            n += 1
            print("fixed", p.name)
    print("total fixed", n)


if __name__ == "__main__":
    main()
