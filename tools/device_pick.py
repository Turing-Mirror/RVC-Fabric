# -*- coding: utf-8 -*-
"""Pick / resolve sound-device names without pulling in torch.

The worker and the old Tk GUI used to treat any name containing 麦克风/mic
as a real microphone. NVIDIA Broadcast, Steam, OBS virtual cables all match
that, and they usually appear *before* the hardware mic in the MME list.
Auto-pick then silently opened Broadcast while the leftover `input_device`
field still said Realtek.

Rules:
- A saved name that still resolves (exact or truncated MME prefix) wins.
- Only fill a side that is actually missing. A truncated CABLE output name
  must not cause the input to be re-picked.
- Default input skips software / processed captures.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

_VIRTUAL_CAPTURE = (
    "cable",
    "voicemeeter",
    "vb-audio",
    "vb audio",
    "virtual",
    "nvidia broadcast",
    "broadcast",
    "steam streaming",
    "obs",
    "mapper",
    "stereo mix",
    "what u hear",
    "sonar",
    "vac ",
    "line 1",
)

_VIRTUAL_PLAYBACK = (
    "cable output",
    "voicemeeter out",
    "mapper",
    "steam streaming",
    "nvidia high definition",
    "nvidia broadcast",
    "obs virtual",
    "stereo mix",
    "primary sound driver",
    "主声音驱动",
)

_MIC_HINTS = ("microphone", "mic", "麦克风", "array", "headset")
_CABLE_IN_HINTS = ("cable input", "voicemeeter input", "voicemeeter aux input")


def _low(name: str) -> str:
    return (name or "").strip().lower()


def is_virtual_capture_name(name: str) -> bool:
    low = _low(name)
    if not low:
        return True
    return any(k in low for k in _VIRTUAL_CAPTURE)


def is_virtual_playback_name(name: str) -> bool:
    low = _low(name)
    if not low:
        return True
    return any(k in low for k in _VIRTUAL_PLAYBACK)


def resolve_device_name(name: str, names: Iterable[str]) -> Optional[str]:
    """Exact match, then truncated-MME prefix. Never '麦克风' → first 麦克风.

    再按括号里的硬件串匹配：插拔耳机时 Windows 会把同一块声卡在
    「扬声器 (3- KM-HIFI-384KHZ)」和「耳机 (3- KM-HIFI-384KHZ)」之间改名，
    配置里还写着扬声器、列表里只剩耳机时，前缀对不上，监听自己就开不了 ——
    纯 DSP 变声时输出在 CABLE，用户全靠监听，看起来就像「DSP 开不起来」。
    """
    names = [n for n in names if n]
    if not name or not names:
        return None
    if name in names:
        return name
    # Saved MME names are often cut at 31 chars.
    for n in names:
        if n.startswith(name) or name.startswith(n):
            return n
    m = re.search(r"\(([^)]+)\)\s*$", name)
    if not m:
        return None
    token = m.group(1).strip().lower()
    if not token or len(token) < 3:
        return None
    hits = [n for n in names if token in n.lower()]
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    # 多个命中时尽量保住角色词（耳机/扬声器/麦克风）
    for role in ("耳机", "headphone", "headset", "扬声器", "speaker", "麦克风", "microphone", "mic"):
        if role in name.lower() or role in name:
            for n in hits:
                if role in n.lower() or role in n:
                    return n
    return hits[0]


def pick_default_input(names: Iterable[str]) -> str:
    names = list(names or [])
    real = [n for n in names if not is_virtual_capture_name(n)]
    for n in real:
        low = _low(n)
        if any(k in low for k in _MIC_HINTS):
            return n
    if real:
        return real[0]
    return names[0] if names else ""


def pick_default_output(names: Iterable[str]) -> str:
    """主输出必须是 CABLE 类虚拟设备；找不到就返回空，让调用方报错。

    以前找不到 CABLE 会退回「第一个真实放音设备」。变声主输出一旦落在
    耳机/扬声器上，用户从头到尾听到的都是自己变声后的声音（diag
    26.8.19/3：CABLE 瞬时不在列表里，自动补选挑了 HyperX 耳机）。宁可
    这一次启动失败并说清「输出设备不可用」，也不能把声音悄悄送进耳机。
    """
    names = list(names or [])
    for n in names:
        low = _low(n)
        if any(k in low for k in _CABLE_IN_HINTS):
            return n
    for n in names:
        if "cable input" in _low(n) or (
            "cable" in _low(n) and "output" not in _low(n)
        ):
            return n
    return ""


def fill_missing_devices(
    saved_in: str,
    saved_out: str,
    inputs: Iterable[str],
    outputs: Iterable[str],
) -> tuple[str, str, list[str]]:
    """Keep any saved name that still resolves. Only fill the missing side.

    Returns (input, output, notes).
    """
    notes: list[str] = []
    ins = list(inputs or [])
    outs = list(outputs or [])
    got_in = resolve_device_name(saved_in, ins)
    got_out = resolve_device_name(saved_out, outs)
    if got_in is None:
        got_in = pick_default_input(ins)
        if saved_in:
            notes.append("input %r not in list → %r" % (saved_in, got_in))
    if got_out is None:
        got_out = pick_default_output(outs)
        if saved_out:
            notes.append("output %r not in list → %r" % (saved_out, got_out))
    return got_in or "", got_out or "", notes
