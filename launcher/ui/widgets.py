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


def center_over(win: tk.Toplevel, master: tk.Misc) -> None:
    """Place a dialog centered over its parent window (upper third)."""
    try:
        win.update_idletasks()
        top = master.winfo_toplevel()
        mx, my = top.winfo_rootx(), top.winfo_rooty()
        mw, mh = top.winfo_width(), top.winfo_height()
        w = max(win.winfo_width(), win.winfo_reqwidth())
        h = max(win.winfo_height(), win.winfo_reqheight())
        x = mx + max((mw - w) // 2, 0)
        y = my + max((mh - h) // 3, 0)
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    except Exception:
        pass


def ask_choice(
    parent: tk.Misc,
    title: str,
    message: str,
    options: list[tuple[str, str]],
    *,
    cancel_text: str = "取消",
) -> Optional[str]:
    """Modal question whose buttons say what they DO (not 是/否).

    ``options`` = [(key, button_label), …]; first option renders as the
    primary button. Returns the chosen key, or None on cancel/close.
    """
    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=TM_BG)
    win.resizable(False, False)
    win.transient(parent.winfo_toplevel())
    result: dict = {"v": None}

    tk.Label(
        win,
        text=message,
        font=sans_font(10),
        bg=TM_BG,
        fg=TM_INK,
        justify="left",
        anchor="w",
        wraplength=400,
    ).pack(padx=22, pady=(18, 14), anchor="w")

    row = tk.Frame(win, bg=TM_BG)
    row.pack(padx=22, pady=(0, 18), anchor="e", fill="x")

    def _pick(key):
        result["v"] = key
        win.destroy()

    GhostButton(row, cancel_text, command=lambda: _pick(None), padx=14, pady=7).pack(
        side="right", padx=(8, 0)
    )
    for i, (key, label) in enumerate(reversed(options)):
        is_primary = i == len(options) - 1  # first option = primary
        cls = PrimaryButton if is_primary else GhostButton
        cls(row, label, command=lambda k=key: _pick(k), padx=14, pady=7).pack(
            side="right", padx=(8, 0)
        )

    win.protocol("WM_DELETE_WINDOW", lambda: _pick(None))
    center_over(win, parent)
    try:
        win.grab_set()
    except Exception:
        pass
    win.wait_window()
    return result["v"]


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


def _no_chrome(**extra) -> dict:
    """Kill Windows Tk default Label/Button borders that frame text."""
    d = {
        "bd": 0,
        "borderwidth": 0,
        "highlightthickness": 0,
        "relief": "flat",
    }
    d.update(extra)
    return d


class PrimaryButton(tk.Button):
    def __init__(self, master, text: str, command=None, **kw):
        # Windows default highlightthickness=1 draws a system box around the label
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
            borderwidth=0,
            highlightthickness=0,
            padx=kw.pop("padx", 22),
            pady=kw.pop("pady", 10),
            command=command,
            **kw,
        )


class GhostButton(tk.Button):
    def __init__(self, master, text: str, command=None, **kw):
        # Hairline via highlight only; force bd=0 so text is not double-framed
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
            borderwidth=0,
            padx=kw.pop("padx", 16),
            pady=kw.pop("pady", 9),
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            highlightcolor=TM_HAIRLINE,
            command=command,
            **kw,
        )


class SectionCard(tk.Frame):
    """Flat panel with optional mono eyebrow + title (no accent rail)."""

    def __init__(
        self,
        master,
        title: str = "",
        *,
        eyebrow: str = "",
        accent_rail: bool = False,  # accepted for compat; rail design removed
        pad: int = 16,
        **kw,
    ):
        super().__init__(master, bg=TM_BG, **kw)
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
                **_no_chrome(),
            ).pack(anchor="w", pady=(0, 4))
        if title:
            self.title_lbl = tk.Label(
                self.body,
                text=title,
                font=title_font(13, "bold"),
                bg=TM_SURFACE,
                fg=TM_INK,
                anchor="w",
                **_no_chrome(),
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


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    s = (h or "#000000").lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except Exception:
        return 0, 0, 0


class SoftSlider(tk.Frame):
    """Anti-aliased range control (Material/iOS-style pill track + soft thumb).

    Pillow 2× supersample for smooth edges. Layout is height-fixed so parent
    dock does not reflow/jitter when the value changes.
    """

    def __init__(
        self,
        master,
        variable: tk.Variable,
        from_: float,
        to: float,
        *,
        resolution: float = 1,
        command=None,
        on_press=None,
        on_release=None,
        bar_width: int = 200,
        bar_height: int = 36,
        width: int | None = None,
        height: int | None = None,
        **kw,
    ):
        bg = kw.pop("bg", TM_SURFACE)
        kw.pop("width", None)
        kw.pop("height", None)
        super().__init__(master, bg=bg, **kw)
        self.variable = variable
        self.from_ = float(from_)
        self.to = float(to)
        self.resolution = float(resolution) if resolution else 1.0
        self.command = command
        self.on_press = on_press
        self.on_release = on_release
        self._bg = bg
        self._drag = False
        self._pad_x = 14
        self._photo = None
        self._img_id = None
        self._drawing = False
        self._last_frac = -1.0
        bw = int(width if width is not None else bar_width)
        bh = int(height if height is not None else bar_height)
        bh = max(bh, 34)

        # Fixed height canvas — prevents dock vertical jitter on redraw
        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
            bg=bg,
            height=bh,
        )
        self.canvas.configure(width=bw, height=bh)
        self.canvas.pack(fill="x", expand=True)
        # Never assign self._w — Tk uses it for widget path
        self._bar_w = bw
        self._bar_h = bh

        self.canvas.bind("<Configure>", self._on_cfg)
        self.canvas.bind("<Button-1>", self._on_down)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_up)
        try:
            self.variable.trace_add("write", lambda *_a: self._on_var_write())
        except Exception:
            pass
        self.after(10, self._draw)

    def _on_var_write(self) -> None:
        # Skip redundant redraws when frac unchanged (stops feedback thrash)
        f = self._frac()
        if abs(f - self._last_frac) < 1e-6 and self._photo is not None:
            return
        self._draw()

    def _on_cfg(self, event) -> None:
        # Only react to real width changes; never grow height from event (jitter source)
        if event.width <= 1:
            return
        if abs(event.width - self._bar_w) < 2:
            return
        self._bar_w = int(event.width)
        self._draw()

    def get(self):
        return self.variable.get()

    def set(self, value) -> None:
        self.variable.set(value)

    def _clamp_val(self, v: float) -> float:
        lo, hi = (self.from_, self.to) if self.from_ <= self.to else (self.to, self.from_)
        v = max(lo, min(hi, float(v)))
        step = self.resolution
        if step and step > 0:
            n = round((v - self.from_) / step)
            v = self.from_ + n * step
            v = max(lo, min(hi, v))
            if step >= 1:
                v = int(round(v))
            else:
                decimals = max(0, min(6, len(str(step).split(".")[-1])))
                v = round(v, decimals)
        return v

    def _frac(self) -> float:
        span = self.to - self.from_
        if abs(span) < 1e-12:
            return 0.0
        try:
            v = float(self.variable.get())
        except Exception:
            v = self.from_
        f = (v - self.from_) / span
        return max(0.0, min(1.0, f))

    def _x_to_val(self, x: float) -> float:
        usable = max(1.0, self._bar_w - 2 * self._pad_x)
        f = (x - self._pad_x) / usable
        f = max(0.0, min(1.0, f))
        return self._clamp_val(self.from_ + f * (self.to - self.from_))

    def _draw(self) -> None:
        if self._drawing:
            return
        self._drawing = True
        try:
            w = max(int(self._bar_w), 48)
            h = max(int(self._bar_h), 34)
            try:
                self._draw_pil(w, h)
            except Exception:
                self._draw_fallback(w, h)
            self._last_frac = self._frac()
        finally:
            self._drawing = False

    def _draw_pil(self, w: int, h: int) -> None:
        """2× supersampled rounded track + soft thumb (anti-aliased)."""
        from PIL import Image, ImageDraw, ImageFilter, ImageTk

        scale = 2
        W, H = w * scale, h * scale
        pad = self._pad_x * scale
        track_h = max(10, int(6 * scale))
        thumb_r = int(9 * scale)
        cy = H // 2
        x0, x1 = pad, W - pad

        bg = _hex_to_rgb(self._bg)
        inset = _hex_to_rgb(TM_INSET)
        accent = _hex_to_rgb(TM_ACCENT)
        white = (255, 255, 255)

        img = Image.new("RGBA", (W, H), (*bg, 255))
        draw = ImageDraw.Draw(img)

        def rounded_capsule(x_a, x_b, y_c, th, fill):
            if x_b <= x_a:
                return
            r = th / 2
            y0, y1 = y_c - r, y_c + r
            draw.rounded_rectangle([x_a, y0, x_b, y1], radius=r, fill=fill)

        rounded_capsule(x0, x1, cy, track_h, (*inset, 255))

        frac = self._frac()
        fill_x = x0 + (x1 - x0) * frac
        if fill_x > x0 + 1:
            rounded_capsule(
                x0, max(fill_x, x0 + track_h), cy, track_h, (*accent, 255)
            )

        tx = int(round(fill_x))
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sr = thumb_r + 2
        sd.ellipse(
            [tx - sr, cy - sr + 2, tx + sr, cy + sr + 2],
            fill=(0, 0, 0, 36),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(1, scale)))
        img = Image.alpha_composite(img, shadow)
        draw = ImageDraw.Draw(img)

        ring = thumb_r
        draw.ellipse(
            [tx - ring, cy - ring, tx + ring, cy + ring],
            fill=(*white, 255),
            outline=(*accent, 255),
            width=max(2, scale),
        )
        cr = max(2, scale)
        draw.ellipse(
            [tx - cr, cy - cr, tx + cr, cy + cr],
            fill=(*accent, 255),
        )

        out = img.resize((w, h), Image.Resampling.LANCZOS)
        # Keep canvas height locked so pack geometry never shifts
        try:
            self.canvas.configure(height=h)
        except Exception:
            pass
        photo = ImageTk.PhotoImage(out, master=self.canvas)
        self._photo = photo
        c = self.canvas
        if self._img_id is None:
            self._img_id = c.create_image(0, 0, anchor="nw", image=photo)
        else:
            c.itemconfigure(self._img_id, image=photo)

    def _draw_fallback(self, w: int, h: int) -> None:
        """If PIL missing: thick track + filled thumb."""
        c = self.canvas
        c.delete("all")
        self._img_id = None
        pad = self._pad_x
        cy = h // 2
        track_h = 8
        x0, x1 = pad, w - pad
        c.create_line(x0, cy, x1, cy, fill=TM_INSET, width=track_h, capstyle=tk.ROUND)
        frac = self._frac()
        fill_x = x0 + (x1 - x0) * frac
        if fill_x > x0 + 2:
            c.create_line(
                x0, cy, fill_x, cy, fill=TM_ACCENT, width=track_h, capstyle=tk.ROUND
            )
        r = 9
        c.create_oval(
            fill_x - r,
            cy - r,
            fill_x + r,
            cy + r,
            fill=TM_SURFACE_HOVER,
            outline=TM_ACCENT,
            width=2,
        )

    def _apply_x(self, x: float, *, notify: bool = True) -> None:
        v = self._x_to_val(x)
        try:
            cur = self.variable.get()
        except Exception:
            cur = None
        if cur == v:
            self._draw()
            return
        # Set var; trace will redraw — avoid double draw
        self.variable.set(v)
        if notify and self.command:
            try:
                self.command(v)
            except TypeError:
                try:
                    self.command()
                except Exception:
                    pass
            except Exception:
                pass

    def _on_down(self, event) -> None:
        self._drag = True
        if self.on_press:
            try:
                self.on_press()
            except Exception:
                pass
        self._apply_x(event.x)

    def _on_drag(self, event) -> None:
        if self._drag:
            self._apply_x(event.x)

    def _on_up(self, event) -> None:
        was = self._drag
        self._drag = False
        self._apply_x(event.x)
        if was and self.on_release:
            try:
                self.on_release()
            except Exception:
                pass


class ParamTile(tk.Frame):
    """Dock parameter cell: mono label + fixed-width value + SoftSlider."""

    def __init__(
        self,
        master,
        label: str,
        variable: tk.Variable,
        from_: float,
        to: float,
        *,
        resolution: float = 1,
        command=None,
        on_press=None,
        on_release=None,
        width: int = 168,
        fmt: str = "int",
        **kw,
    ):
        super().__init__(
            master,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            **kw,
        )
        self.variable = variable
        self.fmt = fmt
        self._user_cmd = command
        # Fixed outer size — prevents bottom bar vertical/horizontal thrash
        tile_w = max(int(width), 168)
        tile_h = 92
        try:
            self.configure(width=tile_w, height=tile_h)
            self.pack_propagate(False)
        except Exception:
            pass

        inner = tk.Frame(self, bg=TM_SURFACE, padx=14, pady=10)
        inner.pack(fill="both", expand=True)

        head = tk.Frame(inner, bg=TM_SURFACE)
        head.pack(fill="x")
        tk.Label(
            head,
            text=tracked(label.upper(), gap="  ") if label.isascii() else label,
            font=mono_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        ).pack(side="left")
        # Fixed character columns so values never reflow neighbors
        self.val_lbl = tk.Label(
            head,
            text="+0",
            font=mono_font(12),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="e",
            width=7,
        )
        self.val_lbl.pack(side="right")

        self.slider = SoftSlider(
            inner,
            variable,
            from_,
            to,
            resolution=resolution,
            command=self._on_slide,
            on_press=on_press,
            on_release=on_release,
            bar_width=max(tile_w - 28, 150),
            bar_height=36,
            bg=TM_SURFACE,
        )
        self.slider.pack(fill="x", expand=True, pady=(6, 0))
        try:
            variable.trace_add("write", lambda *_a: self._fmt())
        except Exception:
            pass
        self._fmt()

    def set_history_hooks(self, on_press=None, on_release=None) -> None:
        try:
            self.slider.on_press = on_press
            self.slider.on_release = on_release
        except Exception:
            pass

    def _fmt(self) -> None:
        try:
            v = self.variable.get()
            if self.fmt == "int":
                text = f"{int(v):+d}"
            elif self.fmt == "signed":
                text = f"{float(v):+.2f}"
            else:
                text = f"{float(v):.2f}"
            self.val_lbl.configure(text=text)
        except Exception:
            pass

    def _on_slide(self, _v=None) -> None:
        self._fmt()
        if self._user_cmd:
            try:
                self._user_cmd()
            except Exception:
                pass


class SoftActionCard(tk.Frame):
    """Bootstrap action tile — larger, mono caption (rail design removed).

    Hover / press feedback is **rim only** (thicker + accent border). Never recolor
    title/subtitle: painting Label bg draws a tight gray box around the glyphs on
    Windows (looks like the text itself is selected/deepened).
    """

    def __init__(self, master, title: str, subtitle: str, command, **kw):
        super().__init__(
            master,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            highlightcolor=TM_HAIRLINE,
            cursor="hand2",
            **kw,
        )
        self.configure(width=168, height=140)
        self.pack_propagate(False)
        self._cmd = command
        # Inner column: no default Label chrome (Windows Label bd defaults to 2
        # and draws a box tightly around the title text).
        self._col = tk.Frame(self, bg=TM_SURFACE, bd=0, highlightthickness=0)
        self._col.pack(fill="both", expand=True, padx=14, pady=16)
        self._lbl = tk.Label(
            self._col,
            text=title,
            font=title_font(12, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            wraplength=130,
            justify="left",
            anchor="w",
            takefocus=0,
            **_no_chrome(),
        )
        self._lbl.pack(anchor="nw", pady=(4, 6))
        self._sub = None
        if subtitle:
            self._sub = tk.Label(
                self._col,
                text=subtitle,
                font=mono_font(8),
                bg=TM_SURFACE,
                fg=TM_META,
                wraplength=130,
                justify="left",
                anchor="w",
                takefocus=0,
                **_no_chrome(),
            )
            self._sub.pack(anchor="nw")
        for w in (self, self._col, self._lbl) + ((self._sub,) if self._sub else ()):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _set_rim(self, *, hover: bool) -> None:
        """Only the card perimeter changes; surface + ink stay constant."""
        try:
            if hover:
                self.configure(
                    bg=TM_SURFACE,
                    highlightthickness=2,
                    highlightbackground=TM_ACCENT,
                    highlightcolor=TM_ACCENT,
                )
            else:
                self.configure(
                    bg=TM_SURFACE,
                    highlightthickness=1,
                    highlightbackground=TM_HAIRLINE,
                    highlightcolor=TM_HAIRLINE,
                )
            self._col.configure(bg=TM_SURFACE)
            self._lbl.configure(bg=TM_SURFACE, fg=TM_INK)
            if self._sub is not None:
                self._sub.configure(bg=TM_SURFACE, fg=TM_META)
        except Exception:
            pass

    def _enter(self, _e=None):
        self._set_rim(hover=True)

    def _leave(self, _e=None):
        self._set_rim(hover=False)

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
        author: str = "",
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

        # Layout: cover | meta (tag/name/author) | foot (使用 button, fixed).
        # Author line was packed into the same body as the action button; with
        # fixed card height + pack_propagate(False) the blue「使用」button was
        # vertically clipped (looked "squeezed"). Foot is reserved so the
        # button always keeps full height. Index badge stays place()'d SE so
        # it never shares a pack-row with the button either.
        has_action = bool(action_text)
        foot_h = 36 if has_action else 0
        # Slightly lower cover ratio when action is shown so meta+foot fit
        cover_ratio = 0.52 if has_action else 0.58
        cover_h = max(int(height * cover_ratio), 96)
        # Cap cover so meta (tag+name+author ≈ 52px) + foot always fit
        meta_min = 52
        max_cover = max(height - meta_min - foot_h - 16, 96)
        cover_h = min(cover_h, max_cover)

        cover_box = tk.Frame(self, bg=TM_INSET, height=cover_h)
        cover_box.pack(side="top", fill="x")
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

        # Reserve foot before body expands, so「使用」is never clipped
        foot = None
        if has_action:
            foot = tk.Frame(self, bg=TM_SURFACE, height=foot_h)
            foot.pack(side="bottom", fill="x", padx=10, pady=(4, 8))
            foot.pack_propagate(False)
            widgets.append(foot)
            if on_action and not active:
                btn = tk.Button(
                    foot,
                    text=action_text,
                    font=title_font(9, "bold"),
                    bg=TM_ACCENT,
                    fg=TM_ACCENT_INK,
                    relief="flat",
                    cursor="hand2",
                    command=on_action,
                    bd=0,
                    padx=14,
                    pady=3,
                    highlightthickness=0,
                )
                btn.pack(side="left", anchor="w")
            elif active:
                soft = tk.Label(
                    foot,
                    text=action_text,
                    font=mono_font(8),
                    bg=TM_ACCENT_SOFT,
                    fg=TM_ACCENT,
                    padx=10,
                    pady=3,
                )
                soft.pack(side="left", anchor="w")
                widgets.append(soft)

        body = tk.Frame(self, bg=TM_SURFACE)
        body.pack(side="top", fill="both", expand=True, padx=10, pady=(6, 0))

        tag_lbl = tk.Label(
            body,
            text=(tag or "音色").upper() if (tag or "").isascii() else (tag or "音色"),
            font=mono_font(7),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
            **_no_chrome(),
        )
        tag_lbl.pack(anchor="w")
        name_lbl = tk.Label(
            body,
            text=name[:16],
            font=title_font(12 if focus else 11, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
            **_no_chrome(),
        )
        name_lbl.pack(anchor="w", pady=(2, 0))
        widgets.extend([body, name_lbl, tag_lbl, cover_box, self])
        author_s = (author or "").strip()
        auth_lbl = tk.Label(
            body,
            text=f"作者 · {author_s[:18]}" if author_s else "作者 · 未标注",
            font=mono_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
            **_no_chrome(),
        )
        auth_lbl.pack(anchor="w", pady=(1, 0))
        widgets.append(auth_lbl)

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
            # Bottom-right corner badge — absolute, never packs with「使用」
            idx = tk.Label(
                self,
                text=index_text,
                font=mono_font(8),
                bg=TM_SURFACE,
                fg=TM_META,
            )
            idx.place(relx=1.0, rely=1.0, x=-10, y=-8, anchor="se")
            widgets.append(idx)

        def _click(_e=None):
            if on_click:
                on_click()

        for w in widgets:
            w.bind("<Button-1>", _click)


class SearchField(tk.Frame):
    """Flat themed search input: mono glyph + placeholder (Schale library search).

    Kept visually quiet — hairline border, surface fill, no focus glow — so it
    reads as library chrome, not an AI-app input.
    """

    def __init__(
        self,
        master,
        *,
        placeholder: str = "搜索音色…",
        on_change: Optional[Callable[[str], None]] = None,
        width: int = 20,
        **kw,
    ):
        super().__init__(
            master,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            **kw,
        )
        self._on_change = on_change
        self._placeholder = placeholder
        self._ph_active = True

        row = tk.Frame(self, bg=TM_SURFACE, padx=10, pady=6)
        row.pack(fill="x")
        tk.Label(
            row, text="⌕", font=mono_font(12), bg=TM_SURFACE, fg=TM_META
        ).pack(side="left", padx=(0, 8))
        self.entry = tk.Entry(
            row,
            font=sans_font(10),
            bg=TM_SURFACE,
            fg=TM_META,
            relief="flat",
            bd=0,
            insertbackground=TM_INK,
            width=width,
            highlightthickness=0,
        )
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.insert(0, placeholder)
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)
        self.entry.bind("<KeyRelease>", self._changed)
        self._clear = tk.Label(
            row, text="✕", font=mono_font(9), bg=TM_SURFACE, fg=TM_META, cursor="hand2"
        )
        self._clear.bind("<Button-1>", lambda _e: self.reset())

    def query(self) -> str:
        return "" if self._ph_active else self.entry.get().strip()

    def reset(self) -> None:
        self.entry.delete(0, "end")
        self._show_placeholder()
        self._clear.pack_forget()
        if self._on_change:
            self._on_change("")

    def _show_placeholder(self) -> None:
        self._ph_active = True
        self.entry.delete(0, "end")
        self.entry.insert(0, self._placeholder)
        self.entry.configure(fg=TM_META)

    def _focus_in(self, _e=None) -> None:
        if self._ph_active:
            self._ph_active = False
            self.entry.delete(0, "end")
            self.entry.configure(fg=TM_INK)

    def _focus_out(self, _e=None) -> None:
        if not self.entry.get().strip():
            self._show_placeholder()

    def _changed(self, _e=None) -> None:
        has = bool(self.entry.get().strip()) and not self._ph_active
        if has:
            self._clear.pack(side="left", padx=(6, 0))
        else:
            self._clear.pack_forget()
        if self._on_change:
            self._on_change(self.query())


class SegmentControl(tk.Frame):
    """Schale-style pill segment for a small, mutually-exclusive option set."""

    def __init__(
        self,
        master,
        options: list[tuple[str, str]],
        *,
        value: Optional[str] = None,
        on_change: Optional[Callable[[str], None]] = None,
        **kw,
    ):
        super().__init__(master, bg=TM_INSET, **kw)
        self._on_change = on_change
        self._items: dict[str, NavItem] = {}
        self._value = value or (options[0][0] if options else "")
        for key, label in options:
            it = NavItem(self, label, key, self._pick, bg=TM_INSET)
            it.pack(side="left")
            self._items[key] = it
        self._refresh()

    def value(self) -> str:
        return self._value

    def set_value(self, key: str) -> None:
        if key in self._items:
            self._value = key
            self._refresh()

    def _pick(self, key: str) -> None:
        if key == self._value:
            return
        self._value = key
        self._refresh()
        if self._on_change:
            self._on_change(key)

    def _refresh(self) -> None:
        for k, it in self._items.items():
            it.set_active(k == self._value)


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
        if eyebrow:
            tk.Label(
                self,
                text=(
                    tracked(eyebrow, gap="  ")
                    if all(ord(c) < 128 for c in eyebrow)
                    else eyebrow
                ),
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
        ).pack(anchor="w", pady=(4, 0) if eyebrow else (0, 0))
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
