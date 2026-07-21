# -*- coding: utf-8 -*-
"""Dock bar voice params, MODE buttons, undo/redo history wiring.

Split out of main_app. Pure history stack lives in voice_history; this mixin
owns Tk var sync, per-model persist, and hot push of dock params.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from launcher.catalog import get_model_voice_params, save_model_voice_params
from launcher.config_store import save_config
from launcher.theme import (
    TM_ACCENT,
    TM_ACCENT_INK,
    TM_INK,
    TM_INSET,
    TM_META,
    TM_OK,
    TM_SURFACE,
    TM_SURFACE_HOVER,
)


class DockVoiceMixin:
    def _sync_bottom(self) -> None:
        if self.models:
            m = self.models[self.model_idx]
            self.bottom_name.configure(text=f"当前：{m['name']}")
            extra = m.get("source") or ""
            tag = m.get("tag") or "音色"
            self.bottom_tag.configure(
                text=f"{tag}"
                + (f" · {extra}" if extra == "legacy_weights" else "")
                + f"  ·  {self.model_idx + 1}/{len(self.models)}"
            )
            if hasattr(self, "bottom_voice_hint"):
                try:
                    p = int(self.var_pitch.get())
                    f = float(self.var_formant.get())
                    mode = "变声" if str(self.var_function.get()) == "vc" else "原声"
                    # Keep one short line — dock height is fixed
                    self.bottom_voice_hint.configure(
                        text=f"专属参数  音高 {p:+d}  共鸣 {f:.2f}  ·  {mode}"
                    )
                except Exception:
                    self.bottom_voice_hint.configure(text="参数随音色单独保存")
        else:
            self.bottom_name.configure(text="未选择模型")
            self.bottom_tag.configure(text="请到「模型」页导入音色")
            if hasattr(self, "bottom_voice_hint"):
                self.bottom_voice_hint.configure(text="参数随音色单独保存")
        try:
            self._update_mode_buttons()
        except Exception:
            pass

    def _update_mode_buttons(self) -> None:
        """Style bottom segment control for vc / im."""
        if not hasattr(self, "btn_mode_vc"):
            return
        mode = "vc"
        try:
            mode = str(self.var_function.get() or "vc")
        except Exception:
            mode = str(self.cfg.get("function") or "vc")
        active = mode == "vc"
        try:
            self.btn_mode_vc.configure(
                bg=TM_ACCENT if active else TM_INSET,
                fg=TM_ACCENT_INK if active else TM_INK,
                activebackground=TM_ACCENT if active else TM_SURFACE_HOVER,
                activeforeground=TM_ACCENT_INK if active else TM_INK,
            )
            self.btn_mode_im.configure(
                bg=TM_INSET if active else TM_ACCENT,
                fg=TM_INK if active else TM_ACCENT_INK,
                activebackground=TM_SURFACE_HOVER if active else TM_ACCENT,
                activeforeground=TM_INK if active else TM_ACCENT_INK,
            )
        except Exception:
            pass

    def _set_function_mode(self, mode: str) -> None:
        """Switch 输出变声 (vc) / 原声旁路 (im). Session-level, hot-updatable."""
        mode = "im" if str(mode) == "im" else "vc"
        try:
            self.var_function.set(mode)
        except Exception:
            pass
        self.cfg["function"] = mode
        self._update_mode_buttons()
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self._sync_bottom()
        if self.vc_running:
            self._on_hot_param()
        else:
            try:
                self._collect_settings_into_cfg()
                if self.models:
                    self._sync_model_to_realtime_gui(self.models[self.model_idx])
            except Exception:
                pass
        self._set_status_visual(
            "live" if self.vc_running else "idle",
            "模式：输出变声" if mode == "vc" else "模式：原声旁路",
            "运行中已热切换" if self.vc_running else "下次开启变声生效",
        )

    def _collect_voice_params_dict(self) -> dict:
        """Current UI voice params for per-model save."""
        d: dict = {}
        try:
            d["pitch"] = int(self.var_pitch.get())
            d["formant"] = float(self.var_formant.get())
            d["threhold"] = int(self.var_threhold.get())
            d["index_rate"] = float(self.var_index_rate.get())
            d["rms_mix_rate"] = float(self.var_rms.get())
            d["f0method"] = str(self.var_f0.get() or "fcpe")
        except Exception:
            d["pitch"] = int(self.cfg.get("pitch") or 0)
            d["formant"] = float(self.cfg.get("formant") or 0)
            d["threhold"] = int(
                self.cfg.get("threhold")
                if self.cfg.get("threhold") is not None
                else -60
            )
            d["index_rate"] = float(self.cfg.get("index_rate") or 0)
            d["rms_mix_rate"] = float(self.cfg.get("rms_mix_rate") or 0)
            d["f0method"] = str(self.cfg.get("f0method") or "fcpe")
        return d

    def _apply_model_voice_params(
        self, m: dict, *, push_remote: bool = False
    ) -> None:
        """Load per-model pitch/formant/… into UI + cfg (fallback: global app cfg)."""
        if not m:
            return
        self._loading_voice = True
        try:
            # Prefer live sidecar on disk, then catalog fields, then app defaults
            disk: dict = {}
            if m.get("source") == "user_data" and m.get("dir"):
                try:
                    disk = get_model_voice_params(Path(m["dir"]))
                except Exception:
                    disk = {}
            def pick(key, cast, default):
                if key in disk and disk[key] is not None:
                    return cast(disk[key])
                if m.get(key) is not None:
                    return cast(m.get(key))
                v = self.cfg.get(key)
                if v is None or v == "":
                    return cast(default)
                return cast(v)

            pitch = pick("pitch", lambda x: int(round(float(x))), 0)
            formant = pick("formant", float, 0.0)
            thr = pick("threhold", lambda x: int(round(float(x))), -60)
            ir = pick("index_rate", float, 0.0)
            rms = pick("rms_mix_rate", float, 0.0)
            f0 = pick("f0method", str, "fcpe")

            self.var_pitch.set(pitch)
            self.var_formant.set(formant)
            self.var_threhold.set(thr)
            self.var_index_rate.set(ir)
            self.var_rms.set(rms)
            self.var_f0.set(f0)

            self.cfg["pitch"] = pitch
            self.cfg["formant"] = formant
            self.cfg["threhold"] = thr
            self.cfg["index_rate"] = ir
            self.cfg["rms_mix_rate"] = rms
            self.cfg["f0method"] = f0

            # Keep in-memory model dict in sync
            m["pitch"] = pitch
            m["formant"] = formant
            m["threhold"] = thr
            m["index_rate"] = ir
            m["rms_mix_rate"] = rms
            m["f0method"] = f0
        finally:
            self._loading_voice = False
        try:
            self._sync_bottom()
        except Exception:
            pass
        if push_remote and self.vc_running:
            self._push_hot_params()

    def _persist_voice_params_to_model(
        self, m: Optional[dict] = None, *, immediate: bool = False
    ) -> None:
        """Write current voice params into this model's config.json (user_data only)."""
        if self._loading_voice:
            return
        if m is None:
            if not self.models:
                return
            m = self.models[self.model_idx]
        if m.get("source") != "user_data" or not m.get("dir"):
            return
        params = self._collect_voice_params_dict()

        def _write():
            self._voice_save_job = None
            try:
                side = save_model_voice_params(
                    Path(m["dir"]),
                    params,
                    display_name=m.get("name"),
                )
                for k, v in params.items():
                    m[k] = v
                # also refresh tag/name from disk if any
                if side.get("name"):
                    m["name"] = side["name"]
            except Exception:
                pass

        if immediate:
            if self._voice_save_job is not None:
                try:
                    self.root.after_cancel(self._voice_save_job)
                except Exception:
                    pass
                self._voice_save_job = None
            _write()
            return
        if self._voice_save_job is not None:
            try:
                self.root.after_cancel(self._voice_save_job)
            except Exception:
                pass
        self._voice_save_job = self.root.after(280, _write)

    def _voice_snapshot(self) -> dict:
        return self._collect_voice_params_dict()

    def _voice_hist_push(self) -> None:
        """Push current voice params before a user edit (slider press / reset)."""
        if self._loading_voice:
            return
        self._voice_hist.push(self._voice_snapshot())

    def _apply_voice_snapshot(self, snap: dict, *, push_remote: bool = True) -> None:
        if not snap:
            return
        self._loading_voice = True
        try:
            if "pitch" in snap:
                self.var_pitch.set(int(snap["pitch"]))
                self.cfg["pitch"] = int(snap["pitch"])
            if "formant" in snap:
                self.var_formant.set(float(snap["formant"]))
                self.cfg["formant"] = float(snap["formant"])
            if "threhold" in snap:
                self.var_threhold.set(int(snap["threhold"]))
                self.cfg["threhold"] = int(snap["threhold"])
            if "index_rate" in snap and hasattr(self, "var_index_rate"):
                self.var_index_rate.set(float(snap["index_rate"]))
                self.cfg["index_rate"] = float(snap["index_rate"])
            if "rms_mix_rate" in snap and hasattr(self, "var_rms"):
                self.var_rms.set(float(snap["rms_mix_rate"]))
                self.cfg["rms_mix_rate"] = float(snap["rms_mix_rate"])
            if "f0method" in snap and hasattr(self, "var_f0"):
                self.var_f0.set(str(snap["f0method"]))
                self.cfg["f0method"] = str(snap["f0method"])
        finally:
            self._loading_voice = False
        self._persist_voice_params_to_model(immediate=True)
        self._refresh_dock_hint_only()
        if push_remote:
            self._on_hot_param()

    def undo_voice_params(self) -> None:
        prev = self._voice_hist.undo(self._voice_snapshot())
        if prev is None:
            self._set_status_visual(
                "live" if self.vc_running else "idle",
                "无可撤销",
                "先调整音高/共鸣/阈值",
            )
            return
        self._apply_voice_snapshot(prev)
        self._set_status_visual(
            "live" if self.vc_running else "idle",
            "已撤销",
            f"剩余 {self._voice_hist.undo_len} 步",
        )

    def redo_voice_params(self) -> None:
        nxt = self._voice_hist.redo(self._voice_snapshot())
        if nxt is None:
            self._set_status_visual(
                "live" if self.vc_running else "idle",
                "无可重做",
                "",
            )
            return
        self._apply_voice_snapshot(nxt)
        self._set_status_visual(
            "live" if self.vc_running else "idle",
            "已重做",
            f"还可重做 {self._voice_hist.redo_len} 步",
        )

    def reset_voice_params_default(self) -> None:
        """Restore pitch/formant/threshold defaults for current session + model."""
        self._voice_hist_push()
        defaults = {
            "pitch": 0,
            "formant": 0.0,
            "threhold": -60,
            # keep index/f0/rms as-is (model/index dependent)
        }
        # merge with current so index_rate etc stay
        snap = self._voice_snapshot()
        snap.update(defaults)
        self._apply_voice_snapshot(snap)
        self._set_status_visual(
            "live" if self.vc_running else "idle",
            "已恢复默认",
            "音高 0 · 共鸣 0 · 阈值 -60",
        )

    def _refresh_dock_hint_only(self) -> None:
        """Update dock hint text without full bottom rebuild (no layout thrash)."""
        if not hasattr(self, "bottom_voice_hint"):
            return
        try:
            p = int(self.var_pitch.get())
            f = float(self.var_formant.get())
            mode = "变声" if str(self.var_function.get()) == "vc" else "原声"
            self.bottom_voice_hint.configure(
                text=f"专属参数  音高 {p:+d}  共鸣 {f:.2f}  ·  {mode}"
            )
        except Exception:
            pass

    def _on_dock_param(self) -> None:
        """Bottom dock slider moved — save per-model + hot update (no dock reflow)."""
        if self._loading_voice:
            return
        try:
            self.cfg["pitch"] = int(self.var_pitch.get())
            self.cfg["formant"] = float(self.var_formant.get())
            self.cfg["threhold"] = int(self.var_threhold.get())
        except Exception:
            pass
        self._persist_voice_params_to_model()
        # Debounce hint only — never full _sync_bottom while dragging (causes shake)
        if self._dock_hint_job is not None:
            try:
                self.root.after_cancel(self._dock_hint_job)
            except Exception:
                pass
        self._dock_hint_job = self.root.after(120, self._refresh_dock_hint_only)
        # Hot push without _sync_bottom
        if self._hot_job is not None:
            try:
                self.root.after_cancel(self._hot_job)
            except Exception:
                pass
        self._hot_job = self.root.after(180, self._push_hot_params)

