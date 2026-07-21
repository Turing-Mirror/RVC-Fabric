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
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.app_presets import format_latency_line
from launcher.config_store import load_config, save_config, sync_realtime_gui_model
from launcher.pages import (
    DockVoiceMixin,
    HomePageMixin,
    HotkeysMixin,
    ModelsPageMixin,
    MonitorMixin,
    MorePageMixin,
    OnboardingMixin,
    ProfilesMixin,
    RealtimeControlMixin,
    SettingsPageMixin,
)
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
    mono_font,
    sans_font,
    title_font,
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


class MainApp(
    HomePageMixin,
    ModelsPageMixin,
    MorePageMixin,
    OnboardingMixin,
    HotkeysMixin,
    MonitorMixin,
    RealtimeControlMixin,
    DockVoiceMixin,
    ProfilesMixin,
    SettingsPageMixin,
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
            "原声旁路（设置里的「输入监听」）：不改变声音，只输出麦克风原声，用来测麦/接线。",
        )

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
        GhostButton(
            hist_in, "撤销", command=self.undo_voice_params, padx=10, pady=4
        ).pack(fill="x", pady=(0, 4))
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
