# -*- coding: utf-8 -*-
"""离线语音转换的分段计时报告。

写这个是因为「一条 5 秒语音要一两分钟」这件事，之前只能靠读代码估：
import torch 几秒、fairseq 几秒、hubert 几秒……全是猜的。猜错了就会把力气
花在错的地方。有了这份报告，快慢之争就有数字可以对。

跟 tools/perf_report.py 同形：纯 stdlib、只落本地 JSON、不上传，用户自己把
文件发过来（QQ 群 / 反馈）。这是我们拿到别人机器上时间分布的唯一途径。

用法::

    t = StsTimer()
    with t.stage("import"):
        import torch
    with t.stage("model"):
        vc.get_vc(path)
    ...
    t.save(out_dir, extra={"files": 3, "hot": False})
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager

# 报告很小（几百字节），但也没必要无限攒。
_KEEP_REPORTS = 30

# 这些阶段名是固定的，界面和排查都按它们对号入座。
STAGES = (
    "import",     # import torch / fairseq / scipy
    "config",     # Config() 探测设备
    "model",      # .pth → net_g
    "hubert",     # hubert_base.pt
    "rmvpe",      # rmvpe.pt
    "convert",    # 真正的转换
    "write",      # 写盘
)


class StsTimer:
    """按阶段累计耗时。任何一步都不该因为计时而失败。"""

    def __init__(self, hot: bool = False) -> None:
        self.hot = bool(hot)
        self._t0 = time.monotonic()
        self._stages: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str):
        start = time.monotonic()
        try:
            yield
        finally:
            try:
                self._stages[name] = self._stages.get(name, 0.0) + (
                    time.monotonic() - start
                )
            except Exception:
                pass

    def add(self, name: str, seconds: float) -> None:
        try:
            self._stages[name] = self._stages.get(name, 0.0) + float(seconds)
        except Exception:
            pass

    def summary(self, extra: dict | None = None) -> dict:
        total = max(1e-6, time.monotonic() - self._t0)
        stages = {k: round(v, 3) for k, v in self._stages.items()}
        accounted = sum(self._stages.values())
        out = {
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            # 热路径 = 复用实时 worker 里常驻的模型，没有加载阶段。
            "hot": self.hot,
            "total_s": round(total, 3),
            "stages_s": stages,
            # 没被任何 stage 圈住的时间。这一项大就说明还有没量到的开销。
            "other_s": round(max(0.0, total - accounted), 3),
            "load_share": round(
                sum(
                    v
                    for k, v in self._stages.items()
                    if k in ("import", "config", "model", "hubert", "rmvpe")
                )
                / total,
                3,
            ),
        }
        if extra:
            out.update({k: v for k, v in extra.items() if k not in out})
        return out

    def save(self, dir_path: str, extra: dict | None = None) -> str:
        """落一份 JSON，返回路径。失败返回空串 —— 计时不该让转换失败。"""
        try:
            os.makedirs(dir_path, exist_ok=True)
            name = "sts_%s.json" % time.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(dir_path, name)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.summary(extra), f, ensure_ascii=False, indent=2)
            _prune(dir_path)
            return path
        except Exception:
            return ""


def load_latest(dir_path: str) -> dict | None:
    try:
        names = sorted(
            n for n in os.listdir(dir_path) if n.startswith("sts_") and n.endswith(".json")
        )
    except OSError:
        return None
    if not names:
        return None
    try:
        with open(os.path.join(dir_path, names[-1]), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _prune(dir_path: str, keep: int = _KEEP_REPORTS) -> None:
    try:
        names = sorted(
            n for n in os.listdir(dir_path) if n.startswith("sts_") and n.endswith(".json")
        )
        for n in names[:-keep] if len(names) > keep else []:
            try:
                os.remove(os.path.join(dir_path, n))
            except OSError:
                pass
    except OSError:
        pass
