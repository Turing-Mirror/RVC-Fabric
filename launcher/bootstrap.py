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
from launcher.env_setup import check_environment, download_pretrained
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
from launcher.win_util import create_desktop_shortcut, open_path, start_main_app


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
        self.root.title(f"{APP_TITLE} · 首次设置")
        self.root.geometry("540x380")
        self.root.configure(bg=TM_BG)
        self.root.resizable(False, False)
        try:
            self.root.attributes("-topmost", True)
            self.root.after(350, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass

        head = tk.Frame(self.root, bg=TM_BG)
        head.pack(fill="x", pady=(32, 6), padx=28)
        tk.Label(
            head,
            text=APP_TITLE,
            font=serif_font(18, "bold"),
            bg=TM_BG,
            fg=TM_INK,
        ).pack(anchor="w")
        tk.Label(
            head,
            text=APP_BRAND + "  ·  首次设置：快捷方式 · 声卡 · 环境",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_INK_MUTED,
        ).pack(anchor="w", pady=(4, 0))

        cards = tk.Frame(self.root, bg=TM_BG)
        cards.pack(pady=20)
        SoftCard(cards, "发送快捷方式", "放到桌面 · 一键打开", self.on_shortcut).pack(
            side="left", padx=8
        )
        SoftCard(cards, "安装虚拟声卡", "VB-Cable · 开黑用", self.on_vbcable).pack(
            side="left", padx=8
        )
        SoftCard(cards, "检测与部署", "预训练与环境", self.on_deploy).pack(
            side="left", padx=8
        )

        self.status = tk.Label(
            self.root,
            text="正在准备界面…",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            wraplength=480,
            justify="left",
            anchor="w",
        )
        self.status.pack(fill="x", padx=28, pady=(4, 8))

        btn_row = tk.Frame(self.root, bg=TM_BG)
        btn_row.pack(pady=10)
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

    def _set_status(self, text: str, ok: bool = True) -> None:
        self.status.configure(text=text, fg=TM_OK if ok else TM_WARN)

    def _refresh_hint(self) -> None:
        # GPU line (non-blocking: short WMI + optional Runtime probe)
        def _gpu_line():
            try:
                from launcher.config_store import load_config
                from launcher.gpu_backend import detect_full

                pref = str(load_config().get("accel_backend") or "auto")
                info = detect_full(RROOT, pref)
                return f"加速：{info.get('label')} {info.get('detail') or ''}（{info.get('backend')}）"
            except Exception as e:
                return f"加速：检测失败 ({e})"

        def _done(gpu_text: str):
            bad = [i for i in check_environment() if not i.ok]
            base = ""
            if not bad:
                base = "环境看起来正常。可发送快捷方式、安装声卡后打开变声器。"
            else:
                base = "缺少：" + "；".join(i.name for i in bad[:4])
            self._set_status(base + "\n" + gpu_text, ok=not bad)

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

    def on_deploy(self) -> None:
        self._set_status("正在检测…")

        def work():
            lines = [f"[{'OK' if i.ok else '缺'}] {i.name}: {i.detail}" for i in check_environment()]
            report = "\n".join(lines)
            need_dl = any(
                not i.ok and i.name in ("Hubert 模型", "RMVPE 模型")
                for i in check_environment()
            )

            def after():
                if need_dl:
                    self._set_status("正在下载预训练（体积较大）…")

                    def dl():
                        ok, msg = download_pretrained()
                        self.root.after(0, lambda: self._after_dl(ok, msg, report))

                    threading.Thread(target=dl, daemon=True).start()
                else:
                    messagebox.showinfo("环境检测", report)
                    self._refresh_hint()

            self.root.after(0, after)

        threading.Thread(target=work, daemon=True).start()

    def _after_dl(self, ok: bool, msg: str, report: str) -> None:
        self._set_status(msg, ok=ok)
        messagebox.showinfo("部署结果", f"{msg}\n\n{report[:800]}")
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
    import os
    from pathlib import Path

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
