# -*- coding: utf-8 -*-
"""最小化到系统托盘（可选能力）。

有 pystray + Pillow 时：点最小化 → 窗口缩进托盘，不占任务栏；托盘菜单
提供 显示主界面 / 开关变声 / 退出，双击图标恢复窗口。
缺这两个库时完全不介入，窗口正常最小化。

打包注意：这两个库要装进【壳层 host Python】环境（跑启动器的那个，
不是 Runtime）：``pip install pystray Pillow``。
"""

from __future__ import annotations

import threading


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

    # 品牌蓝底 + 白色圆环（无需字体文件，任何机器都能画）
    img = Image.new("RGB", (64, 64), "#1289f0")
    d = ImageDraw.Draw(img)
    d.ellipse((16, 16, 48, 48), fill="#ffffff")
    d.ellipse((25, 25, 39, 39), fill="#1289f0")
    return img


class TrayController:
    """Owns the pystray icon; all Tk calls are marshalled onto the Tk thread."""

    def __init__(self, app) -> None:
        self.app = app
        self._icon = None

    @property
    def active(self) -> bool:
        return self._icon is not None

    def hide_to_tray(self) -> None:
        if self._icon is not None or not tray_available():
            return
        import pystray

        root = self.app.root

        def _ui(fn):
            try:
                root.after(0, fn)
            except Exception:
                pass

        def on_show(icon, item=None):
            self.restore()

        def on_toggle(icon, item=None):
            _ui(self.app.toggle_vc)

        def on_quit(icon, item=None):
            self.stop()
            _ui(self.app._on_close)

        menu = pystray.Menu(
            pystray.MenuItem("显示主界面", on_show, default=True),
            pystray.MenuItem("开启 / 停止变声", on_toggle),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", on_quit),
        )
        self._icon = pystray.Icon(
            "rvc_fabric", _make_icon_image(), "RVC Fabric · 图灵镜", menu
        )
        try:
            root.withdraw()
        except Exception:
            pass
        threading.Thread(target=self._icon.run, daemon=True).start()

    def stop(self) -> None:
        icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    def restore(self) -> None:
        self.stop()
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
            pass
