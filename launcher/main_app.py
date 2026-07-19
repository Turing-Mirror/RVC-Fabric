# -*- coding: utf-8 -*-
"""Consumer app (RVCMAX role: daily GUI).

Turing Mirror companion skin — 「白无垢」. Not RVCMAX pink/purple chrome.
Models: User_Data/models catalog first; engine assets only for hubert/rmvpe story.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.catalog import import_model_to_catalog
from launcher.config_store import load_config, save_config, sync_realtime_gui_model
from launcher.paths import (
    APP_TITLE,
    MODELS_DIR,
    USER_DATA,
    ensure_dirs,
    list_voice_models,
)
from launcher.theme import (
    APP_PRODUCT_TAGLINE,
    TM_ACCENT,
    TM_ACCENT_INK,
    TM_BG,
    TM_HAIRLINE,
    TM_INK,
    TM_INK_MUTED,
    TM_META,
    TM_OK,
    TM_SURFACE,
    TM_SURFACE_HOVER,
    sans_font,
    serif_font,
)
from launcher.win_util import (
    focus_window_by_title,
    open_path,
    read_tail,
    realtime_gui_log_path,
    start_legacy_realtime_gui,
    start_webui,
)


class MainApp:
    def __init__(self) -> None:
        ensure_dirs()
        self.cfg = load_config()
        self.models = list_voice_models()
        self.model_idx = 0
        want = (
            self.cfg.get("last_model_path")
            or self.cfg.get("last_model")
            or self.cfg.get("last_model_name")
        )
        if want and self.models:
            for i, m in enumerate(self.models):
                if (
                    m.get("path") == want
                    or m.get("file") == want
                    or m.get("name") == want
                ):
                    self.model_idx = i
                    break

        self.webui_proc = None
        self.gui_proc = None
        self.vc_running = False
        self._current_page = "home"
        self._resize_job = None
        self._toast_job = None
        self._placed_once = False

        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("960x620")
        self.root.minsize(720, 480)
        self.root.configure(bg=TM_BG)
        self._place_and_raise(force_size=True)

        self._build_chrome()
        self._build_pages()
        self.root.bind("<Configure>", self._on_root_configure)
        self.show_page("home")
        self._tick_status()
        self.root.after(200, lambda: self._place_and_raise(force_size=False))
        self.root.after(800, lambda: self._place_and_raise(force_size=False))

    def _place_and_raise(self, force_size: bool = False) -> None:
        """Show window on primary screen. Only set default size once (allow user resize)."""
        try:
            self.root.update_idletasks()
            if force_size or not self._placed_once:
                w, h = 960, 620
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
                x = max(0, (sw - w) // 2)
                y = max(0, (sh - h) // 2)
                self.root.geometry(f"{w}x{h}+{x}+{y}")
                self._placed_once = True
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(1200, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
            if sys.platform == "win32":
                try:
                    import ctypes

                    self.root.update()
                    hwnd = self.root.winfo_id()
                    user32 = ctypes.windll.user32
                    parent = user32.GetParent(hwnd)
                    target = parent or hwnd
                    user32.ShowWindow(target, 9)
                    user32.SetForegroundWindow(target)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_root_configure(self, event) -> None:
        if event.widget is not self.root:
            return
        # Debounce reflow on resize
        if self._resize_job is not None:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.root.after(120, self._reflow_current_page)

    def _reflow_current_page(self) -> None:
        self._resize_job = None
        if self._current_page == "home":
            self._render_carousel()
        elif self._current_page == "models":
            self.refresh_models()

    def _build_chrome(self) -> None:
        top = tk.Frame(self.root, bg=TM_BG, height=52)
        top.pack(fill="x")
        top.pack_propagate(False)

        brand = tk.Frame(top, bg=TM_BG)
        brand.pack(side="left", padx=20, pady=10)
        tk.Label(
            brand,
            text="Turing Mirror",
            font=serif_font(15, "bold"),
            bg=TM_BG,
            fg=TM_INK,
        ).pack(side="left")
        tk.Label(
            brand,
            text="  变声器",
            font=sans_font(11),
            bg=TM_BG,
            fg=TM_INK_MUTED,
        ).pack(side="left")

        nav = tk.Frame(top, bg=TM_BG)
        nav.pack(side="left", expand=True, padx=12)
        self.nav_btns = {}
        for key, label in (
            ("home", "首页"),
            ("models", "模型"),
            ("settings", "设置"),
            ("more", "其他"),
        ):
            b = tk.Label(
                nav,
                text=label,
                font=sans_font(11),
                bg=TM_BG,
                fg=TM_INK_MUTED,
                padx=14,
                cursor="hand2",
            )
            b.pack(side="left", padx=2)
            b.bind("<Button-1>", lambda e, k=key: self.show_page(k))
            self.nav_btns[key] = b

        self.body = tk.Frame(self.root, bg=TM_BG)
        self.body.pack(fill="both", expand=True)

        bottom = tk.Frame(self.root, bg=TM_SURFACE, height=70)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)
        # hairline top
        tk.Frame(self.root, bg=TM_HAIRLINE, height=1).pack(fill="x", side="bottom")

        self.bottom_name = tk.Label(
            bottom,
            text="未选择模型",
            font=serif_font(12, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        )
        self.bottom_name.place(x=20, y=12)
        self.bottom_tag = tk.Label(
            bottom,
            text="请先导入音色到 User_Data/models",
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        )
        self.bottom_tag.place(x=20, y=36)

        ctrl = tk.Frame(bottom, bg=TM_SURFACE)
        ctrl.place(relx=0.5, rely=0.5, anchor="center")
        self.btn_start = tk.Button(
            ctrl,
            text="开启变声",
            font=sans_font(10, "bold"),
            bg=TM_ACCENT,
            fg=TM_ACCENT_INK,
            activebackground=TM_INK,
            activeforeground=TM_ACCENT_INK,
            relief="flat",
            padx=18,
            pady=7,
            cursor="hand2",
            command=self.toggle_vc,
            bd=0,
        )
        self.btn_start.pack(side="left", padx=6)
        tk.Button(
            ctrl,
            text="高级实时面板",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            relief="flat",
            padx=12,
            pady=7,
            cursor="hand2",
            command=self.open_legacy_gui,
            bd=0,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        ).pack(side="left", padx=6)

        right = tk.Frame(bottom, bg=TM_SURFACE)
        right.place(relx=0.97, rely=0.5, anchor="e")
        self.lbl_online = tk.Label(
            right,
            text="引擎待命",
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_META,
        )
        self.lbl_online.pack(anchor="e")
        self.lbl_latency = tk.Label(
            right,
            text=APP_PRODUCT_TAGLINE,
            font=sans_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
        )
        self.lbl_latency.pack(anchor="e")
        self._sync_bottom()

    def _build_pages(self) -> None:
        self.pages = {
            "home": self._page_home(),
            "models": self._page_models(),
            "settings": self._page_settings(),
            "more": self._page_more(),
        }

    def show_page(self, key: str) -> None:
        self._current_page = key
        for fr in self.pages.values():
            fr.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        for k, b in self.nav_btns.items():
            active = k == key
            b.configure(
                fg=TM_INK if active else TM_INK_MUTED,
                font=sans_font(11, "bold" if active else "normal"),
            )
        if key == "models":
            self.refresh_models()
        if key == "home":
            self._render_carousel()
            self._update_home_current_label()

    def _page_home(self) -> tk.Frame:
        fr = tk.Frame(self.body, bg=TM_BG)
        fr.columnconfigure(0, weight=1)
        fr.rowconfigure(2, weight=1)

        hero = tk.Frame(fr, bg=TM_BG)
        hero.grid(row=0, column=0, sticky="ew", pady=(16, 4), padx=16)
        tk.Label(
            hero,
            text="选择音色，开始变声",
            font=serif_font(18, "bold"),
            bg=TM_BG,
            fg=TM_INK,
        ).pack()
        tk.Label(
            hero,
            text="左右切换会立即设为当前音色 · 底部栏也会同步更新",
            font=sans_font(10),
            bg=TM_BG,
            fg=TM_INK_MUTED,
        ).pack(pady=(6, 0))

        # Current selection banner (always visible)
        cur_wrap = tk.Frame(fr, bg=TM_SURFACE, highlightthickness=1, highlightbackground=TM_HAIRLINE)
        cur_wrap.grid(row=1, column=0, sticky="ew", padx=24, pady=(8, 4))
        self.home_current_lbl = tk.Label(
            cur_wrap,
            text="当前音色：—",
            font=serif_font(13, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        )
        self.home_current_lbl.pack(fill="x", padx=14, pady=(10, 2))
        self.home_hint_lbl = tk.Label(
            cur_wrap,
            text="点击左右箭头或卡片即可切换",
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        )
        self.home_hint_lbl.pack(fill="x", padx=14, pady=(0, 10))

        self.carousel_host = tk.Frame(fr, bg=TM_BG)
        self.carousel_host.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        self.carousel_host.bind("<Configure>", lambda e: self._schedule_carousel_reflow())

        nav = tk.Frame(fr, bg=TM_BG)
        nav.grid(row=3, column=0, sticky="ew", pady=(4, 12))
        nav_inner = tk.Frame(nav, bg=TM_BG)
        nav_inner.pack()
        tk.Button(
            nav_inner,
            text="‹ 上一个",
            font=sans_font(11),
            bg=TM_SURFACE,
            fg=TM_INK,
            relief="flat",
            padx=16,
            pady=8,
            command=lambda: self._shift_model(-1),
            bd=0,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            cursor="hand2",
        ).pack(side="left", padx=8)
        tk.Button(
            nav_inner,
            text="下一个 ›",
            font=sans_font(11),
            bg=TM_SURFACE,
            fg=TM_INK,
            relief="flat",
            padx=16,
            pady=8,
            command=lambda: self._shift_model(1),
            bd=0,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            cursor="hand2",
        ).pack(side="left", padx=8)

        self.home_toast = tk.Label(
            fr,
            text="",
            font=sans_font(10),
            bg=TM_BG,
            fg=TM_OK,
        )
        self.home_toast.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        return fr

    def _schedule_carousel_reflow(self) -> None:
        if getattr(self, "_carousel_job", None):
            try:
                self.root.after_cancel(self._carousel_job)
            except Exception:
                pass
        self._carousel_job = self.root.after(80, self._render_carousel)

    def _render_carousel(self) -> None:
        if not hasattr(self, "carousel_host"):
            return
        for w in self.carousel_host.winfo_children():
            w.destroy()
        self._update_home_current_label()

        if not self.models:
            box = tk.Frame(
                self.carousel_host,
                bg=TM_SURFACE,
                highlightthickness=1,
                highlightbackground=TM_HAIRLINE,
            )
            box.pack(expand=True, fill="both", padx=40, pady=20)
            tk.Label(
                box,
                text="暂无音色\n\n请到「模型」页导入 .pth",
                font=sans_font(11),
                bg=TM_SURFACE,
                fg=TM_INK_MUTED,
                justify="center",
            ).pack(expand=True, pady=40)
            return

        # Scale card sizes with host width
        self.carousel_host.update_idletasks()
        host_w = max(self.carousel_host.winfo_width(), 400)
        host_h = max(self.carousel_host.winfo_height(), 220)
        focus_w = max(160, min(280, int(host_w * 0.28)))
        focus_h = max(180, min(300, int(host_h * 0.75)))
        side_w = max(110, int(focus_w * 0.7))
        side_h = max(140, int(focus_h * 0.75))

        n = len(self.models)
        idxs = [(self.model_idx - 1) % n, self.model_idx % n, (self.model_idx + 1) % n]
        row = tk.Frame(self.carousel_host, bg=TM_BG)
        row.place(relx=0.5, rely=0.5, anchor="center")

        for i, mi in enumerate(idxs):
            m = self.models[mi]
            focus = i == 1
            w, h = (focus_w, focus_h) if focus else (side_w, side_h)
            card = tk.Frame(
                row,
                bg=TM_SURFACE if focus else TM_BG,
                width=w,
                height=h,
                highlightthickness=2 if focus else 1,
                highlightbackground=TM_INK if focus else TM_HAIRLINE,
                cursor="hand2",
            )
            card.pack(side="left", padx=max(6, int(host_w * 0.012)), pady=8)
            card.pack_propagate(False)

            if focus:
                badge = tk.Label(
                    card,
                    text="当前使用",
                    font=sans_font(8, "bold"),
                    bg=TM_INK,
                    fg=TM_ACCENT_INK,
                    padx=8,
                    pady=2,
                )
                badge.place(relx=0.5, rely=0.12, anchor="center")

            name_lbl = tk.Label(
                card,
                text=m["name"][:12],
                font=serif_font(14 if focus else 10, "bold"),
                bg=card["bg"],
                fg=TM_INK,
            )
            name_lbl.place(relx=0.5, rely=0.42 if focus else 0.38, anchor="center")
            tag_lbl = tk.Label(
                card,
                text=m.get("tag") or "音色",
                font=sans_font(9),
                bg=card["bg"],
                fg=TM_META,
            )
            tag_lbl.place(relx=0.5, rely=0.58 if focus else 0.55, anchor="center")
            if focus:
                idx_lbl = tk.Label(
                    card,
                    text=f"{self.model_idx + 1} / {n}",
                    font=sans_font(9),
                    bg=card["bg"],
                    fg=TM_META,
                )
                idx_lbl.place(relx=0.5, rely=0.78, anchor="center")

            def _bind_all(widget, ix=mi):
                widget.bind("<Button-1>", lambda e, i=ix: self._select_model(i, feedback=True))

            for wdg in (card, name_lbl, tag_lbl):
                _bind_all(wdg)

    def _update_home_current_label(self) -> None:
        if not hasattr(self, "home_current_lbl"):
            return
        if not self.models:
            self.home_current_lbl.configure(text="当前音色：尚未选择")
            self.home_hint_lbl.configure(text="请先到「模型」页导入音色")
            return
        m = self.models[self.model_idx]
        n = len(self.models)
        self.home_current_lbl.configure(
            text=f"当前音色：{m['name']}    （{self.model_idx + 1} / {n}）"
        )
        self.home_hint_lbl.configure(
            text=f"标签：{m.get('tag') or '音色'}  ·  左右切换会立即生效并保存"
        )

    def _show_switch_toast(self, name: str) -> None:
        if not hasattr(self, "home_toast"):
            return
        self.home_toast.configure(text=f"已切换为「{name}」", fg=TM_OK)
        if self._toast_job is not None:
            try:
                self.root.after_cancel(self._toast_job)
            except Exception:
                pass
        self._toast_job = self.root.after(
            2200, lambda: self.home_toast.configure(text="")
        )

    def _shift_model(self, delta: int) -> None:
        if not self.models:
            return
        self._select_model((self.model_idx + delta) % len(self.models), feedback=True)

    def _select_model(self, idx: int, feedback: bool = False) -> None:
        if not self.models:
            return
        idx = idx % len(self.models)
        prev = self.model_idx
        self.model_idx = idx
        m = self.models[self.model_idx]
        # Persist so realtime / next launch use the same model
        self.cfg["last_model"] = m["file"]
        self.cfg["last_model_name"] = m["name"]
        self.cfg["last_model_path"] = m.get("path") or ""
        save_config(self.cfg)
        # Push into gui_v1's configs/inuse/config.json (read only at panel start)
        self._sync_model_to_realtime_gui(m)
        self._sync_bottom()
        self._update_home_current_label()
        if self._current_page == "home":
            self._render_carousel()
        elif self._current_page == "models":
            self.refresh_models()
        if feedback or prev != idx:
            self._show_switch_toast(m["name"])

    def _sync_model_to_realtime_gui(self, m: Optional[dict] = None) -> None:
        """Write current model + pitch settings into realtime panel config."""
        if m is None:
            if not self.models:
                return
            m = self.models[self.model_idx]
        pth = m.get("path") or ""
        if not pth:
            return
        idx_path = m.get("index") or ""
        try:
            sync_realtime_gui_model(
                pth,
                idx_path,
                pitch=float(self.cfg.get("pitch") or 0),
                formant=float(self.cfg.get("formant") or 0),
                index_rate=float(self.cfg.get("index_rate") or 0),
                f0method=str(self.cfg.get("f0method") or "fcpe"),
                rms_mix_rate=float(self.cfg.get("rms_mix_rate") or 0),
            )
        except Exception:
            pass

    def _current_model_key(self) -> str:
        if not self.models:
            return ""
        m = self.models[self.model_idx]
        return m.get("path") or m.get("file") or m.get("name") or ""

    def _is_active_model(self, m: dict) -> bool:
        if not self.models:
            return False
        cur = self.models[self.model_idx]
        if m.get("path") and cur.get("path"):
            return Path(m["path"]).resolve() == Path(cur["path"]).resolve()
        return m.get("file") == cur.get("file") and m.get("name") == cur.get("name")

    def _sync_bottom(self) -> None:
        if self.models:
            m = self.models[self.model_idx]
            self.bottom_name.configure(text=f"当前：{m['name']}")
            extra = m.get("source") or ""
            tag = m.get("tag") or "音色"
            self.bottom_tag.configure(
                text=f"{tag}"
                + (f" · {extra}" if extra == "legacy_weights" else "")
                + f"  ·  {self.model_idx + 1}/{len(self.models)}"
            )
        else:
            self.bottom_name.configure(text="未选择模型")
            self.bottom_tag.configure(text="请到「模型」页导入音色")

    def _page_models(self) -> tk.Frame:
        fr = tk.Frame(self.body, bg=TM_BG)
        fr.columnconfigure(0, weight=1)
        fr.rowconfigure(1, weight=1)

        bar = tk.Frame(fr, bg=TM_BG)
        bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        left = tk.Frame(bar, bg=TM_BG)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(
            left,
            text="音色目录",
            font=serif_font(14, "bold"),
            bg=TM_BG,
            fg=TM_INK,
        ).pack(side="left")
        self.models_status_lbl = tk.Label(
            left,
            text="",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_META,
        )
        self.models_status_lbl.pack(side="left", padx=10)

        for text, cmd in (
            ("刷新", self.refresh_models),
            ("导入模型", self.import_model),
            ("打开目录", lambda: open_path(MODELS_DIR)),
        ):
            primary = text == "导入模型"
            tk.Button(
                bar,
                text=text,
                font=sans_font(9),
                bg=TM_ACCENT if primary else TM_SURFACE,
                fg=TM_ACCENT_INK if primary else TM_INK_MUTED,
                relief="flat",
                padx=12,
                pady=5,
                cursor="hand2",
                command=cmd,
                bd=0,
            ).pack(side="right", padx=4)

        list_wrap = tk.Frame(fr, bg=TM_BG)
        list_wrap.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        list_wrap.columnconfigure(0, weight=1)
        list_wrap.rowconfigure(0, weight=1)

        canvas = tk.Canvas(list_wrap, bg=TM_BG, highlightthickness=0)
        scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=canvas.yview)
        self.model_grid = tk.Frame(canvas, bg=TM_BG)
        self._models_canvas = canvas
        self._models_canvas_win = canvas.create_window((0, 0), window=self.model_grid, anchor="nw")

        def _on_grid_cfg(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_cfg(e):
            canvas.itemconfigure(self._models_canvas_win, width=e.width)
            self._schedule_models_reflow()

        self.model_grid.bind("<Configure>", _on_grid_cfg)
        canvas.bind("<Configure>", _on_canvas_cfg)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        return fr

    def _schedule_models_reflow(self) -> None:
        if getattr(self, "_models_job", None):
            try:
                self.root.after_cancel(self._models_job)
            except Exception:
                pass
        self._models_job = self.root.after(100, self.refresh_models)

    def refresh_models(self) -> None:
        if not hasattr(self, "model_grid"):
            return
        self.models = list_voice_models()
        if self.model_idx >= len(self.models):
            self.model_idx = max(0, len(self.models) - 1)

        # Restore selection from saved path if possible
        want = self.cfg.get("last_model_path") or self.cfg.get("last_model")
        if want and self.models:
            for i, m in enumerate(self.models):
                if m.get("path") == want or m.get("file") == want or m.get("name") == want:
                    self.model_idx = i
                    break

        for w in self.model_grid.winfo_children():
            w.destroy()

        if hasattr(self, "models_status_lbl"):
            if self.models:
                cur = self.models[self.model_idx]["name"]
                self.models_status_lbl.configure(
                    text=f"共 {len(self.models)} 个 · 使用中：{cur}"
                )
            else:
                self.models_status_lbl.configure(text="共 0 个音色")

        if not self.models:
            tk.Label(
                self.model_grid,
                text="还没有模型。点右上角「导入模型」添加音色。",
                bg=TM_BG,
                fg=TM_INK_MUTED,
                font=sans_font(11),
            ).grid(row=0, column=0, padx=20, pady=40, sticky="w")
            self._sync_bottom()
            return

        # Columns adapt to width
        self._models_canvas.update_idletasks()
        cw = max(self._models_canvas.winfo_width(), 320)
        card_min = 160
        cols = max(1, min(6, cw // (card_min + 16)))
        for c in range(cols):
            self.model_grid.columnconfigure(c, weight=1, uniform="m")

        for i, m in enumerate(self.models):
            r, c = divmod(i, cols)
            active = self._is_active_model(m)
            card = tk.Frame(
                self.model_grid,
                bg=TM_SURFACE,
                height=150,
                highlightthickness=2 if active else 1,
                highlightbackground=TM_INK if active else TM_HAIRLINE,
                cursor="hand2",
            )
            card.grid(row=r, column=c, padx=8, pady=8, sticky="nsew")
            card.grid_propagate(False)
            self.model_grid.rowconfigure(r, weight=0)

            # Tag row: always show type; active gets extra ink badge
            tk.Label(
                card,
                text=m.get("tag") or "音色",
                font=sans_font(8),
                bg=TM_SURFACE,
                fg=TM_META,
            ).place(x=10, y=10)
            if active:
                tk.Label(
                    card,
                    text="使用中",
                    font=sans_font(8, "bold"),
                    bg=TM_INK,
                    fg="#ffffff",
                    padx=8,
                    pady=2,
                ).place(relx=1.0, x=-10, y=10, anchor="ne")

            tk.Label(
                card,
                text=m["name"][:16],
                font=serif_font(11, "bold"),
                bg=TM_SURFACE,
                fg=TM_INK,
            ).place(relx=0.5, rely=0.42, anchor="center")

            # Active: use Label (disabled Button grays out to unreadable bar on Windows)
            if active:
                tk.Label(
                    card,
                    text="正在使用",
                    font=sans_font(9, "bold"),
                    bg=TM_INK,
                    fg="#ffffff",
                    padx=14,
                    pady=5,
                ).place(relx=0.5, rely=0.78, anchor="center")
            else:
                tk.Button(
                    card,
                    text="使用",
                    font=sans_font(9),
                    bg=TM_ACCENT,
                    fg=TM_ACCENT_INK,
                    relief="flat",
                    cursor="hand2",
                    command=lambda ix=i: self._use_model_from_grid(ix),
                    bd=0,
                    padx=14,
                    pady=4,
                ).place(relx=0.5, rely=0.78, anchor="center")
                card.bind("<Button-1>", lambda e, ix=i: self._use_model_from_grid(ix))

        self._sync_bottom()

    def _use_model_from_grid(self, ix: int) -> None:
        self._select_model(ix, feedback=True)
        # Light toast via status label; avoid modal spam
        if hasattr(self, "models_status_lbl") and self.models:
            self.models_status_lbl.configure(
                text=f"已切换为：{self.models[ix]['name']}",
                fg=TM_OK,
            )
            self.root.after(
                2000,
                lambda: self.models_status_lbl.configure(
                    text=f"共 {len(self.models)} 个 · 使用中：{self.models[self.model_idx]['name']}",
                    fg=TM_META,
                )
                if self.models
                else None,
            )

    def import_model(self) -> None:
        paths = filedialog.askopenfilenames(
            title="选择 RVC 模型 (.pth)",
            filetypes=[("RVC 模型", "*.pth"), ("全部", "*.*")],
        )
        if not paths:
            return
        n = 0
        for p in paths:
            try:
                import_model_to_catalog(Path(p), MODELS_DIR)
                n += 1
            except Exception as e:
                messagebox.showerror("导入失败", f"{p}\n{e}")
        self.refresh_models()
        if n:
            messagebox.showinfo("导入完成", f"已写入 {n} 个模型到\n{MODELS_DIR}")

    def _page_settings(self) -> tk.Frame:
        fr = tk.Frame(self.body, bg=TM_BG)
        wrap = tk.Frame(fr, bg=TM_BG)
        wrap.pack(fill="both", expand=True, padx=36, pady=20)

        left = tk.Frame(
            wrap,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            padx=16,
            pady=12,
        )
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right = tk.Frame(
            wrap,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            padx=16,
            pady=12,
        )
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        tk.Label(
            left, text="设备与音频", font=serif_font(13, "bold"), bg=TM_SURFACE, fg=TM_INK
        ).pack(anchor="w", pady=(0, 8))
        tk.Label(
            left,
            text="输入：麦克风\n输出：CABLE Input（安装虚拟声卡后）\n"
            "游戏 / 语音软件麦克风：CABLE Output\n\n"
            "细调设备请打开「高级实时面板」。",
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            justify="left",
        ).pack(anchor="w")
        tk.Button(
            left,
            text="打开高级实时面板",
            font=sans_font(9),
            bg=TM_ACCENT,
            fg=TM_ACCENT_INK,
            relief="flat",
            cursor="hand2",
            command=self.open_legacy_gui,
            bd=0,
            pady=6,
        ).pack(anchor="w", pady=12)

        tk.Label(
            right, text="变声参数", font=serif_font(13, "bold"), bg=TM_SURFACE, fg=TM_INK
        ).pack(anchor="w", pady=(0, 8))
        self.var_pitch = tk.IntVar(value=int(self.cfg.get("pitch") or 0))
        self.var_formant = tk.DoubleVar(value=float(self.cfg.get("formant") or 0))
        self.var_f0 = tk.StringVar(value=self.cfg.get("f0method") or "fcpe")

        def scale_row(parent, label, widget):
            f = tk.Frame(parent, bg=TM_SURFACE)
            f.pack(fill="x", pady=6)
            tk.Label(
                f, text=label, width=12, anchor="w", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(9)
            ).pack(side="left")
            widget.pack(side="left", fill="x", expand=True)

        scale_row(
            right,
            "音高 Pitch",
            tk.Scale(
                right,
                from_=-24,
                to=24,
                orient="horizontal",
                variable=self.var_pitch,
                bg=TM_SURFACE,
                fg=TM_INK,
                highlightthickness=0,
                troughcolor=TM_HAIRLINE,
                length=220,
            ),
        )
        scale_row(
            right,
            "共鸣 Formant",
            tk.Scale(
                right,
                from_=-2,
                to=2,
                resolution=0.1,
                orient="horizontal",
                variable=self.var_formant,
                bg=TM_SURFACE,
                fg=TM_INK,
                highlightthickness=0,
                troughcolor=TM_HAIRLINE,
                length=220,
            ),
        )
        f0f = tk.Frame(right, bg=TM_SURFACE)
        f0f.pack(fill="x", pady=6)
        tk.Label(
            f0f, text="音高算法", width=12, anchor="w", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(9)
        ).pack(side="left")
        ttk.Combobox(
            f0f,
            textvariable=self.var_f0,
            values=["fcpe", "rmvpe", "harvest", "crepe", "pm"],
            state="readonly",
            width=12,
        ).pack(side="left")
        tk.Button(
            right,
            text="保存设置",
            font=sans_font(9),
            bg=TM_ACCENT,
            fg=TM_ACCENT_INK,
            relief="flat",
            cursor="hand2",
            command=self.save_settings,
            bd=0,
            pady=6,
        ).pack(anchor="e", pady=12)
        return fr

    def save_settings(self) -> None:
        self.cfg["pitch"] = int(self.var_pitch.get())
        self.cfg["formant"] = float(self.var_formant.get())
        self.cfg["f0method"] = self.var_f0.get()
        save_config(self.cfg)
        messagebox.showinfo("已保存", f"设置已写入\n{USER_DATA}")

    def save_settings_silent(self) -> None:
        try:
            self.cfg["pitch"] = int(self.var_pitch.get())
            self.cfg["formant"] = float(self.var_formant.get())
            self.cfg["f0method"] = self.var_f0.get()
            save_config(self.cfg)
        except Exception:
            pass

    def _page_more(self) -> tk.Frame:
        fr = tk.Frame(self.body, bg=TM_BG)
        box = tk.Frame(fr, bg=TM_BG)
        box.place(relx=0.5, rely=0.42, anchor="center")

        def soft(text, cmd):
            tk.Button(
                box,
                text=text,
                font=sans_font(11),
                bg=TM_SURFACE,
                fg=TM_INK,
                relief="flat",
                width=30,
                pady=11,
                cursor="hand2",
                command=cmd,
                bd=0,
                highlightthickness=1,
                highlightbackground=TM_HAIRLINE,
            ).pack(pady=6)

        soft("打开训练 / 翻唱 WebUI（高级 · 浏览器）", self.open_webui)
        soft("打开首次设置启动器", self.open_bootstrap)
        soft("打开 User_Data", lambda: open_path(USER_DATA))
        soft("打开安装目录", lambda: open_path(ROOT))
        soft("使用说明", self.open_help)
        tk.Label(
            fr,
            text="Turing Mirror 配套 · 开源 RVC 引擎 · 请遵守当地法规与平台规则",
            bg=TM_BG,
            fg=TM_META,
            font=sans_font(8),
        ).place(relx=0.5, rely=0.9, anchor="center")
        return fr

    def open_bootstrap(self) -> None:
        from launcher.paths import find_python
        from launcher.win_util import run_no_console

        pyw = find_python(prefer_windowed=True)
        run_no_console([pyw, str(ROOT / "launcher" / "bootstrap.py")])

    def open_help(self) -> None:
        """User-facing help in a popup window (not developer markdown files)."""
        win = tk.Toplevel(self.root)
        win.title("使用说明")
        win.configure(bg=TM_BG)
        win.geometry("520x480")
        win.minsize(420, 360)
        win.transient(self.root)
        try:
            win.grab_set()
        except Exception:
            pass

        tk.Label(
            win,
            text="Turing Mirror 变声器 · 使用说明",
            font=serif_font(16, "bold"),
            bg=TM_BG,
            fg=TM_INK,
        ).pack(anchor="w", padx=20, pady=(18, 6))

        frame = tk.Frame(win, bg=TM_SURFACE, highlightthickness=1, highlightbackground=TM_HAIRLINE)
        frame.pack(fill="both", expand=True, padx=20, pady=8)

        text = tk.Text(
            frame,
            wrap="word",
            font=sans_font(10),
            bg=TM_SURFACE,
            fg=TM_INK,
            relief="flat",
            padx=14,
            pady=12,
            cursor="arrow",
        )
        scroll = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)

        body = (
            "【快速上手：实时变声】\n"
            "1. 首次：用「首次设置启动器」安装虚拟声卡（VB-Cable），并发送桌面快捷方式。\n"
            "2. 在「模型」页导入或选择音色（.pth，约 50–60MB 的推理小模型）。\n"
            "3. 点底部「开启变声」或「高级实时面板」。\n"
            "4. 实时面板里建议：\n"
            "   · 输入设备 = 你的麦克风\n"
            "   · 输出设备 = CABLE Input（虚拟声卡）\n"
            "   · 输入/输出尽量选同一种类型（例如都是 MME，或都是 ASIO）\n"
            "5. 游戏 / QQ / 微信 / Discord 的「麦克风」选 CABLE Output。\n"
            "6. 自己监听可戴耳机，避免扬声器回授啸叫。\n"
            "\n"
            "【音高与参数（大家最常问）】\n"
            "· 音高 Pitch：男变女常试 +8～+12；女变男试 -8～-12；同性别可从 0 微调。\n"
            "· 音高算法：实时优先 fcpe / rmvpe（更稳、少哑音）；不稳可换 harvest。\n"
            "· 特征检索 index rate：越高越像模型音色、越少「漏原声」；模型音质一般时\n"
            "  过高可能发糊，可试 0.3～0.75。没有 .index 文件也可以用，只是还原度可能差一点。\n"
            "· 响度/包络：实时里可让输出响度贴近你的说话大小，减少「不说话还有底噪」。\n"
            "\n"
            "【音色模型】\n"
            "· 请使用约 55–60MB 的推理用 .pth（别人分享的「小模型」）。\n"
            "· 不要用训练过程里几百 MB 的大文件去变声，容易打不开或报错。\n"
            "· 导入：本页「模型」→「导入模型」。有同名 .index 时尽量一起使用。\n"
            "· 分享给朋友：发小模型 .pth + 对应 .index（如有），不要发训练日志里的大包。\n"
            "\n"
            "【常见问题与解决】\n"
            "\n"
            "Q：对方听不到变声，只有原声或没声？\n"
            "A：1）是否安装 VB-Cable 且软件输出选 CABLE Input；\n"
            "   2）对方软件麦克风是否选 CABLE Output；\n"
            "   3）变声是否已点 Start/开启；\n"
            "   4）关掉系统「对麦克风的独占模式」或换一组同类型设备再试。\n"
            "\n"
            "Q：只有自己能听到变声，通话软件里没有？\n"
            "A：通话软件选错麦克风。应选 CABLE Output，不要选物理麦克风。\n"
            "\n"
            "Q：破音、电流声、爆破音？\n"
            "A：1）输入输出选同一种 API；\n"
            "   2）略增大缓冲/块时长，降低采样压力；\n"
            "   3）麦克风增益别过大；\n"
            "   4）关掉其他占用麦克风的软件；\n"
            "   5）ASIO 用户确认驱动稳定。\n"
            "\n"
            "Q：延迟很高，对不上嘴？\n"
            "A：1）减小实时块时长（过小可能爆音，需折中）；\n"
            "   2）优先用独立显卡，关省电；\n"
            "   3）关闭无关后台；\n"
            "   4）输入输出用同类型低延迟设备（ASIO 通常更低，但看驱动）。\n"
            "\n"
            "Q：变出来不像、发虚、哑音（没音调）？\n"
            "A：1）换 rmvpe/fcpe 音高算法；\n"
            "   2）微调 Pitch；\n"
            "   3）有 index 时打开检索并试 index rate；\n"
            "   4）换更高质量的模型；干声/原麦尽量清晰少底噪。\n"
            "\n"
            "Q：一说话有杂音，不说话也有沙沙声？\n"
            "A：调高门限/阈值，打开输入降噪（若面板有）；麦克风远离风扇；\n"
            "   可开「响度贴近输入」减少静音段噪声。\n"
            "\n"
            "Q：显存不足 / CUDA out of memory？\n"
            "A：关闭其他占显存程序；换更小模型或降低实时质量相关选项；\n"
            "   显存很小的卡实时会吃力，可尝试 CPU（更慢）或减小音频块。\n"
            "\n"
            "Q：翻唱/推理时报路径、ffmpeg 错误？\n"
            "A：音频路径尽量不要有特殊符号；可先把文件拷到简单英文路径再试。\n"
            "   本整合包已带 ffmpeg 时一般无需另装。\n"
            "\n"
            "Q：WebUI 提示 Connection Error 或 JSON 解析错误？\n"
            "A：关掉系统代理/VPN 全局模式后再开；不要关掉正在运行的主程序窗口。\n"
            "\n"
            "Q：模型列表是空的？\n"
            "A：到「模型」页导入 .pth；导入后点刷新。确认文件是完整推理模型。\n"
            "\n"
            "Q：想自己训练音色？\n"
            "A：用「其他」里的训练/翻唱 WebUI。建议干净人声约 10 分钟以上；\n"
            "   音质差时轮数不必太多（大约 20–50 轮量级按效果调整）。\n"
            "   训练完成后用「小模型」做推理和分享，不要把训练中途的大文件当成品。\n"
            "\n"
            "【提示】\n"
            "日常开黑只需要：虚拟声卡 + 音色 + 实时变声。\n"
            "训练/翻唱 WebUI 是进阶功能，不是每次都要开。\n"
            "\n"
            "本软件与 Turing Mirror 配套，请遵守当地法律法规与游戏/平台规则。"
        )
        text.insert("1.0", body)
        text.configure(state="disabled")

        tk.Button(
            win,
            text="知道了",
            font=sans_font(10, "bold"),
            bg=TM_ACCENT,
            fg=TM_ACCENT_INK,
            relief="flat",
            padx=24,
            pady=8,
            cursor="hand2",
            command=win.destroy,
            bd=0,
        ).pack(pady=14)

        # Center on parent
        try:
            win.update_idletasks()
            px = self.root.winfo_rootx() + 80
            py = self.root.winfo_rooty() + 40
            win.geometry(f"+{px}+{py}")
            win.lift()
            win.focus_force()
        except Exception:
            pass

    def open_webui(self) -> None:
        try:
            if self.webui_proc is None or self.webui_proc.poll() is not None:
                self.webui_proc = start_webui(7897)
            threading.Thread(target=self._open_browser_later, daemon=True).start()
            messagebox.showinfo(
                "WebUI",
                "正在后台启动（无黑框）。\n浏览器将打开 http://127.0.0.1:7897",
            )
        except Exception as e:
            messagebox.showerror("失败", str(e))

    def _open_browser_later(self) -> None:
        time.sleep(3.5)
        try:
            webbrowser.open("http://127.0.0.1:7897")
        except Exception:
            pass

    def _watch_realtime_gui(self, proc) -> None:
        """Background: surface crash; when window appears, bring to front."""
        log = realtime_gui_log_path()
        try:
            # Cold start: torch/CUDA often 20–40s before FreeSimpleGUI window
            focused = focus_window_by_title("RVC - GUI", timeout_s=50.0)
            if focused:
                def _ok():
                    self.lbl_online.configure(text="实时面板已打开", fg=TM_OK)
                self.root.after(0, _ok)
                return
            if proc.poll() is not None:
                tail = read_tail(log)
                msg = (
                    f"实时面板进程已退出（代码 {proc.returncode}）。\n"
                    f"日志：{log}\n\n{tail or '（日志为空，可能是 Runtime/依赖缺失）'}"
                )

                def _fail():
                    self.lbl_online.configure(text="实时面板启动失败", fg="#a33")
                    self.vc_running = False
                    try:
                        self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
                    except Exception:
                        pass
                    messagebox.showerror("实时面板启动失败", msg)

                self.root.after(0, _fail)
                return

            def _slow():
                self.lbl_online.configure(
                    text="实时面板加载中…若无窗口请看任务栏",
                    fg=TM_META,
                )

            self.root.after(0, _slow)
        except Exception:
            pass

    def open_legacy_gui(self) -> None:
        try:
            self.save_settings_silent()
            if self.models:
                self._sync_model_to_realtime_gui(self.models[self.model_idx])
            # Do NOT show a blocking "已载入音色" dialog — that looked like the
            # only result while gui_v1 still loads torch for ~30s.
            name = ""
            if self.models:
                name = self.models[self.model_idx].get("name") or ""
            self.lbl_online.configure(
                text="正在启动实时面板（约 20–40 秒）…",
                fg=TM_OK,
            )
            proc = start_legacy_realtime_gui()
            self.gui_proc = proc
            threading.Thread(
                target=self._watch_realtime_gui,
                args=(proc,),
                daemon=True,
            ).start()
            if name:
                # Non-blocking status only; window will appear separately
                self.lbl_online.configure(
                    text=f"启动中：{name}（首次约半分钟）",
                    fg=TM_OK,
                )
        except Exception as e:
            messagebox.showerror("失败", str(e))

    def toggle_vc(self) -> None:
        if not self.models:
            messagebox.showwarning("没有模型", "请先导入音色。")
            self.show_page("models")
            return
        if self.vc_running:
            self.vc_running = False
            self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
            self.lbl_online.configure(text="引擎待命", fg=TM_META)
            messagebox.showinfo("提示", "若实时面板仍在运行，请在面板内停止。")
            return
        m = self.models[self.model_idx]
        self.save_settings_silent()
        self._sync_model_to_realtime_gui(m)
        try:
            proc = start_legacy_realtime_gui()
            self.gui_proc = proc
            self.vc_running = True
            self.btn_start.configure(text="变声运行中", bg=TM_OK)
            self.lbl_online.configure(
                text=f"启动中：{m['name']}（约 20–40 秒）",
                fg=TM_OK,
            )
            threading.Thread(
                target=self._watch_realtime_gui,
                args=(proc,),
                daemon=True,
            ).start()
        except Exception as e:
            messagebox.showerror("启动失败", str(e))

    def _tick_status(self) -> None:
        self.root.after(2000, self._tick_status)

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self) -> None:
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self.root.destroy()


def main() -> None:
    os.chdir(ROOT)
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except Exception:
        pass
    log = ROOT / "TEMP" / "gui_alive.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("main_app main() enter\n", encoding="utf-8")
    except Exception:
        pass
    app = MainApp()
    try:
        log.write_text(
            "main_app window up geometry=" + app.root.geometry() + "\n",
            encoding="utf-8",
        )
    except Exception:
        pass
    app.run()


if __name__ == "__main__":
    main()
