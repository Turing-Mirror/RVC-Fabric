# -*- coding: utf-8 -*-
"""First-run helper (RVCMAX role: 启动器).

Jobs: desktop shortcut, VB-Cable install, env check — not the daily voice UI.
Skin: Turing Mirror 「白无垢」 (docs/UI-AESTHETIC-DESIGN.md). No pink RVCMAX chrome.
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
    core_ready,
    download_pretrained,
    format_check_report,
    missing_items,
)
from launcher.paths import APP_BRAND, APP_TITLE, ROOT as RROOT, ensure_dirs
from launcher.theme import (
    TM_ACCENT,
    TM_ACCENT_INK,
    TM_BG,
    TM_HAIRLINE,
    TM_INK,
    TM_INK_MUTED,
    TM_META,
    TM_OK,
    TM_SURFACE,
    TM_SURFACE_HOVER,
    TM_WARN,
    sans_font,
    serif_font,
)
from launcher.vbcable import install_vbcable
from launcher.win_util import (
    create_desktop_shortcut,
    open_path,
    open_windows_sound_panel,
    start_main_app,
)


class SoftCard(tk.Frame):
    """Surface card with ink label — no pink fill."""

    def __init__(self, master, title: str, subtitle: str, command, **kw):
        super().__init__(
            master,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            **kw,
        )
        self.configure(width=148, height=118)
        self._cmd = command
        self._inner = tk.Frame(self, bg=TM_SURFACE, width=128, height=72)
        self._inner.pack(padx=10, pady=(14, 4))
        self._inner.pack_propagate(False)
        self._lbl = tk.Label(
            self._inner,
            text=title,
            font=sans_font(11, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            wraplength=118,
            justify="center",
        )
        self._lbl.place(relx=0.5, rely=0.5, anchor="center")
        self._sub = tk.Label(
            self,
            text=subtitle,
            font=sans_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
        )
        self._sub.pack(pady=(0, 10))
        for w in (self, self._inner, self._lbl, self._sub):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _enter(self, _e=None):
        for w in (self, self._inner, self._lbl, self._sub):
            w.configure(bg=TM_SURFACE_HOVER)

    def _leave(self, _e=None):
        for w in (self, self._inner, self._lbl, self._sub):
            w.configure(bg=TM_SURFACE)

    def _click(self, _e=None):
        if self._cmd:
            self._cmd()


class BootstrapApp:
    def __init__(self) -> None:
        ensure_dirs()
        self.root = tk.Tk()
        self.root.title(f"{APP_TITLE} · 启动器")
        self.root.geometry("560x460")
        self.root.configure(bg=TM_BG)
        self.root.resizable(False, False)
        self._page = "setup"  # setup | system
        try:
            self.root.attributes("-topmost", True)
            self.root.after(350, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass

        head = tk.Frame(self.root, bg=TM_BG)
        head.pack(fill="x", pady=(24, 4), padx=28)
        tk.Label(
            head,
            text=APP_TITLE,
            font=serif_font(18, "bold"),
            bg=TM_BG,
            fg=TM_INK,
        ).pack(anchor="w")
        self.lbl_subtitle = tk.Label(
            head,
            text=APP_BRAND + "  ·  首次设置：快捷方式 · 声卡 · 环境",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_INK_MUTED,
        )
        self.lbl_subtitle.pack(anchor="w", pady=(4, 0))

        # Page switch (白无垢：素墨选中，淡面未选)
        nav = tk.Frame(self.root, bg=TM_BG)
        nav.pack(fill="x", padx=28, pady=(12, 4))
        self.btn_nav_setup = tk.Button(
            nav,
            text="首次设置",
            font=sans_font(9, "bold"),
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
            bd=0,
            command=lambda: self.show_page("setup"),
        )
        self.btn_nav_setup.pack(side="left", padx=(0, 6))
        self.btn_nav_system = tk.Button(
            nav,
            text="系统快捷",
            font=sans_font(9),
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
            bd=0,
            command=lambda: self.show_page("system"),
        )
        self.btn_nav_system.pack(side="left")

        # Content host
        self.content = tk.Frame(self.root, bg=TM_BG)
        self.content.pack(fill="both", expand=True, padx=0, pady=0)

        self.page_setup = self._build_page_setup(self.content)
        self.page_system = self._build_page_system(self.content)

        self.status = tk.Label(
            self.root,
            text="正在准备界面…",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            wraplength=500,
            justify="left",
            anchor="w",
        )
        self.status.pack(fill="x", padx=28, pady=(2, 6))

        btn_row = tk.Frame(self.root, bg=TM_BG)
        btn_row.pack(pady=(2, 14))
        tk.Button(
            btn_row,
            text="打开变声器",
            font=sans_font(11, "bold"),
            bg=TM_ACCENT,
            fg=TM_ACCENT_INK,
            activebackground=TM_INK,
            activeforeground=TM_ACCENT_INK,
            relief="flat",
            padx=26,
            pady=8,
            cursor="hand2",
            command=self.on_start_app,
            bd=0,
        ).pack(side="left", padx=6)
        tk.Button(
            btn_row,
            text="打开安装目录",
            font=sans_font(10),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            activebackground=TM_SURFACE_HOVER,
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
            command=lambda: open_path(RROOT),
            bd=0,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        ).pack(side="left", padx=6)

        self.show_page("setup")

        # Defer env check so the window paints immediately (no torch import freeze)
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

        # Notice: first-run black console is normal
        notice = tk.Frame(
            page,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        notice.pack(fill="x", padx=28, pady=(8, 4))
        tk.Label(
            notice,
            text="说明",
            font=sans_font(9, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        ).pack(fill="x", padx=12, pady=(8, 2))
        tk.Label(
            notice,
            text=(
                "初次启动或「检测与部署」时，若短暂出现黑色命令行窗口，属于正常现象，"
                "是绿色运行环境在加载，不是报错。窗口会自行关闭；日常用桌面快捷方式 / "
                "「变声器」一般不会再弹黑框。"
            ),
            font=sans_font(8),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            wraplength=480,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 10))

        cards = tk.Frame(page, bg=TM_BG)
        cards.pack(pady=(12, 8))
        SoftCard(cards, "发送快捷方式", "放到桌面 · 一键打开", self.on_shortcut).pack(
            side="left", padx=8
        )
        SoftCard(cards, "安装虚拟声卡", "VB-Cable · 开黑用", self.on_vbcable).pack(
            side="left", padx=8
        )
        SoftCard(cards, "检测与部署", "日常必需 · 可选训练", self.on_deploy).pack(
            side="left", padx=8
        )
        return page

    def _build_page_system(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=TM_BG)
        tk.Label(
            page,
            text="系统设置快捷入口（Windows）",
            font=sans_font(10, "bold"),
            bg=TM_BG,
            fg=TM_INK,
            anchor="w",
        ).pack(fill="x", padx=28, pady=(10, 4))
        tk.Label(
            page,
            text="用于配置麦克风、CABLE、默认设备等。此处打开的是系统「声音」面板，不是设备管理器。",
            font=sans_font(8),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            wraplength=480,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=28, pady=(0, 12))

        cards = tk.Frame(page, bg=TM_BG)
        cards.pack(pady=8)
        SoftCard(
            cards,
            "声音设备",
            "播放 · 录制列表",
            self.on_open_sound_panel,
        ).pack(side="left", padx=8)
        # 预留：后续可在此并排增加更多系统快捷卡片
        return page

    def show_page(self, key: str) -> None:
        self._page = key if key in ("setup", "system") else "setup"
        self.page_setup.pack_forget()
        self.page_system.pack_forget()
        if self._page == "system":
            self.page_system.pack(fill="both", expand=True)
            self.lbl_subtitle.configure(
                text=APP_BRAND + "  ·  系统快捷：声音设备等"
            )
            self._style_nav(active="system")
        else:
            self.page_setup.pack(fill="both", expand=True)
            self.lbl_subtitle.configure(
                text=APP_BRAND + "  ·  首次设置：快捷方式 · 声卡 · 环境"
            )
            self._style_nav(active="setup")

    def _style_nav(self, active: str) -> None:
        def style(btn: tk.Button, on: bool) -> None:
            if on:
                btn.configure(
                    bg=TM_ACCENT,
                    fg=TM_ACCENT_INK,
                    activebackground=TM_INK,
                    activeforeground=TM_ACCENT_INK,
                    font=sans_font(9, "bold"),
                )
            else:
                btn.configure(
                    bg=TM_SURFACE,
                    fg=TM_INK_MUTED,
                    activebackground=TM_SURFACE_HOVER,
                    activeforeground=TM_INK,
                    font=sans_font(9),
                    highlightthickness=1,
                    highlightbackground=TM_HAIRLINE,
                )

        style(self.btn_nav_setup, active == "setup")
        style(self.btn_nav_system, active == "system")

    def _set_status(self, text: str, ok: bool = True) -> None:
        self.status.configure(text=text, fg=TM_OK if ok else TM_WARN)

    def _refresh_hint(self) -> None:
        # GPU line (non-blocking: short WMI + optional Runtime probe)
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
            # 状态只看日常变声必需项；训练/UVR/Gradio 缺失不算「环境异常」
            core_miss = missing_items(items, kinds={KIND_CORE})
            train_miss = missing_items(items, kinds={KIND_TRAINING})
            if not core_miss:
                base = "日常变声环境正常。可发送快捷方式、安装声卡后打开变声器。"
                if train_miss:
                    base += f"（训练/WebUI 可选资源未齐 {len(train_miss)} 项，不影响开黑）"
                ok = True
            else:
                base = "日常变声还缺：" + "；".join(i.name for i in core_miss[:4])
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
        """Classic Sound panel: 播放 / 录制 设备列表（mmsys.cpl）。"""
        try:
            open_windows_sound_panel()
            self._set_status(
                "已打开系统「声音」面板（播放 / 录制设备）。不是设备管理器。"
            )
        except Exception as e:
            messagebox.showerror("无法打开", str(e))
            self._set_status(f"打开声音面板失败：{e}", ok=False)

    def on_deploy(self) -> None:
        self._set_status("正在检测…（若出现黑框属正常）")

        def work():
            items = check_environment()
            report = format_check_report(items)
            core_miss = missing_items(items, kinds={KIND_CORE})
            # 训练底模 / UVR / Gradio 等 — 仅提示，不强制
            train_file_miss = [
                i
                for i in missing_items(items, kinds={KIND_TRAINING})
                if i.name in ("训练底模 (pretrained)", "伴奏分离 UVR")
            ]

            def after():
                messagebox.showinfo("环境检测", report[:1200])
                self._refresh_hint()

                # 1) 日常必需缺失 → 询问是否只下 hubert/rmvpe
                need_core_files = any(
                    i.name in ("Hubert 模型", "RMVPE 模型") for i in core_miss
                )
                if need_core_files:
                    if messagebox.askyesno(
                        "下载日常必需资源",
                        "缺少 Hubert / RMVPE（实时变声需要）。\n\n"
                        "是否现在下载？体积约数百 MB，仅日常变声相关，不含训练底模。",
                    ):
                        self._set_status("正在下载日常必需（Hubert / RMVPE）…")
                        self._run_download("core", then_training=bool(train_file_miss))
                        return

                # 2) 训练/分离可选 → 单独询问，默认不下载
                if train_file_miss:
                    names = "、".join(i.name for i in train_file_miss)
                    if messagebox.askyesno(
                        "可选：训练 / 伴奏分离资源",
                        f"检测到以下【进阶】资源未齐：\n{names}\n\n"
                        "这些只用于 WebUI 训练音色、伴奏分离，\n"
                        "开黑实时变声不需要。\n\n"
                        "体积很大（数 GB 级），是否现在下载？\n"
                        "（选「否」完全不影响日常变声）",
                    ):
                        self._set_status("正在下载训练/分离资源（体积大，请耐心）…")
                        self._run_download("all_advanced")
                        return

                if not need_core_files and not train_file_miss:
                    if core_ready(items):
                        self._set_status("检测完成：日常变声环境已就绪。")

            self.root.after(0, after)

        threading.Thread(target=work, daemon=True).start()

    def _run_download(self, scope: str, *, then_training: bool = False) -> None:
        """scope: core | training | uvr | all_advanced (training+uvr)."""

        def work():
            if scope == "all_advanced":
                ok1, msg1 = download_pretrained(scope="training")
                ok2, msg2 = download_pretrained(scope="uvr")
                ok, msg = ok1 and ok2, f"{msg1}\n{msg2}"
            else:
                ok, msg = download_pretrained(scope=scope)

            def done():
                self._after_dl(ok, msg)
                if then_training and ok:
                    if messagebox.askyesno(
                        "可选：训练 / 伴奏分离",
                        "日常资源已处理。\n\n"
                        "是否继续下载训练底模与伴奏分离权重？\n"
                        "（体积大，仅 WebUI 训练/分离需要，日常变声不需要）",
                    ):
                        self._set_status("正在下载训练/分离资源…")
                        self._run_download("all_advanced")

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _after_dl(self, ok: bool, msg: str, report: str = "") -> None:
        self._set_status(msg, ok=ok)
        body = msg
        if report:
            body = f"{msg}\n\n{report[:600]}"
        messagebox.showinfo("部署结果", body)
        self._refresh_hint()

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
    app = BootstrapApp()
    try:
        log.write_text(
            "bootstrap window up geometry=" + app.root.geometry() + "\n",
            encoding="utf-8",
        )
    except Exception:
        pass
    app.run()


if __name__ == "__main__":
    main()
