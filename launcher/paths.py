# -*- coding: utf-8 -*-
"""Release layout paths — RVCMAX *roles*, RVC Fabric product naming.

Roles::

    first-run helper  → 启动器.exe  / launcher/bootstrap.py  (dev)
    consumer App      → 变声器.exe  / launcher/main_app.py   (dev)
    engine            → package root (infer*, assets)
    User_Data         → models + config + logs
    VBCABLE           → virtual cable installers
    Runtime           → embedded Python (required for release)

Dev uses repo root + system/Runtime python + .bat/.vbs.
Release uses root *.exe + Runtime/ + bundled User_Data/models + VBCABLE.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from launcher.catalog import list_voice_catalog
from launcher.theme import APP_PRODUCT_NAME, APP_PRODUCT_TAGLINE


def _detect_root() -> Path:
    """Package root: directory containing Runtime/User_Data or repo root."""
    if getattr(sys, "frozen", False):
        # PyInstaller onefile/onedir: exe sits at release root
        return Path(sys.executable).resolve().parent
    here = Path(__file__).resolve().parent.parent
    # If running from source but cwd is a release tree, prefer cwd with Runtime
    cwd = Path.cwd()
    if (cwd / "Runtime" / "python.exe").is_file() and (
        (cwd / "User_Data").is_dir() or (cwd / "变声器.exe").is_file()
    ):
        return cwd
    return here


ROOT = _detect_root()

# Runtime embed (release MUST ship this)
if (ROOT / "Runtime").is_dir():
    RUNTIME_DIR = ROOT / "Runtime"
elif (ROOT / "runtime").is_dir():
    RUNTIME_DIR = ROOT / "runtime"
else:
    RUNTIME_DIR = ROOT / "Runtime"

# User data
if (ROOT / "User_Data").is_dir() or not (ROOT / "UserData").is_dir():
    USER_DATA = ROOT / "User_Data"
else:
    USER_DATA = ROOT / "UserData"

MODELS_DIR = USER_DATA / "models"
USER_LOGS = USER_DATA / "logs"
# Local character covers (mirrors CNB ch-banner/). config.json cover:
#   "ch-banner/<id>.jpg"  or  "<id>.jpg" under this folder
CH_BANNER_DIR = USER_DATA / "ch-banner"
# Default browse target for 绑定 index / 导入·导出档案 — a stable in-app folder
# so users can drop reusable files here, yet still navigate out to their own.
INDICES_DIR = USER_DATA / "indices"
SHARED_PROFILES_DIR = USER_DATA / "shared_profiles"
WALLPAPER_DIR = USER_DATA / "wallpaper"
VBCABLE_DIR = ROOT / "VBCABLE"

ENGINE_WEIGHTS = ROOT / "assets" / "weights"
WEIGHTS = ENGINE_WEIGHTS
HUBERT = ROOT / "assets" / "hubert" / "hubert_base.pt"
RMVPE = ROOT / "assets" / "rmvpe" / "rmvpe.pt"

# Product brand art (window icon + in-app logo)
BRAND_DIR = ROOT / "assets" / "brand"
BRAND_ICO = BRAND_DIR / "app.ico"
BRAND_LOGO = BRAND_DIR / "RVC_Fabric.png"  # square mark for stage / tray
BRAND_LOGO_UI = BRAND_DIR / "logo_ui.png"  # ~256px home stage
BRAND_LOGO_NAV = BRAND_DIR / "logo_nav.png"  # ~64px chrome

CONFIG_PATH = USER_DATA / "app_config.json"
SHORTCUT_NAME = "RVC Fabric.lnk"
APP_TITLE = APP_PRODUCT_NAME
APP_BRAND = APP_PRODUCT_TAGLINE

# Canonical release exe names (ASCII-safe + Chinese brand)
EXE_BOOTSTRAP_NAMES = ("启动器.exe", "TM_Setup.exe", "bootstrap.exe")
EXE_APP_NAMES = (
    "RVC Fabric.exe",
    "RVC_Fabric.exe",
    "变声器.exe",
    "TM_Voice.exe",
    "RVC变声器.exe",
    "main_app.exe",
)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_release_layout() -> bool:
    """True when a usable Runtime is available (local or RVCMAX ref)."""
    for base in (
        ROOT / "Runtime",
        ROOT / "runtime",
        ROOT / "RVCMAX" / "RVCMAX_Nvidia_xiaoyuan" / "Runtime",
    ):
        if (base / "python.exe").is_file():
            return True
    return False


def find_release_exe(kind: str = "app") -> Path | None:
    """Locate packaged GUI exe next to ROOT."""
    names = EXE_APP_NAMES if kind == "app" else EXE_BOOTSTRAP_NAMES
    for n in names:
        p = ROOT / n
        if p.is_file():
            return p
    return None


def ensure_dirs() -> None:
    USER_DATA.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    CH_BANNER_DIR.mkdir(parents=True, exist_ok=True)
    INDICES_DIR.mkdir(parents=True, exist_ok=True)
    SHARED_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
    USER_LOGS.mkdir(parents=True, exist_ok=True)
    VBCABLE_DIR.mkdir(parents=True, exist_ok=True)
    ENGINE_WEIGHTS.mkdir(parents=True, exist_ok=True)
    (ROOT / "logs").mkdir(parents=True, exist_ok=True)
    # Optional package-root ch-banner (read-only ships / shared banners)
    (ROOT / "ch-banner").mkdir(parents=True, exist_ok=True)
    # Never leave foreign absolute model paths in configs/inuse (release pollution)
    try:
        from launcher.inuse_config import ensure_clean_inuse_config

        ensure_clean_inuse_config(ROOT)
    except Exception:
        pass


def release_roles() -> dict[str, str]:
    return {
        "first_run_helper": "启动器.exe (release) / launcher/bootstrap.py (dev)",
        "consumer_app": "变声器.exe (release) / launcher/main_app.py (dev)",
        "engine_core": str(ROOT),
        "user_data": str(USER_DATA),
        "models_catalog": str(MODELS_DIR),
        "vbcable": str(VBCABLE_DIR),
        "runtime_hook": str(RUNTIME_DIR),
        "advanced_webui": "go-web.bat (developer only)",
        "is_release_layout": str(is_release_layout()),
        "is_frozen": str(is_frozen()),
    }


def _runtime_bases() -> list[Path]:
    """Ordered Runtime roots: local pack, then RVCMAX reference (dev without install)."""
    bases = [
        ROOT / "Runtime",
        ROOT / "runtime",
        ROOT / "RVCMAX" / "RVCMAX_Nvidia_xiaoyuan" / "Runtime",
    ]
    # When frozen, also allow sibling RVCMAX only under ROOT already covered
    return bases


def find_python(prefer_windowed: bool = False) -> str:
    """Prefer embedded Runtime (release / RVCMAX); avoid requiring user pip install.

    Never returns the frozen shell exe (``变声器.exe``) as a Python interpreter —
    that used to spawn a second main-app instance when Runtime was missing.
    """
    candidates: list[Path] = []
    for base in _runtime_bases():
        if not base.is_dir():
            continue
        if prefer_windowed:
            candidates.append(base / "pythonw.exe")
        candidates.append(base / "python.exe")
    # Host interpreter only in non-frozen (dev) sessions, and only if the
    # basename really looks like python*.
    if not is_frozen() and sys.executable:
        p = Path(sys.executable)
        base = p.name.lower()
        if prefer_windowed:
            for w in (p.with_name("pythonw.exe"), p.parent / "pythonw.exe"):
                if w.is_file():
                    candidates.append(w)
        if base.startswith("python"):
            candidates.append(p)
    for c in candidates:
        if c and Path(c).is_file():
            return str(c)
    return "pythonw" if prefer_windowed else "python"


def desktop_dir() -> Path:
    """User Desktop, including OneDrive/KFM redirected folders (review #27)."""
    if sys.platform == "win32":
        # User Shell Folders expands %USERPROFILE% and OneDrive redirects
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as k:
                val, _ = winreg.QueryValueEx(k, "Desktop")
                expanded = os.path.expandvars(str(val))
                p = Path(expanded)
                if p.is_dir():
                    return p
        except Exception:
            pass
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", wintypes.BYTE * 8),
                ]

            # FOLDERID_Desktop
            fid = GUID(
                0xB4BFCC3A,
                0xDB2C,
                0x424C,
                (wintypes.BYTE * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41),
            )
            path_ptr = ctypes.c_wchar_p()
            hr = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(fid), 0, None, ctypes.byref(path_ptr)
            )
            if hr == 0 and path_ptr.value:
                p = Path(path_ptr.value)
                if p.is_dir():
                    return p
        except Exception:
            pass
    home = Path.home()
    for desk in (
        home / "Desktop",
        home / "桌面",
        home / "OneDrive" / "Desktop",
        home / "OneDrive" / "桌面",
    ):
        if desk.is_dir():
            return desk
    return home / "Desktop"


def index_search_roots() -> list[Path]:
    """Folders scanned for FAISS .index files (feature retrieval, not 底模)."""
    ensure_dirs()
    roots = [
        MODELS_DIR,
        USER_DATA / "indices",
        ROOT / "logs",
        ROOT / "assets" / "indices",
    ]
    return roots


def list_voice_models() -> list[dict]:
    ensure_dirs()
    return list_voice_catalog(
        MODELS_DIR,
        ENGINE_WEIGHTS,
        index_search_roots=index_search_roots(),
    )
