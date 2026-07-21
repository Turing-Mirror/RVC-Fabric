# -*- coding: utf-8 -*-
"""Voice-config profile logic mixed into MainApp (Plan A M3a).

Applies a model's active profile (voice + FX + perf) by reflecting its values
into the existing settings/dock Tk vars and reusing the production hot-push
path (``_push_hot_params``) — so the engine applies the whole profile live,
with no engine change. Perf keys are cold (take effect on the next start).

UI (bind / switch / cancel panel) is M3b; this layer already enables the paid
delivery loop: drop a ``.tmvp`` into the model's ``profiles/`` + point
``active_profile`` at it, and it applies on model select.
"""

from __future__ import annotations

from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

from launcher import profiles as P
from launcher.config_store import save_config
from launcher.theme import (
    TM_ACCENT,
    TM_ACCENT_SOFT,
    TM_BG,
    TM_HAIRLINE,
    TM_INK,
    TM_META,
    TM_SURFACE,
    mono_font,
    sans_font,
    title_font,
    tracked,
)
from launcher.ui import GhostButton, PrimaryButton

_SOURCE_LABELS = {
    "default": "原始",
    "self": "自建",
    "import": "导入",
    "official": "官方优化",
}


def _safe_filename(name: str) -> str:
    """Strip characters that are invalid in filenames (for export suggestions)."""
    import re

    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", str(name or "")).strip(". ")
    return cleaned[:80] or "档案"

# cfg-key -> the settings/dock Tk var attribute that mirrors it. Reflecting a
# profile into these vars (then calling _push_hot_params, which re-collects from
# them) keeps cfg, UI, and the worker consistent. Verified against
# settings_page._collect_settings_into_cfg.
_PROFILE_SCALAR_VARS: dict[str, str] = {
    "pitch": "var_pitch",
    "formant": "var_formant",
    "f0method": "var_f0",
    "threhold": "var_threhold",
    "index_rate": "var_index_rate",
    "rms_mix_rate": "var_rms",
    "block_time": "var_block",
    "crossfade_length": "var_crossfade",
    "extra_time": "var_extra",
    "fx_enabled": "var_fx_enabled",
    "fx_gate_enabled": "var_fx_gate_en",
    "fx_gate_threshold_db": "var_fx_gate_thr",
    "fx_gate_release_ms": "var_fx_gate_rel",
    "fx_gate_hold_ms": "var_fx_gate_hold",
    "fx_gate_range_db": "var_fx_gate_range",
    "fx_comp_enabled": "var_fx_comp_en",
    "fx_comp_threshold_db": "var_fx_comp_thr",
    "fx_comp_ratio": "var_fx_comp_ratio",
    "fx_comp_attack_ms": "var_fx_comp_att",
    "fx_comp_release_ms": "var_fx_comp_rel",
    "fx_comp_makeup_db": "var_fx_comp_mu",
    "fx_eq_enabled": "var_fx_eq_en",
    "fx_eq_preset": "var_fx_eq_preset",
    "fx_out_gain_db": "var_fx_out_gain",
}
_PERF_KEYS = frozenset(P.PERF_KEYS)


class ProfilesMixin:
    # -- current model helpers --------------------------------------------
    def _current_model(self) -> Optional[dict]:
        if not getattr(self, "models", None):
            return None
        try:
            return self.models[self.model_idx]
        except (IndexError, TypeError):
            return None

    def _current_model_dir(self) -> Optional[str]:
        m = self._current_model()
        if not m or m.get("source") != "user_data" or not m.get("dir"):
            return None
        return str(m["dir"])

    # -- apply -------------------------------------------------------------
    def _reflect_updates_to_ui(self, updates: dict) -> None:
        """Push profile values into the mirror Tk vars (+ cfg) so the next
        _push_hot_params re-collects the profile, not the stale UI state."""
        self._loading_voice = True
        try:
            for key, val in updates.items():
                self.cfg[key] = val
                if key == "fx_eq_gains":
                    bands = getattr(self, "var_fx_eq_gains", None)
                    if bands and isinstance(val, (list, tuple)) and len(val) == 5:
                        for i in range(5):
                            try:
                                bands[i].set(float(val[i]))
                            except Exception:
                                pass
                    continue
                attr = _PROFILE_SCALAR_VARS.get(key)
                var = getattr(self, attr, None) if attr else None
                if var is not None:
                    try:
                        var.set(val)
                    except Exception:
                        pass
        finally:
            self._loading_voice = False

    def _apply_active_profile(self) -> bool:
        """Overlay the current model's active profile onto UI + engine.

        Returns True when a profile was applied (False = on default). Models
        without an active profile are untouched (early return), keeping the
        blast radius to exactly the feature's users.
        """
        d = self._current_model_dir()
        if not d:
            return False
        try:
            prof = P.resolve_active_profile(d)
        except Exception:
            prof = None
        updates = P.profile_to_config_updates(prof)
        if not updates:
            return False
        self._reflect_updates_to_ui(updates)
        # reuse the production hot path (collects vars -> cfg -> worker + save)
        try:
            self._push_hot_params()
        except Exception:
            try:
                save_config(self.cfg)
            except Exception:
                pass
        # perf keys are cold: hint if a running stream needs a restart
        if self.vc_running and any(k in _PERF_KEYS for k in updates):
            try:
                self._set_status_visual(
                    "live", "档案已应用", "性能项需重新开启变声后完全生效"
                )
            except Exception:
                pass
        return True

    # -- management (called by M3b UI) ------------------------------------
    def _profiles_for_current(self) -> list[dict]:
        d = self._current_model_dir()
        return P.list_profiles(d) if d else []

    def _active_profile_id_current(self) -> str:
        d = self._current_model_dir()
        return P.get_active_profile_id(d) if d else ""

    def _switch_profile(self, profile_id: str) -> bool:
        d = self._current_model_dir()
        if not d:
            return False
        P.set_active_profile_id(d, profile_id)
        if profile_id:
            return self._apply_active_profile()
        # cleared -> revert to the model's default voice params
        m = self._current_model()
        if m is not None:
            try:
                self._apply_model_voice_params(m, push_remote=True)
            except Exception:
                pass
        return False

    def _clear_profile(self) -> None:
        self._switch_profile("")

    def _save_current_as_profile(
        self, name: str, *, source: str = "self", activate: bool = True
    ) -> Optional[str]:
        """Snapshot the current settings into a new profile bound to this model."""
        d = self._current_model_dir()
        if not d:
            return None
        try:
            self._collect_settings_into_cfg()
        except Exception:
            pass
        m = self._current_model() or {}
        prof = P.config_to_profile(
            self.cfg, name, source=source, for_model=str(m.get("name") or "")
        )
        P.save_profile(d, prof)
        if activate:
            P.set_active_profile_id(d, prof["id"])
        return prof["id"]

    def _import_profile(self, src_path: str, *, activate: bool = True) -> Optional[str]:
        """Import an external .tmvp into the current model's profiles/."""
        d = self._current_model_dir()
        if not d:
            return None
        import json

        try:
            with open(src_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return None
        prof = P.validate_profile(raw)
        if prof is None:
            return None
        P.save_profile(d, prof)
        if activate:
            P.set_active_profile_id(d, prof["id"])
            self._apply_active_profile()
        return prof["id"]

    def _delete_profile(self, profile_id: str) -> bool:
        d = self._current_model_dir()
        if not d:
            return False
        was_active = P.get_active_profile_id(d) == profile_id
        ok = P.delete_profile(d, profile_id)
        if ok and was_active:
            m = self._current_model()
            if m is not None:
                try:
                    self._apply_model_voice_params(m, push_remote=True)
                except Exception:
                    pass
        return ok

    def _export_profile(self, profile_id: str, dest_path: str) -> bool:
        d = self._current_model_dir()
        if not d:
            return False
        prof = P.load_profile(d, profile_id)
        if prof is None:
            return False
        import json

        try:
            with open(dest_path, "w", encoding="utf-8") as f:
                json.dump(prof, f, ensure_ascii=False, indent=2)
        except Exception:
            return False
        return True

    # -- UI panel (M3b) ----------------------------------------------------
    def _build_profiles_panel(self, parent) -> tk.Frame:
        """Compact 「配置档案」 strip for the current model (bind/switch/cancel)."""
        host = tk.Frame(parent, bg=TM_BG)
        host.pack(fill="x")
        self._profiles_host = host
        self.refresh_profiles_ui()
        return host

    def refresh_profiles_ui(self) -> None:
        host = getattr(self, "_profiles_host", None)
        if host is None:
            return
        for w in host.winfo_children():
            w.destroy()

        d = self._current_model_dir()
        head = tk.Frame(host, bg=TM_BG)
        head.pack(fill="x", pady=(6, 4))
        tk.Label(
            head,
            text=tracked("PROFILES", gap="  "),
            font=mono_font(8),
            bg=TM_BG,
            fg=TM_META,
        ).pack(side="left")
        if not d:
            tk.Label(
                host,
                text="选中一个用户音色(User_Data)后可绑定配置档案。",
                font=sans_font(10),
                bg=TM_BG,
                fg=TM_META,
                anchor="w",
            ).pack(anchor="w", pady=(2, 4))
            return

        active = self._active_profile_id_current()
        rows = tk.Frame(host, bg=TM_BG)
        rows.pack(fill="x")

        # default (unbound) row
        self._profile_row(rows, pid="", name="默认（原始参数）", source="default",
                          score=None, active=(active == ""))
        for prof in self._profiles_for_current():
            self._profile_row(
                rows,
                pid=prof["id"],
                name=prof.get("name") or "未命名",
                source=str(prof.get("meta", {}).get("source") or "self"),
                score=prof.get("meta", {}).get("score"),
                active=(active == prof["id"]),
            )

        actions = tk.Frame(host, bg=TM_BG)
        actions.pack(fill="x", pady=(6, 2))
        GhostButton(actions, "另存当前为档案", command=self._ui_save_current,
                    padx=12, pady=6).pack(side="left", padx=(0, 6))
        GhostButton(actions, "导入档案…", command=self._ui_import,
                    padx=12, pady=6).pack(side="left", padx=6)
        GhostButton(actions, "导出当前档案…", command=self._ui_export_active,
                    padx=12, pady=6).pack(side="left", padx=6)

    def _profile_row(self, parent, *, pid, name, source, score, active) -> None:
        edge = TM_ACCENT if active else TM_HAIRLINE
        row = tk.Frame(parent, bg=TM_SURFACE, highlightthickness=1,
                       highlightbackground=edge)
        row.pack(fill="x", pady=3)
        inner = tk.Frame(row, bg=TM_SURFACE, padx=12, pady=8)
        inner.pack(fill="x")
        left = tk.Frame(inner, bg=TM_SURFACE)
        left.pack(side="left", fill="x", expand=True)
        badge = _SOURCE_LABELS.get(source, source)
        if score is not None:
            try:
                badge += f" · 相似度 {float(score):.2f}"
            except (TypeError, ValueError):
                pass
        tk.Label(left, text=badge, font=mono_font(7), bg=TM_SURFACE,
                 fg=TM_META, anchor="w").pack(anchor="w")
        tk.Label(left, text=name, font=title_font(11, "bold"), bg=TM_SURFACE,
                 fg=TM_INK, anchor="w").pack(anchor="w", pady=(1, 0))

        right = tk.Frame(inner, bg=TM_SURFACE)
        right.pack(side="right")
        if active:
            tk.Label(right, text="使用中", font=mono_font(8), bg=TM_ACCENT_SOFT,
                     fg=TM_ACCENT, padx=10, pady=4).pack(side="right")
        else:
            PrimaryButton(right, "使用", command=lambda p=pid: self._ui_switch(p),
                          padx=12, pady=4).pack(side="right")
        # default row can't be deleted
        if pid:
            GhostButton(right, "删除", command=lambda p=pid: self._ui_delete(p),
                        padx=10, pady=4).pack(side="right", padx=(0, 6))

    # -- UI action handlers -----------------------------------------------
    def _ui_switch(self, pid: str) -> None:
        self._switch_profile(pid)
        self.refresh_profiles_ui()
        self._toast_profile("已切换档案" if pid else "已回到默认")

    def _ui_delete(self, pid: str) -> None:
        if not messagebox.askyesno("删除档案", "确定删除这个配置档案？(不影响模型本身)"):
            return
        self._delete_profile(pid)
        self.refresh_profiles_ui()

    def _ui_save_current(self) -> None:
        name = simpledialog.askstring("另存为档案", "档案名称：", parent=self.root)
        if not name:
            return
        if self._save_current_as_profile(name) is None:
            messagebox.showinfo("提示", "请先选中一个用户音色(User_Data)。")
            return
        self.refresh_profiles_ui()
        self._toast_profile("已保存并绑定档案")

    def _ui_import(self) -> None:
        path = filedialog.askopenfilename(
            title="导入别人分享的配置档案",
            filetypes=[("配置档案", "*.tmvp"), ("全部", "*.*")],
        )
        if not path:
            return
        # warn if this profile was tuned for a different voice (peer sharing)
        import json

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for_model = str((raw.get("meta") or {}).get("for_model") or "")
        except Exception:
            for_model = ""
        cur = str((self._current_model() or {}).get("name") or "")
        if for_model and cur and for_model != cur:
            if not messagebox.askyesno(
                "音色不一致",
                f"这份档案是给「{for_model}」调的，你现在选的是「{cur}」。\n"
                "仍然可以用，但效果可能和分享者的不一样。要继续导入吗？",
            ):
                return
        if self._import_profile(path) is None:
            messagebox.showerror("导入失败", "这个档案打不开或格式不对，或者你还没选中一个用户音色。")
            return
        self.refresh_profiles_ui()
        self._toast_profile("已导入并应用")

    def _ui_export_active(self) -> None:
        pid = self._active_profile_id_current()
        d = self._current_model_dir()
        if not pid or not d:
            messagebox.showinfo("提示", "现在用的是默认参数，没有可分享的档案。先切到某个档案再导出。")
            return
        prof = P.load_profile(d, pid)
        cur = str((self._current_model() or {}).get("name") or "音色")
        pname = str((prof or {}).get("name") or "档案")
        suggested = _safe_filename(f"{cur}-{pname}") + P.PROFILE_EXT
        path = filedialog.asksaveasfilename(
            title="导出档案（可发给别人使用）",
            initialfile=suggested,
            defaultextension=P.PROFILE_EXT,
            filetypes=[("配置档案", "*.tmvp")],
        )
        if not path:
            return
        if self._export_profile(pid, path):
            self._toast_profile("已导出，可以把这个文件发给别人")
        else:
            messagebox.showerror("导出失败", "无法写入文件。")

    def _toast_profile(self, text: str) -> None:
        try:
            self._set_status_visual(
                "live" if self.vc_running else "idle", text, ""
            )
        except Exception:
            pass
