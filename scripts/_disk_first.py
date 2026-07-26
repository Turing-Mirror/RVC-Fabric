# -*- coding: utf-8 -*-
"""磁盘优先加载 launcher 包（frozen 壳 exe 专用，无副作用模块）。

背景：PyInstaller 冻结的模块由 FrozenImporter 提供，安装目录里被
gui_patch 更新过的 launcher/*.py 默认永远不会被加载 —— 这正是
「增量更新后版本号不变、壳层新功能不生效」的根因。

本模块在一切业务 import 之前往 sys.meta_path 最前插入一个只服务
``launcher`` / ``launcher.*`` 的磁盘 finder：安装目录存在 launcher/
源码树（Setup 载荷与 gui_patch 都会放）时，壳层代码一律从磁盘加载，
exe 内冻结副本仅作缺文件时的兜底。

救援开关：磁盘 launcher 被坏补丁损坏导致无法启动时，设置环境变量
``TM_NO_DISK_LAUNCHER=1`` 再启动即可回到 exe 内置版本。
"""

import os
import sys


def install_disk_first() -> None:
    if not getattr(sys, "frozen", False):
        return  # 源码运行走正常 import，无需介入
    if os.environ.get("TM_NO_DISK_LAUNCHER", "").strip() == "1":
        return
    try:
        root = os.path.dirname(os.path.abspath(sys.executable))
        if not os.path.isfile(os.path.join(root, "launcher", "__init__.py")):
            return
        import importlib.abc
        import importlib.machinery

        class _DiskFirstLauncher(importlib.abc.MetaPathFinder):
            """launcher.* 优先从安装目录解析；找不到时返回 None 落回 frozen。"""

            def find_spec(self, fullname, path=None, target=None):
                if fullname != "launcher" and not fullname.startswith("launcher."):
                    return None
                search = [root] if fullname == "launcher" else path
                try:
                    return importlib.machinery.PathFinder.find_spec(fullname, search)
                except Exception:
                    return None

        sys.meta_path.insert(0, _DiskFirstLauncher())
        # 磁盘 launcher 的兄弟目录（tools/ configs/ 等）也可按包根导入
        if root not in sys.path:
            sys.path.insert(0, root)
    except Exception:
        pass  # 任何异常都退回 frozen 行为，绝不阻断启动
