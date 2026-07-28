# -*- coding: utf-8 -*-
"""Custom app wallpaper: PIL cover-scale + Gaussian frost + strength blend.

Technique (well-trodden, not bespoke R&D)::

  - Cover crop / resize like CSS ``background-size: cover`` (LANCZOS)
  - Frosted glass ≈ ``PIL.ImageFilter.GaussianBlur``
  - Opacity / strength ≈ ``Image.blend`` against theme canvas color
  - Windows see-through: layered-window **dedicated chromakey** (not TM_BG)
    via ``SetLayeredWindowAttributes`` / optional ``pywinstyles`` — same idea
    as Akascape/py-window-styles, but never color-key the theme paint used by
    buttons (which would punch interactive holes).

Config keys (app_config.json)::

  ui_wallpaper_path      relative under User_Data/wallpaper/ only
  ui_wallpaper_opacity   0–100 image strength
  ui_wallpaper_blur      0–40 Gaussian radius
"""

from __future__ import annotations

import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Optional

# Dedicated chromakey — must NOT be TM_BG / SURFACE / accent (those paint controls).
# Only page-root / body / scroll canvas use this while wallpaper is on.
WALLPAPER_CHROMAKEY: str = "#010203"
_WALLPAPER_DIRNAME = "wallpaper"
_STORED_NAME = "background"
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
# P0: reject multi‑tens-of-MB / multi‑10k-pixel dumps on install
MAX_WALLPAPER_BYTES = 20 * 1024 * 1024
MAX_WALLPAPER_EDGE = 4096


def _theme_fill_rgb() -> tuple[int, int, int]:
    """Parse theme.TM_BG; fallback Schale default if theme unavailable."""
    try:
        from launcher.theme import TM_BG

        h = str(TM_BG).strip().lstrip("#")
        if len(h) == 6:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        pass
    return (247, 249, 251)


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


def _is_under_dir(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def resolve_wallpaper_path(raw: str, *, user_data: Path, root: Path) -> Optional[Path]:
    """Only files under ``User_Data/wallpaper/`` (portable + no arbitrary abs paths)."""
    del root  # kept for call-site compatibility
    s = (raw or "").strip()
    if not s:
        return None
    wp_root = (Path(user_data) / _WALLPAPER_DIRNAME).resolve()
    p = Path(s)
    candidates: list[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(Path(user_data) / s)
        candidates.append(wp_root / Path(s).name)
    for c in candidates:
        try:
            if not c.is_file():
                continue
            if c.suffix.lower() not in _ALLOWED_EXT:
                continue
            resolved = c.resolve()
            if not _is_under_dir(resolved, wp_root):
                continue
            return resolved
        except OSError:
            continue
    return None


def install_wallpaper_file(src: Path, user_data: Path) -> str:
    """Validate, downscale if needed, copy into User_Data/wallpaper/.

    Returns a relative path string (``wallpaper/background.ext``).
    """
    src = Path(src)
    if not src.is_file():
        raise FileNotFoundError(str(src))
    ext = src.suffix.lower()
    if ext not in _ALLOWED_EXT:
        raise ValueError(f"不支持的图片格式：{ext or '（无扩展名）'}")
    try:
        sz = src.stat().st_size
    except OSError as e:
        raise ValueError(f"无法读取文件：{e}") from e
    if sz <= 0:
        raise ValueError("文件为空")
    if sz > MAX_WALLPAPER_BYTES:
        raise ValueError(
            f"图片过大（{sz // (1024 * 1024)} MB），请选用不超过 "
            f"{MAX_WALLPAPER_BYTES // (1024 * 1024)} MB 的图片"
        )

    from PIL import Image

    try:
        im = Image.open(src)
        im.load()
    except Exception as e:
        raise ValueError(f"无法解码图片：{e}") from e

    # Flatten alpha; cap long edge (decompression / RAM guard)
    if im.mode not in ("RGB", "L"):
        fill = _theme_fill_rgb()
        rgba = im.convert("RGBA")
        base = Image.new("RGB", rgba.size, fill)
        base.paste(rgba, mask=rgba.split()[-1])
        im = base
    else:
        im = im.convert("RGB")

    w, h = im.size
    if w <= 0 or h <= 0:
        raise ValueError("图片尺寸无效")
    edge = max(w, h)
    if edge > MAX_WALLPAPER_EDGE:
        scale = MAX_WALLPAPER_EDGE / float(edge)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)

    dest_dir = wallpaper_dir(user_data)
    for old in dest_dir.glob(f"{_STORED_NAME}.*"):
        try:
            old.unlink()
        except OSError:
            pass

    # Prefer JPEG for photos; keep PNG if source was PNG (graphics)
    if ext in (".png", ".webp", ".bmp"):
        dest = dest_dir / f"{_STORED_NAME}.png"
        im.save(dest, format="PNG", optimize=True)
    else:
        dest = dest_dir / f"{_STORED_NAME}.jpg"
        im.save(dest, format="JPEG", quality=88, optimize=True)

    # Final size guard after re-encode
    try:
        if dest.stat().st_size > MAX_WALLPAPER_BYTES:
            raise ValueError("处理后图片仍过大，请换一张更小的图")
    except OSError:
        pass
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

    fill = _theme_fill_rgb()
    tw, th = max(1, int(tw)), max(1, int(th))
    w, h = im.size
    if w <= 0 or h <= 0:
        return Image.new("RGB", (tw, th), fill)
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
    fill_rgb: Optional[tuple[int, int, int]] = None,
):
    """Load → cover *size* → blur → blend with theme fill. Pure PIL (any thread)."""
    from PIL import Image, ImageFilter

    fill = fill_rgb if fill_rgb is not None else _theme_fill_rgb()
    tw, th = max(1, int(size[0])), max(1, int(size[1]))
    op = clamp_opacity(opacity) / 100.0
    br = clamp_blur(blur)

    im = Image.open(path)
    im.load()
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGBA")
        base = Image.new("RGB", im.size, fill)
        base.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
        im = base
    else:
        im = im.convert("RGB")

    im = cover_resize(im, tw, th)
    if br > 0:
        radius = float(br) * max(1.0, min(tw, th) / 900.0)
        im = im.filter(ImageFilter.GaussianBlur(radius=radius))

    if op <= 0.001:
        return Image.new("RGB", (tw, th), fill)
    if op >= 0.999:
        return im
    fill_im = Image.new("RGB", (tw, th), fill)
    return Image.blend(fill_im, im, op)


def process_wallpaper_photo(
    path: Path,
    size: tuple[int, int],
    *,
    opacity: int = 40,
    blur: int = 16,
    master=None,
):
    """Main-thread helper: process + ImageTk.PhotoImage."""
    from PIL import ImageTk

    im = process_wallpaper(path, size, opacity=opacity, blur=blur)
    if master is not None:
        return ImageTk.PhotoImage(im, master=master)
    return ImageTk.PhotoImage(im)


# ---------------------------------------------------------------------------
# Windows color-key (dedicated chromakey only)
# ---------------------------------------------------------------------------


def _hex_to_colorref(hex_color: str) -> int:
    h = (hex_color or "").strip().lstrip("#")
    if len(h) != 6:
        h = "010203"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r | (g << 8) | (b << 16)


def _tk_hwnd(widget) -> int:
    """Tk widget client hwnd (no GetParent — avoids wrong parent layered state)."""
    return int(widget.winfo_id())


def set_widget_colorkey(widget, hex_color: str = WALLPAPER_CHROMAKEY) -> bool:
    """Make *hex_color* pixels of *widget* see-through (Windows layered hwnd)."""
    if sys.platform != "win32":
        return False
    try:
        import pywinstyles  # type: ignore

        pywinstyles.set_opacity(widget, color=hex_color)
        return True
    except Exception:
        pass
    try:
        import ctypes

        hwnd = _tk_hwnd(widget)
        if not hwnd:
            return False
        user32 = ctypes.windll.user32
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
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = _tk_hwnd(widget)
        if not hwnd:
            return
        user32 = ctypes.windll.user32
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
        self._resize_job = None
        self._glass_job = None
        self._gen = 0  # invalidates in-flight worker results
        self._last_sig: tuple = ()
        self._glass_on = False
        self._glass_targets: list = []
        self._saved_bgs: dict[int, str] = {}  # id(widget) -> previous bg

    def setup(self) -> None:
        import tkinter as tk

        root = self.app.root
        if self._label is not None:
            return
        self._label = tk.Label(root, bd=0, highlightthickness=0)
        self._label.place(x=0, y=0, relwidth=1, relheight=1)
        try:
            self._label.lower()
        except Exception:
            pass

    def apply_from_config(self) -> None:
        self.setup()
        self.refresh(force=True)

    def refresh(self, force: bool = False) -> None:
        """Re-render wallpaper; heavy PIL work runs off the UI thread."""
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
            self._gen += 1
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

        self._gen += 1
        gen = self._gen
        path_s = str(path)
        fill = _theme_fill_rgb()

        def work() -> None:
            try:
                im = process_wallpaper(
                    Path(path_s),
                    (w, h),
                    opacity=opacity,
                    blur=blur,
                    fill_rgb=fill,
                )
            except Exception:
                def _fail() -> None:
                    if gen != self._gen:
                        return
                    self._clear_visual()

                try:
                    root.after(0, _fail)
                except Exception:
                    pass
                return

            def apply() -> None:
                if gen != self._gen:
                    return
                try:
                    from PIL import ImageTk

                    photo = ImageTk.PhotoImage(im, master=root)
                except Exception:
                    self._clear_visual()
                    return
                self._last_sig = sig
                self._photo = photo
                if self._label is None:
                    self.setup()
                try:
                    self._label.configure(image=photo, bg=TM_BG)
                    self._label.place(x=0, y=0, relwidth=1, relheight=1)
                    self._label.lower()
                except Exception:
                    return
                self._schedule_glass(enabled=True)

            try:
                root.after(0, apply)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True, name="tm-wallpaper").start()

    def on_resize(self) -> None:
        root = self.app.root
        if self._resize_job is not None:
            try:
                root.after_cancel(self._resize_job)
            except Exception:
                pass
        # Slightly longer debounce than page reflow — full-frame blur is expensive
        self._resize_job = root.after(200, lambda: self.refresh(force=False))

    def set_image_from_dialog(self) -> bool:
        from tkinter import filedialog, messagebox

        from launcher.config_store import save_config
        from launcher.paths import USER_DATA

        path = filedialog.askopenfilename(
            parent=self.app.root,
            title="选择背景图",
            filetypes=[
                ("图片", "*.jpg;*.jpeg;*.png;*.webp;*.bmp"),
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
        self._gen += 1
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
        """Small PhotoImage for settings (main-thread; tiny cost)."""
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

    def on_page_changed(self) -> None:
        """Re-bind chromakey to the newly visible page only (show_page hook)."""
        if self._photo is None and not self._glass_on:
            return
        self._schedule_glass(enabled=self._photo is not None)

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
        self._schedule_glass(enabled=False)

    def _schedule_glass(self, *, enabled: bool) -> None:
        """Single-flight glass apply (cancel prior after)."""
        app = self.app
        root = app.root
        if self._glass_job is not None:
            try:
                root.after_cancel(self._glass_job)
            except Exception:
                pass
            self._glass_job = None

        def _go() -> None:
            self._glass_job = None
            self._apply_glass_panels(enabled=enabled)

        try:
            self._glass_job = root.after(40, _go)
        except Exception:
            _go()

    def _apply_glass_panels(self, *, enabled: bool) -> None:
        """Chromakey only the *visible* page shell + body — never all pages.

        Stacking all pages with TM_BG color-key made the top page transparent
        so the last-gridded page (其他) showed through until ready.
        """
        from launcher.theme import TM_BG

        # Always clear previous glass targets first (inactive pages go solid)
        for w in list(self._glass_targets):
            try:
                clear_widget_colorkey(w)
            except Exception:
                pass
            self._restore_bg(w, TM_BG)
        self._glass_targets = []

        if not enabled:
            self._glass_on = False
            self._saved_bgs.clear()
            return

        targets = self._collect_glass_targets()
        ok_any = False
        for w in targets:
            try:
                self._paint_chromakey(w)
                if set_widget_colorkey(w, WALLPAPER_CHROMAKEY):
                    ok_any = True
            except Exception:
                pass
        self._glass_targets = targets if ok_any else []
        self._glass_on = ok_any
        if not ok_any:
            for w in targets:
                self._restore_bg(w, TM_BG)

    def _paint_chromakey(self, widget) -> None:
        wid = id(widget)
        if wid not in self._saved_bgs:
            try:
                self._saved_bgs[wid] = str(widget.cget("bg") or "")
            except Exception:
                self._saved_bgs[wid] = ""
        try:
            widget.configure(bg=WALLPAPER_CHROMAKEY)
        except Exception:
            pass

    def _restore_bg(self, widget, default: str) -> None:
        wid = id(widget)
        prev = self._saved_bgs.pop(wid, None)
        try:
            widget.configure(bg=prev or default)
        except Exception:
            try:
                widget.configure(bg=default)
            except Exception:
                pass

    def _collect_glass_targets(self) -> list:
        """Only body + the current page (and settings scroll guts when on settings)."""
        app = self.app
        out: list = []
        body = getattr(app, "body", None)
        if body is not None:
            out.append(body)
        key = str(getattr(app, "_current_page", None) or "home")
        pages = getattr(app, "pages", None) or {}
        fr = pages.get(key)
        if fr is not None:
            out.append(fr)
        if key == "settings":
            for name in ("_settings_canvas", "_settings_wrap"):
                w = getattr(app, name, None)
                if w is not None:
                    out.append(w)
        if key == "help":
            help_page = getattr(app, "_help_page", None)
            if help_page is not None:
                hfr = getattr(help_page, "frame", None)
                if hfr is not None:
                    out.append(hfr)
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
