# -*- coding: utf-8 -*-
"""Dedicated in-app usage guide page.

Help bodies may use lightweight ``**bold**`` markers (same as markdown docs).
They are rendered as bold in a Text widget — never shown as raw asterisks.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from launcher.theme import (
    GUTTER,
    TM_BG,
    TM_INK,
    TM_SURFACE,
    sans_font,
)
from launcher.ui.help_content import HELP_SECTIONS, iter_md_segments
from launcher.ui.widgets import PageHeader, SectionCard

if TYPE_CHECKING:
    from launcher.main_app import MainApp


def _fill_rich_text(widget: tk.Text, body: str) -> None:
    """Insert body with **bold** segments as font weight bold."""
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    for kind, chunk in iter_md_segments(body):
        if not chunk:
            continue
        if kind == "bold":
            widget.insert("end", chunk, ("bold",))
        else:
            widget.insert("end", chunk)
    widget.configure(state="disabled")


class HelpPage:
    def __init__(self, app: "MainApp", parent: tk.Frame) -> None:
        self.app = app
        self.fr = tk.Frame(parent, bg=TM_BG)
        self._body_texts: list[tk.Text] = []
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
            eyebrow="",
            title="使用说明",
            lead="",
        ).pack(side="left", fill="x", expand=True)

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
                tw = max(int(e.width) - 100, 280)
                for t in self._body_texts:
                    try:
                        t.configure(width=max(tw // 8, 36))
                    except Exception:
                        pass

        inner.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _width)

        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        canvas.bind("<MouseWheel>", _wheel)
        inner.bind("<MouseWheel>", _wheel)

        for i, (_eye, title, body) in enumerate(HELP_SECTIONS):
            sec = SectionCard(inner, title=title, eyebrow="", pad=16)
            sec.pack(fill="x", padx=GUTTER, pady=(0, 10) if i else (4, 10))
            txt = tk.Text(
                sec.body,
                wrap="word",
                font=sans_font(10),
                bg=TM_SURFACE,
                fg=TM_INK,
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                padx=0,
                pady=0,
                cursor="arrow",
                height=1,
            )
            txt.tag_configure("bold", font=sans_font(10, "bold"), foreground=TM_INK)
            _fill_rich_text(txt, body)
            txt.pack(fill="x", anchor="w")
            txt.bind("<Key>", lambda e: "break")
            self._body_texts.append(txt)

            def _autosize(t=txt):
                try:
                    t.update_idletasks()
                    n = t.count("1.0", "end-1c", "displaylines")
                    if isinstance(n, (tuple, list)):
                        n = n[0]
                    t.configure(height=max(int(n or 1), 2))
                except Exception:
                    try:
                        n = int(float(t.index("end-1c").split(".")[0]))
                        t.configure(height=max(n, 2))
                    except Exception:
                        t.configure(height=8)

            _autosize()
            txt.bind("<Configure>", lambda _e, t=txt: _autosize(t), add="+")

        def _wheel_tree(w):
            w.bind("<MouseWheel>", _wheel)
            for c in w.winfo_children():
                _wheel_tree(c)

        try:
            _wheel_tree(inner)
        except Exception:
            pass

        fr.after(
            100,
            lambda: _width(
                type("E", (), {"width": max(canvas.winfo_width(), 600)})()
            ),
        )

    def on_show(self) -> None:
        pass
