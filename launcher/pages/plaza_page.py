# -*- coding: utf-8 -*-
"""广场 page + models-page ad banner + 更新日志子页 (UI mixin).

Split out of main_app. Pure consumer of launcher.online.plaza / changelog
(parse / filter / cache / user actions live there); this module only renders.
Uses MainApp state (self.body, self.root, self.cfg, …) on the composed instance.

Shell-import safe: stdlib + tkinter + launcher pure modules only — no numpy /
torch anywhere in the import chain (the frozen shell has neither).
"""

from __future__ import annotations

import threading

import tkinter as tk
from tkinter import ttk

from launcher.config_store import save_config
from launcher.online import changelog as cl_mod
from launcher.online import plaza
from launcher.theme import (
    GUTTER,
    TM_BG,
    TM_HAIRLINE,
    TM_INK,
    TM_INK_MUTED,
    TM_INSET,
    TM_META,
    TM_SURFACE,
    meta_font,
    px,
    sans_font,
    title_font,
)
from launcher.ui import GhostButton
from launcher.version import APP_VERSION, display_version


def _fmt_plaza_date(d: str) -> str:
    """YYMMDD → human date; anything unexpected passes through unchanged."""
    s = (d or "").strip()
    if len(s) == 6 and s.isdigit():
        return f"20{s[0:2]}-{s[2:4]}-{s[4:6]}"
    return s


class PlazaPageMixin:
    # ------------------------------------------------------------ page build

    def _page_plaza(self) -> tk.Frame:
        """Whole-page Canvas scroll (same pattern as the models page)."""
        # Startup timers may call _silent_fetch_plaza before this builder runs;
        # never clobber state those early calls already produced.
        if not hasattr(self, "_plaza_items"):
            self._plaza_items = plaza.load_cached_feed()
        if not hasattr(self, "_changelog_entries"):
            self._changelog_entries = cl_mod.load_cached_changelog()
        self._plaza_render_snap = None
        self._plaza_subview = "main"  # main | changelog
        if not hasattr(self, "_plaza_job"):
            self._plaza_job = None
        if not hasattr(self, "_plaza_fetching"):
            self._plaza_fetching = False
        if not hasattr(self, "_plaza_fetched_once"):
            self._plaza_fetched_once = False
        if not hasattr(self, "_plaza_img_inflight"):
            self._plaza_img_inflight = set()
        if not hasattr(self, "_plaza_feed_source"):
            self._plaza_feed_source = ""
        if not hasattr(self, "_changelog_feed_source"):
            self._changelog_feed_source = ""

        fr = tk.Frame(self.body, bg=TM_BG)
        canvas = tk.Canvas(fr, bg=TM_BG, highlightthickness=0)
        sb = ttk.Scrollbar(fr, orient="vertical", command=canvas.yview)
        wrap = tk.Frame(canvas, bg=TM_BG)
        win_id = canvas.create_window((0, 0), window=wrap, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._plaza_canvas = canvas
        self._plaza_wrap = wrap

        def _sync(_e=None):
            if getattr(self, "_layout_is_frozen", None) and self._layout_is_frozen():
                return
            if getattr(self, "schedule_scrollregion", None):
                self.schedule_scrollregion(canvas)

        def _width(e):
            if getattr(self, "_layout_is_frozen", None) and self._layout_is_frozen():
                return
            if e.width <= 1:
                return
            try:
                canvas.itemconfigure(win_id, width=int(e.width))
            except Exception:
                return
            snap = getattr(self, "_plaza_render_snap", None)
            if snap is None or int(e.width) != snap[0]:
                if getattr(self, "_plaza_job", None):
                    try:
                        self.root.after_cancel(self._plaza_job)
                    except Exception:
                        pass
                self._plaza_job = self.root.after(120, self._plaza_reflow_tick)

        wrap.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _width)

        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        def _bind_wheel_tree(w):
            w.bind("<MouseWheel>", _wheel)
            for ch in w.winfo_children():
                _bind_wheel_tree(ch)

        canvas.bind("<MouseWheel>", _wheel)
        self._plaza_bind_wheel = lambda: _bind_wheel_tree(wrap)

        # --- Header: back (changelog subview) + title + refresh ---
        bar = tk.Frame(wrap, bg=TM_BG)
        bar.pack(fill="x", padx=GUTTER, pady=(18, 8))
        self._plaza_header_bar = bar
        left = tk.Frame(bar, bg=TM_BG)
        left.pack(side="left", fill="x", expand=True)
        title_row = tk.Frame(left, bg=TM_BG)
        title_row.pack(anchor="w", fill="x")
        self._plaza_back_host = tk.Frame(title_row, bg=TM_BG)
        # back host packed only in changelog subview
        self._plaza_title_lbl = tk.Label(
            title_row,
            text="广场",
            font=title_font(22, "bold"),
            bg=TM_BG,
            fg=TM_INK,
        )
        self._plaza_title_lbl.pack(side="left", anchor="w")
        self._plaza_status_lbl = tk.Label(
            left,
            text="",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_META,
        )
        self._plaza_status_lbl.pack(anchor="w", pady=(6, 0))
        actions = tk.Frame(bar, bg=TM_BG)
        actions.pack(side="right", anchor="n", pady=(8, 0))
        self._plaza_refresh_btn = GhostButton(
            actions, "刷新", command=self._silent_fetch_plaza, padx=12, pady=6
        )
        self._plaza_refresh_btn.pack(side="right")

        # Main feed host (changelog teaser + plaza cards)
        self._plaza_list_host = tk.Frame(wrap, bg=TM_BG)
        self._plaza_list_host.pack(fill="x", padx=GUTTER, pady=(4, 16))
        # Full changelog host (hidden until subview)
        self._plaza_changelog_host = tk.Frame(wrap, bg=TM_BG)
        return fr

    # -------------------------------------------------------------- helpers

    def _plaza_visible(self) -> list:
        """Plaza-placement items; hide auto release-* when changelog is present."""
        items = plaza.visible_items(
            getattr(self, "_plaza_items", None) or [],
            plaza.PLACEMENT_PLAZA,
            dismissed=plaza.dismissed_ids(self.cfg),
        )
        if getattr(self, "_changelog_entries", None):
            items = [
                it
                for it in items
                if not str(it.id or "").startswith("release-")
            ]
        return items

    def _plaza_snap_now(self):
        """Render snapshot: (width, feed stamp, dismissed, cl stamp, subview)."""
        canvas = getattr(self, "_plaza_canvas", None)
        if canvas is None:
            return None
        try:
            w = int(canvas.winfo_width())
        except Exception:
            w = 0
        dismissed = plaza.dismissed_ids(self.cfg)
        cl = getattr(self, "_changelog_entries", None) or []
        return (
            w,
            plaza.feed_stamp(self._plaza_visible()),
            tuple(sorted(dismissed)),
            cl_mod.feed_stamp(cl),
            getattr(self, "_plaza_subview", "main"),
        )

    def _plaza_update_status(self) -> None:
        lbl = getattr(self, "_plaza_status_lbl", None)
        if lbl is None:
            return
        try:
            if not lbl.winfo_exists():
                return
            if getattr(self, "_plaza_fetching", False):
                lbl.configure(text="正在刷新…")
                return
            if getattr(self, "_plaza_subview", "main") == "changelog":
                n = len(getattr(self, "_changelog_entries", None) or [])
                src = getattr(self, "_changelog_feed_source", "") or getattr(
                    self, "_plaza_feed_source", ""
                )
                name = {
                    "remote": "在线",
                    "cache": "缓存",
                    "none": "离线",
                }.get(src, "本地")
                cur = display_version(APP_VERSION)
                lbl.configure(text=f"{name} · {n} 个版本 · 当前已装 {cur}")
                return
            src = getattr(self, "_plaza_feed_source", "")
            name = {
                "remote": "在线内容",
                "cache": "离线缓存",
                "none": "网络不可用",
            }.get(src, "本地缓存")
            lbl.configure(text=f"{name} · 共 {len(self._plaza_visible())} 条")
        except Exception:
            pass

    def _plaza_set_subview(self, view: str) -> None:
        """Switch plaza main feed vs full changelog (same page stack)."""
        view = "changelog" if view == "changelog" else "main"
        prev = getattr(self, "_plaza_subview", "main")
        self._plaza_subview = view
        if prev != view:
            self._plaza_render_snap = None
        if view == "changelog":
            self._render_plaza_changelog()
        else:
            self._render_plaza()
        try:
            canvas = getattr(self, "_plaza_canvas", None)
            if canvas is not None:
                canvas.yview_moveto(0)
        except Exception:
            pass

    def _plaza_apply_subview_chrome(self) -> None:
        """Title / back button / which body host is packed."""
        view = getattr(self, "_plaza_subview", "main")
        title = getattr(self, "_plaza_title_lbl", None)
        back_host = getattr(self, "_plaza_back_host", None)
        main_host = getattr(self, "_plaza_list_host", None)
        cl_host = getattr(self, "_plaza_changelog_host", None)
        try:
            if title is not None:
                title.configure(text="更新日志" if view == "changelog" else "广场")
            if back_host is not None:
                for w in back_host.winfo_children():
                    w.destroy()
                if view == "changelog":
                    back_host.pack(side="left", before=title, padx=(0, 8))
                    GhostButton(
                        back_host,
                        "返回",
                        command=lambda: self._plaza_set_subview("main"),
                        padx=10,
                        pady=4,
                    ).pack(side="left")
                else:
                    back_host.pack_forget()
            if view == "changelog":
                if main_host is not None:
                    main_host.pack_forget()
                if cl_host is not None:
                    cl_host.pack(fill="x", padx=GUTTER, pady=(4, 16))
            else:
                if cl_host is not None:
                    cl_host.pack_forget()
                if main_host is not None:
                    main_host.pack(fill="x", padx=GUTTER, pady=(4, 16))
        except Exception:
            pass
        self._plaza_update_status()

    def _plaza_bind_card_click(self, widget, item, skip=()) -> None:
        """Whole-card click-through — buttons and the close × stay excluded."""
        skip_set = set(skip)

        def _cb(_e, it=item):
            plaza.on_card_clicked(it)
            return "break"

        def rec(w):
            if w in skip_set or isinstance(w, tk.Button):
                return
            try:
                w.bind("<Button-1>", _cb)
            except Exception:
                pass
            for ch in w.winfo_children():
                rec(ch)

        rec(widget)

    def _plaza_dismiss(self, item_id: str) -> None:
        """Permanent per-id close; refresh every surface that shows the feed."""
        if plaza.dismiss(self.cfg, item_id):
            try:
                save_config(self.cfg)
            except Exception:
                pass
        try:
            self._invalidate_catalog_views()
        except Exception:
            pass
        self._render_plaza()
        self._render_models_ad()
        self._apply_plaza_nav_badge()

    # ------------------------------------------------------------ page render

    def _render_plaza(self) -> None:
        """Full re-render of main plaza feed (changelog teaser + cards)."""
        if getattr(self, "_plaza_subview", "main") == "changelog":
            self._render_plaza_changelog()
            return
        self._plaza_apply_subview_chrome()
        host = getattr(self, "_plaza_list_host", None)
        canvas = getattr(self, "_plaza_canvas", None)
        if host is None or canvas is None:
            return
        for w in host.winfo_children():
            w.destroy()

        dismissed = plaza.dismissed_ids(self.cfg)
        items = self._plaza_visible()
        self._plaza_update_status()

        cw = max(int(canvas.winfo_width()) - 2 * GUTTER, 320)

        # --- 更新日志区块：仅最新一条 + 进入全文 ---
        self._plaza_build_changelog_teaser(host, cw)

        if not items:
            tk.Label(
                host,
                text="暂无其它内容，点右上角刷新试试",
                font=sans_font(11),
                bg=TM_BG,
                fg=TM_INK_MUTED,
            ).pack(pady=px(40))
        for it in items:
            self._plaza_build_card(host, it, cw)

        self._plaza_render_snap = self._plaza_snap_now()
        try:
            self.root.after(30, self._plaza_bind_wheel)
        except Exception:
            pass

    def _plaza_build_changelog_teaser(self, host: tk.Frame, cw: int) -> None:
        """Pinned section: latest shell notes + open full changelog."""
        entries = getattr(self, "_changelog_entries", None) or []
        latest = cl_mod.latest_entry(entries)
        section = tk.Frame(host, bg=TM_BG)
        section.pack(fill="x", pady=(0, 14))
        head = tk.Frame(section, bg=TM_BG)
        head.pack(fill="x", pady=(0, 8))
        tk.Label(
            head,
            text="更新日志",
            font=title_font(13, "bold"),
            bg=TM_BG,
            fg=TM_INK,
        ).pack(side="left")
        GhostButton(
            head,
            "查看全部",
            command=lambda: self._plaza_set_subview("changelog"),
            padx=10,
            pady=4,
        ).pack(side="right")

        card = tk.Frame(
            section,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        card.pack(fill="x")
        wrap_w = max(cw - px(28), px(200))
        if latest is None:
            tk.Label(
                card,
                text="暂无版本记录，刷新后重试（或等待运营发布 changelog）",
                font=sans_font(10),
                bg=TM_SURFACE,
                fg=TM_INK_MUTED,
                wraplength=wrap_w,
                justify="left",
                anchor="w",
            ).pack(fill="x", padx=14, pady=14)
            return
        top = tk.Frame(card, bg=TM_SURFACE)
        top.pack(fill="x", padx=14, pady=(12, 0))
        tk.Label(
            top,
            text=latest.display_title,
            font=title_font(12, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        ).pack(side="left")
        if latest.date:
            tk.Label(
                top,
                text=_fmt_plaza_date(latest.date),
                font=meta_font(_fmt_plaza_date(latest.date), 8),
                bg=TM_SURFACE,
                fg=TM_META,
            ).pack(side="right")
        summary = latest.summary
        if summary:
            tk.Label(
                card,
                text=summary,
                font=sans_font(10),
                bg=TM_SURFACE,
                fg=TM_INK_MUTED,
                anchor="w",
                justify="left",
                wraplength=wrap_w,
            ).pack(fill="x", padx=14, pady=(6, 4))
        foot = tk.Frame(card, bg=TM_SURFACE)
        foot.pack(fill="x", padx=14, pady=(0, 12))
        GhostButton(
            foot,
            "查看全部更新日志",
            command=lambda: self._plaza_set_subview("changelog"),
            padx=12,
            pady=5,
        ).pack(side="right")

    def _render_plaza_changelog(self) -> None:
        """Full-page changelog list inside the plaza stack (with back chrome)."""
        self._plaza_apply_subview_chrome()
        host = getattr(self, "_plaza_changelog_host", None)
        canvas = getattr(self, "_plaza_canvas", None)
        if host is None or canvas is None:
            return
        for w in host.winfo_children():
            w.destroy()
        self._plaza_update_status()
        entries = list(getattr(self, "_changelog_entries", None) or [])
        cw = max(int(canvas.winfo_width()) - 2 * GUTTER, 320)
        wrap_w = max(cw - px(28), px(200))
        if not entries:
            tk.Label(
                host,
                text="暂无更新日志，点右上角刷新试试",
                font=sans_font(11),
                bg=TM_BG,
                fg=TM_INK_MUTED,
            ).pack(pady=px(60))
        for ent in entries:
            self._plaza_build_changelog_entry_card(host, ent, wrap_w)
        self._plaza_render_snap = self._plaza_snap_now()
        try:
            self.root.after(30, self._plaza_bind_wheel)
        except Exception:
            pass

    def _plaza_build_changelog_entry_card(
        self, host: tk.Frame, ent, wrap_w: int
    ) -> None:
        card = tk.Frame(
            host,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        card.pack(fill="x", pady=(0, 12))
        head = tk.Frame(card, bg=TM_SURFACE)
        head.pack(fill="x", padx=14, pady=(12, 0))
        tk.Label(
            head,
            text=ent.display_title,
            font=title_font(12, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        ).pack(side="left")
        meta_bits = []
        if ent.date:
            meta_bits.append(_fmt_plaza_date(ent.date))
        meta_bits.append(ent.version)
        tk.Label(
            head,
            text=" · ".join(meta_bits),
            font=meta_font(" · ".join(meta_bits), 8),
            bg=TM_SURFACE,
            fg=TM_META,
        ).pack(side="right")
        detail = ent.detail_text
        if detail:
            tk.Label(
                card,
                text=detail,
                font=sans_font(10),
                bg=TM_SURFACE,
                fg=TM_INK_MUTED,
                anchor="w",
                justify="left",
                wraplength=wrap_w,
            ).pack(fill="x", padx=14, pady=(8, 14))
        else:
            tk.Frame(card, bg=TM_SURFACE, height=12).pack()

    def _plaza_build_card(self, host: tk.Frame, it, cw: int) -> None:
        big = bool(it.image_url) and (it.pinned or it.type == "banner")
        card = tk.Frame(
            host,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        card.pack(fill="x", pady=(0, 12))

        wrap_w = max(cw - px(28), px(200))
        if big:
            # Hero image on top — fixed-height box so async load never jumps
            img_box = tk.Frame(card, bg=TM_INSET, height=px(180))
            img_box.pack(fill="x", padx=14, pady=(14, 0))
            img_box.pack_propagate(False)
            img_lbl = tk.Label(img_box, bg=TM_INSET)
            img_lbl.place(relx=0.5, rely=0.5, anchor="center")
            # Quantize the width to a 16px bucket (home carousel precedent):
            # CoverCache keys on (path, w, h) and never evicts, so a raw
            # drag-resize width would grow the cache without bound
            hero_w = max(cw - px(28), px(200))
            hero_w = max(16, (hero_w // 16) * 16)
            self._plaza_load_image(img_lbl, it.image_url, hero_w, px(180))

        head = tk.Frame(card, bg=TM_SURFACE)
        head.pack(fill="x", padx=14, pady=(8 if big else 12, 0))
        badge_reserve = px(70) if (it.is_ad or it.dismissible) else 0
        tk.Label(
            head,
            text=it.title,
            font=title_font(12, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
            justify="left",
            wraplength=max(wrap_w - badge_reserve, px(160)),
        ).pack(anchor="w")

        content = tk.Frame(card, bg=TM_SURFACE)
        content.pack(fill="x", padx=14, pady=(6, 4 if it.url else 12))
        if it.image_url and not big:
            # Small thumbnail on the left
            box = tk.Frame(content, bg=TM_INSET, width=px(96), height=px(72))
            box.pack(side="left", padx=(0, 12), anchor="n")
            box.pack_propagate(False)
            lbl = tk.Label(box, bg=TM_INSET)
            lbl.place(relx=0.5, rely=0.5, anchor="center")
            self._plaza_load_image(lbl, it.image_url, px(96), px(72))
            wrap_w = max(wrap_w - px(96) - px(12), px(200))

        txt = tk.Frame(content, bg=TM_SURFACE)
        txt.pack(side="left", fill="x", expand=True)
        if it.body:
            tk.Label(
                txt,
                text=it.body,
                font=sans_font(10),
                bg=TM_SURFACE,
                fg=TM_INK_MUTED,
                anchor="w",
                justify="left",
                wraplength=wrap_w,
            ).pack(anchor="w")
        meta_parts = []
        if it.date:
            meta_parts.append(_fmt_plaza_date(it.date))
        if it.is_ad and it.sponsor:
            meta_parts.append(f"赞助 · {it.sponsor}")
        if meta_parts:
            meta = " · ".join(meta_parts)
            tk.Label(
                txt,
                text=meta,
                font=meta_font(meta, 8),
                bg=TM_SURFACE,
                fg=TM_META,
                anchor="w",
            ).pack(anchor="w", pady=(4, 0))

        if it.url:
            foot = tk.Frame(card, bg=TM_SURFACE)
            foot.pack(fill="x", padx=14, pady=(0, 12))
            GhostButton(
                foot,
                it.action_label or "查看详情",
                command=lambda item=it: plaza.on_card_clicked(item),
                padx=12,
                pady=5,
            ).pack(side="right")

        # Top-right chrome floats above everything built so far (incl. hero)
        skip = []
        right_x = px(8)
        if it.dismissible:
            close = tk.Label(
                card,
                text="×",
                font=sans_font(11),
                bg=TM_SURFACE,
                fg=TM_META,
                cursor="hand2",
                padx=4,
            )
            close.place(relx=1.0, x=-right_x, y=px(6), anchor="ne")
            close.bind(
                "<Button-1>",
                lambda _e, i=it.id: (self._plaza_dismiss(i), "break")[-1],
            )
            skip.append(close)
            right_x += px(26)
        if it.is_ad:
            ad_badge = tk.Label(
                card,
                text="广告",
                font=sans_font(8),
                bg=TM_INSET,
                fg=TM_META,
                padx=6,
                pady=1,
            )
            ad_badge.place(relx=1.0, x=-right_x, y=px(8), anchor="ne")

        if it.url:
            card.configure(cursor="hand2")
            self._plaza_bind_card_click(card, it, skip=skip)

    # ------------------------------------------------------------ page hooks

    def _show_plaza_page(self) -> None:
        """show_page hook (runs before tkraise): render only when stale."""
        if getattr(self, "_plaza_job", None):
            try:
                self.root.after_cancel(self._plaza_job)
            except Exception:
                pass
            self._plaza_job = None
        # Leaving other nav tabs returns to main plaza feed (not stuck in changelog)
        if getattr(self, "_plaza_subview", "main") != "main":
            self._plaza_subview = "main"
            self._plaza_render_snap = None
        if not getattr(self, "_plaza_fetched_once", False):
            self._silent_fetch_plaza()
        snap_now = self._plaza_snap_now()
        if snap_now is None or snap_now != getattr(self, "_plaza_render_snap", None):
            self._render_plaza()
        else:
            self._plaza_update_status()
        try:
            if plaza.mark_seen(self.cfg, [it.id for it in self._plaza_visible()]):
                save_config(self.cfg)
        except Exception:
            pass
        self._apply_plaza_nav_badge()

    def _plaza_reflow_tick(self) -> None:
        self._plaza_job = None
        # Hidden pages still receive Configure under grid stacking — the
        # show_page snapshot catches up on the next visit instead
        if getattr(self, "_current_page", "") != "plaza":
            return
        canvas = getattr(self, "_plaza_canvas", None)
        if canvas is None:
            return
        snap = getattr(self, "_plaza_render_snap", None)
        try:
            w = int(canvas.winfo_width())
        except Exception:
            return
        if snap is None or w != snap[0]:
            self._render_plaza()

    # ---------------------------------------------------------------- fetch

    def _silent_fetch_plaza(self) -> None:
        """Background plaza + changelog fetch; never raises / never blocks UI.

        May run from a startup timer before _page_plaza built anything —
        every attribute access goes through getattr with a default.
        """
        if getattr(self, "_plaza_fetching", False):
            return
        self._plaza_fetching = True
        self._plaza_update_status()

        def work():
            try:
                items, source = plaza.fetch_feed()
            except Exception:
                items, source = [], "none"
            try:
                cl_entries, cl_source = cl_mod.fetch_changelog()
            except Exception:
                cl_entries, cl_source = [], "none"

            def done(
                items=items,
                source=source,
                cl_entries=cl_entries,
                cl_source=cl_source,
            ):
                self._plaza_fetching = False
                self._plaza_fetched_once = True
                self._plaza_items = items
                self._plaza_feed_source = source
                self._changelog_entries = cl_entries
                self._changelog_feed_source = cl_source
                self._apply_plaza_nav_badge()
                self._render_models_ad()
                if getattr(self, "_current_page", "") == "plaza":
                    snap_now = self._plaza_snap_now()
                    if snap_now is None or snap_now != getattr(
                        self, "_plaza_render_snap", None
                    ):
                        self._render_plaza()
                    else:
                        self._plaza_update_status()
                    try:
                        ids = [it.id for it in self._plaza_visible()]
                        if plaza.mark_seen(self.cfg, ids):
                            save_config(self.cfg)
                    except Exception:
                        pass
                    self._apply_plaza_nav_badge()
                else:
                    self._plaza_update_status()

            try:
                self.root.after(0, done)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    # ----------------------------------------------------------- nav badge

    def _apply_plaza_nav_badge(self) -> None:
        try:
            btns = getattr(self, "nav_btns", None) or {}
            btn = btns.get("plaza")
            if not btn:
                return
            unread = plaza.unread_ids(
                getattr(self, "_plaza_items", None) or [],
                plaza.seen_ids(self.cfg),
                dismissed=plaza.dismissed_ids(self.cfg),
            )
            btn.configure(text="广场·新" if unread else "广场")
            if getattr(self, "_current_page", "") == "plaza":
                btn.set_active(True)
        except Exception:
            pass

    # ------------------------------------------------------ models-page ad

    def _render_models_ad(self) -> None:
        """At most one dismissible banner on the models page (host is created
        by the models page integration; absent host = nothing to do)."""
        host = getattr(self, "_models_ad_host", None)
        if host is None:
            return
        ad = plaza.pick_models_banner(
            getattr(self, "_plaza_items", None) or [],
            dismissed=plaza.dismissed_ids(self.cfg),
        )
        # Content-level stamp, not just the id — a same-id feed edit
        # (body/image/url) must rebuild the banner, not short-circuit
        ad_snap = plaza.feed_stamp([ad]) if ad is not None else None
        prev = getattr(self, "_models_ad_snap", "\x00unset")
        try:
            has_children = bool(host.winfo_children())
        except Exception:
            has_children = False
        # Same ad already on screen (or same "no ad") → skip the rebuild
        if ad_snap == prev and (ad is None or has_children):
            return
        try:
            for w in host.winfo_children():
                w.destroy()
        except Exception:
            return
        if ad is None:
            self._models_ad_snap = None
            return

        bar = tk.Frame(
            host,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=TM_HAIRLINE,
        )
        bar.pack(fill="x")
        inner = tk.Frame(bar, bg=TM_SURFACE)
        inner.pack(fill="x", padx=10, pady=8)

        if ad.image_url:
            box = tk.Frame(inner, bg=TM_INSET, width=px(72), height=px(54))
            box.pack(side="left", padx=(0, 10))
            box.pack_propagate(False)
            lbl = tk.Label(box, bg=TM_INSET)
            lbl.place(relx=0.5, rely=0.5, anchor="center")
            self._plaza_load_image(lbl, ad.image_url, px(72), px(54))

        def _close(_e=None, i=ad.id):
            if plaza.dismiss(self.cfg, i):
                try:
                    save_config(self.cfg)
                except Exception:
                    pass
            try:
                self._invalidate_catalog_views()
            except Exception:
                pass
            try:
                for w in host.winfo_children():
                    w.destroy()
            except Exception:
                pass
            self._models_ad_snap = None
            # A dismissal also changes what the plaza page should show
            self._plaza_render_snap = None
            self._apply_plaza_nav_badge()
            return "break"

        close = tk.Label(
            inner,
            text="×",
            font=sans_font(11),
            bg=TM_SURFACE,
            fg=TM_META,
            cursor="hand2",
            padx=4,
        )
        close.pack(side="right", padx=(6, 0))
        close.bind("<Button-1>", _close)
        GhostButton(
            inner,
            ad.action_label or "了解详情",
            command=lambda item=ad: plaza.on_card_clicked(item),
            padx=10,
            pady=4,
        ).pack(side="right")

        mid = tk.Frame(inner, bg=TM_SURFACE)
        mid.pack(side="left", fill="x", expand=True)
        row = tk.Frame(mid, bg=TM_SURFACE)
        row.pack(anchor="w")
        tk.Label(
            row,
            text="广告",
            font=sans_font(8),
            bg=TM_INSET,
            fg=TM_META,
            padx=6,
            pady=1,
        ).pack(side="left", padx=(0, 8))
        title = (ad.title or "").strip()
        if len(title) > 30:
            title = title[:30] + "…"
        tk.Label(
            row,
            text=title,
            font=sans_font(10, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        ).pack(side="left")
        body_lines = (ad.body or "").strip().splitlines()
        line = body_lines[0].strip() if body_lines else ""
        if len(line) > 48:
            line = line[:48] + "…"
        if line:
            tk.Label(
                mid,
                text=line,
                font=sans_font(9),
                bg=TM_SURFACE,
                fg=TM_INK_MUTED,
                anchor="w",
            ).pack(anchor="w", pady=(2, 0))

        if ad.url:
            bar.configure(cursor="hand2")
            self._plaza_bind_card_click(bar, ad, skip=[close])
        self._models_ad_snap = ad_snap

    # ---------------------------------------------------------------- images

    def _plaza_load_image(self, label, url, max_w, max_h) -> None:
        """Async feed-image loader shared by page cards and the ad banner.

        max_w / max_h are PHYSICAL pixels (callers apply px()); CoverCache is
        keyed on the same values so repeated renders reuse the PhotoImage.
        """
        u = (url or "").strip()
        if not u:
            return
        cache = getattr(self, "_cover_cache", None)
        if cache is None:
            return
        path = plaza.image_cache_path(u)

        def _show_from(p):
            try:
                if not label.winfo_exists():
                    return
                photo = cache.get(str(p), max_w=max_w, max_h=max_h)
                if photo is not None:
                    label.configure(image=photo)
                    label.image = photo  # keep a ref so Tk does not GC it
            except Exception:
                pass

        try:
            ready = path.is_file() and path.stat().st_size > 0
        except OSError:
            ready = False
        if ready:
            _show_from(path)
            return

        inflight = getattr(self, "_plaza_img_inflight", None)
        if inflight is None:
            inflight = set()
            self._plaza_img_inflight = inflight
        waiters = getattr(self, "_plaza_img_waiters", None)
        if waiters is None:
            waiters = {}
            self._plaza_img_waiters = waiters
        # Every interested label registers as a waiter; the single download
        # fan-outs to all of them on completion. (A bounded disk poll here
        # used to give up at ~6.6s while the download timeout allows 20s —
        # the second same-URL card then stayed blank for the whole session.)
        waiters.setdefault(u, []).append((label, max_w, max_h))
        if u in inflight:
            return
        inflight.add(u)

        def work():
            p = None
            try:
                p = plaza.ensure_image_cached(u)
            finally:
                try:
                    inflight.discard(u)
                except Exception:
                    pass

            def apply(p=p):
                pending = waiters.pop(u, [])
                if p is None:
                    return
                for lbl, w, h in pending:
                    try:
                        if not lbl.winfo_exists():
                            continue
                        photo = cache.get(str(p), max_w=w, max_h=h)
                        if photo is not None:
                            lbl.configure(image=photo)
                            lbl.image = photo
                    except Exception:
                        pass

            try:
                self.root.after(0, apply)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()
