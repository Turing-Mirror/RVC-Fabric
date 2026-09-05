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


NVIDIA_HINTS = ("nvidia", "geforce", "rtx", "gtx", "quadro", "tesla")


def looks_like_nvidia(name: str) -> bool:
    n = str(name or "").lower()
    return any(k in n for k in NVIDIA_HINTS)


def nvidia_names_from_env(environ=None) -> list:
    """壳层写入的 ``TM_NVIDIA_GPUS``（``|`` 分隔）。没有或空则 []。"""
    import os

    raw = (environ if environ is not None else os.environ).get("TM_NVIDIA_GPUS", "")
    raw = str(raw or "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split("|") if p.strip()]


def nvidia_present_without_cuda(cuda_available: bool, names) -> bool:
    """注册表/nvidia-smi 看到 N 卡，但 torch.cuda 起不来。

    diag 26.9.6 落了灰的歌单：P106-100 在，CUDA 不可用，自动后端却去了
    HD 4600 DirectML，实时变声在 ``torch.zeros(..., dtype=long)`` 上空报错。
    """
    if cuda_available:
        return False
    return any(looks_like_nvidia(n) for n in (names or []))


def auto_use_dml(cuda_available: bool, dml_count: int, nvidia_names=None) -> bool:
    """自动后端：CUDA 可用就不用 DirectML；N 卡在而 CUDA 挂了也不自动改走
    DirectML（退 CPU，让界面把「装驱动」说出来）；否则 DirectML 设备数 ≥ 1。"""
    if cuda_available:
        return False
    if nvidia_present_without_cuda(False, nvidia_names):
        return False
    return int(dml_count or 0) >= 1


def first_real_adapter(names) -> "int | None":
    """名字看着不像虚拟适配器的第一块。全都像、或者一个名字都读不出来就返回 None。

    名字为空时不能当真卡：读不到名字补的就是空串，而空串里当然不含任何关键词。
    """
    for i, name in enumerate(names):
        low = str(name or "").lower()
        if low and not any(h in low for h in VIRTUAL_ADAPTER_HINTS):
            return i
    return None
