# -*- coding: utf-8 -*-
"""系统托盘（常驻图标 + 最小化/关闭进托盘）。

有 pystray + Pillow 时：启动即在 Windows 右下角常驻托盘图标；最小化或
「关闭时选择最小化到托盘」→ 窗口隐藏、变声继续后台运行；托盘菜单提供
显示主界面 / 开关变声 / 退出，双击图标恢复窗口。
缺这两个库时完全不介入，窗口正常最小化/关闭。

打包注意：这两个库要装进【壳层 host Python】环境（跑启动器的那个，
不是 Runtime）：``pip install pystray Pillow``。build_release 的
ensure_shell_download_deps / shell_hidden_imports 已包含。
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
    """Owns the pystray icon; all Tk calls are marshalled onto the Tk thread.

    图标常驻：ensure_icon() 启动时调用一次；hide_to_tray()/restore() 只
    隐藏/恢复窗口，不销毁图标；stop() 仅在真正退出时调用。
    """

    def __init__(self, app) -> None:
        self.app = app
        self._icon = None

    @property
    def active(self) -> bool:
        return self._icon is not None

    def _ui(self, fn) -> None:
        try:
            self.app.root.after(0, fn)
        except Exception:
            pass

    def ensure_icon(self) -> None:
        """常驻托盘图标（不动窗口）。pystray 缺失时安静跳过。"""
        if self._icon is not None or not tray_available():
            return
        import pystray

        def on_show(icon, item=None):
            self.restore()

        def on_toggle(icon, item=None):
            self._ui(self.app.toggle_vc)

        def on_quit(icon, item=None):
            # 托盘退出 = 明确退出，不再弹「关闭询问」
            self._ui(lambda: self.app._on_close(force_exit=True))

        menu = pystray.Menu(
            pystray.MenuItem("显示主界面", on_show, default=True),
            pystray.MenuItem("开启 / 停止变声", on_toggle),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", on_quit),
        )
        self._icon = pystray.Icon(
            "rvc_fabric", _make_icon_image(), "RVC Fabric · 图灵镜", menu
        )
        threading.Thread(target=self._icon.run, daemon=True).start()

    def hide_to_tray(self) -> None:
        """窗口缩进托盘（图标已常驻则复用）。"""
        self.ensure_icon()
        if self._icon is None:
            return  # pystray 不可用，绝不能把窗口藏没
        try:
            self.app.root.withdraw()
        except Exception:
            pass

    def stop(self) -> None:
        icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    def restore(self) -> None:
        """恢复主窗口；托盘图标保持常驻。"""
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
