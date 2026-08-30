# -*- coding: utf-8 -*-
"""音高纠错：只删算错的，不碰人的表达。

## 这里刻意**不做**平滑

最容易想到的做法是「跨块平滑，让音高稳住」。那是错的：**平滑就是抹掉突变，
而颤音、气声、爆发力本身就是突变**。抹平之后，会配音的用户就没内味了 ——
他表达得越好，被削得越狠。

所以这里只修三类**算法错误**。它们的共同点是**不像任何人声表达**，
删掉是纯收益：

| 错误 | 听感 | 判据 |
| --- | --- | --- |
| 八度错误 | 突然尖一下再掉回来 | 跳了接近 12 个半音，且前后都稳定在原音高 |
| 无声段冒音高 | 呼吸时突然出个音 | 该帧能量低于有声门限，却给出了音高值 |
| 孤立野值 | 单帧突刺 | 前后都正常，只有中间一帧离谱 |

**因此不需要说话/唱歌两套参数** —— 纠错对两种情况都成立，
界面上一个开关都不用加。

## 判据为什么是这几个数

* `OCTAVE_TOL`：八度是 12 个半音，允许 ±1.5 的余量。收得太紧会漏掉
  算法给出的 11.2 或 12.7；放得太松会把真实的十度跳进算成错误。
* `ISLAND_TOL`：孤立野值按 7 个半音判 —— 比正常的大跳（六度以内）高，
  比八度低，夹在中间。
* **前后都要稳定**才算错。只看「跳了一下」的话，一段真实的滑音会被逐帧判成
  一串错误，然后被改成一条直线。

## 纯函数，不引 torch

要能在没有 Runtime 的机器上单测，也要能在打分器那边复用。
"""

from __future__ import annotations

import numpy as np

#: 认作八度错误的容差（半音）。
OCTAVE_TOL = 1.5
#: 认作孤立野值的门限（半音）。
ISLAND_TOL = 7.0
#: 判断「前后是否稳定」时，两侧各看几帧。
CONTEXT = 2
#: 前后两侧自身的抖动超过这个数就不算「稳定」，这一帧也就不判错 ——
#: 本来就在大幅滑动的地方，谈不上「突然跳了一下」。
STEADY_TOL = 3.0


def _semitones(a: float, b: float) -> float:
    """b 相对 a 差几个半音。任一为零（无声）时返回 0。"""
    if a <= 0.0 or b <= 0.0:
        return 0.0
    return float(12.0 * np.log2(b / a))


def _steady(values: np.ndarray) -> bool:
    """这一小段是不是稳定的（都有声，且彼此相差不大）。"""
    vals = values[values > 0]
    if vals.size < values.size or vals.size == 0:
        return False
    if vals.size == 1:
        return True
    spread = 12.0 * np.log2(float(np.max(vals)) / float(np.min(vals)))
    return spread <= STEADY_TOL


def repair(
    f0: np.ndarray,
    voiced: np.ndarray | None = None,
    *,
    octave_tol: float = OCTAVE_TOL,
    island_tol: float = ISLAND_TOL,
) -> tuple[np.ndarray, dict]:
    """修掉三类算法错误。返回 (修好的 f0, 统计)。

    `voiced` 是每帧是否有声（能量高于门限）。给 None 就跳过「无声段冒音高」
    那一类 —— **不猜**：拿 f0 自己去反推有声与否是循环论证。

    统计里带每一类各改了几帧。这个数要能被看见：如果某台机器上八度错误占到
    百分之几，那说明音高算法本身在这台机器上有问题，而不是纠错该更努力。
    """
    out = np.asarray(f0, dtype=np.float64).copy()
    n = out.size
    stats = {"octave": 0, "unvoiced": 0, "island": 0, "frames": int(n)}
    if n == 0:
        return out, stats

    # 1) 无声段冒音高。先做这一类：它会把一批假值清零，
    #    后面两类就不会再拿这些假值当「上下文」。
    if voiced is not None:
        mask = np.asarray(voiced).astype(bool).ravel()
        if mask.size == n:
            bad = (out > 0) & (~mask)
            stats["unvoiced"] = int(np.count_nonzero(bad))
            out[bad] = 0.0

    # 2) 八度错误与孤立野值。逐帧看，但**要求两侧都稳定**——
    #    只看「跳了一下」的话，一段真实的滑音会被判成一串错误，
    #    然后被改成一条直线。
    for i in range(n):
        cur = out[i]
        if cur <= 0.0:
            continue
        lo = max(0, i - CONTEXT)
        hi = min(n, i + CONTEXT + 1)
        left = out[lo:i]
        right = out[i + 1:hi]
        if left.size == 0 or right.size == 0:
            continue
        if not (_steady(left) and _steady(right)):
            continue
        neighbour = float(np.median(np.concatenate([left, right])))
        if neighbour <= 0.0:
            continue
        delta = abs(_semitones(neighbour, cur))
        if abs(delta - 12.0) <= octave_tol:
            # 八度错误：按方向折回去，而不是抹成邻居的值 ——
            # 折回去保留了这一帧本来的细微起伏。
            out[i] = cur / 2.0 if cur > neighbour else cur * 2.0
            stats["octave"] += 1
        elif delta >= island_tol:
            out[i] = neighbour
            stats["island"] += 1
    return out, stats
