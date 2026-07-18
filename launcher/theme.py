# -*- coding: utf-8 -*-
"""Turing Mirror 「白无垢」tokens for desktop shells (bootstrap + main app).

Mirrors docs/UI-AESTHETIC-DESIGN.md light theme. Accent = ink (no brand hue).
No blue-purple gradients, neon, or RVCMAX pink chrome.
"""

from __future__ import annotations

from typing import Final

# Light canvas (warm paper) — primary product theme
TM_BG: Final[str] = "#f4f1ea"
TM_SURFACE: Final[str] = "#faf8f4"  # solid approx of rgba white 0.48 on paper
TM_SURFACE_HOVER: Final[str] = "#ffffff"
TM_INK: Final[str] = "#1c1a17"
TM_INK_MUTED: Final[str] = "#9a948a"
TM_META: Final[str] = "#b0a99d"
TM_INSET: Final[str] = "#e8e4dc"  # low-contrast group divider
TM_HAIRLINE: Final[str] = "#e0dbd2"
TM_ACCENT: Final[str] = TM_INK  # ink-only accent
TM_ACCENT_INK: Final[str] = "#ffffff"
TM_OK: Final[str] = "#5c7a6b"  # quiet green (type Image), not neon
TM_WARN: Final[str] = "#a8894e"  # quiet amber (type Chat)

# Dark ink paper (optional)
TM_BG_DARK: Final[str] = "#1c1b18"
TM_INK_DARK: Final[str] = "#ece3d0"

# Type stacks (Windows-friendly approximations of Songti / system sans)
FONT_SERIF: Final[tuple] = ("Georgia", "Noto Serif SC", "SimSun", "serif")
FONT_SANS: Final[tuple] = ("Segoe UI", "Microsoft YaHei UI", "sans-serif")
FONT_MONO: Final[tuple] = ("Cascadia Code", "Consolas", "monospace")

APP_PRODUCT_NAME: Final[str] = "Turing Mirror 变声器"
APP_PRODUCT_TAGLINE: Final[str] = "与 Turing Mirror 配套 · 白无垢"


def light_tokens() -> dict[str, str]:
    """Return a flat dict of light-theme color tokens (for tests and GUI)."""
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
    }


def forbidden_chrome_hexes() -> frozenset[str]:
    """Colors that must not be primary chrome (RVCMAX pink / AI purple)."""
    return frozenset(
        {
            "#f7c9d4",
            "#f0a8bb",
            "#e89ab0",
            "#f0a0b4",
            "#7b6cf6",
            "#6a5ae0",
            "#3a3a42",  # dark pill chrome from old RVCMAX-ish shell
        }
    )


def serif_font(size: int, weight: str = "normal") -> tuple:
    family = FONT_SERIF[0]
    return (family, size, weight) if weight != "normal" else (family, size)


def sans_font(size: int, weight: str = "normal") -> tuple:
    family = FONT_SANS[0]
    return (family, size, weight) if weight != "normal" else (family, size)
