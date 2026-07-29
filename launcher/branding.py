# -*- coding: utf-8 -*-
"""Product icon + logo helpers (window, tray, home stage).

Assets live under ``assets/brand/`` (shipped with Setup payload).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from launcher.paths import BRAND_ICO, BRAND_LOGO, BRAND_LOGO_NAV, BRAND_LOGO_UI, ROOT


def brand_logo_path(*, prefer: str = "ui") -> Optional[Path]:
    """Best available logo file. prefer: ui | nav | full."""
    order = {
        "ui": (BRAND_LOGO_UI, BRAND_LOGO, BRAND_LOGO_NAV),
        "nav": (BRAND_LOGO_NAV, BRAND_LOGO_UI, BRAND_LOGO),
        "full": (BRAND_LOGO, BRAND_LOGO_UI, BRAND_LOGO_NAV),
    }.get(prefer, (BRAND_LOGO_UI, BRAND_LOGO, BRAND_LOGO_NAV))
    for p in order:
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    # Dev fallback: docs reference screenshot
    alt = ROOT / "docs" / "reference-screenshots" / "RVC_Fabric.png"
    try:
        if alt.is_file():
            return alt
    except OSError:
        pass
    return None


def apply_window_icon(root) -> None:
    """Set taskbar / title-bar icon for a Tk root (best-effort)."""
    ico = BRAND_ICO
    try:
        if ico.is_file():
            # Windows Tk: iconbitmap wants .ico
            root.iconbitmap(default=str(ico))
    except Exception:
        pass
    # iconphoto works cross-platform and is sharper on some builds
    path = brand_logo_path(prefer="nav")
    if path is None:
        return
    try:
        from PIL import Image, ImageTk

        im = Image.open(path).convert("RGBA")
        im.thumbnail((64, 64), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(im, master=root)
        root.iconphoto(True, photo)
        # Keep reference on root so GC does not drop the image
        root._tm_iconphoto = photo  # type: ignore[attr-defined]
    except Exception:
        pass


def load_logo_photo(
    master,
    *,
    max_side: int = 160,
    prefer: str = "ui",
) -> Any:
    """Return a Tk PhotoImage of the product logo, or None."""
    path = brand_logo_path(prefer=prefer)
    if path is None:
        return None
    try:
        from PIL import Image, ImageTk

        im = Image.open(path).convert("RGBA")
        im.thumbnail((int(max_side), int(max_side)), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(im, master=master)
    except Exception:
        return None
