# -*- coding: utf-8 -*-
"""Consult-pack wizard: gather samples + model identity for team tuning.

Does not gate any knobs — users still fully self-configure and share .tmvp.
This path only builds a zip the user can send to the team.

Supports in-app recording (sounddevice) for dry original / wet converted samples.
"""

from __future__ import annotations

import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

from launcher.consult_pack import (
    ConsultPackError,
    default_include_model_files,
    estimate_model_files_bytes,
    fabric_match_reasons,
    is_fabric_model,
    pack_consult_zip,
)
from launcher.paths import ROOT, USER_DATA
from launcher.sample_record import (
    MAX_SECONDS,
    SampleRecordError,
    SampleRecorder,
    resolve_device_name,
    samples_dir,
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
from launcher.ui import GhostButton, PrimaryButton
from launcher.version import APP_VERSION
from launcher.win_util import open_path


def _fmt_size(n: int) -> str:
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024.0)
    return "%.1f MB" % (n / (1024.0 * 1024.0))


class ConsultMixin:
    def open_consult_wizard(self) -> None:
        """Entry used by 其他 page and 模型/档案 panel."""
        m = None
        try:
            m = self._current_model()
        except Exception:
            m = None
        if not m or m.get("source") != "user_data" or not m.get("dir"):
            messagebox.showinfo(
                "咨询包",
                "请先在「模型」页选中一个用户音色（User_Data），再生成咨询包。",
            )
            return
        self._show_consult_wizard(m)

    def _show_consult_wizard(self, model: dict) -> None:
        model_dir = str(model["dir"])
        side = {}
        try:
            import json

            cfg_path = os.path.join(model_dir, "config.json")
            if os.path.isfile(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    side = raw
        except Exception:
            side = {}

        fabric = is_fabric_model(side)
        match_reasons = fabric_match_reasons(side)
        display = str(model.get("name") or side.get("name") or "音色")
        cfg = getattr(self, "cfg", None) or {}
        recorder = SampleRecorder()
        rec_dir = samples_dir(str(USER_DATA))

        win = tk.Toplevel(self.root)
        win.title("生成咨询包")
        win.configure(bg=TM_BG)
        win.transient(self.root)
        win.grab_set()
        try:
            win.geometry("560x640")
            win.minsize(500, 580)
        except Exception:
            pass

        body = tk.Frame(win, bg=TM_BG, padx=20, pady=16)
        body.pack(fill="both", expand=True)

        tk.Label(
            body,
            text="咨询包（调参服务）",
            font=title_font(14, "bold"),
            bg=TM_BG,
            fg=TM_INK,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            body,
            text="采集原声与变声效果、当前参数与设备信息，打包发给团队。"
            "参数仍可自行调节与分享配置档案。",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_META,
            anchor="w",
            wraplength=500,
            justify="left",
        ).pack(fill="x", pady=(4, 12))

        # current model (read-only)
        card = tk.Frame(
            body, bg=TM_SURFACE, highlightthickness=1, highlightbackground=TM_HAIRLINE
        )
        card.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(card, bg=TM_SURFACE, padx=12, pady=10)
        inner.pack(fill="x")
        tk.Label(
            inner, text="当前音色", font=mono_font(7), bg=TM_SURFACE, fg=TM_META, anchor="w"
        ).pack(anchor="w")
        tk.Label(
            inner,
            text=display,
            font=title_font(12, "bold"),
            bg=TM_SURFACE,
            fg=TM_INK,
            anchor="w",
        ).pack(anchor="w")
        if fabric:
            oid = str(side.get("online_id") or "")
            bits = []
            if oid:
                bits.append(oid)
            if "publisher_mark" in match_reasons:
                bits.append("官方标记")
            if "catalog_id_match" in match_reasons:
                bits.append("清单匹配")
            tip = "RVC Fabric 官方库音色"
            if bits:
                tip += "（" + " · ".join(bits) + "）"
            tip += " — 默认只写入身份信息，无需上传大模型文件"
        else:
            tip = "自备音色 — 如需团队本地复现推理，可勾选下方「包含模型文件」"
        tk.Label(
            inner,
            text=tip,
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
            wraplength=480,
        ).pack(anchor="w", pady=(4, 0))

        # character name
        tk.Label(
            body,
            text="角色音色名（你怎么称呼这个声音）",
            font=sans_font(10),
            bg=TM_BG,
            fg=TM_INK,
            anchor="w",
        ).pack(fill="x", pady=(4, 2))
        var_name = tk.StringVar(value=display)
        ent_name = tk.Entry(
            body, textvariable=var_name, font=sans_font(11), relief="flat", bd=6
        )
        ent_name.pack(fill="x", pady=(0, 8))
        ent_name.configure(
            highlightthickness=1, highlightbackground=TM_HAIRLINE, highlightcolor=TM_ACCENT
        )

        # samples
        var_dry = tk.StringVar(value="")
        var_wet = tk.StringVar(value="")
        rec_status = tk.StringVar(value="")
        tick_id: list = [None]

        def _cancel_tick() -> None:
            if tick_id[0] is not None:
                try:
                    win.after_cancel(tick_id[0])
                except Exception:
                    pass
                tick_id[0] = None

        def _tick() -> None:
            if not recorder.recording:
                return
            rec_status.set(
                "录音中 %s · %.0f / %ds（再点「停止」结束）"
                % (recorder.role, recorder.elapsed, MAX_SECONDS)
            )
            tick_id[0] = win.after(200, _tick)

        def _row_file(parent, label: str, role: str, var: tk.StringVar) -> None:
            fr = tk.Frame(parent, bg=TM_BG)
            fr.pack(fill="x", pady=3)
            tk.Label(
                fr,
                text=label,
                font=sans_font(10),
                bg=TM_BG,
                fg=TM_INK,
                width=12,
                anchor="w",
            ).pack(side="left")
            ent = tk.Entry(fr, textvariable=var, font=mono_font(8), relief="flat", bd=4)
            ent.pack(side="left", fill="x", expand=True, padx=(0, 4))
            ent.configure(highlightthickness=1, highlightbackground=TM_HAIRLINE)

            def browse() -> None:
                path = filedialog.askopenfilename(
                    parent=win,
                    title=label,
                    filetypes=[
                        ("音频", "*.wav *.mp3 *.flac *.ogg *.m4a"),
                        ("全部", "*.*"),
                    ],
                )
                if path:
                    var.set(path)

            def toggle_rec() -> None:
                if recorder.recording:
                    if recorder.role != role:
                        messagebox.showinfo(
                            "录音", "请先停止当前录音。", parent=win
                        )
                        return
                    try:
                        path = recorder.stop()
                        var.set(path)
                        rec_status.set("已保存 %s" % os.path.basename(path))
                    except SampleRecordError as e:
                        messagebox.showerror("录音失败", str(e), parent=win)
                    except Exception as e:
                        messagebox.showerror("录音失败", str(e), parent=win)
                    _cancel_tick()
                    btn_rec.configure(text="录音")
                    return
                # start
                try:
                    self._collect_settings_into_cfg()
                except Exception:
                    pass
                live_cfg = getattr(self, "cfg", None) or cfg
                if role == "wet" and not getattr(self, "vc_running", False):
                    if not messagebox.askyesno(
                        "变声后录音",
                        "当前未开启变声。\n"
                        "变声后样本建议：开启变声后，从 CABLE Output 录音"
                        "（即游戏听到的声音）。\n\n仍要继续录音吗？",
                        parent=win,
                    ):
                        return
                stamp = time.strftime("%Y%m%d_%H%M%S")
                path = os.path.join(rec_dir, "%s_%s.wav" % (role, stamp))
                device = resolve_device_name(role, live_cfg)

                def on_auto(p: str) -> None:
                    def _ui() -> None:
                        var.set(p)
                        rec_status.set("已达最长时长，已保存 %s" % os.path.basename(p))
                        btn_rec.configure(text="录音")
                        _cancel_tick()

                    try:
                        win.after(0, _ui)
                    except Exception:
                        pass

                try:
                    recorder.start(
                        path,
                        role=role,
                        device_name=device,
                        on_auto_stop=on_auto,
                    )
                except SampleRecordError as e:
                    messagebox.showerror("无法录音", str(e), parent=win)
                    return
                btn_rec.configure(text="停止")
                hint = device or "系统默认"
                rec_status.set("录音中 %s · 设备：%s" % (role, hint))
                _tick()

            GhostButton(fr, "浏览…", command=browse, padx=8, pady=4).pack(side="left", padx=(0, 4))
            btn_rec = GhostButton(fr, "录音", command=toggle_rec, padx=8, pady=4)
            btn_rec.pack(side="left")

        tk.Label(
            body,
            text="音频样本（建议各 10–30 秒；可录音或浏览已有文件）",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_META,
            anchor="w",
            wraplength=500,
        ).pack(fill="x", pady=(4, 2))
        tk.Label(
            body,
            text="原声 → 用真实麦克风；变声后 → 请先「开启变声」，软件优先录 CABLE Output。",
            font=sans_font(9),
            bg=TM_BG,
            fg=TM_META,
            anchor="w",
            wraplength=500,
        ).pack(fill="x", pady=(0, 2))
        _row_file(body, "原声", "dry", var_dry)
        _row_file(body, "变声后效果", "wet", var_wet)
        tk.Label(
            body,
            textvariable=rec_status,
            font=mono_font(8),
            bg=TM_BG,
            fg=TM_ACCENT,
            anchor="w",
        ).pack(fill="x", pady=(2, 4))

        # include model files
        var_include = tk.BooleanVar(value=default_include_model_files(side))
        chk_fr = tk.Frame(body, bg=TM_BG)
        chk_fr.pack(fill="x", pady=(8, 2))
        tk.Checkbutton(
            chk_fr,
            text="包含模型文件（.pth / .index）",
            variable=var_include,
            font=sans_font(10),
            bg=TM_BG,
            fg=TM_INK,
            activebackground=TM_BG,
            selectcolor=TM_SURFACE,
            anchor="w",
        ).pack(anchor="w")
        size_hint = estimate_model_files_bytes(model_dir)
        size_txt = (
            f"当前模型约 {_fmt_size(size_hint)}；官方库一般不必勾选。"
            if fabric
            else f"当前模型约 {_fmt_size(size_hint)}；体积较大时请确认网盘/发送方式。"
        )
        tk.Label(
            body, text=size_txt, font=sans_font(9), bg=TM_BG, fg=TM_META, anchor="w"
        ).pack(fill="x")

        # notes
        tk.Label(
            body, text="备注（可选）", font=sans_font(10), bg=TM_BG, fg=TM_INK, anchor="w"
        ).pack(fill="x", pady=(10, 2))
        notes_box = scrolledtext.ScrolledText(
            body, height=3, font=sans_font(10), relief="flat", wrap="word", bd=4
        )
        notes_box.pack(fill="both", expand=True, pady=(0, 8))
        notes_box.configure(highlightthickness=1, highlightbackground=TM_HAIRLINE)

        status = tk.Label(body, text="", font=sans_font(9), bg=TM_BG, fg=TM_META, anchor="w")
        status.pack(fill="x", pady=(0, 6))

        actions = tk.Frame(body, bg=TM_BG)
        actions.pack(fill="x")

        def close() -> None:
            _cancel_tick()
            try:
                recorder.cancel()
            except Exception:
                pass
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        def do_pack() -> None:
            if recorder.recording:
                messagebox.showinfo("提示", "请先停止录音。", parent=win)
                return
            name = (var_name.get() or "").strip()
            if not name:
                messagebox.showinfo("提示", "请填写角色音色名。", parent=win)
                return
            dry = (var_dry.get() or "").strip()
            wet = (var_wet.get() or "").strip()
            if not dry or not wet:
                messagebox.showinfo(
                    "提示",
                    "请录制或选择原声和变声后效果两段音频。",
                    parent=win,
                )
                return
            include = bool(var_include.get())
            if include and size_hint >= 30 * 1024 * 1024:
                if not messagebox.askyesno(
                    "确认包含模型",
                    f"模型文件约 {_fmt_size(size_hint)}，打包会稍慢，zip 也更大。\n确定要包含吗？",
                    parent=win,
                ):
                    return
            notes = notes_box.get("1.0", "end").strip()
            try:
                self._collect_settings_into_cfg()
            except Exception:
                pass
            live_cfg = getattr(self, "cfg", None) or {}
            status.configure(text="正在打包…", fg=TM_META)
            win.update_idletasks()
            try:
                zpath = pack_consult_zip(
                    str(ROOT),
                    model_dir=model_dir,
                    character_name=name,
                    dry_path=dry,
                    wet_path=wet,
                    include_model_files=include,
                    notes=notes,
                    cfg=live_cfg,
                    app_version=APP_VERSION,
                )
            except ConsultPackError as e:
                status.configure(text="")
                messagebox.showerror("无法生成", str(e), parent=win)
                return
            except Exception as e:
                status.configure(text="")
                messagebox.showerror("失败", str(e), parent=win)
                return
            out = USER_DATA / "consult_packs"
            try:
                open_path(out)
            except Exception:
                pass
            messagebox.showinfo(
                "咨询包已生成",
                f"已生成：\n{zpath}\n\n"
                "请把这个 zip 发给团队（可进群后发送）。\n"
                "内容含环境摘要、配置档案、音频对照与模型身份"
                + ("及模型文件。" if include else "（未含模型文件）。"),
                parent=win,
            )
            close()

        win.protocol("WM_DELETE_WINDOW", close)
        GhostButton(actions, "取消", command=close, padx=16, pady=8).pack(side="right")
        PrimaryButton(actions, "生成咨询包", command=do_pack, padx=18, pady=8).pack(
            side="right", padx=(0, 8)
        )
