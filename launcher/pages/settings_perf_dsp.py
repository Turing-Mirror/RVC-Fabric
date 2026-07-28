# -*- coding: utf-8 -*-
"""Settings: performance presets + post-RVC DSP (gate / compressor / EQ)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from launcher.app_presets import perf_preset_name, perf_preset_values
from launcher.config_store import save_config
from launcher.pages.settings_ui import SettingsUiKit
from launcher.theme import TM_HELP, TM_INK_MUTED, TM_SURFACE, sans_font
from launcher.ui import GhostButton
from launcher.ui.help_content import SETTING_TIPS


class SettingsPerfDspMixin:
    def _build_settings_perf_section(self, kit: SettingsUiKit) -> None:
        # Performance
        perf = kit.card( "性能设置（改后需重新「开启变声」）")
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
        kit.help_mark(
            preset_row,
            "一键设置采样长度/淡入淡出/额外推理时长。"
            "低延迟更跟嘴、对机器要求高；稳定更扛卡顿、延迟更高。改后需重新开启变声。",
        )
        kit.scale_row(perf, "采样长度", self.var_block, 0.02, 1.5, 0.01, tip_key="block")
        kit.scale_row(
            perf, "淡入淡出", self.var_crossfade, 0.01, 0.15, 0.01, tip_key="crossfade"
        )
        kit.scale_row(
            perf, "额外推理时长", self.var_extra, 0.05, 5.0, 0.01, tip_key="extra"
        )
        kit.scale_row(perf, "harvest进程数", self.var_n_cpu, 1, 8, 1, tip_key="n_cpu")
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
        kit.help_mark(nrf, SETTING_TIPS["i_nr"])
        tk.Checkbutton(
            nrf,
            text="输出降噪",
            variable=self.var_o_nr,
            bg=TM_SURFACE,
            command=self._on_hot_param,
            font=sans_font(9),
        ).pack(side="left", padx=(8, 0))
        kit.help_mark(nrf, SETTING_TIPS["o_nr"])
        tk.Checkbutton(
            nrf,
            text="相位声码器",
            variable=self.var_use_pv,
            bg=TM_SURFACE,
            command=self._on_hot_param,
            font=sans_font(9),
        ).pack(side="left", padx=(8, 0))
        kit.help_mark(nrf, SETTING_TIPS["use_pv"])


    def _build_settings_dsp_section(self, kit: SettingsUiKit) -> None:
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

        fx = kit.card( "声音效果（变声后 · 可选）")
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
        kit.help_mark(fx_en_row, SETTING_TIPS["fx_en"])

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
        kit.help_mark(gate_row, SETTING_TIPS["fx_gate"])
        kit.scale_row(
            gbox,
            "门限 dB",
            self.var_fx_gate_thr,
            -80,
            -10,
            1,
            hot=True,
            tip_key="fx_gate_thr",
        )
        kit.scale_row(
            gbox,
            "释放 ms",
            self.var_fx_gate_rel,
            5,
            300,
            1,
            hot=True,
            tip_key="fx_gate_rel",
        )
        kit.scale_row(
            gbox,
            "保持 ms",
            self.var_fx_gate_hold,
            0,
            200,
            1,
            hot=True,
            tip_key="fx_gate_hold",
        )
        kit.scale_row(
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
        kit.help_mark(comp_row, SETTING_TIPS["fx_comp"])
        kit.scale_row(
            cbox,
            "阈值 dB",
            self.var_fx_comp_thr,
            -40,
            0,
            1,
            hot=True,
            tip_key="fx_comp_thr",
        )
        kit.scale_row(
            cbox,
            "比率",
            self.var_fx_comp_ratio,
            1,
            20,
            0.5,
            hot=True,
            tip_key="fx_comp_ratio",
        )
        kit.scale_row(
            cbox,
            "启动 ms",
            self.var_fx_comp_att,
            0.5,
            50,
            0.5,
            hot=True,
            tip_key="fx_comp_att",
        )
        kit.scale_row(
            cbox,
            "释放 ms",
            self.var_fx_comp_rel,
            10,
            500,
            1,
            hot=True,
            tip_key="fx_comp_rel",
        )
        kit.scale_row(
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
        kit.help_mark(erow, SETTING_TIPS["fx_eq"])
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
            kit.scale_row(
                ebox,
                name,
                self.var_fx_eq_gains[i],
                -12,
                12,
                0.5,
                hot=True,
                tip_key=eq_tip_keys[i] if i < len(eq_tip_keys) else "",
            )

        kit.scale_row(
            fx,
            "输出增益 dB",
            self.var_fx_out_gain,
            -12,
            12,
            0.5,
            hot=True,
            tip_key="fx_out",
        )


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


