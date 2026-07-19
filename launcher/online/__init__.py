# -*- coding: utf-8 -*-
"""In-app online update + voice library (GitHub / SharePoint direct links)."""

from launcher.online.catalog import (
    OnlineCatalog,
    fetch_catalog,
    load_bundled_catalog,
    merge_catalogs,
)
from launcher.online.downloader import DownloadError, download_file, resolve_download_url
from launcher.online.gui_update import apply_gui_zip, check_gui_update
from launcher.online.voice_install import install_voice_from_entry

__all__ = [
    "DownloadError",
    "OnlineCatalog",
    "apply_gui_zip",
    "check_gui_update",
    "download_file",
    "fetch_catalog",
    "install_voice_from_entry",
    "load_bundled_catalog",
    "merge_catalogs",
    "resolve_download_url",
]
