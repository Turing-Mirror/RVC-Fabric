# -*- coding: utf-8 -*-
"""Dedicated in-app usage guide page."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from launcher.theme import (
    GUTTER,
    TM_ACCENT,
    TM_BG,
    TM_HAIRLINE,
    TM_INK,
    TM_INK_MUTED,
    TM_META,
    TM_SURFACE,
    mono_font,
    sans_font,
    title_font,
    tracked,
)
from launcher.ui.help_content import HELP_SECTIONS, help_plain_text
from launcher.ui.widgets import GhostButton, PageHeader, SectionCard

if TYPE_CHECKING:
    from launcher.main_app import MainApp


class HelpPage:
    def __init__(self, app: "MainApp", parent: tk.Frame) -> None:
        self.app = app
        self.fr = tk.Frame(parent, bg=TM_BG)
        self._build()

    @property
    def frame(self) -> tk.Frame:
        return self.fr

    def _build(self) -> None:
        fr = self.fr
        fr.columnconfigure(0, weight=1)
        fr.rowconfigure(1, weight=1)

        head = tk.Frame(fr, bg=TM_BG)
        head.grid(row=0, column=0, sticky="ew", padx=GUTTER, pady=(16, 8))
        PageHeader(
            head,
            eyebrow="GUIDE",
            title="使用说明",
            lead="按本软件实际按钮与页面编写。设置页每一项旁也有说明，可对照阅读。",
        ).pack(side="left", fill="x", expand=True)
        GhostButton(
            head,
            "复制全文",
            command=self._copy_all,
            padx=12,
            pady=6,
        ).pack(side="right", padx=(12, 0), pady=(28, 0))

        host = tk.Frame(fr, bg=TM_BG)
        host.grid(row=1, column=0, sticky="nsew")
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)

        canvas = tk.Canvas(host, bg=TM_BG, highlightthickness=0)
        sb = tk.Scrollbar(host, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=TM_BG)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        def _sync(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _width(e):
            if e.width > 1:
                canvas.itemconfigure(win, width=e.width)

        inner.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _width)

        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        canvas.bind("<MouseWheel>", _wheel)
        inner.bind("<MouseWheel>", _wheel)

        for i, (eye, title, body) in enumerate(HELP_SECTIONS):
            sec = SectionCard(inner, title=title, eyebrow=eye, pad=16)
            sec.pack(fill="x", padx=GUTTER, pady=(0, 10) if i else (4, 10))
            lbl = tk.Label(
                sec.body,
                text=body,
                font=sans_font(10),
                bg=TM_SURFACE,
                fg=TM_INK,
                justify="left",
                anchor="w",
                wraplength=720,
            )
            lbl.pack(fill="x", anchor="w")
            # reflow wrap on resize
            def _bind_wrap(label=lbl, canvas=canvas):
                def on_cfg(e):
                    w = max(int(canvas.winfo_width()) - 100, 320)
                    try:
                        label.configure(wraplength=w)
                    except Exception:
                        pass

                canvas.bind("<Configure>", on_cfg, add="+")

            _bind_wrap()

        foot = tk.Label(
            inner,
            text=tracked("TURING MIRROR  ·  VOICE GUIDE", gap="  "),
            font=mono_font(8),
            bg=TM_BG,
            fg=TM_META,
        )
        foot.pack(pady=(8, 24))

        def _wheel_tree(w):
            w.bind("<MouseWheel>", _wheel)
            for c in w.winfo_children():
                _wheel_tree(c)

        try:
            _wheel_tree(inner)
        except Exception:
            pass

    def _copy_all(self) -> None:
        text = help_plain_text()
        try:
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(text)
            from tkinter import messagebox

            messagebox.showinfo("已复制", "使用说明全文已复制到剪贴板。")
        except Exception:
            pass

    def on_show(self) -> None:
        pass
