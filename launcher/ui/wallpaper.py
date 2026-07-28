# -*- coding: utf-8 -*-
"""Custom app wallpaper: PIL cover-scale + Gaussian frost + strength blend.

Technique (well-trodden, not bespoke R&D)::

  - Cover crop / resize like CSS ``background-size: cover`` (LANCZOS)
  - Frosted glass ≈ ``PIL.ImageFilter.GaussianBlur`` (same family as
    soft UI shadows already used in ``launcher/ui/widgets.py``)
  - Opacity / strength ≈ ``Image.blend`` against the theme canvas color
    (standard Pillow compositing)

Windows see-through for solid ``TM_BG`` panels uses layered-window color-key
(``SetLayeredWindowAttributes``), the same approach wrapped by
`Akascape/py-window-styles` (CustomTkinter community) — optional soft import
of ``pywinstyles`` when present, else a minimal ctypes fallback.

Config keys (app_config.json)::

  ui_wallpaper_path      relative under User_Data/ or absolute image path
  ui_wallpaper_opacity   0–100 image strength (0 = theme only, 100 = full art)
  ui_wallpaper_blur      0–40 Gaussian radius at design pixels
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import tkinter as tk

# Theme canvas (Schale bg) — blend target for strength
_FILL_RGB = (247, 249, 251)  # TM_BG
_WALLPAPER_DIRNAME = "wallpaper"
_STORED_NAME = "background"
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def wallpaper_dir(user_data: Path) -> Path:
    d = Path(user_data) / _WALLPAPER_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def clamp_opacity(v: Any) -> int:
    try:
        return max(0, min(100, int(round(float(v)))))
    except (TypeError, ValueError):
        return 40


def clamp_blur(v: Any) -> int:
    try:
        return max(0, min(40, int(round(float(v)))))
    except (TypeError, ValueError):
        return 16


def resolve_wallpaper_path(raw: str, *, user_data: Path, root: Path) -> Optional[Path]:
    """Return an existing image path, or None."""
    s = (raw or "").strip()
    if not s:
        return None
    p = Path(s)
    candidates: list[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        # Prefer User_Data-relative (portable installs)
        candidates.append(Path(user_data) / s)
        candidates.append(Path(user_data) / _WALLPAPER_DIRNAME / Path(s).name)
        candidates.append(Path(root) / s)
    for c in candidates:
        try:
            if c.is_file() and c.suffix.lower() in _ALLOWED_EXT:
                return c.resolve()
        except OSError:
            continue
    return None


def install_wallpaper_file(src: Path, user_data: Path) -> str:
    """Copy *src* into User_Data/wallpaper/ and return a relative path string."""
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(str(src))
    ext = src.suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise ValueError(f"不支持的图片格式：{ext or '（无扩展名）'}")
    dest_dir = wallpaper_dir(user_data)
    # Clear previous stored files (one active wallpaper)
    for old in dest_dir.glob(f"{_STORED_NAME}.*"):
        try:
            old.unlink()
        except OSError:
            pass
    dest = dest_dir / f"{_STORED_NAME}{ext if ext != '.jpeg' else '.jpg'}"
    shutil.copy2(src, dest)
    # Relative for portability across machines / drive letters
    return f"{_WALLPAPER_DIRNAME}/{dest.name}"


def clear_installed_wallpaper(user_data: Path) -> None:
    d = Path(user_data) / _WALLPAPER_DIRNAME
    if not d.is_dir():
        return
    for old in d.glob(f"{_STORED_NAME}.*"):
        try:
            old.unlink()
        except OSError:
            pass


def cover_resize(im, tw: int, th: int):
    """CSS-like cover: scale to fill, center-crop (Pillow)."""
    from PIL import Image

    tw, th = max(1, int(tw)), max(1, int(th))
    w, h = im.size
    if w <= 0 or h <= 0:
        return Image.new("RGB", (tw, th), _FILL_RGB)
    scale = max(tw / w, th / h)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, (nw - tw) // 2)
    top = max(0, (nh - th) // 2)
    return im.crop((left, top, left + tw, top + th))


def process_wallpaper(
    path: Path,
    size: tuple[int, int],
    *,
    opacity: int = 40,
    blur: int = 16,
    fill_rgb: tuple[int, int, int] = _FILL_RGB,
):
    """Load *path* → cover *size* → blur → blend with *fill_rgb* by *opacity*.

    ``opacity`` 0..100: 0 = pure fill (no art), 100 = full processed art.
    ``blur`` 0..40: Gaussian radius in pixels (0 = sharp).
    Returns a PIL RGB Image.
    """
    from PIL import Image, ImageFilter

    tw, th = max(1, int(size[0])), max(1, int(size[1]))
    op = clamp_opacity(opacity) / 100.0
    br = clamp_blur(blur)

    im = Image.open(path)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGBA")
        # Flatten alpha onto fill
        base = Image.new("RGB", im.size, fill_rgb)
        base.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
        im = base
    else:
        im = im.convert("RGB")

    im = cover_resize(im, tw, th)
    if br > 0:
        # Radius scales mildly with size so 4K windows stay soft without mush
        radius = float(br) * max(1.0, min(tw, th) / 900.0)
        im = im.filter(ImageFilter.GaussianBlur(radius=radius))

    if op <= 0.001:
        return Image.new("RGB", (tw, th), fill_rgb)
    if op >= 0.999:
        return im
    fill = Image.new("RGB", (tw, th), fill_rgb)
    # blend(fill, im, op): op=1 → im, op=0 → fill
    return Image.blend(fill, im, op)


def process_wallpaper_photo(
    path: Path,
    size: tuple[int, int],
    *,
    opacity: int = 40,
    blur: int = 16,
    master=None,
):
    """process_wallpaper + ImageTk.PhotoImage (keeps ref via return)."""
    from PIL import ImageTk

    im = process_wallpaper(path, size, opacity=opacity, blur=blur)
    if master is not None:
        return ImageTk.PhotoImage(im, master=master)
    return ImageTk.PhotoImage(im)


# ---------------------------------------------------------------------------
# Windows color-key (pywinstyles-compatible technique)
# ---------------------------------------------------------------------------

_TM_BG_HEX = "#f7f9fb"


def _hex_to_colorref(hex_color: str) -> int:
    h = (hex_color or "").strip().lstrip("#")
    if len(h) != 6:
        h = "f7f9fb"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r | (g << 8) | (b << 16)


def set_widget_colorkey(widget, hex_color: str = _TM_BG_HEX) -> bool:
    """Make *hex_color* pixels of *widget* see-through (Windows layered hwnd).

    Prefer ``pywinstyles.set_opacity`` when installed; otherwise ctypes
    ``SetLayeredWindowAttributes`` + ``LWA_COLORKEY`` (same Win32 API).
    """
    if sys.platform != "win32":
        return False
    # Soft dep: Akascape/py-window-styles
    try:
        import pywinstyles  # type: ignore

        pywinstyles.set_opacity(widget, color=hex_color)
        return True
    except Exception:
        pass
    try:
        import ctypes

        hwnd = int(widget.winfo_id())
        user32 = ctypes.windll.user32
        # Tk child ids often need parent for the real client hwnd
        parent = user32.GetParent(hwnd)
        if parent:
            hwnd = int(parent)
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        LWA_COLORKEY = 0x00000001
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
        user32.SetLayeredWindowAttributes(
            hwnd, _hex_to_colorref(hex_color), 0, LWA_COLORKEY
        )
        return True
    except Exception:
        return False


def clear_widget_colorkey(widget) -> None:
    """Best-effort remove WS_EX_LAYERED from widget hwnd (restore solid paint)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(widget.winfo_id())
        user32 = ctypes.windll.user32
        parent = user32.GetParent(hwnd)
        if parent:
            hwnd = int(parent)
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if style & WS_EX_LAYERED:
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style & ~WS_EX_LAYERED)
    except Exception:
        pass


class WallpaperController:
    """Owns the full-window wallpaper Label + config apply/refresh."""

    def __init__(self, app) -> None:
        self.app = app
        self._label: Any = None
        self._photo = None
        self._job = None
        self._last_size: tuple[int, int] = (0, 0)
        self._last_sig: tuple = ()
        self._glass_targets: list = []

    # -- public API ---------------------------------------------------------

    def setup(self) -> None:
        """Create the wallpaper layer once (call after chrome exists)."""
        import tkinter as tk

        root = self.app.root
        if self._label is not None:
            return
        self._label = tk.Label(root, bd=0, highlightthickness=0)
        # Behind chrome: place full window then lower under packed children
        self._label.place(x=0, y=0, relwidth=1, relheight=1)
        try:
            self._label.lower()
        except Exception:
            pass

    def apply_from_config(self) -> None:
        self.setup()
        self.refresh(force=True)

    def refresh(self, force: bool = False) -> None:
        """Re-render wallpaper to the current window size (debounced by caller)."""
        import tkinter as tk

        from launcher.paths import ROOT, USER_DATA
        from launcher.theme import TM_BG

        root = self.app.root
        cfg = self.app.cfg
        path = resolve_wallpaper_path(
            str(cfg.get("ui_wallpaper_path") or ""),
            user_data=USER_DATA,
            root=ROOT,
        )
        opacity = clamp_opacity(cfg.get("ui_wallpaper_opacity", 40))
        blur = clamp_blur(cfg.get("ui_wallpaper_blur", 16))

        if path is None or opacity <= 0:
            self._clear_visual()
            return

        try:
            root.update_idletasks()
            w = max(int(root.winfo_width()), 320)
            h = max(int(root.winfo_height()), 240)
        except Exception:
            w, h = 1100, 720

        sig = (str(path), w, h, opacity, blur)
        if not force and sig == self._last_sig:
            return
        self._last_sig = sig
        self._last_size = (w, h)

        try:
            photo = process_wallpaper_photo(
                path, (w, h), opacity=opacity, blur=blur, master=root
            )
        except Exception:
            self._clear_visual()
            return

        self._photo = photo  # keep ref
        if self._label is None:
            self.setup()
        try:
            self._label.configure(image=photo, bg=TM_BG)
            self._label.place(x=0, y=0, relwidth=1, relheight=1)
            self._label.lower()
        except Exception:
            return
        self._apply_glass_panels(enabled=True)

    def on_resize(self) -> None:
        """Debounced refresh when the window size changes."""
        root = self.app.root
        if self._job is not None:
            try:
                root.after_cancel(self._job)
            except Exception:
                pass
        self._job = root.after(120, lambda: self.refresh(force=False))

    def set_image_from_dialog(self) -> bool:
        from tkinter import filedialog, messagebox

        from launcher.config_store import save_config
        from launcher.paths import USER_DATA

        path = filedialog.askopenfilename(
            parent=self.app.root,
            title="选择背景图",
            filetypes=[
                ("图片", "*.jpg;*.jpeg;*.png;*.webp;*.bmp;*.gif"),
                ("全部", "*.*"),
            ],
        )
        if not path:
            return False
        try:
            rel = install_wallpaper_file(Path(path), USER_DATA)
        except Exception as e:
            messagebox.showerror("背景图", f"无法使用该图片：\n{e}")
            return False
        self.app.cfg["ui_wallpaper_path"] = rel
        save_config(self.app.cfg)
        self.apply_from_config()
        return True

    def clear_image(self) -> None:
        from launcher.config_store import save_config
        from launcher.paths import USER_DATA

        clear_installed_wallpaper(USER_DATA)
        self.app.cfg["ui_wallpaper_path"] = ""
        save_config(self.app.cfg)
        self._clear_visual()

    def set_opacity(self, value: int) -> None:
        from launcher.config_store import save_config

        self.app.cfg["ui_wallpaper_opacity"] = clamp_opacity(value)
        save_config(self.app.cfg)
        self.refresh(force=True)

    def set_blur(self, value: int) -> None:
        from launcher.config_store import save_config

        self.app.cfg["ui_wallpaper_blur"] = clamp_blur(value)
        save_config(self.app.cfg)
        self.refresh(force=True)

    def preview_photo(self, max_w: int = 200, max_h: int = 112):
        """Small PhotoImage for the settings card, or None."""
        from launcher.paths import ROOT, USER_DATA

        cfg = self.app.cfg
        path = resolve_wallpaper_path(
            str(cfg.get("ui_wallpaper_path") or ""),
            user_data=USER_DATA,
            root=ROOT,
        )
        if path is None:
            return None
        try:
            return process_wallpaper_photo(
                path,
                (max_w, max_h),
                opacity=clamp_opacity(cfg.get("ui_wallpaper_opacity", 40)),
                blur=clamp_blur(cfg.get("ui_wallpaper_blur", 16)),
                master=self.app.root,
            )
        except Exception:
            return None

    # -- internals ----------------------------------------------------------

    def _clear_visual(self) -> None:
        self._last_sig = ()
        self._photo = None
        if self._label is not None:
            try:
                self._label.place_forget()
                self._label.configure(image="")
            except Exception:
                pass
        self._apply_glass_panels(enabled=False)

    def _apply_glass_panels(self, *, enabled: bool) -> None:
        """Color-key TM_BG on body/pages so wallpaper shows; cards stay SURFACE."""
        from launcher.theme import TM_BG

        targets = self._collect_glass_targets()
        if not enabled:
            for w in targets:
                clear_widget_colorkey(w)
            self._glass_targets = []
            return
        # Apply after idle so hwnds exist
        app = self.app

        def _go():
            ok_any = False
            for w in targets:
                try:
                    if set_widget_colorkey(w, TM_BG):
                        ok_any = True
                except Exception:
                    pass
            self._glass_targets = targets if ok_any else []

        try:
            app.root.after(50, _go)
        except Exception:
            _go()

    def _collect_glass_targets(self) -> list:
        """Frames painted with TM_BG that should reveal wallpaper underneath."""
        app = self.app
        out: list = []
        for name in (
            "body",
            "_settings_canvas",
            "_settings_wrap",
            "_help_page",
        ):
            w = getattr(app, name, None)
            if w is not None:
                out.append(getattr(w, "frame", w))
        pages = getattr(app, "pages", None) or {}
        for fr in pages.values():
            if fr is not None:
                out.append(fr)
        # Dedup by id
        seen: set[int] = set()
        uniq: list = []
        for w in out:
            try:
                i = id(w)
                if i in seen:
                    continue
                seen.add(i)
                uniq.append(w)
            except Exception:
                pass
        return uniq
