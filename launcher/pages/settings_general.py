# -*- coding: utf-8 -*-
"""Settings: general / close-window behaviour section."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from launcher.config_store import save_config
from launcher.pages.settings_ui import SettingsUiKit
from launcher.theme import TM_INK_MUTED, TM_SURFACE, sans_font


class SettingsGeneralMixin:
    def _build_settings_general_section(self, kit: SettingsUiKit) -> None:
        # --- 常规（关闭行为等） ---
        gen = kit.card("常规")
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
        kit.help_mark(
            close_row,
            "点标题栏 X、Alt+F4、或系统菜单「关闭」时的行为：\n"
            "· 每次询问：弹出「到托盘 / 直接关闭」（可勾选记住）\n"
            "· 最小化到托盘：不再询问，直接藏到右下角图标（变声继续）\n"
            "· 直接退出：不再询问，停止变声并退出\n"
            "托盘图标从软件启动后一直显示，直到真正退出。\n"
            "若从未出现询问框：请确认本项是否被设成了「最小化到托盘」。",
        )
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
