# -*- coding: utf-8 -*-
"""Settings: FAISS .index bind helpers (file UI mostly on models page)."""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

from launcher.catalog import (
    bind_index_to_model_dir,
    clear_model_index,
    discover_index_files,
)
from launcher.paths import MODELS_DIR, index_search_roots
from launcher.theme import TM_HELP, TM_OK


class SettingsIndexMixin:
    def _update_index_hint(self) -> None:
        if not hasattr(self, "lbl_index_status"):
            return
        path = ""
        try:
            path = str(self.var_index_path.get() or "").strip()
        except Exception:
            path = ""
        if not path:
            self.lbl_index_status.configure(
                text="当前：未绑定 index（仅用 .pth，Index Rate=0）",
                fg=TM_HELP,
            )
            return
        if Path(path).is_file():
            self.lbl_index_status.configure(
                text=f"当前：{Path(path).name}",
                fg=TM_OK,
            )
        else:
            self.lbl_index_status.configure(
                text="当前路径无效，请重新选择 .index",
                fg=TM_HELP,
            )


    def _refresh_index_combobox_values(self) -> None:
        if not hasattr(self, "cmb_index"):
            return
        roots = index_search_roots()
        found = discover_index_files(roots)
        # Always include current selection even if outside roots
        cur = ""
        try:
            cur = str(self.var_index_path.get() or "").strip()
        except Exception:
            pass
        if cur and cur not in found and Path(cur).is_file():
            found = [cur] + found
        self.cmb_index["values"] = found
        self._update_index_hint()


    def _on_index_chosen(self) -> None:
        path = str(self.var_index_path.get() or "").strip()
        if path and Path(path).is_file():
            self._apply_index_to_current_model(path)
        else:
            self._update_index_hint()


    def browse_index_file(self) -> None:
        if not self.models:
            messagebox.showwarning("没有模型", "请先在「模型」页选择或导入音色。")
            return
        initial = MODELS_DIR
        m = self.models[self.model_idx]
        if m.get("dir") and Path(m["dir"]).is_dir():
            initial = Path(m["dir"])
        path = filedialog.askopenfilename(
            title="选择特征检索 .index 文件",
            initialdir=str(initial),
            filetypes=[
                ("FAISS index", "*.index"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self._apply_index_to_current_model(path)


    def clear_index_file(self) -> None:
        if not self.models:
            return
        m = self.models[self.model_idx]
        model_dir = m.get("dir") or ""
        try:
            if model_dir and m.get("source") == "user_data":
                clear_model_index(Path(model_dir))
            m["index"] = ""
            self.var_index_path.set("")
            self.cfg["index_rate"] = 0.0
            if hasattr(self, "var_index_rate"):
                self.var_index_rate.set(0.0)
            save_config(self.cfg)
            self._sync_model_to_realtime_gui(m)
            self._update_index_hint()
            self.lbl_online.configure(
                text="已清除 index（需重新开启变声才完全生效）",
                fg=TM_META,
            )
        except Exception as e:
            messagebox.showerror("清除失败", str(e))


    def _apply_index_to_current_model(self, index_path: str) -> None:
        if not self.models:
            return
        m = self.models[self.model_idx]
        ip = Path(index_path)
        if not ip.is_file():
            messagebox.showerror("无效文件", f"找不到：\n{index_path}")
            return
        try:
            model_dir = m.get("dir") or ""
            if model_dir and m.get("source") == "user_data":
                bound = bind_index_to_model_dir(
                    Path(model_dir),
                    ip,
                    display_name=m.get("name"),
                    copy_into_folder=True,
                )
            else:
                # Legacy weights: keep absolute path without catalog sidecar
                bound = str(ip.resolve())
            m["index"] = bound
            self.var_index_path.set(bound)
            # Sensible default rate when binding an index
            if float(self.cfg.get("index_rate") or 0) <= 0:
                self.cfg["index_rate"] = 0.5
                if hasattr(self, "var_index_rate"):
                    self.var_index_rate.set(0.5)
            save_config(self.cfg)
            self._sync_model_to_realtime_gui(m)
            self._refresh_index_combobox_values()
            self._update_index_hint()
            self.lbl_online.configure(
                text=f"已绑定 index：{Path(bound).name}（请重新开启变声）",
                fg=TM_OK,
            )
            if self.vc_running:
                messagebox.showinfo(
                    "需要重新开始",
                    "特征检索库已更换。\n请先「停止变声」再「开启变声」后才会加载新的 .index。",
                )
        except Exception as e:
            messagebox.showerror("绑定失败", str(e))


