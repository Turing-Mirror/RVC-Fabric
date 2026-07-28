# -*- coding: utf-8 -*-
"""Consumer app (RVCMAX role: daily GUI).

Shell layout inspired by content-library chrome + stage focus.
Models: User_Data/models catalog first; engine assets only for hubert/rmvpe story.
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional
import tkinter as tk
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.app_presets import format_latency_line
from launcher.config_store import load_config, save_config, sync_realtime_gui_model
from launcher.pages import (
    ConsultMixin,
    DockVoiceMixin,
    HomePageMixin,
    HotkeysMixin,
    IndexPanelMixin,
    ModelsPageMixin,
    MonitorMixin,
    MorePageMixin,
    OnboardingMixin,
    PlazaPageMixin,
    ProfilesMixin,
    RealtimeControlMixin,
    SettingsPageMixin,
)
from launcher.tray import TrayController, tray_available
from launcher.voice_history import VoiceParamHistory
from launcher.hotkeys import GlobalHotkeyManager, merge_hotkeys
from launcher.paths import (
    APP_TITLE,
    USER_DATA,
    ensure_dirs,
    list_voice_models,
)
from launcher import realtime_client as rt_client
from launcher.theme import (
    APP_PRODUCT_TAGLINE,
    APP_WORDMARK,
    BOTTOM_HEIGHT,
    NAV_HEIGHT,
    DEFAULT_WIN_H,
    DEFAULT_WIN_W,
    MIN_WIN_H,
    MIN_WIN_W,
    PAD_X,
    TM_ACCENT,
    TM_BG,
    TM_HAIRLINE,
    TM_INK,
    TM_INSET,
    TM_META,
    TM_OK,
    TM_SURFACE,
    TM_WARN,
    mono_font,
    px,
    sans_font,
    set_scale_from_dpi,
    title_font,
)
from launcher.ui import (
    CoverCache,
    HoverTip,
    NavItem,
    ParamTile,
    PrimaryButton,
    StatusBadge,
)
from launcher.ui.help_page import HelpPage
from launcher.ui.store_page import StorePage
from launcher.win_util import (
    enable_dpi_awareness,
    focus_window_by_title,
    get_window_dpi,
    read_tail,
    realtime_gui_log_path,
    start_legacy_realtime_gui,
    start_webui,
)


class MainApp(
    HomePageMixin,
    ModelsPageMixin,
    PlazaPageMixin,
    MorePageMixin,
    OnboardingMixin,
    HotkeysMixin,
    MonitorMixin,
    RealtimeControlMixin,
    DockVoiceMixin,
    IndexPanelMixin,
    ProfilesMixin,
    ConsultMixin,
    SettingsPageMixin,
):
    def __init__(self) -> None:
        ensure_dirs()
        # Path / write perms / inuse sanitize (log only; UI may show later)
        try:
            from launcher.install_health import ensure_install_health

            self._install_health = ensure_install_health()
        except Exception:
            self._install_health = {}
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
        self._voice_hist = VoiceParamHistory(limit=40)
        self._dock_hint_job = None

        self.root = tk.Tk()
        # DPI awareness was declared in main() (before Tk); read the real DPI
        # so point fonts scale via `tk scaling` and pixel constants via px()
        self._ui_dpi = get_window_dpi(self.root.winfo_id())
        set_scale_from_dpi(self._ui_dpi)
        try:
            self.root.tk.call("tk", "scaling", self._ui_dpi / 72.0)
        except Exception:
            pass
        try:
            # Combobox popdown Listbox ignores widget font= — set it app-wide
            # (widget-level font on the entry part is set per Combobox)
            self.root.option_add("*TCombobox*Listbox.font", sans_font(10))
        except Exception:
            pass
        self.root.title(APP_TITLE)
        self.root.geometry(f"{px(DEFAULT_WIN_W)}x{px(DEFAULT_WIN_H)}")
        self.root.minsize(px(MIN_WIN_W), px(MIN_WIN_H))
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
        # System tray: persistent icon in the Windows notification area
        # (needs pystray/Pillow in the shell env; silently absent otherwise)
        self._tray = TrayController(self)
        self.root.after(500, self._tray.ensure_icon)
        # Do NOT bind <Unmap> → hide_to_tray. Windows minimizes the window when
        # the user clicks the taskbar button of the active app; auto-withdrawing
        # to the tray made it look like "click 变声器 on the taskbar → vanishes".
        # Tray hide is only via close_action / the close dialog.
        self.show_page("home")
        self._tick_status()
        self._setup_hotkeys()
        self.root.after(200, lambda: self._place_and_raise(force_size=False))
        self.root.after(800, lambda: self._place_and_raise(force_size=False))
        self.root.after(400, self._init_gpu_backend)
        self.root.after(600, self._bootstrap_devices_async)
        self.root.after(350, self._poll_global_hotkeys)
        self.root.after(900, self._tick_mic_level)
        self.root.after(2500, self._silent_check_updates)
        self.root.after(3000, self._silent_fetch_plaza)
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
            if not force_size and self._placed_once:
                # Already up and focused (user may even be dragging it) —
                # re-raising would interrupt them for no benefit.
                try:
                    if self.root.focus_displayof() is not None:
                        return
                except Exception:
                    pass
            self.root.update_idletasks()
            if force_size or not self._placed_once:
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
                if not self._restore_saved_geometry(sw, sh):
                    w, h = px(DEFAULT_WIN_W), px(DEFAULT_WIN_H)
                    # Leave margin on small laptops
                    w = min(w, max(px(MIN_WIN_W), sw - 48))
                    h = min(h, max(px(MIN_WIN_H), sh - 72))
                    x = max(0, (sw - w) // 2)
                    y = max(0, (sh - h) // 2)
                    self.root.geometry(f"{w}x{h}+{x}+{y}")
                self._placed_once = True
            # Show + raise ONCE, without forcing topmost — pinning the window
            # above everything on launch covered whatever the user was doing.
            self.root.deiconify()
            if force_size or not getattr(self, "_raised_once", False):
                self.root.lift()
                self.root.focus_force()
                self._raised_once = True
        except Exception:
            pass

    def _restore_saved_geometry(self, sw: int, sh: int) -> bool:
        """Reopen at the size/place the user left the window (if still sane)."""
        saved = str(self.cfg.get("win_geometry") or "").strip()
        if saved == "zoomed":
            try:
                self.root.state("zoomed")
                return True
            except Exception:
                return False
        m = re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", saved)
        if not m:
            return False
        w, h, x, y = (int(g) for g in m.groups())
        # Geometry saved by a pre-DPI-aware build (or at another monitor scale)
        # is in different physical units — rescale before the sanity checks
        saved_dpi = int(self.cfg.get("win_dpi") or 96)
        cur_dpi = int(getattr(self, "_ui_dpi", 96) or 96)
        if saved_dpi > 0 and saved_dpi != cur_dpi:
            k = cur_dpi / saved_dpi
            w, h, x, y = round(w * k), round(h * k), round(x * k), round(y * k)
        # Reject sizes/positions that no longer fit (monitor unplugged etc.)
        # Saved geometry is physical pixels, so compare against scaled minimums
        if w < px(MIN_WIN_W) or h < px(MIN_WIN_H) or w > sw + 64 or h > sh + 64:
            return False
        if x < -32 or y < -32 or x > sw - 160 or y > sh - 120:
            return False
        try:
            # Apply the RESCALED values — applying `saved` verbatim would
            # discard the DPI migration the checks above just validated
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            return True
        except Exception:
            return False

    def _remember_geometry(self) -> None:
        try:
            if self.root.state() == "zoomed":
                self.cfg["win_geometry"] = "zoomed"
            else:
                self.cfg["win_geometry"] = self.root.geometry()
            # Physical pixels are DPI-relative; record the scale they refer to
            self.cfg["win_dpi"] = int(getattr(self, "_ui_dpi", 96) or 96)
        except Exception:
            pass

    def _on_root_configure(self, event) -> None:
        if event.widget is not self.root:
            return
        # <Configure> also fires while the window is being MOVED. Rebuilding
        # widgets mid-drag makes Windows cancel the drag and snap the window
        # back, so only reflow when the size actually changed.
        size = (int(event.width), int(event.height))
        if size == getattr(self, "_last_root_size", None):
            return
        self._last_root_size = size
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

    def _build_chrome(self) -> None:
        # LyricsKara-style head: tracked wordmark + mono route | Schale segment nav
        top = tk.Frame(self.root, bg=TM_SURFACE, height=px(NAV_HEIGHT))
        top.pack(fill="x")
        top.pack_propagate(False)

        brand = tk.Frame(top, bg=TM_SURFACE)
        brand.pack(side="left", padx=PAD_X, pady=10)
        tk.Label(
            brand,
            text=APP_WORDMARK,
            font=title_font(14, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
        ).pack(anchor="w")

        # Segment control rail
        nav_rail = tk.Frame(top, bg=TM_INSET, padx=4, pady=4)
        nav_rail.pack(side="right", padx=PAD_X, pady=12)
        self.nav_btns: dict[str, NavItem] = {}
        for key, label in (
            ("home", "首页"),
            ("models", "模型"),
            ("plaza", "广场"),
            ("settings", "设置"),
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
        bottom = tk.Frame(self.root, bg=TM_SURFACE, height=px(BOTTOM_HEIGHT))
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)
        self._bottom_bar = bottom

        # Bottom dock zones (Schale card grouping + LyricsKara now-playing meta)
        # [ NOW PLAYING ] [ MODE ] [ PITCH | FORMANT | THRESH ] …… [ CTA | status ]

        dock_pad_y = 8  # vertical air inside fixed-height dock (must fit BOTTOM_HEIGHT)

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
        self.bottom_name = tk.Label(
            left_info,
            text="未选择模型",
            font=title_font(13, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        )
        self.bottom_name.pack(anchor="w")
        # tag + voice hint share one line (was 2 lines → got clipped)
        self.bottom_tag = tk.Label(
            left_info,
            text="请先导入音色到 User_Data/models",
            font=sans_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        )
        self.bottom_tag.pack(anchor="w", pady=(4, 0))
        self.bottom_voice_hint = tk.Label(
            left_info,
            text="参数随音色单独保存",
            font=sans_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
            width=36,  # fixed cols — value changes must not reflow dock
        )
        self.bottom_voice_hint.pack(anchor="w", pady=(2, 0))

        # --- Right: transport + status. Start button top 1/3, status lower 2/3.
        # (高级面板 entry lives in 设置 only.)
        right = tk.Frame(bottom, bg=TM_SURFACE)
        right.pack(side="right", padx=(10, PAD_X), pady=dock_pad_y, fill="y")
        right_col = tk.Frame(right, bg=TM_SURFACE)
        right_col.pack(fill="both", expand=True)
        right_col.columnconfigure(0, weight=1)
        right_col.rowconfigure(0, weight=1)
        right_col.rowconfigure(1, weight=2)
        self.btn_start = PrimaryButton(
            right_col, "开启变声", command=self.toggle_vc, padx=18, pady=8
        )
        self.btn_start.grid(row=0, column=0, sticky="nsew")
        self.status_badge = StatusBadge(right_col)
        self.status_badge.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
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
        seg = tk.Frame(mode_inner, bg=TM_INSET, padx=4, pady=4)
        seg.pack(anchor="w")
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
            "原声旁路（设置里的「输入监听」）：不改变声音，只输出麦克风原声，用来测麦/连接。",
        )

        # Mic level meter — the fastest "is it hearing me?" answer
        meter_row = tk.Frame(mode_inner, bg=TM_SURFACE)
        meter_row.pack(fill="x", pady=(10, 0))
        tk.Label(
            meter_row,
            text="麦克风",
            font=sans_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
        ).pack(side="left")
        self._mic_meter = tk.Canvas(
            meter_row,
            width=150,
            height=8,
            bg=TM_INSET,
            highlightthickness=0,
        )
        self._mic_meter.pack(side="left", padx=(8, 0), pady=1)
        HoverTip(
            meter_row,
            "变声中实时显示麦克风音量。\n"
            "条到不了竖线（响应阈值）时会被判定为安静、不变声；\n"
            "说话时条应明显越过竖线。",
        )
        self._draw_mic_meter(None)

        tiles = tk.Frame(mid, bg=TM_SURFACE)
        tiles.pack(side="left", fill="both", expand=True)
        self._dock_pitch = ParamTile(
            tiles,
            "音高",
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
            "共鸣",
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
        # 阈值滑块与「撤销/重做/默认」按钮列已从底栏移除 —— 阈值在设置页调，
        # 撤销/重做仍可用 Ctrl+Z / Ctrl+Y / Ctrl+0 快捷键。底栏只保留最常用的
        # 音高与共鸣。

        self._update_mode_buttons()
        self._sync_bottom()

    def _format_latency_line(self, delay_ms: int, infer_ms: int) -> str:
        return format_latency_line(delay_ms, infer_ms, APP_PRODUCT_TAGLINE)

    def _draw_mic_meter(self, db) -> None:
        """Level bar vs threshold marker. db=None → empty bar (engine idle)."""
        c = getattr(self, "_mic_meter", None)
        if c is None:
            return
        try:
            w = int(c.winfo_width()) or 150
            if w <= 1:
                w = 150
            h = 8
            c.delete("all")
            try:
                thr = int(self.var_threhold.get())
            except Exception:
                thr = int(self.cfg.get("threhold") or -60)

            def _x(v) -> int:
                return int((max(-60.0, min(0.0, float(v))) + 60.0) / 60.0 * w)

            if db is not None:
                x = _x(db)
                over = float(db) >= thr
                c.create_rectangle(
                    0,
                    0,
                    x,
                    h,
                    fill=TM_ACCENT if over else TM_HAIRLINE,
                    width=0,
                )
            tx = _x(thr)
            c.create_rectangle(max(tx - 1, 0), 0, tx + 1, h, fill=TM_WARN, width=0)
        except Exception:
            pass

    def _set_status_visual(self, mode: str, title: str, subtitle: str = "") -> None:
        """Update bottom-right status badge. mode: idle|busy|live|error."""
        try:
            self.status_badge.set_mode(mode, title, subtitle or APP_PRODUCT_TAGLINE)
        except Exception:
            pass

    def _build_pages(self) -> None:
        self._help_page = HelpPage(self, self.body)
        self.pages = {
            "home": self._page_home(),
            "models": self._page_models(),
            "plaza": self._page_plaza(),
            "settings": self._page_settings(),
            "help": self._help_page.frame,
            "more": self._page_more(),
        }
        # Built after settings — the online-update section lives inside it
        self._store_page = StorePage(self, self._online_update_card_body)
        # All pages stay gridded in one cell; show_page just raises one.
        # pack_forget→pack unmapped the body for a frame (white flash on
        # Windows — Tk has no double buffering); tkraise never unmaps.
        self.body.rowconfigure(0, weight=1)
        self.body.columnconfigure(0, weight=1)
        for fr in self.pages.values():
            fr.grid(row=0, column=0, sticky="nsew")

    def show_page(self, key: str) -> None:
        self._current_page = key
        for k, b in self.nav_btns.items():
            b.set_active(k == key)
        # Per-page hooks run BEFORE tkraise: render first, then lift the
        # finished page (raising early would flash stale content mid-rebuild)
        if key == "models":
            self._show_models_page()
        if key == "plaza":
            self._show_plaza_page()
        if key == "home":
            # Cancel any pending hidden-state reflow; render synchronously so
            # the raised page is already final (no post-switch jump)
            if getattr(self, "_carousel_job", None):
                try:
                    self.root.after_cancel(self._carousel_job)
                except Exception:
                    pass
                self._carousel_job = None
            self._render_carousel()
            self._update_home_current_label()
        if key == "settings":
            self._reflow_settings_page()
            # Wheel rebind replaces the old <Map> hook: pages stay mapped
            # under grid stacking, so <Map> would fire only once at startup
            # and miss widgets StorePage rebuilds at runtime
            cb = getattr(self, "_settings_bind_wheel", None)
            if cb:
                self.root.after_idle(cb)
        if key == "help":
            try:
                self._help_page.on_show()
            except Exception:
                pass
        self.pages[key].tkraise()

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
                self._persist_voice_params_to_model(self.models[prev], immediate=True)
            except Exception:
                pass
        self.model_idx = idx
        m = self.models[self.model_idx]
        # Persist so realtime / next launch use the same model
        self.cfg["last_model"] = m["file"]
        self.cfg["last_model_name"] = m["name"]
        self.cfg["last_model_path"] = m.get("path") or ""
        # Most-recently-used order for the home page (front = latest)
        key = m.get("path") or ((m.get("dir") or "") + "|" + (m.get("name") or ""))
        recents = [k for k in (self.cfg.get("recent_models") or []) if k != key]
        recents.insert(0, key)
        self.cfg["recent_models"] = recents[:12]
        # Load this voice's pitch/formant/… then overlay its active profile
        # (voice + FX + perf). Models without a bound profile are untouched.
        self._apply_model_voice_params(m, push_remote=False)
        try:
            self._apply_active_profile()
        except Exception:
            pass
        self._voice_hist.clear()
        save_config(self.cfg)
        # Index UI / var_index_path MUST be refreshed BEFORE engine sync.
        # Otherwise the previous voice's .index stays in the UI var and is
        # written into configs/inuse (and shows as「使用中」for the new voice).
        self._refresh_index_ui_for_model(m)
        self._sync_model_to_realtime_gui(m)
        self._sync_bottom()
        self._update_home_current_label()
        if self._current_page == "home":
            self._render_carousel()
        elif self._current_page == "models":
            # Selecting keeps the page scroll position (no jump to top)
            self.refresh_models(keep_scroll=True)
            # refresh_models rebuilds self.models — re-bind index from the
            # fresh entry so the panel cannot keep a stale path.
            if self.models:
                m = self.models[self.model_idx]
                self._refresh_index_ui_for_model(m)
        if feedback or prev != idx:
            self._show_switch_toast(m["name"])
        # Model weight loads only at stream start — switching voice while live
        # ALWAYS auto-restarts the stream (product promise: 运行中切换立即生效).
        # No config gate: a stale/off toggle used to leave the old voice
        # playing after a switch, which read as "switching does nothing".
        if prev != idx and (self.vc_running or self._vc_starting):
            self._restart_vc_for_new_model()

    def _sync_model_to_realtime_gui(self, m: Optional[dict] = None) -> None:
        """Write current model + full settings into engine config.json."""
        if m is None:
            if not self.models:
                return
            m = self.models[self.model_idx]
        pth = m.get("path") or ""
        if not pth:
            return
        # Prefer the *model's* bound index over the UI var. The var can still
        # hold the previous voice after a switch if refresh order slips.
        idx_path = str(m.get("index") or "").strip()
        if not idx_path:
            try:
                if hasattr(self, "var_index_path"):
                    idx_path = str(self.var_index_path.get() or "").strip()
            except Exception:
                idx_path = ""
        if idx_path and not Path(idx_path).is_file():
            idx_path = ""
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
        # Re-read from disk when possible so a previous voice's path never
        # sticks on the in-memory catalog entry.
        idx = ""
        if m.get("source") == "user_data" and m.get("dir"):
            try:
                from launcher.catalog import get_model_active_index

                idx = get_model_active_index(Path(m["dir"]))
            except Exception:
                idx = ""
        if not idx:
            idx = str(m.get("index") or "").strip()
        if idx and not Path(idx).is_file():
            idx = ""
        m["index"] = idx
        self.var_index_path.set(idx)
        self._update_index_hint()
        try:
            self._refresh_index_combobox_values()
        except Exception:
            pass
        try:
            self.refresh_index_panel_ui()
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

    def open_help(self) -> None:
        """Open dedicated in-app 说明 page."""
        self.show_page("help")

    def _show_cable_help(self) -> None:
        # 虚拟声卡（VB-Cable）的选法在设置页各设备项旁与「说明」页已覆盖，
        # 这里只讲外置实体声卡（USB 直播声卡 / 调音台）怎么接。
        messagebox.showinfo(
            "实体声卡连接",
            "虚拟声卡（VB-Cable）怎么选设备，本页各设备项旁已有说明；\n"
            "这里讲外置实体声卡（USB 直播声卡 / 调音台）怎么接。\n\n"
            "【麦克风走实体声卡】\n"
            "· 输入设备 = 实体声卡的录音设备（名字带声卡型号）\n"
            "· 输出设备 = 仍选 CABLE Input（对面听到变声仍靠虚拟声卡）\n"
            "· 监听：耳机插在声卡上 → 监听设备选实体声卡的播放\n\n"
            "【声卡带「内录 / 立体声混音」通道】\n"
            "· 也可不用 CABLE：输出设备 = 实体声卡的播放，\n"
            "  游戏 / QQ 麦克风 = 声卡的内录通道（叫法以声卡说明书为准）\n\n"
            "【注意】\n"
            "· 先关掉声卡驱动自带的降噪 / 混响 / 变声，避免和本软件叠加\n"
            "· 列表里没设备：点「重载设备列表」或重启软件\n\n"
            "虚拟声卡的完整连接说明见顶部导航「说明」页。",
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

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _ask_close_action(self) -> Optional[str]:
        """点 X 时询问：最小化到托盘还是退出。返回 "tray" / "exit" / None(取消)。"""
        from launcher.theme import TM_BG as _BG, TM_INK as _INK, TM_META as _META
        from launcher.theme import TM_SURFACE as _SURF
        from launcher.theme import sans_font as _sans, title_font as _title
        from launcher.ui import GhostButton, PrimaryButton, center_over

        win = tk.Toplevel(self.root)
        win.title("关闭 RVC Fabric")
        win.configure(bg=_BG)
        win.transient(self.root)
        win.resizable(False, False)
        win.grab_set()
        result: list = [None]

        body = tk.Frame(win, bg=_BG, padx=22, pady=16)
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text="要如何关闭？",
            font=_title(13, "bold"),
            bg=_BG,
            fg=_INK,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            body,
            text="最小化到托盘后变声继续在后台运行，右下角图标可随时恢复。",
            font=_sans(9),
            bg=_BG,
            fg=_META,
            anchor="w",
            wraplength=px(320),
            justify="left",
        ).pack(fill="x", pady=(4, 10))

        var_choice = tk.StringVar(value="tray")
        for val, label in (
            ("tray", "最小化到托盘（后台继续变声）"),
            ("exit", "直接关闭软件"),
        ):
            tk.Radiobutton(
                body,
                text=label,
                value=val,
                variable=var_choice,
                font=_sans(10),
                bg=_BG,
                fg=_INK,
                activebackground=_BG,
                selectcolor=_SURF,
                anchor="w",
            ).pack(fill="x", pady=1)

        var_remember = tk.BooleanVar(value=False)
        tk.Checkbutton(
            body,
            text="记住我的选择，下次不再询问（可在设置里更改）",
            variable=var_remember,
            font=_sans(9),
            bg=_BG,
            fg=_META,
            activebackground=_BG,
            selectcolor=_SURF,
            anchor="w",
        ).pack(fill="x", pady=(8, 10))

        def _done(ok: bool) -> None:
            if ok:
                result[0] = str(var_choice.get() or "tray")
                if var_remember.get():
                    self.cfg["close_action"] = result[0]
                    save_config(self.cfg)
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        row = tk.Frame(body, bg=_BG)
        row.pack(fill="x")
        GhostButton(row, "取消", command=lambda: _done(False), padx=14, pady=7).pack(
            side="right"
        )
        PrimaryButton(row, "确定", command=lambda: _done(True), padx=18, pady=7).pack(
            side="right", padx=(0, 8)
        )
        win.protocol("WM_DELETE_WINDOW", lambda: _done(False))
        center_over(win, self.root)
        self.root.wait_window(win)
        return result[0]

    def _on_close(self, force_exit: bool = False) -> None:
        """Close UI quickly; use fast worker teardown (no multi-second polls)."""
        if getattr(self, "_closing", False):
            return
        if not force_exit:
            action = str(self.cfg.get("close_action") or "ask")
            if action == "ask" and tray_available():
                picked = self._ask_close_action()
                if picked is None:
                    return
                action = picked
            if action == "tray" and tray_available():
                self._tray.hide_to_tray()
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
            "_plaza_job",
        ):
            job = getattr(self, attr, None)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
                setattr(self, attr, None)

        # Remember size/place BEFORE hiding — next launch reopens here
        self._remember_geometry()
        try:
            self._tray.stop()
        except Exception:
            pass

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
    # Must run before tk.Tk(): neither shell exe nor Runtime pythonw carries
    # a dpiAware manifest, so scaled displays bitmap-stretch us otherwise
    dpi_level = enable_dpi_awareness()
    os.chdir(ROOT)
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except Exception:
        pass
    log = ROOT / "TEMP" / "gui_alive.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(
            f"main_app main() enter dpi_awareness={dpi_level}\n", encoding="utf-8"
        )
    except Exception:
        pass
    app = MainApp()
    try:
        log.write_text(
            "main_app window up geometry="
            + app.root.geometry()
            + f" dpi={getattr(app, '_ui_dpi', '?')} awareness={dpi_level}\n",
            encoding="utf-8",
        )
    except Exception:
        pass
    app.run()


if __name__ == "__main__":
    main()
