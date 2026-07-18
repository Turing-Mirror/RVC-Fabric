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
