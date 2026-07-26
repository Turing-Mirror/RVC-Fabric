# -*- coding: utf-8 -*-
"""Thumbnail loader for model cover images (Tk PhotoImage)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

import tkinter as tk


def _resize_with_pil(path: Path, max_w: int, max_h: int) -> Optional[tk.PhotoImage]:
    """Scale image to fit inside max_w x max_h without cropping (contain)."""
    try:
        from PIL import Image, ImageTk  # type: ignore
    except Exception:
        return None
    try:
        im = Image.open(path).convert("RGBA")
        w, h = im.size
        if w <= 0 or h <= 0:
            return None
        # Always fit into target box for consistent card/list thumbs
        # (small art is upscaled on purpose so grids stay uniform)
        scale = min(max_w / w, max_h / h)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)
        # Pad to exact box so standing art is not letterbox-cropped by layout
        canvas = Image.new("RGB", (max_w, max_h), (240, 244, 248))
        canvas.paste(im, ((max_w - nw) // 2, (max_h - nh) // 2), im.split()[-1])
        return ImageTk.PhotoImage(canvas)
    except Exception:
        return None


def _resize_with_tk(path: Path, max_w: int, max_h: int) -> Optional[tk.PhotoImage]:
    """Fallback without PIL — subsample only (coarse)."""
    try:
        raw = tk.PhotoImage(file=str(path))
    except Exception:
        return None
    w, h = raw.width(), raw.height()
    if w <= 0 or h <= 0:
        return raw
    fx = max(1, int(w / max_w + 0.99))
    fy = max(1, int(h / max_h + 0.99))
    factor = max(fx, fy)
    if factor > 1:
        try:
            return raw.subsample(factor, factor)
        except Exception:
            return raw
    return raw


def load_cover_photo(
    path: Optional[str],
    *,
    max_w: int = 200,
    max_h: int = 140,
) -> Optional[tk.PhotoImage]:
    """Load and shrink a cover image. Returns None if missing/unreadable."""
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    photo = _resize_with_pil(p, max_w, max_h)
    if photo is not None:
        return photo
    return _resize_with_tk(p, max_w, max_h)


class CoverCache:
    """Path+size keyed PhotoImage cache (keep refs so Tk does not GC them)."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int, int], tk.PhotoImage] = {}

    def get(
        self,
        path: Optional[str],
        *,
        max_w: int = 200,
        max_h: int = 140,
    ) -> Optional[tk.PhotoImage]:
        if not path:
            return None
        key = (str(path), max_w, max_h)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        photo = load_cover_photo(path, max_w=max_w, max_h=max_h)
        if photo is not None:
            self._cache[key] = photo
        return photo

    def clear(self) -> None:
        self._cache.clear()
