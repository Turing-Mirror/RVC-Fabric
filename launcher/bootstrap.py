# -*- coding: utf-8 -*-
"""First-run helper (RVCMAX role: 启动器).

Jobs: desktop shortcut, VB-Cable install, env check — not the daily voice UI.
Typography / chrome aligned with main_app (tracked wordmark, segment nav).
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.config_store import load_config, save_config
from launcher.env_setup import (
    KIND_CORE,
    KIND_TRAINING,
    check_environment,
    download_pretrained,
    format_check_report,
    missing_items,
)
from launcher.paths import APP_BRAND, APP_TITLE, ROOT as RROOT, ensure_dirs
from launcher.theme import (
    APP_ROUTE,
    APP_WORDMARK,
    PAD_X,
    TM_ACCENT,
    TM_ACCENT_INK,
    TM_BG,
    TM_HAIRLINE,
    TM_INK,
    TM_INK_MUTED,
    TM_INSET,
    TM_META,
    TM_OK,
    TM_SURFACE,
    TM_SURFACE_HOVER,
    TM_WARN,
    display_font,
    mono_font,
    sans_font,
    title_font,
    tracked,
)
from launcher.ui import GhostButton, PrimaryButton, SoftActionCard
from launcher.vbcable import install_vbcable
from launcher.win_util import (
    create_desktop_shortcut,
    open_path,
    open_windows_sound_panel,
    start_main_app,
)


class BootstrapApp:
    def __init__(self) -> None:
        ensure_dirs()
        self.root = tk.Tk()
        self.root.title(f"{APP_TITLE} · 启动器")
        self.root.geometry("620x540")
        self.root.configure(bg=TM_BG)
        self.root.resizable(False, False)
        self._page = "setup"
        self._deploy_busy = False
        try:
            self.root.attributes("-topmost", True)
            self.root.after(350, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass

        head = tk.Frame(self.root, bg=TM_SURFACE)
        head.pack(fill="x")
        head_inner = tk.Frame(head, bg=TM_SURFACE)
        head_inner.pack(fill="x", pady=(20, 14), padx=PAD_X)
        tk.Label(
            head_inner,
            text=tracked(APP_WORDMARK, gap="  "),
            font=display_font(14),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            head_inner,
            text="启动器  ·  " + tracked(APP_ROUTE, gap=""),
            font=mono_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))
        self.lbl_subtitle = tk.Label(
            head_inner,
            text="首次设置：快捷方式 · 声卡 · 环境",
            font=sans_font(10),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            anchor="w",
        )
        self.lbl_subtitle.pack(anchor="w", pady=(10, 0))
        tk.Frame(self.root, bg=TM_HAIRLINE, height=1).pack(fill="x")

        nav = tk.Frame(self.root, bg=TM_BG)
        nav.pack(fill="x", padx=PAD_X, pady=(16, 6))
        rail = tk.Frame(nav, bg=TM_INSET, padx=4, pady=4)
        rail.pack(side="left")
        self.btn_nav_setup = tk.Button(
            rail,
            text="首次设置",
            font=title_font(9, "bold"),
            relief="flat",
            padx=16,
            pady=7,
            cursor="hand2",
            bd=0,
            command=lambda: self.show_page("setup"),
        )
        self.btn_nav_setup.pack(side="left", padx=2)
        self.btn_nav_system = tk.Button(
            rail,
            text="系统快捷",
            font=sans_font(9),
            relief="flat",
            padx=16,
            pady=7,
            cursor="hand2",
            bd=0,
            command=lambda: self.show_page("system"),
        )
        self.btn_nav_system.pack(side="left", padx=2)

        self.content = tk.Frame(self.root, bg=TM_BG)
        self.content.pack(fill="both", expand=True)

        self.page_setup = self._build_page_setup(self.content)
        self.page_system = self._build_page_system(self.content)

        self.status = tk.Label(
            self.root,
            text="正在准备界面…",
            font=mono_font(8),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            wraplength=540,
            justify="left",
            anchor="w",
        )
        self.status.pack(fill="x", padx=PAD_X, pady=(4, 8))

        btn_row = tk.Frame(self.root, bg=TM_BG)
        btn_row.pack(pady=(2, 18))
        PrimaryButton(btn_row, "打开变声器", command=self.on_start_app, padx=28, pady=10).pack(
            side="left", padx=6
        )
        GhostButton(
            btn_row, "打开安装目录", command=lambda: open_path(RROOT), padx=16, pady=10
        ).pack(side="left", padx=6)

        self.show_page("setup")

        try:
            self.root.update_idletasks()
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(500, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass
        self.root.after(50, self._refresh_hint)

    def _build_page_setup(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=TM_BG)

        notice = tk.Frame(
            page,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        notice.pack(fill="x", padx=PAD_X, pady=(10, 6))
        tk.Frame(notice, bg=TM_ACCENT, width=4).pack(side="left", fill="y")
        notice_body = tk.Frame(notice, bg=TM_SURFACE)
        notice_body.pack(side="left", fill="both", expand=True, padx=14, pady=12)
        tk.Label(
            notice_body,
            text=tracked("NOTICE", gap="  "),
            font=mono_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            notice_body,
            text="说明",
            font=title_font(12, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        ).pack(fill="x", pady=(4, 4))
        tk.Label(
            notice_body,
            text=(
                "初次启动或「检测与部署」时，若短暂出现黑色命令行窗口，属于正常现象，"
                "是绿色运行环境在加载，不是报错。窗口会自行关闭；日常用桌面快捷方式 / "
                "「变声器」一般不会再弹黑框。"
            ),
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            wraplength=500,
            justify="left",
            anchor="w",
        ).pack(fill="x")

        cards = tk.Frame(page, bg=TM_BG)
        cards.pack(pady=(18, 10))
        SoftActionCard(cards, "发送快捷方式", "DESKTOP SHORTCUT", self.on_shortcut).pack(
            side="left", padx=10
        )
        SoftActionCard(cards, "安装虚拟声卡", "VB-CABLE", self.on_vbcable).pack(
            side="left", padx=10
        )
        SoftActionCard(cards, "检测与部署", "ENV · CORE", self.on_deploy).pack(
            side="left", padx=10
        )
        return page

    def _build_page_system(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=TM_BG)
        tk.Label(
            page,
            text=tracked("SYSTEM", gap="  "),
            font=mono_font(8),
            bg=TM_BG,
            fg=TM_META,
            anchor="w",
        ).pack(fill="x", padx=PAD_X, pady=(14, 2))
        tk.Label(
            page,
            text="系统快捷",
            font=title_font(16, "bold"),
            bg=TM_BG,
            fg=TM_INK,
            anchor="w",
        ).pack(fill="x", padx=PAD_X, pady=(0, 4))
        tk.Label(
            page,
            text="打开 Windows「声音」面板，配置麦克风、CABLE 与默认设备。",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            wraplength=500,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=PAD_X, pady=(0, 14))

        cards = tk.Frame(page, bg=TM_BG)
        cards.pack(pady=8)
        SoftActionCard(
            cards,
            "声音设备",
            "PLAYBACK · RECORD",
            self.on_open_sound_panel,
        ).pack(side="left", padx=10)
        return page

    def show_page(self, key: str) -> None:
        self._page = key if key in ("setup", "system") else "setup"
        self.page_setup.pack_forget()
        self.page_system.pack_forget()
        if self._page == "system":
            self.page_system.pack(fill="both", expand=True)
            self.lbl_subtitle.configure(text="系统快捷：声音设备等")
            self._style_nav(active="system")
        else:
            self.page_setup.pack(fill="both", expand=True)
            self.lbl_subtitle.configure(text="首次设置：快捷方式 · 声卡 · 环境")
            self._style_nav(active="setup")

    def _style_nav(self, active: str) -> None:
        def style(btn: tk.Button, on: bool) -> None:
            if on:
                btn.configure(
                    bg=TM_ACCENT,
                    fg=TM_ACCENT_INK,
                    activebackground=TM_INK,
                    activeforeground=TM_ACCENT_INK,
                    font=title_font(9, "bold"),
                )
            else:
                btn.configure(
                    bg=TM_INSET,
                    fg=TM_INK_MUTED,
                    activebackground=TM_SURFACE_HOVER,
                    activeforeground=TM_INK,
                    font=sans_font(9),
                )

        style(self.btn_nav_setup, active == "setup")
        style(self.btn_nav_system, active == "system")

    def _set_status(self, text: str, ok: bool = True) -> None:
        self.status.configure(text=text, fg=TM_OK if ok else TM_WARN)

    def _refresh_hint(self) -> None:
        def _gpu_line():
            try:
                from launcher.config_store import load_config
                from launcher.gpu_backend import detect_full
                from launcher.package_meta import load_package_meta

                pref = str(load_config().get("accel_backend") or "auto")
                info = detect_full(RROOT, pref)
                pm = load_package_meta()
                pack = str(pm.get("label") or pm.get("variant") or "未标记")
                return (
                    f"发行包：{pack}\n"
                    f"加速：{info.get('label')} {info.get('detail') or ''}（{info.get('backend')}）"
                )
            except Exception as e:
                return f"加速：检测失败 ({e})"

        def _done(gpu_text: str):
            items = check_environment()
            core_miss = missing_items(items, kinds={KIND_CORE})
            if not core_miss:
                base = "环境正常，可打开变声器。"
                ok = True
            else:
                base = "缺少：" + "、".join(i.name for i in core_miss[:4])
                ok = False
            self._set_status(base + "\n" + gpu_text, ok=ok)

        def work():
            t = _gpu_line()
            self.root.after(0, lambda: _done(t))

        threading.Thread(target=work, daemon=True).start()

    def on_shortcut(self) -> None:
        try:
            path = create_desktop_shortcut()
            cfg = load_config()
            cfg["desktop_shortcut_done"] = True
            save_config(cfg)
            self._set_status(f"已创建桌面快捷方式：{path.name}")
            messagebox.showinfo(
                "完成",
                f"桌面快捷方式已创建：\n{path}\n\n之后双击即可打开主界面（无黑框）。",
            )
        except Exception as e:
            messagebox.showerror("失败", str(e))

    def on_vbcable(self) -> None:
        ok, msg = install_vbcable()
        self._set_status(msg, ok=ok)
        (messagebox.showinfo if ok else messagebox.showwarning)("虚拟声卡", msg)
        cfg = load_config()
        cfg["vbcable_hint_done"] = True
        save_config(cfg)

    def on_open_sound_panel(self) -> None:
        try:
            open_windows_sound_panel()
            self._set_status(
                "已打开系统「声音」面板（播放 / 录制设备）。不是设备管理器。"
            )
        except Exception as e:
            messagebox.showerror("无法打开", str(e))
            self._set_status(f"打开声音面板失败：{e}", ok=False)

    def on_deploy(self) -> None:
        if self._deploy_busy:
            self._set_status("正在处理，请稍候…", ok=False)
            return
        self._deploy_busy = True
        self._set_status("正在检测…")

        def work():
            try:
                items = check_environment()
                report = format_check_report(items)
                core_miss = missing_items(items, kinds={KIND_CORE})
                need_core_files = any(
                    i.name in ("Hubert 模型", "RMVPE 模型") for i in core_miss
                )
                train_file_miss = [
                    i
                    for i in missing_items(items, kinds={KIND_TRAINING})
                    if i.name in ("训练底模 (pretrained)", "伴奏分离 UVR")
                ]
            except Exception as e:
                # bind the message now — `e` is unbound once the except block ends,
                # so the deferred callback must not reference it directly
                err = str(e)

                def fail():
                    self._deploy_busy = False
                    messagebox.showerror("检测失败", err)
                    self._set_status(f"检测失败：{err}", ok=False)

                self.root.after(0, fail)
                return

            def after():
                self._refresh_hint()
                try:
                    if need_core_files:
                        if messagebox.askyesno(
                            "环境检测",
                            f"{report}\n\n缺少变声必需文件，是否下载？",
                        ):
                            self._set_status("正在下载…")
                            self._run_download("core")
                            return
                        self._deploy_busy = False
                        return

                    if train_file_miss:
                        if messagebox.askyesno(
                            "环境检测",
                            f"{report}\n\n是否下载训练/分离资源？（可选，体积较大）",
                        ):
                            self._set_status("正在下载…")
                            self._run_download("all_advanced")
                            return
                        self._deploy_busy = False
                        self._set_status("环境正常，可打开变声器。")
                        return

                    messagebox.showinfo("环境检测", report)
                    self._set_status("环境正常，可打开变声器。")
                finally:
                    if not getattr(self, "_download_running", False):
                        self._deploy_busy = False

            self.root.after(0, after)

        threading.Thread(target=work, daemon=True).start()

    def _run_download(self, scope: str) -> None:
        self._download_running = True
        self._deploy_busy = True

        def work():
            try:
                if scope == "all_advanced":
                    ok1, msg1 = download_pretrained(scope="training")
                    ok2, msg2 = download_pretrained(scope="uvr")
                    ok = ok1 and ok2
                    msg = "下载完成。" if ok else f"下载未全部成功。\n{msg1}\n{msg2}"
                else:
                    ok, raw = download_pretrained(scope=scope)
                    msg = "下载完成。" if ok else raw
            except Exception as e:
                ok, msg = False, str(e)

            def done():
                self._download_running = False
                self._deploy_busy = False
                self._set_status(msg, ok=ok)
                messagebox.showinfo("完成" if ok else "提示", msg)
                self._refresh_hint()

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def on_start_app(self) -> None:
        try:
            start_main_app()
            self._set_status("主程序已启动。")
            self.root.after(500, self.root.destroy)
        except Exception as e:
            messagebox.showerror("启动失败", str(e))

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    log = Path(__file__).resolve().parent.parent / "TEMP" / "gui_alive.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("bootstrap main() enter\n", encoding="utf-8")
    except Exception:
        pass
    BootstrapApp().run()


if __name__ == "__main__":
    main()
