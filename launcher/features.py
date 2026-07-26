# -*- coding: utf-8 -*-
"""Product feature switches (hide / show optional funnels).

Keep these as plain constants — the frozen shell reads them at import time.
Code paths behind a disabled switch must stay importable and unit-testable
(e.g. ConsultMixin remains in the MainApp MRO); only the UI entries hide.
"""

from __future__ import annotations

from typing import Final

# 官方技术调优 / 申请专业优化（咨询包漏斗）入口。
# False = 隐藏所有界面入口（模型页头部按钮、其他页服务按钮）。
# 打包逻辑 launcher/consult_pack.py 与 ConsultMixin 保留，随时可重新开启。
CONSULT_ENTRY_ENABLED: Final[bool] = False
