# -*- coding: utf-8 -*-
"""Settings page scaffold: layout, vars, autosave, hot-param push.

Section UIs live in focused mixins (devices / voice / perf+dsp / general /
wallpaper / hotkeys / updates / accel / index). This module owns the scroll
shell and the shared save/hot-param path so public method names stay stable.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from launcher import realtime_client as rt_client
from launcher.config_store import save_config
from launcher.gpu_backend import normalize_accel
from launcher.pages.settings_ui import SettingsUiKit
from launcher.theme import (
    GUTTER,
    TM_BG,
    TM_HELP,
    TM_INSET,
    TM_INK_MUTED,
    TM_SURFACE,
    sans_font,
)
from launcher.ui import HoverTip


class SettingsPageMixin:
    def _page_settings(self) -> tk.Frame:
        fr = tk.Frame(self.body, bg=TM_BG)
        idx_bar = tk.Frame(fr, bg=TM_BG)
        idx_bar.pack(fill="x", padx=GUTTER, pady=(8, 0))
        self._settings_sections: list = []
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
            if getattr(self, "_layout_is_frozen", None) and self._layout_is_frozen():
                return
            if getattr(self, "schedule_scrollregion", None):
                self.schedule_scrollregion(canvas)

        def _on_canvas_width(event) -> None:
            if getattr(self, "_layout_is_frozen", None) and self._layout_is_frozen():
                return
            if event.width <= 1:
                return
            try:
                canvas.itemconfigure(win_id, width=int(event.width))
            except Exception:
                pass

        wrap.bind("<Configure>", _sync_scroll)
        canvas.bind("<Configure>", _on_canvas_width)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            # Suppress TCombobox class binding: wheel over combobox must not
            # mutate selection / kill the engine (accel) (review #15).
            return "break"

        def _bind_wheel_recursive(widget) -> None:
            widget.bind("<MouseWheel>", _on_mousewheel)
            for ch in widget.winfo_children():
                _bind_wheel_recursive(ch)

        canvas.bind("<MouseWheel>", _on_mousewheel)
        wrap.bind("<MouseWheel>", _on_mousewheel)
        self._settings_bind_wheel = lambda: _bind_wheel_recursive(wrap)
        _bind_wheel_recursive(wrap)

        self._init_settings_page_vars()
        kit = SettingsUiKit(self, wrap)

        self._build_settings_devices_section(kit)
        self._build_settings_voice_section(kit)
        self._build_settings_perf_section(kit)
        self._build_settings_dsp_section(kit)
        self._build_wallpaper_settings_section(wrap, kit.card)
        self._build_settings_general_section(kit)
        self._build_hotkeys_settings_section(wrap, kit.card)
        self._online_update_card_body = kit.card("在线更新")

        tk.Label(
            wrap,
            text="调整会立即保存。音色与声音效果立即生效；设备与性能类改动需重新「开启变声」。",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_HELP,
            anchor="w",
        ).pack(fill="x", padx=28, pady=(4, 12))

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

        for _cmb, _var in (
            (getattr(self, "cmb_input", None), self.var_input_dev),
            (getattr(self, "cmb_output", None), self.var_output_dev),
            (getattr(self, "cmb_monitor", None), self.var_monitor_dev),
        ):
            if _cmb is not None:
                self._attach_full_value_tip(_cmb, _var)

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

        try:
            _bind_wheel_recursive(wrap)
        except Exception:
            pass
        fr.after(80, self._reflow_settings_page)
        return fr

    def _init_settings_page_vars(self) -> None:
        """Tk vars owned by the settings page (shared voice vars already exist)."""
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

    def _reflow_settings_page(self) -> None:
        """Keep settings cards/sliders matching window width (fix maximize empty right)."""
        canvas = getattr(self, "_settings_canvas", None)
        wrap = getattr(self, "_settings_wrap", None)
        win_id = getattr(self, "_settings_win_id", None)
        if not canvas or not wrap or win_id is None:
            return
        try:
            # Pages stay mapped under grid stacking, so the width is always
            # current — no update_idletasks needed. Same width = same layout.
            w = max(int(canvas.winfo_width()), 400)
            if w == getattr(self, "_settings_reflow_w", None):
                return
            canvas.itemconfigure(win_id, width=w)
            # Help / intro labels wrap to card width
            inner = max(w - 80, 280)
            for lbl in getattr(self, "_settings_wrap_labels", []) or []:
                try:
                    lbl.configure(wraplength=inner)
                except Exception:
                    pass
            if getattr(self, "schedule_scrollregion", None):
                self.schedule_scrollregion(canvas)
            else:
                canvas.configure(scrollregion=canvas.bbox("all"))
            self._settings_reflow_w = w
        except Exception:
            pass

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
