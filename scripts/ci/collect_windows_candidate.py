"""Collect a cross-compiled test installer without publishing a release."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGET = "x86_64-pc-windows-msvc"


def main() -> None:
    version = json.loads((REPO / "app/package.json").read_text(encoding="utf-8"))["version"]
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()
    source = REPO / f"app/src-tauri/target/{TARGET}/release/bundle/nsis/RVC Fabric_{version}_x64-setup.exe"
    output = REPO / "dist/cnb-candidate"
    output.mkdir(parents=True, exist_ok=True)
    name = f"RVC_Fabric_{version}_cnb-{commit[:12]}_x64-setup.exe"
    installer = output / name
    shutil.copyfile(source, installer)
    with installer.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    (output / (name + ".sha256")).write_text(f"{digest}  {name}\n", encoding="utf-8")
    metadata = {
        "purpose": "Windows cross-compilation candidate for manual testing",
        "version": version,
        "commit": commit,
        "target": TARGET,
        "build_id": os.environ.get("CNB_BUILD_ID"),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "file": name,
        "size": installer.stat().st_size,
        "sha256": digest,
        "updater_signed": False,
        "published_to_production": False,
    }
    (output / "build-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    main()
