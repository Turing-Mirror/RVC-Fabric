# -*- coding: utf-8 -*-
"""Shared Tk widgets for Turing Mirror shell (library chrome + stage focus)."""

from __future__ import annotations

from typing import Callable, Optional

import tkinter as tk

from launcher.theme import (
    TM_ACCENT,
    TM_ACCENT_INK,
    TM_ACCENT_SOFT,
    TM_BG,
    TM_ERROR,
    TM_HAIRLINE,
    TM_INK,
    TM_INK_MUTED,
    TM_INSET,
    TM_META,
    TM_OK,
    TM_SURFACE,
    TM_SURFACE_HOVER,
    TM_WARN,
    mono_font,
    sans_font,
    serif_font,
)


class HoverTip:
    """Quiet paper popover on hover."""

    def __init__(self, widget: tk.Widget, text: str, *, delay_ms: int = 350) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: Optional[str] = None
        self._tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None

    def _show(self) -> None:
        self._after_id = None
        if self._tip is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_attributes("-topmost", True)
        tip.configure(bg=TM_HAIRLINE)
        wrap = tk.Frame(tip, bg=TM_SURFACE, padx=10, pady=8)
        wrap.pack(padx=1, pady=1)
        tk.Label(
            wrap,
            text=self.text,
            justify="left",
            bg=TM_SURFACE,
            fg=TM_INK,
            font=sans_font(9),
            wraplength=320,
        ).pack(anchor="w")
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip


class PrimaryButton(tk.Button):
    def __init__(self, master, text: str, command=None, **kw):
        super().__init__(
            master,
            text=text,
            font=kw.pop("font", sans_font(10, "bold")),
            bg=TM_ACCENT,
            fg=TM_ACCENT_INK,
            activebackground=TM_INK,
            activeforeground=TM_ACCENT_INK,
            relief="flat",
            cursor="hand2",
            bd=0,
            padx=kw.pop("padx", 18),
            pady=kw.pop("pady", 7),
            command=command,
            **kw,
        )


class GhostButton(tk.Button):
    def __init__(self, master, text: str, command=None, **kw):
        super().__init__(
            master,
            text=text,
            font=kw.pop("font", sans_font(9)),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            activebackground=TM_SURFACE_HOVER,
            activeforeground=TM_INK,
            relief="flat",
            cursor="hand2",
            bd=0,
            padx=kw.pop("padx", 12),
            pady=kw.pop("pady", 7),
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            command=command,
            **kw,
        )


class SectionCard(tk.Frame):
    """Surface panel with optional left accent rail (library section card)."""

    def __init__(
        self,
        master,
        title: str = "",
        *,
        accent_rail: bool = True,
        pad: int = 14,
        **kw,
    ):
        super().__init__(master, bg=TM_BG, **kw)
        rail_w = 3 if accent_rail else 0
        if accent_rail:
            tk.Frame(self, bg=TM_ACCENT, width=rail_w).pack(side="left", fill="y")
        self.body = tk.Frame(
            self,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            padx=pad,
            pady=10,
        )
        self.body.pack(side="left", fill="both", expand=True)
        self.title_lbl: Optional[tk.Label] = None
        if title:
            self.title_lbl = tk.Label(
                self.body,
                text=title,
                font=serif_font(12, "bold"),
                bg=TM_SURFACE,
                fg=TM_INK,
                anchor="w",
            )
            self.title_lbl.pack(anchor="w", pady=(0, 6))


class NavItem(tk.Label):
    """Top-bar text nav with active accent treatment."""

    def __init__(self, master, text: str, key: str, on_click: Callable[[str], None], **kw):
        super().__init__(
            master,
            text=text,
            font=sans_font(11),
            bg=kw.pop("bg", TM_SURFACE),
            fg=TM_INK_MUTED,
            padx=14,
            pady=6,
            cursor="hand2",
            **kw,
        )
        self.key = key
        self._on_click = on_click
        self._active = False
        self.bind("<Button-1>", lambda _e: self._on_click(key))
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            self.configure(
                fg=TM_ACCENT,
                font=sans_font(11, "bold"),
                bg=TM_ACCENT_SOFT,
            )
        else:
            self.configure(
                fg=TM_INK_MUTED,
                font=sans_font(11),
                bg=self.master.cget("bg") if self.master else TM_SURFACE,
            )

    def _enter(self, _e=None) -> None:
        if not self._active:
            self.configure(fg=TM_INK)

    def _leave(self, _e=None) -> None:
        if not self._active:
            self.configure(fg=TM_INK_MUTED)


class StatusBadge(tk.Frame):
    """Bottom-right engine status pill."""

    def __init__(self, master, **kw):
        super().__init__(master, bg=TM_INSET, padx=12, pady=5, **kw)
        self.title_lbl = tk.Label(
            self,
            text="引擎待命",
            font=sans_font(10),
            bg=TM_INSET,
            fg=TM_INK_MUTED,
        )
        self.title_lbl.pack(anchor="e")
        self.sub_lbl = tk.Label(
            self,
            text="",
            font=mono_font(8),
            bg=TM_INSET,
            fg=TM_META,
        )
        self.sub_lbl.pack(anchor="e")

    def set_mode(self, mode: str, title: str, subtitle: str = "") -> None:
        """mode: idle|busy|live|error"""
        if mode == "live":
            badge_bg = TM_ACCENT_SOFT
            title_fg = TM_ACCENT
            title_font = sans_font(11, "bold")
            sub_fg = TM_OK
            title = "● " + title
        elif mode == "busy":
            badge_bg = TM_INSET
            title_fg = TM_WARN
            title_font = sans_font(10, "bold")
            sub_fg = TM_META
        elif mode == "error":
            badge_bg = TM_INSET
            title_fg = TM_ERROR
            title_font = sans_font(10, "bold")
            sub_fg = TM_META
        else:
            badge_bg = TM_INSET
            title_fg = TM_INK_MUTED
            title_font = sans_font(10)
            sub_fg = TM_META
        try:
            self.configure(bg=badge_bg)
            self.title_lbl.configure(
                text=title, bg=badge_bg, fg=title_fg, font=title_font
            )
            self.sub_lbl.configure(
                text=subtitle or "",
                bg=badge_bg,
                fg=sub_fg,
                font=mono_font(8),
            )
        except Exception:
            pass


class SoftActionCard(tk.Frame):
    """Clickable action tile (bootstrap)."""

    def __init__(self, master, title: str, subtitle: str, command, **kw):
        super().__init__(
            master,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            **kw,
        )
        self.configure(width=148, height=118)
        self._cmd = command
        rail = tk.Frame(self, bg=TM_ACCENT, width=3, height=118)
        rail.place(x=0, y=0)
        self._inner = tk.Frame(self, bg=TM_SURFACE, width=128, height=72)
        self._inner.pack(padx=10, pady=(14, 4))
        self._inner.pack_propagate(False)
        self._lbl = tk.Label(
            self._inner,
            text=title,
            font=sans_font(11, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            wraplength=118,
            justify="center",
        )
        self._lbl.place(relx=0.5, rely=0.5, anchor="center")
        self._sub = tk.Label(
            self,
            text=subtitle,
            font=sans_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
        )
        self._sub.pack(pady=(0, 10))
        for w in (self, self._inner, self._lbl, self._sub):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _enter(self, _e=None):
        for w in (self, self._inner, self._lbl, self._sub):
            w.configure(bg=TM_SURFACE_HOVER)

    def _leave(self, _e=None):
        for w in (self, self._inner, self._lbl, self._sub):
            w.configure(bg=TM_SURFACE)

    def _click(self, _e=None):
        if self._cmd:
            self._cmd()


class ModelCoverCard(tk.Frame):
    """Cover-forward model tile for home carousel / model grid."""

    def __init__(
        self,
        master,
        *,
        name: str,
        tag: str = "",
        photo: Optional[tk.PhotoImage] = None,
        active: bool = False,
        focus: bool = False,
        index_text: str = "",
        width: int = 180,
        height: int = 220,
        on_click: Optional[Callable] = None,
        action_text: str = "",
        on_action: Optional[Callable] = None,
        **kw,
    ):
        edge = TM_ACCENT if (active or focus) else TM_HAIRLINE
        thick = 2 if (active or focus) else 1
        super().__init__(
            master,
            bg=TM_SURFACE if (focus or active) else TM_BG,
            width=width,
            height=height,
            highlightthickness=thick,
            highlightbackground=edge,
            cursor="hand2",
            **kw,
        )
        self.pack_propagate(False)
        self.grid_propagate(False)
        self._on_click = on_click
        self._photo = photo  # keep ref

        # Cover / placeholder
        cover_h = max(int(height * 0.48), 72)
        cover_box = tk.Frame(self, bg=TM_INSET, height=cover_h)
        cover_box.pack(fill="x")
        cover_box.pack_propagate(False)
        if photo is not None:
            lbl = tk.Label(cover_box, image=photo, bg=TM_INSET)
            lbl.place(relx=0.5, rely=0.5, anchor="center")
            widgets = [lbl]
        else:
            initial = (name[:1] or "·").upper()
            lbl = tk.Label(
                cover_box,
                text=initial,
                font=serif_font(22 if focus else 16, "bold"),
                bg=TM_INSET,
                fg=TM_META,
            )
            lbl.place(relx=0.5, rely=0.5, anchor="center")
            widgets = [lbl]

        body = tk.Frame(self, bg=self.cget("bg"))
        body.pack(fill="both", expand=True, padx=8, pady=6)
        name_lbl = tk.Label(
            body,
            text=name[:14],
            font=serif_font(12 if focus else 10, "bold"),
            bg=self.cget("bg"),
            fg=TM_INK,
        )
        name_lbl.pack(pady=(2, 0))
        tag_lbl = tk.Label(
            body,
            text=tag or "音色",
            font=sans_font(8),
            bg=self.cget("bg"),
            fg=TM_META,
        )
        tag_lbl.pack()
        widgets.extend([body, name_lbl, tag_lbl, cover_box, self])

        if active:
            badge = tk.Label(
                self,
                text="使用中",
                font=sans_font(8, "bold"),
                bg=TM_ACCENT,
                fg=TM_ACCENT_INK,
                padx=6,
                pady=1,
            )
            badge.place(relx=1.0, x=-6, y=6, anchor="ne")
            widgets.append(badge)

        if index_text:
            idx = tk.Label(
                body,
                text=index_text,
                font=mono_font(8),
                bg=self.cget("bg"),
                fg=TM_META,
            )
            idx.pack(pady=(4, 0))
            widgets.append(idx)

        if action_text and on_action and not active:
            btn = tk.Button(
                body,
                text=action_text,
                font=sans_font(9),
                bg=TM_ACCENT,
                fg=TM_ACCENT_INK,
                relief="flat",
                cursor="hand2",
                command=on_action,
                bd=0,
                padx=12,
                pady=3,
            )
            btn.pack(pady=(6, 2))
        elif active and action_text:
            tk.Label(
                body,
                text=action_text,
                font=sans_font(9, "bold"),
                bg=TM_ACCENT,
                fg=TM_ACCENT_INK,
                padx=12,
                pady=3,
            ).pack(pady=(6, 2))

        def _click(_e=None):
            if on_click:
                on_click()

        for w in widgets:
            w.bind("<Button-1>", _click)
