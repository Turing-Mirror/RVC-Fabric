# -*- coding: utf-8 -*-
"""变声器.exe 入口 stub — 磁盘优先加载 launcher 后启动主界面。

机制与救援开关（TM_NO_DISK_LAUNCHER=1）见 scripts/_disk_first.py。
"""

import sys

import runpy

from _disk_first import install_disk_first

# Disk-first before single-instance so gui_patch can fix the guard without a
# full exe rebuild. Guard still runs before runpy / heavy launcher import so
# a second onefile process does not race Temp\_MEI*\python313.dll.
install_disk_first()
try:
    from launcher.single_instance import ensure_single_instance_or_exit

    ensure_single_instance_or_exit(kind="voice")
except SystemExit:
    raise
except Exception:
    pass

runpy.run_module("launcher.main_app", run_name="__main__", alter_sys=True)
