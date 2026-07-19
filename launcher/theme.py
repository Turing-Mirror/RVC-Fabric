# -*- coding: utf-8 -*-
"""Turing Mirror shell design tokens.

Layout / hierarchy inspired by Schale-Library (content-library chrome, cover
cards, section panels) and LyricsKara (serif wordmark scale, mono meta, stage
focus). Colors are a product-owned palette — not a copy of either site's CSS,
and not locked to the historical 白无垢 table.

Accent is an independent quiet teal-ink (not pure black, not BA #1289F0).
No blue-purple gradients, neon glow, or RVCMAX pink chrome.
"""

from __future__ import annotations

from typing import Final

# --- Canvas & surfaces (cool-neutral paper library) ---
TM_BG: Final[str] = "#f0efeb"
TM_SURFACE: Final[str] = "#fafaf7"
TM_SURFACE_HOVER: Final[str] = "#ffffff"
TM_INK: Final[str] = "#1f221f"
TM_INK_MUTED: Final[str] = "#7d7f78"
TM_META: Final[str] = "#9a9b93"
TM_INSET: Final[str] = "#e4e3dc"
TM_HAIRLINE: Final[str] = "#d6d4cb"

# Independent accent (quiet teal-slate) — CTA / active nav / selection edge
TM_ACCENT: Final[str] = "#3d5c55"
TM_ACCENT_INK: Final[str] = "#f7f8f6"
TM_ACCENT_SOFT: Final[str] = "#e6eeeb"  # soft wash behind active pills

# Semantic status (quiet, not neon)
TM_OK: Final[str] = "#4a7a68"
TM_WARN: Final[str] = "#a8894e"
TM_ERROR: Final[str] = "#8a4a48"

# Optional dark ink paper (reserved; shell is light-first)
TM_BG_DARK: Final[str] = "#1a1c1a"
TM_INK_DARK: Final[str] = "#e8e6de"

# Type stacks
FONT_SERIF: Final[tuple] = ("Georgia", "Noto Serif SC", "SimSun", "serif")
FONT_SANS: Final[tuple] = ("Segoe UI", "Microsoft YaHei UI", "sans-serif")
FONT_MONO: Final[tuple] = ("Cascadia Code", "Consolas", "monospace")

# Layout rhythm
PAD_X: Final[int] = 20
PAD_CARD: Final[int] = 14
NAV_HEIGHT: Final[int] = 56
BOTTOM_HEIGHT: Final[int] = 72
CARD_RADIUS_HINT: Final[int] = 8  # Tk cannot round; documented for future

APP_PRODUCT_NAME: Final[str] = "Turing Mirror 变声器"
APP_PRODUCT_TAGLINE: Final[str] = "与 Turing Mirror 配套"


def light_tokens() -> dict[str, str]:
    """Flat dict of light-theme color tokens (tests / GUI)."""
    return {
        "tm-bg": TM_BG,
        "tm-surface": TM_SURFACE,
        "tm-surface-hover": TM_SURFACE_HOVER,
        "tm-ink": TM_INK,
        "tm-ink-muted": TM_INK_MUTED,
        "tm-meta": TM_META,
        "tm-inset": TM_INSET,
        "tm-hairline": TM_HAIRLINE,
        "tm-accent": TM_ACCENT,
        "tm-accent-ink": TM_ACCENT_INK,
        "tm-accent-soft": TM_ACCENT_SOFT,
        "tm-ok": TM_OK,
        "tm-warn": TM_WARN,
        "tm-error": TM_ERROR,
    }


def forbidden_chrome_hexes() -> frozenset[str]:
    """Colors that must not be primary chrome (RVCMAX pink / AI purple / BA blue copy)."""
    return frozenset(
        {
            "#f7c9d4",
            "#f0a8bb",
            "#e89ab0",
            "#f0a0b4",
            "#7b6cf6",
            "#6a5ae0",
            "#3a3a42",
            "#1289f0",  # Schale primary — do not copy as our accent
            "#f32d90",  # BA pink
            "#2df3e0",  # BA cyan as brand fill
        }
    )


def serif_font(size: int, weight: str = "normal") -> tuple:
    family = FONT_SERIF[0]
    return (family, size, weight) if weight != "normal" else (family, size)


def sans_font(size: int, weight: str = "normal") -> tuple:
    family = FONT_SANS[0]
    return (family, size, weight) if weight != "normal" else (family, size)


def mono_font(size: int, weight: str = "normal") -> tuple:
    family = FONT_MONO[0]
    return (family, size, weight) if weight != "normal" else (family, size)
