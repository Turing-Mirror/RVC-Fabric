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
            self.btn_start.configure(bg=TM_OK)
        except Exception:
            pass
        self._animate_busy_btn("切换中")
        threading.Thread(target=work, daemon=True).start()

    def toggle_vc(self) -> None:
        if not self.models:
            messagebox.showwarning("没有模型", "请先导入音色。")
            self.show_page("models")
            return
        if self.vc_running or self._vc_starting:
            self._stop_vc()
            return
        # Preflight: current voice's model file must actually be there
        cur = self.models[self.model_idx] if self.models else None
        if cur and cur.get("missing"):
            messagebox.showinfo(
                "音色文件缺失",
                f"当前音色「{cur.get('name')}」的模型文件缺失或没下载完整，无法开启变声。\n\n"
                "请到「模型」页换一个可用音色，或重新下载这个音色。",
            )
            self.show_page("models")
            return
        # Preflight: catch missing devices NOW instead of a 20–40s wait + error
        try:
            inp = str(self.var_input_dev.get() or "").strip()
            out = str(self.var_output_dev.get() or "").strip()
        except Exception:
            inp = str(self.cfg.get("sg_input_device") or "").strip()
            out = str(self.cfg.get("sg_output_device") or "").strip()
        if not inp or not out:
            messagebox.showinfo(
                "先选好设备",
                "还没有选输入/输出设备，开了也不会出声。\n\n"
                "输入设备 = 你的真实麦克风\n"
                "输出设备 = CABLE Input（虚拟声卡）\n\n"
                "带你去设置页选好，再回来点「开启变声」。",
            )
            self.show_page("settings")
            return
        self._start_vc()

    def _start_vc(self) -> None:
        m = self.models[self.model_idx]
        self.save_settings_silent()
        self._sync_model_to_realtime_gui(m)
        # Generation counter: Stop during startup invalidates in-flight work (#14)
        gen = int(getattr(self, "_vc_gen", 0) or 0) + 1
        self._vc_gen = gen
        self._vc_starting = True
        self.vc_running = False
        self.btn_start.configure(bg=TM_OK)
        self._animate_busy_btn("启动中")
        self._set_status_visual(
            "busy",
            f"启动中 · {m['name']}",
            "加载模型中，约 20–40 秒",
        )

        def work():
            err = ""
            try:
                if int(getattr(self, "_vc_gen", 0) or 0) != gen:
                    return  # cancelled by stop
                # Ensure single healthy worker; wipe orphans from previous crash
                if not rt_client.is_worker_alive():
                    rt_client.start_worker_process(clean_orphans=True)
                if int(getattr(self, "_vc_gen", 0) or 0) != gen:
                    return
                st0 = rt_client.wait_worker_ready(timeout_s=100)
                if int(getattr(self, "_vc_gen", 0) or 0) != gen:
                    return
                if str(st0.get("state")) == "error" and st0.get("error"):
                    err = str(st0.get("error"))
                    self.root.after(0, lambda e=err: self._on_vc_start_failed(e))
                    return
                try:
                    rt_client.stop_vc_remote(force=False, timeout_s=4.0)
                except Exception:
                    pass
                if int(getattr(self, "_vc_gen", 0) or 0) != gen:
                    return
                time.sleep(0.25)
                if int(getattr(self, "_vc_gen", 0) or 0) != gen:
                    return
                rt_client.start_vc_remote()
                st = rt_client.wait_vc_running(timeout_s=180)
                if int(getattr(self, "_vc_gen", 0) or 0) != gen:
                    # User stopped while we were starting — soft-stop the stream
                    try:
                        rt_client.stop_vc_remote(force=True, timeout_s=6.0)
                    except Exception:
                        pass
                    return
                if str(st.get("state")) == "running":
                    self.root.after(0, lambda s=st: self._on_vc_started(m, s))
                    return
                err = str(st.get("error") or st.get("message") or "启动失败")
            except Exception as e:
                if int(getattr(self, "_vc_gen", 0) or 0) != gen:
                    return
                err = str(e)
            if int(getattr(self, "_vc_gen", 0) or 0) != gen:
                return
            self.root.after(0, lambda e=err: self._on_vc_start_failed(e))

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
        # Invalidate any in-flight _start_vc work thread (review #14)
        self._vc_gen = int(getattr(self, "_vc_gen", 0) or 0) + 1
        if getattr(self, "_model_restart_job", None) is not None:
            try:
                self.root.after_cancel(self._model_restart_job)
            except Exception:
                pass
            self._model_restart_job = None
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

    def _tick_mic_level(self) -> None:
        """Fast, cheap loop for the dock mic meter (separate from _tick_status
        so the meter can move ~3×/s while everything else stays at 1s)."""
        if getattr(self, "_closing", False):
            return
        delay = 800
        try:
            if self.vc_running:
                st = rt_client.poll_status()
                db = st.get("input_db")
                self._draw_mic_meter(float(db) if db is not None else None)
                delay = 300
            else:
                self._draw_mic_meter(None)
        except Exception:
            pass
        try:
            self.root.after(delay, self._tick_mic_level)
        except Exception:
            pass

    def _animate_busy_btn(self, base: str) -> None:
        """While starting/switching, the button text pulses ('切换中·''··'…)
        so the silent seconds visibly ARE doing something."""
        self._busy_anim_base = base
        self._busy_anim_i = 0
        self._busy_anim_step()

    def _busy_anim_step(self) -> None:
        if not self._vc_starting:
            return  # final text is set by _on_vc_started/_on_vc_start_failed
        base = getattr(self, "_busy_anim_base", "启动中")
        i = getattr(self, "_busy_anim_i", 0)
        try:
            self.btn_start.configure(text=base + "·" * (1 + i % 3))
        except Exception:
            return
        self._busy_anim_i = i + 1
        try:
            self.root.after(400, self._busy_anim_step)
        except Exception:
            pass

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

