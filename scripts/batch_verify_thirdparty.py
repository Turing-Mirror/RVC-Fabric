# -*- coding: utf-8 -*-
"""并行验证 thirdparty YAML（默认 2 路，用 Runtime python + torch）。"""
from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TP = ROOT / "CNB-GIT-RELEASE" / "catalog-src" / "thirdparty"
DRAFT = ROOT / "CNB-GIT-RELEASE" / "catalog-src" / "thirdparty-draft"


def needs(p: Path) -> bool:
    return "pth_struct_ok" not in p.read_text(encoding="utf-8", errors="replace")


def verify_one(py: str, yaml_path: Path) -> tuple[str, int]:
    r = subprocess.run(
        [
            py,
            "-u",
            str(ROOT / "scripts" / "verify_voice_pack.py"),
            "--yaml",
            str(yaml_path),
            "--write",
            "--endpoint",
            "https://hf-cdn.sufy.com",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = (r.stdout or "")[-800:] + "\n" + (r.stderr or "")[-400:]
    return f"{yaml_path.name} exit={r.returncode}\n{tail}", r.returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=str(ROOT / "Runtime" / "python.exe"))
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--move-fail",
        action="store_true",
        help="验证失败或仍缺 pth_struct_ok 的移到 thirdparty-draft",
    )
    args = ap.parse_args()
    py = args.python
    files = sorted(p for p in TP.glob("tp-*.yaml") if needs(p))
    if args.limit > 0:
        files = files[: args.limit]
    print(f"verify {len(files)} files, jobs={args.jobs}, py={py}", flush=True)
    ok = fail = 0
    failed_paths: list[Path] = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        futs = {ex.submit(verify_one, py, p): p for p in files}
        for fut in as_completed(futs):
            p = futs[fut]
            try:
                msg, code = fut.result()
            except Exception as e:  # noqa: BLE001
                msg, code = f"{p.name} exception {e}", 1
            print(msg, flush=True)
            print("-" * 40, flush=True)
            if code == 0 and p.is_file() and not needs(p):
                ok += 1
            else:
                fail += 1
                failed_paths.append(p)
    print(f"done ok={ok} fail={fail}", flush=True)
    if args.move_fail and failed_paths:
        DRAFT.mkdir(parents=True, exist_ok=True)
        for p in failed_paths:
            dest = DRAFT / p.name
            p.replace(dest)
            print(f"moved {p.name} -> thirdparty-draft/")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
