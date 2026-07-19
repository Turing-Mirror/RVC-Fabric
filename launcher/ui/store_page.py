# -*- coding: utf-8 -*-
"""「更新」页：检查 GUI 更新、在线音色库、完整包外链（QQ / SharePoint）。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING, Any, Optional

from launcher.config_store import load_config, save_config
from launcher.online.catalog import (
    OnlineCatalog,
    VoiceEntry,
    fetch_catalog,
    is_voice_installed,
    load_bundled_catalog,
    local_app_version,
)
from launcher.online.downloader import DownloadError, open_in_browser
from launcher.online.gui_update import check_gui_update, download_and_apply_gui
from launcher.online.package_spec import (
    PKG_FULL,
    PKG_GUI_PATCH,
    describe_package_type,
)
from launcher.online.voice_install import install_voice_from_entry
from launcher.paths import MODELS_DIR
from launcher.theme import (
    GUTTER,
    TM_ACCENT,
    TM_BG,
    TM_HAIRLINE,
    TM_INK,
    TM_INK_MUTED,
    TM_META,
    TM_OK,
    TM_SURFACE,
    TM_WARN,
    mono_font,
    sans_font,
    title_font,
    tracked,
)
from launcher.ui.widgets import GhostButton, PageHeader, PrimaryButton, SectionCard

if TYPE_CHECKING:
    from launcher.main_app import MainApp


class StorePage:
    """Builds and owns the online update / voice library page."""

    def __init__(self, app: "MainApp", parent: tk.Frame) -> None:
        self.app = app
        self.root = app.root
        self.catalog: OnlineCatalog = load_bundled_catalog()
        self._busy = False
        self.fr = tk.Frame(parent, bg=TM_BG)
        self._build()

    @property
    def frame(self) -> tk.Frame:
        return self.fr

    def _build(self) -> None:
        fr = self.fr
        fr.columnconfigure(0, weight=1)
        fr.rowconfigure(1, weight=1)

        head = tk.Frame(fr, bg=TM_BG)
        head.grid(row=0, column=0, sticky="ew", padx=GUTTER, pady=(16, 8))
        PageHeader(
            head,
            eyebrow="UPDATE  ·  LIBRARY",
            title="在线更新与音色库",
            lead="软件内：GUI 补丁 + 音色下载（GitHub / SharePoint 直链）。"
            "完整包请走 SharePoint 或 QQ 群。",
        ).pack(anchor="w")

        # Scrollable body
        wrap_host = tk.Frame(fr, bg=TM_BG)
        wrap_host.grid(row=1, column=0, sticky="nsew")
        wrap_host.columnconfigure(0, weight=1)
        wrap_host.rowconfigure(0, weight=1)

        canvas = tk.Canvas(wrap_host, bg=TM_BG, highlightthickness=0)
        sb = tk.Scrollbar(wrap_host, orient="vertical", command=canvas.yview)
        self._inner = tk.Frame(canvas, bg=TM_BG)
        win = canvas.create_window((0, 0), window=self._inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        def _sync(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _width(e):
            if e.width > 1:
                canvas.itemconfigure(win, width=e.width)

        self._inner.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _width)

        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        canvas.bind("<MouseWheel>", _wheel)
        self._inner.bind("<MouseWheel>", _wheel)

        # --- GUI update ---
        sec_gui = SectionCard(
            self._inner, title="软件本体（GUI）", eyebrow="GUI PATCH", pad=16
        )
        sec_gui.pack(fill="x", padx=GUTTER, pady=8)
        self.lbl_ver = tk.Label(
            sec_gui.body,
            text=f"当前版本  {local_app_version()}",
            font=mono_font(9),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        )
        self.lbl_ver.pack(anchor="w")
        self.lbl_gui_status = tk.Label(
            sec_gui.body,
            text="点击「检查更新」拉取在线清单。",
            font=sans_font(10),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            anchor="w",
            wraplength=640,
            justify="left",
        )
        self.lbl_gui_status.pack(anchor="w", pady=(6, 8))
        row_g = tk.Frame(sec_gui.body, bg=TM_SURFACE)
        row_g.pack(anchor="w")
        PrimaryButton(row_g, "检查更新", command=self.refresh_catalog, padx=14, pady=6).pack(
            side="left", padx=(0, 8)
        )
        self.btn_gui_apply = PrimaryButton(
            row_g, "下载并应用增量包", command=self.apply_gui, padx=14, pady=6
        )
        self.btn_gui_apply.pack(side="left", padx=4)
        self.btn_gui_apply.configure(state="disabled")
        GhostButton(
            row_g, "全量包说明 / 打开链接", command=self.open_full_package_help, padx=12, pady=6
        ).pack(side="left", padx=4)

        # --- Manifest URL ---
        sec_url = SectionCard(
            self._inner, title="清单地址", eyebrow="MANIFEST", pad=16
        )
        sec_url.pack(fill="x", padx=GUTTER, pady=8)
        tk.Label(
            sec_url.body,
            text="在线 catalog JSON（GitHub raw / SharePoint 直链）。可覆盖 configs/online_catalog.json 内 manifest_urls。",
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            wraplength=640,
            justify="left",
            anchor="w",
        ).pack(anchor="w")
        self.var_manifest = tk.StringVar(
            value=str(load_config().get("update_manifest_url") or "")
        )
        ent = tk.Entry(
            sec_url.body,
            textvariable=self.var_manifest,
            font=mono_font(9),
            bg=TM_BG,
            fg=TM_INK,
            relief="flat",
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        ent.pack(fill="x", pady=(8, 6), ipady=6)
        GhostButton(
            sec_url.body, "保存清单地址", command=self.save_manifest_url, padx=12, pady=5
        ).pack(anchor="w")

        # --- Voices ---
        sec_v = SectionCard(
            self._inner, title="在线音色库", eyebrow="VOICES", pad=16
        )
        sec_v.pack(fill="x", padx=GUTTER, pady=8)
        self.voices_host = tk.Frame(sec_v.body, bg=TM_SURFACE)
        self.voices_host.pack(fill="x")
        self.lbl_voices_empty = tk.Label(
            self.voices_host,
            text="暂无可用音色条目。请配置清单中的 voices[].pth_url。",
            font=sans_font(10),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        )
        self.lbl_voices_empty.pack(anchor="w")

        # --- Full package / community ---
        sec_c = SectionCard(
            self._inner, title="完整包与社群", eyebrow="FULL PACKAGE", pad=16
        )
        sec_c.pack(fill="x", padx=GUTTER, pady=8)
        self.lbl_community = tk.Label(
            sec_c.body,
            text="",
            font=sans_font(10),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            wraplength=640,
            justify="left",
            anchor="w",
        )
        self.lbl_community.pack(anchor="w", pady=(0, 8))
        row_c = tk.Frame(sec_c.body, bg=TM_SURFACE)
        row_c.pack(anchor="w")
        GhostButton(
            row_c, "打开 SharePoint 完整包", command=self.open_sharepoint, padx=12, pady=6
        ).pack(side="left", padx=(0, 8))
        GhostButton(
            row_c, "打开 QQ 群", command=self.open_qq, padx=12, pady=6
        ).pack(side="left")

        self.lbl_progress = tk.Label(
            self._inner,
            text="",
            font=mono_font(9),
            bg=TM_BG,
            fg=TM_OK,
            anchor="w",
        )
        self.lbl_progress.pack(fill="x", padx=GUTTER, pady=(4, 20))

        self._render_catalog()

    def on_show(self) -> None:
        """Called when user switches to this page."""
        self._render_catalog()

    def save_manifest_url(self) -> None:
        cfg = load_config()
        cfg["update_manifest_url"] = self.var_manifest.get().strip()
        save_config(cfg)
        self.lbl_progress.configure(text="清单地址已保存。", fg=TM_OK)

    def refresh_catalog(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.lbl_progress.configure(text="正在拉取在线清单…", fg=TM_ACCENT)
        urls = []
        u = self.var_manifest.get().strip()
        if u:
            urls.append(u)

        def work():
            try:
                cat = fetch_catalog(urls)
                err = None
            except Exception as e:
                cat = load_bundled_catalog()
                err = str(e)

            def done():
                self._busy = False
                self.catalog = cat
                self._render_catalog()
                if err:
                    self.lbl_progress.configure(
                        text=f"拉取失败，已用本地清单：{err}", fg=TM_WARN
                    )
                else:
                    src = cat.source
                    self.lbl_progress.configure(
                        text=f"清单已更新（来源：{src}，音色 {len(cat.voices)} 个）",
                        fg=TM_OK,
                    )

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _render_catalog(self) -> None:
        cat = self.catalog
        self.lbl_ver.configure(text=f"当前版本  {local_app_version()}")
        st = check_gui_update(cat)
        ptype = st.get("package_type") or PKG_GUI_PATCH
        type_line = f"包类型：{describe_package_type(ptype)}"
        if st["available"]:
            if ptype == PKG_FULL or st.get("action") == "external":
                self.lbl_gui_status.configure(
                    text=(
                        f"发现【全量】更新提示：{st['local']} → {st['remote']}\n"
                        f"{type_line}\n"
                        f"{st['notes'] or ''}\n"
                        "全量包不会在软件内覆盖 Runtime，请用下方按钮打开下载链接，"
                        "解压到新目录后使用。"
                    ),
                    fg=TM_ACCENT,
                )
                self.btn_gui_apply.configure(state="disabled")
            else:
                self.lbl_gui_status.configure(
                    text=(
                        f"发现【增量】GUI 更新：{st['local']} → {st['remote']}\n"
                        f"{type_line}\n"
                        f"{st['notes'] or '（无更新说明）'}"
                    ),
                    fg=TM_ACCENT,
                )
                self.btn_gui_apply.configure(state="normal")
        elif st["url"]:
            self.lbl_gui_status.configure(
                text=(
                    f"已是最新或同版本（本地 {st['local']} · 远程 {st['remote']}）\n"
                    f"{type_line}"
                ),
                fg=TM_INK_MUTED,
            )
            self.btn_gui_apply.configure(state="disabled")
        else:
            self.lbl_gui_status.configure(
                text=(
                    "清单中未配置 gui.url。\n"
                    "增量包：package_type=gui_patch + zip 直链；"
                    "全量包：package_type=full_package + SharePoint/QQ（软件外安装）。"
                ),
                fg=TM_META,
            )
            self.btn_gui_apply.configure(state="disabled")

        note = cat.full_package_note or ""
        lines = [note]
        if cat.qq_group:
            lines.append(f"QQ 群：{cat.qq_group}")
        if cat.sharepoint_full:
            lines.append("SharePoint 完整包：已配置链接")
        else:
            lines.append("SharePoint 完整包：未配置（请编辑 online_catalog.json community.sharepoint_full）")
        self.lbl_community.configure(text="\n".join(lines))

        for w in self.voices_host.winfo_children():
            w.destroy()
        voices = [v for v in cat.voices if v.pth_url]
        if not voices:
            tk.Label(
                self.voices_host,
                text="暂无带直链的音色。编辑 configs/online_catalog.json 的 voices，"
                "或配置远程清单。",
                font=sans_font(10),
                bg=TM_SURFACE,
                fg=TM_META,
                wraplength=640,
                justify="left",
                anchor="w",
            ).pack(anchor="w")
            return

        for v in voices:
            self._voice_row(v)

    def open_full_package_help(self) -> None:
        from launcher.online.package_spec import full_package_policy_help

        url = (self.catalog.sharepoint_full or self.catalog.gui.url or "").strip()
        msg = full_package_policy_help()
        if url and (
            normalize_is_full(self.catalog)
            or (self.catalog.sharepoint_full or "").strip()
        ):
            if messagebox.askyesno(
                "全量包",
                msg + "\n\n是否打开配置的完整包 / 更新链接？",
            ):
                open_in_browser(
                    (self.catalog.sharepoint_full or self.catalog.gui.url or "").strip()
                )
        else:
            messagebox.showinfo("全量包策略", msg)

    def _voice_row(self, v: VoiceEntry) -> None:
        row = tk.Frame(
            self.voices_host,
            bg=TM_BG,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        row.pack(fill="x", pady=6)
        left = tk.Frame(row, bg=TM_BG)
        left.pack(side="left", fill="x", expand=True, padx=12, pady=10)
        tk.Label(
            left,
            text=v.name,
            font=title_font(12, "bold"),
            bg=TM_BG,
            fg=TM_INK,
            anchor="w",
        ).pack(anchor="w")
        kind = "zip包" if v.pack_url else "多文件"
        meta = f"{v.tag}  ·  {kind}  ·  id={v.id}"
        if v.size_bytes:
            meta += f"  ·  {v.size_bytes // 1024 // 1024} MB"
        installed = is_voice_installed(v.id, MODELS_DIR)
        if installed:
            meta += "  ·  已安装"
        tk.Label(
            left,
            text=meta,
            font=mono_font(8),
            bg=TM_BG,
            fg=TM_META,
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        if v.description:
            tk.Label(
                left,
                text=v.description,
                font=sans_font(9),
                bg=TM_BG,
                fg=TM_INK_MUTED,
                wraplength=480,
                justify="left",
                anchor="w",
            ).pack(anchor="w", pady=(4, 0))

        right = tk.Frame(row, bg=TM_BG)
        right.pack(side="right", padx=12, pady=10)
        label = "重新下载" if installed else "下载安装"
        PrimaryButton(
            right,
            label,
            command=lambda e=v: self.download_voice(e),
            padx=12,
            pady=6,
        ).pack()

    def apply_gui(self) -> None:
        if self._busy:
            return
        st = check_gui_update(self.catalog)
        if not st["url"]:
            messagebox.showinfo("GUI 更新", "没有可用的 GUI 更新地址。")
            return
        if st.get("package_type") == PKG_FULL or st.get("action") == "external":
            messagebox.showinfo(
                "全量包",
                "当前清单指向全量包，不能在软件内合并安装。\n"
                "请使用「全量包说明 / 打开链接」。",
            )
            return
        if not messagebox.askyesno(
            "应用增量 GUI 包",
            f"将下载【增量壳层包】并合并覆盖白名单路径（launcher/、configs/ 等）。\n"
            f"{st['local']} → {st['remote']}\n\n"
            "不会替换 Runtime / User_Data / 大权重。\n"
            "若 zip 被识别为全量包将中止。完成后请重启。\n继续？",
        ):
            return
        self._busy = True
        self.lbl_progress.configure(text="正在下载增量 GUI 包…", fg=TM_ACCENT)

        def work():
            try:
                result = download_and_apply_gui(
                    self.catalog.gui,
                    progress=lambda phase, d, t: self.root.after(
                        0,
                        lambda: self.lbl_progress.configure(
                            text=_fmt_prog(phase, d, t), fg=TM_ACCENT
                        ),
                    ),
                )
                err = None
            except Exception as e:
                result = {}
                err = str(e)

            def done():
                self._busy = False
                if err:
                    self.lbl_progress.configure(text=f"GUI 更新失败：{err}", fg=TM_WARN)
                    messagebox.showerror("GUI 更新失败", err)
                else:
                    written = result.get("written") or []
                    self.lbl_progress.configure(
                        text=f"增量包已应用（{len(written)} 个文件），请重启。",
                        fg=TM_OK,
                    )
                    messagebox.showinfo(
                        "完成",
                        f"增量 GUI 已应用（{len(written)} 个文件）。\n"
                        f"类型：{result.get('package_type')}\n"
                        "请关闭并重新打开变声器。",
                    )

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def download_voice(self, entry: VoiceEntry) -> None:
        if self._busy:
            return
        if not entry.pth_url:
            messagebox.showinfo("音色", "该条目没有 pth 直链。")
            return
        self._busy = True
        self.lbl_progress.configure(text=f"正在下载「{entry.name}」…", fg=TM_ACCENT)

        def work():
            try:
                info = install_voice_from_entry(
                    entry,
                    progress=lambda phase, d, t: self.root.after(
                        0,
                        lambda: self.lbl_progress.configure(
                            text=f"{entry.name} · {_fmt_prog(phase, d, t)}",
                            fg=TM_ACCENT,
                        ),
                    ),
                )
                err = None
            except Exception as e:
                info = None
                err = str(e)

            def done():
                self._busy = False
                if err:
                    self.lbl_progress.configure(text=f"下载失败：{err}", fg=TM_WARN)
                    messagebox.showerror("下载失败", err)
                else:
                    self.lbl_progress.configure(
                        text=f"已安装：{info and info.get('name')}",
                        fg=TM_OK,
                    )
                    try:
                        self.app.refresh_models()
                    except Exception:
                        pass
                    self._render_catalog()
                    messagebox.showinfo(
                        "完成",
                        f"音色已安装到：\n{info and info.get('dir')}\n\n可在首页 / 模型页选用。",
                    )

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def open_sharepoint(self) -> None:
        url = (self.catalog.sharepoint_full or "").strip()
        if not url:
            messagebox.showinfo(
                "SharePoint",
                "未配置完整包链接。\n请在 configs/online_catalog.json → community.sharepoint_full 填写。",
            )
            return
        open_in_browser(url)

    def open_qq(self) -> None:
        url = (self.catalog.qq_link or "").strip()
        if url:
            open_in_browser(url)
            return
        g = (self.catalog.qq_group or "").strip()
        if g:
            messagebox.showinfo("QQ 群", f"群号：{g}\n（未配置 qq_link 时请手动搜索加群）")
        else:
            messagebox.showinfo(
                "QQ 群",
                "未配置。请在 configs/online_catalog.json → community.qq_group / qq_link 填写。",
            )


def _fmt_prog(phase: str, done: int, total: int) -> str:
    if total > 0:
        pct = min(100, done * 100 // total)
        return f"{phase}  {pct}%  ({done // 1024} KB / {total // 1024} KB)"
    return f"{phase}  {done // 1024} KB"


def normalize_is_full(cat) -> bool:
    st = check_gui_update(cat)
    return st.get("package_type") == PKG_FULL
