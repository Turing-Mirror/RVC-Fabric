# -*- coding: utf-8 -*-
"""在线功能：设置页内的「在线更新」区块 + 模型页弹出的「社区下载」窗口。

原独立「更新」页已按产品要求拆掉：GUI 更新降级为设置页一个区块；
在线音色库改为模型页的社区下载对话框（首页最新在前分页 + 系列专区折叠视图）。
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
    filter_voices,
    group_series_only,
    is_voice_installed,
    load_bundled_catalog,
    local_app_version,
    paginate,
    sort_voices_newest_first,
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
from launcher.ui.widgets import (
    GhostButton,
    PrimaryButton,
    SearchField,
    SegmentControl,
    center_over,
)

if TYPE_CHECKING:
    from launcher.main_app import MainApp


class StorePage:
    """Owns online-update state; renders into settings card + community dialog."""

    def __init__(self, app: "MainApp", update_parent: tk.Frame) -> None:
        self.app = app
        self.root = app.root
        self.catalog: OnlineCatalog = load_bundled_catalog()
        self._busy = False  # 下载/应用增量占用（互斥用户操作）
        self._refreshing = False  # 清单刷新占用（不阻塞下载点击）
        self._cover_inflight: set = set()  # 封面下载去重（防搜索重建线程放大）
        self._dlg: Optional[tk.Toplevel] = None
        self.voices_host: Optional[tk.Frame] = None
        self._dlg_progress: Optional[tk.Label] = None
        self._voices_search: Optional[SearchField] = None
        self._voices_search_q: str = ""
        self._store_view: str = "home"  # home = 分页平铺 | series = 系列专区
        self._voices_page: int = 1  # 1-based（paginate 会 clamp）
        self._expanded_series: set = set()
        self._voices_pager_host: Optional[tk.Frame] = None
        self._voices_filter_job = None  # 搜索防抖 after id
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

        # 清单地址固定为 CNB（configs/online_catalog.json manifest_urls），
        # 不再提供 UI 覆盖；高级用户仍可手改 app_config.json 的 update_manifest_url。
        self.lbl_progress = tk.Label(
            body,
            text="",
            font=mono_font(9),
            bg=TM_SURFACE,
            fg=TM_OK,
            anchor="w",
        )
        self.lbl_progress.pack(fill="x", pady=(8, 0))

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
        """「社区下载」 window: paged newest-first voices + collapsible series view.

        Every open (including re-focus of an existing dialog) auto-refreshes the
        online catalog so new CNB releases show without a manual「刷新清单」.
        """
        if self._dlg is not None:
            try:
                self._dlg.lift()
                self._dlg.focus_force()
                # Keep typed query if search field still alive
                if self._voices_search is not None:
                    try:
                        self._voices_search_q = self._voices_search.query()
                    except Exception:
                        pass
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
            self._dlg_progress = None
            self._voices_search = None
            self._voices_pager_host = None
            if self._voices_filter_job:
                try:
                    self.root.after_cancel(self._voices_filter_job)
                except Exception:
                    pass
                self._voices_filter_job = None

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

        # Search bar (filters list by name / id / author / tag / series) + view toggle
        search_row = tk.Frame(dlg, bg=TM_BG, padx=GUTTER)
        search_row.pack(fill="x", pady=(0, 8))
        self._voices_search = SearchField(
            search_row,
            placeholder="搜索音色 / 作者 / 系列 / 标签…",
            on_change=self._on_voices_search,
            width=30,
        )
        self._voices_search.pack(side="left", fill="x", expand=True)
        self._voices_view_seg = SegmentControl(
            search_row,
            [("home", "首页"), ("series", "系列专区")],
            value="home",
            on_change=self._on_view_change,
        )
        self._voices_view_seg.pack(side="right", padx=(8, 0))
        # Fresh dialog resets query / view / page (StorePage outlives the Toplevel)
        self._voices_search_q = ""
        self._store_view = "home"
        self._voices_page = 1
        self._expanded_series = set()

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

        # Pager stays outside the canvas so it never scrolls out of reach
        self._voices_pager_host = tk.Frame(dlg, bg=TM_BG, padx=GUTTER)
        self._voices_pager_host.pack(fill="x", pady=(4, 0))

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
        # 刷新用独立 _refreshing 标志：打开对话框自动刷新期间（弱网可达数十秒）
        # 不得占用 _busy，否则「下载安装」点击会被静默吞掉
        if self._refreshing:
            return
        self._refreshing = True
        self._set_progress("正在拉取在线清单…", TM_ACCENT)
        urls = []
        u = str(load_config().get("update_manifest_url") or "").strip()
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
                self._refreshing = False
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

    def _on_voices_search(self, q: str) -> None:
        self._voices_search_q = (q or "").strip()
        self._voices_page = 1  # 新搜索回到第 1 页
        # 120ms debounce（对齐模型页）：逐键全量重建会放大封面轮询与滚轮重绑
        if self._voices_filter_job:
            try:
                self.root.after_cancel(self._voices_filter_job)
            except Exception:
                pass
        self._voices_filter_job = self.root.after(120, self._render_voices_list)

    def _on_view_change(self, key: str) -> None:
        if key == self._store_view:
            return
        self._store_view = key
        self._voices_page = 1
        self._render_voices_list()

    def _render_catalog(self) -> None:
        """Full render: settings update card + dialog voices list."""
        self._render_update_card()
        self._render_voices_list()

    def _render_update_card(self) -> None:
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

    def _render_voices_list(self) -> None:
        """Re-render only the dialog voice list + pager (search/page/view/toggle)."""
        self._voices_filter_job = None
        cat = self.catalog
        host = self.voices_host
        if host is None:
            return
        try:
            for w in host.winfo_children():
                w.destroy()
        except Exception:
            self.voices_host = None
            return
        pager = self._voices_pager_host
        if pager is not None:
            try:
                for w in pager.winfo_children():
                    w.destroy()
            except Exception:
                self._voices_pager_host = None
        voices = [v for v in cat.voices if v.has_download()]
        voices = filter_voices(voices, self._voices_search_q)
        if self._store_view == "series":
            self._render_series_view(voices)
        else:
            self._render_home_view(voices)
        try:
            self.root.after(30, self._dlg_bind_wheel)
        except Exception:
            pass

    def _render_home_view(self, voices: list) -> None:
        """首页：最新上架在前的平铺列表，底部页码分页（每页 5 个）。"""
        if not voices:
            self._voices_empty_label(
                f"没有匹配「{self._voices_search_q}」的音色。"
                if self._voices_search_q
                else "暂无可在线下载的音色。可点「刷新清单」重试，或通过社群获取。"
            )
            return
        ordered = sort_voices_newest_first(voices)
        page_items, self._voices_page, total_pages = paginate(
            ordered, self._voices_page, 5
        )
        for v in page_items:
            self._voice_row(v)
        self._render_voices_pager(total_pages, len(ordered))

    def _render_series_view(self, voices: list) -> None:
        """系列专区：只列现有系列，默认收起；点标题展开；搜索词激活时自动展开。"""
        groups = group_series_only(voices)
        if not groups:
            self._voices_empty_label(
                f"没有匹配「{self._voices_search_q}」的系列音色。"
                if self._voices_search_q
                else "暂无系列音色。可点「刷新清单」重试。"
            )
            return
        q_active = bool(self._voices_search_q)
        for series, group in groups:
            expanded = q_active or (series in self._expanded_series)
            self._series_toggle_header(series, len(group), expanded)
            if expanded:
                for v in group:
                    self._voice_row(v)

    def _voices_empty_label(self, text: str) -> None:
        tk.Label(
            self.voices_host,
            text=text,
            font=sans_font(10),
            bg=TM_BG,
            fg=TM_META,
            wraplength=520,
            justify="left",
            anchor="w",
        ).pack(anchor="w", pady=8)

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

    def _series_toggle_header(self, series: str, count: int, expanded: bool) -> None:
        """系列专区折叠标题 — 整行可点，▸ 收起 / ▾ 展开（几何箭头，非 emoji）。"""
        head = tk.Frame(self.voices_host, bg=TM_BG, cursor="hand2")
        head.pack(fill="x", pady=(10, 6))
        arrow = "▾" if expanded else "▸"
        left = tk.Label(
            head,
            text=f"{arrow} 系列 · {series}",
            font=mono_font(8),
            bg=TM_BG,
            fg=TM_META,
            anchor="w",
        )
        left.pack(side="left")
        right = tk.Label(
            head,
            text=f"{count} 个音色",
            font=mono_font(8),
            bg=TM_BG,
            fg=TM_META,
            anchor="e",
        )
        right.pack(side="right")
        for w in (head, left, right):
            w.bind("<Button-1>", lambda _e, s=series: self._toggle_series(s))
        tk.Frame(self.voices_host, bg=TM_HAIRLINE, height=1).pack(fill="x")

    def _toggle_series(self, series: str) -> None:
        if series in self._expanded_series:
            self._expanded_series.discard(series)
        else:
            self._expanded_series.add(series)
        self._render_voices_list()

    def _render_voices_pager(self, total_pages: int, total_items: int) -> None:
        """页码条：【1】【2】…、第 N/M 页 · 共 X 个、跳到 x 页。单页时留空。"""
        host = self._voices_pager_host
        if host is None or total_pages <= 1:
            return
        cur = self._voices_page

        def page_btn(p: int) -> None:
            cls = PrimaryButton if p == cur else GhostButton
            btn = cls(
                host,
                str(p),
                command=(None if p == cur else (lambda p=p: self._set_voices_page(p))),
                padx=10,
                pady=4,
                font=mono_font(9),
            )
            btn.pack(side="left", padx=2)

        def ellipsis() -> None:
            tk.Label(host, text="…", font=mono_font(9), bg=TM_BG, fg=TM_META).pack(
                side="left", padx=2
            )

        if total_pages <= 7:
            pages = list(range(1, total_pages + 1))
        else:
            mid = [p for p in (cur - 1, cur, cur + 1) if 1 < p < total_pages]
            pages = [1] + mid + [total_pages]
        prev = 0
        for p in pages:
            if p - prev > 1:
                ellipsis()
            page_btn(p)
            prev = p

        # Right side: jump entry + summary（pack 逆序从右往左排）
        GhostButton(
            host,
            "跳转",
            command=lambda: self._jump_to_page(jump),
            padx=8,
            pady=3,
            font=mono_font(9),
        ).pack(side="right", padx=(4, 0))
        tk.Label(host, text="页", font=mono_font(9), bg=TM_BG, fg=TM_META).pack(
            side="right"
        )
        jump = tk.Entry(
            host,
            width=3,
            font=mono_font(9),
            justify="center",
            relief="flat",
            bg=TM_SURFACE,
            fg=TM_INK,
            insertbackground=TM_INK,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        jump.pack(side="right", padx=(4, 2))
        jump.bind("<Return>", lambda _e: self._jump_to_page(jump))
        tk.Label(host, text="跳到", font=mono_font(9), bg=TM_BG, fg=TM_META).pack(
            side="right"
        )
        tk.Label(
            host,
            text=f"第 {cur} / {total_pages} 页 · 共 {total_items} 个",
            font=mono_font(9),
            bg=TM_BG,
            fg=TM_META,
        ).pack(side="right", padx=(0, 10))

    def _set_voices_page(self, page: int) -> None:
        self._voices_page = int(page)  # paginate clamps out-of-range values
        self._render_voices_list()

    def _jump_to_page(self, entry: tk.Entry) -> None:
        try:
            self._set_voices_page(int(entry.get().strip()))
        except (ValueError, tk.TclError):
            pass  # 非数字输入静默忽略

    def _voice_row(self, v: VoiceEntry) -> None:
        row = tk.Frame(
            self.voices_host,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        row.pack(fill="x", pady=5)

        installed = is_voice_installed(v.id, MODELS_DIR)
        # Pack button first (side=right) so meta text cannot squeeze it.
        right = tk.Frame(row, bg=TM_SURFACE)
        right.pack(side="right", padx=(4, 12), pady=10)
        label = "重新下载" if installed else "下载安装"
        PrimaryButton(
            right,
            label,
            command=lambda e=v: self.download_voice(e),
            padx=12,
            pady=6,
        ).pack()

        if v.cover_url:
            try:
                self._attach_cover_thumb(row, v)
            except Exception:
                pass

        left = tk.Frame(row, bg=TM_SURFACE)
        left.pack(side="left", fill="both", expand=True, padx=(8, 8), pady=10)
        tk.Label(
            left,
            text=v.name,
            font=title_font(12, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
            bd=0,
            highlightthickness=0,
        ).pack(anchor="w")
        kind = "音色包" if v.pack_url else "多文件"
        meta = f"{v.tag}  ·  {kind}"
        if v.series:
            meta += f"  ·  系列: {v.series}"
        if v.author:
            meta += f"  ·  作者: {v.author}"
        if v.date:
            meta += f"  ·  {v.date}"
        if v.size_bytes:
            meta += f"  ·  {v.size_bytes // 1024 // 1024} MB"
        if installed:
            meta += "  ·  已安装"
        tk.Label(
            left,
            text=meta,
            font=mono_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
            # Long meta wraps instead of stealing button width
            wraplength=360,
            justify="left",
            bd=0,
            highlightthickness=0,
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
                wraplength=360,
                justify="left",
                bd=0,
                highlightthickness=0,
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
                wraplength=360,
                justify="left",
                anchor="w",
                bd=0,
                highlightthickness=0,
            ).pack(anchor="w", pady=(4, 0))

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
        # 搜索每键会重建列表；同一封面的下载线程只允许一个在途。
        # 命中在途时轮询缓存，下载完成后仍能点亮当前这行的缩略图。
        if v.cover_url in self._cover_inflight:

            def _poll(tries: int = 20) -> None:
                if not lbl.winfo_exists():
                    return
                photo = cache.get(v.cover_url)
                if photo is not None:
                    lbl.configure(image=photo)
                elif tries > 0:
                    # 不依赖 inflight 状态：worker 清掉 inflight 与 apply()
                    # 写入缓存之间有窗口，多轮询几次直到拿到或超时
                    self.root.after(500, lambda: _poll(tries - 1))

            self.root.after(500, _poll)
            return
        self._cover_inflight.add(v.cover_url)

        def work() -> None:
            try:
                req = urllib.request.Request(
                    v.cover_url, headers={"User-Agent": "RVCFabric/1.0"}
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    raw = resp.read()
                from PIL import Image, ImageTk

                # Contain (not crop): full standing art stays visible in the square
                im = Image.open(io.BytesIO(raw)).convert("RGBA")
                box_s = 56
                w, h = im.size
                scale = min(box_s / max(w, 1), box_s / max(h, 1))
                nw = max(1, int(round(w * scale)))
                nh = max(1, int(round(h * scale)))
                im = im.resize((nw, nh), Image.Resampling.LANCZOS)
                canvas = Image.new("RGB", (box_s, box_s), (240, 244, 248))
                canvas.paste(
                    im,
                    ((box_s - nw) // 2, (box_s - nh) // 2),
                    im.split()[-1],
                )

                def apply() -> None:
                    try:
                        photo = ImageTk.PhotoImage(canvas)
                        cache[v.cover_url] = photo
                        if lbl.winfo_exists():
                            lbl.configure(image=photo)
                    except Exception:
                        pass

                self.root.after(0, apply)
            except Exception:
                pass
            finally:
                self._cover_inflight.discard(v.cover_url)

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


def _fmt_prog(phase: str, done: int, total: int) -> str:
    if total > 0:
        pct = min(100, done * 100 // total)
        return f"{phase}  {pct}%  ({done // 1024} KB / {total // 1024} KB)"
    return f"{phase}  {done // 1024} KB"


def normalize_is_full(cat) -> bool:
    st = check_gui_update(cat)
    return st.get("package_type") == PKG_FULL
