"""Safe model/checkpoint loading helpers for RVC.

Untrusted .pth files can execute arbitrary code via pickle when loaded with
plain torch.load. Prefer weights_only when supported; always validate paths
against an allowed root directory.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

PathLike = Union[str, os.PathLike]


def resolve_under_root(root: PathLike, user_path: PathLike) -> Path:
    """Resolve user_path under root; raise ValueError on path traversal."""
    if root is None or str(root).strip() == "":
        raise ValueError("root directory is not configured")
    root_p = Path(root).expanduser().resolve()
    # Treat bare names as relative to root; strip accidental absolute prefixes
    name = os.path.basename(str(user_path).replace("\\", "/"))
    if not name or name in (".", ".."):
        raise ValueError(f"invalid path component: {user_path!r}")
    # If caller passed a path that already lives under root, allow it
    candidate = Path(user_path)
    if candidate.is_absolute() or os.path.dirname(str(user_path).replace("\\", "/")):
        try:
            resolved = candidate.expanduser().resolve()
            resolved.relative_to(root_p)
            return resolved
        except (ValueError, OSError):
            # Fall back to basename under root
            pass
    resolved = (root_p / name).resolve()
    try:
        resolved.relative_to(root_p)
    except ValueError as e:
        raise ValueError(
            f"path escapes allowed root {root_p}: {user_path!r}"
        ) from e
    return resolved


def safe_model_path(weight_root: Optional[str], sid: str) -> str:
    """Build an absolute model path for a voice weight file name (sid)."""
    if not sid or not str(sid).strip():
        raise ValueError("model name (sid) is empty")
    sid = str(sid).strip()
    root = weight_root or os.getenv("weight_root") or "assets/weights"
    path = resolve_under_root(root, sid)
    if not path.is_file():
        # allow missing extension handling only for existence check by caller
        pass
    return str(path)


def safe_torch_load(
    path: PathLike,
    map_location: Any = "cpu",
    *,
    weights_only: Optional[bool] = None,
) -> Any:
    """Load a torch checkpoint with the safest available API.

    On PyTorch >= 2.0, tries weights_only=True first (safe for pure tensor
    state dicts). RVC full checkpoints often contain non-tensor metadata
    (lists, strings), so we fall back to weights_only=False with a warning
    when that fails. Never use this on untrusted files without review.
    """
    import torch  # lazy: path helpers must work without torch installed

    path = str(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"checkpoint not found: {path}")

    # Explicit override
    if weights_only is True:
        return torch.load(path, map_location=map_location, weights_only=True)
    if weights_only is False:
        logger.warning(
            "Loading %s with weights_only=False (pickle). Only use trusted files.",
            path,
        )
        return torch.load(path, map_location=map_location, weights_only=False)

    # Auto: try safe path, then legacy RVC checkpoints
    try:
        return torch.load(path, map_location=map_location, weights_only=True)
    except TypeError:
        # Older torch without weights_only kwarg
        return torch.load(path, map_location=map_location)
    except Exception as e:
        logger.debug(
            "weights_only=True failed for %s (%s); falling back for RVC metadata.",
            path,
            e,
        )
        try:
            return torch.load(path, map_location=map_location, weights_only=False)
        except TypeError:
            return torch.load(path, map_location=map_location)
        except Exception as e:
            # 两条路都读不出来，说明文件本身坏了 —— 最常见的是下载只下了一半
            # （diag 26.8.19/3：unpickling stack underflow 反复出现，用户看到
            # 的只是「模型加载失败」四个字）。把「文件坏了、该怎么办」说出来。
            raise RuntimeError(
                f"{os.path.basename(str(path))} 读取失败，文件可能不完整或已损坏"
                f"（{type(e).__name__}: {e}）。\n"
                "下载来的音色：删除后重新下载；自己训练的：检查当时的磁盘空间，"
                "再用「进阶设置 → 模型提取」从训练存档恢复。"
            ) from e


# 训练检查点（train.py 存进 logs/<实验>/ 的 G_*.pth / D_*.pth）里有这些键，
# 可用的音色模型里没有。用来把两者分开。
_TRAIN_CKPT_KEYS = ("model", "optimizer", "iteration", "learning_rate")


def check_voice_ckpt(cpt: Any, path: PathLike = "") -> None:
    """确认这份 .pth 是能直接用的音色模型，不是训练中间检查点。

    音色模型是 ``{"weight": ..., "config": [...], ...}``；训练检查点是
    ``{"model": ..., "optimizer": ..., "iteration": ...}``，两者都叫 .pth，
    体积还差着七八倍，用户分不出来很正常。

    以前不检查，直接 ``cpt["config"][-1]``，用户选错文件时收到的是::

        加载模型失败：'config'

    这句话既没说错在哪，也没说该怎么办（26.8.20 用户诊断包：连着四次都栽在
    同一个 G_35200.pth 上）。这里把话说清楚，并指向真正能解决的那个功能。
    """
    name = os.path.basename(str(path or "")) or "所选文件"
    if not isinstance(cpt, dict):
        raise RuntimeError(f"{name} 不是音色模型：文件里不是权重字典。")
    if "weight" in cpt and "config" in cpt:
        return
    if any(k in cpt for k in _TRAIN_CKPT_KEYS):
        raise RuntimeError(
            f"{name} 是训练过程中的存档（G_ / D_ 开头那种），不能直接当音色用。\n"
            "请在训练窗「进阶设置 → 模型提取」里把它转成音色模型，"
            "或者改选训练完成后生成的那个音色 .pth。"
        )
    missing = "、".join(k for k in ("weight", "config") if k not in cpt)
    raise RuntimeError(f"{name} 不是 RVC 音色模型：缺少 {missing}。")
