# -*- coding: utf-8 -*-
"""在线功能：设置页内的「在线更新」区块 + 模型页弹出的「社区下载」窗口。

原独立「更新」页已按产品要求拆掉：GUI 更新降级为设置页一个区块；
在线音色库改为模型页的社区下载对话框。完整包 / 社群链接放在对话框内。
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING, Optional

from launcher.config_store import load_config, save_config
from launcher.online.catalog import (
    OnlineCatalog,
    VoiceEntry,
    fetch_catalog,
    is_voice_installed,
    load_bundled_catalog,
    local_app_version,
)
from launcher.online.downloader import open_in_browser
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
)
from launcher.ui.widgets import GhostButton, PrimaryButton, center_over

if TYPE_CHECKING:
    from launcher.main_app import MainApp


class StorePage:
    """Owns online-update state; renders into settings card + community dialog."""

    def __init__(self, app: "MainApp", update_parent: tk.Frame) -> None:
        self.app = app
        self.root = app.root
        self.catalog: OnlineCatalog = load_bundled_catalog()
        self._busy = False
        self._dlg: Optional[tk.Toplevel] = None
        self.voices_host: Optional[tk.Frame] = None
        self.lbl_community: Optional[tk.Label] = None
        self._dlg_progress: Optional[tk.Label] = None
        self._dlg_bind_wheel = lambda: None
        self._build_update_section(update_parent)
        self._render_catalog()

    # ------------------------------------------------------------------ update
    def _build_update_section(self, body: tk.Frame) -> None:
        """Settings-page card body: version, status, actions, manifest URL."""
        self.lbl_ver = tk.Label(
            body,
            text=f"当前版本  {local_app_version()}",
            font=mono_font(9),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        )
        self.lbl_ver.pack(anchor="w")
        self.lbl_gui_status = tk.Label(
            body,
            text="点击「检查更新」拉取在线清单。",
            font=sans_font(10),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            anchor="w",
            wraplength=640,
            justify="left",
        )
        self.lbl_gui_status.pack(anchor="w", pady=(6, 8))
        row_g = tk.Frame(body, bg=TM_SURFACE)
        row_g.pack(anchor="w")
        PrimaryButton(
            row_g, "检查更新", command=self.refresh_catalog, padx=14, pady=6
        ).pack(side="left", padx=(0, 8))
        self.btn_gui_apply = PrimaryButton(
            row_g, "下载并应用增量包", command=self.apply_gui, padx=14, pady=6
        )
        self.btn_gui_apply.pack(side="left", padx=4)
        self.btn_gui_apply.configure(state="disabled")
        GhostButton(
            row_g,
            "全量包说明 / 打开链接",
            command=self.open_full_package_help,
            padx=12,
            pady=6,
        ).pack(side="left", padx=4)

        # Manifest URL (merged into the same card)
        tk.Label(
            body,
            text="在线清单地址（可选，覆盖内置 configs/online_catalog.json）：",
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            anchor="w",
        ).pack(anchor="w", pady=(12, 0))
        self.var_manifest = tk.StringVar(
            value=str(load_config().get("update_manifest_url") or "")
        )
        row_u = tk.Frame(body, bg=TM_SURFACE)
        row_u.pack(fill="x", pady=(6, 0))
        tk.Entry(
            row_u,
            textvariable=self.var_manifest,
            font=mono_font(9),
            bg=TM_BG,
            fg=TM_INK,
            relief="flat",
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        ).pack(side="left", fill="x", expand=True, ipady=6)
        GhostButton(
            row_u, "保存地址", command=self.save_manifest_url, padx=12, pady=5
        ).pack(side="left", padx=(8, 0))

        self.lbl_progress = tk.Label(
            body,
            text="",
            font=mono_font(9),
            bg=TM_SURFACE,
            fg=TM_OK,
            anchor="w",
        )
        self.lbl_progress.pack(fill="x", pady=(8, 0))

    def save_manifest_url(self) -> None:
        cfg = load_config()
        cfg["update_manifest_url"] = self.var_manifest.get().strip()
        save_config(cfg)
        self._set_progress("清单地址已保存。", TM_OK)

    def _set_progress(self, text: str, fg: str) -> None:
        """Update every live progress label (settings card + dialog if open)."""
        for lbl in (self.lbl_progress, self._dlg_progress):
            if lbl is None:
                continue
            try:
                lbl.configure(text=text, fg=fg)
            except Exception:
                pass

    # ------------------------------------------------------------ voices dialog
    def open_voices_dialog(self) -> None:
        """「社区下载」 window: online voices + full package / community links.

        Every open (including re-focus of an existing dialog) auto-refreshes the
        online catalog so new CNB releases show without a manual「刷新清单」.
        """
        if self._dlg is not None:
            try:
                self._dlg.lift()
                self._dlg.focus_force()
                # Re-open: still pull latest list
                self.root.after(50, self.refresh_catalog)
                return
            except Exception:
                self._dlg = None
        dlg = tk.Toplevel(self.root)
        dlg.title("社区下载 · 在线音色库")
        dlg.configure(bg=TM_BG)
        dlg.transient(self.root)
        try:
            dlg.geometry("640x640")
            dlg.minsize(520, 480)
        except Exception:
            pass
        center_over(dlg, self.root)
        self._dlg = dlg

        def _closed(_e=None):
            self._dlg = None
            self.voices_host = None
            self.lbl_community = None
            self._dlg_progress = None

        dlg.bind("<Destroy>", lambda e: _closed() if e.widget is dlg else None)

        head = tk.Frame(dlg, bg=TM_BG, padx=GUTTER, pady=12)
        head.pack(fill="x")
        tk.Label(
            head,
            text="社区下载",
            font=title_font(15, "bold"),
            bg=TM_BG,
            fg=TM_INK,
            anchor="w",
        ).pack(side="left")
        GhostButton(
            head, "刷新清单", command=self.refresh_catalog, padx=12, pady=5
        ).pack(side="right")

        # Scrollable voices list with a visible scrollbar
        host = tk.Frame(dlg, bg=TM_BG)
        host.pack(fill="both", expand=True, padx=GUTTER)
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)
        canvas = tk.Canvas(host, bg=TM_BG, highlightthickness=0)
        sb = tk.Scrollbar(host, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=TM_BG)
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        def _sync(_e=None):
            try:
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass

        def _width(e):
            if e.width > 1:
                canvas.itemconfigure(win, width=e.width)

        inner.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _width)

        def _wheel(e):
            try:
                if getattr(e, "delta", 0):
                    canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except Exception:
                pass
            return "break"

        def _bind_tree(w):
            try:
                w.bind("<MouseWheel>", _wheel, add="+")
                for ch in w.winfo_children():
                    _bind_tree(ch)
            except Exception:
                pass

        self._dlg_bind_wheel = lambda: _bind_tree(dlg)

        self.voices_host = tk.Frame(inner, bg=TM_BG)
        self.voices_host.pack(fill="x", pady=(4, 8))

        # Community / full package block at the bottom of the dialog
        comm = tk.Frame(
            inner,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        comm.pack(fill="x", pady=(4, 12))
        comm_in = tk.Frame(comm, bg=TM_SURFACE, padx=14, pady=12)
        comm_in.pack(fill="x")
        tk.Label(
            comm_in,
            text="完整包与社群",
            font=title_font(11, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        ).pack(anchor="w")
        self.lbl_community = tk.Label(
            comm_in,
            text="",
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_INK_MUTED,
            wraplength=520,
            justify="left",
            anchor="w",
        )
        self.lbl_community.pack(anchor="w", pady=(4, 8))
        row_c = tk.Frame(comm_in, bg=TM_SURFACE)
        row_c.pack(anchor="w")
        GhostButton(
            row_c, "打开完整包链接", command=self.open_sharepoint, padx=12, pady=6
        ).pack(side="left", padx=(0, 8))
        GhostButton(row_c, "打开 QQ 群", command=self.open_qq, padx=12, pady=6).pack(
            side="left"
        )

        self._dlg_progress = tk.Label(
            dlg,
            text="",
            font=mono_font(9),
            bg=TM_BG,
            fg=TM_OK,
            anchor="w",
            padx=GUTTER,
        )
        self._dlg_progress.pack(fill="x", pady=(0, 10))

        # Show cached list first, then always refresh from network on open
        self._render_catalog()
        self.root.after(60, self._dlg_bind_wheel)
        self.root.after(120, self.refresh_catalog)

    # ---------------------------------------------------------------- catalog
    def refresh_catalog(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._set_progress("正在拉取在线清单…", TM_ACCENT)
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
                    self._set_progress(f"拉取失败，已用本地清单:{err}", TM_WARN)
                else:
                    self._set_progress(
                        f"清单已更新（来源:{cat.source}，音色 {len(cat.voices)} 个）",
                        TM_OK,
                    )

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _render_catalog(self) -> None:
        cat = self.catalog
        try:
            self.lbl_ver.configure(text=f"当前版本  {local_app_version()}")
        except Exception:
            pass
        st = check_gui_update(cat)
        ptype = st.get("package_type") or PKG_GUI_PATCH
        type_line = f"包类型:{describe_package_type(ptype)}"
        if st["available"]:
            if ptype == PKG_FULL or st.get("action") == "external":
                self.lbl_gui_status.configure(
                    text=(
                        f"发现【全量】更新提示:{st['local']} → {st['remote']}\n"
                        f"{type_line}\n"
                        f"{st['notes'] or ''}\n"
                        "全量包不会在软件内覆盖 Runtime，请用「全量包说明」按钮打开下载链接，"
                        "解压到新目录后使用。"
                    ),
                    fg=TM_ACCENT,
                )
                self.btn_gui_apply.configure(state="disabled")
            else:
                self.lbl_gui_status.configure(
                    text=(
                        f"发现【增量】软件更新:{st['local']} → {st['remote']}\n"
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
                text="清单中未配置软件更新地址。",
                fg=TM_META,
            )
            self.btn_gui_apply.configure(state="disabled")

        if self.lbl_community is not None:
            note = cat.full_package_note or ""
            lines = [note] if note else []
            if cat.qq_group:
                lines.append(f"QQ 群:{cat.qq_group}")
            if cat.sharepoint_full:
                lines.append("完整包链接:已配置")
            else:
                lines.append("完整包链接:未配置")
            try:
                self.lbl_community.configure(text="\n".join(lines))
            except Exception:
                pass

        host = self.voices_host
        if host is None:
            return
        try:
            for w in host.winfo_children():
                w.destroy()
        except Exception:
            self.voices_host = None
            return
        voices = [v for v in cat.voices if v.has_download()]
        if not voices:
            tk.Label(
                host,
                text="暂无可在线下载的音色。可点「刷新清单」重试，或通过社群获取。",
                font=sans_font(10),
                bg=TM_BG,
                fg=TM_META,
                wraplength=520,
                justify="left",
                anchor="w",
            ).pack(anchor="w", pady=8)
        else:
            for v in voices:
                self._voice_row(v)
        try:
            self.root.after(30, self._dlg_bind_wheel)
        except Exception:
            pass

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
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        row.pack(fill="x", pady=5)
        if v.cover_url:
            try:
                self._attach_cover_thumb(row, v)
            except Exception:
                pass
        left = tk.Frame(row, bg=TM_SURFACE)
        left.pack(side="left", fill="x", expand=True, padx=12, pady=10)
        tk.Label(
            left,
            text=v.name,
            font=title_font(12, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        ).pack(anchor="w")
        kind = "音色包" if v.pack_url else "多文件"
        meta = f"{v.tag}  ·  {kind}"
        if v.author:
            meta += f"  ·  作者: {v.author}"
        if v.date:
            meta += f"  ·  {v.date}"
        if v.size_bytes:
            meta += f"  ·  {v.size_bytes // 1024 // 1024} MB"
        installed = is_voice_installed(v.id, MODELS_DIR)
        if installed:
            meta += "  ·  已安装"
        tk.Label(
            left,
            text=meta,
            font=mono_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        if v.author_url:
            link = tk.Label(
                left,
                text=v.author_url,
                font=mono_font(7),
                bg=TM_SURFACE,
                fg=TM_ACCENT,
                anchor="w",
                cursor="hand2",
            )
            link.pack(anchor="w")
            link.bind(
                "<Button-1>",
                lambda _e, u=v.author_url: open_in_browser(u),
            )
        if v.description:
            tk.Label(
                left,
                text=v.description,
                font=sans_font(9),
                bg=TM_SURFACE,
                fg=TM_INK_MUTED,
                wraplength=340,
                justify="left",
                anchor="w",
            ).pack(anchor="w", pady=(4, 0))

        right = tk.Frame(row, bg=TM_SURFACE)
        right.pack(side="right", padx=12, pady=10)
        label = "重新下载" if installed else "下载安装"
        PrimaryButton(
            right,
            label,
            command=lambda e=v: self.download_voice(e),
            padx=12,
            pady=6,
        ).pack()

    def _attach_cover_thumb(self, row: tk.Frame, v: VoiceEntry) -> None:
        """Show ch-banner cover from cover_url (async)."""
        import io
        import urllib.request

        from launcher.theme import TM_INSET

        box = tk.Frame(row, bg=TM_INSET, width=56, height=56)
        box.pack(side="left", padx=(10, 0), pady=10)
        box.pack_propagate(False)
        lbl = tk.Label(box, text="", bg=TM_INSET)
        lbl.pack(expand=True)
        cache = getattr(self, "_cover_photos", None)
        if cache is None:
            self._cover_photos = {}
            cache = self._cover_photos
        if v.cover_url in cache:
            lbl.configure(image=cache[v.cover_url])
            return

        def work() -> None:
            try:
                req = urllib.request.Request(
                    v.cover_url, headers={"User-Agent": "RVCFabric/1.0"}
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    raw = resp.read()
                from PIL import Image, ImageTk

                im = Image.open(io.BytesIO(raw)).convert("RGB")
                im.thumbnail((56, 56))

                def apply() -> None:
                    try:
                        photo = ImageTk.PhotoImage(im)
                        cache[v.cover_url] = photo
                        if lbl.winfo_exists():
                            lbl.configure(image=photo)
                    except Exception:
                        pass

                self.root.after(0, apply)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def apply_gui(self) -> None:
        if self._busy:
            return
        st = check_gui_update(self.catalog)
        if not st["url"]:
            messagebox.showinfo("软件更新", "没有可用的更新地址。")
            return
        if st.get("package_type") == PKG_FULL or st.get("action") == "external":
            messagebox.showinfo(
                "全量包",
                "当前清单指向全量包，不能在软件内合并安装。\n"
                "请使用「全量包说明 / 打开链接」。",
            )
            return
        if not messagebox.askyesno(
            "应用增量更新",
            f"将下载增量更新包并覆盖软件文件（不动 Runtime / User_Data / 模型）。\n"
            f"{st['local']} → {st['remote']}\n\n完成后请重启软件。继续？",
        ):
            return
        self._busy = True
        self._set_progress("正在下载增量更新包…", TM_ACCENT)

        def work():
            try:
                result = download_and_apply_gui(
                    self.catalog.gui,
                    progress=lambda phase, d, t: self.root.after(
                        0,
                        lambda p=phase, dd=d, tt=t: self._set_progress(
                            _fmt_prog(p, dd, tt), TM_ACCENT
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
                    self._set_progress(f"更新失败:{err}", TM_WARN)
                    messagebox.showerror("更新失败", err)
                else:
                    written = result.get("written") or []
                    self._set_progress(
                        f"增量包已应用（{len(written)} 个文件），请重启。", TM_OK
                    )
                    messagebox.showinfo(
                        "完成",
                        f"更新已应用（{len(written)} 个文件）。\n"
                        "请关闭并重新打开软件。",
                    )

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def download_voice(self, entry: VoiceEntry) -> None:
        if self._busy:
            return
        if not entry.has_download():
            messagebox.showinfo("音色", "该条目没有下载地址。")
            return
        self._busy = True
        self._set_progress(f"正在下载「{entry.name}」…", TM_ACCENT)

        def work():
            try:
                info = install_voice_from_entry(
                    entry,
                    progress=lambda phase, d, t: self.root.after(
                        0,
                        lambda p=phase, dd=d, tt=t, n=entry.name: self._set_progress(
                            f"{n} · {_fmt_prog(p, dd, tt)}", TM_ACCENT
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
                    self._set_progress(f"下载失败:{err}", TM_WARN)
                    messagebox.showerror("下载失败", err)
                else:
                    self._set_progress(f"已安装:{info and info.get('name')}", TM_OK)
                    try:
                        self.app.refresh_models()
                    except Exception:
                        pass
                    self._render_catalog()
                    messagebox.showinfo(
                        "完成",
                        f"音色已安装到:\n{info and info.get('dir')}\n\n"
                        "可在首页 / 模型页选用。",
                    )

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def open_sharepoint(self) -> None:
        url = (self.catalog.sharepoint_full or "").strip()
        if not url:
            messagebox.showinfo(
                "完整包",
                "未配置完整包链接。请通过 QQ 群等社群渠道获取。",
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
            messagebox.showinfo("QQ 群", f"群号:{g}\n（可在 QQ 中搜索群号加群）")
        else:
            messagebox.showinfo("QQ 群", "未配置社群信息。")


def _fmt_prog(phase: str, done: int, total: int) -> str:
    if total > 0:
        pct = min(100, done * 100 // total)
        return f"{phase}  {pct}%  ({done // 1024} KB / {total // 1024} KB)"
    return f"{phase}  {done // 1024} KB"


def normalize_is_full(cat) -> bool:
    st = check_gui_update(cat)
    return st.get("package_type") == PKG_FULL
