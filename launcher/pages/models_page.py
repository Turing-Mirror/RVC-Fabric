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
    TM_INK_MUTED,
    TM_META,
    TM_OK,
    mono_font,
    sans_font,
)
from launcher.ui import (
    GhostButton,
    ModelCoverCard,
    PageHeader,
    PrimaryButton,
    SearchField,
    SegmentControl,
)
from launcher.win_util import open_path


class ModelsPageMixin:
    def _page_models(self) -> tk.Frame:
        fr = tk.Frame(self.body, bg=TM_BG)
        fr.columnconfigure(0, weight=1)

        bar = tk.Frame(fr, bg=TM_BG)
        bar.grid(row=0, column=0, sticky="ew", padx=GUTTER, pady=(18, 8))
        left = tk.Frame(bar, bg=TM_BG)
        left.pack(side="left", fill="x", expand=True)
        PageHeader(
            left,
            eyebrow="",
            title="音色目录",
            lead="",
        ).pack(anchor="w")
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
        PrimaryButton(actions, "导入模型", command=self.import_model, padx=14, pady=6).pack(
            side="right", padx=4
        )

        # Filter row: search (left) + sort segment (right) — library chrome
        filt = tk.Frame(fr, bg=TM_BG)
        filt.grid(row=1, column=0, sticky="ew", padx=GUTTER, pady=(0, 6))
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

        fr.rowconfigure(2, weight=1)
        list_wrap = tk.Frame(fr, bg=TM_BG)
        list_wrap.grid(row=2, column=0, sticky="nsew", padx=GUTTER - 8, pady=(4, 12))
        list_wrap.columnconfigure(0, weight=1)
        list_wrap.rowconfigure(0, weight=1)

        canvas = tk.Canvas(list_wrap, bg=TM_BG, highlightthickness=0)
        scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=canvas.yview)
        self.model_grid = tk.Frame(canvas, bg=TM_BG)
        self._models_canvas = canvas
        self._models_canvas_win = canvas.create_window((0, 0), window=self.model_grid, anchor="nw")

        def _on_grid_cfg(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_cfg(e):
            canvas.itemconfigure(self._models_canvas_win, width=e.width)
            self._schedule_models_reflow()

        self.model_grid.bind("<Configure>", _on_grid_cfg)
        canvas.bind("<Configure>", _on_canvas_cfg)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        # Per-model config profiles (bind / switch / cancel) — outside the grid
        # so grid rebuilds don't destroy it
        panel = tk.Frame(fr, bg=TM_BG)
        panel.grid(row=3, column=0, sticky="ew", padx=GUTTER, pady=(0, 12))
        try:
            self._build_profiles_panel(panel)
        except Exception:
            pass
        return fr

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
                text="还没有模型。点右上角「导入模型」添加音色，或到「更新」页下载。",
                bg=TM_BG,
                fg=TM_INK_MUTED,
                font=sans_font(11),
            ).grid(row=0, column=0, padx=20, pady=40, sticky="w")
            self._sync_bottom()
            return

        if not view:
            tk.Label(
                self.model_grid,
                text=f"没有匹配「{query}」的音色。清空搜索可看全部。",
                bg=TM_BG,
                fg=TM_INK_MUTED,
                font=sans_font(11),
            ).grid(row=0, column=0, padx=20, pady=40, sticky="w")
            self._sync_bottom()
            return

        # Columns adapt to width — cover-first cards need more width
        self._models_canvas.update_idletasks()
        cw = max(self._models_canvas.winfo_width(), 320)
        card_min = 180
        cols = max(1, min(5, cw // (card_min + 20)))
        for c in range(cols):
            self.model_grid.columnconfigure(c, weight=1, uniform="m")

        for pos, m in enumerate(view):
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

        self._sync_bottom()
        try:
            self.refresh_profiles_ui()
        except Exception:
            pass

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
        n = 0
        for p in paths:
            try:
                import_model_to_catalog(Path(p), MODELS_DIR)
                n += 1
            except Exception as e:
                messagebox.showerror("导入失败", f"{p}\n{e}")
        self.refresh_models()
        if n:
            messagebox.showinfo("导入完成", f"已写入 {n} 个模型到\n{MODELS_DIR}")
