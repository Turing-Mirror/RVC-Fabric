# -*- coding: utf-8 -*-
"""变声器.exe 入口 stub — 磁盘优先加载 launcher 后启动主界面。

机制与救援开关（TM_NO_DISK_LAUNCHER=1）见 scripts/_disk_first.py。
"""

import sys

# Before any heavy import: refuse a second frozen instance so PyInstaller
# onefile does not race on Temp\_MEI*\python313.dll (error.png / LoadLibrary).
try:
    from launcher.single_instance import ensure_single_instance_or_exit

    ensure_single_instance_or_exit(kind="voice")
except SystemExit:
    raise
except Exception:
    pass

import runpy

from _disk_first import install_disk_first

install_disk_first()
runpy.run_module("launcher.main_app", run_name="__main__", alter_sys=True)
