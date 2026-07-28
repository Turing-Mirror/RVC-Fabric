# -*- coding: utf-8 -*-
"""Settings → 外观（背景图）UI, split out of settings_page to keep that file lean."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import tkinter as tk

from launcher.theme import (
    TM_HELP,
    TM_INK,
    TM_INK_MUTED,
    TM_INSET,
    TM_META,
    TM_SURFACE,
    mono_font,
    px,
    sans_font,
)
from launcher.ui import SoftSlider
from launcher.ui.wallpaper import clamp_blur, clamp_opacity


class WallpaperSettingsMixin:
    """Mixin methods for wallpaper settings section + handlers."""

    def _build_wallpaper_settings_section(self, wrap: tk.Frame, card) -> None:
        body = card(wrap, "外观（背景图）")
        note = tk.Label(
            body,
            text=(
                "为软件换一张自己的背景图。磨砂使用 Pillow 高斯模糊"
                "（与界面阴影同源技术）；不透明度控制图案相对默认画布的强度。"
                "导航栏、底栏与白卡片保持实色以便阅读。图片保存在 User_Data/wallpaper/，"
                "单张不超过 20MB，最长边会缩到 4096。"
            ),
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_HELP,
            justify="left",
            anchor="w",
            wraplength=px(640),
        )
        note.pack(fill="x", anchor="w", pady=(0, 8))
        self._settings_wrap_labels.append(note)

        row = tk.Frame(body, bg=TM_SURFACE)
        row.pack(fill="x", pady=4)
        # Buttons use SURFACE-adjacent solid ink on INSET — never WALLPAPER_CHROMAKEY
        # and not the glass shell paint path.
        tk.Button(
            row,
            text="选择图片…",
            font=sans_font(9),
            bg=TM_INSET,
            fg=TM_INK,
            relief="flat",
            cursor="hand2",
            command=self._wallpaper_pick,
            bd=0,
            padx=12,
            pady=5,
        ).pack(side="left")
        tk.Button(
            row,
            text="恢复默认",
            font=sans_font(9),
            bg=TM_INSET,
            fg=TM_INK_MUTED,
            relief="flat",
            cursor="hand2",
            command=self._wallpaper_clear,
            bd=0,
            padx=12,
            pady=5,
        ).pack(side="left", padx=(8, 0))
        self.lbl_wallpaper_path = tk.Label(
            row,
            text=self._wallpaper_path_caption(),
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        )
        self.lbl_wallpaper_path.pack(side="left", padx=(12, 0), fill="x", expand=True)

        prev_row = tk.Frame(body, bg=TM_SURFACE)
        prev_row.pack(fill="x", pady=(6, 4))
        self.lbl_wallpaper_preview = tk.Label(
            prev_row,
            text="（未设置背景图）",
            font=sans_font(9),
            bg=TM_INSET,
            fg=TM_META,
            width=28,
            height=6,
            anchor="center",
        )
        self.lbl_wallpaper_preview.pack(side="left")
        self._wallpaper_preview_photo = None
        self.root.after(80, self._wallpaper_update_preview)

        self.var_wallpaper_opacity = tk.IntVar(
            value=clamp_opacity(self.cfg.get("ui_wallpaper_opacity", 40))
        )
        self.var_wallpaper_blur = tk.IntVar(
            value=clamp_blur(self.cfg.get("ui_wallpaper_blur", 16))
        )
        self._build_wallpaper_slider(
            body,
            "背景不透明度",
            self.var_wallpaper_opacity,
            0,
            100,
            self._wallpaper_on_opacity,
        )
        self._build_wallpaper_slider(
            body,
            "磨砂程度",
            self.var_wallpaper_blur,
            0,
            40,
            self._wallpaper_on_blur,
        )
        tip = tk.Label(
            body,
            text=(
                "提示：不透明度 0≈纯色界面；磨砂 0=清晰，数值越大越雾。"
                "仅支持静态 jpg/png/webp/bmp（不支持动态 GIF）。"
            ),
            font=sans_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
            justify="left",
            wraplength=px(640),
        )
        tip.pack(fill="x", pady=(4, 0))
        self._settings_wrap_labels.append(tip)

    def _build_wallpaper_slider(
        self,
        parent: tk.Frame,
        label: str,
        variable: tk.Variable,
        from_: int,
        to: int,
        on_change,
    ) -> None:
        f = tk.Frame(parent, bg=TM_SURFACE)
        f.pack(fill="x", pady=6)
        tk.Label(
            f,
            text=label,
            width=14,
            anchor="w",
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            font=sans_font(10),
        ).pack(side="left")
        val = tk.Label(
            f,
            text="",
            width=5,
            anchor="e",
            bg=TM_SURFACE,
            fg=TM_INK,
            font=mono_font(11),
        )
        val.pack(side="right")

        def _fmt(*_a):
            try:
                val.configure(text=str(int(variable.get())))
            except Exception:
                pass

        def _on(_v=None):
            _fmt()
            on_change()

        SoftSlider(
            f,
            variable,
            from_,
            to,
            resolution=1,
            command=_on,
            bar_width=px(320),
            bar_height=px(36),
            bg=TM_SURFACE,
        ).pack(side="left", fill="x", expand=True, padx=4)
        try:
            variable.trace_add("write", lambda *_: _fmt())
        except Exception:
            pass
        _fmt()

    def _wallpaper_path_caption(self) -> str:
        p = str(self.cfg.get("ui_wallpaper_path") or "").strip()
        if not p:
            return "当前：默认画布（无自定义图）"
        return f"当前：{Path(p).name}"

    def _wallpaper_pick(self) -> None:
        ctrl = getattr(self, "_wallpaper", None)
        if ctrl is None:
            return
        if ctrl.set_image_from_dialog():
            try:
                self.lbl_wallpaper_path.configure(text=self._wallpaper_path_caption())
            except Exception:
                pass
            self._wallpaper_update_preview()

    def _wallpaper_clear(self) -> None:
        ctrl = getattr(self, "_wallpaper", None)
        if ctrl is None:
            return
        ctrl.clear_image()
        try:
            self.lbl_wallpaper_path.configure(text=self._wallpaper_path_caption())
        except Exception:
            pass
        self._wallpaper_update_preview()

    def _wallpaper_on_opacity(self) -> None:
        self._wallpaper_debounce_slider(
            "_wallpaper_opacity_job",
            lambda: int(self.var_wallpaper_opacity.get()),
            lambda v: getattr(self, "_wallpaper").set_opacity(v),
            delay_ms=280,
        )

    def _wallpaper_on_blur(self) -> None:
        self._wallpaper_debounce_slider(
            "_wallpaper_blur_job",
            lambda: int(self.var_wallpaper_blur.get()),
            lambda v: getattr(self, "_wallpaper").set_blur(v),
            delay_ms=280,
        )

    def _wallpaper_debounce_slider(
        self,
        job_attr: str,
        get_val,
        apply_fn: Callable,
        *,
        delay_ms: int = 280,
    ) -> None:
        ctrl = getattr(self, "_wallpaper", None)
        if ctrl is None:
            return
        try:
            v = get_val()
        except Exception:
            return
        job = getattr(self, job_attr, None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass

        def _apply(val=v):
            setattr(self, job_attr, None)
            try:
                apply_fn(val)
            except Exception:
                pass
            self._wallpaper_update_preview()

        setattr(self, job_attr, self.root.after(delay_ms, _apply))

    def _wallpaper_update_preview(self) -> None:
        lbl = getattr(self, "lbl_wallpaper_preview", None)
        ctrl = getattr(self, "_wallpaper", None)
        if lbl is None or ctrl is None:
            return
        photo = ctrl.preview_photo(max_w=px(200), max_h=px(112))
        self._wallpaper_preview_photo = photo
        try:
            if photo is None:
                lbl.configure(image="", text="（未设置背景图）")
            else:
                lbl.configure(image=photo, text="")
        except Exception:
            pass
