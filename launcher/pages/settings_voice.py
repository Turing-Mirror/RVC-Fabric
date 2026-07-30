# -*- coding: utf-8 -*-
"""Settings: per-voice pitch / formant / index rate / f0 / mode section."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from launcher.pages.settings_ui import SettingsUiKit
from launcher.theme import TM_HELP, TM_INK_MUTED, TM_SURFACE, px, sans_font
from launcher.ui import HoverTip
from launcher.ui.help_content import SETTING_TIPS


class SettingsVoiceParamsMixin:
    def _build_settings_voice_section(self, kit: SettingsUiKit) -> None:
        # Voice params (also on bottom dock; saved per model under User_Data/models)
        right = kit.card("变声参数（运行中可热更新 · 按音色保存）")
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
        kit.scale_row(
            right,
            "响应阈值",
            self.var_threhold,
            -60,
            0,
            1,
            hot=True,
            tip_key="threhold",
        )
        kit.scale_row(
            right, "音高 Pitch", self.var_pitch, -24, 24, 1, hot=True, tip_key="pitch"
        )
        kit.scale_row(
            right,
            "共鸣 Formant",
            self.var_formant,
            -2,
            2,
            0.05,
            hot=True,
            tip_key="formant",
        )
        kit.scale_row(
            right,
            "Index Rate",
            self.var_index_rate,
            0,
            1,
            0.01,
            hot=True,
            tip_key="index_rate",
        )
        kit.scale_row(
            right, "响度因子", self.var_rms, 0, 1, 0.01, hot=True, tip_key="rms"
        )

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
        kit.help_mark(f0f, SETTING_TIPS["f0"])
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
        _mode_tip = (
            "【输出变声】日常开黑/语音用这个。\n"
            "麦克风 → 变成所选音色 → 从「输出设备」出去（一般选 CABLE Input）。\n"
            "\n"
            "【输入监听】不进行变声，只把麦克风原声送到输出。\n"
            "用来检查麦是否正常、声卡连接对不对；听完记得切回「输出变声」。"
        )
        kit.help_mark(modef, _mode_tip)
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
        HoverTip(rb_vc, "输出变声：把麦克风变成所选音色再输出（日常变声用这个）。")
        HoverTip(rb_im, "输入监听：不改变声音，只输出麦克风原声（测麦/测连接）。")
