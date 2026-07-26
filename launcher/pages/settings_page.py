# -*- coding: utf-8 -*-
"""Settings page: devices, monitor, index, accel, perf presets, updates.

Split out of main_app (largest page). Uses MainApp state (self.cfg, self.root,
self.var_*, self._set_status_visual, self.refresh_models, …) present on the
composed instance.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from launcher.app_presets import perf_preset_name, perf_preset_values
from launcher.catalog import (
    bind_index_to_model_dir,
    clear_model_index,
    discover_index_files,
)
from launcher.config_store import save_config
from launcher.gpu_backend import apply_backend_env, detect_full, normalize_accel
from launcher.paths import MODELS_DIR, ROOT, index_search_roots
from launcher import realtime_client as rt_client
from launcher.theme import (
    APP_PRODUCT_TAGLINE,
    GUTTER,
    TM_ACCENT,
    TM_ACCENT_SOFT,
    TM_BG,
    TM_HELP,
    TM_INK,
    TM_INK_MUTED,
    TM_INSET,
    TM_META,
    TM_OK,
    TM_SURFACE,
    mono_font,
    px,
    sans_font,
)
from launcher.ui import GhostButton, HoverTip, SectionCard, SoftSlider
from launcher.ui.help_content import SETTING_TIPS


class SettingsPageMixin:
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
        # Fixed section index on top — one click jumps straight to a section
        idx_bar = tk.Frame(fr, bg=TM_BG)
        idx_bar.pack(fill="x", padx=GUTTER, pady=(8, 0))
        self._settings_sections: list = []
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
        self.var_input_dev = tk.StringVar(
            value=str(self.cfg.get("sg_input_device") or "")
        )
        self.var_output_dev = tk.StringVar(
            value=str(self.cfg.get("sg_output_device") or "")
        )
        self.var_monitor_dev = tk.StringVar(
            value=str(self.cfg.get("monitor_device") or "")
        )
        self.var_monitor_on = tk.BooleanVar(value=bool(self.cfg.get("monitor_enabled")))
        self.var_wasapi = tk.BooleanVar(value=bool(self.cfg.get("sg_wasapi_exclusive")))
        self.var_sr_type = tk.StringVar(
            value=str(self.cfg.get("sr_type") or "sr_model")
        )
        self.var_i_nr = tk.BooleanVar(value=bool(self.cfg.get("I_noise_reduce")))
        self.var_o_nr = tk.BooleanVar(value=bool(self.cfg.get("O_noise_reduce")))
        self.var_use_pv = tk.BooleanVar(value=bool(self.cfg.get("use_pv")))
        self.var_accel = tk.StringVar(
            value=str(self.cfg.get("accel_backend") or "auto")
        )

        def card(parent, title: str) -> tk.Frame:
            outer = SectionCard(parent, title=title, eyebrow="", pad=16)
            outer.pack(fill="x", expand=False, padx=GUTTER, pady=10)
            # Short name (before any parenthetical) feeds the top jump index
            self._settings_sections.append((title.split("（")[0], outer))
            return outer.body

        def help_mark(
            parent, tip: str, *, pack_side: str = "left"
        ) -> Optional[tk.Label]:
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
                bar_width=px(360),
                bar_height=px(36),
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
            wraplength=px(640),
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
            font=sans_font(10),
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
            HoverTip(
                self.lbl_pack_meta, _psum + "\n请勿混用 N 卡 / A 卡 / 50 系 Runtime。"
            )

        row = tk.Frame(left, bg=TM_SURFACE)
        row.pack(fill="x", pady=3)
        tk.Label(
            row,
            text="设备类型",
            width=14,
            anchor="w",
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            font=sans_font(10),
        ).pack(side="left")
        self.cmb_hostapi = ttk.Combobox(
            row,
            textvariable=self.var_hostapi,
            values=["MME"],
            state="readonly",
            font=sans_font(10),
            width=28,
        )
        self.cmb_hostapi.pack(side="left", fill="x", expand=True)
        self.cmb_hostapi.bind(
            "<<ComboboxSelected>>", lambda e: self._on_hostapi_change()
        )
        help_mark(row, SETTING_TIPS["hostapi"])

        row = tk.Frame(left, bg=TM_SURFACE)
        row.pack(fill="x", pady=3)
        tk.Label(
            row,
            text="输入设备",
            width=14,
            anchor="w",
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            font=sans_font(10),
        ).pack(side="left")
        self.cmb_input = ttk.Combobox(
            row,
            textvariable=self.var_input_dev,
            values=[],
            state="readonly",
            width=48,
            font=sans_font(10),
        )
        self.cmb_input.pack(side="left", fill="x", expand=True)
        help_mark(row, SETTING_TIPS["input"])

        # 麦克风增益：门限/电平表之前的输入前置增益，运行中可热调
        self.var_in_gain = tk.DoubleVar(value=float(self.cfg.get("in_gain_db") or 0.0))
        scale_row(
            left,
            "麦克风增益 dB",
            self.var_in_gain,
            -20,
            20,
            0.5,
            hot=True,
            tip_key="in_gain",
        )

        row = tk.Frame(left, bg=TM_SURFACE)
        row.pack(fill="x", pady=3)
        tk.Label(
            row,
            text="输出设备",
            width=14,
            anchor="w",
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            font=sans_font(10),
        ).pack(side="left")
        self.cmb_output = ttk.Combobox(
            row,
            textvariable=self.var_output_dev,
            values=[],
            state="readonly",
            width=48,
            font=sans_font(10),
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
            font=sans_font(10),
            width=48,
        )
        self.cmb_monitor.pack(side="left", fill="x", expand=True)
        self.cmb_monitor.bind(
            "<<ComboboxSelected>>", lambda e: self._on_monitor_device()
        )
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
            font=sans_font(10),
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
        # 虚拟声卡（VB-Cable）的选法在各设备项旁与「说明」页已覆盖；
        # 这个按钮专讲外置实体声卡的接法。原版实时面板入口在「其他」页。
        tk.Button(
            btnrow,
            text="实体声卡连接说明",
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
            wraplength=px(640),
        )
        voice_note.pack(fill="x", pady=(0, 6))
        self._settings_wrap_labels.append(voice_note)
        scale_row(
            right,
            "响应阈值",
            self.var_threhold,
            -60,
            0,
            1,
            hot=True,
            tip_key="threhold",
        )
        scale_row(
            right, "音高 Pitch", self.var_pitch, -24, 24, 1, hot=True, tip_key="pitch"
        )
        scale_row(
            right,
            "共鸣 Formant",
            self.var_formant,
            -2,
            2,
            0.05,
            hot=True,
            tip_key="formant",
        )
        scale_row(
            right,
            "Index Rate",
            self.var_index_rate,
            0,
            1,
            0.01,
            hot=True,
            tip_key="index_rate",
        )
        scale_row(right, "响度因子", self.var_rms, 0, 1, 0.01, hot=True, tip_key="rms")

        # .index 文件的绑定/切换在「模型」页管理；这里只保留内部变量
        # （Index Rate 滑杆仍在上方 — 它是参数，不是文件选择）。
        self.var_index_path = tk.StringVar(value="")
        tk.Label(
            right,
            text="检索库（.index 文件）的绑定与切换在「模型」页进行。",
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_HELP,
            anchor="w",
        ).pack(fill="x", pady=(4, 6))
        self._refresh_index_ui_for_model()

        f0f = tk.Frame(right, bg=TM_SURFACE)
        f0f.pack(fill="x", pady=3)
        tk.Label(
            f0f,
            text="音高算法",
            width=14,
            anchor="w",
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            font=sans_font(10),
        ).pack(side="left")
        cmb_f0 = ttk.Combobox(
            f0f,
            textvariable=self.var_f0,
            values=["fcpe", "rmvpe", "harvest", "crepe", "pm"],
            state="readonly",
            font=sans_font(10),
            width=12,
        )
        cmb_f0.pack(side="left")
        cmb_f0.bind("<<ComboboxSelected>>", lambda e: self._on_hot_param())
        help_mark(f0f, SETTING_TIPS["f0"])

        modef = tk.Frame(right, bg=TM_SURFACE)
        modef.pack(fill="x", pady=4)
        tk.Label(
            modef,
            text="模式",
            width=14,
            anchor="w",
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            font=sans_font(10),
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
            "用来检查麦是否正常、声卡连接对不对；听完记得切回「输出变声」。"
        )
        help_mark(modef, _mode_tip)
        HoverTip(rb_vc, "输出变声：把麦克风变成所选音色再输出（日常变声用这个）。")
        HoverTip(rb_im, "输入监听：不改变声音，只输出麦克风原声（测麦/测连接）。")

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
        scale_row(
            perf, "淡入淡出", self.var_crossfade, 0.01, 0.15, 0.01, tip_key="crossfade"
        )
        scale_row(
            perf, "额外推理时长", self.var_extra, 0.05, 5.0, 0.01, tip_key="extra"
        )
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
        # Shell (PyInstaller) has no numpy; dsp_fx must not hard-require it at import.
        # Fallback keeps settings UI up even if tools.dsp_fx is missing/broken.
        try:
            from tools.dsp_fx import EQ_LABELS, EQ_PRESET_LABELS, EQ_PRESETS
        except Exception:
            EQ_LABELS = ("60Hz", "250Hz", "1kHz", "4kHz", "8kHz")
            EQ_PRESETS = {
                "flat": [0.0, 0.0, 0.0, 0.0, 0.0],
                "vocal_front": [-2.0, 1.0, 3.0, 2.5, 1.0],
                "warm": [2.0, 1.5, 0.0, -1.0, -2.0],
                "bright": [-1.5, 0.0, 1.0, 3.0, 2.5],
                "de_nasal": [0.0, -3.5, -1.0, 1.5, 0.5],
                "thick": [3.0, 1.5, 0.0, -0.5, -1.5],
            }
            EQ_PRESET_LABELS = {
                "flat": "平直",
                "vocal_front": "人声前倾",
                "warm": "温暖饱满",
                "bright": "清晰明亮",
                "de_nasal": "消除鼻音",
                "thick": "低沉厚实",
            }

        self.var_fx_enabled = tk.BooleanVar(value=bool(self.cfg.get("fx_enabled")))
        self.var_fx_gate_en = tk.BooleanVar(
            value=bool(self.cfg.get("fx_gate_enabled", True))
        )
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
        self.var_fx_eq_en = tk.BooleanVar(
            value=bool(self.cfg.get("fx_eq_enabled", True))
        )
        self.var_fx_eq_preset = tk.StringVar(
            value=str(self.cfg.get("fx_eq_preset") or "flat")
        )
        gains0 = self.cfg.get("fx_eq_gains") or [0, 0, 0, 0, 0]
        if not isinstance(gains0, (list, tuple)):
            gains0 = [0, 0, 0, 0, 0]
        gains0 = list(gains0) + [0] * 5
        self.var_fx_eq_gains = [tk.DoubleVar(value=float(gains0[i])) for i in range(5)]
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
            font=sans_font(10, "bold"),
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
        scale_row(
            gbox,
            "门限 dB",
            self.var_fx_gate_thr,
            -80,
            -10,
            1,
            hot=True,
            tip_key="fx_gate_thr",
        )
        scale_row(
            gbox,
            "释放 ms",
            self.var_fx_gate_rel,
            5,
            300,
            1,
            hot=True,
            tip_key="fx_gate_rel",
        )
        scale_row(
            gbox,
            "保持 ms",
            self.var_fx_gate_hold,
            0,
            200,
            1,
            hot=True,
            tip_key="fx_gate_hold",
        )
        scale_row(
            gbox,
            "衰减 dB",
            self.var_fx_gate_range,
            6,
            60,
            1,
            hot=True,
            tip_key="fx_gate_range",
        )

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
        scale_row(
            cbox,
            "阈值 dB",
            self.var_fx_comp_thr,
            -40,
            0,
            1,
            hot=True,
            tip_key="fx_comp_thr",
        )
        scale_row(
            cbox,
            "比率",
            self.var_fx_comp_ratio,
            1,
            20,
            0.5,
            hot=True,
            tip_key="fx_comp_ratio",
        )
        scale_row(
            cbox,
            "启动 ms",
            self.var_fx_comp_att,
            0.5,
            50,
            0.5,
            hot=True,
            tip_key="fx_comp_att",
        )
        scale_row(
            cbox,
            "释放 ms",
            self.var_fx_comp_rel,
            10,
            500,
            1,
            hot=True,
            tip_key="fx_comp_rel",
        )
        scale_row(
            cbox,
            "增益 dB",
            self.var_fx_comp_mu,
            0,
            12,
            0.5,
            hot=True,
            tip_key="fx_comp_mu",
        )

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
            font=sans_font(10),
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
            fx,
            "输出增益 dB",
            self.var_fx_out_gain,
            -12,
            12,
            0.5,
            hot=True,
            tip_key="fx_out",
        )

        # --- 常规（关闭行为等） ---
        gen = card(wrap, "常规")
        self.var_close_action = tk.StringVar(
            value=str(self.cfg.get("close_action") or "ask")
        )
        close_row = tk.Frame(gen, bg=TM_SURFACE)
        close_row.pack(fill="x", pady=3)
        tk.Label(
            close_row,
            text="关闭主窗口时",
            width=14,
            anchor="w",
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            font=sans_font(10),
        ).pack(side="left")
        _close_labels = {"ask": "每次询问", "tray": "最小化到托盘", "exit": "直接退出"}
        _close_keys = {v: k for k, v in _close_labels.items()}
        self.cmb_close_action = ttk.Combobox(
            close_row,
            values=list(_close_labels.values()),
            state="readonly",
            font=sans_font(10),
            width=16,
        )
        self.cmb_close_action.set(
            _close_labels.get(str(self.var_close_action.get()), "每次询问")
        )

        def _on_close_action(_e=None):
            key = _close_keys.get(self.cmb_close_action.get(), "ask")
            self.var_close_action.set(key)
            self.cfg["close_action"] = key
            save_config(self.cfg)

        self.cmb_close_action.bind("<<ComboboxSelected>>", _on_close_action)
        self.cmb_close_action.pack(side="left")
        help_mark(
            close_row,
            "最小化到托盘：窗口藏到右下角托盘图标，变声继续后台运行。\n"
            "每次询问：点关闭时弹出选择（可勾选记住）。\n"
            "直接退出：关闭窗口即停止变声并退出软件。",
        )

        # --- Keyboard shortcuts ---
        self._build_hotkeys_settings_section(wrap, card)

        # --- Online update (demoted from its own page to a settings section) ---
        self._online_update_card_body = card(wrap, "在线更新")

        # No save button: every change is saved the moment it is made.
        tk.Label(
            wrap,
            text="调整会立即保存。音色与声音效果立即生效；设备与性能类改动需重新「开启变声」。",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_HELP,
            anchor="w",
        ).pack(fill="x", padx=28, pady=(4, 12))

        # Populate the top jump index now that all sections exist
        def _jump_to(outer=None):
            try:
                canvas.update_idletasks()
                total = max(int(wrap.winfo_height()), 1)
                canvas.yview_moveto(max(0, int(outer.winfo_y()) - 6) / total)
            except Exception:
                pass

        for short, outer in self._settings_sections:
            b = tk.Label(
                idx_bar,
                text=short,
                font=sans_font(9),
                bg=TM_INSET,
                fg=TM_INK_MUTED,
                padx=12,
                pady=5,
                cursor="hand2",
            )
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda _e, o=outer: _jump_to(o))

        # Long device names get clipped in the closed field — hovering shows
        # the full current value.
        for _cmb, _var in (
            (getattr(self, "cmb_input", None), self.var_input_dev),
            (getattr(self, "cmb_output", None), self.var_output_dev),
            (getattr(self, "cmb_monitor", None), self.var_monitor_dev),
        ):
            if _cmb is not None:
                self._attach_full_value_tip(_cmb, _var)

        # Device names are long ("Voicemeeter AUX Input (VB-Audio…)"): widen
        # each combobox's popdown list to the longest item before it opens.
        for _cmb in (
            getattr(self, "cmb_hostapi", None),
            getattr(self, "cmb_input", None),
            getattr(self, "cmb_output", None),
            getattr(self, "cmb_monitor", None),
            getattr(self, "cmb_index", None),
            getattr(self, "cmb_accel", None),
            getattr(self, "cmb_fx_preset", None),
        ):
            if _cmb is not None:
                _cmb.configure(postcommand=lambda c=_cmb: self._fit_combo_popdown(c))

        # Auto-save: any settings var change → debounced silent save
        def _autosave_later(*_a):
            if getattr(self, "_loading_voice", False):
                return
            job = getattr(self, "_settings_autosave_job", None)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
            self._settings_autosave_job = self.root.after(600, self._settings_autosave)

        for name in dir(self):
            if not name.startswith("var_"):
                continue
            v = getattr(self, name, None)
            items = v if isinstance(v, (list, tuple)) else [v]
            for one in items:
                if isinstance(one, tk.Variable):
                    try:
                        one.trace_add("write", _autosave_later)
                    except Exception:
                        pass

        # Wheel + width after children exist
        try:
            _bind_wheel_recursive(wrap)
        except Exception:
            pass
        fr.after(80, self._reflow_settings_page)
        return fr

    def _settings_autosave(self) -> None:
        self._settings_autosave_job = None
        self.save_settings_silent()

    @staticmethod
    def _attach_full_value_tip(cmb, var) -> None:
        """Hovering a combobox shows its full (possibly clipped) value."""
        tip = HoverTip(cmb, "")

        def _upd(*_a):
            try:
                tip.text = str(var.get() or "")
            except Exception:
                pass

        try:
            var.trace_add("write", _upd)
        except Exception:
            pass
        _upd()

    @staticmethod
    def _fit_combo_popdown(cmb) -> None:
        """Make the dropdown list wide enough for its longest entry."""
        try:
            values = cmb.cget("values") or ()
            longest = max((len(str(v)) for v in values), default=0)
            pd = cmb.tk.call("ttk::combobox::PopdownWindow", cmb)
            cmb.tk.call(f"{pd}.f.l", "configure", "-width", max(longest, 20))
        except Exception:
            pass

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
            if hasattr(self, "var_in_gain"):
                self.cfg["in_gain_db"] = float(self.var_in_gain.get())
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
                    lambda e=e: self._set_status_visual(
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
            if (
                var in ("nvidia", "nvidia50")
                and pref in ("auto", "cuda")
                and not info.get("has_cuda")
            ):
                line += "  · 未检出 CUDA，确认使用了对应显卡发行包 Runtime"
        except Exception:
            pass
        try:
            if hasattr(self, "lbl_accel_status"):
                self.lbl_accel_status.configure(text=line, fg=TM_INK_MUTED)
        except Exception:
            pass
        # Subtitle when idle — never clobber an engine-error badge with GPU text
        if not self.vc_running and not self._vc_starting:
            try:
                title_now = ""
                try:
                    title_now = str(self.lbl_online.cget("text") or "")
                except Exception:
                    title_now = ""
                if "错误" in title_now or "失败" in title_now:
                    pass  # keep real worker error subtitle
                else:
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
                self.root.after(0, lambda e=e: messagebox.showerror("检测失败", str(e)))

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
                in_gain_db=self.cfg.get("in_gain_db"),
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
        """Fill device lists + prewarm worker (引擎待命). No Runtime\\python.exe probe."""

        def work():
            try:
                from launcher.audio_devices import list_audio_devices_for_ui

                host = ""
                try:
                    host = str(self.var_hostapi.get() or "")
                except Exception:
                    host = str(self.cfg.get("sg_hostapi") or "")
                # Fast UI fill (no worker)
                st_local = list_audio_devices_for_ui(host or None)
                if st_local.get("input_devices") is not None:
                    self.root.after(0, lambda s=st_local: self._apply_device_status(s))
                # Engine standby prewarm (pythonw worker only)
                st = rt_client.ensure_worker_and_devices(timeout_s=100)
                if st.get("input_devices") is not None:
                    self.root.after(0, lambda s=st: self._apply_device_status(s))
                elif str(st.get("state")) == "error" and st.get("error"):
                    err = str(st.get("error") or "")[:48]
                    self.root.after(
                        0,
                        lambda e=err: self.lbl_online.configure(
                            text=f"引擎预热: {e}", fg=TM_META
                        ),
                    )
            except Exception as e:
                self.root.after(
                    0,
                    lambda e=e: self.lbl_online.configure(
                        text=f"设备枚举失败: {e}", fg=TM_META
                    ),
                )

        threading.Thread(target=work, daemon=True).start()
        self._set_status_visual("busy", "正在连接变声引擎…", "预热中，首次变声会更快")

    def _apply_perf_preset(self, key: str) -> None:
        """Map quality/latency presets (inspired by realtime VC chunk tradeoffs)."""
        block, crossfade, extra = perf_preset_values(key)
        try:
            self.var_block.set(block)
            self.var_crossfade.set(crossfade)
            self.var_extra.set(extra)
            self.cfg["block_time"] = block
            self.cfg["crossfade_length"] = crossfade
            self.cfg["extra_time"] = extra
            save_config(self.cfg)
        except Exception:
            pass
        name = perf_preset_name(key)
        self._set_status_visual(
            "idle",
            f"性能预设：{name}",
            "请重新「开启变声」后生效",
        )

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
        # 在线更新 now lives inside 设置 — badge the 设置 nav item instead
        btn = self.nav_btns.get("settings")
        if not btn:
            return
        try:
            if self._update_badge_on:
                btn.configure(text="设置·新")
            else:
                btn.configure(text="设置")
            if self._current_page == "settings":
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
                self.root.after(0, lambda e=e: messagebox.showerror("重载失败", str(e)))

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
                    if (
                        (not cur)
                        or (cur not in outs)
                        or self._is_virtual_monitor_name(cur)
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
