# -*- coding: utf-8 -*-
"""后端选择里不依赖 torch 的那部分。

单独成文件是为了能测：`configs/config.py` 顶上就 `import torch`，开发机上根本
导不进来，把这几行留在那边等于永远跑不到。
"""

# 串流、远程桌面和 VR 软件都会装一块虚拟显示适配器，名字里带这些词。它们在
# DirectML 的枚举里和真显卡平起平坐，而且经常排在前面 —— 装了这类软件的机器上，
# 0 号就不是显卡。
VIRTUAL_ADAPTER_HINTS = (
    "virtual",
    "remote",
    "mirror",
    "basic display",
    "basic render",
    "idd",
    "gameviewer",
    "parsec",
    "sunshine",
    "oculus",
    "vmware",
    "virtualbox",
    "hyper-v",
    "citrix",
)


def first_real_adapter(names) -> "int | None":
    """名字看着不像虚拟适配器的第一块。全都像、或者一个名字都读不出来就返回 None。

    名字为空时不能当真卡：读不到名字补的就是空串，而空串里当然不含任何关键词。
    """
    for i, name in enumerate(names):
        low = str(name or "").lower()
        if low and not any(h in low for h in VIRTUAL_ADAPTER_HINTS):
            return i
    return None
