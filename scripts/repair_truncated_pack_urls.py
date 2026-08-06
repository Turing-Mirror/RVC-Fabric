# -*- coding: utf-8 -*-
"""Re-add thirdparty entries whose pack_url was truncated at spaces by bad YAML dump."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from batch_thirdparty_expand import CANDIDATES  # noqa: E402

TP = ROOT / "CNB-GIT-RELEASE" / "catalog-src" / "thirdparty"
CNB = ROOT / "CNB-GIT-RELEASE"


def pack_url_ok(text: str) -> bool:
    m = re.search(r"^pack_url:\s*(.+)$", text, re.M)
    if not m:
        return True
    url = m.group(1).strip().strip("\"'")
    # Truncated form ends mid-filename without .zip
    if url.endswith(".zip") or "%2Ezip" in url.lower() or url.lower().endswith("%2ezip"):
        return True
    # Multi-line broken: next non-empty line indented
    after = text.split("pack_url:", 1)[-1]
    lines = after.splitlines()
    if len(lines) >= 2 and lines[1].startswith("  ") and not lines[1].lstrip().startswith("#"):
        return False
    if " " in url and "%20" not in url:
        return False
    if not url.endswith(".zip"):
        return False
    return True


def main() -> int:
    py = sys.executable
    n = 0
    for c in CANDIDATES:
        if c.get("kind") != "pack":
            continue
        y = TP / f"{c['id']}.yaml"
        if not y.is_file():
            continue
        text = y.read_text(encoding="utf-8")
        if pack_url_ok(text):
            continue
        print("repair", c["id"], c.get("pack"))
        y.unlink()
        cmd = [
            py,
            str(ROOT / "scripts" / "add_thirdparty_voice.py"),
            "--hf",
            c["hf"],
            "--id",
            c["id"],
            "--name",
            c["name"],
            "--series",
            c.get("series") or "",
            "--tag",
            c.get("tag") or "女声",
            "--yes",
            "--endpoint",
            "https://hf-mirror.com",
            "--cnb",
            str(CNB),
            "--pack-path",
            c["pack"],
            "--no-cover",  # keep existing cover file on disk
        ]
        r = subprocess.run(cmd, cwd=str(ROOT))
        print(" ", "ok" if r.returncode == 0 else f"fail {r.returncode}")
        n += 1
    print("repaired", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
