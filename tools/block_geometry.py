# -*- coding: utf-8 -*-
"""实时变声的分块几何：一条流该怎么切、每块要喂进去多少、要取回来多少。

这段算术原来在三个地方各写一份：`gui_v1.start_vc`（真实时链路）、
`tools/benchmark_realtime.py`（离线基准），以及将来加工流程里的分块渲染器。
三份的问题不在于重复，而在于**它们必须完全一致，而不一致时没有任何征兆**——
渲染出来的声音听着像那么回事，只是和用户实际听到的差了半个块，
于是照着它调出来的参数到了用户机器上就不对。

所以抽到这里，谁都从这一份取。

一条流的时间轴（单位是采样点）::

    ┌─────────── input_frames ───────────┐
    │  extra   │ crossfade │ search │ blk │
    └──────────┴───────────┴────────┴─────┘
       上下文      交叉淡化   SOLA 搜索  本块

* ``zc``：一厘秒（采样率 / 100）。所有长度都对齐到它的整数倍，
  这样 16k 侧的换算 ``160 * n // zc`` 永远是整数。
* ``extra``：给模型的额外上下文。它只进不出——``skip_head`` 把它跳过去。
* ``crossfade`` / ``search``：块与块之间做 SOLA 对齐和淡入淡出用的余量。
* ``blk``：这一块真正要输出的长度。

**不要在这里引 torch 或 numpy。** 这份模块要能在没有 Runtime 的机器上导入和
单测，也要能在只有 CPU 的租赁服务器上跑。
"""

from __future__ import annotations


def zc_of(samplerate: int) -> int:
    """一厘秒的采样点数。所有长度都对齐到它。"""
    if samplerate <= 0:
        raise ValueError("samplerate must be positive")
    return samplerate // 100


def _align(seconds: float, samplerate: int, zc: int) -> int:
    """秒 → 对齐到 zc 的采样点数。

    用 ``round`` 而不是 ``int``：``int`` 是向零取整，0.25 秒在 44100 上会算成
    上一个 zc，块比用户设的短一点点。这个偏差每块都发生，累积起来就是
    输出比输入慢一截。
    """
    if seconds < 0:
        seconds = 0.0
    return int(round(seconds * samplerate / zc)) * zc


def geometry(
    samplerate: int,
    block_time: float,
    crossfade_time: float,
    extra_time: float,
) -> dict:
    """一条流的完整帧布局。

    键名与 ``gui_v1`` 里的成员同名，方便对照阅读；数值必须逐字相同。
    """
    zc = zc_of(samplerate)
    block_frame = _align(block_time, samplerate, zc)
    crossfade_frame = _align(crossfade_time, samplerate, zc)
    # SOLA 的对齐窗最多 4 个 zc：再长的话相关运算的开销压过收益，
    # 而且窗口越长越容易把「下一块的起头」当成「上一块的尾巴」。
    sola_buffer_frame = min(crossfade_frame, 4 * zc)
    sola_search_frame = zc
    extra_frame = _align(extra_time, samplerate, zc)

    input_frames = extra_frame + crossfade_frame + sola_search_frame + block_frame
    return {
        "zc": zc,
        "block_frame": block_frame,
        "block_frame_16k": 160 * block_frame // zc,
        "crossfade_frame": crossfade_frame,
        "sola_buffer_frame": sola_buffer_frame,
        "sola_search_frame": sola_search_frame,
        "extra_frame": extra_frame,
        "input_frames": input_frames,
        # 送进模型的是 16k 重采样后的长度。
        "input_res_len": 160 * input_frames // zc,
        # 这两个是 RVC.infer 的参数：跳过多少上下文、要回来多长。
        "skip_head": extra_frame // zc,
        "return_length": (block_frame + sola_buffer_frame + sola_search_frame) // zc,
    }
