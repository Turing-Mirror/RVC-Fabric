# -*- coding: utf-8 -*-
"""兼容入口：转发到 extract_i18n_strings.py。

历史用法::

    python scripts/dev/extract_ui_copy.py
    python scripts/dev/extract_ui_copy.py --check

完整 i18n 文案目录见 docs/i18n/。
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

sys.argv[0] = str(Path(__file__).with_name("extract_i18n_strings.py"))
runpy.run_path(str(Path(__file__).with_name("extract_i18n_strings.py")), run_name="__main__")
