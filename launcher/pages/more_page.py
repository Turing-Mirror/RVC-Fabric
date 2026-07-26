# -*- coding: utf-8 -*-
"""More page: advanced entries + emergency actions + support tooling.

Split out of main_app. Uses MainApp state (self.open_webui, self.show_page,
self.btn_start, self._set_status_visual, …) present on the composed instance.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from launcher import realtime_client as rt_client
from launcher.features import CONSULT_ENTRY_ENABLED
from launcher.paths import ROOT, USER_DATA
from launcher.theme import (
    APP_PRODUCT_TAGLINE,
    GUTTER,
    TM_ACCENT,
    TM_BG,
    TM_META,
    mono_font,
)
from launcher.ui import GhostButton, PageHeader, PrimaryButton
from launcher.version import APP_VERSION
from launcher.win_util import open_path


class MorePageMixin:
    def _page_more(self) -> tk.Frame:
        """Same chrome as the other pages: left-aligned header at the page
        gutter, then a full-width 3-per-row button grid."""
        fr = tk.Frame(self.body, bg=TM_BG)
        canvas = tk.Canvas(fr, bg=TM_BG, highlightthickness=0)
        sb = tk.Scrollbar(fr, orient="vertical", command=canvas.yview)
        wrap = tk.Frame(canvas, bg=TM_BG)
        win = canvas.create_window((0, 0), window=wrap, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _sync(_e=None):
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass

        def _width(e):
            if e.width > 1:
                canvas.itemconfigure(win, width=e.width)

        wrap.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _width)

        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        canvas.bind("<MouseWheel>", _wheel)

        PageHeader(
            wrap,
            eyebrow="",
            title="其他",
            lead="高级入口与紧急操作。",
        ).pack(anchor="w", padx=GUTTER, pady=(18, 12))
        box = tk.Frame(wrap, bg=TM_BG)
        box.pack(fill="x", padx=GUTTER)
        for c in range(3):
            box.columnconfigure(c, weight=1, uniform="more")

        entries = [
            # (文本, 回调, 是否主按钮)
            ("根据本机表现自动优化性能", self._auto_perf_from_history, False),
            ("重新观看新手引导", lambda: self.show_onboarding(first_run=False), False),
            ("使用说明", lambda: self.show_page("help"), False),
            ("快捷键说明", self.show_hotkeys_help, False),
            ("生成诊断包（反馈问题）", self._collect_diagnostics, False),
            ("校验 Runtime 完整性", self._verify_runtime_integrity, False),
            ("打开性能信息文件夹", self._open_perf_reports, False),
            ("打开 User_Data", lambda: open_path(USER_DATA), False),
            ("打开安装目录", lambda: open_path(ROOT), False),
            ("训练 / 翻唱 WebUI（高级）", self.open_webui, False),
            ("强制结束变声引擎（卡音频时点）", self._force_kill_engine, False),
        ]
        if CONSULT_ENTRY_ENABLED:
            entries.insert(0, ("性能&参数优化服务", self.open_consult_wizard, True))
        for i, (text, cmd, primary) in enumerate(entries):
            cls = PrimaryButton if primary else GhostButton
            b = cls(box, text, command=cmd, padx=10, pady=14)
            b.grid(row=i // 3, column=i % 3, sticky="nsew", padx=6, pady=6)

        tk.Label(
            wrap,
            text=f"v{APP_VERSION}",
            bg=TM_BG,
            fg=TM_META,
            font=mono_font(8),
        ).pack(anchor="center", pady=(24, 16))

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

        Optionally runs a quick offline benchmark in the Runtime first (user's
        current voice + settings) so the bundle carries fresh timing samples
        from this machine — that is how the team gathers per-GPU data for
        further optimization. Benchmark and packing run off the Tk thread."""
        if getattr(self, "_diag_busy", False):
            return
        from launcher import perf_bench

        run_bench = False
        bench_note = "本次未运行性能测试。"
        bench_pth = ""
        bench_index = ""
        if self.vc_running or self._vc_starting:
            messagebox.showinfo(
                "生成诊断包",
                "检测到变声正在运行，将直接打包现有日志与性能记录。\n"
                "如需附带全新的性能测试数据，请先停止变声再生成。",
            )
        else:
            m = self.models[self.model_idx] if getattr(self, "models", None) else {}
            bench_pth = str(m.get("path") or "")
            bench_index = str(m.get("index") or "")
            ready, why = perf_bench.bench_ready(ROOT, bench_pth)
            if ready:
                run_bench = messagebox.askyesno(
                    "生成诊断包",
                    "是否先运行一次性能测试（约 1 分钟）？\n\n"
                    "测试会用当前音色与设置做一小段离线推理（不占用麦克风），\n"
                    "结果仅保存在本机并打进诊断包，帮助团队针对你的机型优化。\n\n"
                    "选「否」则只打包现有日志与配置。",
                )
            else:
                bench_note = f"本次未运行性能测试（{why}）。"

        import threading

        self._diag_busy = True
        if run_bench:
            self._set_status_visual("busy", "正在性能测试…", "约 1 分钟 · 请勿开启变声")
        else:
            self._set_status_visual("busy", "正在生成诊断包…", "")
        # Snapshot on the Tk thread: settings sliders mutate self.cfg live, and
        # copying a dict while it grows raises RuntimeError on the worker thread
        bench_cfg = dict(self.cfg or {})

        def work() -> None:
            note = bench_note
            err = ""
            path = ""
            try:
                if run_bench:
                    res = perf_bench.run_benchmark(
                        ROOT, bench_pth, bench_index, bench_cfg
                    )
                    if res["ok"]:
                        line = perf_bench.format_bench_summary(res["summary"])
                        note = "已包含刚测得的性能数据" + (
                            f"：{line}" if line else "。"
                        )
                    else:
                        note = f"性能测试未完成（{res['error']}），已打包其余信息。"
                import importlib.util

                spec = importlib.util.spec_from_file_location(
                    "tm_collect_diagnostics",
                    str(ROOT / "tools" / "collect_diagnostics.py"),
                )
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                path = mod.collect(str(ROOT))
            except Exception as e:
                err = str(e)

            def done() -> None:
                self._diag_busy = False
                if err:
                    self._set_status_visual("error", "诊断包生成失败", err[:48])
                    messagebox.showerror("失败", err)
                    return
                self._set_status_visual("idle", "诊断包已生成", APP_PRODUCT_TAGLINE)
                open_path(USER_DATA / "diagnostics")
                messagebox.showinfo(
                    "诊断包已生成",
                    f"已生成：\n{path}\n\n{note}\n\n"
                    "内容仅含日志、配置、机器环境与性能记录，"
                    "不含音频或音色模型，也不会自动上传。\n"
                    "反馈问题时把这个 zip 发给团队即可。",
                )

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _verify_runtime_integrity(self) -> None:
        """Compare local Runtime to CNB integrity JSON + import smoke."""
        import threading

        self._set_status_visual("busy", "校验 Runtime…", "文件与 torch 导入探测")

        def work() -> None:
            err = ""
            summary = ""
            ok = False
            path = None
            try:
                from launcher.runtime_integrity import (
                    format_report_summary,
                    integrity_report_path,
                    verify_runtime,
                )

                rep = verify_runtime(ROOT, fetch_remote=True)
                ok = bool(rep.get("ok"))
                summary = format_report_summary(rep)
                path = integrity_report_path(ROOT)
            except Exception as e:
                err = str(e)

            def done() -> None:
                if err:
                    self._set_status_visual("error", "校验失败", err[:48])
                    messagebox.showerror("Runtime 完整性", err)
                    return
                self._set_status_visual(
                    "idle" if ok else "error",
                    "Runtime 校验通过" if ok else "Runtime 校验失败",
                    (summary or "")[:64],
                )
                messagebox.showinfo(
                    "Runtime 完整性",
                    (summary or "")
                    + (f"\n\n详情：\n{path}" if path else "")
                    + "\n\n失败时可在启动器重新「补全运行环境」。",
                )

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()
