# -*- coding: utf-8 -*-
"""变声器.exe 入口 stub — 磁盘优先加载 launcher 后启动主界面。

机制与救援开关（TM_NO_DISK_LAUNCHER=1）见 scripts/_disk_first.py。
"""

import runpy

from _disk_first import install_disk_first

install_disk_first()
runpy.run_module("launcher.main_app", run_name="__main__", alter_sys=True)
