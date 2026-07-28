# -*- coding: utf-8 -*-
"""Settings: GPU / accel backend detect + worker restart."""

from __future__ import annotations

import os
import threading
from tkinter import messagebox

from launcher.config_store import save_config
from launcher.gpu_backend import apply_backend_env, detect_full, normalize_accel
from launcher.paths import ROOT
from launcher.theme import TM_ACCENT, TM_INK_MUTED


class SettingsAccelMixin:
    def _init_gpu_backend(self) -> None:
        """Detect CUDA / DirectML and apply env for worker children."""

        def work():
            try:
                pref = normalize_accel(str(self.cfg.get("accel_backend") or "auto"))
                info = detect_full(ROOT, pref)
                self.root.after(0, lambda: self._apply_gpu_info(info))
            except Exception as e:
                self.root.after(
                    0,
                    lambda e=e: self._set_status_visual(
                        "idle", "引擎待命", f"GPU 检测失败: {e}"
                    ),
                )

        threading.Thread(target=work, daemon=True).start()


    def _apply_gpu_info(self, info: dict) -> None:
        self._gpu_info = info or {}
        try:
            # In-place write to os.environ (apply_backend_env mutates mapping)
            apply_backend_env(os.environ, info)
        except Exception:
            pass
        label = info.get("label") or "?"
        detail = info.get("detail") or ""
        pref = info.get("preference") or "auto"
        backend = info.get("backend") or "?"
        line = f"加速：{label}"
        if detail:
            line += f" · {detail}"
        line += f"  （偏好 {pref} → {backend}）"
        # Soft mismatch: AMD pack but no DML / 50 pack but no CUDA
        try:
            from launcher.package_meta import load_package_meta

            pm = load_package_meta()
            var = str(pm.get("variant") or "")
            if var == "amd" and not info.get("has_dml"):
                line += "  · 本包为 DirectML，但 Runtime 未检出 DML"
            if (
                var in ("nvidia", "nvidia50")
                and pref in ("auto", "cuda")
                and not info.get("has_cuda")
            ):
                line += "  · 未检出 CUDA，确认使用了对应显卡发行包 Runtime"
        except Exception:
            pass
        try:
            if hasattr(self, "lbl_accel_status"):
                self.lbl_accel_status.configure(text=line, fg=TM_INK_MUTED)
        except Exception:
            pass
        # Subtitle when idle — never clobber an engine-error badge with GPU text
        if not self.vc_running and not self._vc_starting:
            try:
                title_now = ""
                try:
                    title_now = str(self.lbl_online.cget("text") or "")
                except Exception:
                    title_now = ""
                if "错误" in title_now or "失败" in title_now:
                    pass  # keep real worker error subtitle
                else:
                    self.lbl_latency.configure(
                        text=f"{label}" + (f" · {detail}" if detail else "")
                    )
            except Exception:
                pass


    def _force_restart_worker_for_backend(self) -> None:
        """Kill live worker so next VC start loads new TM_USE_DML / torch device."""
        import launcher.realtime_client as rt_client

        was_running = bool(self.vc_running or self._vc_starting)
        self.vc_running = False
        self._vc_starting = False
        try:
            rt_client.stop_vc_remote(force=True)
        except Exception:
            pass
        try:
            rt_client.quit_worker(force=True)
        except Exception:
            pass
        try:
            rt_client.kill_orphan_runtime_workers(include_worker=True)
        except Exception:
            pass
        try:
            self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
            self._set_status_visual(
                "idle",
                "引擎待命",
                "加速后端已变更，变声引擎已重置" if was_running else "加速后端已更新",
            )
            self._sync_bottom()
        except Exception:
            pass


    def _on_accel_changed(self) -> None:
        self.cfg["accel_backend"] = normalize_accel(str(self.var_accel.get() or "auto"))
        save_config(self.cfg)

        # Re-detect; always restart worker so CUDA/DML/CPU env reloads
        def work():
            try:
                info = detect_full(ROOT, self.cfg["accel_backend"])

                def done():
                    self._apply_gpu_info(info)
                    self._force_restart_worker_for_backend()
                    tip = (
                        f"已设为：{info.get('label')}（{info.get('backend')}）\n"
                        "变声引擎已按新后端重置；请重新「开启变声」。\n\n"
                        "A/I 卡请用 AMD 发行包；50 系请用 50 系包，勿混用 Runtime。"
                    )
                    messagebox.showinfo("加速后端", tip)

                self.root.after(0, done)
            except Exception as e:
                self.root.after(0, lambda e=e: messagebox.showerror("检测失败", str(e)))

        threading.Thread(target=work, daemon=True).start()


