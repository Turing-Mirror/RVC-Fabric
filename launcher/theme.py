# -*- coding: utf-8 -*-
"""RVC Fabric shell design tokens.

Typography & layout methods from LyricsKara (tracked wordmark, mono meta,
stage hierarchy) and Schale-Library (segment nav, cover-first cards, panels).
Product-owned colors — not a hex copy of either site.
"""

from __future__ import annotations

from typing import Final, Sequence

# --- Canvas & surfaces ---
# Palette copied from the Schale-Library project (frontend globals.css) —
# light-blue library look. Primary = BA blue #1289F0. We deliberately DO NOT
# use Schale's cyan accent #2DF3E0 (no teal per product direction); blue carries
# both primary and the live/active state. Values are Schale tokens 1:1 unless a
# note says otherwise (readability nudges for desktop Tk text).
TM_BG: Final[str] = "#f7f9fb"  # Schale --background
TM_SURFACE: Final[str] = "#ffffff"  # Schale --card
TM_SURFACE_HOVER: Final[str] = "#f0f4f8"  # Schale --muted (subtle hover on white)
TM_INK: Final[str] = "#2b333e"  # Schale --foreground / --ba-dark
# Form field labels / secondary body — darker than Schale muted-foreground so
# Tk labels stay crisp on white
TM_INK_MUTED: Final[str] = "#46525f"
# Helper prose under settings rows = Schale --muted-foreground
TM_HELP: Final[str] = "#5a6a7a"
# True meta: mono eyebrows, route, timestamps (slightly lighter than help)
TM_META: Final[str] = "#6e7d8c"
TM_INSET: Final[str] = "#f0f4f8"  # Schale --muted (cover placeholder / badge bg)
TM_HAIRLINE: Final[str] = "#d6e4f0"  # Schale --border
TM_STAGE: Final[str] = "#e8f4fd"  # Schale --secondary (home stage band, light blue)

TM_ACCENT: Final[str] = "#1289f0"  # Schale --primary (BA blue)
TM_ACCENT_INK: Final[str] = "#ffffff"  # Schale --primary-foreground
TM_ACCENT_SOFT: Final[str] = "#e8f4fd"  # Schale --secondary (active nav soft)

TM_OK: Final[str] = "#1178d6"  # deeper blue for live/ok (no green/teal)
TM_WARN: Final[str] = "#b5791c"  # restrained amber (Schale has no warn token)
TM_ERROR: Final[str] = "#e53e3e"  # Schale --destructive

TM_BG_DARK: Final[str] = "#1a1f2e"  # Schale dark --background
TM_INK_DARK: Final[str] = "#e8f4fd"  # Schale dark --foreground

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

# Layout rhythm — air like Schale cards / LyricsKara stage padding
PAD_X: Final[int] = 36
PAD_CARD: Final[int] = 18
NAV_HEIGHT: Final[int] = 68
# Player-style dock: room for now-playing lines + param tiles (no clip)
BOTTOM_HEIGHT: Final[int] = 168
GUTTER: Final[int] = 36
# Wider default so dock tiles + page content breathe
DEFAULT_WIN_W: Final[int] = 1320
DEFAULT_WIN_H: Final[int] = 900
MIN_WIN_W: Final[int] = 1100
MIN_WIN_H: Final[int] = 740

# --- HiDPI scaling ---
# The shell declares DPI awareness at startup (win_util.enable_dpi_awareness);
# point-size fonts then scale via `tk scaling`, but raw pixel values (geometry,
# wraplength, fixed card sizes) do not — they go through px().
# Anti-double-scaling contract: px() may appear only (a) at the outermost
# page/entry call site, or (b) inside a composite widget's __init__ for its
# OWN constants. Widget width=/height= parameters are design units — the
# widget itself applies px(); callers pass bare numbers.
_SCALE: float = 1.0


def set_scale_from_dpi(dpi: int) -> None:
    """Record UI scale from monitor DPI (96 → 1.0). Never scales below 1."""
    global _SCALE
    try:
        _SCALE = max(1.0, float(dpi) / 96.0)
    except (TypeError, ValueError):
        _SCALE = 1.0


def scale() -> float:
    return _SCALE


def px(n: int) -> int:
    """Design-unit pixels → physical pixels. Exact identity at 96 dpi."""
    return n if _SCALE == 1.0 else round(n * _SCALE)


APP_PRODUCT_NAME: Final[str] = "RVC Fabric"
APP_PRODUCT_TAGLINE: Final[str] = "就绪"
APP_WORDMARK: Final[str] = "RVC Fabric · 图灵镜"
# Deprecated decorative route string (kept empty; UI no longer shows it)
APP_ROUTE: Final[str] = ""


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


def meta_font(text: str, size: int = 8) -> tuple:
    """Meta caption font for text that may be ASCII or CJK.

    Cascadia Mono carries no CJK glyphs — Tk falls back per-glyph and small
    grey captions render mushy. ASCII keeps the mono eyebrow look; CJK goes sans.
    """
    return mono_font(size) if (text or "").isascii() else sans_font(size)


def light_tokens() -> dict[str, str]:
    return {
        "tm-bg": TM_BG,
        "tm-surface": TM_SURFACE,
        "tm-surface-hover": TM_SURFACE_HOVER,
        "tm-ink": TM_INK,
        "tm-ink-muted": TM_INK_MUTED,
        "tm-help": TM_HELP,
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
    # BA blue #1289f0 is now the sanctioned primary (copied from Schale-Library
    # per product direction). Still forbidden: RVCMAX pinks, AI purples, and
    # Schale's cyan/pink accents — no teal, no high-sat AI chrome.
    return frozenset(
        {
            "#f7c9d4",
            "#f0a8bb",
            "#e89ab0",
            "#f0a0b4",
            "#7b6cf6",
            "#6a5ae0",
            "#3a3a42",
            "#f32d90",  # Schale BA pink — not used
            "#2df3e0",  # Schale BA cyan/teal — no teal
        }
    )
