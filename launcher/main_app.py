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
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.catalog import get_model_voice_params, save_model_voice_params
from launcher.app_presets import format_latency_line
from launcher.audio_devices import is_virtual_monitor_name, prefer_monitor_device
from launcher.config_store import load_config, save_config, sync_realtime_gui_model
from launcher.pages import (
    HomePageMixin,
    ModelsPageMixin,
    MorePageMixin,
    ProfilesMixin,
    SettingsPageMixin,
)
from launcher.voice_history import VoiceParamHistory
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
    USER_DATA,
    ensure_dirs,
    list_voice_models,
)
from launcher import realtime_client as rt_client
from launcher.theme import (
    APP_PRODUCT_TAGLINE,
    APP_ROUTE,
    APP_WORDMARK,
    BOTTOM_HEIGHT,
    NAV_HEIGHT,
    DEFAULT_WIN_H,
    DEFAULT_WIN_W,
    MIN_WIN_H,
    MIN_WIN_W,
    PAD_X,
    TM_ACCENT,
    TM_ACCENT_INK,
    TM_BG,
    TM_HAIRLINE,
    TM_HELP,
    TM_INK,
    TM_INK_MUTED,
    TM_INSET,
    TM_META,
    TM_OK,
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
    NavItem,
    ParamTile,
    PrimaryButton,
    StatusBadge,
)
from launcher.ui.help_page import HelpPage
from launcher.ui.store_page import StorePage
from launcher.win_util import (
    focus_window_by_title,
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


class MainApp(
    HomePageMixin, ModelsPageMixin, MorePageMixin, ProfilesMixin, SettingsPageMixin
):
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
        self._voice_hist = VoiceParamHistory(limit=40)
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
        return format_latency_line(delay_ms, infer_ms, APP_PRODUCT_TAGLINE)

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
        # Load this voice's pitch/formant/… then overlay its active profile
        # (voice + FX + perf). Models without a bound profile are untouched.
        self._apply_model_voice_params(m, push_remote=False)
        try:
            self._apply_active_profile()
        except Exception:
            pass
        self._voice_hist.clear()
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
        self._voice_hist.push(self._voice_snapshot())

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
        prev = self._voice_hist.undo(self._voice_snapshot())
        if prev is None:
            self._set_status_visual(
                "live" if self.vc_running else "idle",
                "无可撤销",
                "先调整音高/共鸣/阈值",
            )
            return
        self._apply_voice_snapshot(prev)
        self._set_status_visual(
            "live" if self.vc_running else "idle",
            "已撤销",
            f"剩余 {self._voice_hist.undo_len} 步",
        )

    def redo_voice_params(self) -> None:
        nxt = self._voice_hist.redo(self._voice_snapshot())
        if nxt is None:
            self._set_status_visual(
                "live" if self.vc_running else "idle",
                "无可重做",
                "",
            )
            return
        self._apply_voice_snapshot(nxt)
        self._set_status_visual(
            "live" if self.vc_running else "idle",
            "已重做",
            f"还可重做 {self._voice_hist.redo_len} 步",
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
        return is_virtual_monitor_name(name)

    def _prefer_monitor_device(self, outs: list, current: str = "") -> str:
        try:
            main_out = str(self.var_output_dev.get() or "")
        except Exception:
            main_out = str(self.cfg.get("sg_output_device") or "")
        return prefer_monitor_device(outs, current, main_out)

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
