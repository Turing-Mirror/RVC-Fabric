# -*- coding: utf-8 -*-
"""Turing Mirror shell design tokens.

Typography & layout methods from LyricsKara (tracked wordmark, mono meta,
stage hierarchy) and Schale-Library (segment nav, cover-first cards, panels).
Product-owned colors — not a hex copy of either site.
"""

from __future__ import annotations

from typing import Final, Sequence

# --- Canvas & surfaces ---
TM_BG: Final[str] = "#ebeae4"
TM_SURFACE: Final[str] = "#f7f6f2"
TM_SURFACE_HOVER: Final[str] = "#ffffff"
TM_INK: Final[str] = "#1a1d1b"
TM_INK_MUTED: Final[str] = "#6e726c"
TM_META: Final[str] = "#92968f"
TM_INSET: Final[str] = "#dddcd4"
TM_HAIRLINE: Final[str] = "#cccbc2"
TM_STAGE: Final[str] = "#e2e5e1"  # home stage band (slightly cooler wash)

TM_ACCENT: Final[str] = "#3d5c55"
TM_ACCENT_INK: Final[str] = "#f7f8f6"
TM_ACCENT_SOFT: Final[str] = "#dce8e4"

TM_OK: Final[str] = "#4a7a68"
TM_WARN: Final[str] = "#a8894e"
TM_ERROR: Final[str] = "#8a4a48"

TM_BG_DARK: Final[str] = "#1a1c1a"
TM_INK_DARK: Final[str] = "#e8e6de"

# Font stacks — prefer faces that read clearly on Chinese Windows
# Display (English wordmark / stage): serif tracking look
_FONT_DISPLAY: Final[tuple] = (
    "Cambria",
    "Georgia",
    "Palatino Linotype",
    "Times New Roman",
    "serif",
)
# Chinese page titles: YaHei UI (Schale-like clean UI face) then legacy
_FONT_TITLE: Final[tuple] = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "PingFang SC",
    "Noto Sans SC",
    "sans-serif",
)
# Body UI
_FONT_SANS: Final[tuple] = (
    "Microsoft YaHei UI",
    "Segoe UI",
    "Microsoft YaHei",
    "sans-serif",
)
# Meta / route / latency (LyricsKara mono)
_FONT_MONO: Final[tuple] = (
    "Cascadia Mono",
    "Cascadia Code",
    "Consolas",
    "Courier New",
    "monospace",
)

# Back-compat aliases used elsewhere
FONT_SERIF: Final[tuple] = _FONT_DISPLAY
FONT_SANS: Final[tuple] = _FONT_SANS
FONT_MONO: Final[tuple] = _FONT_MONO

# Layout rhythm (more air than old compact shell)
PAD_X: Final[int] = 28
PAD_CARD: Final[int] = 16
NAV_HEIGHT: Final[int] = 64
# Dock: single-row-ish mode + sliders + transport (taller window leaves body room)
BOTTOM_HEIGHT: Final[int] = 100
GUTTER: Final[int] = 32
# Default main window (bottom dock needs width; body needs height)
DEFAULT_WIN_W: Final[int] = 1120
DEFAULT_WIN_H: Final[int] = 780
MIN_WIN_W: Final[int] = 960
MIN_WIN_H: Final[int] = 640

APP_PRODUCT_NAME: Final[str] = "Turing Mirror 变声器"
APP_PRODUCT_TAGLINE: Final[str] = "TURING MIRROR · VOICE"
APP_WORDMARK: Final[str] = "TURING MIRROR"
APP_ROUTE: Final[str] = "voice.local"


def _family(families: Sequence[str]) -> str:
    """Return preferred family name; Tk falls back if missing on the system."""
    return families[0]


def _display() -> str:
    return _family(_FONT_DISPLAY)


def _title() -> str:
    return _family(_FONT_TITLE)


def _sans() -> str:
    return _family(_FONT_SANS)


def _mono() -> str:
    return _family(_FONT_MONO)


def tracked(text: str, *, gap: str = " ") -> str:
    """Letter-spacing approximation (Tk has no CSS letter-spacing).

    Latin words get inter-letter gaps; spaces between words become a double gap.
    CJK strings are left unchanged.
    """
    s = (text or "").strip()
    if not s:
        return s
    if any(ord(c) >= 128 and not c.isspace() for c in s):
        return s
    words = s.split()
    spaced = [gap.join(list(w)) for w in words]
    return (gap * 3).join(spaced)


def display_font(size: int, weight: str = "normal") -> tuple:
    """English wordmark / display serif."""
    f = _display()
    return (f, size, weight) if weight != "normal" else (f, size)


def title_font(size: int, weight: str = "bold") -> tuple:
    """Chinese / page hero titles (YaHei UI)."""
    f = _title()
    return (f, size, weight) if weight != "normal" else (f, size)


def serif_font(size: int, weight: str = "normal") -> tuple:
    """Alias: display serif (legacy name)."""
    return display_font(size, weight)


def sans_font(size: int, weight: str = "normal") -> tuple:
    f = _sans()
    return (f, size, weight) if weight != "normal" else (f, size)


def mono_font(size: int, weight: str = "normal") -> tuple:
    f = _mono()
    return (f, size, weight) if weight != "normal" else (f, size)


def light_tokens() -> dict[str, str]:
    return {
        "tm-bg": TM_BG,
        "tm-surface": TM_SURFACE,
        "tm-surface-hover": TM_SURFACE_HOVER,
        "tm-ink": TM_INK,
        "tm-ink-muted": TM_INK_MUTED,
        "tm-meta": TM_META,
        "tm-inset": TM_INSET,
        "tm-hairline": TM_HAIRLINE,
        "tm-stage": TM_STAGE,
        "tm-accent": TM_ACCENT,
        "tm-accent-ink": TM_ACCENT_INK,
        "tm-accent-soft": TM_ACCENT_SOFT,
        "tm-ok": TM_OK,
        "tm-warn": TM_WARN,
        "tm-error": TM_ERROR,
    }


def forbidden_chrome_hexes() -> frozenset[str]:
    return frozenset(
        {
            "#f7c9d4",
            "#f0a8bb",
            "#e89ab0",
            "#f0a0b4",
            "#7b6cf6",
            "#6a5ae0",
            "#3a3a42",
            "#1289f0",
            "#f32d90",
            "#2df3e0",
        }
    )
