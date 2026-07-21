# -*- coding: utf-8 -*-
"""Self-monitor (listen-to-self) handlers split out of main_app.

Pure device heuristics live in launcher.audio_devices; this mixin only owns
Tk-facing validation, hint labels, and hot-param push for monitor state.
"""

from __future__ import annotations

from tkinter import messagebox

from launcher.audio_devices import is_virtual_monitor_name, prefer_monitor_device
from launcher.config_store import save_config
from launcher.theme import TM_HELP, TM_OK, TM_WARN


class MonitorMixin:
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
