# -*- coding: utf-8 -*-
"""More page: advanced entries + emergency actions + support tooling.

Split out of main_app. Uses MainApp state (self.open_webui, self.show_page,
self.btn_start, self._set_status_visual, …) present on the composed instance.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from launcher import realtime_client as rt_client
from launcher.paths import ROOT, USER_DATA
from launcher.theme import (
    APP_PRODUCT_TAGLINE,
    TM_ACCENT,
    TM_BG,
    TM_META,
    mono_font,
)
from launcher.ui import GhostButton, PageHeader
from launcher.version import APP_VERSION
from launcher.win_util import open_path


class MorePageMixin:
    def _page_more(self) -> tk.Frame:
        """More page: pack layout only (no place) so footer never overlaps buttons."""
        fr = tk.Frame(self.body, bg=TM_BG)
        fr.columnconfigure(0, weight=1)
        fr.rowconfigure(0, weight=1)

        # Scroll when window is short — fixed place() used to sit on top of buttons
        canvas = tk.Canvas(fr, bg=TM_BG, highlightthickness=0)
        sb = tk.Scrollbar(fr, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        wrap = tk.Frame(canvas, bg=TM_BG)
        win = canvas.create_window((0, 0), window=wrap, anchor="n")

        def _sync(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            try:
                cw = max(int(canvas.winfo_width()), 200)
                # Center content block
                wrap.update_idletasks()
                ww = max(wrap.winfo_reqwidth(), 320)
                x = max((cw - ww) // 2, 12)
                canvas.coords(win, x, 16)
                canvas.itemconfigure(win, width=min(ww + 8, cw - 24))
            except Exception:
                pass

        wrap.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _sync)

        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        canvas.bind("<MouseWheel>", _wheel)
        wrap.bind("<MouseWheel>", _wheel)

        inner = tk.Frame(wrap, bg=TM_BG)
        inner.pack(padx=24, pady=(8, 16))

        PageHeader(
            inner,
            eyebrow="",
            title="其他",
            lead="高级入口与紧急操作。",
        ).pack(anchor="w", pady=(0, 16))
        box = tk.Frame(inner, bg=TM_BG)
        box.pack(anchor="w", fill="x")

        def soft(text, cmd):
            GhostButton(box, text, command=cmd, padx=22, pady=12).pack(
                pady=6, fill="x", ipadx=40
            )

        soft("打开训练 / 翻唱 WebUI（高级 · 浏览器）", self.open_webui)
        soft("打开首次设置启动器", self.open_bootstrap)
        soft("打开 User_Data", lambda: open_path(USER_DATA))
        soft("打开安装目录", lambda: open_path(ROOT))
        soft("根据本机表现自动优化性能", self._auto_perf_from_history)
        soft("打开性能信息文件夹（帮助我们优化适配）", self._open_perf_reports)
        soft("生成诊断包（反馈问题时用）", self._collect_diagnostics)
        soft("生成咨询包（调参服务用）", self.open_consult_wizard)
        soft("强制结束变声引擎（卡音频时点）", self._force_kill_engine)
        soft("快捷键说明", self.show_hotkeys_help)
        soft("使用说明", lambda: self.show_page("help"))
        soft("重新观看新手引导", lambda: self.show_onboarding(first_run=False))
        soft("在线更新与音色库", lambda: self.show_page("store"))

        # Footer after buttons (pack) — never place() over the list
        tk.Label(
            inner,
            text=f"v{APP_VERSION}",
            bg=TM_BG,
            fg=TM_META,
            font=mono_font(8),
        ).pack(anchor="center", pady=(20, 12))

        def _wheel_tree(w):
            w.bind("<MouseWheel>", _wheel)
            for c in w.winfo_children():
                _wheel_tree(c)

        try:
            _wheel_tree(wrap)
        except Exception:
            pass
        fr.after(80, _sync)
        return fr

    def open_bootstrap(self) -> None:
        from launcher.paths import find_python
        from launcher.win_util import run_no_console

        pyw = find_python(prefer_windowed=True)
        run_no_console([pyw, str(ROOT / "launcher" / "bootstrap.py")])

    def _force_kill_engine(self) -> None:
        """Emergency: kill all orphan workers and release sound devices."""
        if not messagebox.askyesno(
            "强制结束",
            "将强制结束所有变声后台进程并释放声卡。\n确定？",
        ):
            return
        try:
            n = rt_client.kill_all_project_workers()
            self.vc_running = False
            self._vc_starting = False
            self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
            self._set_status_visual("idle", "引擎已强制结束", APP_PRODUCT_TAGLINE)
            messagebox.showinfo("完成", f"已清理变声相关进程（约 {n} 个）。")
        except Exception as e:
            messagebox.showerror("失败", str(e))

    def _auto_perf_from_history(self) -> None:
        """Pick a good performance setting from this machine's own usage record."""
        from launcher.app_presets import perf_preset_name, recommend_perf_preset
        from tools.perf_report import load_latest

        rep = load_latest(str(USER_DATA / "perf_reports"))
        summary = (rep or {}).get("summary") or {}
        n = int(summary.get("n") or 0)
        if not rep or n <= 0:
            messagebox.showinfo(
                "自动优化性能",
                "还没有足够的使用记录。\n"
                "正常变声用一会儿再回来，我会按你电脑的实际表现帮你调好。",
            )
            return
        key, reason = recommend_perf_preset(
            float(summary.get("p95_ms") or 0),
            float(summary.get("block_ms") or 0),
            int(summary.get("over_budget_blocks") or 0),
            n,
        )
        try:
            self._apply_perf_preset(key)
        except Exception:
            pass
        messagebox.showinfo(
            "性能已优化",
            f"{reason}\n已切换到「{perf_preset_name(key)}」，重新开启变声后完全生效。",
        )

    def _open_perf_reports(self) -> None:
        """Perf samples live here; user decides whether to share them."""
        d = USER_DATA / "perf_reports"
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        open_path(d)
        try:
            has_reports = any(p.name.startswith("perf_") for p in d.iterdir())
        except Exception:
            has_reports = True
        if not has_reports:
            messagebox.showinfo(
                "性能信息",
                "软件偶尔会把变声性能信息记录在此文件夹（仅保存在本机，不会自动上传）。\n\n"
                "目前还没有记录：正常变声一段时间后会自动生成。\n"
                "如愿意帮助我们优化和适配，可将文件夹内的文件发送给团队。",
            )

    def _collect_diagnostics(self) -> None:
        """Build a support zip via tools/collect_diagnostics.py (stdlib-only).

        Loaded from file so it works from the PyInstaller exe too."""
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "tm_collect_diagnostics",
                str(ROOT / "tools" / "collect_diagnostics.py"),
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            path = mod.collect(str(ROOT))
            open_path(USER_DATA / "diagnostics")
            messagebox.showinfo(
                "诊断包已生成",
                f"已生成：\n{path}\n\n"
                "内容仅含日志与配置，不含音频或音色模型。\n"
                "反馈问题时把这个 zip 发给团队即可。",
            )
        except Exception as e:
            messagebox.showerror("失败", str(e))
