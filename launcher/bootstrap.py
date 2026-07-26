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
from launcher.provision_progress import (
    ProvisionSnapshot,
    ProvisionTracker,
    format_bytes,
    format_eta,
    format_speed,
)
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
    TM_META,
    TM_OK,
    TM_SURFACE,
    TM_SURFACE_HOVER,
    TM_WARN,
    mono_font,
    px,
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


class ProvisionProgressPanel(tk.Frame):
    """Schale-quiet multi-step progress for Runtime / engine-core / VB-Cable."""

    def __init__(self, master, **kw):
        super().__init__(
            master,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
            **kw,
        )
        self._step_labels: list[tk.Label] = []
        top = tk.Frame(self, bg=TM_SURFACE)
        top.pack(fill="x", padx=12, pady=(10, 4))
        self.lbl_head = tk.Label(
            top,
            text="运行环境",
            font=title_font(10, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        )
        self.lbl_head.pack(side="left")
        self.lbl_stepn = tk.Label(
            top,
            text="",
            font=mono_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="e",
        )
        self.lbl_stepn.pack(side="right")

        # Not packed until provision actually starts
        self.steps_host = tk.Frame(self, bg=TM_SURFACE)

        # Bar host — not packed while idle (no fake blue fill)
        self.bar_row = tk.Frame(self, bg=TM_SURFACE)
        self.bar_bg = tk.Frame(self.bar_row, bg=TM_INSET, height=8)
        self.bar_bg.pack(fill="x")
        self.bar_bg.pack_propagate(False)
        self.bar_fg = tk.Frame(self.bar_bg, bg=TM_ACCENT, height=8)
        self._bar_w = 520
        self.bar_bg.bind("<Configure>", self._on_bar_cfg)
        self._active_ui = False

        self.lbl_detail = tk.Label(
            self,
            text="",
            font=mono_font(8),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            anchor="w",
            justify="left",
        )
        self.lbl_detail.pack(fill="x", padx=12, pady=(0, 4))
        self.lbl_remain = tk.Label(
            self,
            text="",
            font=sans_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
            justify="left",
            wraplength=px(520),
        )
        self.lbl_remain.pack(fill="x", padx=12, pady=(0, 10))

    def _on_bar_cfg(self, e) -> None:
        self._bar_w = max(int(e.width), 1)
        # Keep fill ratio if currently active
        if self._active_ui and hasattr(self, "_last_pct"):
            self._set_bar_pct(self._last_pct)

    def _set_bar_pct(self, pct: float) -> None:
        """0 = empty track (no blue). Only show fill when pct > 0."""
        self._last_pct = max(0.0, min(100.0, float(pct)))
        if self._last_pct <= 0.05:
            try:
                self.bar_fg.place_forget()
            except Exception:
                pass
            return
        w = max(2, int(self._bar_w * self._last_pct / 100.0))
        self.bar_fg.place(x=0, y=0, relheight=1.0, width=w)

    def _show_active_chrome(self) -> None:
        if self._active_ui:
            return
        self._active_ui = True
        self.bar_row.pack(fill="x", padx=12, pady=(0, 4), before=self.lbl_detail)
        self.steps_host.pack(fill="x", padx=12, pady=(2, 6), before=self.bar_row)

    def _hide_active_chrome(self) -> None:
        self._active_ui = False
        try:
            self.bar_fg.place_forget()
        except Exception:
            pass
        try:
            self.bar_row.pack_forget()
        except Exception:
            pass
        # steps_host stays packed empty after clear; forget to reclaim space
        try:
            self.steps_host.pack_forget()
        except Exception:
            pass

    def reset_idle(self, message: str = "") -> None:
        """Idle: no steps, no blue fill — only a quiet hint (not a fake progress)."""
        self.lbl_head.configure(text="运行环境")
        self.lbl_stepn.configure(text="")
        for w in self._step_labels:
            w.destroy()
        self._step_labels.clear()
        self._hide_active_chrome()
        self.lbl_detail.configure(
            text=message or "尚未开始补全。点上方「补全运行环境」后才会显示下载进度。"
        )
        self.lbl_remain.configure(text="")

    def apply(self, snap: ProvisionSnapshot) -> None:
        self._show_active_chrome()
        self.lbl_head.configure(text="补全进度")
        self.lbl_stepn.configure(
            text=f"第 {snap.step_index + 1} / {snap.total_steps} 步"
        )
        # rebuild step rows if count mismatch
        if len(self._step_labels) != len(snap.steps):
            for w in self._step_labels:
                w.destroy()
            self._step_labels.clear()
            for _ in snap.steps:
                lb = tk.Label(
                    self.steps_host,
                    text="",
                    font=mono_font(8),
                    bg=TM_SURFACE,
                    fg=TM_META,
                    anchor="w",
                    bd=0,
                    highlightthickness=0,
                )
                lb.pack(fill="x", pady=1)
                self._step_labels.append(lb)
        status_map = {
            "done": ("[完成]", TM_OK),
            "active": ("[进行]", TM_ACCENT),
            "error": ("[失败]", TM_WARN),
            "skipped": ("[跳过]", TM_META),
            "pending": ("[等待]", TM_META),
        }
        for lb, st in zip(self._step_labels, snap.steps):
            tag, color = status_map.get(st.status, ("[等待]", TM_META))
            lb.configure(text=f"  {tag}  {st.title}", fg=color)

        pct = snap.pct
        if snap.phase == "extract":
            # Indeterminate-ish: show a small active cue, not a fake %
            self._set_bar_pct(8.0 if pct <= 0 else pct)
        else:
            self._set_bar_pct(pct)

        if snap.total_bytes > 0 and snap.phase == "download":
            detail = (
                f"{pct:.0f}%  ·  {format_bytes(snap.done_bytes)} / "
                f"{format_bytes(snap.total_bytes)}  ·  "
                f"{format_speed(snap.speed_bps)}  ·  {format_eta(snap.eta_sec)}"
            )
        elif snap.phase == "extract":
            detail = "正在解压…"
        else:
            detail = snap.note or snap.step_title
        self.lbl_detail.configure(text=detail)
        if snap.remaining_titles:
            self.lbl_remain.configure(text="剩余：" + " → ".join(snap.remaining_titles))
        else:
            # Only say "最后一步" when actually on last step in active run
            if snap.step_index >= snap.total_steps - 1:
                self.lbl_remain.configure(text="剩余：无（本流程最后一步）")
            else:
                self.lbl_remain.configure(text="")

    def set_finished(self, message: str = "补全完成") -> None:
        self.lbl_head.configure(text="运行环境")
        self.lbl_stepn.configure(text="")
        self._set_bar_pct(100.0)
        self.lbl_detail.configure(text=message)
        self.lbl_remain.configure(text="")


class BootstrapApp:
    def __init__(self) -> None:
        ensure_dirs()
        try:
            from launcher.install_health import ensure_install_health

            self._install_health = ensure_install_health(RROOT)
        except Exception:
            self._install_health = {}
        self.root = tk.Tk()
        self.root.title(f"{APP_TITLE} · 启动器")
        # Fixed-size window: must scale or 125%/150% content gets clipped
        self.root.geometry(f"{px(640)}x{px(720)}")
        self.root.configure(bg=TM_BG)
        self.root.resizable(False, False)
        self._page = "setup"
        self._deploy_busy = False
        self._provision_busy = False
        self._tracker: ProvisionTracker | None = None
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
            borderwidth=0,
            highlightthickness=0,
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
            borderwidth=0,
            highlightthickness=0,
            command=lambda: self.show_page("system"),
        )
        self.btn_nav_system.pack(side="left", padx=2)

        self.content = tk.Frame(self.root, bg=TM_BG)
        self.content.pack(fill="both", expand=True)

        self.page_setup = self._build_page_setup(self.content)
        self.page_system = self._build_page_system(self.content)

        self.progress_panel = ProvisionProgressPanel(self.root)
        self.progress_panel.pack(fill="x", padx=PAD_X, pady=(4, 4))
        self.progress_panel.reset_idle()

        self.status = tk.Label(
            self.root,
            text="正在准备界面…",
            font=mono_font(8),
            bg=TM_BG,
            fg=TM_INK_MUTED,
            wraplength=px(560),
            justify="left",
            anchor="w",
        )
        self.status.pack(fill="x", padx=PAD_X, pady=(2, 6))

        btn_row = tk.Frame(self.root, bg=TM_BG)
        btn_row.pack(pady=(2, 18))
        PrimaryButton(
            btn_row, "打开主界面", command=self.on_start_app, padx=28, pady=10
        ).pack(side="left", padx=6)
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
                "新电脑默认缺少 Runtime：点「补全运行环境」从 CNB 下载（不依赖本机 pip/requests）。"
                "补完后可再按需下载模型等。日常请用桌面快捷方式或本启动器进主界面。"
            ),
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            wraplength=px(500),
            justify="left",
            anchor="w",
        ).pack(fill="x")

        cards = tk.Frame(page, bg=TM_BG)
        cards.pack(pady=(18, 10))
        SoftActionCard(cards, "发送快捷方式", "", self.on_shortcut).pack(
            side="left", padx=10
        )
        SoftActionCard(cards, "安装虚拟声卡", "", self.on_vbcable).pack(
            side="left", padx=10
        )
        SoftActionCard(cards, "补全运行环境", "", self.on_provision_runtime).pack(
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
            wraplength=px(500),
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
        """仅在 Setup 留下 pending 标记时提示补全；绝不静默下数 GB。"""
        if self._provision_busy or self._deploy_busy:
            return
        if runtime_ready(RROOT):
            self._clear_pending_marker()
            return
        pending = self._pending_runtime_marker()
        from_setup = bool(pending and pending.get("pending_runtime"))
        # 提示用户，不自动开下
        hint_var = self._selected_variant()
        if from_setup:
            self._set_status(
                f"安装未完成：尚未下载 Runtime（当前分版标记：{hint_var}）。\n"
                "请点「补全运行环境」确认显卡分版后开始下载（约数 GB）。",
                ok=False,
            )
        else:
            self._set_status(
                "未检测到 Runtime。请点「补全运行环境」选择显卡分版并下载。",
                ok=False,
            )

    def _ask_variant_and_confirm(self, *, force: bool = False) -> str | None:
        """Ask GPU variant + size warning. Returns variant or None if cancelled."""
        from launcher.cnb_sources import (
            VARIANT_LABELS,
            format_size,
            resolve_runtime_spec,
        )
        from launcher.ui import ask_choice

        current = self._selected_variant()
        options = [
            ("nvidia", VARIANT_LABELS.get("nvidia", "NVIDIA")),
            ("amd", VARIANT_LABELS.get("amd", "AMD/Intel")),
            ("nvidia50", VARIANT_LABELS.get("nvidia50", "NVIDIA 50系")),
        ]
        # Put current first
        options.sort(key=lambda x: 0 if x[0] == current else 1)
        choice = ask_choice(
            self.root,
            "选择显卡分版",
            "Runtime 体积较大（约 2–7 GB），请选择与本机显卡匹配的分版：\n"
            "· NVIDIA 大多数 N 卡（非 50 系）\n"
            "· AMD / Intel（DirectML）\n"
            "· NVIDIA 50 系（RTX 50xx）\n\n"
            "下载来自 CNB，需保持网络畅通。",
            options,
            cancel_text="取消",
        )
        if not choice:
            return None
        var = str(choice).lower()
        try:
            spec = resolve_runtime_spec(var, prefer_remote=True)
            size_s = format_size(spec.size_bytes or spec.primary.size_bytes)
            url_hint = (spec.primary.urls[0] if spec.primary.urls else "")[:72]
        except Exception:
            size_s = "数 GB"
            url_hint = ""
        verb = "重新下载并覆盖" if force else "下载并安装"
        # Py3.9 Runtime: no backslash inside f-string expressions
        src_line = ("  源：" + url_hint + "…\n") if url_hint else ""
        confirm = (
            f"将{verb}：\n"
            f"  分版：{VARIANT_LABELS.get(var, var)}\n"
            f"  约：{size_s}\n"
            f"{src_line}\n"
            "是否继续？"
        )
        if not messagebox.askyesno("确认补全运行环境", confirm):
            return None
        # Persist choice for package_meta / next launch
        try:
            from launcher.package_meta import write_package_meta

            write_package_meta(RROOT, var, install_via="bootstrap_confirm")
        except Exception:
            pass
        try:
            USER_DATA.mkdir(parents=True, exist_ok=True)
            (USER_DATA / "setup_pending.json").write_text(
                '{"pending_runtime": true, "variant": "%s"}\n' % var,
                encoding="utf-8",
            )
        except Exception:
            pass
        return var

    def on_provision_runtime(self) -> None:
        """一键：确认分版后补 Runtime，再可选补模型/训练资源。"""
        if self._provision_busy or self._deploy_busy:
            self._set_status("正在补全运行环境，请稍候…", ok=False)
            return
        force = False
        if runtime_ready(RROOT):
            # 已有 Runtime：先问是否二次补全 / 强制重装
            self._offer_optional_after_runtime(already_had_runtime=True)
            return
        var = self._ask_variant_and_confirm(force=False)
        if not var:
            self._set_status("已取消补全。", ok=False)
            return
        self._set_status(f"开始补全 Runtime（{var}）…", ok=True)
        self._run_provision(var, interactive=True, force=force)

    def _offer_optional_after_runtime(self, *, already_had_runtime: bool) -> None:
        """Runtime 就绪后：合并原「检测与部署」的可选下载。"""
        try:
            items = check_environment()
            report = format_check_report(items)
            core_miss = missing_items(items, kinds={KIND_CORE})
            try:
                from launcher.engine_core import engine_core_ready

                need_core_files = not engine_core_ready(RROOT)
            except Exception:
                need_core_files = any(
                    i.name in ("Hubert 模型", "RMVPE 模型") for i in core_miss
                )
            train_file_miss = [
                i
                for i in missing_items(items, kinds={KIND_TRAINING})
                if i.name in ("训练底模 (pretrained)", "伴奏分离 UVR")
            ]
        except Exception as e:
            messagebox.showwarning("检测", f"Runtime 已就绪，附加检测失败：{e}")
            self._refresh_hint()
            return

        if already_had_runtime and not need_core_files and not train_file_miss:
            if messagebox.askyesno(
                "运行环境",
                "已检测到 Runtime，日常变声所需也基本齐全。\n\n"
                "是否强制重新下载 Runtime？（一般不需要，仅环境损坏时选「是」。）",
            ):
                var = self._ask_variant_and_confirm(force=True)
                if var:
                    self._run_provision(var, interactive=True, force=True)
            else:
                messagebox.showinfo("环境", report + "\n\n可打开主界面使用。")
                self._set_status("环境正常，可打开主界面。")
            self._refresh_hint()
            return

        if need_core_files:
            if messagebox.askyesno(
                "继续补全",
                f"Runtime 已就绪。\n\n{report}\n\n"
                "是否继续下载引擎资源包 engine-core？\n"
                "（含 Hubert / RMVPE / ffmpeg，约 700+ MB；Setup 薄包不含此项。）",
            ):
                self._set_status("正在下载引擎资源…")
                self._run_engine_core_download()
                return
            self._set_status("已跳过引擎资源；可稍后再次点「补全运行环境」。")
            self._refresh_hint()
            return

        if train_file_miss:
            if messagebox.askyesno(
                "可选资源",
                f"日常变声环境已就绪。\n\n{report}\n\n"
                "是否再下载训练/伴奏分离资源？（可选，体积较大，日常变声不需要。）",
            ):
                self._set_status("正在下载训练/分离资源…")
                self._run_download("all_advanced")
                return
            self._set_status("日常环境已就绪，可打开主界面。")
            self._refresh_hint()
            return

        messagebox.showinfo("完成", report + "\n\n可打开主界面开始使用。")
        self._set_status("环境正常，可打开主界面。")
        self._refresh_hint()

    def _apply_tracker_ui(self, snap: ProvisionSnapshot) -> None:
        try:
            self.progress_panel.apply(snap)
            line = f"{snap.step_title} · 第 {snap.step_index + 1}/{snap.total_steps} 步"
            if snap.total_bytes > 0 and snap.phase == "download":
                line += f" · {snap.pct:.0f}%"
            self._set_status(line, ok=True)
        except Exception:
            pass

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

        tracker = ProvisionTracker(
            on_change=lambda snap: self.root.after(
                0, lambda s=snap: self._apply_tracker_ui(s)
            )
        )
        self._tracker = tracker
        self.root.after(
            0,
            lambda: self.progress_panel.apply(tracker.snapshot()),
        )

        def work() -> None:
            def log(msg: str) -> None:
                tracker.set_note(msg)
                self.root.after(0, lambda m=msg: self._set_status(m, ok=True))

            def progress(phase: str, done: int, total: int) -> None:
                if phase == "download":
                    tracker.set_step("runtime_dl")  # no-op if already on this step
                    tracker.set_bytes(done, total)
                elif phase == "extract":
                    tracker.set_step("runtime_extract")
                    tracker.set_phase("extract")
                elif phase == "models":
                    tracker.set_step("engine_dl")

            try:
                from launcher.runtime_provision import (
                    provision_runtime,
                    runtime_ready as _rr,
                )

                already_rt = _rr(RROOT) and not force
                if already_rt:
                    tracker.set_step("runtime_dl")
                    tracker.mark_done("runtime_dl")
                    tracker.mark_done("runtime_extract")
                    ok, msg = True, "Runtime 已就绪，跳过下载。"
                else:
                    tracker.set_step("runtime_dl")
                    ok, msg = provision_runtime(
                        variant,
                        root=RROOT,
                        progress=progress,
                        log=log,
                        force=force,
                        download_core_models=False,
                    )
                    if ok:
                        tracker.mark_done("runtime_dl")
                        tracker.mark_done("runtime_extract")
            except Exception as e:
                ok, msg = False, str(e)
                tracker.mark_error("runtime_dl", msg)

            extra_msgs: list[str] = []
            if ok:
                try:
                    from launcher.engine_core import (
                        ensure_engine_core,
                        engine_core_ready,
                    )

                    if not engine_core_ready(RROOT) or force:
                        tracker.set_step("engine_dl")

                        def _ecore_progress(phase: str, done: int, total: int) -> None:
                            if phase in ("engine_core", "download"):
                                tracker.set_step("engine_dl")  # no-op if already active
                                tracker.set_bytes(done, total)
                            elif phase == "engine_extract":
                                tracker.set_step("engine_extract")
                                tracker.set_phase("extract")

                        eok, emsg = ensure_engine_core(
                            root=RROOT,
                            force=bool(force),
                            progress=_ecore_progress,
                            log=log,
                        )
                        extra_msgs.append(emsg)
                        if eok:
                            tracker.mark_done("engine_dl")
                            tracker.mark_done("engine_extract")
                        else:
                            ok = False
                            msg = emsg
                            tracker.mark_error("engine_dl", emsg)
                    else:
                        tracker.mark_skipped("engine_dl")
                        tracker.mark_skipped("engine_extract")
                        extra_msgs.append("引擎资源已就绪")
                except Exception as e:
                    ok = False
                    msg = f"引擎资源补全失败：{e}"
                    extra_msgs.append(msg)
                    tracker.mark_error("engine_dl", msg)

            if ok:
                try:
                    from launcher.vbcable import ensure_vbcable_pack, vbcable_pack_ready

                    if not vbcable_pack_ready():
                        tracker.set_step("vbcable_dl")

                        def _vb_prog(done: int, total: int) -> None:
                            tracker.set_bytes(done, total)

                        vok, vmsg = ensure_vbcable_pack(log=log, progress=_vb_prog)
                        extra_msgs.append(vmsg if vok else f"虚拟声卡包未就绪：{vmsg}")
                        if vok:
                            tracker.mark_done("vbcable_dl")
                            log("VB-Cable 安装包已就绪（可点「安装虚拟声卡」）。")
                        else:
                            tracker.mark_error("vbcable_dl", vmsg)
                    else:
                        tracker.mark_skipped("vbcable_dl")
                        extra_msgs.append("本地已有虚拟声卡安装包")
                except Exception as e:
                    extra_msgs.append(f"虚拟声卡包下载跳过：{e}")
                    tracker.mark_skipped("vbcable_dl")

            def done() -> None:
                self._provision_busy = False
                self._deploy_busy = False
                self._tracker = None
                if ok:
                    self._clear_pending_marker()
                    full = msg
                    if extra_msgs:
                        full = msg + "\n" + "\n".join(extra_msgs)
                    self._set_status(full, ok=True)
                    try:
                        self.progress_panel.set_finished(
                            "补全完成。可打开主界面，或再点「补全运行环境」重试。"
                        )
                    except Exception:
                        pass
                    if interactive:
                        self._offer_optional_after_runtime(already_had_runtime=False)
                else:
                    self._set_status(msg, ok=False)
                    try:
                        self.progress_panel.reset_idle(
                            "补全未完成。点「补全运行环境」可重试（支持断点续传）。"
                        )
                    except Exception:
                        pass
                    if interactive or not runtime_ready(RROOT):
                        messagebox.showwarning(
                            "补全未完成",
                            msg + "\n\n可点击「补全运行环境」重试。\n"
                            "支持断点续传；大文件使用多连接下载。",
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
        # 先说明即将出现 UAC / 安装窗；成功启动后不要再弹窗或置顶，
        # 否则会把 UAC 和 VB-Cable 安装界面盖住，看起来像“没有安装提示”。
        from launcher.vbcable import vbcable_pack_ready

        need_dl = not vbcable_pack_ready()
        extra = (
            "\n\n本地尚无安装包：将先从 CNB 下载（约 1–2 MB，需联网），"
            "再启动安装程序。"
            if need_dl
            else ""
        )
        if not messagebox.askyesno(
            "安装虚拟声卡",
            "即将启动 VB-Cable 安装程序。" + extra + "\n\n点「是」之后请注意：\n"
            "· 若需下载安装包，请稍候状态栏进度\n"
            "· Windows 用户账户控制（UAC）— 请点「是」\n"
            "· VB-Cable 安装窗口 — 请点 Install / 安装\n\n"
            "软件须已完整安装/解压到硬盘（不要从压缩包内直接运行）。\n"
            "是否继续？",
        ):
            self._set_status("已取消安装虚拟声卡。", ok=False)
            return

        def work() -> None:
            def log(m: str) -> None:
                self.root.after(0, lambda s=m: self._set_status(s, ok=True))

            if need_dl:
                log("正在下载虚拟声卡安装包…")
            ok, msg = install_vbcable(download_if_missing=True, log=log)

            def done() -> None:
                self._set_status(msg, ok=ok)
                cfg = load_config()
                cfg["vbcable_hint_done"] = True
                save_config(cfg)
                if not ok:
                    messagebox.showwarning("虚拟声卡", msg)
                # 成功时只更新状态栏，让 UAC / 安装窗保持在前台

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def on_open_sound_panel(self) -> None:
        try:
            open_windows_sound_panel()
            self._set_status(
                "已打开系统「声音」面板（播放 / 录制设备）。不是设备管理器。"
            )
        except Exception as e:
            messagebox.showerror("无法打开", str(e))
            self._set_status(f"打开声音面板失败：{e}", ok=False)

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
                elif scope == "core":
                    from launcher.engine_core import ensure_engine_core

                    ok, raw = ensure_engine_core(root=RROOT, log=None)
                    msg = raw if ok else raw
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

    def _run_engine_core_download(self) -> None:
        """Download CNB engine-core pack (hubert/rmvpe/ffmpeg)."""
        self._run_download("core")

    def on_start_app(self) -> None:
        if self._provision_busy:
            messagebox.showinfo("请稍候", "正在补全运行环境，完成后再打开主界面。")
            return
        if not runtime_ready(RROOT):
            if messagebox.askyesno(
                "缺少运行环境",
                "尚未安装 Runtime，主界面无法推理变声。\n" "是否现在从 CNB 下载补全？",
            ):
                self._run_provision(self._selected_variant(), interactive=True)
            return
        try:
            from launcher.engine_core import engine_core_ready

            if not engine_core_ready(RROOT):
                if messagebox.askyesno(
                    "缺少引擎资源",
                    "尚未下载 engine-core（Hubert / RMVPE / ffmpeg）。\n"
                    "是否现在从 CNB 下载？",
                ):
                    self._run_engine_core_download()
                return
        except Exception:
            pass
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
