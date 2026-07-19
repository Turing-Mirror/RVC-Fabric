# -*- coding: utf-8 -*-
"""Shared Tk widgets — library chrome, stage band, cover cards."""

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
    TM_STAGE,
    TM_SURFACE,
    TM_SURFACE_HOVER,
    TM_WARN,
    display_font,
    mono_font,
    sans_font,
    title_font,
    tracked,
)


class HoverTip:
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
        wrap = tk.Frame(tip, bg=TM_SURFACE, padx=12, pady=10)
        wrap.pack(padx=1, pady=1)
        tk.Label(
            wrap,
            text=self.text,
            justify="left",
            bg=TM_SURFACE,
            fg=TM_INK,
            font=sans_font(9),
            wraplength=340,
        ).pack(anchor="w")
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip


class PrimaryButton(tk.Button):
    def __init__(self, master, text: str, command=None, **kw):
        super().__init__(
            master,
            text=text,
            font=kw.pop("font", title_font(11, "bold")),
            bg=TM_ACCENT,
            fg=TM_ACCENT_INK,
            activebackground=TM_INK,
            activeforeground=TM_ACCENT_INK,
            relief="flat",
            cursor="hand2",
            bd=0,
            padx=kw.pop("padx", 22),
            pady=kw.pop("pady", 10),
            command=command,
            **kw,
        )


class GhostButton(tk.Button):
    def __init__(self, master, text: str, command=None, **kw):
        super().__init__(
            master,
            text=text,
            font=kw.pop("font", sans_font(10)),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            activebackground=TM_SURFACE_HOVER,
            activeforeground=TM_INK,
            relief="flat",
            cursor="hand2",
            bd=0,
            padx=kw.pop("padx", 16),
            pady=kw.pop("pady", 9),
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            command=command,
            **kw,
        )


class SectionCard(tk.Frame):
    """Panel with left accent rail + optional mono eyebrow + title."""

    def __init__(
        self,
        master,
        title: str = "",
        *,
        eyebrow: str = "",
        accent_rail: bool = True,
        pad: int = 16,
        **kw,
    ):
        super().__init__(master, bg=TM_BG, **kw)
        if accent_rail:
            tk.Frame(self, bg=TM_ACCENT, width=4).pack(side="left", fill="y")
        self.body = tk.Frame(
            self,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            padx=pad,
            pady=14,
        )
        self.body.pack(side="left", fill="both", expand=True)
        self.title_lbl: Optional[tk.Label] = None
        if eyebrow:
            tk.Label(
                self.body,
                text=tracked(eyebrow.upper(), gap="  ") if eyebrow.isascii() else eyebrow,
                font=mono_font(8),
                bg=TM_SURFACE,
                fg=TM_META,
                anchor="w",
            ).pack(anchor="w", pady=(0, 4))
        if title:
            self.title_lbl = tk.Label(
                self.body,
                text=title,
                font=title_font(13, "bold"),
                bg=TM_SURFACE,
                fg=TM_INK,
                anchor="w",
            )
            self.title_lbl.pack(anchor="w", pady=(0, 8))


class NavItem(tk.Label):
    """Segment control item (Schale-like pill group)."""

    def __init__(
        self,
        master,
        text: str,
        key: str,
        on_click: Callable[[str], None],
        **kw,
    ):
        super().__init__(
            master,
            text=text,
            font=sans_font(10),
            bg=kw.pop("bg", TM_INSET),
            fg=TM_INK_MUTED,
            padx=18,
            pady=8,
            cursor="hand2",
            **kw,
        )
        self.key = key
        self._on_click = on_click
        self._active = False
        self._rail_bg = master.cget("bg") if master else TM_INSET
        self.bind("<Button-1>", lambda _e: self._on_click(key))
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            self.configure(
                fg=TM_ACCENT_INK,
                font=title_font(10, "bold"),
                bg=TM_ACCENT,
            )
        else:
            self.configure(
                fg=TM_INK_MUTED,
                font=sans_font(10),
                bg=self._rail_bg,
            )

    def _enter(self, _e=None) -> None:
        if not self._active:
            self.configure(fg=TM_INK, bg=TM_SURFACE_HOVER)

    def _leave(self, _e=None) -> None:
        if not self._active:
            self.configure(fg=TM_INK_MUTED, bg=self._rail_bg)


class StatusBadge(tk.Frame):
    def __init__(self, master, **kw):
        super().__init__(master, bg=TM_INSET, padx=14, pady=8, **kw)
        self.title_lbl = tk.Label(
            self,
            text="引擎待命",
            font=title_font(10, "bold"),
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
        self.sub_lbl.pack(anchor="e", pady=(2, 0))

    def set_mode(self, mode: str, title: str, subtitle: str = "") -> None:
        if mode == "live":
            badge_bg, title_fg, sub_fg = TM_ACCENT_SOFT, TM_ACCENT, TM_OK
            title_font_ = title_font(11, "bold")
            title = "● " + title
        elif mode == "busy":
            badge_bg, title_fg, sub_fg = TM_INSET, TM_WARN, TM_META
            title_font_ = title_font(10, "bold")
        elif mode == "error":
            badge_bg, title_fg, sub_fg = TM_INSET, TM_ERROR, TM_META
            title_font_ = title_font(10, "bold")
        else:
            badge_bg, title_fg, sub_fg = TM_INSET, TM_INK_MUTED, TM_META
            title_font_ = sans_font(10)
        try:
            self.configure(bg=badge_bg)
            self.title_lbl.configure(
                text=title, bg=badge_bg, fg=title_fg, font=title_font_
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
    """Bootstrap action tile — larger, mono caption, left rail."""

    def __init__(self, master, title: str, subtitle: str, command, **kw):
        super().__init__(
            master,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            **kw,
        )
        self.configure(width=168, height=140)
        self.pack_propagate(False)
        self._cmd = command
        tk.Frame(self, bg=TM_ACCENT, width=4).pack(side="left", fill="y")
        col = tk.Frame(self, bg=TM_SURFACE)
        col.pack(side="left", fill="both", expand=True, padx=12, pady=14)
        self._lbl = tk.Label(
            col,
            text=title,
            font=title_font(12, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            wraplength=130,
            justify="left",
            anchor="w",
        )
        self._lbl.pack(anchor="w", pady=(8, 6))
        self._sub = tk.Label(
            col,
            text=subtitle,
            font=mono_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            wraplength=130,
            justify="left",
            anchor="w",
        )
        self._sub.pack(anchor="w")
        for w in (self, col, self._lbl, self._sub):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _enter(self, _e=None):
        for w in (self, self._lbl, self._sub):
            try:
                w.configure(bg=TM_SURFACE_HOVER)
            except Exception:
                pass

    def _leave(self, _e=None):
        for w in (self, self._lbl, self._sub):
            try:
                w.configure(bg=TM_SURFACE)
            except Exception:
                pass

    def _click(self, _e=None):
        if self._cmd:
            self._cmd()


class ModelCoverCard(tk.Frame):
    """Cover-dominant tile (Schale work-card proportion)."""

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
        width: int = 200,
        height: int = 260,
        on_click: Optional[Callable] = None,
        action_text: str = "",
        on_action: Optional[Callable] = None,
        **kw,
    ):
        edge = TM_ACCENT if (active or focus) else TM_HAIRLINE
        thick = 2 if (active or focus) else 1
        super().__init__(
            master,
            bg=TM_SURFACE,
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
        self._photo = photo

        # Cover ~58% of card (image-first)
        cover_h = max(int(height * 0.58), 96)
        cover_box = tk.Frame(self, bg=TM_INSET, height=cover_h)
        cover_box.pack(fill="x")
        cover_box.pack_propagate(False)
        if photo is not None:
            lbl = tk.Label(cover_box, image=photo, bg=TM_INSET)
            lbl.place(relx=0.5, rely=0.5, anchor="center")
            widgets = [lbl]
        else:
            initial = (name[:1] or "·")
            lbl = tk.Label(
                cover_box,
                text=initial,
                font=display_font(28 if focus else 20),
                bg=TM_INSET,
                fg=TM_META,
            )
            lbl.place(relx=0.5, rely=0.5, anchor="center")
            widgets = [lbl]

        body = tk.Frame(self, bg=TM_SURFACE)
        body.pack(fill="both", expand=True, padx=10, pady=(8, 10))

        tag_lbl = tk.Label(
            body,
            text=(tag or "音色").upper() if (tag or "").isascii() else (tag or "音色"),
            font=mono_font(7),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        )
        tag_lbl.pack(anchor="w")
        name_lbl = tk.Label(
            body,
            text=name[:16],
            font=title_font(12 if focus else 11, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        )
        name_lbl.pack(anchor="w", pady=(2, 0))
        widgets.extend([body, name_lbl, tag_lbl, cover_box, self])

        if active:
            badge = tk.Label(
                self,
                text="使用中",
                font=mono_font(7),
                bg=TM_ACCENT,
                fg=TM_ACCENT_INK,
                padx=8,
                pady=2,
            )
            badge.place(relx=1.0, x=-8, y=8, anchor="ne")
            widgets.append(badge)

        if index_text:
            idx = tk.Label(
                body,
                text=index_text,
                font=mono_font(8),
                bg=TM_SURFACE,
                fg=TM_META,
                anchor="w",
            )
            idx.pack(anchor="w", pady=(4, 0))
            widgets.append(idx)

        if action_text and on_action and not active:
            btn = tk.Button(
                body,
                text=action_text,
                font=title_font(9, "bold"),
                bg=TM_ACCENT,
                fg=TM_ACCENT_INK,
                relief="flat",
                cursor="hand2",
                command=on_action,
                bd=0,
                padx=14,
                pady=4,
            )
            btn.pack(anchor="w", pady=(8, 0))
        elif active and action_text:
            tk.Label(
                body,
                text=action_text,
                font=mono_font(8),
                bg=TM_ACCENT_SOFT,
                fg=TM_ACCENT,
                padx=10,
                pady=3,
            ).pack(anchor="w", pady=(8, 0))

        def _click(_e=None):
            if on_click:
                on_click()

        for w in widgets:
            w.bind("<Button-1>", _click)


class PageHeader(tk.Frame):
    """Page title block: mono eyebrow + large title + muted lead."""

    def __init__(
        self,
        master,
        *,
        eyebrow: str,
        title: str,
        lead: str = "",
        bg: str = TM_BG,
        **kw,
    ):
        super().__init__(master, bg=bg, **kw)
        tk.Label(
            self,
            text=tracked(eyebrow, gap="  ") if all(ord(c) < 128 for c in eyebrow) else eyebrow,
            font=mono_font(8),
            bg=bg,
            fg=TM_META,
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            self,
            text=title,
            font=title_font(22, "bold"),
            bg=bg,
            fg=TM_INK,
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))
        if lead:
            tk.Label(
                self,
                text=lead,
                font=sans_font(10),
                bg=bg,
                fg=TM_INK_MUTED,
                anchor="w",
                wraplength=640,
                justify="left",
            ).pack(anchor="w", pady=(8, 0))
