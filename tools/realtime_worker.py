# -*- coding: utf-8 -*-
"""Headless realtime VC worker entry.

Runs the same engine as gui_v1.py without FreeSimpleGUI window.
Main app controls it via User_Data/runtime_control/*.json.

Usage (from package root, Runtime python)::

    set TM_REALTIME_WORKER=1
    Runtime\\pythonw.exe tools\\realtime_worker.py
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def main() -> None:
    # Package root: parent of tools/
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.environ["TM_REALTIME_WORKER"] = "1"
    # Prefer package root for relative assets / configs
    os.environ.setdefault("TM_VOICE_ROOT", str(root))
    gui = root / "gui_v1.py"
    if not gui.is_file():
        raise SystemExit(f"gui_v1.py not found: {gui}")
    runpy.run_path(str(gui), run_name="__main__")


if __name__ == "__main__":
    main()
