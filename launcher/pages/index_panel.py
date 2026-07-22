# -*- coding: utf-8 -*-
"""特征索引文件（.index）绑定面板 — 模型页目录与配置档案之间的区块。

一个模型可绑定多个 .index 候选、随时切换或不用；同一个 .index 文件也可以
被多个模型绑定（记录路径即可，多对多）。数据层在 launcher/catalog.py：
list_index_bindings / add_index_binding / remove_index_binding / set_active_index。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from launcher.catalog import (
    add_index_binding,
    get_model_active_index,
    list_index_bindings,
    remove_index_binding,
    set_active_index,
)
from launcher.theme import (
    TM_ACCENT,
    TM_BG,
    TM_HAIRLINE,
    TM_INK,
    TM_META,
    TM_SURFACE,
    mono_font,
    sans_font,
    title_font,
)
from launcher.ui import GhostButton, ask_choice


class IndexPanelMixin:
    def _build_index_panel(self, parent: tk.Frame) -> tk.Frame:
        host = tk.Frame(parent, bg=TM_BG)
        host.pack(fill="x")
        self._index_panel_host = host
        self.refresh_index_panel_ui()
        return host

    def refresh_index_panel_ui(self) -> None:
        host = getattr(self, "_index_panel_host", None)
        if host is None:
            return
        for w in host.winfo_children():
            w.destroy()
        # New rows need the models-page wheel binding (mouse over this panel
        # must still scroll the page). Runs after this rebuild completes.
        cb = getattr(self, "_models_bind_wheel", None)
        if cb:
            try:
                self.root.after(0, cb)
            except Exception:
                pass

        d = self._current_model_dir()
        head = tk.Frame(host, bg=TM_BG)
        head.pack(fill="x", pady=(6, 4))
        tk.Label(
            head,
            text="特征索引文件（.index）",
            font=sans_font(10, "bold"),
            bg=TM_BG,
            fg=TM_INK,
        ).pack(side="left")
        if not d:
            reason = ""
            promotable = False
            try:
                reason = self._current_model_block_reason()
                promotable = self._current_model_is_promotable()
            except Exception:
                pass
            tk.Label(
                host,
                text=reason or "选中一个用户音色后可绑定检索库。",
                font=sans_font(10),
                bg=TM_BG,
                fg=TM_META,
                anchor="w",
            ).pack(anchor="w", pady=(2, 4))
            if promotable:
                GhostButton(
                    host,
                    "转为可管理音色",
                    command=self._promote_current_legacy,
                    padx=12,
                    pady=5,
                ).pack(anchor="w", pady=(0, 4))
            return
        tk.Label(
            head,
            text="检索库让咬字更贴角色；没有也能用",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_META,
        ).pack(side="left", padx=(10, 0))
        GhostButton(
            head, "绑定 index 文件…", command=self._ui_bind_index, padx=12, pady=5
        ).pack(side="right")

        m = self._current_model() or {}
        model_dir = Path(d)
        # Disk is source of truth — never use a stale in-memory m["index"]
        # left over from the previously selected voice.
        try:
            active = get_model_active_index(model_dir)
        except Exception:
            active = str(m.get("index") or "").strip()
            try:
                if active and not Path(active).is_file():
                    active = ""
            except Exception:
                active = ""
        if m is not None:
            m["index"] = active

        rows = tk.Frame(host, bg=TM_BG)
        rows.pack(fill="x")
        self._index_row(
            rows, path="", label="不用检索库（仅 .pth）", badge="", active=(active == "")
        )
        for p in list_index_bindings(model_dir):
            inside = False
            try:
                inside = Path(p).parent.resolve() == model_dir.resolve()
            except Exception:
                pass
            self._index_row(
                rows,
                path=p,
                label=Path(p).name,
                badge="模型文件夹内" if inside else "共享位置（可被多个模型绑定）",
                active=bool(active) and self._same_index_path(p, active),
            )

    @staticmethod
    def _same_index_path(a: str, b: str) -> bool:
        try:
            return Path(a).resolve() == Path(b).resolve()
        except Exception:
            return a == b

    def _index_row(self, parent, *, path, label, badge, active) -> None:
        edge = TM_ACCENT if active else TM_HAIRLINE
        row = tk.Frame(
            parent,
            bg=TM_SURFACE,
            highlightthickness=1,
            highlightbackground=edge,
        )
        row.pack(fill="x", pady=3)
        inner = tk.Frame(row, bg=TM_SURFACE, padx=12, pady=6)
        inner.pack(fill="x")
        left = tk.Frame(inner, bg=TM_SURFACE)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(
            left,
            text=label,
            font=title_font(10, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        ).pack(anchor="w")
        if badge:
            tk.Label(
                left,
                text=badge,
                font=mono_font(7),
                bg=TM_SURFACE,
                fg=TM_META,
                anchor="w",
            ).pack(anchor="w")
        right = tk.Frame(inner, bg=TM_SURFACE)
        right.pack(side="right")
        if active:
            tk.Label(
                right,
                text="使用中",
                font=sans_font(9, "bold"),
                bg=TM_SURFACE,
                fg=TM_ACCENT,
            ).pack(side="right", padx=6)
        else:
            GhostButton(
                right,
                "使用",
                command=lambda p=path: self._ui_use_index(p),
                padx=10,
                pady=4,
            ).pack(side="right", padx=3)
        if path and not active:
            GhostButton(
                right,
                "解绑",
                command=lambda p=path: self._ui_unbind_index(p),
                padx=10,
                pady=4,
            ).pack(side="right", padx=3)

    # -- actions ------------------------------------------------------------
    def _ui_bind_index(self) -> None:
        d = self._current_model_dir()
        if not d:
            return
        # Default to this model's own folder if present, else the shared
        # indices folder — users can still browse out to external files.
        from launcher.paths import INDICES_DIR

        init = d if d and Path(d).is_dir() else str(INDICES_DIR)
        path = filedialog.askopenfilename(
            title="选择特征索引文件 (.index)",
            initialdir=init,
            filetypes=[("特征索引", "*.index"), ("全部", "*.*")],
        )
        if not path:
            return
        choice = ask_choice(
            self.root,
            "绑定方式",
            "把这个 index 文件放在哪里？\n"
            "复制进模型文件夹：跟着模型走，推荐。\n"
            "留在原位置：仅记录路径，同一个文件可被多个模型绑定。",
            [("copy", "复制进模型文件夹"), ("link", "留在原位置")],
        )
        if choice is None:
            return
        try:
            add_index_binding(Path(d), Path(path), copy_into_folder=(choice == "copy"))
        except Exception as e:
            messagebox.showerror("绑定失败", str(e))
            return
        self.refresh_index_panel_ui()
        self._toast_profile("已绑定 index，点「使用」启用")

    def _ui_use_index(self, path: str) -> None:
        d = self._current_model_dir()
        if not d:
            return
        try:
            set_active_index(Path(d), path)
        except Exception as e:
            messagebox.showerror("切换失败", str(e))
            return
        self._after_index_change(path)

    def _ui_unbind_index(self, path: str) -> None:
        d = self._current_model_dir()
        if not d:
            return
        try:
            remove_index_binding(Path(d), path)
        except Exception as e:
            messagebox.showerror("解绑失败", str(e))
            return
        self.refresh_index_panel_ui()
        self._toast_profile("已解绑（文件本身未删除）")

    def _after_index_change(self, path: str) -> None:
        """Reflect the new active index into models list, settings and engine."""
        m = self._current_model()
        if m is not None:
            m["index"] = path
        try:
            if hasattr(self, "var_index_path"):
                self.var_index_path.set(path)
                self._update_index_hint()
        except Exception:
            pass
        try:
            self._sync_model_to_realtime_gui(m)
        except Exception:
            pass
        self.refresh_index_panel_ui()
        self._toast_profile(
            "已切换检索库，重新「开启变声」后生效" if path else "已改为不用检索库"
        )
