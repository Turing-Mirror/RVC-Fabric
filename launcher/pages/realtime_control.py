# -*- coding: utf-8 -*-
"""Realtime VC start/stop, status tick, model-switch restart.

Split out of main_app. Orchestrates launcher.realtime_client only; does not
change IPC timeouts or stream semantics. run/_on_close stay on MainApp.
"""

from __future__ import annotations

import threading
import time

from tkinter import messagebox

from launcher import realtime_client as rt_client
from launcher.theme import APP_PRODUCT_TAGLINE, TM_ACCENT, TM_META, TM_OK


class RealtimeControlMixin:
    def _restart_vc_for_new_model(self) -> None:
        """Debounced stop+start so rapid Left/Right only restarts once."""
        if self._model_restart_job is not None:
            try:
                self.root.after_cancel(self._model_restart_job)
            except Exception:
                pass
        name = ""
        if self.models:
            name = self.models[self.model_idx].get("name") or ""
        self._set_status_visual(
            "busy",
            f"切换音色 · {name}",
            "将自动重启变声引擎…",
        )
        self._model_restart_job = self.root.after(450, self._do_model_restart)

    def _do_model_restart(self) -> None:
        self._model_restart_job = None
        if not self.models:
            return

        def work():
            try:
                rt_client.stop_vc_remote(force=False, timeout_s=8.0)
            except Exception:
                try:
                    rt_client.stop_vc_remote(force=True, timeout_s=6.0)
                except Exception:
                    pass
            self.root.after(0, self._start_vc)

        self.vc_running = False
        self._vc_starting = True
        try:
            self.btn_start.configure(text="切换中…", bg=TM_OK)
        except Exception:
            pass
        threading.Thread(target=work, daemon=True).start()

    def toggle_vc(self) -> None:
        if not self.models:
            messagebox.showwarning("没有模型", "请先导入音色。")
            self.show_page("models")
            return
        if self.vc_running or self._vc_starting:
            self._stop_vc()
            return
        self._start_vc()

    def _start_vc(self) -> None:
        m = self.models[self.model_idx]
        self.save_settings_silent()
        self._sync_model_to_realtime_gui(m)
        self._vc_starting = True
        self.vc_running = False
        self.btn_start.configure(text="启动中…", bg=TM_OK)
        self._set_status_visual(
            "busy",
            f"启动中 · {m['name']}",
            "加载模型中，约 20–40 秒",
        )

        def work():
            err = ""
            try:
                # Ensure single healthy worker; wipe orphans from previous crash
                if not rt_client.is_worker_alive():
                    rt_client.start_worker_process(clean_orphans=True)
                st0 = rt_client.wait_worker_ready(timeout_s=100)
                if str(st0.get("state")) == "error" and st0.get("error"):
                    err = str(st0.get("error"))
                    self.root.after(0, lambda: self._on_vc_start_failed(err))
                    return
                try:
                    rt_client.stop_vc_remote(force=False, timeout_s=4.0)
                except Exception:
                    pass
                time.sleep(0.25)
                rt_client.start_vc_remote()
                st = rt_client.wait_vc_running(timeout_s=180)
                if str(st.get("state")) == "running":
                    self.root.after(0, lambda s=st: self._on_vc_started(m, s))
                    return
                err = str(st.get("error") or st.get("message") or "启动失败")
            except Exception as e:
                err = str(e)
            self.root.after(0, lambda: self._on_vc_start_failed(err))

        threading.Thread(target=work, daemon=True).start()

    def _on_vc_started(self, m: dict, st: dict) -> None:
        self._vc_starting = False
        self.vc_running = True
        self.btn_start.configure(text="停止变声", bg=TM_OK)
        delay = int(st.get("delay_ms") or 0)
        infer = int(st.get("infer_ms") or 0)
        self._set_status_visual(
            "live",
            f"变声中 · {m.get('name') or ''}",
            self._format_latency_line(delay, infer),
        )

    def _on_vc_start_failed(self, err: str) -> None:
        self._vc_starting = False
        self.vc_running = False
        self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
        self._set_status_visual("error", "启动失败", (err or "")[:40])
        msg = err or "未知错误"
        # Friendlier text for known engine errors
        low = msg.lower()
        if "jsondecode" in low or "expecting value" in low or "empty" in low:
            msg = (
                "引擎配置文件损坏或为空（常见于上次强制结束时正在写配置）。\n"
                "已可自动修复，请再点一次「开启变声」。\n\n"
                f"技术信息：{err}"
            )
        messagebox.showerror(
            "启动失败",
            msg
            + "\n\n仍不行时：设置里检查输入/输出设备，或「其他 → 强制结束变声引擎」后再试。",
        )

    def _stop_vc(self) -> None:
        self.btn_start.configure(text="停止中…", bg=TM_META)
        self._set_status_visual("busy", "正在停止…", "释放声卡中")

        def work():
            try:
                # Soft stop then force-kill process tree if stream still running
                rt_client.stop_vc_remote(force=True, timeout_s=12.0)
            except Exception:
                try:
                    rt_client.kill_all_project_workers()
                except Exception:
                    pass
            self.root.after(0, self._on_vc_stopped)

        threading.Thread(target=work, daemon=True).start()

    def _on_vc_stopped(self) -> None:
        self.vc_running = False
        self._vc_starting = False
        self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
        self._set_status_visual("idle", "引擎待命", APP_PRODUCT_TAGLINE)

    def _tick_status(self) -> None:
        if getattr(self, "_closing", False):
            return
        try:
            st = rt_client.poll_status()
            state = str(st.get("state") or "")
            if self.vc_running or self._vc_starting:
                if state == "running":
                    self.vc_running = True
                    self._vc_starting = False
                    delay = int(st.get("delay_ms") or 0)
                    infer = int(st.get("infer_ms") or 0)
                    self.btn_start.configure(text="停止变声", bg=TM_OK)
                    name = ""
                    if self.models:
                        name = self.models[self.model_idx].get("name") or ""
                    self._set_status_visual(
                        "live",
                        f"变声中 · {name}" if name else "变声中",
                        self._format_latency_line(delay, infer),
                    )
                elif state == "error":
                    err = str(st.get("error") or "error")
                    self.vc_running = False
                    self._vc_starting = False
                    self.btn_start.configure(text="开启变声", bg=TM_ACCENT)
                    self._set_status_visual("error", "引擎错误", err[:48])
                elif state == "idle" and self.vc_running and not self._vc_starting:
                    # Worker stopped externally
                    self._on_vc_stopped()
        except Exception:
            pass
        if not getattr(self, "_closing", False):
            self.root.after(1000, self._tick_status)

