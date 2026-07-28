# -*- coding: utf-8 -*-
"""系统托盘（启动即常驻，直到软件真正退出）。

有 pystray + Pillow 时：主界面启动后右下角常驻图标；点 X 选「最小化到托盘」
或设置关闭动作为托盘时，窗口隐藏、变声继续；托盘菜单：显示主界面 / 开关变声 / 退出。
缺库时 tray_available() 为 False，关闭询问里不提供托盘选项。

打包：壳层 host Python 需 ``pip install pystray Pillow``；build_release 已
ensure_shell_download_deps + hidden-import。
"""

from __future__ import annotations

import threading
from typing import Optional


def tray_available() -> bool:
    import importlib

    try:
        for mod in ("pystray", "PIL.Image", "PIL.ImageDraw"):
            importlib.import_module(mod)
        return True
    except Exception:
        return False


def _make_icon_image():
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (64, 64), "#1289f0")
    d = ImageDraw.Draw(img)
    d.ellipse((16, 16, 48, 48), fill="#ffffff")
    d.ellipse((25, 25, 39, 39), fill="#1289f0")
    return img


class TrayController:
    """Owns the pystray icon for the whole app lifetime.

    ensure_icon() may be called many times (startup retries); hide_to_tray /
    restore never destroy the icon; stop() only on real process exit.
    """

    def __init__(self, app) -> None:
        self.app = app
        self._icon = None
        self._lock = threading.Lock()
        self._stopped = False

    @property
    def active(self) -> bool:
        return self._icon is not None and not self._stopped

    def _ui(self, fn) -> None:
        try:
            self.app.root.after(0, fn)
        except Exception:
            pass

    def ensure_icon(self) -> bool:
        """Create the always-on tray icon if missing. Returns True if active."""
        if self._stopped:
            return False
        with self._lock:
            if self._icon is not None:
                return True
            if not tray_available():
                return False
            try:
                import pystray

                def on_show(icon, item=None):
                    self.restore()

                def on_toggle(icon, item=None):
                    self._ui(self.app.toggle_vc)

                def on_quit(icon, item=None):
                    # Explicit quit — skip close dialog
                    self._ui(lambda: self.app._on_close(force_exit=True))

                menu = pystray.Menu(
                    pystray.MenuItem("显示主界面", on_show, default=True),
                    pystray.MenuItem("开启 / 停止变声", on_toggle),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("退出", on_quit),
                )
                icon = pystray.Icon(
                    "rvc_fabric",
                    _make_icon_image(),
                    "RVC Fabric · 图灵镜",
                    menu,
                )
                self._icon = icon
                threading.Thread(
                    target=icon.run, daemon=True, name="tm-tray"
                ).start()
                return True
            except Exception:
                self._icon = None
                return False

    def hide_to_tray(self) -> bool:
        """Withdraw main window; keep tray icon. Returns False if tray unusable."""
        if not self.ensure_icon():
            return False
        try:
            self.app.root.withdraw()
            return True
        except Exception:
            return False

    def stop(self) -> None:
        """Tear down icon (only when the process is really exiting)."""
        self._stopped = True
        with self._lock:
            icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    def restore(self) -> None:
        """Show main window again; tray icon stays."""
        root = self.app.root

        def _show():
            try:
                root.deiconify()
                root.state("normal")
                root.lift()
                root.focus_force()
            except Exception:
                pass

        try:
            root.after(0, _show)
        except Exception:
            try:
                _show()
            except Exception:
                pass
