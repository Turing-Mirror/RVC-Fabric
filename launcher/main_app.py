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

from launcher.catalog import (
    bind_index_to_model_dir,
    clear_model_index,
    discover_index_files,
    import_model_to_catalog,
)
from launcher.config_store import load_config, save_config, sync_realtime_gui_model
from launcher.paths import (
    APP_TITLE,
    MODELS_DIR,
    USER_DATA,
    ensure_dirs,
    index_search_roots,
    list_voice_models,
)
from launcher import realtime_client as rt_client
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
        self._vc_starting = False
        self._current_page = "home"
        self._resize_job = None
        self._toast_job = None
        self._placed_once = False
        self._hot_job = None
        self._device_lists = {
            "hostapis": [],
            "input_devices": [],
            "output_devices": [],
        }

        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("980x680")
        self.root.minsize(780, 520)
        self.root.configure(bg=TM_BG)
        self._place_and_raise(force_size=True)

        self._build_chrome()
        self._build_pages()
        self.root.bind("<Configure>", self._on_root_configure)
        self.show_page("home")
        self._tick_status()
        self.root.after(200, lambda: self._place_and_raise(force_size=False))
        self.root.after(800, lambda: self._place_and_raise(force_size=False))
        self.root.after(600, self._bootstrap_devices_async)

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
        self._refresh_index_ui_for_model(m)

    def _sync_model_to_realtime_gui(self, m: Optional[dict] = None) -> None:
        """Write current model + full settings into engine config.json."""
        if m is None:
            if not self.models:
                return
            m = self.models[self.model_idx]
        pth = m.get("path") or ""
        if not pth:
            return
        idx_path = ""
        try:
            if hasattr(self, "var_index_path"):
                idx_path = str(self.var_index_path.get() or "").strip()
        except Exception:
            idx_path = ""
        if not idx_path:
            idx_path = m.get("index") or ""
        try:
            self._collect_settings_into_cfg()
            # Keep rate 0 when no index file
            if not idx_path or not Path(idx_path).is_file():
                self.cfg["index_rate"] = 0.0
                try:
                    if hasattr(self, "var_index_rate"):
                        self.var_index_rate.set(0.0)
                except Exception:
                    pass
            sync_realtime_gui_model(
                pth,
                idx_path,
                app_cfg=self.cfg,
            )
        except Exception:
            pass

    def _refresh_index_ui_for_model(self, m: Optional[dict] = None) -> None:
        """Update settings page index path label for current voice."""
        if not hasattr(self, "var_index_path"):
            return
        if m is None:
            if not self.models:
                self.var_index_path.set("")
                self._update_index_hint()
                return
            m = self.models[self.model_idx]
        idx = str(m.get("index") or "").strip()
        if idx and not Path(idx).is_file():
            idx = ""
        self.var_index_path.set(idx)
        self._update_index_hint()
        try:
            self._refresh_index_combobox_values()
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
        # Scrollable settings
        canvas = tk.Canvas(fr, bg=TM_BG, highlightthickness=0)
        sb = ttk.Scrollbar(fr, orient="vertical", command=canvas.yview)
        wrap = tk.Frame(canvas, bg=TM_BG)
        wrap.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=wrap, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # --- vars ---
        self.var_pitch = tk.IntVar(value=int(self.cfg.get("pitch") or 0))
        self.var_formant = tk.DoubleVar(value=float(self.cfg.get("formant") or 0))
        self.var_f0 = tk.StringVar(value=str(self.cfg.get("f0method") or "fcpe"))
        self.var_threhold = tk.IntVar(
            value=int(self.cfg.get("threhold") if self.cfg.get("threhold") is not None else -60)
        )
        self.var_index_rate = tk.DoubleVar(value=float(self.cfg.get("index_rate") or 0))
        self.var_rms = tk.DoubleVar(value=float(self.cfg.get("rms_mix_rate") or 0))
        self.var_block = tk.DoubleVar(value=float(self.cfg.get("block_time") or 0.25))
        self.var_crossfade = tk.DoubleVar(
            value=float(self.cfg.get("crossfade_length") or 0.05)
        )
        self.var_extra = tk.DoubleVar(value=float(self.cfg.get("extra_time") or 2.5))
        self.var_n_cpu = tk.IntVar(value=int(self.cfg.get("n_cpu") or 4))
        self.var_hostapi = tk.StringVar(value=str(self.cfg.get("sg_hostapi") or "MME"))
        self.var_input_dev = tk.StringVar(value=str(self.cfg.get("sg_input_device") or ""))
        self.var_output_dev = tk.StringVar(
            value=str(self.cfg.get("sg_output_device") or "")
        )
        self.var_wasapi = tk.BooleanVar(value=bool(self.cfg.get("sg_wasapi_exclusive")))
        self.var_sr_type = tk.StringVar(value=str(self.cfg.get("sr_type") or "sr_model"))
        self.var_i_nr = tk.BooleanVar(value=bool(self.cfg.get("I_noise_reduce")))
        self.var_o_nr = tk.BooleanVar(value=bool(self.cfg.get("O_noise_reduce")))
        self.var_use_pv = tk.BooleanVar(value=bool(self.cfg.get("use_pv")))
        self.var_function = tk.StringVar(value=str(self.cfg.get("function") or "vc"))

        def card(parent, title: str) -> tk.Frame:
            box = tk.Frame(
                parent,
                bg=TM_SURFACE,
                highlightthickness=1,
                highlightbackground=TM_HAIRLINE,
                padx=14,
                pady=10,
            )
            box.pack(fill="x", padx=28, pady=8)
            tk.Label(
                box, text=title, font=serif_font(12, "bold"), bg=TM_SURFACE, fg=TM_INK
            ).pack(anchor="w", pady=(0, 6))
            return box

        def scale_row(parent, label, variable, from_, to, res=1, hot=False):
            f = tk.Frame(parent, bg=TM_SURFACE)
            f.pack(fill="x", pady=3)
            tk.Label(
                f,
                text=label,
                width=14,
                anchor="w",
                bg=TM_SURFACE,
                fg=TM_INK_MUTED,
                font=sans_font(9),
            ).pack(side="left")
            sc = tk.Scale(
                f,
                from_=from_,
                to=to,
                resolution=res,
                orient="horizontal",
                variable=variable,
                bg=TM_SURFACE,
                fg=TM_INK,
                highlightthickness=0,
                troughcolor=TM_HAIRLINE,
                length=260,
                command=(lambda _v: self._on_hot_param()) if hot else None,
            )
            sc.pack(side="left", fill="x", expand=True)
            return sc

        # Device card
        left = card(wrap, "设备与音频")
        tk.Label(
            left,
            text=(
                "输入=真实麦克风 · 输出=CABLE Input · 游戏麦克风=CABLE Output\n"
                "点「开启变声」在本软件内开始，无需再开第二个窗口。"
            ),
            font=sans_font(8),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            justify="left",
        ).pack(anchor="w", pady=(0, 6))

        row = tk.Frame(left, bg=TM_SURFACE)
        row.pack(fill="x", pady=3)
        tk.Label(
            row, text="设备类型", width=14, anchor="w", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(9)
        ).pack(side="left")
        self.cmb_hostapi = ttk.Combobox(
            row, textvariable=self.var_hostapi, values=["MME"], state="readonly", width=28
        )
        self.cmb_hostapi.pack(side="left")
        self.cmb_hostapi.bind("<<ComboboxSelected>>", lambda e: self._on_hostapi_change())

        row = tk.Frame(left, bg=TM_SURFACE)
        row.pack(fill="x", pady=3)
        tk.Label(
            row, text="输入设备", width=14, anchor="w", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(9)
        ).pack(side="left")
        self.cmb_input = ttk.Combobox(
            row, textvariable=self.var_input_dev, values=[], state="readonly", width=48
        )
        self.cmb_input.pack(side="left", fill="x", expand=True)

        row = tk.Frame(left, bg=TM_SURFACE)
        row.pack(fill="x", pady=3)
        tk.Label(
            row, text="输出设备", width=14, anchor="w", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(9)
        ).pack(side="left")
        self.cmb_output = ttk.Combobox(
            row, textvariable=self.var_output_dev, values=[], state="readonly", width=48
        )
        self.cmb_output.pack(side="left", fill="x", expand=True)

        row = tk.Frame(left, bg=TM_SURFACE)
        row.pack(fill="x", pady=4)
        tk.Checkbutton(
            row,
            text="WASAPI 独占（一般不要勾）",
            variable=self.var_wasapi,
            bg=TM_SURFACE,
            fg=TM_INK,
            activebackground=TM_SURFACE,
            font=sans_font(9),
        ).pack(side="left")
        tk.Label(
            row, text="采样率", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(9)
        ).pack(side="left", padx=(16, 4))
        ttk.Combobox(
            row,
            textvariable=self.var_sr_type,
            values=["sr_model", "sr_device"],
            state="readonly",
            width=12,
        ).pack(side="left")
        tk.Button(
            row,
            text="重载设备列表",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_INK,
            relief="flat",
            cursor="hand2",
            command=self.reload_devices,
            bd=0,
            padx=10,
        ).pack(side="right")

        btnrow = tk.Frame(left, bg=TM_SURFACE)
        btnrow.pack(fill="x", pady=6)
        tk.Button(
            btnrow,
            text="声卡接线说明",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            relief="flat",
            cursor="hand2",
            command=self._show_cable_help,
            bd=0,
            padx=10,
            pady=4,
        ).pack(side="left")
        tk.Button(
            btnrow,
            text="打开原版实时面板",
            font=sans_font(9),
            bg=TM_ACCENT,
            fg=TM_ACCENT_INK,
            relief="flat",
            cursor="hand2",
            command=self.open_legacy_gui,
            bd=0,
            padx=10,
            pady=4,
        ).pack(side="left", padx=8)

        # Voice params
        right = card(wrap, "变声参数（运行中可热更新）")
        scale_row(right, "响应阈值", self.var_threhold, -60, 0, 1, hot=True)
        scale_row(right, "音高 Pitch", self.var_pitch, -24, 24, 1, hot=True)
        scale_row(right, "共鸣 Formant", self.var_formant, -2, 2, 0.05, hot=True)
        scale_row(right, "Index Rate", self.var_index_rate, 0, 1, 0.01, hot=True)
        scale_row(right, "响度因子", self.var_rms, 0, 1, 0.01, hot=True)

        # Feature retrieval .index (bound to current voice model)
        self.var_index_path = tk.StringVar(value="")
        idx_block = tk.Frame(right, bg=TM_SURFACE)
        idx_block.pack(fill="x", pady=(8, 4))
        tk.Label(
            idx_block,
            text="特征检索 .index",
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            idx_block,
            text=(
                "对应原版实时面板的 .index 文件（特征检索库，不是训练底模）。\n"
                "绑定到当前音色；换音色会跟着切换。改后需重新「开启变声」。"
            ),
            font=sans_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            justify="left",
            anchor="w",
        ).pack(anchor="w", pady=(0, 4))
        idx_row = tk.Frame(idx_block, bg=TM_SURFACE)
        idx_row.pack(fill="x")
        self.cmb_index = ttk.Combobox(
            idx_row,
            textvariable=self.var_index_path,
            values=[],
            width=52,
        )
        self.cmb_index.pack(side="left", fill="x", expand=True)
        self.cmb_index.bind("<<ComboboxSelected>>", lambda e: self._on_index_chosen())
        tk.Button(
            idx_row,
            text="浏览…",
            font=sans_font(8),
            bg=TM_BG,
            fg=TM_INK,
            relief="flat",
            cursor="hand2",
            command=self.browse_index_file,
            bd=0,
            padx=8,
        ).pack(side="left", padx=(6, 0))
        tk.Button(
            idx_row,
            text="清除",
            font=sans_font(8),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            relief="flat",
            cursor="hand2",
            command=self.clear_index_file,
            bd=0,
            padx=8,
        ).pack(side="left")
        tk.Button(
            idx_row,
            text="扫描",
            font=sans_font(8),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            relief="flat",
            cursor="hand2",
            command=self._refresh_index_combobox_values,
            bd=0,
            padx=8,
        ).pack(side="left")
        self.lbl_index_status = tk.Label(
            idx_block,
            text="",
            font=sans_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        )
        self.lbl_index_status.pack(anchor="w", pady=(2, 0))
        self._refresh_index_ui_for_model()

        f0f = tk.Frame(right, bg=TM_SURFACE)
        f0f.pack(fill="x", pady=3)
        tk.Label(
            f0f, text="音高算法", width=14, anchor="w", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(9)
        ).pack(side="left")
        cmb_f0 = ttk.Combobox(
            f0f,
            textvariable=self.var_f0,
            values=["fcpe", "rmvpe", "harvest", "crepe", "pm"],
            state="readonly",
            width=12,
        )
        cmb_f0.pack(side="left")
        cmb_f0.bind("<<ComboboxSelected>>", lambda e: self._on_hot_param())

        modef = tk.Frame(right, bg=TM_SURFACE)
        modef.pack(fill="x", pady=4)
        tk.Label(
            modef, text="模式", width=14, anchor="w", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(9)
        ).pack(side="left")
        tk.Radiobutton(
            modef,
            text="输出变声",
            variable=self.var_function,
            value="vc",
            bg=TM_SURFACE,
            command=self._on_hot_param,
            font=sans_font(9),
        ).pack(side="left")
        tk.Radiobutton(
            modef,
            text="输入监听",
            variable=self.var_function,
            value="im",
            bg=TM_SURFACE,
            command=self._on_hot_param,
            font=sans_font(9),
        ).pack(side="left", padx=8)

        # Performance
        perf = card(wrap, "性能设置（改后需重新「开启变声」）")
        scale_row(perf, "采样长度", self.var_block, 0.02, 1.5, 0.01)
        scale_row(perf, "淡入淡出", self.var_crossfade, 0.01, 0.15, 0.01)
        scale_row(perf, "额外推理时长", self.var_extra, 0.05, 5.0, 0.01)
        scale_row(perf, "harvest进程数", self.var_n_cpu, 1, 8, 1)
        nrf = tk.Frame(perf, bg=TM_SURFACE)
        nrf.pack(fill="x", pady=4)
        tk.Checkbutton(
            nrf,
            text="输入降噪",
            variable=self.var_i_nr,
            bg=TM_SURFACE,
            command=self._on_hot_param,
            font=sans_font(9),
        ).pack(side="left")
        tk.Checkbutton(
            nrf,
            text="输出降噪",
            variable=self.var_o_nr,
            bg=TM_SURFACE,
            command=self._on_hot_param,
            font=sans_font(9),
        ).pack(side="left", padx=8)
        tk.Checkbutton(
            nrf,
            text="相位声码器",
            variable=self.var_use_pv,
            bg=TM_SURFACE,
            command=self._on_hot_param,
            font=sans_font(9),
        ).pack(side="left")

        act = tk.Frame(wrap, bg=TM_BG)
        act.pack(fill="x", padx=28, pady=10)
        tk.Button(
            act,
            text="保存设置",
            font=sans_font(10),
            bg=TM_ACCENT,
            fg=TM_ACCENT_INK,
            relief="flat",
            cursor="hand2",
            command=self.save_settings,
            bd=0,
            padx=16,
            pady=6,
        ).pack(side="right")
        self.lbl_settings_hint = tk.Label(
            act,
            text="无 .index 时 Index Rate 自动为 0；换 index 后请重新开启变声",
            font=sans_font(8),
            bg=TM_BG,
            fg=TM_META,
        )
        self.lbl_settings_hint.pack(side="left")
        return fr

    def _update_index_hint(self) -> None:
        if not hasattr(self, "lbl_index_status"):
            return
        path = ""
        try:
            path = str(self.var_index_path.get() or "").strip()
        except Exception:
            path = ""
        if not path:
            self.lbl_index_status.configure(
                text="当前：未绑定 index（仅用 .pth，Index Rate=0）",
                fg=TM_META,
            )
            return
        if Path(path).is_file():
            self.lbl_index_status.configure(
                text=f"当前：{Path(path).name}",
                fg=TM_OK,
            )
        else:
            self.lbl_index_status.configure(
                text="当前路径无效，请重新选择 .index",
                fg=TM_META,
            )

    def _refresh_index_combobox_values(self) -> None:
        if not hasattr(self, "cmb_index"):
            return
        roots = index_search_roots()
        found = discover_index_files(roots)
        # Always include current selection even if outside roots
        cur = ""
        try:
            cur = str(self.var_index_path.get() or "").strip()
        except Exception:
            pass
        if cur and cur not in found and Path(cur).is_file():
            found = [cur] + found
        self.cmb_index["values"] = found
        self._update_index_hint()

    def _on_index_chosen(self) -> None:
        path = str(self.var_index_path.get() or "").strip()
        if path and Path(path).is_file():
            self._apply_index_to_current_model(path)
        else:
            self._update_index_hint()

    def browse_index_file(self) -> None:
        if not self.models:
            messagebox.showwarning("没有模型", "请先在「模型」页选择或导入音色。")
            return
        initial = MODELS_DIR
        m = self.models[self.model_idx]
        if m.get("dir") and Path(m["dir"]).is_dir():
            initial = Path(m["dir"])
        path = filedialog.askopenfilename(
            title="选择特征检索 .index 文件",
            initialdir=str(initial),
            filetypes=[
                ("FAISS index", "*.index"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self._apply_index_to_current_model(path)

    def clear_index_file(self) -> None:
        if not self.models:
            return
        m = self.models[self.model_idx]
        model_dir = m.get("dir") or ""
        try:
            if model_dir and m.get("source") == "user_data":
                clear_model_index(Path(model_dir))
            m["index"] = ""
            self.var_index_path.set("")
            self.cfg["index_rate"] = 0.0
            if hasattr(self, "var_index_rate"):
                self.var_index_rate.set(0.0)
            save_config(self.cfg)
            self._sync_model_to_realtime_gui(m)
            self._update_index_hint()
            self.lbl_online.configure(
                text="已清除 index（需重新开启变声才完全生效）",
                fg=TM_META,
            )
        except Exception as e:
            messagebox.showerror("清除失败", str(e))

    def _apply_index_to_current_model(self, index_path: str) -> None:
        if not self.models:
            return
        m = self.models[self.model_idx]
        ip = Path(index_path)
        if not ip.is_file():
            messagebox.showerror("无效文件", f"找不到：\n{index_path}")
            return
        try:
            model_dir = m.get("dir") or ""
            if model_dir and m.get("source") == "user_data":
                bound = bind_index_to_model_dir(
                    Path(model_dir),
                    ip,
                    display_name=m.get("name"),
                    copy_into_folder=True,
                )
            else:
                # Legacy weights: keep absolute path without catalog sidecar
                bound = str(ip.resolve())
            m["index"] = bound
            self.var_index_path.set(bound)
            # Sensible default rate when binding an index
            if float(self.cfg.get("index_rate") or 0) <= 0:
                self.cfg["index_rate"] = 0.5
                if hasattr(self, "var_index_rate"):
                    self.var_index_rate.set(0.5)
            save_config(self.cfg)
            self._sync_model_to_realtime_gui(m)
            self._refresh_index_combobox_values()
            self._update_index_hint()
            self.lbl_online.configure(
                text=f"已绑定 index：{Path(bound).name}（请重新开启变声）",
                fg=TM_OK,
            )
            if self.vc_running:
                messagebox.showinfo(
                    "需要重新开始",
                    "特征检索库已更换。\n请先「停止变声」再「开启变声」后才会加载新的 .index。",
                )
        except Exception as e:
            messagebox.showerror("绑定失败", str(e))

    def _collect_settings_into_cfg(self) -> None:
        """Pull UI vars into self.cfg (safe if settings page not built yet)."""
        try:
            self.cfg["pitch"] = int(self.var_pitch.get())
            self.cfg["formant"] = float(self.var_formant.get())
            self.cfg["f0method"] = str(self.var_f0.get())
            self.cfg["threhold"] = int(self.var_threhold.get())
            self.cfg["index_rate"] = float(self.var_index_rate.get())
            self.cfg["rms_mix_rate"] = float(self.var_rms.get())
            self.cfg["block_time"] = float(self.var_block.get())
            self.cfg["crossfade_length"] = float(self.var_crossfade.get())
            self.cfg["extra_time"] = float(self.var_extra.get())
            self.cfg["n_cpu"] = int(self.var_n_cpu.get())
            self.cfg["sg_hostapi"] = str(self.var_hostapi.get() or "MME")
            self.cfg["sg_input_device"] = str(self.var_input_dev.get() or "")
            self.cfg["sg_output_device"] = str(self.var_output_dev.get() or "")
            self.cfg["sg_wasapi_exclusive"] = bool(self.var_wasapi.get())
            self.cfg["sr_type"] = str(self.var_sr_type.get() or "sr_model")
            self.cfg["I_noise_reduce"] = bool(self.var_i_nr.get())
            self.cfg["O_noise_reduce"] = bool(self.var_o_nr.get())
            self.cfg["use_pv"] = bool(self.var_use_pv.get())
            self.cfg["function"] = str(self.var_function.get() or "vc")
        except Exception:
            pass

    def save_settings(self) -> None:
        self._collect_settings_into_cfg()
        save_config(self.cfg)
        if self.models:
            self._sync_model_to_realtime_gui(self.models[self.model_idx])
        if self.vc_running:
            self._push_hot_params()
        messagebox.showinfo("已保存", "设置已写入，并同步到变声引擎配置。")

    def save_settings_silent(self) -> None:
        try:
            self._collect_settings_into_cfg()
            save_config(self.cfg)
        except Exception:
            pass

    def _on_hot_param(self) -> None:
        """Debounced hot update while VC running."""
        if self._hot_job is not None:
            try:
                self.root.after_cancel(self._hot_job)
            except Exception:
                pass
        self._hot_job = self.root.after(180, self._push_hot_params)

    def _push_hot_params(self) -> None:
        self._hot_job = None
        self._collect_settings_into_cfg()
        try:
            save_config(self.cfg)
        except Exception:
            pass
        if not self.vc_running:
            return
        try:
            rt_client.set_params_remote(
                pitch=self.cfg.get("pitch"),
                formant=self.cfg.get("formant"),
                index_rate=self.cfg.get("index_rate"),
                rms_mix_rate=self.cfg.get("rms_mix_rate"),
                threhold=self.cfg.get("threhold"),
                f0method=self.cfg.get("f0method"),
                I_noise_reduce=self.cfg.get("I_noise_reduce"),
                O_noise_reduce=self.cfg.get("O_noise_reduce"),
                use_pv=self.cfg.get("use_pv"),
                function=self.cfg.get("function"),
            )
        except Exception:
            pass

    def _bootstrap_devices_async(self) -> None:
        def work():
            try:
                st = rt_client.ensure_worker_and_devices(timeout_s=100)
                self.root.after(0, lambda: self._apply_device_status(st))
            except Exception as e:
                self.root.after(
                    0,
                    lambda: self.lbl_online.configure(
                        text=f"设备枚举失败: {e}", fg=TM_META
                    ),
                )

        threading.Thread(target=work, daemon=True).start()
        self.lbl_online.configure(text="正在连接变声引擎…", fg=TM_OK)

    def reload_devices(self) -> None:
        # list_devices stops the audio stream on the worker — reflect that in UI
        if self.vc_running or self._vc_starting:
            self.vc_running = False
            self._vc_starting = False
            try:
                self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
            except Exception:
                pass
        self.lbl_online.configure(text="重载设备列表…", fg=TM_OK)

        def work():
            try:
                if not rt_client.is_worker_alive():
                    rt_client.start_worker_process()
                rt_client.wait_worker_ready(timeout_s=60)
                host = ""
                try:
                    host = self.var_hostapi.get()
                except Exception:
                    host = self.cfg.get("sg_hostapi") or ""
                # Save hostapi into config file path worker reads for list
                rt_client.send_command("list_devices", sg_hostapi=host)
                time.sleep(0.5)
                st = rt_client.poll_status()
                self.root.after(0, lambda: self._apply_device_status(st, toast=True))
            except Exception as e:
                self.root.after(
                    0, lambda: messagebox.showerror("重载失败", str(e))
                )

        threading.Thread(target=work, daemon=True).start()

    def _on_hostapi_change(self) -> None:
        self.reload_devices()

    def _apply_device_status(self, st: dict, toast: bool = False) -> None:
        if not st:
            return
        hosts = list(st.get("hostapis") or [])
        ins = list(st.get("input_devices") or [])
        outs = list(st.get("output_devices") or [])
        self._device_lists = {
            "hostapis": hosts,
            "input_devices": ins,
            "output_devices": outs,
        }
        try:
            if hasattr(self, "cmb_hostapi") and hosts:
                self.cmb_hostapi["values"] = hosts
                cur = self.var_hostapi.get()
                if cur not in hosts:
                    prefer = "MME" if "MME" in hosts else hosts[0]
                    self.var_hostapi.set(prefer)
            if hasattr(self, "cmb_input"):
                self.cmb_input["values"] = ins
                cur = self.var_input_dev.get()
                if (not cur or cur not in ins) and ins:
                    # Prefer non-cable mic
                    pick = next(
                        (
                            n
                            for n in ins
                            if "cable" not in n.lower()
                            and "voicemeeter" not in n.lower()
                        ),
                        ins[0],
                    )
                    self.var_input_dev.set(pick)
            if hasattr(self, "cmb_output"):
                self.cmb_output["values"] = outs
                cur = self.var_output_dev.get()
                if (not cur or cur not in outs) and outs:
                    pick = next(
                        (
                            n
                            for n in outs
                            if "cable input" in n.lower()
                            or "voicemeeter input" in n.lower()
                        ),
                        outs[0],
                    )
                    self.var_output_dev.set(pick)
        except Exception:
            pass
        err = str(st.get("error") or "")
        state = str(st.get("state") or "")
        if err and state == "error":
            self.lbl_online.configure(text=f"引擎错误: {err[:60]}", fg=TM_META)
        elif toast:
            self.lbl_online.configure(
                text=f"已刷新设备（输入 {len(ins)} / 输出 {len(outs)}）", fg=TM_OK
            )
        elif not self.vc_running and not self._vc_starting:
            self.lbl_online.configure(text="引擎待命", fg=TM_META)

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
        soft("强制结束变声引擎（卡音频时点）", self._force_kill_engine)
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

    def _force_kill_engine(self) -> None:
        """Emergency: kill all orphan workers and release sound devices."""
        if not messagebox.askyesno(
            "强制结束",
            "将强制结束所有变声后台进程并释放声卡。\n确定？",
        ):
            return
        try:
            n = rt_client.kill_all_project_workers()
            self.vc_running = False
            self._vc_starting = False
            self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
            self.lbl_online.configure(text="引擎已强制结束", fg=TM_META)
            self.lbl_latency.configure(text=APP_PRODUCT_TAGLINE)
            messagebox.showinfo("完成", f"已清理变声相关进程（约 {n} 个）。")
        except Exception as e:
            messagebox.showerror("失败", str(e))

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

    def _show_cable_help(self) -> None:
        messagebox.showinfo(
            "虚拟声卡接线",
            "推荐：VB-Cable 或 VoiceMeeter\n\n"
            "【本软件高级实时面板】\n"
            "· 输入设备：你的真实麦克风（不要选 CABLE）\n"
            "· 输出设备：CABLE Input\n"
            "  （有的列表显示为「CABLE Input (VB-Audio Virtual Cable)」）\n"
            "· 设备类型：MME 最省事；WASAPI 不要勾独占\n\n"
            "【游戏 / 语音软件】\n"
            "· 麦克风 / 输入：CABLE Output\n"
            "· 这样对面听到的是变声后的声音\n\n"
            "【自己监听】\n"
            "· 用耳机听系统声音；不要把 CABLE 设成 Windows 默认播放\n\n"
            "【开启变声】\n"
            "· 主界面点「开启变声」→ 自动打开面板并开始转换\n"
            "· 若只有 pth 没有 index 文件也能用，Index 会自动关闭\n"
            "· 首次加载模型约 20–40 秒，请稍候",
        )

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
        """Background: when RVC-GUI appears, bring to front; else report failure.

        Note: release path launches via wscript→VBS; that helper process exits
        immediately even when gui_v1 is still loading — do not treat early
        proc.poll()!=None as failure.
        """
        log = realtime_gui_log_path()
        vbs_log = Path(USER_DATA) / "logs" / "realtime_gui_vbs.log"
        try:
            # Cold start: torch/CUDA often 20–40s before FreeSimpleGUI window
            focused = focus_window_by_title("RVC - GUI", timeout_s=55.0)
            if focused:
                def _ok():
                    self.lbl_online.configure(text="实时面板已打开", fg=TM_OK)

                self.root.after(0, _ok)
                return

            tail = read_tail(log) + "\n" + read_tail(vbs_log)
            # If any pythonw running gui_v1 is still up, don't scare the user
            still = False
            try:
                import subprocess as _sp

                r = _sp.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "Get-CimInstance Win32_Process | "
                        "Where-Object { $_.CommandLine -match 'gui_v1' } | "
                        "Select-Object -First 1 ProcessId",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=8,
                    creationflags=0x08000000 if sys.platform == "win32" else 0,
                )
                still = bool((r.stdout or "").strip())
            except Exception:
                still = False

            if still:
                def _loading():
                    self.lbl_online.configure(
                        text="实时面板加载中…请看任务栏 RVC - GUI",
                        fg=TM_META,
                    )

                self.root.after(0, _loading)
                return

            msg = (
                "未检测到实时面板窗口（RVC - GUI）。\n"
                f"日志：\n{log}\n{vbs_log}\n\n"
                f"{tail.strip() or '（日志为空）'}\n\n"
                "开发版 bat 正常而 exe 不行时，多半是 Runtime 启动失败；"
                "请确认包内有 Runtime\\pythonw.exe 与 gui_v1.py。"
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
        except Exception:
            pass

    def open_legacy_gui(self) -> None:
        """Open original RVC FreeSimpleGUI panel (optional / debug)."""
        try:
            self.save_settings_silent()
            if self.models:
                self._sync_model_to_realtime_gui(self.models[self.model_idx])
            os.environ.pop("TM_AUTO_START_VC", None)
            name = ""
            if self.models:
                name = self.models[self.model_idx].get("name") or ""
            self.lbl_online.configure(
                text="正在启动原版实时面板（约 20–40 秒）…",
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
                self.lbl_online.configure(
                    text=f"原版面板启动中：{name}",
                    fg=TM_OK,
                )
        except Exception as e:
            messagebox.showerror("失败", str(e))

    def toggle_vc(self) -> None:
        if not self.models:
            messagebox.showwarning("没有模型", "请先导入音色。")
            self.show_page("models")
            return
        if self.vc_running or self._vc_starting:
            self._stop_vc()
            return
        self._start_vc()

    def _start_vc(self) -> None:
        m = self.models[self.model_idx]
        self.save_settings_silent()
        self._sync_model_to_realtime_gui(m)
        self._vc_starting = True
        self.vc_running = False
        self.btn_start.configure(text="启动中…", bg=TM_OK)
        self.lbl_online.configure(
            text=f"启动中：{m['name']}（首次约 20–40 秒，无第二窗口）",
            fg=TM_OK,
        )

        def work():
            err = ""
            try:
                # Single worker only; stop any previous stream before start
                if not rt_client.is_worker_alive():
                    rt_client.start_worker_process()
                rt_client.wait_worker_ready(timeout_s=100)
                try:
                    rt_client.stop_vc_remote(force=False, timeout_s=5.0)
                except Exception:
                    pass
                time.sleep(0.3)
                rt_client.start_vc_remote()
                deadline = time.time() + 180
                while time.time() < deadline:
                    st = rt_client.poll_status()
                    state = str(st.get("state") or "")
                    if state == "running":
                        self.root.after(0, lambda s=st: self._on_vc_started(m, s))
                        return
                    if state == "error":
                        err = str(st.get("error") or "start failed")
                        break
                    time.sleep(0.35)
                if not err:
                    err = "启动超时，请查看 User_Data/logs"
            except Exception as e:
                err = str(e)
            self.root.after(0, lambda: self._on_vc_start_failed(err))

        threading.Thread(target=work, daemon=True).start()

    def _on_vc_started(self, m: dict, st: dict) -> None:
        self._vc_starting = False
        self.vc_running = True
        self.btn_start.configure(text="停止变声", bg=TM_OK)
        delay = int(st.get("delay_ms") or 0)
        self.lbl_online.configure(
            text=f"变声中：{m.get('name') or ''}",
            fg=TM_OK,
        )
        if delay:
            self.lbl_latency.configure(text=f"算法延迟约 {delay} ms")

    def _on_vc_start_failed(self, err: str) -> None:
        self._vc_starting = False
        self.vc_running = False
        self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
        self.lbl_online.configure(text="启动失败", fg=TM_META)
        messagebox.showerror(
            "启动失败",
            (err or "未知错误")
            + "\n\n可尝试：设置里检查输入/输出设备，或「打开原版实时面板」。",
        )

    def _stop_vc(self) -> None:
        self.btn_start.configure(text="停止中…", bg=TM_META)
        self.lbl_online.configure(text="正在停止并释放声卡…", fg=TM_META)

        def work():
            try:
                # Soft stop then force-kill process tree if stream still running
                rt_client.stop_vc_remote(force=True, timeout_s=12.0)
            except Exception:
                try:
                    rt_client.kill_all_project_workers()
                except Exception:
                    pass
            self.root.after(0, self._on_vc_stopped)

        threading.Thread(target=work, daemon=True).start()

    def _on_vc_stopped(self) -> None:
        self.vc_running = False
        self._vc_starting = False
        self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
        self.lbl_online.configure(text="引擎待命", fg=TM_META)
        self.lbl_latency.configure(text=APP_PRODUCT_TAGLINE)

    def _tick_status(self) -> None:
        try:
            st = rt_client.poll_status()
            state = str(st.get("state") or "")
            if self.vc_running or self._vc_starting:
                if state == "running":
                    self.vc_running = True
                    self._vc_starting = False
                    delay = int(st.get("delay_ms") or 0)
                    infer = int(st.get("infer_ms") or 0)
                    self.btn_start.configure(text="停止变声", bg=TM_OK)
                    parts = []
                    if delay:
                        parts.append(f"延迟 {delay}ms")
                    if infer:
                        parts.append(f"推理 {infer}ms")
                    if parts:
                        self.lbl_latency.configure(text=" · ".join(parts))
                elif state == "error":
                    err = str(st.get("error") or "error")
                    self.vc_running = False
                    self._vc_starting = False
                    self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
                    self.lbl_online.configure(text=f"错误: {err[:48]}", fg=TM_META)
                elif state == "idle" and self.vc_running and not self._vc_starting:
                    # Worker stopped externally
                    self._on_vc_stopped()
        except Exception:
            pass
        self.root.after(1000, self._tick_status)

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self) -> None:
        try:
            self.save_settings_silent()
            save_config(self.cfg)
        except Exception:
            pass
        try:
            # Must release audio devices; force-kill leftover workers
            rt_client.stop_vc_remote(force=True, timeout_s=8.0)
            rt_client.quit_worker(force=True)
        except Exception:
            try:
                rt_client.kill_all_project_workers()
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
