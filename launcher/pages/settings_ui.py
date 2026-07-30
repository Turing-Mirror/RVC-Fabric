# -*- coding: utf-8 -*-
"""Shared settings-page UI kit (SectionCard / help / SoftSlider rows).

Used by every settings section builder so cards share one jump-index list and
the same row layout without nesting helpers inside ``_page_settings``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import tkinter as tk

from launcher.theme import (
    GUTTER,
    TM_ACCENT,
    TM_ACCENT_SOFT,
    TM_HELP,
    TM_INK,
    TM_INK_MUTED,
    TM_SURFACE,
    mono_font,
    px,
    sans_font,
)
from launcher.ui import HoverTip, SectionCard, SoftSlider
from launcher.ui.help_content import SETTING_TIPS

if TYPE_CHECKING:
    from typing import Any, Callable


class SettingsUiKit:
    """Per-build helpers bound to the settings page owner (MainApp instance)."""

    def __init__(self, owner: Any, wrap: tk.Frame) -> None:
        self.owner = owner
        self.wrap = wrap

    def card(self, *args) -> tk.Frame:
        """Create a section card.

        Accepts either ``card("标题")`` or legacy ``card(parent, "标题")``
        (parent is ignored; cards always attach to the settings wrap).
        """
        if len(args) == 1:
            title = str(args[0])
        elif len(args) == 2:
            title = str(args[1])
        else:
            raise TypeError("card() expects title or (parent, title)")
        outer = SectionCard(self.wrap, title=title, eyebrow="", pad=16)
        outer.pack(fill="x", expand=False, padx=GUTTER, pady=10)
        # Short name (before any parenthetical) feeds the top jump index
        self.owner._settings_sections.append((title.split("（")[0], outer))
        return outer.body

    def help_mark(
        self, parent, tip: str, *, pack_side: str = "left"
    ) -> Optional[tk.Label]:
        """Prominent ? badge; hover shows full tip.

        Always pack **immediately after the field label** (and before the
        combobox / slider / other control) so every row has the mark on the
        left — never trailing at the far right of an expanding control.
        """
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
        # Slight gap after the label; keep side=left so pack order controls column
        q.pack(side=pack_side, padx=(4, 6))
        HoverTip(q, tip)
        return q

    def field_label(self, parent, text: str, **pack_kw) -> tk.Label:
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
        self,
        parent,
        label,
        variable,
        from_,
        to,
        res=1,
        hot: bool = False,
        tip_key: str = "",
    ):
        """Settings row with SoftSlider; tip only on ?."""
        f = tk.Frame(parent, bg=TM_SURFACE)
        f.pack(fill="x", pady=6)
        self.field_label(f, label).pack(side="left")
        tip = SETTING_TIPS.get(tip_key, "")
        if tip:
            self.help_mark(f, tip)
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
        owner = self.owner

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
                owner._on_hot_param()

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

    def note_label(self, parent, text: str) -> tk.Label:
        lbl = tk.Label(
            parent,
            text=text,
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_HELP,
            justify="left",
            anchor="w",
            wraplength=px(640),
        )
        lbl.pack(fill="x", anchor="w", pady=(0, 6))
        self.owner._settings_wrap_labels.append(lbl)
        return lbl
