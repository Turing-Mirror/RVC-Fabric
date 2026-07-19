# -*- coding: utf-8 -*-
"""In-app online update + voice library (GitHub / SharePoint direct links)."""

from launcher.online.catalog import (
    OnlineCatalog,
    fetch_catalog,
    load_bundled_catalog,
    merge_catalogs,
)
from launcher.online.downloader import DownloadError, download_file, resolve_download_url
from launcher.online.gui_update import (
    apply_gui_patch_zip,
    apply_gui_zip,
    check_gui_update,
    download_and_apply_gui,
)
from launcher.online.package_spec import (
    PKG_FULL,
    PKG_GUI_PATCH,
    PKG_VOICE_FILES,
    PKG_VOICE_PACK,
    describe_package_type,
    detect_zip_package_type,
)
from launcher.online.voice_install import (
    install_voice_from_entry,
    install_voice_pack_zip,
)

__all__ = [
    "DownloadError",
    "OnlineCatalog",
    "PKG_FULL",
    "PKG_GUI_PATCH",
    "PKG_VOICE_FILES",
    "PKG_VOICE_PACK",
    "apply_gui_patch_zip",
    "apply_gui_zip",
    "check_gui_update",
    "describe_package_type",
    "detect_zip_package_type",
    "download_and_apply_gui",
    "download_file",
    "fetch_catalog",
    "install_voice_from_entry",
    "install_voice_pack_zip",
    "load_bundled_catalog",
    "merge_catalogs",
    "resolve_download_url",
]
