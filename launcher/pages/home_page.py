# -*- coding: utf-8 -*-
"""Home page: stage band + cover-focus carousel.

Split out of main_app. Uses MainApp state (self.body, self.models,
self.model_idx, self._cover_cache, self._shift_model, self._select_model, …)
present on the composed instance.
"""

from __future__ import annotations

import tkinter as tk

from launcher.theme import (
    GUTTER,
    TM_ACCENT,
    TM_BG,
    TM_HAIRLINE,
    TM_INK,
    TM_INK_MUTED,
    TM_META,
    TM_OK,
    TM_STAGE,
    TM_SURFACE,
    mono_font,
    sans_font,
    title_font,
)
from launcher.ui import ModelCoverCard, SectionCard


class HomePageMixin:
    def _page_home(self) -> tk.Frame:
        fr = tk.Frame(self.body, bg=TM_BG)
        fr.columnconfigure(0, weight=1)
        fr.rowconfigure(1, weight=1)

        # Full-width stage band (LyricsKara “band” hierarchy)
        stage = tk.Frame(fr, bg=TM_STAGE)
        stage.grid(row=0, column=0, sticky="ew")
        stage_inner = tk.Frame(stage, bg=TM_STAGE)
        stage_inner.pack(fill="x", padx=GUTTER, pady=(22, 18))
        stage_inner.columnconfigure(0, weight=1)

        tk.Label(
            stage_inner,
            text="选择音色，开始变声",
            font=title_font(24, "bold"),
            bg=TM_STAGE,
            fg=TM_INK,
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(10, 6))

        self.home_current_lbl = tk.Label(
            stage_inner,
            text="当前音色：—",
            font=title_font(15, "bold"),
            bg=TM_STAGE,
            fg=TM_ACCENT,
            anchor="w",
        )
        self.home_current_lbl.grid(row=2, column=0, sticky="w", pady=(4, 2))
        self.home_hint_lbl = tk.Label(
            stage_inner,
            text="点卡片切换音色 · F5 启停变声 · F1 快捷键",
            font=sans_font(10),
            bg=TM_STAGE,
            fg=TM_INK_MUTED,
            anchor="w",
        )
        self.home_hint_lbl.grid(row=3, column=0, sticky="w", pady=(2, 0))
        tk.Frame(fr, bg=TM_HAIRLINE, height=1).grid(row=0, column=0, sticky="sew")

        # Recent voices (最近使用的三个) — click to switch
        mid = tk.Frame(fr, bg=TM_BG)
        mid.grid(row=1, column=0, sticky="nsew", padx=GUTTER, pady=(8, 0))
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(1, weight=1)
        tk.Label(
            mid,
            text="最近使用",
            font=sans_font(10, "bold"),
            bg=TM_BG,
            fg=TM_META,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(4, 0))
        self.carousel_host = tk.Frame(mid, bg=TM_BG)
        self.carousel_host.grid(row=1, column=0, sticky="nsew")
        self.carousel_host.bind("<Configure>", lambda e: self._schedule_carousel_reflow())

        self.home_toast = tk.Label(
            fr,
            text="",
            font=mono_font(9),
            bg=TM_BG,
            fg=TM_OK,
        )
        self.home_toast.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        return fr

    def _recent_models(self, limit: int = 3) -> list[int]:
        """Indices (into self.models) of the most-recently-used voices, current
        first. Falls back to catalog order when there's no history yet."""
        if not self.models:
            return []
        order: list[int] = []
        seen: set[int] = set()

        def _push(i: int) -> None:
            if 0 <= i < len(self.models) and i not in seen:
                seen.add(i)
                order.append(i)

        _push(self.model_idx)  # current always shown first
        keys = self.cfg.get("recent_models") or []
        by_key = {}
        for i, m in enumerate(self.models):
            by_key[m.get("path") or ""] = i
            by_key[(m.get("dir") or "") + "|" + (m.get("name") or "")] = i
        for k in keys:
            j = by_key.get(k)
            if j is not None:
                _push(j)
        for i in range(len(self.models)):  # pad with catalog order
            _push(i)
        return order[:limit]

    def _schedule_carousel_reflow(self) -> None:
        if getattr(self, "_carousel_job", None):
            try:
                self.root.after_cancel(self._carousel_job)
            except Exception:
                pass
        self._carousel_job = self.root.after(80, self._render_carousel)

    def _render_carousel(self) -> None:
        if not hasattr(self, "carousel_host"):
            return
        for w in self.carousel_host.winfo_children():
            w.destroy()
        self._update_home_current_label()

        if not self.models:
            box = SectionCard(self.carousel_host, accent_rail=False, pad=20)
            box.pack(expand=True, fill="both", padx=40, pady=20)
            tk.Label(
                box.body,
                text="暂无音色\n\n请到「模型」页导入 .pth / .zip",
                font=sans_font(11),
                bg=TM_SURFACE,
                fg=TM_INK_MUTED,
                justify="center",
            ).pack(expand=True, pady=40)
            return

        self.carousel_host.update_idletasks()
        host_w = max(self.carousel_host.winfo_width(), 400)
        host_h = max(self.carousel_host.winfo_height(), 240)
        # First card (current) dominates; the other recents are smaller
        focus_w = max(200, min(320, int(host_w * 0.34)))
        focus_h = max(240, min(360, int(host_h * 0.88)))
        side_w = max(130, int(focus_w * 0.62))
        side_h = max(180, int(focus_h * 0.72))

        idxs = self._recent_models(limit=3)
        row = tk.Frame(self.carousel_host, bg=TM_BG)
        row.place(relx=0.5, rely=0.5, anchor="center")

        for i, mi in enumerate(idxs):
            m = self.models[mi]
            focus = i == 0  # current is first + largest
            w, h = (focus_w, focus_h) if focus else (side_w, side_h)
            photo = self._cover_cache.get(
                m.get("cover"),
                max_w=max(w - 4, 100),
                max_h=max(int(h * 0.58), 80),
            )
            if m.get("missing"):
                corner = "⚠ 缺失"
            elif m.get("index"):
                corner = "✓ 检索库"
            else:
                corner = ""
            card = ModelCoverCard(
                row,
                name=m["name"],
                tag=m.get("tag") or "音色",
                author=str(m.get("author") or ""),
                photo=photo,
                active=focus,
                focus=focus,
                index_text=corner,
                width=w,
                height=h,
                on_click=lambda ix=mi: self._select_model(
                    ix, feedback=True, maybe_restart=True
                ),
            )
            card.pack(side="left", padx=max(10, int(host_w * 0.016)), pady=12)

    def _update_home_current_label(self) -> None:
        if not hasattr(self, "home_current_lbl"):
            return
        if not self.models:
            self.home_current_lbl.configure(text="尚未选择音色")
            self.home_hint_lbl.configure(text="请先到「模型」页导入音色")
            return
        m = self.models[self.model_idx]
        self.home_current_lbl.configure(text=m["name"])
        bits = [str(m.get("tag") or "音色")]
        if m.get("author"):
            bits.append(str(m.get("author")))
        if m.get("date"):
            bits.append(str(m.get("date")))
        bits.append("切换立即生效 · 运行中会自动重载")
        self.home_hint_lbl.configure(text="  ·  ".join(bits))

    def _show_switch_toast(self, name: str) -> None:
        if not hasattr(self, "home_toast"):
            return
        self.home_toast.configure(text=f"已切换为「{name}」", fg=TM_OK)
        if self._toast_job is not None:
            try:
                self.root.after_cancel(self._toast_job)
            except Exception:
                pass
        self._toast_job = self.root.after(
            2200, lambda: self.home_toast.configure(text="")
        )
