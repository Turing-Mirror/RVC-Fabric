# -*- coding: utf-8 -*-
"""Settings: devices & audio section + list / reload / prewarm handlers."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from launcher import realtime_client as rt_client
from launcher.config_store import save_config
from launcher.pages.settings_ui import SettingsUiKit
from launcher.theme import (
    APP_PRODUCT_TAGLINE,
    TM_ACCENT,
    TM_HELP,
    TM_INK,
    TM_INK_MUTED,
    TM_INSET,
    TM_META,
    TM_SURFACE,
    px,
    sans_font,
)
from launcher.ui import HoverTip
from launcher.ui.help_content import SETTING_TIPS


class SettingsDevicesMixin:
    def _build_settings_devices_section(self, kit: SettingsUiKit) -> None:
        # Device card
        left = kit.card( "设备与音频")
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
        kit.help_mark(row, SETTING_TIPS["accel"])
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
        kit.help_mark(row, SETTING_TIPS["hostapi"])

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
        kit.help_mark(row, SETTING_TIPS["input"])

        # 麦克风增益：门限/电平表之前的输入前置增益，运行中可热调
        self.var_in_gain = tk.DoubleVar(value=float(self.cfg.get("in_gain_db") or 0.0))
        kit.scale_row(
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
        kit.help_mark(row, SETTING_TIPS["output"])

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
        kit.help_mark(
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
            bg=TM_INSET,  # not TM_BG: glass chromakey must never paint controls
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
            bg=TM_INSET,
            fg=TM_INK_MUTED,
            relief="flat",
            cursor="hand2",
            command=self._show_cable_help,
            bd=0,
            padx=10,
            pady=4,
        ).pack(side="left")


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
                # Wait for worker to ack list_devices (review #26) — fixed 0.5s
                # sleep often showed a stale device list.
                seq = rt_client.send_command(
                    "list_devices", sg_hostapi=host, wait_seq=True, timeout_s=15
                )
                st = {}
                deadline = time.time() + 15.0
                while time.time() < deadline:
                    st = rt_client.poll_status()
                    if int(st.get("last_cmd_seq") or 0) >= int(seq or 0):
                        if st.get("input_devices") is not None or st.get("hostapis"):
                            break
                    if not rt_client.is_worker_alive():
                        break
                    time.sleep(0.1)
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

