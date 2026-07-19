# -*- coding: utf-8 -*-
"""Keyboard shortcuts for the consumer main app.

- In-app bindings (Tk) when the window has focus
- Optional Windows global hotkeys (game overlay friendly)
- User-editable mapping stored in app_config.json under ``hotkeys``
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Action catalog
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HotkeyAction:
    id: str
    label: str
    group: str  # voice | transport | nav | misc
    global_ok: bool = True  # allow global register


ACTIONS: list[HotkeyAction] = [
    HotkeyAction("prev_model", "上一个音色", "voice", True),
    HotkeyAction("next_model", "下一个音色", "voice", True),
    HotkeyAction("select_model_1", "快捷选音色 1", "voice", True),
    HotkeyAction("select_model_2", "快捷选音色 2", "voice", True),
    HotkeyAction("select_model_3", "快捷选音色 3", "voice", True),
    HotkeyAction("select_model_4", "快捷选音色 4", "voice", True),
    HotkeyAction("select_model_5", "快捷选音色 5", "voice", True),
    HotkeyAction("select_model_6", "快捷选音色 6", "voice", True),
    HotkeyAction("select_model_7", "快捷选音色 7", "voice", True),
    HotkeyAction("select_model_8", "快捷选音色 8", "voice", True),
    HotkeyAction("select_model_9", "快捷选音色 9", "voice", True),
    HotkeyAction("toggle_vc", "开启 / 停止变声", "transport", True),
    HotkeyAction("pitch_up", "音高 +1", "voice", True),
    HotkeyAction("pitch_down", "音高 -1", "voice", True),
    HotkeyAction("toggle_monitor", "开关「监听自己」", "transport", True),
    HotkeyAction("toggle_mode", "变声 / 原声旁路切换", "transport", True),
    HotkeyAction("page_home", "打开首页", "nav", False),
    HotkeyAction("page_models", "打开模型页", "nav", False),
    HotkeyAction("page_settings", "打开设置页", "nav", False),
    HotkeyAction("page_more", "打开其他页", "nav", False),
    HotkeyAction("show_hotkeys", "显示快捷键说明", "misc", False),
    HotkeyAction("undo_voice", "撤销音色参数", "voice", False),
    HotkeyAction("redo_voice", "重做音色参数", "voice", False),
    HotkeyAction("reset_voice", "音色参数恢复默认", "voice", False),
]

ACTION_BY_ID: dict[str, HotkeyAction] = {a.id: a for a in ACTIONS}

# Human-readable defaults (modifiers + key, joined by +)
DEFAULT_HOTKEYS: dict[str, str] = {
    "prev_model": "Left",
    "next_model": "Right",
    "toggle_vc": "F5",
    "pitch_up": "Ctrl+Up",
    "pitch_down": "Ctrl+Down",
    "toggle_monitor": "Ctrl+M",
    "toggle_mode": "Ctrl+B",
    "page_home": "Ctrl+1",
    "page_models": "Ctrl+2",
    "page_settings": "Ctrl+3",
    "page_more": "Ctrl+4",
    "show_hotkeys": "F1",
    "undo_voice": "Ctrl+Z",
    "redo_voice": "Ctrl+Y",
    "reset_voice": "Ctrl+0",
    "select_model_1": "Ctrl+Alt+1",
    "select_model_2": "Ctrl+Alt+2",
    "select_model_3": "Ctrl+Alt+3",
    "select_model_4": "Ctrl+Alt+4",
    "select_model_5": "Ctrl+Alt+5",
    "select_model_6": "Ctrl+Alt+6",
    "select_model_7": "Ctrl+Alt+7",
    "select_model_8": "Ctrl+Alt+8",
    "select_model_9": "Ctrl+Alt+9",
}

# Actions that should register as Windows global hotkeys when enabled
DEFAULT_GLOBAL_ACTIONS: tuple[str, ...] = (
    "prev_model",
    "next_model",
    "toggle_vc",
    "pitch_up",
    "pitch_down",
    "toggle_monitor",
    "toggle_mode",
    "select_model_1",
    "select_model_2",
    "select_model_3",
    "select_model_4",
    "select_model_5",
    "select_model_6",
    "select_model_7",
    "select_model_8",
    "select_model_9",
)

# Canonical key token → (tk suffix, VK code)
# tk suffix is used after modifiers, e.g. Control-Left, F5, Key-1
_KEY_TABLE: dict[str, tuple[str, int]] = {
    "left": ("Left", 0x25),
    "right": ("Right", 0x27),
    "up": ("Up", 0x26),
    "down": ("Down", 0x28),
    "space": ("space", 0x20),
    "tab": ("Tab", 0x09),
    "escape": ("Escape", 0x1B),
    "esc": ("Escape", 0x1B),
    "return": ("Return", 0x0D),
    "enter": ("Return", 0x0D),
    "backspace": ("BackSpace", 0x08),
    "delete": ("Delete", 0x2E),
    "home": ("Home", 0x24),
    "end": ("End", 0x23),
    "prior": ("Prior", 0x21),
    "pageup": ("Prior", 0x21),
    "next": ("Next", 0x22),
    "pagedown": ("Next", 0x22),
    "insert": ("Insert", 0x2D),
    "f1": ("F1", 0x70),
    "f2": ("F2", 0x71),
    "f3": ("F3", 0x72),
    "f4": ("F4", 0x73),
    "f5": ("F5", 0x74),
    "f6": ("F6", 0x75),
    "f7": ("F7", 0x76),
    "f8": ("F8", 0x77),
    "f9": ("F9", 0x78),
    "f10": ("F10", 0x79),
    "f11": ("F11", 0x7A),
    "f12": ("F12", 0x7B),
    "plus": ("plus", 0xBB),
    "minus": ("minus", 0xBD),
    "equal": ("equal", 0xBB),
    "comma": ("comma", 0xBC),
    "period": ("period", 0xBE),
    "slash": ("slash", 0xBF),
    "backslash": ("backslash", 0xDC),
    "bracketleft": ("bracketleft", 0xDB),
    "bracketright": ("bracketright", 0xDD),
    "semicolon": ("semicolon", 0xBA),
    "quote": ("quoteright", 0xDE),
    "grave": ("grave", 0xC0),
}

# Modifier aliases
_MOD_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "ctl": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "option": "alt",
    "meta": "alt",
    "win": "win",
    "windows": "win",
    "super": "win",
    "cmd": "win",
}


def normalize_hotkey(spec: str) -> str:
    """Normalize user input to Canonical form e.g. ``Ctrl+Shift+F5``."""
    if not spec or not str(spec).strip():
        return ""
    parts = [p.strip() for p in str(spec).replace("-", "+").split("+") if p.strip()]
    mods: list[str] = []
    key = ""
    for p in parts:
        low = p.lower()
        if low in _MOD_ALIASES:
            m = _MOD_ALIASES[low]
            label = {"ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "win": "Win"}[m]
            if label not in mods:
                mods.append(label)
            continue
        # key token
        key = p
    if not key:
        return ""
    # Normalize key casing
    klow = key.lower()
    if klow in _KEY_TABLE:
        key = _KEY_TABLE[klow][0]
        # Prefer friendly names
        friendly = {
            "Prior": "PageUp",
            "Next": "PageDown",
            "BackSpace": "Backspace",
            "space": "Space",
        }
        key = friendly.get(key, key if len(key) > 1 else key.upper())
    elif len(key) == 1:
        key = key.upper()
    else:
        # F-keys already handled; keep title case for unknown
        key = key[:1].upper() + key[1:].lower() if key.isalpha() else key
    # Stable mod order
    order = ["Ctrl", "Alt", "Shift", "Win"]
    mods_sorted = [m for m in order if m in mods]
    return "+".join(mods_sorted + [key])


def _parse_parts(spec: str) -> tuple[set[str], str]:
    """Return (mod set lowercase, key_token lowercase)."""
    norm = normalize_hotkey(spec)
    if not norm:
        return set(), ""
    parts = norm.split("+")
    mods: set[str] = set()
    key = parts[-1]
    for p in parts[:-1]:
        mods.add(p.lower())
    return mods, key.lower()


def to_tk_sequence(spec: str) -> Optional[str]:
    """Convert ``Ctrl+Alt+1`` → ``<Control-Alt-Key-1>`` for Tk bind."""
    mods, key = _parse_parts(spec)
    if not key:
        return None
    tk_mods: list[str] = []
    if "ctrl" in mods:
        tk_mods.append("Control")
    if "alt" in mods:
        tk_mods.append("Alt")
    if "shift" in mods:
        tk_mods.append("Shift")
    # Win/Super not reliably available on all Tk builds — skip for in-app

    if key in _KEY_TABLE:
        tk_key = _KEY_TABLE[key][0]
        # Prefer PageUp naming consistency in table already
        if tk_key == "Prior":
            tk_key = "Prior"
        elif tk_key == "Next":
            tk_key = "Next"
    elif len(key) == 1 and key.isalnum():
        tk_key = f"Key-{key.upper()}" if key.isdigit() else f"Key-{key.lower()}"
    else:
        tk_key = key.capitalize() if key.isalpha() else key

    body = "-".join(tk_mods + [tk_key]) if tk_mods else tk_key
    return f"<{body}>"


def to_win_hotkey(spec: str) -> Optional[tuple[int, int]]:
    """Convert to (fsModifiers, vk) for RegisterHotKey, or None if invalid."""
    mods, key = _parse_parts(spec)
    if not key:
        return None
    # MOD_ALT=1 MOD_CONTROL=2 MOD_SHIFT=4 MOD_WIN=8 MOD_NOREPEAT=0x4000
    flags = 0x4000
    if "alt" in mods:
        flags |= 0x0001
    if "ctrl" in mods:
        flags |= 0x0002
    if "shift" in mods:
        flags |= 0x0004
    if "win" in mods:
        flags |= 0x0008

    if key in _KEY_TABLE:
        vk = _KEY_TABLE[key][1]
    elif len(key) == 1 and "a" <= key <= "z":
        vk = ord(key.upper())
    elif len(key) == 1 and "0" <= key <= "9":
        vk = ord(key)
    else:
        return None
    return flags, vk


def merge_hotkeys(cfg_hotkeys: Any) -> dict[str, str]:
    """Merge user config with defaults; drop unknown / empty overrides."""
    out = dict(DEFAULT_HOTKEYS)
    if not isinstance(cfg_hotkeys, dict):
        return out
    for k, v in cfg_hotkeys.items():
        if k not in ACTION_BY_ID:
            continue
        if v is None or str(v).strip() == "":
            # empty = unbound
            out[k] = ""
            continue
        norm = normalize_hotkey(str(v))
        if norm:
            out[k] = norm
    return out


def find_duplicate_bindings(mapping: dict[str, str]) -> list[tuple[str, list[str]]]:
    """Return list of (normalized_key, [action_ids]) for collisions."""
    inv: dict[str, list[str]] = {}
    for aid, spec in mapping.items():
        if not spec:
            continue
        n = normalize_hotkey(spec)
        if not n:
            continue
        inv.setdefault(n, []).append(aid)
    return [(k, ids) for k, ids in inv.items() if len(ids) > 1]


def format_help_text(mapping: Optional[dict[str, str]] = None) -> str:
    """Multi-line help for the shortcuts dialog."""
    m = merge_hotkeys(mapping)
    groups = [
        ("voice", "音色与音高"),
        ("transport", "变声控制"),
        ("nav", "页面切换（仅窗口内）"),
        ("misc", "其他"),
    ]
    lines = [
        "【快捷键】",
        "· 默认在变声器窗口内生效。",
        "· 可在「设置 → 快捷键」自定义；可选开启「全局快捷键」以便游戏中切换。",
        "· 全局快捷键请用带 Ctrl/Alt/Shift 的组合键，或 F1–F12（纯方向键不会注册为全局，以免抢系统按键）。",
        "· 在输入框内打字时，窗口内快捷键不会触发。",
        "",
    ]
    by_group: dict[str, list[HotkeyAction]] = {}
    for a in ACTIONS:
        by_group.setdefault(a.group, []).append(a)
    for gid, title in groups:
        lines.append(f"—— {title} ——")
        for a in by_group.get(gid, []):
            key = m.get(a.id) or "（未绑定）"
            lines.append(f"  {a.label}：{key}")
        lines.append("")
    lines.append("提示：变声运行中切换音色会自动重启引擎加载新模型。")
    return "\n".join(lines)


# Widgets that should swallow keys instead of app hotkeys
_FOCUS_SKIP_CLASSES = frozenset(
    {
        "Entry",
        "Text",
        "TEntry",
        "TCombobox",
        "Combobox",
        "Spinbox",
        "TSpinbox",
        "Listbox",
        "Toplevel",
    }
)


def focus_should_skip_hotkey(widget) -> bool:
    """True when keyboard focus is in a text-like control."""
    if widget is None:
        return False
    try:
        cls = widget.winfo_class()
    except Exception:
        return False
    if cls in _FOCUS_SKIP_CLASSES:
        return True
    # Some ttk comboboxes report TCombobox
    name = str(cls).lower()
    return name in ("entry", "text", "tentry", "tcombobox", "spinbox", "listbox")


# ---------------------------------------------------------------------------
# Windows global hotkeys via RegisterHotKey
# ---------------------------------------------------------------------------

class GlobalHotkeyManager:
    """Register system-wide hotkeys; poll via Tk ``after`` loop."""

    WM_HOTKEY = 0x0312
    # id base; keep in 1..0xBFFF
    _ID_BASE = 0x5000

    def __init__(self) -> None:
        self._registered: dict[int, str] = {}  # hotkey id → action id
        self._hwnd = None
        self._user32 = None
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled and bool(self._registered)

    def unregister_all(self) -> None:
        if sys.platform != "win32" or not self._user32:
            self._registered.clear()
            self._enabled = False
            return
        for hid in list(self._registered.keys()):
            try:
                self._user32.UnregisterHotKey(self._hwnd, hid)
            except Exception:
                pass
        self._registered.clear()
        self._enabled = False

    def register(
        self,
        hwnd,
        mapping: dict[str, str],
        action_ids: Optional[list[str]] = None,
    ) -> list[str]:
        """Register global hotkeys. Returns list of human-readable failures."""
        self.unregister_all()
        if sys.platform != "win32":
            return ["全局快捷键仅支持 Windows"]
        try:
            import ctypes
            from ctypes import wintypes

            self._user32 = ctypes.windll.user32
            self._hwnd = int(hwnd) if hwnd else None
        except Exception as e:
            return [f"无法加载 user32：{e}"]

        # Prefer top-level HWND (Tk root.winfo_id may be child)
        try:
            parent = self._user32.GetParent(self._hwnd)
            if parent:
                self._hwnd = parent
        except Exception:
            pass

        ids = action_ids if action_ids is not None else list(DEFAULT_GLOBAL_ACTIONS)
        failures: list[str] = []
        used_vk: set[tuple[int, int]] = set()

        for i, aid in enumerate(ids):
            act = ACTION_BY_ID.get(aid)
            if not act or not act.global_ok:
                continue
            spec = mapping.get(aid) or ""
            if not spec:
                continue
            parsed = to_win_hotkey(spec)
            if not parsed:
                failures.append(f"{act.label}：无法解析「{spec}」")
                continue
            flags, vk = parsed
            # Refuse bare keys without modifiers (except F1–F12) — would steal system input
            mod_bits = flags & 0x000F  # alt|ctrl|shift|win
            is_fn = 0x70 <= vk <= 0x7B
            if mod_bits == 0 and not is_fn:
                failures.append(
                    f"{act.label}（{spec}）：全局快捷键需带 Ctrl/Alt/Shift，"
                    "或使用 F1–F12（避免抢走方向键/字母）"
                )
                continue
            if (flags, vk) in used_vk:
                failures.append(f"{act.label}：与其它全局键冲突「{spec}」")
                continue
            hid = self._ID_BASE + i
            ok = self._user32.RegisterHotKey(self._hwnd, hid, flags, vk)
            if not ok:
                failures.append(
                    f"{act.label}（{spec}）：注册失败（可能被其它软件占用）"
                )
                continue
            used_vk.add((flags, vk))
            self._registered[hid] = aid

        self._enabled = bool(self._registered)
        return failures

    def poll_once(self) -> Optional[str]:
        """Non-blocking peek for WM_HOTKEY only (does not steal Tk messages)."""
        if not self._enabled or sys.platform != "win32" or not self._user32:
            return None
        try:
            import ctypes
            from ctypes import wintypes

            class MSG(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM),
                    ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD),
                    ("pt_x", wintypes.LONG),
                    ("pt_y", wintypes.LONG),
                ]

            msg = MSG()
            # Filter only WM_HOTKEY so we never starve Tk's queue
            # PM_REMOVE = 1
            found: Optional[str] = None
            while self._user32.PeekMessageW(
                ctypes.byref(msg),
                0,
                self.WM_HOTKEY,
                self.WM_HOTKEY,
                1,
            ):
                hid = int(msg.wParam)
                aid = self._registered.get(hid)
                if aid and found is None:
                    found = aid
            return found
        except Exception:
            return None


def event_to_hotkey_spec(event) -> str:
    """Build a normalized hotkey string from a Tk KeyPress event (for capture UI)."""
    try:
        keysym = str(getattr(event, "keysym", "") or "")
        state = int(getattr(event, "state", 0) or 0)
    except Exception:
        return ""
    if not keysym:
        return ""
    # Ignore pure modifier presses
    if keysym.lower() in (
        "shift_l",
        "shift_r",
        "control_l",
        "control_r",
        "alt_l",
        "alt_r",
        "meta_l",
        "meta_r",
        "win_l",
        "win_r",
        "caps_lock",
    ):
        return ""
    mods: list[str] = []
    # Tk state bits: Shift=0x1, Control=0x4, Alt/Mod1=0x20000 (platform varies)
    if state & 0x4:
        mods.append("Ctrl")
    if state & 0x20000 or state & 0x8:  # Alt / Mod1 common masks
        # Avoid double-counting when key itself is Alt
        if keysym.lower() not in ("alt_l", "alt_r"):
            # On Windows Alt is often 0x20000
            if state & 0x20000:
                mods.append("Alt")
    if state & 0x1:
        mods.append("Shift")
    # Normalize keysym to our table
    ks = keysym
    mapping = {
        "Prior": "PageUp",
        "Next": "PageDown",
        "BackSpace": "Backspace",
        "Return": "Enter",
        "Escape": "Esc",
    }
    ks = mapping.get(ks, ks)
    if len(ks) == 1:
        ks = ks.upper()
    parts = mods + [ks]
    return normalize_hotkey("+".join(parts))
