# -*- coding: utf-8 -*-
"""Hotkeys: in-app binds, global hotkeys, settings card, capture UI.

Split out of main_app. Uses MainApp state (self.root, self.cfg, self._hotkey_map,
self.vc_running, dock/voice helpers, …) on the composed instance.
"""

from __future__ import annotations

import sys
from typing import Optional

import tkinter as tk
from tkinter import messagebox, ttk

from launcher.config_store import save_config
from launcher.hotkeys import (
    ACTION_BY_ID,
    DEFAULT_GLOBAL_ACTIONS,
    DEFAULT_HOTKEYS,
    event_to_hotkey_spec,
    find_duplicate_bindings,
    focus_should_skip_hotkey,
    format_help_text,
    merge_global_actions,
    merge_hotkeys,
    normalize_hotkey,
    to_tk_sequence,
)
from launcher.theme import (
    TM_ACCENT,
    TM_ACCENT_INK,
    TM_BG,
    TM_HAIRLINE,
    TM_HELP,
    TM_INK,
    TM_INK_MUTED,
    TM_INSET,
    TM_META,
    TM_OK,
    TM_SURFACE,
    TM_WARN,
    mono_font,
    px,
    sans_font,
    serif_font,
)
from launcher.ui import GhostButton


class HotkeysMixin:
    def _setup_hotkeys(self) -> None:
        """(Re)bind in-app Tk shortcuts and optional Windows global hotkeys."""
        self._hotkey_map = merge_hotkeys(self.cfg.get("hotkeys"))
        # Clear previous binds
        for seq in self._tk_hotkey_binds:
            try:
                self.root.unbind(seq)
            except Exception:
                pass
        self._tk_hotkey_binds.clear()

        for action_id, spec in self._hotkey_map.items():
            if not spec:
                continue
            seq = to_tk_sequence(spec)
            if not seq:
                continue

            def _handler(_event=None, aid=action_id):
                return self._on_hotkey_event(aid, _event)

            try:
                self.root.bind(seq, _handler)
                self._tk_hotkey_binds.append(seq)
            except Exception:
                pass

        self._refresh_global_hotkeys()

    def _enabled_global_action_ids(self) -> list[str]:
        """Global-eligible actions whose per-key「全局」toggle is on."""
        flags = merge_global_actions(self.cfg.get("global_hotkey_actions"))
        return [aid for aid in DEFAULT_GLOBAL_ACTIONS if flags.get(aid, True)]

    def _refresh_global_hotkeys(self) -> None:
        """Register or tear down Windows global hotkeys based on config."""
        try:
            self._global_hk.unregister_all()
        except Exception:
            pass
        if not bool(self.cfg.get("global_hotkeys")):
            return
        if sys.platform != "win32":
            return
        try:
            hwnd = self.root.winfo_id()
            fails = self._global_hk.register(
                hwnd, self._hotkey_map, action_ids=self._enabled_global_action_ids()
            )
            if fails and hasattr(self, "lbl_online"):
                # Soft notice — don't block UI
                self.lbl_online.configure(
                    text=f"部分全局快捷键未注册（{len(fails)}）",
                    fg=TM_WARN,
                )
        except Exception:
            pass

    def _poll_global_hotkeys(self) -> None:
        if getattr(self, "_closing", False):
            return
        try:
            aid = self._global_hk.poll_once()
            if aid:
                self._dispatch_hotkey(aid, from_global=True)
        except Exception:
            pass
        try:
            if not getattr(self, "_closing", False):
                self.root.after(80, self._poll_global_hotkeys)
        except Exception:
            pass

    def _on_hotkey_event(self, action_id: str, event=None) -> Optional[str]:
        # Skip when typing in Entry / Combobox
        try:
            focus = self.root.focus_get()
            if focus_should_skip_hotkey(focus):
                return None
        except Exception:
            pass
        self._dispatch_hotkey(action_id, from_global=False)
        return "break"

    def _dispatch_hotkey(self, action_id: str, from_global: bool = False) -> None:
        if action_id == "prev_model":
            self._shift_model(-1)
        elif action_id == "next_model":
            self._shift_model(1)
        elif action_id == "toggle_vc":
            self.toggle_vc()
        elif action_id == "pitch_up":
            self._nudge_pitch(1)
        elif action_id == "pitch_down":
            self._nudge_pitch(-1)
        elif action_id == "toggle_monitor":
            self._toggle_monitor()
        elif action_id == "toggle_mode":
            cur = "vc"
            try:
                cur = str(self.var_function.get() or "vc")
            except Exception:
                cur = str(self.cfg.get("function") or "vc")
            self._set_function_mode("im" if cur == "vc" else "vc")
        elif action_id == "undo_voice":
            self.undo_voice_params()
        elif action_id == "redo_voice":
            self.redo_voice_params()
        elif action_id == "reset_voice":
            self.reset_voice_params_default()
        elif action_id == "page_home":
            self.show_page("home")
        elif action_id == "page_models":
            self.show_page("models")
        elif action_id == "page_plaza":
            self.show_page("plaza")
        elif action_id == "page_settings":
            self.show_page("settings")
        elif action_id == "page_more":
            self.show_page("more")
        elif action_id == "show_hotkeys":
            self.show_hotkeys_help()
        elif action_id.startswith("select_model_"):
            try:
                n = int(action_id.rsplit("_", 1)[-1])
                self._select_model_by_slot(n)
            except Exception:
                pass

    def _select_model_by_slot(self, one_based: int) -> None:
        """Quick-pick model 1..9 (1-based index into catalog order)."""
        if not self.models or one_based < 1:
            return
        ix = one_based - 1
        if ix >= len(self.models):
            self._show_switch_toast(f"没有第 {one_based} 个音色")
            return
        self._select_model(ix, feedback=True, maybe_restart=True)

    def _nudge_pitch(self, delta: int) -> None:
        self._voice_hist_push()
        try:
            if hasattr(self, "var_pitch"):
                cur = int(self.var_pitch.get())
            else:
                cur = int(self.cfg.get("pitch") or 0)
        except Exception:
            cur = int(self.cfg.get("pitch") or 0)
        new_v = max(-24, min(24, cur + int(delta)))
        self.cfg["pitch"] = new_v
        try:
            if hasattr(self, "var_pitch"):
                self.var_pitch.set(new_v)
        except Exception:
            pass
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self._persist_voice_params_to_model()
        self._refresh_dock_hint_only()
        if self.vc_running:
            self._on_hot_param()
        self._set_status_visual(
            "live" if self.vc_running else "idle",
            f"音高 {new_v:+d}" if new_v else "音高 0",
            "已写入当前音色" if self.vc_running else "已保存到当前音色",
        )

    def _build_hotkeys_settings_section(self, wrap, card_fn) -> None:
        """Settings card: enable global, list bindings, capture/reset."""
        sec = card_fn(wrap, "快捷键")
        intro = tk.Label(
            sec,
            text=(
                "窗口内快捷键默认可用；开启「全局快捷键」总开关后，勾选了「全局」的按键在游戏全屏时也能触发。"
                "每个按键可单独取消「全局」；点「录制」后按下组合键即可自定义。F1 打开完整说明。"
            ),
            font=sans_font(9),
            bg=TM_SURFACE,
            fg=TM_HELP,
            justify="left",
            anchor="w",
            wraplength=px(640),
        )
        intro.pack(fill="x", pady=(0, 8))
        self._settings_wrap_labels.append(intro)

        self.var_global_hk = tk.BooleanVar(value=bool(self.cfg.get("global_hotkeys")))
        tk.Checkbutton(
            sec,
            text="启用全局快捷键（Windows · 游戏中可用 · 各键的「全局」总开关）",
            variable=self.var_global_hk,
            bg=TM_SURFACE,
            font=sans_font(9),
            command=self._on_global_hk_toggle,
        ).pack(anchor="w", pady=(0, 8))
        # 「切换音色自动重启」不再是可选项：运行中切换音色一律自动重载，
        # 这是产品承诺（其余设置改动仍需手动重新开启变声）。

        # Per-action global-enable flags (default all on; gated by master switch)
        gflags = merge_global_actions(self.cfg.get("global_hotkey_actions"))
        self._global_action_vars: dict[str, tk.BooleanVar] = {}
        self._global_action_checks: dict[str, tk.Checkbutton] = {}
        self._hotkey_row_vars: dict[str, tk.StringVar] = {}
        # Compact list — primary actions first
        primary = [
            "prev_model",
            "next_model",
            "toggle_vc",
            "pitch_up",
            "pitch_down",
            "toggle_monitor",
            "select_model_1",
            "select_model_2",
            "select_model_3",
            "page_home",
            "page_models",
            "page_settings",
            "show_hotkeys",
        ]
        for aid in primary:
            act = ACTION_BY_ID.get(aid)
            if not act:
                continue
            row = tk.Frame(sec, bg=TM_SURFACE)
            row.pack(fill="x", pady=2)
            tk.Label(
                row,
                text=act.label,
                font=sans_font(9),
                bg=TM_SURFACE,
                fg=TM_INK,
                width=18,
                anchor="w",
            ).pack(side="left")
            var = tk.StringVar(value=self._hotkey_map.get(aid) or "")
            self._hotkey_row_vars[aid] = var
            ent = tk.Entry(
                row,
                textvariable=var,
                font=mono_font(9),
                width=16,
                relief="flat",
                bg=TM_INSET,
                fg=TM_INK,
            )
            ent.pack(side="left", padx=(4, 6))
            tk.Button(
                row,
                text="录制",
                font=sans_font(8),
                bg=TM_INSET,
                fg=TM_INK,
                relief="flat",
                cursor="hand2",
                command=lambda a=aid: self._begin_capture_hotkey(a),
                bd=0,
                padx=8,
                pady=2,
            ).pack(side="left", padx=2)
            tk.Button(
                row,
                text="清空",
                font=sans_font(8),
                bg=TM_INSET,
                fg=TM_INK_MUTED,
                relief="flat",
                cursor="hand2",
                command=lambda a=aid, v=var: self._clear_hotkey_row(a, v),
                bd=0,
                padx=6,
                pady=2,
            ).pack(side="left", padx=2)
            if act.global_ok:
                gvar = tk.BooleanVar(value=bool(gflags.get(aid, True)))
                self._global_action_vars[aid] = gvar
                gcb = tk.Checkbutton(
                    row,
                    text="全局",
                    variable=gvar,
                    bg=TM_SURFACE,
                    fg=TM_INK_MUTED,
                    activebackground=TM_SURFACE,
                    selectcolor=TM_INSET,
                    font=sans_font(8),
                    command=self._on_per_key_global_toggle,
                )
                gcb.pack(side="left", padx=(8, 0))
                self._global_action_checks[aid] = gcb
            else:
                tk.Label(
                    row,
                    text="窗口内",
                    font=sans_font(8),
                    bg=TM_SURFACE,
                    fg=TM_META,
                ).pack(side="left", padx=(8, 0))

        self._sync_per_key_global_state()

        btnrow = tk.Frame(sec, bg=TM_SURFACE)
        btnrow.pack(fill="x", pady=(10, 0))
        tk.Button(
            btnrow,
            text="应用快捷键",
            font=sans_font(9),
            bg=TM_ACCENT,
            fg=TM_ACCENT_INK,
            relief="flat",
            cursor="hand2",
            command=self._apply_hotkeys_from_ui,
            bd=0,
            padx=12,
            pady=5,
        ).pack(side="left")
        tk.Button(
            btnrow,
            text="恢复默认",
            font=sans_font(9),
            bg=TM_INSET,
            fg=TM_INK,
            relief="flat",
            cursor="hand2",
            command=self._reset_hotkeys_defaults,
            bd=0,
            padx=12,
            pady=5,
        ).pack(side="left", padx=8)
        tk.Button(
            btnrow,
            text="查看全部",
            font=sans_font(9),
            bg=TM_INSET,
            fg=TM_INK,
            relief="flat",
            cursor="hand2",
            command=self.show_hotkeys_help,
            bd=0,
            padx=12,
            pady=5,
        ).pack(side="left")
        self.lbl_hk_status = tk.Label(
            sec,
            text="",
            font=sans_font(8),
            bg=TM_SURFACE,
            fg=TM_META,
            anchor="w",
        )
        self.lbl_hk_status.pack(fill="x", pady=(6, 0))

    def _on_global_hk_toggle(self) -> None:
        self.cfg["global_hotkeys"] = bool(self.var_global_hk.get())
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self._sync_per_key_global_state()
        self._refresh_global_hotkeys()
        if hasattr(self, "lbl_hk_status"):
            on = bool(self.cfg.get("global_hotkeys"))
            self.lbl_hk_status.configure(
                text="全局快捷键已开启" if on else "全局快捷键已关闭",
                fg=TM_OK if on else TM_META,
            )

    def _sync_per_key_global_state(self) -> None:
        """Enable per-key「全局」checkboxes only while the master switch is on."""
        on = bool(getattr(self, "var_global_hk", None) and self.var_global_hk.get())
        for cb in getattr(self, "_global_action_checks", {}).values():
            try:
                cb.configure(state="normal" if on else "disabled")
            except Exception:
                pass

    def _collect_global_action_flags(self) -> dict[str, bool]:
        return {
            aid: bool(v.get())
            for aid, v in getattr(self, "_global_action_vars", {}).items()
        }

    def _on_per_key_global_toggle(self) -> None:
        self.cfg["global_hotkey_actions"] = self._collect_global_action_flags()
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self._refresh_global_hotkeys()
        if hasattr(self, "lbl_hk_status"):
            n = sum(1 for v in self._collect_global_action_flags().values() if v)
            self.lbl_hk_status.configure(text=f"全局按键已更新（{n} 个启用）", fg=TM_OK)

    def _clear_hotkey_row(self, action_id: str, var: tk.StringVar) -> None:
        var.set("")

    def _begin_capture_hotkey(self, action_id: str) -> None:
        self._capture_action_id = action_id
        act = ACTION_BY_ID.get(action_id)
        label = act.label if act else action_id
        if hasattr(self, "lbl_hk_status"):
            self.lbl_hk_status.configure(
                text=f"请按下要绑定到「{label}」的键…（Esc 取消）",
                fg=TM_WARN,
            )
        # Bind once on root
        self.root.bind("<KeyPress>", self._on_capture_key, add="+")

    def _on_capture_key(self, event) -> Optional[str]:
        if not self._capture_action_id:
            return None
        try:
            ks = str(getattr(event, "keysym", "") or "")
            if ks.lower() in ("escape", "esc"):
                self._end_capture(None)
                return "break"
            # Ignore bare modifiers
            if ks.lower() in (
                "shift_l",
                "shift_r",
                "control_l",
                "control_r",
                "alt_l",
                "alt_r",
                "meta_l",
                "meta_r",
                "win_l",
                "win_r",
            ):
                return "break"
            spec = event_to_hotkey_spec(event)
            if not spec:
                return "break"
            self._end_capture(spec)
            return "break"
        except Exception:
            self._end_capture(None)
            return "break"

    def _end_capture(self, spec: Optional[str]) -> None:
        aid = self._capture_action_id
        self._capture_action_id = None
        try:
            self.root.unbind("<KeyPress>")
        except Exception:
            pass
        # Re-apply normal hotkeys after unbinding capture
        self._setup_hotkeys()
        if not aid:
            return
        if spec is None:
            if hasattr(self, "lbl_hk_status"):
                self.lbl_hk_status.configure(text="已取消录制", fg=TM_META)
            return
        if aid in getattr(self, "_hotkey_row_vars", {}):
            self._hotkey_row_vars[aid].set(spec)
        if hasattr(self, "lbl_hk_status"):
            self.lbl_hk_status.configure(
                text=f"已录制 {spec}（请点「应用快捷键」生效）",
                fg=TM_OK,
            )

    def _apply_hotkeys_from_ui(self) -> None:
        custom: dict[str, str] = {}
        # Start from full map so unlisted select_model_4..9 stay
        custom.update(self._hotkey_map)
        for aid, var in getattr(self, "_hotkey_row_vars", {}).items():
            raw = str(var.get() or "").strip()
            if not raw:
                custom[aid] = ""
            else:
                custom[aid] = normalize_hotkey(raw)
        # Preserve select_model_4..9 from defaults if not in UI
        for i in range(4, 10):
            k = f"select_model_{i}"
            if k not in getattr(self, "_hotkey_row_vars", {}):
                custom.setdefault(k, DEFAULT_HOTKEYS.get(k, ""))

        dups = find_duplicate_bindings(custom)
        if dups:
            lines = []
            for key, ids in dups:
                labels = [
                    ACTION_BY_ID[i].label if i in ACTION_BY_ID else i for i in ids
                ]
                lines.append(f"{key} → {', '.join(labels)}")
            messagebox.showwarning(
                "快捷键冲突",
                "以下按键绑定到了多个功能，请修改后再应用：\n\n" + "\n".join(lines),
            )
            return

        self.cfg["hotkeys"] = {
            k: v for k, v in custom.items() if v != DEFAULT_HOTKEYS.get(k)
        }
        # Also store explicit empty overrides for cleared defaults
        for k, v in custom.items():
            if not v and DEFAULT_HOTKEYS.get(k):
                self.cfg["hotkeys"][k] = ""
        if hasattr(self, "var_global_hk"):
            self.cfg["global_hotkeys"] = bool(self.var_global_hk.get())
        if getattr(self, "_global_action_vars", None):
            self.cfg["global_hotkey_actions"] = self._collect_global_action_flags()
        try:
            save_config(self.cfg)
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            return
        self._hotkey_map = merge_hotkeys(self.cfg.get("hotkeys"))
        # Refresh row display
        for aid, var in getattr(self, "_hotkey_row_vars", {}).items():
            var.set(self._hotkey_map.get(aid) or "")
        self._setup_hotkeys()
        if hasattr(self, "lbl_hk_status"):
            self.lbl_hk_status.configure(text="快捷键已应用", fg=TM_OK)
        messagebox.showinfo("已应用", "快捷键已更新。")

    def _reset_hotkeys_defaults(self) -> None:
        if not messagebox.askyesno("恢复默认", "将快捷键恢复为默认绑定？"):
            return
        self.cfg["hotkeys"] = {}
        self.cfg["global_hotkey_actions"] = {}
        try:
            save_config(self.cfg)
        except Exception:
            pass
        self._hotkey_map = merge_hotkeys({})
        for aid, var in getattr(self, "_hotkey_row_vars", {}).items():
            var.set(self._hotkey_map.get(aid) or "")
        # Per-key「全局」flags back to all-on default
        defaults = merge_global_actions({})
        for aid, gvar in getattr(self, "_global_action_vars", {}).items():
            gvar.set(bool(defaults.get(aid, True)))
        self._sync_per_key_global_state()
        self._setup_hotkeys()
        if hasattr(self, "lbl_hk_status"):
            self.lbl_hk_status.configure(text="已恢复默认快捷键", fg=TM_OK)

    def show_hotkeys_help(self) -> None:
        """Popup listing current shortcut map."""
        win = tk.Toplevel(self.root)
        win.title("快捷键说明")
        win.configure(bg=TM_BG)
        win.geometry(f"{px(480)}x{px(520)}")
        win.minsize(px(400), px(360))
        win.transient(self.root)
        try:
            win.grab_set()
        except Exception:
            pass
        tk.Label(
            win,
            text="快捷键",
            font=serif_font(16, "bold"),
            bg=TM_BG,
            fg=TM_INK,
        ).pack(anchor="w", padx=20, pady=(18, 6))
        frame = tk.Frame(
            win, bg=TM_SURFACE, highlightthickness=1, highlightbackground=TM_HAIRLINE
        )
        frame.pack(fill="both", expand=True, padx=20, pady=8)
        text = tk.Text(
            frame,
            wrap="word",
            font=sans_font(10),
            bg=TM_SURFACE,
            fg=TM_INK,
            relief="flat",
            padx=14,
            pady=12,
            cursor="arrow",
        )
        scroll = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        body = format_help_text(self.cfg.get("hotkeys"))
        if bool(self.cfg.get("global_hotkeys")):
            body += "\n\n当前：全局快捷键已开启。"
        else:
            body += "\n\n当前：仅窗口内生效（可在设置中开启全局）。"
        text.insert("1.0", body)
        text.configure(state="disabled")
        GhostButton(win, "关闭", command=win.destroy, padx=18, pady=8).pack(
            pady=(4, 14)
        )
