# -*- coding: utf-8 -*-
"""Consumer app (RVCMAX role: daily GUI).

Shell layout inspired by content-library chrome + stage focus.
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
    get_model_voice_params,
    import_model_to_catalog,
    save_model_voice_params,
)
from launcher.config_store import load_config, save_config, sync_realtime_gui_model
from launcher.hotkeys import (
    ACTION_BY_ID,
    DEFAULT_GLOBAL_ACTIONS,
    DEFAULT_HOTKEYS,
    GlobalHotkeyManager,
    event_to_hotkey_spec,
    find_duplicate_bindings,
    focus_should_skip_hotkey,
    format_help_text,
    merge_global_actions,
    merge_hotkeys,
    normalize_hotkey,
    to_tk_sequence,
)
from launcher.paths import (
    APP_TITLE,
    MODELS_DIR,
    USER_DATA,
    ensure_dirs,
    index_search_roots,
    list_voice_models,
)
from launcher import realtime_client as rt_client
from launcher.gpu_backend import apply_backend_env, detect_full, normalize_accel
from launcher.theme import (
    APP_PRODUCT_TAGLINE,
    APP_ROUTE,
    APP_WORDMARK,
    BOTTOM_HEIGHT,
    GUTTER,
    NAV_HEIGHT,
    DEFAULT_WIN_H,
    DEFAULT_WIN_W,
    MIN_WIN_H,
    MIN_WIN_W,
    PAD_X,
    TM_ACCENT,
    TM_ACCENT_INK,
    TM_ACCENT_SOFT,
    TM_BG,
    TM_HAIRLINE,
    TM_HELP,
    TM_INK,
    TM_INK_MUTED,
    TM_INSET,
    TM_META,
    TM_OK,
    TM_STAGE,
    TM_SURFACE,
    TM_SURFACE_HOVER,
    TM_WARN,
    display_font,
    mono_font,
    sans_font,
    serif_font,
    title_font,
    tracked,
)
from launcher.ui import (
    CoverCache,
    GhostButton,
    HoverTip,
    ModelCoverCard,
    NavItem,
    PageHeader,
    ParamTile,
    PrimaryButton,
    SectionCard,
    SoftSlider,
    StatusBadge,
)
from launcher.ui.help_content import SETTING_TIPS, help_plain_text
from launcher.ui.help_page import HelpPage
from launcher.ui.store_page import StorePage
from launcher.version import APP_VERSION
from launcher.win_util import (
    focus_window_by_title,
    open_path,
    read_tail,
    realtime_gui_log_path,
    start_legacy_realtime_gui,
    start_webui,
)


# ---------------------------------------------------------------------------
# 运营占位：新手引导最后一步「加入 QQ 群」的入口链接。
# TODO(运营): 上线前把下面的 URL 换成你的【B 站视频链接】。
#   视频文案引导：一键三连 + 关注 UP 主后，私信「加群」即可获取 QQ 群号。
# 只需改这一处；引导页与「其他」页的重看入口都会用它。
# ---------------------------------------------------------------------------
COMMUNITY_LINK_URL = "https://www.bilibili.com/"  # ← 改成 B 站视频链接


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
        self._cover_cache = CoverCache()
        self._device_lists = {
            "hostapis": [],
            "input_devices": [],
            "output_devices": [],
        }
        self._hotkey_map: dict[str, str] = merge_hotkeys(self.cfg.get("hotkeys"))
        self._tk_hotkey_binds: list[str] = []
        self._global_hk = GlobalHotkeyManager()
        self._model_restart_job = None
        self._capture_action_id: Optional[str] = None
        self._loading_voice = False  # skip persist while applying per-model params
        self._voice_save_job = None
        self._voice_undo: list[dict] = []
        self._voice_redo: list[dict] = []
        self._voice_hist_limit = 40
        self._dock_hint_job = None

        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry(f"{DEFAULT_WIN_W}x{DEFAULT_WIN_H}")
        self.root.minsize(MIN_WIN_W, MIN_WIN_H)
        self.root.configure(bg=TM_BG)
        self._place_and_raise(force_size=True)

        # Shared hot-control vars (bottom dock + settings page)
        self._init_shared_voice_vars()
        self._build_chrome()
        self._build_pages()
        # Apply selected model's saved voice params after UI exists
        if self.models:
            self._apply_model_voice_params(
                self.models[self.model_idx], push_remote=False
            )
        self.root.bind("<Configure>", self._on_root_configure)
        self.show_page("home")
        self._tick_status()
        self._setup_hotkeys()
        self.root.after(200, lambda: self._place_and_raise(force_size=False))
        self.root.after(800, lambda: self._place_and_raise(force_size=False))
        self.root.after(400, self._init_gpu_backend)
        self.root.after(600, self._bootstrap_devices_async)
        self.root.after(350, self._poll_global_hotkeys)
        self.root.after(2500, self._silent_check_updates)
        self.root.after(1200, self._maybe_show_onboarding)
        self._gpu_info: dict = {}
        self._update_badge_on = False

    def _init_shared_voice_vars(self) -> None:
        """Hot-control Tk vars shared by bottom dock and settings page."""
        self.var_pitch = tk.IntVar(value=int(self.cfg.get("pitch") or 0))
        self.var_formant = tk.DoubleVar(value=float(self.cfg.get("formant") or 0))
        self.var_threhold = tk.IntVar(
            value=int(
                self.cfg.get("threhold")
                if self.cfg.get("threhold") is not None
                else -60
            )
        )
        self.var_index_rate = tk.DoubleVar(value=float(self.cfg.get("index_rate") or 0))
        self.var_rms = tk.DoubleVar(value=float(self.cfg.get("rms_mix_rate") or 0))
        self.var_f0 = tk.StringVar(value=str(self.cfg.get("f0method") or "fcpe"))
        self.var_function = tk.StringVar(value=str(self.cfg.get("function") or "vc"))

    def _place_and_raise(self, force_size: bool = False) -> None:
        """Show window on primary screen. Only set default size once (allow user resize)."""
        try:
            self.root.update_idletasks()
            if force_size or not self._placed_once:
                w, h = DEFAULT_WIN_W, DEFAULT_WIN_H
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
                # Leave margin on small laptops
                w = min(w, max(MIN_WIN_W, sw - 48))
                h = min(h, max(MIN_WIN_H, sh - 72))
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
        elif self._current_page == "settings":
            self._reflow_settings_page()
        elif self._current_page == "store":
            try:
                self._store_page.reflow()
            except Exception:
                pass

    def _build_chrome(self) -> None:
        # LyricsKara-style head: tracked wordmark + mono route | Schale segment nav
        top = tk.Frame(self.root, bg=TM_SURFACE, height=NAV_HEIGHT)
        top.pack(fill="x")
        top.pack_propagate(False)

        brand = tk.Frame(top, bg=TM_SURFACE)
        brand.pack(side="left", padx=PAD_X, pady=10)
        tk.Label(
            brand,
            text=tracked(APP_WORDMARK, gap="  "),
            font=display_font(13),
            bg=TM_SURFACE,
            fg=TM_INK,
        ).pack(anchor="w")
        tk.Label(
            brand,
            text="变声器  ·  " + tracked(APP_ROUTE, gap=""),
            font=mono_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
        ).pack(anchor="w", pady=(2, 0))

        # Segment control rail
        nav_rail = tk.Frame(top, bg=TM_INSET, padx=4, pady=4)
        nav_rail.pack(side="right", padx=PAD_X, pady=12)
        self.nav_btns: dict[str, NavItem] = {}
        for key, label in (
            ("home", "首页"),
            ("models", "模型"),
            ("settings", "设置"),
            ("store", "更新"),
            ("help", "说明"),
            ("more", "其他"),
        ):
            b = NavItem(nav_rail, label, key, self.show_page)
            b.pack(side="left", padx=2)
            self.nav_btns[key] = b

        tk.Frame(self.root, bg=TM_HAIRLINE, height=1).pack(fill="x")

        self.body = tk.Frame(self.root, bg=TM_BG)
        self.body.pack(fill="both", expand=True)

        tk.Frame(self.root, bg=TM_HAIRLINE, height=1).pack(fill="x", side="bottom")
        bottom = tk.Frame(self.root, bg=TM_SURFACE, height=BOTTOM_HEIGHT)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)
        self._bottom_bar = bottom

        # Bottom dock zones (Schale card grouping + LyricsKara now-playing meta)
        # [ NOW PLAYING ] [ MODE ] [ PITCH | FORMANT | THRESH ] …… [ CTA | status ]

        dock_pad_y = 12  # vertical air inside fixed-height dock (must fit BOTTOM_HEIGHT)

        # --- Left: now-playing panel (3 lines max so nothing clips) ---
        left_panel = tk.Frame(
            bottom,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        left_panel.pack(side="left", padx=(PAD_X, 10), pady=dock_pad_y, fill="y")
        left_info = tk.Frame(left_panel, bg=TM_SURFACE, padx=14, pady=12)
        left_info.pack(fill="both", expand=True)
        tk.Label(
            left_info,
            text=tracked("NOW PLAYING", gap="  "),
            font=mono_font(7),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        ).pack(anchor="w")
        self.bottom_name = tk.Label(
            left_info,
            text="未选择模型",
            font=title_font(13, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        )
        self.bottom_name.pack(anchor="w", pady=(6, 0))
        # tag + voice hint share one line (was 2 lines → got clipped)
        self.bottom_tag = tk.Label(
            left_info,
            text="请先导入音色到 User_Data/models",
            font=mono_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        )
        self.bottom_tag.pack(anchor="w", pady=(4, 0))
        self.bottom_voice_hint = tk.Label(
            left_info,
            text="参数随音色单独保存",
            font=mono_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
            width=34,  # fixed cols — value changes must not reflow dock
        )
        self.bottom_voice_hint.pack(anchor="w", pady=(2, 0))

        # --- Right: transport + status (compact) ---
        right = tk.Frame(bottom, bg=TM_SURFACE)
        right.pack(side="right", padx=(10, PAD_X), pady=dock_pad_y, fill="y")
        right_col = tk.Frame(right, bg=TM_SURFACE)
        right_col.pack(expand=True)
        ctrl = tk.Frame(right_col, bg=TM_SURFACE)
        ctrl.pack(anchor="e")
        self.btn_start = PrimaryButton(
            ctrl, "开启变声", command=self.toggle_vc, padx=18, pady=8
        )
        self.btn_start.pack(side="left", padx=(0, 8))
        GhostButton(ctrl, "高级面板", command=self.open_legacy_gui, padx=12, pady=7).pack(
            side="left"
        )
        self.status_badge = StatusBadge(right_col)
        self.status_badge.pack(anchor="e", pady=(8, 0))
        self.lbl_online = self.status_badge.title_lbl
        self.lbl_latency = self.status_badge.sub_lbl

        # --- Center: mode + param tiles ---
        mid = tk.Frame(bottom, bg=TM_SURFACE)
        mid.pack(side="left", fill="both", expand=True, padx=4, pady=dock_pad_y)

        mode_card = tk.Frame(
            mid,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        mode_card.pack(side="left", fill="y", padx=(0, 10))
        mode_inner = tk.Frame(mode_card, bg=TM_SURFACE, padx=12, pady=12)
        mode_inner.pack(fill="both", expand=True)
        tk.Label(
            mode_inner,
            text=tracked("MODE", gap="  "),
            font=mono_font(7),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        ).pack(anchor="w")
        seg = tk.Frame(mode_inner, bg=TM_INSET, padx=4, pady=4)
        seg.pack(anchor="w", pady=(12, 0))
        self.btn_mode_vc = tk.Button(
            seg,
            text="输出变声",
            font=sans_font(10),
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
            cursor="hand2",
            command=lambda: self._set_function_mode("vc"),
        )
        self.btn_mode_vc.pack(side="left", padx=2)
        self.btn_mode_im = tk.Button(
            seg,
            text="原声旁路",
            font=sans_font(10),
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
            cursor="hand2",
            command=lambda: self._set_function_mode("im"),
        )
        self.btn_mode_im.pack(side="left", padx=2)
        HoverTip(
            self.btn_mode_vc,
            "输出变声：麦克风 → 变成所选音色再输出（日常开黑）。",
        )
        HoverTip(
            self.btn_mode_im,
            "原声旁路（设置里的「输入监听」）：不改变声音，只输出麦克风原声，用来测麦/接线。",
        )

        tiles = tk.Frame(mid, bg=TM_SURFACE)
        tiles.pack(side="left", fill="both", expand=True)
        self._dock_pitch = ParamTile(
            tiles,
            "音高 Pitch",
            self.var_pitch,
            -24,
            24,
            resolution=1,
            command=self._on_dock_param,
            on_press=self._voice_hist_push,
            width=188,
            fmt="int",
        )
        self._dock_pitch.pack(side="left", fill="y", padx=(0, 8))
        self._dock_formant = ParamTile(
            tiles,
            "共鸣 Formant",
            self.var_formant,
            -2,
            2,
            resolution=0.05,
            command=self._on_dock_param,
            on_press=self._voice_hist_push,
            width=188,
            fmt="signed",
        )
        self._dock_formant.pack(side="left", fill="y", padx=(0, 8))
        self._dock_thr = ParamTile(
            tiles,
            "阈值",
            self.var_threhold,
            -60,
            0,
            resolution=1,
            command=self._on_dock_param,
            on_press=self._voice_hist_push,
            width=168,
            fmt="int",
        )
        self._dock_thr.pack(side="left", fill="y", padx=(0, 8))

        # Undo / reset for voice params (dock)
        hist = tk.Frame(
            tiles,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        hist.pack(side="left", fill="y")
        hist_in = tk.Frame(hist, bg=TM_SURFACE, padx=10, pady=10)
        hist_in.pack(fill="both", expand=True)
        tk.Label(
            hist_in,
            text=tracked("EDIT", gap="  "),
            font=mono_font(7),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        ).pack(anchor="w")
        GhostButton(
            hist_in, "撤销", command=self.undo_voice_params, padx=10, pady=4
        ).pack(fill="x", pady=(8, 4))
        GhostButton(
            hist_in, "重做", command=self.redo_voice_params, padx=10, pady=4
        ).pack(fill="x", pady=2)
        GhostButton(
            hist_in, "默认", command=self.reset_voice_params_default, padx=10, pady=4
        ).pack(fill="x", pady=(4, 0))
        HoverTip(hist_in, "Ctrl+Z 撤销 · Ctrl+Y 重做 · Ctrl+0 恢复默认音高/共鸣/阈值")

        self._update_mode_buttons()
        self._sync_bottom()

    def _format_latency_line(self, delay_ms: int, infer_ms: int) -> str:
        """Human-readable metrics; hide absurd delayed-sentinel values."""
        parts: list[str] = []
        if 0 < delay_ms < 8000:
            parts.append(f"延迟 {delay_ms} ms")
        elif delay_ms >= 8000:
            parts.append("延迟 测量中…")
        if 0 < infer_ms < 8000:
            parts.append(f"推理 {infer_ms} ms")
        return " · ".join(parts) if parts else APP_PRODUCT_TAGLINE

    def _set_status_visual(self, mode: str, title: str, subtitle: str = "") -> None:
        """Update bottom-right status badge. mode: idle|busy|live|error."""
        try:
            self.status_badge.set_mode(
                mode, title, subtitle or APP_PRODUCT_TAGLINE
            )
        except Exception:
            pass

    def _build_pages(self) -> None:
        self._store_page = StorePage(self, self.body)
        self._help_page = HelpPage(self, self.body)
        self.pages = {
            "home": self._page_home(),
            "models": self._page_models(),
            "settings": self._page_settings(),
            "store": self._store_page.frame,
            "help": self._help_page.frame,
            "more": self._page_more(),
        }

    def show_page(self, key: str) -> None:
        self._current_page = key
        for fr in self.pages.values():
            fr.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        for k, b in self.nav_btns.items():
            b.set_active(k == key)
        if key == "models":
            self.refresh_models()
        if key == "home":
            self._render_carousel()
            self._update_home_current_label()
        if key == "settings":
            self.root.after(50, self._reflow_settings_page)
        if key == "store":
            try:
                self._store_page.on_show()
            except Exception:
                pass
        if key == "help":
            try:
                self._help_page.on_show()
            except Exception:
                pass

    def _page_home(self) -> tk.Frame:
        fr = tk.Frame(self.body, bg=TM_BG)
        fr.columnconfigure(0, weight=1)
        fr.rowconfigure(1, weight=1)

        # Full-width stage band (LyricsKara “band” hierarchy)
        stage = tk.Frame(fr, bg=TM_STAGE)
        stage.grid(row=0, column=0, sticky="ew")
        stage_inner = tk.Frame(stage, bg=TM_STAGE)
        stage_inner.pack(fill="x", padx=GUTTER, pady=(22, 18))
        stage_inner.columnconfigure(0, weight=1)

        head_row = tk.Frame(stage_inner, bg=TM_STAGE)
        head_row.grid(row=0, column=0, sticky="ew")
        tk.Label(
            head_row,
            text=tracked("HOME  ·  STAGE", gap="  "),
            font=mono_font(8),
            bg=TM_STAGE,
            fg=TM_META,
            anchor="w",
        ).pack(side="left")
        self.home_index_lbl = tk.Label(
            head_row,
            text="— / —",
            font=mono_font(9),
            bg=TM_STAGE,
            fg=TM_META,
            anchor="e",
        )
        self.home_index_lbl.pack(side="right")

        tk.Label(
            stage_inner,
            text="选择音色，开始变声",
            font=title_font(24, "bold"),
            bg=TM_STAGE,
            fg=TM_INK,
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(10, 6))

        self.home_current_lbl = tk.Label(
            stage_inner,
            text="当前音色：—",
            font=title_font(15, "bold"),
            bg=TM_STAGE,
            fg=TM_ACCENT,
            anchor="w",
        )
        self.home_current_lbl.grid(row=2, column=0, sticky="w", pady=(4, 2))
        self.home_hint_lbl = tk.Label(
            stage_inner,
            text="← → 切换音色 · F5 启停变声 · F1 快捷键",
            font=sans_font(10),
            bg=TM_STAGE,
            fg=TM_INK_MUTED,
            anchor="w",
        )
        self.home_hint_lbl.grid(row=3, column=0, sticky="w", pady=(2, 0))
        tk.Frame(fr, bg=TM_HAIRLINE, height=1).grid(row=0, column=0, sticky="sew")

        # Carousel stage
        mid = tk.Frame(fr, bg=TM_BG)
        mid.grid(row=1, column=0, sticky="nsew", padx=GUTTER, pady=(8, 0))
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(0, weight=1)
        self.carousel_host = tk.Frame(mid, bg=TM_BG)
        self.carousel_host.grid(row=0, column=0, sticky="nsew")
        self.carousel_host.bind("<Configure>", lambda e: self._schedule_carousel_reflow())

        nav = tk.Frame(fr, bg=TM_BG)
        nav.grid(row=2, column=0, sticky="ew", pady=(8, 6))
        nav_inner = tk.Frame(nav, bg=TM_BG)
        nav_inner.pack()
        GhostButton(
            nav_inner,
            "‹  PREV",
            command=lambda: self._shift_model(-1),
            font=mono_font(9),
            padx=20,
            pady=10,
        ).pack(side="left", padx=8)
        GhostButton(
            nav_inner,
            "NEXT  ›",
            command=lambda: self._shift_model(1),
            font=mono_font(9),
            padx=20,
            pady=10,
        ).pack(side="left", padx=8)

        self.home_toast = tk.Label(
            fr,
            text="",
            font=mono_font(9),
            bg=TM_BG,
            fg=TM_OK,
        )
        self.home_toast.grid(row=3, column=0, sticky="ew", pady=(0, 10))
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
            box = SectionCard(self.carousel_host, accent_rail=False, pad=20)
            box.pack(expand=True, fill="both", padx=40, pady=20)
            tk.Label(
                box.body,
                text="暂无音色\n\n请到「模型」页导入 .pth",
                font=sans_font(11),
                bg=TM_SURFACE,
                fg=TM_INK_MUTED,
                justify="center",
            ).pack(expand=True, pady=40)
            return

        self.carousel_host.update_idletasks()
        host_w = max(self.carousel_host.winfo_width(), 400)
        host_h = max(self.carousel_host.winfo_height(), 240)
        # Focus card dominates (stage hierarchy)
        focus_w = max(200, min(320, int(host_w * 0.34)))
        focus_h = max(240, min(360, int(host_h * 0.88)))
        side_w = max(130, int(focus_w * 0.62))
        side_h = max(180, int(focus_h * 0.72))

        n = len(self.models)
        idxs = [(self.model_idx - 1) % n, self.model_idx % n, (self.model_idx + 1) % n]
        row = tk.Frame(self.carousel_host, bg=TM_BG)
        row.place(relx=0.5, rely=0.5, anchor="center")

        for i, mi in enumerate(idxs):
            m = self.models[mi]
            focus = i == 1
            w, h = (focus_w, focus_h) if focus else (side_w, side_h)
            photo = self._cover_cache.get(
                m.get("cover"),
                max_w=max(w - 4, 100),
                max_h=max(int(h * 0.58), 80),
            )
            card = ModelCoverCard(
                row,
                name=m["name"],
                tag=m.get("tag") or "音色",
                photo=photo,
                active=focus,
                focus=focus,
                index_text=f"{self.model_idx + 1:02d} / {n:02d}" if focus else "",
                width=w,
                height=h,
                on_click=lambda ix=mi: self._select_model(
                    ix, feedback=True, maybe_restart=True
                ),
            )
            card.pack(side="left", padx=max(10, int(host_w * 0.016)), pady=12)

    def _update_home_current_label(self) -> None:
        if not hasattr(self, "home_current_lbl"):
            return
        if not self.models:
            self.home_current_lbl.configure(text="尚未选择音色")
            self.home_hint_lbl.configure(text="请先到「模型」页导入音色")
            if hasattr(self, "home_index_lbl"):
                self.home_index_lbl.configure(text="— / —")
            return
        m = self.models[self.model_idx]
        n = len(self.models)
        self.home_current_lbl.configure(text=m["name"])
        self.home_hint_lbl.configure(
            text=f"{m.get('tag') or '音色'}  ·  切换立即生效 · 运行中会自动重载"
        )
        if hasattr(self, "home_index_lbl"):
            self.home_index_lbl.configure(
                text=f"{self.model_idx + 1:02d}  /  {n:02d}"
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
        self._select_model(
            (self.model_idx + delta) % len(self.models),
            feedback=True,
            maybe_restart=True,
        )

    def _select_model(
        self,
        idx: int,
        feedback: bool = False,
        maybe_restart: bool = False,
    ) -> None:
        if not self.models:
            return
        idx = idx % len(self.models)
        prev = self.model_idx
        # Save previous model's voice params before switching
        if prev != idx and self.models:
            try:
                self._persist_voice_params_to_model(
                    self.models[prev], immediate=True
                )
            except Exception:
                pass
        self.model_idx = idx
        m = self.models[self.model_idx]
        # Persist so realtime / next launch use the same model
        self.cfg["last_model"] = m["file"]
        self.cfg["last_model_name"] = m["name"]
        self.cfg["last_model_path"] = m.get("path") or ""
        # Load this voice's pitch/formant/… then sync engine config
        self._apply_model_voice_params(m, push_remote=False)
        self._voice_undo.clear()
        self._voice_redo.clear()
        save_config(self.cfg)
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
        # Cold param: model load only at start — restart stream if already live
        if (
            maybe_restart
            and prev != idx
            and (self.vc_running or self._vc_starting)
            and bool(self.cfg.get("hotkey_restart_on_model_switch", True))
        ):
            self._restart_vc_for_new_model()
        elif prev != idx and self.vc_running:
            # Same stream, different voice params only — hot push (model weight needs restart)
            self._push_hot_params()

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
            if hasattr(self, "bottom_voice_hint"):
                try:
                    p = int(self.var_pitch.get())
                    f = float(self.var_formant.get())
                    mode = "变声" if str(self.var_function.get()) == "vc" else "原声"
                    # Keep one short line — dock height is fixed
                    self.bottom_voice_hint.configure(
                        text=f"专属参数  音高 {p:+d}  共鸣 {f:.2f}  ·  {mode}"
                    )
                except Exception:
                    self.bottom_voice_hint.configure(text="参数随音色单独保存")
        else:
            self.bottom_name.configure(text="未选择模型")
            self.bottom_tag.configure(text="请到「模型」页导入音色")
            if hasattr(self, "bottom_voice_hint"):
                self.bottom_voice_hint.configure(text="参数随音色单独保存")
        try:
            self._update_mode_buttons()
        except Exception:
            pass

    def _update_mode_buttons(self) -> None:
        """Style bottom segment control for vc / im."""
        if not hasattr(self, "btn_mode_vc"):
            return
        mode = "vc"
        try:
            mode = str(self.var_function.get() or "vc")
        except Exception:
            mode = str(self.cfg.get("function") or "vc")
        active = mode == "vc"
        try:
            self.btn_mode_vc.configure(
                bg=TM_ACCENT if active else TM_INSET,
                fg=TM_ACCENT_INK if active else TM_INK,
                activebackground=TM_ACCENT if active else TM_SURFACE_HOVER,
                activeforeground=TM_ACCENT_INK if active else TM_INK,
            )
            self.btn_mode_im.configure(
                bg=TM_INSET if active else TM_ACCENT,
                fg=TM_INK if active else TM_ACCENT_INK,
                activebackground=TM_SURFACE_HOVER if active else TM_ACCENT,
                activeforeground=TM_INK if active else TM_ACCENT_INK,
            )
        except Exception:
            pass

    def _set_function_mode(self, mode: str) -> None:
        """Switch 输出变声 (vc) / 原声旁路 (im). Session-level, hot-updatable."""
        mode = "im" if str(mode) == "im" else "vc"
        try:
            self.var_function.set(mode)
        except Exception:
            pass
        self.cfg["function"] = mode
        self._update_mode_buttons()
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self._sync_bottom()
        if self.vc_running:
            self._on_hot_param()
        else:
            try:
                self._collect_settings_into_cfg()
                if self.models:
                    self._sync_model_to_realtime_gui(self.models[self.model_idx])
            except Exception:
                pass
        self._set_status_visual(
            "live" if self.vc_running else "idle",
            "模式：输出变声" if mode == "vc" else "模式：原声旁路",
            "运行中已热切换" if self.vc_running else "下次开启变声生效",
        )

    def _collect_voice_params_dict(self) -> dict:
        """Current UI voice params for per-model save."""
        d: dict = {}
        try:
            d["pitch"] = int(self.var_pitch.get())
            d["formant"] = float(self.var_formant.get())
            d["threhold"] = int(self.var_threhold.get())
            d["index_rate"] = float(self.var_index_rate.get())
            d["rms_mix_rate"] = float(self.var_rms.get())
            d["f0method"] = str(self.var_f0.get() or "fcpe")
        except Exception:
            d["pitch"] = int(self.cfg.get("pitch") or 0)
            d["formant"] = float(self.cfg.get("formant") or 0)
            d["threhold"] = int(
                self.cfg.get("threhold")
                if self.cfg.get("threhold") is not None
                else -60
            )
            d["index_rate"] = float(self.cfg.get("index_rate") or 0)
            d["rms_mix_rate"] = float(self.cfg.get("rms_mix_rate") or 0)
            d["f0method"] = str(self.cfg.get("f0method") or "fcpe")
        return d

    def _apply_model_voice_params(
        self, m: dict, *, push_remote: bool = False
    ) -> None:
        """Load per-model pitch/formant/… into UI + cfg (fallback: global app cfg)."""
        if not m:
            return
        self._loading_voice = True
        try:
            # Prefer live sidecar on disk, then catalog fields, then app defaults
            disk: dict = {}
            if m.get("source") == "user_data" and m.get("dir"):
                try:
                    disk = get_model_voice_params(Path(m["dir"]))
                except Exception:
                    disk = {}
            def pick(key, cast, default):
                if key in disk and disk[key] is not None:
                    return cast(disk[key])
                if m.get(key) is not None:
                    return cast(m.get(key))
                v = self.cfg.get(key)
                if v is None or v == "":
                    return cast(default)
                return cast(v)

            pitch = pick("pitch", lambda x: int(round(float(x))), 0)
            formant = pick("formant", float, 0.0)
            thr = pick("threhold", lambda x: int(round(float(x))), -60)
            ir = pick("index_rate", float, 0.0)
            rms = pick("rms_mix_rate", float, 0.0)
            f0 = pick("f0method", str, "fcpe")

            self.var_pitch.set(pitch)
            self.var_formant.set(formant)
            self.var_threhold.set(thr)
            self.var_index_rate.set(ir)
            self.var_rms.set(rms)
            self.var_f0.set(f0)

            self.cfg["pitch"] = pitch
            self.cfg["formant"] = formant
            self.cfg["threhold"] = thr
            self.cfg["index_rate"] = ir
            self.cfg["rms_mix_rate"] = rms
            self.cfg["f0method"] = f0

            # Keep in-memory model dict in sync
            m["pitch"] = pitch
            m["formant"] = formant
            m["threhold"] = thr
            m["index_rate"] = ir
            m["rms_mix_rate"] = rms
            m["f0method"] = f0
        finally:
            self._loading_voice = False
        try:
            self._sync_bottom()
        except Exception:
            pass
        if push_remote and self.vc_running:
            self._push_hot_params()

    def _persist_voice_params_to_model(
        self, m: Optional[dict] = None, *, immediate: bool = False
    ) -> None:
        """Write current voice params into this model's config.json (user_data only)."""
        if self._loading_voice:
            return
        if m is None:
            if not self.models:
                return
            m = self.models[self.model_idx]
        if m.get("source") != "user_data" or not m.get("dir"):
            return
        params = self._collect_voice_params_dict()

        def _write():
            self._voice_save_job = None
            try:
                side = save_model_voice_params(
                    Path(m["dir"]),
                    params,
                    display_name=m.get("name"),
                )
                for k, v in params.items():
                    m[k] = v
                # also refresh tag/name from disk if any
                if side.get("name"):
                    m["name"] = side["name"]
            except Exception:
                pass

        if immediate:
            if self._voice_save_job is not None:
                try:
                    self.root.after_cancel(self._voice_save_job)
                except Exception:
                    pass
                self._voice_save_job = None
            _write()
            return
        if self._voice_save_job is not None:
            try:
                self.root.after_cancel(self._voice_save_job)
            except Exception:
                pass
        self._voice_save_job = self.root.after(280, _write)

    def _voice_snapshot(self) -> dict:
        return self._collect_voice_params_dict()

    def _voice_hist_push(self) -> None:
        """Push current voice params before a user edit (slider press / reset)."""
        if self._loading_voice:
            return
        snap = self._voice_snapshot()
        if self._voice_undo and self._voice_undo[-1] == snap:
            return
        self._voice_undo.append(snap)
        if len(self._voice_undo) > self._voice_hist_limit:
            self._voice_undo.pop(0)
        self._voice_redo.clear()

    def _apply_voice_snapshot(self, snap: dict, *, push_remote: bool = True) -> None:
        if not snap:
            return
        self._loading_voice = True
        try:
            if "pitch" in snap:
                self.var_pitch.set(int(snap["pitch"]))
                self.cfg["pitch"] = int(snap["pitch"])
            if "formant" in snap:
                self.var_formant.set(float(snap["formant"]))
                self.cfg["formant"] = float(snap["formant"])
            if "threhold" in snap:
                self.var_threhold.set(int(snap["threhold"]))
                self.cfg["threhold"] = int(snap["threhold"])
            if "index_rate" in snap and hasattr(self, "var_index_rate"):
                self.var_index_rate.set(float(snap["index_rate"]))
                self.cfg["index_rate"] = float(snap["index_rate"])
            if "rms_mix_rate" in snap and hasattr(self, "var_rms"):
                self.var_rms.set(float(snap["rms_mix_rate"]))
                self.cfg["rms_mix_rate"] = float(snap["rms_mix_rate"])
            if "f0method" in snap and hasattr(self, "var_f0"):
                self.var_f0.set(str(snap["f0method"]))
                self.cfg["f0method"] = str(snap["f0method"])
        finally:
            self._loading_voice = False
        self._persist_voice_params_to_model(immediate=True)
        self._refresh_dock_hint_only()
        if push_remote:
            self._on_hot_param()

    def undo_voice_params(self) -> None:
        if not self._voice_undo:
            self._set_status_visual(
                "live" if self.vc_running else "idle",
                "无可撤销",
                "先调整音高/共鸣/阈值",
            )
            return
        cur = self._voice_snapshot()
        prev = self._voice_undo.pop()
        self._voice_redo.append(cur)
        self._apply_voice_snapshot(prev)
        self._set_status_visual(
            "live" if self.vc_running else "idle",
            "已撤销",
            f"剩余 {len(self._voice_undo)} 步",
        )

    def redo_voice_params(self) -> None:
        if not self._voice_redo:
            self._set_status_visual(
                "live" if self.vc_running else "idle",
                "无可重做",
                "",
            )
            return
        cur = self._voice_snapshot()
        nxt = self._voice_redo.pop()
        self._voice_undo.append(cur)
        self._apply_voice_snapshot(nxt)
        self._set_status_visual(
            "live" if self.vc_running else "idle",
            "已重做",
            f"还可重做 {len(self._voice_redo)} 步",
        )

    def reset_voice_params_default(self) -> None:
        """Restore pitch/formant/threshold defaults for current session + model."""
        self._voice_hist_push()
        defaults = {
            "pitch": 0,
            "formant": 0.0,
            "threhold": -60,
            # keep index/f0/rms as-is (model/index dependent)
        }
        # merge with current so index_rate etc stay
        snap = self._voice_snapshot()
        snap.update(defaults)
        self._apply_voice_snapshot(snap)
        self._set_status_visual(
            "live" if self.vc_running else "idle",
            "已恢复默认",
            "音高 0 · 共鸣 0 · 阈值 -60",
        )

    def _refresh_dock_hint_only(self) -> None:
        """Update dock hint text without full bottom rebuild (no layout thrash)."""
        if not hasattr(self, "bottom_voice_hint"):
            return
        try:
            p = int(self.var_pitch.get())
            f = float(self.var_formant.get())
            mode = "变声" if str(self.var_function.get()) == "vc" else "原声"
            self.bottom_voice_hint.configure(
                text=f"专属参数  音高 {p:+d}  共鸣 {f:.2f}  ·  {mode}"
            )
        except Exception:
            pass

    def _on_dock_param(self) -> None:
        """Bottom dock slider moved — save per-model + hot update (no dock reflow)."""
        if self._loading_voice:
            return
        try:
            self.cfg["pitch"] = int(self.var_pitch.get())
            self.cfg["formant"] = float(self.var_formant.get())
            self.cfg["threhold"] = int(self.var_threhold.get())
        except Exception:
            pass
        self._persist_voice_params_to_model()
        # Debounce hint only — never full _sync_bottom while dragging (causes shake)
        if self._dock_hint_job is not None:
            try:
                self.root.after_cancel(self._dock_hint_job)
            except Exception:
                pass
        self._dock_hint_job = self.root.after(120, self._refresh_dock_hint_only)
        # Hot push without _sync_bottom
        if self._hot_job is not None:
            try:
                self.root.after_cancel(self._hot_job)
            except Exception:
                pass
        self._hot_job = self.root.after(180, self._push_hot_params)

    def _page_models(self) -> tk.Frame:
        fr = tk.Frame(self.body, bg=TM_BG)
        fr.columnconfigure(0, weight=1)
        fr.rowconfigure(1, weight=1)

        bar = tk.Frame(fr, bg=TM_BG)
        bar.grid(row=0, column=0, sticky="ew", padx=GUTTER, pady=(18, 8))
        left = tk.Frame(bar, bg=TM_BG)
        left.pack(side="left", fill="x", expand=True)
        PageHeader(
            left,
            eyebrow="CATALOG",
            title="音色目录",
            lead="",
        ).pack(anchor="w")
        self.models_status_lbl = tk.Label(
            left,
            text="",
            font=mono_font(9),
            bg=TM_BG,
            fg=TM_META,
        )
        self.models_status_lbl.pack(anchor="w", pady=(6, 0))

        actions = tk.Frame(bar, bg=TM_BG)
        actions.pack(side="right", anchor="n", pady=(8, 0))
        GhostButton(
            actions, "打开目录", command=lambda: open_path(MODELS_DIR), padx=12, pady=6
        ).pack(side="right", padx=4)
        GhostButton(actions, "刷新", command=self.refresh_models, padx=12, pady=6).pack(
            side="right", padx=4
        )
        PrimaryButton(actions, "导入模型", command=self.import_model, padx=14, pady=6).pack(
            side="right", padx=4
        )

        list_wrap = tk.Frame(fr, bg=TM_BG)
        list_wrap.grid(row=1, column=0, sticky="nsew", padx=GUTTER - 8, pady=(4, 12))
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

        # Columns adapt to width — cover-first cards need more width
        self._models_canvas.update_idletasks()
        cw = max(self._models_canvas.winfo_width(), 320)
        card_min = 180
        cols = max(1, min(5, cw // (card_min + 20)))
        for c in range(cols):
            self.model_grid.columnconfigure(c, weight=1, uniform="m")

        for i, m in enumerate(self.models):
            r, c = divmod(i, cols)
            active = self._is_active_model(m)
            photo = self._cover_cache.get(
                m.get("cover"), max_w=card_min + 40, max_h=130
            )
            card = ModelCoverCard(
                self.model_grid,
                name=m["name"],
                tag=m.get("tag") or "音色",
                photo=photo,
                active=active,
                focus=active,
                width=max(card_min, 180),
                height=250,
                on_click=lambda ix=i: self._use_model_from_grid(ix),
                action_text="使用中" if active else "使用",
                on_action=None if active else (lambda ix=i: self._use_model_from_grid(ix)),
            )
            card.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")
            self.model_grid.rowconfigure(r, weight=0)

        self._sync_bottom()

    def _use_model_from_grid(self, ix: int) -> None:
        self._select_model(ix, feedback=True, maybe_restart=True)
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

    def _reflow_settings_page(self) -> None:
        """Keep settings cards/sliders matching window width (fix maximize empty right)."""
        canvas = getattr(self, "_settings_canvas", None)
        wrap = getattr(self, "_settings_wrap", None)
        win_id = getattr(self, "_settings_win_id", None)
        if not canvas or not wrap or win_id is None:
            return
        try:
            canvas.update_idletasks()
            w = max(int(canvas.winfo_width()), 400)
            canvas.itemconfigure(win_id, width=w)
            # Help / intro labels wrap to card width
            inner = max(w - 80, 280)
            for lbl in getattr(self, "_settings_wrap_labels", []) or []:
                try:
                    lbl.configure(wraplength=inner)
                except Exception:
                    pass
            canvas.configure(scrollregion=canvas.bbox("all"))
        except Exception:
            pass

    def _page_settings(self) -> tk.Frame:
        fr = tk.Frame(self.body, bg=TM_BG)
        # Scrollable settings — inner window width tracks canvas (fills on maximize)
        canvas = tk.Canvas(fr, bg=TM_BG, highlightthickness=0)
        sb = ttk.Scrollbar(fr, orient="vertical", command=canvas.yview)
        wrap = tk.Frame(canvas, bg=TM_BG)
        win_id = canvas.create_window((0, 0), window=wrap, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._settings_canvas = canvas
        self._settings_wrap = wrap
        self._settings_win_id = win_id
        self._settings_wrap_labels: list = []

        def _sync_scroll(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_width(event) -> None:
            # Critical: make wrap as wide as viewport so cards expand
            if event.width > 1:
                canvas.itemconfigure(win_id, width=event.width)

        wrap.bind("<Configure>", _sync_scroll)
        canvas.bind("<Configure>", _on_canvas_width)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        # Bind wheel on canvas only (not bind_all — avoids stripping app-wide handlers)
        def _bind_wheel_recursive(widget) -> None:
            widget.bind("<MouseWheel>", _on_mousewheel)
            for ch in widget.winfo_children():
                _bind_wheel_recursive(ch)

        canvas.bind("<MouseWheel>", _on_mousewheel)
        wrap.bind("<MouseWheel>", _on_mousewheel)
        wrap.bind("<Map>", lambda _e: _bind_wheel_recursive(wrap), add="+")

        # --- vars (pitch/formant/function etc. already created in _init_shared_voice_vars)
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
        self.var_monitor_dev = tk.StringVar(
            value=str(self.cfg.get("monitor_device") or "")
        )
        self.var_monitor_on = tk.BooleanVar(value=bool(self.cfg.get("monitor_enabled")))
        self.var_wasapi = tk.BooleanVar(value=bool(self.cfg.get("sg_wasapi_exclusive")))
        self.var_sr_type = tk.StringVar(value=str(self.cfg.get("sr_type") or "sr_model"))
        self.var_i_nr = tk.BooleanVar(value=bool(self.cfg.get("I_noise_reduce")))
        self.var_o_nr = tk.BooleanVar(value=bool(self.cfg.get("O_noise_reduce")))
        self.var_use_pv = tk.BooleanVar(value=bool(self.cfg.get("use_pv")))
        self.var_accel = tk.StringVar(
            value=str(self.cfg.get("accel_backend") or "auto")
        )

        def card(parent, title: str) -> tk.Frame:
            # Map Chinese section titles to mono eyebrows (library catalog feel)
            brows = {
                "设备与音频": "DEVICES",
                "变声参数（运行中可热更新）": "VOICE",
                "变声参数（运行中可热更新 · 按音色保存）": "VOICE",
                "性能设置（改后需重新「开启变声」）": "PERFORMANCE",
                "声音效果（变声后 · 可选）": "FX CHAIN",
                "快捷键": "HOTKEYS",
            }
            eyebrow = brows.get(title, "SECTION")
            outer = SectionCard(
                parent, title=title, eyebrow=eyebrow, accent_rail=True, pad=16
            )
            outer.pack(fill="x", expand=False, padx=GUTTER, pady=10)
            return outer.body

        def help_mark(parent, tip: str, *, pack_side: str = "left") -> Optional[tk.Label]:
            """Prominent ? badge; hover shows full tip (no duplicate inline text)."""
            if not tip:
                return None
            q = tk.Label(
                parent,
                text="?",
                font=sans_font(10, "bold"),
                bg=TM_ACCENT_SOFT,
                fg=TM_ACCENT,
                cursor="question_arrow",
                padx=6,
                pady=1,
                highlightthickness=1,
                highlightbackground=TM_ACCENT,
            )
            q.pack(side=pack_side, padx=(6, 0))
            HoverTip(q, tip)
            return q

        def field_label(parent, text: str, **pack_kw) -> tk.Label:
            """Settings row caption — high contrast on surface (Schale-like body)."""
            lbl = tk.Label(
                parent,
                text=text,
                width=14,
                anchor="w",
                bg=TM_SURFACE,
                fg=TM_INK_MUTED,
                font=sans_font(10),
            )
            if pack_kw:
                lbl.pack(**pack_kw)
            return lbl

        def scale_row(
            parent, label, variable, from_, to, res=1, hot=False, tip_key: str = ""
        ):
            """Settings row with SoftSlider; tip only on ? (no duplicate caption)."""
            f = tk.Frame(parent, bg=TM_SURFACE)
            f.pack(fill="x", pady=6)
            field_label(f, label).pack(side="left")
            tip = SETTING_TIPS.get(tip_key, "")
            if tip:
                help_mark(f, tip)
            val_lbl = tk.Label(
                f,
                text="",
                width=7,
                anchor="e",
                bg=TM_SURFACE,
                fg=TM_INK,
                font=mono_font(11),
            )
            val_lbl.pack(side="right", padx=(8, 0))

            def _fmt(_=None, lbl=val_lbl, var=variable, r=res):
                try:
                    v = var.get()
                    if float(r) >= 1:
                        lbl.configure(text=str(int(v)))
                    else:
                        lbl.configure(text=f"{float(v):.2f}")
                except Exception:
                    pass

            def _cmd(_v=None):
                _fmt()
                if hot:
                    self._on_hot_param()

            sc = SoftSlider(
                f,
                variable,
                from_,
                to,
                resolution=res,
                command=_cmd if hot else (lambda _v=None: _fmt()),
                bar_width=360,
                bar_height=36,
                bg=TM_SURFACE,
            )
            sc.pack(side="left", fill="x", expand=True, padx=(4, 4))
            try:
                variable.trace_add("write", lambda *_a: _fmt())
            except Exception:
                pass
            _fmt()
            return sc

        # Device card
        left = card(wrap, "设备与音频")
        intro = tk.Label(
            left,
            text=(
                "输入=真实麦克风 · 输出=CABLE Input · 游戏麦克风=CABLE Output\n"
                "勾选「变声时监听自己」并选耳机，可一边开黑一边听自己的变声效果。"
            ),
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_HELP,
            justify="left",
            anchor="w",
            wraplength=640,
        )
        intro.pack(fill="x", anchor="w", pady=(0, 6))
        self._settings_wrap_labels.append(intro)

        # GPU backend (official: CUDA vs --dml DirectML)
        row = tk.Frame(left, bg=TM_SURFACE)
        row.pack(fill="x", pady=3)
        tk.Label(
            row,
            text="加速后端",
            width=14,
            anchor="w",
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            font=sans_font(10),
        ).pack(side="left")
        self.cmb_accel = ttk.Combobox(
            row,
            textvariable=self.var_accel,
            values=["auto", "cuda", "dml", "cpu"],
            state="readonly",
            width=12,
        )
        self.cmb_accel.pack(side="left")
        self.cmb_accel.bind("<<ComboboxSelected>>", lambda e: self._on_accel_changed())
        help_mark(row, SETTING_TIPS["accel"])
        self.lbl_accel_status = tk.Label(
            left,
            text="加速：检测中…",
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_HELP,
            anchor="w",
        )
        self.lbl_accel_status.pack(fill="x", pady=(0, 4))
        # Package identity (Nvidia / AMD DML / 50-series) — avoid mixing Runtimes
        try:
            from launcher.package_meta import load_package_meta

            _pm = load_package_meta()
            _plabel = str(_pm.get("label") or _pm.get("variant") or "NVIDIA CUDA")
            _psum = str(_pm.get("summary") or "").strip()
        except Exception:
            _plabel, _psum = "未标记发行包", "开发树或旧包：请按显卡使用对应 Runtime"
        self.lbl_pack_meta = tk.Label(
            left,
            text=f"发行包：{_plabel}",
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_HELP,
            anchor="w",
        )
        self.lbl_pack_meta.pack(fill="x", pady=(0, 2))
        if _psum:
            HoverTip(self.lbl_pack_meta, _psum + "\n请勿混用 N 卡 / A 卡 / 50 系 Runtime。")

        row = tk.Frame(left, bg=TM_SURFACE)
        row.pack(fill="x", pady=3)
        tk.Label(
            row, text="设备类型", width=14, anchor="w", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(10)
        ).pack(side="left")
        self.cmb_hostapi = ttk.Combobox(
            row, textvariable=self.var_hostapi, values=["MME"], state="readonly", width=28
        )
        self.cmb_hostapi.pack(side="left", fill="x", expand=True)
        self.cmb_hostapi.bind("<<ComboboxSelected>>", lambda e: self._on_hostapi_change())
        help_mark(row, SETTING_TIPS["hostapi"])

        row = tk.Frame(left, bg=TM_SURFACE)
        row.pack(fill="x", pady=3)
        tk.Label(
            row, text="输入设备", width=14, anchor="w", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(10)
        ).pack(side="left")
        self.cmb_input = ttk.Combobox(
            row, textvariable=self.var_input_dev, values=[], state="readonly", width=48
        )
        self.cmb_input.pack(side="left", fill="x", expand=True)
        help_mark(row, SETTING_TIPS["input"])

        row = tk.Frame(left, bg=TM_SURFACE)
        row.pack(fill="x", pady=3)
        tk.Label(
            row, text="输出设备", width=14, anchor="w", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(10)
        ).pack(side="left")
        self.cmb_output = ttk.Combobox(
            row, textvariable=self.var_output_dev, values=[], state="readonly", width=48
        )
        self.cmb_output.pack(side="left", fill="x", expand=True)
        help_mark(row, SETTING_TIPS["output"])

        # Self-monitor: hear converted voice on headphones while CABLE goes to game
        mon_row = tk.Frame(left, bg=TM_SURFACE)
        mon_row.pack(fill="x", pady=(6, 2))
        tk.Checkbutton(
            mon_row,
            text="变声时监听自己",
            variable=self.var_monitor_on,
            bg=TM_SURFACE,
            fg=TM_INK,
            activebackground=TM_SURFACE,
            font=sans_font(9),
            command=self._on_monitor_toggle,
        ).pack(side="left")
        help_mark(
            mon_row,
            "开启后：游戏/语音仍走「输出设备」（一般是 CABLE Input），\n"
            "同时在「监听设备」再放一份变声后的声音给你听。\n"
            "监听请选真实耳机/音箱（如「耳机 KM-HIFI」），\n"
            "不要选 CABLE、Steam Streaming、虚拟声卡。\n"
            "运行中可开关；若仍无声：停一次变声再开，并确认系统默认播放设备。",
        )
        mon_row2 = tk.Frame(left, bg=TM_SURFACE)
        mon_row2.pack(fill="x", pady=3)
        tk.Label(
            mon_row2,
            text="监听设备",
            width=14,
            anchor="w",
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            font=sans_font(10),
        ).pack(side="left")
        self.cmb_monitor = ttk.Combobox(
            mon_row2,
            textvariable=self.var_monitor_dev,
            values=[],
            state="readonly",
            width=48,
        )
        self.cmb_monitor.pack(side="left", fill="x", expand=True)
        self.cmb_monitor.bind("<<ComboboxSelected>>", lambda e: self._on_monitor_device())
        self.lbl_monitor_hint = tk.Label(
            left,
            text="监听设备须为耳机/音箱；不要选 CABLE 或 Steam 虚拟扬声器",
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_HELP,
            anchor="w",
        )
        self.lbl_monitor_hint.pack(fill="x", pady=(0, 4))

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
            row, text="采样率", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(10)
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

        # Voice params (also on bottom dock; saved per model under User_Data/models)
        right = card(wrap, "变声参数（运行中可热更新 · 按音色保存）")
        voice_note = tk.Label(
            right,
            text=(
                "音高 / 共鸣 / 阈值 / Index / 响度 / 算法会写入当前音色目录的 config.json；"
                "切换音色时自动恢复该音色上次的参数。底栏可快速调节。"
            ),
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_HELP,
            justify="left",
            anchor="w",
            wraplength=640,
        )
        voice_note.pack(fill="x", pady=(0, 6))
        self._settings_wrap_labels.append(voice_note)
        scale_row(
            right, "响应阈值", self.var_threhold, -60, 0, 1, hot=True, tip_key="threhold"
        )
        scale_row(right, "音高 Pitch", self.var_pitch, -24, 24, 1, hot=True, tip_key="pitch")
        scale_row(
            right, "共鸣 Formant", self.var_formant, -2, 2, 0.05, hot=True, tip_key="formant"
        )
        scale_row(
            right, "Index Rate", self.var_index_rate, 0, 1, 0.01, hot=True, tip_key="index_rate"
        )
        scale_row(right, "响度因子", self.var_rms, 0, 1, 0.01, hot=True, tip_key="rms")

        # Feature retrieval .index (bound to current voice model)
        self.var_index_path = tk.StringVar(value="")
        idx_block = tk.Frame(right, bg=TM_SURFACE)
        idx_block.pack(fill="x", pady=(8, 4))
        idx_title = tk.Frame(idx_block, bg=TM_SURFACE)
        idx_title.pack(fill="x", anchor="w")
        tk.Label(
            idx_title,
            text="特征检索 .index",
            font=sans_font(10),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            anchor="w",
        ).pack(side="left")
        help_mark(idx_title, SETTING_TIPS["index"])
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
            font=sans_font(9),
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
            font=sans_font(9),
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
            font=sans_font(9),
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
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_HELP,
            anchor="w",
        )
        self.lbl_index_status.pack(anchor="w", pady=(2, 0))
        self._refresh_index_ui_for_model()

        f0f = tk.Frame(right, bg=TM_SURFACE)
        f0f.pack(fill="x", pady=3)
        tk.Label(
            f0f, text="音高算法", width=14, anchor="w", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(10)
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
        help_mark(f0f, SETTING_TIPS["f0"])

        modef = tk.Frame(right, bg=TM_SURFACE)
        modef.pack(fill="x", pady=4)
        tk.Label(
            modef, text="模式", width=14, anchor="w", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(10)
        ).pack(side="left")
        rb_vc = tk.Radiobutton(
            modef,
            text="输出变声",
            variable=self.var_function,
            value="vc",
            bg=TM_SURFACE,
            command=lambda: self._set_function_mode("vc"),
            font=sans_font(9),
            activebackground=TM_SURFACE,
        )
        rb_vc.pack(side="left")
        rb_im = tk.Radiobutton(
            modef,
            text="输入监听",
            variable=self.var_function,
            value="im",
            bg=TM_SURFACE,
            command=lambda: self._set_function_mode("im"),
            font=sans_font(9),
            activebackground=TM_SURFACE,
        )
        rb_im.pack(side="left", padx=(8, 0))
        _mode_tip = (
            "【输出变声】日常开黑/语音用这个。\n"
            "麦克风 → 变成所选音色 → 从「输出设备」出去（一般选 CABLE Input）。\n"
            "\n"
            "【输入监听】不进行变声，只把麦克风原声送到输出。\n"
            "用来检查麦是否正常、声卡接线对不对；听完记得切回「输出变声」。"
        )
        help_mark(modef, _mode_tip)
        HoverTip(rb_vc, "输出变声：把麦克风变成所选音色再输出（日常变声用这个）。")
        HoverTip(rb_im, "输入监听：不改变声音，只输出麦克风原声（测麦/测接线）。")

        # Performance
        perf = card(wrap, "性能设置（改后需重新「开启变声」）")
        preset_row = tk.Frame(perf, bg=TM_SURFACE)
        preset_row.pack(fill="x", pady=(0, 8))
        tk.Label(
            preset_row,
            text="延迟预设",
            width=14,
            anchor="w",
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            font=sans_font(9),
        ).pack(side="left")
        for label, key in (
            ("低延迟", "low_latency"),
            ("均衡", "balanced"),
            ("稳定", "stable"),
        ):
            GhostButton(
                preset_row,
                label,
                command=lambda k=key: self._apply_perf_preset(k),
                padx=10,
                pady=4,
            ).pack(side="left", padx=3)
        help_mark(
            preset_row,
            "一键设置采样长度/淡入淡出/额外推理时长。"
            "低延迟更跟嘴、对机器要求高；稳定更扛卡顿、延迟更高。改后需重新开启变声。",
        )
        scale_row(perf, "采样长度", self.var_block, 0.02, 1.5, 0.01, tip_key="block")
        scale_row(perf, "淡入淡出", self.var_crossfade, 0.01, 0.15, 0.01, tip_key="crossfade")
        scale_row(perf, "额外推理时长", self.var_extra, 0.05, 5.0, 0.01, tip_key="extra")
        scale_row(perf, "harvest进程数", self.var_n_cpu, 1, 8, 1, tip_key="n_cpu")
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
        help_mark(nrf, SETTING_TIPS["i_nr"])
        tk.Checkbutton(
            nrf,
            text="输出降噪",
            variable=self.var_o_nr,
            bg=TM_SURFACE,
            command=self._on_hot_param,
            font=sans_font(9),
        ).pack(side="left", padx=(8, 0))
        help_mark(nrf, SETTING_TIPS["o_nr"])
        tk.Checkbutton(
            nrf,
            text="相位声码器",
            variable=self.var_use_pv,
            bg=TM_SURFACE,
            command=self._on_hot_param,
            font=sans_font(9),
        ).pack(side="left", padx=(8, 0))
        help_mark(nrf, SETTING_TIPS["use_pv"])

        # ----- Post-RVC DSP (noise gate / compressor / EQ) -----
        from tools.dsp_fx import EQ_LABELS, EQ_PRESET_LABELS, EQ_PRESETS

        self.var_fx_enabled = tk.BooleanVar(value=bool(self.cfg.get("fx_enabled")))
        self.var_fx_gate_en = tk.BooleanVar(value=bool(self.cfg.get("fx_gate_enabled", True)))
        self.var_fx_gate_thr = tk.DoubleVar(
            value=float(self.cfg.get("fx_gate_threshold_db", -50))
        )
        self.var_fx_gate_rel = tk.DoubleVar(
            value=float(self.cfg.get("fx_gate_release_ms", 50))
        )
        self.var_fx_gate_hold = tk.DoubleVar(
            value=float(self.cfg.get("fx_gate_hold_ms", 20))
        )
        self.var_fx_gate_range = tk.DoubleVar(
            value=float(self.cfg.get("fx_gate_range_db", 20))
        )
        self.var_fx_comp_en = tk.BooleanVar(
            value=bool(self.cfg.get("fx_comp_enabled", True))
        )
        self.var_fx_comp_thr = tk.DoubleVar(
            value=float(self.cfg.get("fx_comp_threshold_db", -20))
        )
        self.var_fx_comp_ratio = tk.DoubleVar(
            value=float(self.cfg.get("fx_comp_ratio", 4))
        )
        self.var_fx_comp_att = tk.DoubleVar(
            value=float(self.cfg.get("fx_comp_attack_ms", 5))
        )
        self.var_fx_comp_rel = tk.DoubleVar(
            value=float(self.cfg.get("fx_comp_release_ms", 100))
        )
        self.var_fx_comp_mu = tk.DoubleVar(
            value=float(self.cfg.get("fx_comp_makeup_db", 0))
        )
        self.var_fx_eq_en = tk.BooleanVar(value=bool(self.cfg.get("fx_eq_enabled", True)))
        self.var_fx_eq_preset = tk.StringVar(
            value=str(self.cfg.get("fx_eq_preset") or "flat")
        )
        gains0 = self.cfg.get("fx_eq_gains") or [0, 0, 0, 0, 0]
        if not isinstance(gains0, (list, tuple)):
            gains0 = [0, 0, 0, 0, 0]
        gains0 = list(gains0) + [0] * 5
        self.var_fx_eq_gains = [
            tk.DoubleVar(value=float(gains0[i])) for i in range(5)
        ]
        self.var_fx_out_gain = tk.DoubleVar(
            value=float(self.cfg.get("fx_out_gain_db") or 0)
        )

        fx = card(wrap, "声音效果（变声后 · 可选）")
        fx_en_row = tk.Frame(fx, bg=TM_SURFACE)
        fx_en_row.pack(anchor="w", fill="x")
        tk.Checkbutton(
            fx_en_row,
            text="启用声音效果",
            variable=self.var_fx_enabled,
            bg=TM_SURFACE,
            font=sans_font(9, "bold"),
            command=self._on_hot_param,
        ).pack(side="left")
        help_mark(fx_en_row, SETTING_TIPS["fx_en"])

        # Gate
        gbox = tk.Frame(fx, bg=TM_SURFACE)
        gbox.pack(fill="x", pady=(8, 4))
        gate_row = tk.Frame(gbox, bg=TM_SURFACE)
        gate_row.pack(anchor="w", fill="x")
        tk.Checkbutton(
            gate_row,
            text="噪声门",
            variable=self.var_fx_gate_en,
            bg=TM_SURFACE,
            font=sans_font(9),
            command=self._on_hot_param,
        ).pack(side="left")
        help_mark(gate_row, SETTING_TIPS["fx_gate"])
        scale_row(gbox, "门限 dB", self.var_fx_gate_thr, -80, -10, 1, hot=True, tip_key="fx_gate_thr")
        scale_row(gbox, "释放 ms", self.var_fx_gate_rel, 5, 300, 1, hot=True, tip_key="fx_gate_rel")
        scale_row(gbox, "保持 ms", self.var_fx_gate_hold, 0, 200, 1, hot=True, tip_key="fx_gate_hold")
        scale_row(gbox, "衰减 dB", self.var_fx_gate_range, 6, 60, 1, hot=True, tip_key="fx_gate_range")

        # Compressor
        cbox = tk.Frame(fx, bg=TM_SURFACE)
        cbox.pack(fill="x", pady=(8, 4))
        comp_row = tk.Frame(cbox, bg=TM_SURFACE)
        comp_row.pack(anchor="w", fill="x")
        tk.Checkbutton(
            comp_row,
            text="压缩器",
            variable=self.var_fx_comp_en,
            bg=TM_SURFACE,
            font=sans_font(9),
            command=self._on_hot_param,
        ).pack(side="left")
        help_mark(comp_row, SETTING_TIPS["fx_comp"])
        scale_row(cbox, "阈值 dB", self.var_fx_comp_thr, -40, 0, 1, hot=True, tip_key="fx_comp_thr")
        scale_row(cbox, "比率", self.var_fx_comp_ratio, 1, 20, 0.5, hot=True, tip_key="fx_comp_ratio")
        scale_row(cbox, "启动 ms", self.var_fx_comp_att, 0.5, 50, 0.5, hot=True, tip_key="fx_comp_att")
        scale_row(cbox, "释放 ms", self.var_fx_comp_rel, 10, 500, 1, hot=True, tip_key="fx_comp_rel")
        scale_row(cbox, "增益 dB", self.var_fx_comp_mu, 0, 12, 0.5, hot=True, tip_key="fx_comp_mu")

        # EQ
        ebox = tk.Frame(fx, bg=TM_SURFACE)
        ebox.pack(fill="x", pady=(8, 4))
        erow = tk.Frame(ebox, bg=TM_SURFACE)
        erow.pack(fill="x")
        tk.Checkbutton(
            erow,
            text="均衡 EQ",
            variable=self.var_fx_eq_en,
            bg=TM_SURFACE,
            font=sans_font(9),
            command=self._on_hot_param,
        ).pack(side="left")
        help_mark(erow, SETTING_TIPS["fx_eq"])
        tk.Label(
            erow, text="预设", bg=TM_SURFACE, fg=TM_INK_MUTED, font=sans_font(10)
        ).pack(side="left", padx=(16, 4))
        preset_vals = list(EQ_PRESETS.keys())
        self.cmb_fx_preset = ttk.Combobox(
            erow,
            textvariable=self.var_fx_eq_preset,
            values=preset_vals,
            state="readonly",
            width=14,
        )
        self.cmb_fx_preset.pack(side="left")

        def _on_eq_preset(_e=None):
            key = str(self.var_fx_eq_preset.get() or "flat")
            gains = EQ_PRESETS.get(key) or EQ_PRESETS["flat"]
            for i, g in enumerate(gains):
                self.var_fx_eq_gains[i].set(float(g))
            self._on_hot_param()

        self.cmb_fx_preset.bind("<<ComboboxSelected>>", _on_eq_preset)
        # show Chinese labels as tip
        lab = " / ".join(f"{k}={EQ_PRESET_LABELS.get(k, k)}" for k in preset_vals[:3])
        tk.Label(
            ebox,
            text=f"预设：{lab}…",
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_HELP,
            anchor="w",
        ).pack(fill="x")
        eq_tip_keys = ("fx_eq_60", "fx_eq_250", "fx_eq_1k", "fx_eq_4k", "fx_eq_8k")
        for i, name in enumerate(EQ_LABELS):
            scale_row(
                ebox,
                name,
                self.var_fx_eq_gains[i],
                -12,
                12,
                0.5,
                hot=True,
                tip_key=eq_tip_keys[i] if i < len(eq_tip_keys) else "",
            )

        scale_row(
            fx, "输出增益 dB", self.var_fx_out_gain, -12, 12, 0.5, hot=True, tip_key="fx_out"
        )

        # --- Keyboard shortcuts ---
        self._build_hotkeys_settings_section(wrap, card)

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
            text="无 .index 时 Index Rate 自动为 0；换 index 后请重新开启变声 · F1 查看快捷键",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_HELP,
        )
        self.lbl_settings_hint.pack(side="left")
        # Wheel + width after children exist
        try:
            _bind_wheel_recursive(wrap)
        except Exception:
            pass
        fr.after(80, self._reflow_settings_page)
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
                fg=TM_HELP,
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
                fg=TM_HELP,
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
            self.cfg["monitor_device"] = str(self.var_monitor_dev.get() or "")
            self.cfg["monitor_enabled"] = bool(self.var_monitor_on.get())
            self.cfg["sg_wasapi_exclusive"] = bool(self.var_wasapi.get())
            self.cfg["sr_type"] = str(self.var_sr_type.get() or "sr_model")
            self.cfg["I_noise_reduce"] = bool(self.var_i_nr.get())
            self.cfg["O_noise_reduce"] = bool(self.var_o_nr.get())
            self.cfg["use_pv"] = bool(self.var_use_pv.get())
            self.cfg["function"] = str(self.var_function.get() or "vc")
            self.cfg["accel_backend"] = normalize_accel(
                str(self.var_accel.get() or "auto")
            )
            # DSP FX
            if hasattr(self, "var_fx_enabled"):
                self.cfg["fx_enabled"] = bool(self.var_fx_enabled.get())
                self.cfg["fx_gate_enabled"] = bool(self.var_fx_gate_en.get())
                self.cfg["fx_gate_threshold_db"] = float(self.var_fx_gate_thr.get())
                self.cfg["fx_gate_release_ms"] = float(self.var_fx_gate_rel.get())
                self.cfg["fx_gate_hold_ms"] = float(self.var_fx_gate_hold.get())
                self.cfg["fx_gate_range_db"] = float(self.var_fx_gate_range.get())
                self.cfg["fx_comp_enabled"] = bool(self.var_fx_comp_en.get())
                self.cfg["fx_comp_threshold_db"] = float(self.var_fx_comp_thr.get())
                self.cfg["fx_comp_ratio"] = float(self.var_fx_comp_ratio.get())
                self.cfg["fx_comp_attack_ms"] = float(self.var_fx_comp_att.get())
                self.cfg["fx_comp_release_ms"] = float(self.var_fx_comp_rel.get())
                self.cfg["fx_comp_makeup_db"] = float(self.var_fx_comp_mu.get())
                self.cfg["fx_eq_enabled"] = bool(self.var_fx_eq_en.get())
                self.cfg["fx_eq_preset"] = str(self.var_fx_eq_preset.get() or "flat")
                self.cfg["fx_eq_gains"] = [
                    float(self.var_fx_eq_gains[i].get()) for i in range(5)
                ]
                self.cfg["fx_out_gain_db"] = float(self.var_fx_out_gain.get())
            # Hotkey toggles (binding map applied via「应用快捷键」)
            if hasattr(self, "var_global_hk"):
                self.cfg["global_hotkeys"] = bool(self.var_global_hk.get())
            if hasattr(self, "var_restart_on_switch"):
                self.cfg["hotkey_restart_on_model_switch"] = bool(
                    self.var_restart_on_switch.get()
                )
        except Exception:
            pass

    def _init_gpu_backend(self) -> None:
        """Detect CUDA / DirectML and apply env for worker children."""

        def work():
            try:
                pref = normalize_accel(str(self.cfg.get("accel_backend") or "auto"))
                info = detect_full(ROOT, pref)
                self.root.after(0, lambda: self._apply_gpu_info(info))
            except Exception as e:
                self.root.after(
                    0,
                    lambda: self._set_status_visual(
                        "idle", "引擎待命", f"GPU 检测失败: {e}"
                    ),
                )

        threading.Thread(target=work, daemon=True).start()

    def _apply_gpu_info(self, info: dict) -> None:
        self._gpu_info = info or {}
        try:
            # In-place write to os.environ (apply_backend_env mutates mapping)
            apply_backend_env(os.environ, info)
        except Exception:
            pass
        label = info.get("label") or "?"
        detail = info.get("detail") or ""
        pref = info.get("preference") or "auto"
        backend = info.get("backend") or "?"
        line = f"加速：{label}"
        if detail:
            line += f" · {detail}"
        line += f"  （偏好 {pref} → {backend}）"
        # Soft mismatch: AMD pack but no DML / 50 pack but no CUDA
        try:
            from launcher.package_meta import load_package_meta

            pm = load_package_meta()
            var = str(pm.get("variant") or "")
            if var == "amd" and not info.get("has_dml"):
                line += "  · 本包为 DirectML，但 Runtime 未检出 DML"
            if var in ("nvidia", "nvidia50") and pref in ("auto", "cuda") and not info.get(
                "has_cuda"
            ):
                line += "  · 未检出 CUDA，确认使用了对应显卡发行包 Runtime"
        except Exception:
            pass
        try:
            if hasattr(self, "lbl_accel_status"):
                self.lbl_accel_status.configure(text=line, fg=TM_INK_MUTED)
        except Exception:
            pass
        # Subtitle when idle
        if not self.vc_running and not self._vc_starting:
            try:
                self.lbl_latency.configure(
                    text=f"{label}" + (f" · {detail}" if detail else "")
                )
            except Exception:
                pass

    def _force_restart_worker_for_backend(self) -> None:
        """Kill live worker so next VC start loads new TM_USE_DML / torch device."""
        import launcher.realtime_client as rt_client

        was_running = bool(self.vc_running or self._vc_starting)
        self.vc_running = False
        self._vc_starting = False
        try:
            rt_client.stop_vc_remote(force=True)
        except Exception:
            pass
        try:
            rt_client.quit_worker(force=True)
        except Exception:
            pass
        try:
            rt_client.kill_orphan_runtime_workers(include_worker=True)
        except Exception:
            pass
        try:
            self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
            self._set_status_visual(
                "idle",
                "引擎待命",
                "加速后端已变更，变声引擎已重置" if was_running else "加速后端已更新",
            )
            self._sync_bottom()
        except Exception:
            pass

    def _on_accel_changed(self) -> None:
        self.cfg["accel_backend"] = normalize_accel(str(self.var_accel.get() or "auto"))
        save_config(self.cfg)
        # Re-detect; always restart worker so CUDA/DML/CPU env reloads
        def work():
            try:
                info = detect_full(ROOT, self.cfg["accel_backend"])

                def done():
                    self._apply_gpu_info(info)
                    self._force_restart_worker_for_backend()
                    tip = (
                        f"已设为：{info.get('label')}（{info.get('backend')}）\n"
                        "变声引擎已按新后端重置；请重新「开启变声」。\n\n"
                        "A/I 卡请用 AMD 发行包；50 系请用 50 系包，勿混用 Runtime。"
                    )
                    messagebox.showinfo("加速后端", tip)

                self.root.after(0, done)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("检测失败", str(e)))

        threading.Thread(target=work, daemon=True).start()

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
        """Debounced hot update while VC running; also bind params to current voice."""
        if not self._loading_voice:
            try:
                self._collect_settings_into_cfg()
            except Exception:
                pass
            self._persist_voice_params_to_model()
            # Hint only — full _sync_bottom reflows dock and looks like a shake
            try:
                self._refresh_dock_hint_only()
            except Exception:
                pass
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
                monitor_enabled=self.cfg.get("monitor_enabled"),
                monitor_device=self.cfg.get("monitor_device"),
                fx_enabled=self.cfg.get("fx_enabled"),
                fx_gate_enabled=self.cfg.get("fx_gate_enabled"),
                fx_gate_threshold_db=self.cfg.get("fx_gate_threshold_db"),
                fx_gate_release_ms=self.cfg.get("fx_gate_release_ms"),
                fx_gate_hold_ms=self.cfg.get("fx_gate_hold_ms"),
                fx_gate_range_db=self.cfg.get("fx_gate_range_db"),
                fx_comp_enabled=self.cfg.get("fx_comp_enabled"),
                fx_comp_threshold_db=self.cfg.get("fx_comp_threshold_db"),
                fx_comp_ratio=self.cfg.get("fx_comp_ratio"),
                fx_comp_attack_ms=self.cfg.get("fx_comp_attack_ms"),
                fx_comp_release_ms=self.cfg.get("fx_comp_release_ms"),
                fx_comp_makeup_db=self.cfg.get("fx_comp_makeup_db"),
                fx_eq_enabled=self.cfg.get("fx_eq_enabled"),
                fx_eq_gains=self.cfg.get("fx_eq_gains"),
                fx_eq_preset=self.cfg.get("fx_eq_preset"),
                fx_out_gain_db=self.cfg.get("fx_out_gain_db"),
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
        self._set_status_visual("busy", "正在连接变声引擎…", "首次加载可能需要数十秒")

    def _apply_perf_preset(self, key: str) -> None:
        """Map quality/latency presets (inspired by realtime VC chunk tradeoffs)."""
        presets = {
            # block_time, crossfade, extra_time (aligned with realtime quality/latency tradeoff)
            "low_latency": (0.12, 0.04, 1.5),
            "balanced": (0.22, 0.05, 2.5),
            "stable": (0.40, 0.08, 3.5),
        }
        vals = presets.get(key) or presets["balanced"]
        try:
            self.var_block.set(vals[0])
            self.var_crossfade.set(vals[1])
            self.var_extra.set(vals[2])
            self.cfg["block_time"] = vals[0]
            self.cfg["crossfade_length"] = vals[1]
            self.cfg["extra_time"] = vals[2]
            save_config(self.cfg)
        except Exception:
            pass
        names = {"low_latency": "低延迟", "balanced": "均衡", "stable": "稳定"}
        self._set_status_visual(
            "idle",
            f"性能预设：{names.get(key, key)}",
            "请重新「开启变声」后生效",
        )
        try:
            if hasattr(self, "lbl_settings_hint"):
                self.lbl_settings_hint.configure(
                    text=f"已应用「{names.get(key, key)}」预设 · 需重新开启变声",
                    fg=TM_OK,
                )
        except Exception:
            pass

    def _silent_check_updates(self) -> None:
        """Background catalog fetch; badge 更新 nav if newer GUI (no modal)."""

        def work():
            has = False
            cat = None
            try:
                from launcher.config_store import load_config
                from launcher.online.catalog import fetch_catalog
                from launcher.online.gui_update import check_gui_update

                urls = []
                u = str(load_config().get("update_manifest_url") or "").strip()
                if u:
                    urls.append(u)
                cat = fetch_catalog(urls)
                st = check_gui_update(cat)
                has = bool(st.get("available"))
            except Exception:
                has = False
                cat = None

            def done(has_new=has, catalog=cat):
                self._update_badge_on = has_new
                self._apply_update_nav_badge()
                if has_new and catalog is not None and hasattr(self, "_store_page"):
                    try:
                        self._store_page.catalog = catalog
                    except Exception:
                        pass

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _apply_update_nav_badge(self) -> None:
        btn = self.nav_btns.get("store")
        if not btn:
            return
        try:
            if self._update_badge_on:
                btn.configure(text="更新·新")
            else:
                btn.configure(text="更新")
            # re-apply active style if on store page
            if self._current_page == "store":
                btn.set_active(True)
        except Exception:
            pass

    def reload_devices(self) -> None:
        # list_devices stops the audio stream on the worker — reflect that in UI
        was_live = bool(self.vc_running or self._vc_starting)
        if was_live:
            self.vc_running = False
            self._vc_starting = False
            try:
                self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
            except Exception:
                pass
        self._set_status_visual(
            "busy",
            "重载设备列表…",
            "变声已停止，请稍候" if was_live else "请稍候",
        )

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
            if hasattr(self, "cmb_monitor"):
                self.cmb_monitor["values"] = outs
                cur = self.var_monitor_dev.get()
                pick = self._prefer_monitor_device(outs, cur)
                # Always correct empty / missing / virtual endpoints (e.g. Steam Speakers)
                if pick and pick != cur:
                    if (not cur) or (cur not in outs) or self._is_virtual_monitor_name(
                        cur
                    ):
                        self.var_monitor_dev.set(pick)
                        try:
                            self.cfg["monitor_device"] = pick
                            save_config(self.cfg)
                        except Exception:
                            pass
        except Exception:
            pass
        err = str(st.get("error") or "")
        state = str(st.get("state") or "")
        if err and state == "error":
            self._set_status_visual("error", "引擎错误", err[:48])
        elif toast:
            self._set_status_visual(
                "idle",
                "设备已刷新",
                f"输入 {len(ins)} · 输出 {len(outs)}",
            )
        elif not self.vc_running and not self._vc_starting:
            self._set_status_visual("idle", "引擎待命", APP_PRODUCT_TAGLINE)
        try:
            self._refresh_monitor_hint()
        except Exception:
            pass

    def _page_more(self) -> tk.Frame:
        """More page: pack layout only (no place) so footer never overlaps buttons."""
        fr = tk.Frame(self.body, bg=TM_BG)
        fr.columnconfigure(0, weight=1)
        fr.rowconfigure(0, weight=1)

        # Scroll when window is short — fixed place() used to sit on top of buttons
        canvas = tk.Canvas(fr, bg=TM_BG, highlightthickness=0)
        sb = tk.Scrollbar(fr, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        wrap = tk.Frame(canvas, bg=TM_BG)
        win = canvas.create_window((0, 0), window=wrap, anchor="n")

        def _sync(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            try:
                cw = max(int(canvas.winfo_width()), 200)
                # Center content block
                wrap.update_idletasks()
                ww = max(wrap.winfo_reqwidth(), 320)
                x = max((cw - ww) // 2, 12)
                canvas.coords(win, x, 16)
                canvas.itemconfigure(win, width=min(ww + 8, cw - 24))
            except Exception:
                pass

        wrap.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _sync)

        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        canvas.bind("<MouseWheel>", _wheel)
        wrap.bind("<MouseWheel>", _wheel)

        inner = tk.Frame(wrap, bg=TM_BG)
        inner.pack(padx=24, pady=(8, 16))

        PageHeader(
            inner,
            eyebrow="MORE",
            title="其他",
            lead="高级入口与紧急操作。日常开黑一般只需要首页与设置。",
        ).pack(anchor="w", pady=(0, 16))
        box = tk.Frame(inner, bg=TM_BG)
        box.pack(anchor="w", fill="x")

        def soft(text, cmd):
            GhostButton(box, text, command=cmd, padx=22, pady=12).pack(
                pady=6, fill="x", ipadx=40
            )

        soft("打开训练 / 翻唱 WebUI（高级 · 浏览器）", self.open_webui)
        soft("打开首次设置启动器", self.open_bootstrap)
        soft("打开 User_Data", lambda: open_path(USER_DATA))
        soft("打开安装目录", lambda: open_path(ROOT))
        soft("强制结束变声引擎（卡音频时点）", self._force_kill_engine)
        soft("快捷键说明", self.show_hotkeys_help)
        soft("使用说明", lambda: self.show_page("help"))
        soft("重新观看新手引导", lambda: self.show_onboarding(first_run=False))
        soft("在线更新与音色库", lambda: self.show_page("store"))

        # Footer after buttons (pack) — never place() over the list
        tk.Label(
            inner,
            text=tracked("TURING MIRROR  ·  RVC ENGINE", gap="  ")
            + f"  ·  v{APP_VERSION}",
            bg=TM_BG,
            fg=TM_META,
            font=mono_font(8),
        ).pack(anchor="center", pady=(20, 12))

        def _wheel_tree(w):
            w.bind("<MouseWheel>", _wheel)
            for c in w.winfo_children():
                _wheel_tree(c)

        try:
            _wheel_tree(wrap)
        except Exception:
            pass
        fr.after(80, _sync)
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
            self._set_status_visual("idle", "引擎已强制结束", APP_PRODUCT_TAGLINE)
            messagebox.showinfo("完成", f"已清理变声相关进程（约 {n} 个）。")
        except Exception as e:
            messagebox.showerror("失败", str(e))

    def open_help(self) -> None:
        """Open dedicated in-app 说明 page."""
        self.show_page("help")

    def _show_cable_help(self) -> None:
        messagebox.showinfo(
            "虚拟声卡接线",
            "【在本软件「设置」】\n"
            "· 输入设备 = 真实麦克风（不要选 CABLE）\n"
            "· 输出设备 = CABLE Input\n"
            "· 监听设备（可选）= 耳机，配合「变声时监听自己」\n"
            "· 设备类型：MME 最省事；WASAPI 独占一般不要勾\n\n"
            "【游戏 / QQ / Discord】\n"
            "· 麦克风 = CABLE Output（对面听到变声）\n\n"
            "【Windows】\n"
            "· 默认播放 = 耳机，不要设成 CABLE\n\n"
            "【开启变声】\n"
            "· 底栏点「开启变声」；首次加载约 20～40 秒\n"
            "· 没有 .index 也能用\n\n"
            "更完整的说明见顶部导航「说明」页。",
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

    # ------------------------------------------------------------------
    # Hotkeys
    # ------------------------------------------------------------------

    def _setup_hotkeys(self) -> None:
        """(Re)bind in-app Tk shortcuts and optional Windows global hotkeys."""
        self._hotkey_map = merge_hotkeys(self.cfg.get("hotkeys"))
        # Clear previous binds
        for seq in self._tk_hotkey_binds:
            try:
                self.root.unbind(seq)
            except Exception:
                pass
        self._tk_hotkey_binds.clear()

        for action_id, spec in self._hotkey_map.items():
            if not spec:
                continue
            seq = to_tk_sequence(spec)
            if not seq:
                continue

            def _handler(_event=None, aid=action_id):
                return self._on_hotkey_event(aid, _event)

            try:
                self.root.bind(seq, _handler)
                self._tk_hotkey_binds.append(seq)
            except Exception:
                pass

        self._refresh_global_hotkeys()

    def _enabled_global_action_ids(self) -> list[str]:
        """Global-eligible actions whose per-key「全局」toggle is on."""
        flags = merge_global_actions(self.cfg.get("global_hotkey_actions"))
        return [aid for aid in DEFAULT_GLOBAL_ACTIONS if flags.get(aid, True)]

    def _refresh_global_hotkeys(self) -> None:
        """Register or tear down Windows global hotkeys based on config."""
        try:
            self._global_hk.unregister_all()
        except Exception:
            pass
        if not bool(self.cfg.get("global_hotkeys")):
            return
        if sys.platform != "win32":
            return
        try:
            hwnd = self.root.winfo_id()
            fails = self._global_hk.register(
                hwnd, self._hotkey_map, action_ids=self._enabled_global_action_ids()
            )
            if fails and hasattr(self, "lbl_online"):
                # Soft notice — don't block UI
                self.lbl_online.configure(
                    text=f"部分全局快捷键未注册（{len(fails)}）",
                    fg=TM_WARN,
                )
        except Exception:
            pass

    def _poll_global_hotkeys(self) -> None:
        if getattr(self, "_closing", False):
            return
        try:
            aid = self._global_hk.poll_once()
            if aid:
                self._dispatch_hotkey(aid, from_global=True)
        except Exception:
            pass
        try:
            if not getattr(self, "_closing", False):
                self.root.after(80, self._poll_global_hotkeys)
        except Exception:
            pass

    def _on_hotkey_event(self, action_id: str, event=None) -> Optional[str]:
        # Skip when typing in Entry / Combobox
        try:
            focus = self.root.focus_get()
            if focus_should_skip_hotkey(focus):
                return None
        except Exception:
            pass
        self._dispatch_hotkey(action_id, from_global=False)
        return "break"

    def _dispatch_hotkey(self, action_id: str, from_global: bool = False) -> None:
        if action_id == "prev_model":
            self._shift_model(-1)
        elif action_id == "next_model":
            self._shift_model(1)
        elif action_id == "toggle_vc":
            self.toggle_vc()
        elif action_id == "pitch_up":
            self._nudge_pitch(1)
        elif action_id == "pitch_down":
            self._nudge_pitch(-1)
        elif action_id == "toggle_monitor":
            self._toggle_monitor()
        elif action_id == "toggle_mode":
            cur = "vc"
            try:
                cur = str(self.var_function.get() or "vc")
            except Exception:
                cur = str(self.cfg.get("function") or "vc")
            self._set_function_mode("im" if cur == "vc" else "vc")
        elif action_id == "undo_voice":
            self.undo_voice_params()
        elif action_id == "redo_voice":
            self.redo_voice_params()
        elif action_id == "reset_voice":
            self.reset_voice_params_default()
        elif action_id == "page_home":
            self.show_page("home")
        elif action_id == "page_models":
            self.show_page("models")
        elif action_id == "page_settings":
            self.show_page("settings")
        elif action_id == "page_more":
            self.show_page("more")
        elif action_id == "show_hotkeys":
            self.show_hotkeys_help()
        elif action_id.startswith("select_model_"):
            try:
                n = int(action_id.rsplit("_", 1)[-1])
                self._select_model_by_slot(n)
            except Exception:
                pass

    def _select_model_by_slot(self, one_based: int) -> None:
        """Quick-pick model 1..9 (1-based index into catalog order)."""
        if not self.models or one_based < 1:
            return
        ix = one_based - 1
        if ix >= len(self.models):
            self._show_switch_toast(f"没有第 {one_based} 个音色")
            return
        self._select_model(ix, feedback=True, maybe_restart=True)

    def _nudge_pitch(self, delta: int) -> None:
        self._voice_hist_push()
        try:
            if hasattr(self, "var_pitch"):
                cur = int(self.var_pitch.get())
            else:
                cur = int(self.cfg.get("pitch") or 0)
        except Exception:
            cur = int(self.cfg.get("pitch") or 0)
        new_v = max(-24, min(24, cur + int(delta)))
        self.cfg["pitch"] = new_v
        try:
            if hasattr(self, "var_pitch"):
                self.var_pitch.set(new_v)
        except Exception:
            pass
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self._persist_voice_params_to_model()
        self._refresh_dock_hint_only()
        if self.vc_running:
            self._on_hot_param()
        self._set_status_visual(
            "live" if self.vc_running else "idle",
            f"音高 {new_v:+d}" if new_v else "音高 0",
            "已写入当前音色" if self.vc_running else "已保存到当前音色",
        )

    @staticmethod
    def _is_virtual_monitor_name(name: str) -> bool:
        low = (name or "").lower()
        if not low:
            return True
        keys = (
            "cable",
            "voicemeeter",
            "mapper",
            "steam streaming",
            "steam streaming speakers",
            "virtual",
            "vb-audio",
            "vb audio",
            "nvidia high definition",
            "nvidia broadcast",
            "网易虚拟",
            "fxsound",
            "discord",
            "obs virtual",
            "stereo mix",
            "主声音驱动",
            "primary sound",
        )
        return any(k in low for k in keys)

    def _prefer_monitor_device(
        self, outs: list, current: str = ""
    ) -> str:
        """Pick real headphones/speakers; avoid CABLE / Steam / virtual endpoints."""
        if not outs:
            return current or ""
        main_out = ""
        try:
            main_out = str(self.var_output_dev.get() or "")
        except Exception:
            main_out = str(self.cfg.get("sg_output_device") or "")

        def usable(n: str) -> bool:
            if not n or n == main_out:
                return False
            if self._is_virtual_monitor_name(n):
                return False
            if main_out and "cable" in main_out.lower() and "cable" in n.lower():
                return False
            return True

        if current and current in outs and usable(current):
            return current

        # Prefer names that look like headphones
        for n in outs:
            low = n.lower()
            if usable(n) and (
                "耳机" in n
                or "headphone" in low
                or "headset" in low
                or "earphone" in low
            ):
                return n
        for n in outs:
            if usable(n):
                return n
        return current if current in outs else outs[0]

    def _refresh_monitor_hint(self) -> None:
        if not hasattr(self, "lbl_monitor_hint"):
            return
        try:
            on = bool(self.var_monitor_on.get())
            dev = str(self.var_monitor_dev.get() or "")
        except Exception:
            return
        if not on:
            self.lbl_monitor_hint.configure(
                text="关闭时只走「输出设备」（通常 CABLE）；开启后在耳机里听变声",
                fg=TM_HELP,
            )
            return
        if not dev:
            self.lbl_monitor_hint.configure(
                text="请选择监听设备：你的真实耳机/音箱",
                fg=TM_WARN,
            )
            return
        if self._is_virtual_monitor_name(dev):
            self.lbl_monitor_hint.configure(
                text=f"当前「{dev}」是虚拟设备，听不到。请改选真实耳机（如 KM-HIFI）",
                fg=TM_WARN,
            )
            return
        self.lbl_monitor_hint.configure(
            text=f"监听中将播放到：{dev}",
            fg=TM_OK,
        )

    def _on_monitor_toggle(self) -> None:
        """Checkbox: validate device then push hot param."""
        try:
            on = bool(self.var_monitor_on.get())
        except Exception:
            on = False
        if on:
            outs = list(self._device_lists.get("output_devices") or [])
            cur = str(self.var_monitor_dev.get() or "")
            if (not cur) or self._is_virtual_monitor_name(cur) or (
                outs and cur not in outs
            ):
                pick = self._prefer_monitor_device(outs, cur)
                if pick:
                    self.var_monitor_dev.set(pick)
                    self.cfg["monitor_device"] = pick
            self._refresh_monitor_hint()
            # Soft warn if still virtual
            try:
                dev = str(self.var_monitor_dev.get() or "")
            except Exception:
                dev = ""
            if self._is_virtual_monitor_name(dev):
                messagebox.showwarning(
                    "监听设备无效",
                    "监听设备仍是虚拟声卡（CABLE / Steam / 网易虚拟等），"
                    "耳机里不会有声音。\n\n"
                    "请在「监听设备」里选择真实耳机或音箱（例如带「耳机」的设备），"
                    "再开启监听。",
                )
        else:
            self._refresh_monitor_hint()
        self._on_hot_param()

    def _on_monitor_device(self) -> None:
        self._refresh_monitor_hint()
        self._on_hot_param()

    def _toggle_monitor(self) -> None:
        try:
            if hasattr(self, "var_monitor_on"):
                cur = bool(self.var_monitor_on.get())
            else:
                cur = bool(self.cfg.get("monitor_enabled"))
        except Exception:
            cur = bool(self.cfg.get("monitor_enabled"))
        new_v = not cur
        try:
            if hasattr(self, "var_monitor_on"):
                self.var_monitor_on.set(new_v)
        except Exception:
            pass
        self.cfg["monitor_enabled"] = new_v
        if new_v:
            outs = list(self._device_lists.get("output_devices") or [])
            cur_dev = str(self.cfg.get("monitor_device") or "")
            try:
                cur_dev = str(self.var_monitor_dev.get() or cur_dev)
            except Exception:
                pass
            pick = self._prefer_monitor_device(outs, cur_dev)
            if pick:
                self.cfg["monitor_device"] = pick
                try:
                    self.var_monitor_dev.set(pick)
                except Exception:
                    pass
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self._refresh_monitor_hint()
        if self.vc_running:
            self._on_hot_param()
        dev = str(self.cfg.get("monitor_device") or "")
        self._set_status_visual(
            "live" if self.vc_running else "idle",
            "监听自己：开" if new_v else "监听自己：关",
            (dev[:28] if new_v and dev else "运行中可热切换")
            if self.vc_running
            else ("下次开启变声生效" if new_v else ""),
        )

    def _restart_vc_for_new_model(self) -> None:
        """Debounced stop+start so rapid Left/Right only restarts once."""
        if self._model_restart_job is not None:
            try:
                self.root.after_cancel(self._model_restart_job)
            except Exception:
                pass
        name = ""
        if self.models:
            name = self.models[self.model_idx].get("name") or ""
        self._set_status_visual(
            "busy",
            f"切换音色 · {name}",
            "将自动重启变声引擎…",
        )
        self._model_restart_job = self.root.after(450, self._do_model_restart)

    def _do_model_restart(self) -> None:
        self._model_restart_job = None
        if not self.models:
            return

        def work():
            try:
                rt_client.stop_vc_remote(force=False, timeout_s=8.0)
            except Exception:
                try:
                    rt_client.stop_vc_remote(force=True, timeout_s=6.0)
                except Exception:
                    pass
            self.root.after(0, self._start_vc)

        self.vc_running = False
        self._vc_starting = True
        try:
            self.btn_start.configure(text="切换中…", bg=TM_OK)
        except Exception:
            pass
        threading.Thread(target=work, daemon=True).start()

    def _build_hotkeys_settings_section(self, wrap, card_fn) -> None:
        """Settings card: enable global, list bindings, capture/reset."""
        sec = card_fn(wrap, "快捷键")
        intro = tk.Label(
            sec,
            text=(
                "窗口内快捷键默认可用；开启「全局快捷键」总开关后，勾选了「全局」的按键在游戏全屏时也能触发。"
                "每个按键可单独取消「全局」；点「录制」后按下组合键即可自定义。F1 打开完整说明。"
            ),
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_HELP,
            justify="left",
            anchor="w",
            wraplength=640,
        )
        intro.pack(fill="x", pady=(0, 8))
        self._settings_wrap_labels.append(intro)

        self.var_global_hk = tk.BooleanVar(value=bool(self.cfg.get("global_hotkeys")))
        self.var_restart_on_switch = tk.BooleanVar(
            value=bool(self.cfg.get("hotkey_restart_on_model_switch", True))
        )
        tk.Checkbutton(
            sec,
            text="启用全局快捷键（Windows · 游戏中可用 · 各键的「全局」总开关）",
            variable=self.var_global_hk,
            bg=TM_SURFACE,
            font=sans_font(9),
            command=self._on_global_hk_toggle,
        ).pack(anchor="w")
        tk.Checkbutton(
            sec,
            text="切换音色时若正在变声则自动重启引擎",
            variable=self.var_restart_on_switch,
            bg=TM_SURFACE,
            font=sans_font(9),
            command=self._on_restart_switch_toggle,
        ).pack(anchor="w", pady=(2, 8))

        # Per-action global-enable flags (default all on; gated by master switch)
        gflags = merge_global_actions(self.cfg.get("global_hotkey_actions"))
        self._global_action_vars: dict[str, tk.BooleanVar] = {}
        self._global_action_checks: dict[str, tk.Checkbutton] = {}
        self._hotkey_row_vars: dict[str, tk.StringVar] = {}
        # Compact list — primary actions first
        primary = [
            "prev_model",
            "next_model",
            "toggle_vc",
            "pitch_up",
            "pitch_down",
            "toggle_monitor",
            "select_model_1",
            "select_model_2",
            "select_model_3",
            "page_home",
            "page_models",
            "page_settings",
            "show_hotkeys",
        ]
        for aid in primary:
            act = ACTION_BY_ID.get(aid)
            if not act:
                continue
            row = tk.Frame(sec, bg=TM_SURFACE)
            row.pack(fill="x", pady=2)
            tk.Label(
                row,
                text=act.label,
                font=sans_font(9),
                bg=TM_SURFACE,
                fg=TM_INK,
                width=18,
                anchor="w",
            ).pack(side="left")
            var = tk.StringVar(value=self._hotkey_map.get(aid) or "")
            self._hotkey_row_vars[aid] = var
            ent = tk.Entry(
                row,
                textvariable=var,
                font=mono_font(9),
                width=16,
                relief="flat",
                bg=TM_INSET,
                fg=TM_INK,
            )
            ent.pack(side="left", padx=(4, 6))
            tk.Button(
                row,
                text="录制",
                font=sans_font(8),
                bg=TM_INSET,
                fg=TM_INK,
                relief="flat",
                cursor="hand2",
                command=lambda a=aid: self._begin_capture_hotkey(a),
                bd=0,
                padx=8,
                pady=2,
            ).pack(side="left", padx=2)
            tk.Button(
                row,
                text="清空",
                font=sans_font(8),
                bg=TM_INSET,
                fg=TM_INK_MUTED,
                relief="flat",
                cursor="hand2",
                command=lambda a=aid, v=var: self._clear_hotkey_row(a, v),
                bd=0,
                padx=6,
                pady=2,
            ).pack(side="left", padx=2)
            if act.global_ok:
                gvar = tk.BooleanVar(value=bool(gflags.get(aid, True)))
                self._global_action_vars[aid] = gvar
                gcb = tk.Checkbutton(
                    row,
                    text="全局",
                    variable=gvar,
                    bg=TM_SURFACE,
                    fg=TM_INK_MUTED,
                    activebackground=TM_SURFACE,
                    selectcolor=TM_INSET,
                    font=sans_font(8),
                    command=self._on_per_key_global_toggle,
                )
                gcb.pack(side="left", padx=(8, 0))
                self._global_action_checks[aid] = gcb
            else:
                tk.Label(
                    row,
                    text="窗口内",
                    font=sans_font(8),
                    bg=TM_SURFACE,
                    fg=TM_META,
                ).pack(side="left", padx=(8, 0))

        self._sync_per_key_global_state()

        btnrow = tk.Frame(sec, bg=TM_SURFACE)
        btnrow.pack(fill="x", pady=(10, 0))
        tk.Button(
            btnrow,
            text="应用快捷键",
            font=sans_font(9),
            bg=TM_ACCENT,
            fg=TM_ACCENT_INK,
            relief="flat",
            cursor="hand2",
            command=self._apply_hotkeys_from_ui,
            bd=0,
            padx=12,
            pady=5,
        ).pack(side="left")
        tk.Button(
            btnrow,
            text="恢复默认",
            font=sans_font(9),
            bg=TM_INSET,
            fg=TM_INK,
            relief="flat",
            cursor="hand2",
            command=self._reset_hotkeys_defaults,
            bd=0,
            padx=12,
            pady=5,
        ).pack(side="left", padx=8)
        tk.Button(
            btnrow,
            text="查看全部",
            font=sans_font(9),
            bg=TM_INSET,
            fg=TM_INK,
            relief="flat",
            cursor="hand2",
            command=self.show_hotkeys_help,
            bd=0,
            padx=12,
            pady=5,
        ).pack(side="left")
        self.lbl_hk_status = tk.Label(
            sec,
            text="",
            font=sans_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        )
        self.lbl_hk_status.pack(fill="x", pady=(6, 0))

    def _on_global_hk_toggle(self) -> None:
        self.cfg["global_hotkeys"] = bool(self.var_global_hk.get())
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self._sync_per_key_global_state()
        self._refresh_global_hotkeys()
        if hasattr(self, "lbl_hk_status"):
            on = bool(self.cfg.get("global_hotkeys"))
            self.lbl_hk_status.configure(
                text="全局快捷键已开启" if on else "全局快捷键已关闭",
                fg=TM_OK if on else TM_META,
            )

    def _sync_per_key_global_state(self) -> None:
        """Enable per-key「全局」checkboxes only while the master switch is on."""
        on = bool(getattr(self, "var_global_hk", None) and self.var_global_hk.get())
        for cb in getattr(self, "_global_action_checks", {}).values():
            try:
                cb.configure(state="normal" if on else "disabled")
            except Exception:
                pass

    def _collect_global_action_flags(self) -> dict[str, bool]:
        return {
            aid: bool(v.get())
            for aid, v in getattr(self, "_global_action_vars", {}).items()
        }

    def _on_per_key_global_toggle(self) -> None:
        self.cfg["global_hotkey_actions"] = self._collect_global_action_flags()
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self._refresh_global_hotkeys()
        if hasattr(self, "lbl_hk_status"):
            n = sum(1 for v in self._collect_global_action_flags().values() if v)
            self.lbl_hk_status.configure(
                text=f"全局按键已更新（{n} 个启用）", fg=TM_OK
            )

    def _on_restart_switch_toggle(self) -> None:
        self.cfg["hotkey_restart_on_model_switch"] = bool(
            self.var_restart_on_switch.get()
        )
        try:
            save_config(self.cfg)
        except Exception:
            pass

    def _clear_hotkey_row(self, action_id: str, var: tk.StringVar) -> None:
        var.set("")

    def _begin_capture_hotkey(self, action_id: str) -> None:
        self._capture_action_id = action_id
        act = ACTION_BY_ID.get(action_id)
        label = act.label if act else action_id
        if hasattr(self, "lbl_hk_status"):
            self.lbl_hk_status.configure(
                text=f"请按下要绑定到「{label}」的键…（Esc 取消）",
                fg=TM_WARN,
            )
        # Bind once on root
        self.root.bind("<KeyPress>", self._on_capture_key, add="+")

    def _on_capture_key(self, event) -> Optional[str]:
        if not self._capture_action_id:
            return None
        try:
            ks = str(getattr(event, "keysym", "") or "")
            if ks.lower() in ("escape", "esc"):
                self._end_capture(None)
                return "break"
            # Ignore bare modifiers
            if ks.lower() in (
                "shift_l",
                "shift_r",
                "control_l",
                "control_r",
                "alt_l",
                "alt_r",
                "meta_l",
                "meta_r",
                "win_l",
                "win_r",
            ):
                return "break"
            spec = event_to_hotkey_spec(event)
            if not spec:
                return "break"
            self._end_capture(spec)
            return "break"
        except Exception:
            self._end_capture(None)
            return "break"

    def _end_capture(self, spec: Optional[str]) -> None:
        aid = self._capture_action_id
        self._capture_action_id = None
        try:
            self.root.unbind("<KeyPress>")
        except Exception:
            pass
        # Re-apply normal hotkeys after unbinding capture
        self._setup_hotkeys()
        if not aid:
            return
        if spec is None:
            if hasattr(self, "lbl_hk_status"):
                self.lbl_hk_status.configure(text="已取消录制", fg=TM_META)
            return
        if aid in getattr(self, "_hotkey_row_vars", {}):
            self._hotkey_row_vars[aid].set(spec)
        if hasattr(self, "lbl_hk_status"):
            self.lbl_hk_status.configure(
                text=f"已录制 {spec}（请点「应用快捷键」生效）",
                fg=TM_OK,
            )

    def _apply_hotkeys_from_ui(self) -> None:
        custom: dict[str, str] = {}
        # Start from full map so unlisted select_model_4..9 stay
        custom.update(self._hotkey_map)
        for aid, var in getattr(self, "_hotkey_row_vars", {}).items():
            raw = str(var.get() or "").strip()
            if not raw:
                custom[aid] = ""
            else:
                custom[aid] = normalize_hotkey(raw)
        # Preserve select_model_4..9 from defaults if not in UI
        for i in range(4, 10):
            k = f"select_model_{i}"
            if k not in getattr(self, "_hotkey_row_vars", {}):
                custom.setdefault(k, DEFAULT_HOTKEYS.get(k, ""))

        dups = find_duplicate_bindings(custom)
        if dups:
            lines = []
            for key, ids in dups:
                labels = [
                    ACTION_BY_ID[i].label if i in ACTION_BY_ID else i for i in ids
                ]
                lines.append(f"{key} → {', '.join(labels)}")
            messagebox.showwarning(
                "快捷键冲突",
                "以下按键绑定到了多个功能，请修改后再应用：\n\n" + "\n".join(lines),
            )
            return

        self.cfg["hotkeys"] = {
            k: v for k, v in custom.items() if v != DEFAULT_HOTKEYS.get(k)
        }
        # Also store explicit empty overrides for cleared defaults
        for k, v in custom.items():
            if not v and DEFAULT_HOTKEYS.get(k):
                self.cfg["hotkeys"][k] = ""
        if hasattr(self, "var_global_hk"):
            self.cfg["global_hotkeys"] = bool(self.var_global_hk.get())
        if getattr(self, "_global_action_vars", None):
            self.cfg["global_hotkey_actions"] = self._collect_global_action_flags()
        if hasattr(self, "var_restart_on_switch"):
            self.cfg["hotkey_restart_on_model_switch"] = bool(
                self.var_restart_on_switch.get()
            )
        try:
            save_config(self.cfg)
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            return
        self._hotkey_map = merge_hotkeys(self.cfg.get("hotkeys"))
        # Refresh row display
        for aid, var in getattr(self, "_hotkey_row_vars", {}).items():
            var.set(self._hotkey_map.get(aid) or "")
        self._setup_hotkeys()
        if hasattr(self, "lbl_hk_status"):
            self.lbl_hk_status.configure(text="快捷键已应用", fg=TM_OK)
        messagebox.showinfo("已应用", "快捷键已更新。")

    def _reset_hotkeys_defaults(self) -> None:
        if not messagebox.askyesno("恢复默认", "将快捷键恢复为默认绑定？"):
            return
        self.cfg["hotkeys"] = {}
        self.cfg["global_hotkey_actions"] = {}
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self._hotkey_map = merge_hotkeys({})
        for aid, var in getattr(self, "_hotkey_row_vars", {}).items():
            var.set(self._hotkey_map.get(aid) or "")
        # Per-key「全局」flags back to all-on default
        defaults = merge_global_actions({})
        for aid, gvar in getattr(self, "_global_action_vars", {}).items():
            gvar.set(bool(defaults.get(aid, True)))
        self._sync_per_key_global_state()
        self._setup_hotkeys()
        if hasattr(self, "lbl_hk_status"):
            self.lbl_hk_status.configure(text="已恢复默认快捷键", fg=TM_OK)

    def show_hotkeys_help(self) -> None:
        """Popup listing current shortcut map."""
        win = tk.Toplevel(self.root)
        win.title("快捷键说明")
        win.configure(bg=TM_BG)
        win.geometry("480x520")
        win.minsize(400, 360)
        win.transient(self.root)
        try:
            win.grab_set()
        except Exception:
            pass
        tk.Label(
            win,
            text="快捷键",
            font=serif_font(16, "bold"),
            bg=TM_BG,
            fg=TM_INK,
        ).pack(anchor="w", padx=20, pady=(18, 6))
        frame = tk.Frame(
            win, bg=TM_SURFACE, highlightthickness=1, highlightbackground=TM_HAIRLINE
        )
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
        body = format_help_text(self.cfg.get("hotkeys"))
        if bool(self.cfg.get("global_hotkeys")):
            body += "\n\n当前：全局快捷键已开启。"
        else:
            body += "\n\n当前：仅窗口内生效（可在设置中开启全局）。"
        text.insert("1.0", body)
        text.configure(state="disabled")
        GhostButton(win, "关闭", command=win.destroy, padx=18, pady=8).pack(
            pady=(4, 14)
        )

    # ------------------------------------------------------------------
    # First-run newbie onboarding wizard
    # ------------------------------------------------------------------
    def _maybe_show_onboarding(self) -> None:
        """Show the guide once on first launch; no-op if already completed."""
        try:
            if bool(self.cfg.get("onboarding_done", False)):
                return
        except Exception:
            return
        self.show_onboarding(first_run=True)

    def _mark_onboarding_done(self) -> None:
        self.cfg["onboarding_done"] = True
        try:
            save_config(self.cfg)
        except Exception:
            pass

    def _open_community_link(self) -> None:
        """Open the community entry (placeholder → 换成 B 站视频链接)."""
        url = (COMMUNITY_LINK_URL or "").strip()
        if url:
            try:
                webbrowser.open(url)
                return
            except Exception:
                pass
        messagebox.showinfo(
            "获取 QQ 群",
            "请打开 UP 主视频：一键三连 + 关注后，私信「加群」即可获取 QQ 群号。",
        )

    def show_onboarding(self, first_run: bool = False) -> None:
        """Simple multi-step guide; ends with community + help call-to-action."""
        steps: list[tuple[str, str, list[str]]] = [
            (
                "WELCOME",
                "欢迎使用 Turing Mirror 变声器",
                [
                    "这是一个本地实时变声工具：对着麦克风说话，声音会被实时换成你选的音色。",
                    "常用于游戏 / QQ / Discord 语音，全部在本机运行，不上传你的声音。",
                    "跟着下面几步走，两分钟就能开黑。",
                ],
            ),
            (
                "STEP 1 · 接线",
                "先把声音接对（最重要）",
                [
                    "① 本软件「设置」→ 输入设备 = 你的真实麦克风",
                    "② 本软件「设置」→ 输出设备 = CABLE Input",
                    "③ 游戏 / QQ 里的麦克风 = CABLE Output",
                    "还没有虚拟声卡？先在启动器点「安装虚拟声卡」。",
                ],
            ),
            (
                "STEP 2 · 开声",
                "三步开始变声",
                [
                    "① 在「首页」或「模型」页选择一个音色",
                    "② 在「设置」页确认输入 / 输出设备",
                    "③ 点底栏「开启变声」（首次加载约 20～40 秒）",
                    "想边变声边听自己：勾选「监听自己」，监听设备选真实耳机。",
                ],
            ),
            (
                "STEP 3 · 调声",
                "调出更像的声音",
                [
                    "· 音高 Pitch：男变女常试 +8～+12，女变男试 −8～−12。",
                    "· 共鸣 Formant：微调音色的明暗与厚度。",
                    "· 底栏可随时快速调节，并会按当前音色自动记住。",
                    "· 更多细调（降噪 / 声音效果）在设置页，每项旁都有「?」说明。",
                ],
            ),
            (
                "DONE · 加入我们",
                "加群 & 看完整说明",
                [
                    "遇到问题、想要更多音色？欢迎加入玩家 QQ 群一起玩。",
                    "获取方式：点下方按钮打开视频 → 一键三连 + 关注 UP 主 →",
                    "再私信 UP 主「加群」，即可拿到最新 QQ 群号。",
                    "完整图文教程见「说明」页，随时可以回看。",
                ],
            ),
        ]

        win = tk.Toplevel(self.root)
        win.title("新手引导")
        win.configure(bg=TM_BG)
        win.geometry("560x470")
        win.minsize(480, 420)
        win.transient(self.root)
        try:
            win.grab_set()
        except Exception:
            pass

        state = {"i": 0}

        def _close_done():
            self._mark_onboarding_done()
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _close_done)

        eyebrow = tk.Label(win, text="", font=mono_font(9), bg=TM_BG, fg=TM_META)
        eyebrow.pack(anchor="w", padx=24, pady=(20, 0))
        title = tk.Label(
            win,
            text="",
            font=title_font(17, "bold"),
            bg=TM_BG,
            fg=TM_INK,
            justify="left",
            anchor="w",
        )
        title.pack(anchor="w", padx=24, pady=(2, 8))

        body = tk.Frame(
            win, bg=TM_SURFACE, highlightthickness=1, highlightbackground=TM_HAIRLINE
        )
        body.pack(fill="both", expand=True, padx=24, pady=(0, 8))
        body_inner = tk.Frame(body, bg=TM_SURFACE)
        body_inner.pack(fill="both", expand=True, padx=18, pady=16)

        footer = tk.Frame(win, bg=TM_BG)
        footer.pack(fill="x", padx=24, pady=(4, 16))

        def _next():
            if state["i"] < len(steps) - 1:
                state["i"] += 1
                render()

        def _prev():
            if state["i"] > 0:
                state["i"] -= 1
                render()

        def _open_help():
            _close_done()
            self.show_page("help")

        def render():
            i = state["i"]
            eb, ttl, lines = steps[i]
            eyebrow.configure(text=tracked(eb, gap=" "))
            title.configure(text=ttl)
            for w in body_inner.winfo_children():
                w.destroy()
            for ln in lines:
                tk.Label(
                    body_inner,
                    text=ln,
                    font=sans_font(11),
                    bg=TM_SURFACE,
                    fg=TM_INK,
                    justify="left",
                    anchor="w",
                    wraplength=470,
                ).pack(anchor="w", pady=4, fill="x")
            for w in footer.winfo_children():
                w.destroy()
            is_final = i == len(steps) - 1
            tk.Label(
                footer,
                text=f"第 {i + 1} / {len(steps)} 步",
                font=mono_font(9),
                bg=TM_BG,
                fg=TM_META,
            ).pack(side="left")
            GhostButton(
                footer,
                "完成" if is_final else "跳过引导",
                command=_close_done,
                padx=12,
                pady=8,
            ).pack(side="left", padx=(12, 0))
            if is_final:
                PrimaryButton(
                    footer,
                    "打开视频 · 三连关注得 QQ 群",
                    command=self._open_community_link,
                    padx=16,
                    pady=8,
                ).pack(side="right")
                GhostButton(
                    footer, "查看使用说明", command=_open_help, padx=14, pady=8
                ).pack(side="right", padx=(0, 8))
                GhostButton(
                    footer, "上一步", command=_prev, padx=14, pady=8
                ).pack(side="right", padx=(0, 8))
            else:
                PrimaryButton(
                    footer, "下一步", command=_next, padx=22, pady=8
                ).pack(side="right")
                if i > 0:
                    GhostButton(
                        footer, "上一步", command=_prev, padx=14, pady=8
                    ).pack(side="right", padx=(0, 8))

        render()

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
        self._set_status_visual(
            "busy",
            f"启动中 · {m['name']}",
            "加载模型中，约 20–40 秒",
        )

        def work():
            err = ""
            try:
                # Ensure single healthy worker; wipe orphans from previous crash
                if not rt_client.is_worker_alive():
                    rt_client.start_worker_process(clean_orphans=True)
                st0 = rt_client.wait_worker_ready(timeout_s=100)
                if str(st0.get("state")) == "error" and st0.get("error"):
                    err = str(st0.get("error"))
                    self.root.after(0, lambda: self._on_vc_start_failed(err))
                    return
                try:
                    rt_client.stop_vc_remote(force=False, timeout_s=4.0)
                except Exception:
                    pass
                time.sleep(0.25)
                rt_client.start_vc_remote()
                st = rt_client.wait_vc_running(timeout_s=180)
                if str(st.get("state")) == "running":
                    self.root.after(0, lambda s=st: self._on_vc_started(m, s))
                    return
                err = str(st.get("error") or st.get("message") or "启动失败")
            except Exception as e:
                err = str(e)
            self.root.after(0, lambda: self._on_vc_start_failed(err))

        threading.Thread(target=work, daemon=True).start()

    def _on_vc_started(self, m: dict, st: dict) -> None:
        self._vc_starting = False
        self.vc_running = True
        self.btn_start.configure(text="停止变声", bg=TM_OK)
        delay = int(st.get("delay_ms") or 0)
        infer = int(st.get("infer_ms") or 0)
        self._set_status_visual(
            "live",
            f"变声中 · {m.get('name') or ''}",
            self._format_latency_line(delay, infer),
        )

    def _on_vc_start_failed(self, err: str) -> None:
        self._vc_starting = False
        self.vc_running = False
        self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
        self._set_status_visual("error", "启动失败", (err or "")[:40])
        msg = err or "未知错误"
        # Friendlier text for known engine errors
        low = msg.lower()
        if "jsondecode" in low or "expecting value" in low or "empty" in low:
            msg = (
                "引擎配置文件损坏或为空（常见于上次强制结束时正在写配置）。\n"
                "已可自动修复，请再点一次「开启变声」。\n\n"
                f"技术信息：{err}"
            )
        messagebox.showerror(
            "启动失败",
            msg
            + "\n\n仍不行时：设置里检查输入/输出设备，或「其他 → 强制结束变声引擎」后再试。",
        )

    def _stop_vc(self) -> None:
        self.btn_start.configure(text="停止中…", bg=TM_META)
        self._set_status_visual("busy", "正在停止…", "释放声卡中")

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
        self._set_status_visual("idle", "引擎待命", APP_PRODUCT_TAGLINE)

    def _tick_status(self) -> None:
        if getattr(self, "_closing", False):
            return
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
                    name = ""
                    if self.models:
                        name = self.models[self.model_idx].get("name") or ""
                    self._set_status_visual(
                        "live",
                        f"变声中 · {name}" if name else "变声中",
                        self._format_latency_line(delay, infer),
                    )
                elif state == "error":
                    err = str(st.get("error") or "error")
                    self.vc_running = False
                    self._vc_starting = False
                    self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
                    self._set_status_visual("error", "引擎错误", err[:48])
                elif state == "idle" and self.vc_running and not self._vc_starting:
                    # Worker stopped externally
                    self._on_vc_stopped()
        except Exception:
            pass
        if not getattr(self, "_closing", False):
            self.root.after(1000, self._tick_status)

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self) -> None:
        """Close UI quickly; use fast worker teardown (no multi-second polls)."""
        if getattr(self, "_closing", False):
            return
        self._closing = True

        # Stop timers / hotkeys first so nothing keeps the event loop busy
        try:
            self._global_hk.unregister_all()
        except Exception:
            pass
        for attr in (
            "_hot_job",
            "_voice_save_job",
            "_dock_hint_job",
            "_toast_job",
            "_resize_job",
            "_model_restart_job",
            "_carousel_job",
        ):
            job = getattr(self, attr, None)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
                setattr(self, attr, None)

        # Hide immediately so the user sees the window go away
        try:
            self.root.withdraw()
        except Exception:
            pass

        # Fast local writes (usually <50ms)
        try:
            self._persist_voice_params_to_model(immediate=True)
        except Exception:
            pass
        try:
            self.save_settings_silent()
            save_config(self.cfg)
        except Exception:
            pass

        # Worker stop/quit used to block 8s+8s on the UI thread — that felt like a hang.
        # Fast path: short soft wait + kill known PIDs + brief orphan scan.
        try:
            rt_client.shutdown_workers_for_exit(soft_wait_s=0.35, scan_timeout_s=1.2)
        except Exception:
            try:
                rt_client.kill_orphan_runtime_workers(
                    include_worker=True, scan_timeout_s=1.0
                )
            except Exception:
                pass

        try:
            self.root.destroy()
        except Exception:
            pass


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
