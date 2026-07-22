# -*- coding: utf-8 -*-
"""DEPRECATED — do not use as the product Setup.

Official installer is **Inno Setup**::

    installer/RVC_Fabric_Setup.iss
    python scripts/build_setup.py

This module remains only for:
  - unit tests of thin shell copy helpers
  - emergency portable copy without Inno on a dev machine

User-facing install must NOT be a custom Tk wizard. Enterprises use
Inno Setup / NSIS / WiX; we use Inno Setup 6.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

warnings.warn(
    "launcher.setup_app is deprecated. Use Inno Setup: "
    "installer/RVC_Fabric_Setup.iss via scripts/build_setup.py",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export helpers still used by tests
from launcher._setup_shell import (  # noqa: E402
    _is_shell_tree,
    copy_shell_tree,
)

__all__ = ["_is_shell_tree", "copy_shell_tree", "main"]


def main() -> None:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(
        "RVC Fabric Setup",
        "自写 Setup 已废弃。\n\n"
        "请使用 Inno Setup 安装器：\n"
        "  dist\\RVC_Fabric_Setup.exe\n\n"
        "打包：python scripts\\build_setup.py\n"
        "脚本：installer\\RVC_Fabric_Setup.iss\n\n"
        "开发机补环境请运行「启动器」：\n"
        "  python launcher\\bootstrap.py",
    )
    root.destroy()


if __name__ == "__main__":
    main()
