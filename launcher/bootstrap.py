# -*- coding: utf-8 -*-
"""First-run helper (RVCMAX role: 启动器).

Jobs: desktop shortcut, VB-Cable install, env check, **auto-provision Runtime**
from CNB Release when missing — not the daily voice UI.

Typography / chrome aligned with main_app (tracked wordmark, segment nav).
"""

from __future__ import annotations

import json
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
from launcher.package_meta import load_package_meta
from launcher.paths import APP_TITLE, ROOT as RROOT, USER_DATA, ensure_dirs
from launcher.runtime_provision import ensure_runtime, runtime_ready
from launcher.theme import (
    APP_WORDMARK,
    PAD_X,
    TM_ACCENT,
    TM_ACCENT_INK,
    TM_BG,
    TM_HAIRLINE,
    TM_INK,
    TM_INK_MUTED,
    TM_INSET,
    TM_OK,
    TM_SURFACE,
    TM_SURFACE_HOVER,
    TM_WARN,
    mono_font,
    sans_font,
    title_font,
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
        self.root.geometry("620x560")
        self.root.configure(bg=TM_BG)
        self.root.resizable(False, False)
        self._page = "setup"
        self._deploy_busy = False
        self._provision_busy = False
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
            text=APP_WORDMARK,
            font=title_font(16, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        ).pack(anchor="w")
        self.lbl_subtitle = tk.Label(
            head_inner,
            text="首次设置：补全环境 · 快捷方式 · 声卡",
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
        PrimaryButton(btn_row, "打开主界面", command=self.on_start_app, padx=28, pady=10).pack(
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
        # After UI paints: auto-download Runtime when Setup left a pending mark or Runtime missing
        self.root.after(200, self._maybe_auto_provision)

    def _build_page_setup(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=TM_BG)

        notice = tk.Frame(
            page,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        notice.pack(fill="x", padx=PAD_X, pady=(10, 6))
        notice_body = tk.Frame(notice, bg=TM_SURFACE)
        notice_body.pack(side="left", fill="both", expand=True, padx=14, pady=12)
        tk.Label(
            notice_body,
            text="说明",
            font=title_font(12, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        ).pack(fill="x", pady=(0, 4))
        tk.Label(
            notice_body,
            text=(
                "首次使用会自动从 CNB Release 补全 Runtime（按 Setup 所选显卡分版）。"
                "日常请用桌面快捷方式或本启动器进入主界面。"
            ),
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            wraplength=500,
            justify="left",
            anchor="w",
        ).pack(fill="x")

        cards = tk.Frame(page, bg=TM_BG)
        cards.pack(pady=(18, 6))
        SoftActionCard(cards, "发送快捷方式", "", self.on_shortcut).pack(
            side="left", padx=10
        )
        SoftActionCard(cards, "安装虚拟声卡", "", self.on_vbcable).pack(
            side="left", padx=10
        )
        SoftActionCard(cards, "检测与部署", "", self.on_deploy).pack(
            side="left", padx=10
        )
        cards2 = tk.Frame(page, bg=TM_BG)
        cards2.pack(pady=(4, 10))
        SoftActionCard(cards2, "补全运行环境", "", self.on_provision_runtime).pack(
            side="left", padx=10
        )
        return page

    def _build_page_system(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=TM_BG)
        tk.Label(
            page,
            text="系统快捷",
            font=title_font(16, "bold"),
            bg=TM_BG,
            fg=TM_INK,
            anchor="w",
        ).pack(fill="x", padx=PAD_X, pady=(14, 4))
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
            "",
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
            self.lbl_subtitle.configure(text="首次设置：补全环境 · 快捷方式 · 声卡")
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
                base = "环境正常，可打开主界面。"
                ok = True
            else:
                base = "缺少：" + "、".join(i.name for i in core_miss[:4])
                ok = False
            self._set_status(base + "\n" + gpu_text, ok=ok)

        def work():
            t = _gpu_line()
            self.root.after(0, lambda: _done(t))

        threading.Thread(target=work, daemon=True).start()

    def _pending_runtime_marker(self) -> dict | None:
        p = USER_DATA / "setup_pending.json"
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _clear_pending_marker(self) -> None:
        p = USER_DATA / "setup_pending.json"
        try:
            if p.is_file():
                p.unlink()
        except OSError:
            pass

    def _selected_variant(self) -> str:
        pending = self._pending_runtime_marker()
        if pending and pending.get("variant"):
            return str(pending["variant"]).lower()
        try:
            return str(load_package_meta(RROOT).get("variant") or "nvidia").lower()
        except Exception:
            return "nvidia"

    def _maybe_auto_provision(self) -> None:
        if self._provision_busy or self._deploy_busy:
            return
        if runtime_ready(RROOT):
            self._clear_pending_marker()
            return
        pending = self._pending_runtime_marker()
        # Auto when Setup marked pending, or Runtime simply missing on first open
        auto = bool(pending and pending.get("pending_runtime")) or True
        if not auto:
            return
        var = self._selected_variant()
        self._set_status(
            f"未检测到 Runtime，正在按分版「{var}」从 CNB 下载补全…\n"
            "体积较大，请保持网络畅通。",
            ok=False,
        )
        self._run_provision(var, interactive=False)

    def on_provision_runtime(self) -> None:
        if self._provision_busy:
            self._set_status("正在补全运行环境，请稍候…", ok=False)
            return
        var = self._selected_variant()
        if runtime_ready(RROOT):
            if not messagebox.askyesno(
                "运行环境",
                "已检测到 Runtime。是否仍强制重新下载安装？\n"
                "（一般不需要；仅在环境损坏时选择「是」。）",
            ):
                return
            force = True
        else:
            force = False
            if not messagebox.askyesno(
                "补全运行环境",
                f"将从 CNB Release 下载「{var}」分版 Runtime（数 GB）。\n"
                "是否继续？",
            ):
                return
        self._run_provision(var, interactive=True, force=force)

    def _run_provision(
        self,
        variant: str,
        *,
        interactive: bool,
        force: bool = False,
    ) -> None:
        if self._provision_busy:
            return
        self._provision_busy = True
        self._deploy_busy = True

        def work() -> None:
            lines: list[str] = []

            def log(msg: str) -> None:
                lines.append(msg)
                self.root.after(0, lambda m=msg: self._set_status(m, ok=True))

            def progress(phase: str, done: int, total: int) -> None:
                if phase == "download" and total > 0:
                    pct = min(100, int(100 * done / total))
                    mb = done / 1e6
                    tot = total / 1e6
                    self.root.after(
                        0,
                        lambda: self._set_status(
                            f"下载 Runtime… {pct}%（{mb:.0f}/{tot:.0f} MB）",
                            ok=True,
                        ),
                    )
                elif phase == "extract":
                    self.root.after(
                        0, lambda: self._set_status("正在解压 Runtime…", ok=True)
                    )

            try:
                ok, msg = ensure_runtime(
                    variant=variant,
                    root=RROOT,
                    progress=progress,
                    log=log,
                    force=force,
                )
            except Exception as e:
                ok, msg = False, str(e)

            def done() -> None:
                self._provision_busy = False
                self._deploy_busy = False
                if ok:
                    self._clear_pending_marker()
                    self._set_status(msg, ok=True)
                    if interactive:
                        messagebox.showinfo("完成", msg)
                else:
                    self._set_status(msg, ok=False)
                    if interactive or not runtime_ready(RROOT):
                        messagebox.showwarning(
                            "补全未完成",
                            msg + "\n\n可点击「补全运行环境」重试。",
                        )
                self._refresh_hint()

            self.root.after(0, done)

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
                        self._set_status("环境正常，可打开主界面。")
                        return

                    messagebox.showinfo("环境检测", report)
                    self._set_status("环境正常，可打开主界面。")
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
        if self._provision_busy:
            messagebox.showinfo("请稍候", "正在补全运行环境，完成后再打开主界面。")
            return
        if not runtime_ready(RROOT):
            if messagebox.askyesno(
                "缺少运行环境",
                "尚未安装 Runtime，主界面无法推理变声。\n"
                "是否现在从 CNB 下载补全？",
            ):
                self._run_provision(self._selected_variant(), interactive=True)
            return
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
