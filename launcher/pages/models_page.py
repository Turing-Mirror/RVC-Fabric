# -*- coding: utf-8 -*-
"""Voice catalog page: cover grid + search/sort filter row.

Split out of main_app. Relies on MainApp state (self.body, self.models,
self.model_idx, self.cfg, self._cover_cache, self._select_model, …) which is
present on the composed instance.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

from launcher.catalog import filter_sort_models, import_model_to_catalog
from launcher.paths import MODELS_DIR, list_voice_models
from launcher.theme import (
    GUTTER,
    TM_BG,
    TM_INK,
    TM_INK_MUTED,
    TM_META,
    TM_OK,
    mono_font,
    sans_font,
    title_font,
)
from launcher.ui import (
    GhostButton,
    ModelCoverCard,
    PrimaryButton,
    SearchField,
    SegmentControl,
    ask_choice,
)
from launcher.win_util import open_path


class ModelsPageMixin:
    def _page_models(self) -> tk.Frame:
        """Plain top-down flow: header → filter → paged catalog → index →
        profiles. The whole page scrolls (same pattern as 设置页); the catalog
        itself is PAGED — max 3 card rows per page, no inner scrollbar, and no
        blank filler when a page has fewer rows."""
        fr = tk.Frame(self.body, bg=TM_BG)
        canvas = tk.Canvas(fr, bg=TM_BG, highlightthickness=0)
        sb = ttk.Scrollbar(fr, orient="vertical", command=canvas.yview)
        wrap = tk.Frame(canvas, bg=TM_BG)
        win_id = canvas.create_window((0, 0), window=wrap, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._models_canvas = canvas  # page viewport; width drives column count
        self._models_page = 0

        def _sync(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _width(e):
            if e.width > 1:
                canvas.itemconfigure(win_id, width=e.width)
                self._schedule_models_reflow()

        wrap.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _width)

        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        def _bind_wheel_tree(w):
            w.bind("<MouseWheel>", _wheel)
            for ch in w.winfo_children():
                _bind_wheel_tree(ch)

        canvas.bind("<MouseWheel>", _wheel)
        self._models_bind_wheel = lambda: _bind_wheel_tree(wrap)

        # --- Header: title + funnel button inline; actions on the right ---
        bar = tk.Frame(wrap, bg=TM_BG)
        bar.pack(fill="x", padx=GUTTER, pady=(18, 8))
        left = tk.Frame(bar, bg=TM_BG)
        left.pack(side="left", fill="x", expand=True)
        title_row = tk.Frame(left, bg=TM_BG)
        title_row.pack(anchor="w")
        tk.Label(
            title_row,
            text="音色目录",
            font=title_font(22, "bold"),
            bg=TM_BG,
            fg=TM_INK,
        ).pack(side="left")
        PrimaryButton(
            title_row,
            "✦ 想更像这个角色？申请专业优化",
            command=self.open_consult_wizard,
            padx=14,
            pady=7,
        ).pack(side="left", padx=(16, 0))
        self.models_status_lbl = tk.Label(
            left,
            text="",
            font=mono_font(9),
            bg=TM_BG,
            fg=TM_META,
        )
        self.models_status_lbl.pack(anchor="w", pady=(6, 0))

        actions = tk.Frame(bar, bg=TM_BG)
        actions.pack(side="right", anchor="n", pady=(8, 0))
        GhostButton(
            actions, "打开目录", command=lambda: open_path(MODELS_DIR), padx=12, pady=6
        ).pack(side="right", padx=4)
        GhostButton(actions, "刷新", command=self.refresh_models, padx=12, pady=6).pack(
            side="right", padx=4
        )
        GhostButton(actions, "导入模型", command=self.import_model, padx=12, pady=6).pack(
            side="right", padx=4
        )
        PrimaryButton(
            actions,
            "社区下载",
            command=lambda: self._store_page.open_voices_dialog(),
            padx=14,
            pady=6,
        ).pack(side="right", padx=4)

        # --- Filter row: search + sort ---
        filt = tk.Frame(wrap, bg=TM_BG)
        filt.pack(fill="x", padx=GUTTER, pady=(0, 6))
        self._models_search = SearchField(
            filt,
            placeholder="搜索音色 / 标签…",
            on_change=lambda _q: self._apply_models_filter(),
            width=22,
        )
        self._models_search.pack(side="left")
        sort_wrap = tk.Frame(filt, bg=TM_BG)
        sort_wrap.pack(side="right")
        self._models_sort_seg = SegmentControl(
            sort_wrap,
            [("default", "默认"), ("name", "名称"), ("index", "检索库")],
            value="default",
            on_change=lambda _k: self._apply_models_filter(),
        )
        self._models_sort_seg.pack(side="left")

        # --- Paged catalog: plain frame, height = exactly the rows shown ---
        self.model_grid = tk.Frame(wrap, bg=TM_BG)
        self.model_grid.pack(fill="x", padx=GUTTER - 8, pady=(4, 0))

        # Pager (built in refresh; collapses to nothing when single page)
        self._models_pager = tk.Frame(wrap, bg=TM_BG)
        self._models_pager.pack(fill="x", padx=GUTTER, pady=(2, 4))

        # --- Index bindings, then config profiles — natural flow below ---
        panel_host = tk.Frame(wrap, bg=TM_BG)
        panel_host.pack(fill="x", padx=GUTTER, pady=(0, 16))
        self._models_panel_host = panel_host
        try:
            self._build_index_panel(panel_host)
        except Exception:
            pass
        try:
            self._build_profiles_panel(panel_host)
        except Exception:
            pass
        return fr

    def _models_page_shift(self, delta: int) -> None:
        self._models_page = max(0, int(getattr(self, "_models_page", 0)) + delta)
        self.refresh_models()

    def _render_models_pager(self, total_pages: int, total_items: int) -> None:
        pager = getattr(self, "_models_pager", None)
        if pager is None:
            return
        for w in pager.winfo_children():
            w.destroy()
        if total_pages <= 1:
            return
        cur = int(getattr(self, "_models_page", 0))
        box = tk.Frame(pager, bg=TM_BG)
        box.pack(side="right")
        GhostButton(box, "上一页", command=lambda: self._models_page_shift(-1),
                    padx=12, pady=5).pack(side="left", padx=(0, 8))
        tk.Label(
            box,
            text=f"第 {cur + 1} / {total_pages} 页 · 共 {total_items} 个",
            font=mono_font(9),
            bg=TM_BG,
            fg=TM_META,
        ).pack(side="left")
        GhostButton(box, "下一页", command=lambda: self._models_page_shift(1),
                    padx=12, pady=5).pack(side="left", padx=(8, 0))

    def _schedule_models_reflow(self) -> None:
        if getattr(self, "_models_job", None):
            try:
                self.root.after_cancel(self._models_job)
            except Exception:
                pass
        self._models_job = self.root.after(100, self.refresh_models)

    def _apply_models_filter(self) -> None:
        """Re-render the grid for the current search/sort without a disk rescan."""
        if not hasattr(self, "model_grid"):
            return
        self._models_page = 0  # a new filter starts from its first page
        # refresh_models re-lists from disk; that's cheap and keeps things simple,
        # but debounce so fast typing doesn't rescan on every keystroke
        if getattr(self, "_models_filter_job", None):
            try:
                self.root.after_cancel(self._models_filter_job)
            except Exception:
                pass
        self._models_filter_job = self.root.after(120, self.refresh_models)

    def refresh_models(self) -> None:
        if not hasattr(self, "model_grid"):
            return
        self.models = list_voice_models()
        if self.model_idx >= len(self.models):
            self.model_idx = max(0, len(self.models) - 1)

        # Restore selection from saved path if possible
        want = self.cfg.get("last_model_path") or self.cfg.get("last_model")
        if want and self.models:
            for i, m in enumerate(self.models):
                if m.get("path") == want or m.get("file") == want or m.get("name") == want:
                    self.model_idx = i
                    break

        for w in self.model_grid.winfo_children():
            w.destroy()

        # Search + sort view (self.models stays the full list — carousel,
        # hotkeys and model_idx all index into it)
        query = ""
        sort = "default"
        if getattr(self, "_models_search", None) is not None:
            query = self._models_search.query()
        if getattr(self, "_models_sort_seg", None) is not None:
            sort = self._models_sort_seg.value()
        view = filter_sort_models(self.models, query, sort=sort)
        idx_by_path = {m.get("path"): i for i, m in enumerate(self.models)}

        if hasattr(self, "models_status_lbl"):
            if not self.models:
                self.models_status_lbl.configure(text="共 0 个音色")
            elif query and len(view) != len(self.models):
                self.models_status_lbl.configure(
                    text=f"共 {len(self.models)} 个 · 匹配 {len(view)} 个"
                )
            else:
                cur = self.models[self.model_idx]["name"]
                self.models_status_lbl.configure(
                    text=f"共 {len(self.models)} 个 · 使用中：{cur}"
                )

        if not self.models:
            tk.Label(
                self.model_grid,
                text="还没有音色。点「社区下载」在线获取，或点「导入模型」添加本地 .pth。",
                bg=TM_BG,
                fg=TM_INK_MUTED,
                font=sans_font(11),
            ).grid(row=0, column=0, padx=20, pady=40, sticky="w")
            self._render_models_pager(0, 0)
            self._models_after_refresh()
            return

        if not view:
            tk.Label(
                self.model_grid,
                text=f"没有匹配「{query}」的音色。清空搜索可看全部。",
                bg=TM_BG,
                fg=TM_INK_MUTED,
                font=sans_font(11),
            ).grid(row=0, column=0, padx=20, pady=40, sticky="w")
            self._render_models_pager(0, 0)
            self._models_after_refresh()
            return

        # Columns adapt to width — cover-first cards need more width
        self._models_canvas.update_idletasks()
        cw = max(self._models_canvas.winfo_width() - 2 * (GUTTER - 8), 320)
        card_min = 180
        cols = max(1, min(5, cw // (card_min + 20)))
        for c in range(cols):
            self.model_grid.columnconfigure(c, weight=1, uniform="m")

        # Pagination: at most 3 card rows per page; fewer rows = shorter page
        page_size = cols * 3
        total_pages = (len(view) + page_size - 1) // page_size
        self._models_page = min(max(0, int(getattr(self, "_models_page", 0))),
                                total_pages - 1)
        start = self._models_page * page_size
        page_view = view[start:start + page_size]

        for pos, m in enumerate(page_view):
            r, c = divmod(pos, cols)
            full_ix = idx_by_path.get(m.get("path"), 0)
            active = self._is_active_model(m)
            photo = self._cover_cache.get(
                m.get("cover"), max_w=card_min + 40, max_h=130
            )
            card = ModelCoverCard(
                self.model_grid,
                name=m["name"],
                tag=m.get("tag") or "音色",
                photo=photo,
                active=active,
                focus=active,
                index_text="✓ 检索库" if (m.get("index") or "") else "",
                width=max(card_min, 180),
                height=250,
                on_click=lambda ix=full_ix: self._use_model_from_grid(ix),
                action_text="使用中" if active else "使用",
                on_action=None if active else (lambda ix=full_ix: self._use_model_from_grid(ix)),
            )
            card.grid(row=r, column=c, padx=10, pady=10, sticky="nsew")
            self.model_grid.rowconfigure(r, weight=0)
            self._attach_model_menu(card, m, full_ix)

        self._render_models_pager(total_pages, len(view))
        self._models_after_refresh()

    def _models_after_refresh(self) -> None:
        self._sync_bottom()
        try:
            self.refresh_index_panel_ui()
        except Exception:
            pass
        try:
            self.refresh_profiles_ui()
        except Exception:
            pass
        # New cards/panels need the page-scroll wheel binding again
        try:
            self.root.after(30, self._models_bind_wheel)
        except Exception:
            pass

    def _attach_model_menu(self, card, m: dict, full_ix: int) -> None:
        """Right-click on a voice card: use / rename / open folder / delete."""

        def _popup(e):
            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(
                label="使用这个音色",
                command=lambda: self._use_model_from_grid(full_ix),
            )
            if m.get("source") == "user_data" and m.get("dir"):
                menu.add_command(
                    label="重命名…", command=lambda: self._ui_rename_model(m)
                )
                menu.add_command(
                    label="打开所在文件夹",
                    command=lambda: open_path(Path(m["dir"])),
                )
                menu.add_separator()
                menu.add_command(
                    label="删除这个音色…", command=lambda: self._ui_delete_model(m)
                )
            else:
                menu.add_command(
                    label="打开所在文件夹",
                    command=lambda: open_path(Path(m["path"]).parent),
                )
            try:
                menu.tk_popup(e.x_root, e.y_root)
            finally:
                menu.grab_release()
            return "break"

        def _bind_tree(w):
            w.bind("<Button-3>", _popup, add="+")
            for ch in w.winfo_children():
                _bind_tree(ch)

        try:
            _bind_tree(card)
        except Exception:
            pass

    def _ui_rename_model(self, m: dict) -> None:
        from tkinter import simpledialog

        from launcher.catalog import rename_model_display

        new = simpledialog.askstring(
            "重命名", "这个音色显示为：", initialvalue=str(m.get("name") or "")
        )
        if not new or not new.strip():
            return
        try:
            rename_model_display(Path(m["dir"]), new)
        except Exception as e:
            messagebox.showerror("重命名失败", str(e))
            return
        self.refresh_models()

    def _ui_delete_model(self, m: dict) -> None:
        from launcher.catalog import delete_model_dir

        if self._is_active_model(m) and (self.vc_running or self._vc_starting):
            messagebox.showinfo(
                "正在使用", "这个音色正在变声中，先停止变声再删除。"
            )
            return
        if not messagebox.askyesno(
            "删除音色",
            f"确定删除「{m.get('name')}」？\n"
            "模型文件、绑定的配置档案会一起删除，无法撤销。",
        ):
            return
        try:
            delete_model_dir(Path(m["dir"]), MODELS_DIR)
        except Exception as e:
            messagebox.showerror("删除失败", str(e))
            return
        was_current = self._is_active_model(m)
        if was_current:
            self.model_idx = 0
            for k in ("last_model", "last_model_name", "last_model_path"):
                self.cfg.pop(k, None)
        self.refresh_models()
        if hasattr(self, "models_status_lbl"):
            self.models_status_lbl.configure(text=f"已删除：{m.get('name')}")

    def _use_model_from_grid(self, ix: int) -> None:
        self._select_model(ix, feedback=True, maybe_restart=True)
        # Light toast via status label; avoid modal spam
        if hasattr(self, "models_status_lbl") and self.models:
            self.models_status_lbl.configure(
                text=f"已切换为：{self.models[ix]['name']}",
                fg=TM_OK,
            )
            self.root.after(
                2000,
                lambda: self.models_status_lbl.configure(
                    text=f"共 {len(self.models)} 个 · 使用中：{self.models[self.model_idx]['name']}",
                    fg=TM_META,
                )
                if self.models
                else None,
            )

    def import_model(self) -> None:
        paths = filedialog.askopenfilenames(
            title="选择 RVC 模型 (.pth)",
            filetypes=[("RVC 模型", "*.pth"), ("全部", "*.*")],
        )
        if not paths:
            return
        # 规范文件管理：按钮直接写清动作，不用「是/否」猜
        choice = ask_choice(
            self.root,
            "导入方式",
            "把模型文件放进软件目录，用哪种方式？\n"
            "复制：原文件保留在原位置。\n"
            "移动：原位置不再保留，统一由软件管理。",
            [("copy", "复制进来"), ("move", "移动进来")],
        )
        if choice is None:
            return
        move = choice == "move"
        n = 0
        for p in paths:
            try:
                import_model_to_catalog(Path(p), MODELS_DIR, move=move)
                n += 1
            except Exception as e:
                messagebox.showerror("导入失败", f"{p}\n{e}")
        self.refresh_models()
        if n:
            verb = "移入" if move else "复制到"
            messagebox.showinfo(
                "导入完成", f"已{verb} {n} 个模型：\n{MODELS_DIR}"
            )
