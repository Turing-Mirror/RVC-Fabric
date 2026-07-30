# -*- coding: utf-8 -*-
"""Settings: silent GUI update check + nav badge + startup update prompt."""

from __future__ import annotations

import threading
import time

from launcher.theme import TM_ACCENT, TM_META, TM_WARN
from launcher.version import display_version


class SettingsUpdatesMixin:
    # Wall-clock for silent startup check (UI timeout message if exceeded)
    _SILENT_UPDATE_OVERALL_S = 12.0

    def _silent_check_updates(self) -> None:
        """Background catalog fetch on startup; refresh card + badge; prompt if new.

        Long waits were mostly ``download_file`` multipart/Range probes + retries
        on a tiny index.json — now ``fetch_catalog`` uses a simple GET with a
        hard overall budget. UI shows「正在检查…」and a timeout line if slow.
        """
        if getattr(self, "_silent_update_running", False):
            return
        self._silent_update_running = True
        if not hasattr(self, "_update_prompt_shown"):
            self._update_prompt_shown = False

        # Immediate UI feedback so auto-check is visible
        def _mark_checking():
            try:
                if hasattr(self, "_store_page") and self._store_page.lbl_gui_status:
                    self._store_page.lbl_gui_status.configure(
                        text="正在自动检查更新…（国内 CNB，通常数秒内完成）",
                        fg=TM_ACCENT,
                    )
            except Exception:
                pass

        try:
            self.root.after(0, _mark_checking)
        except Exception:
            pass

        overall = float(self._SILENT_UPDATE_OVERALL_S)

        def work():
            has = False
            cat = None
            err = ""
            st: dict = {}
            t0 = time.monotonic()
            try:
                from launcher.config_store import load_config
                from launcher.online.catalog import fetch_catalog
                from launcher.online.gui_update import check_gui_update

                urls = []
                u = str(load_config().get("update_manifest_url") or "").strip()
                if u:
                    urls.append(u)
                # per-URL slightly under overall so we can still surface timeout text
                cat = fetch_catalog(
                    urls,
                    timeout=max(4, int(overall) - 2),
                    overall_timeout=overall,
                )
                st = check_gui_update(cat)
                has = bool(st.get("available"))
                err = (getattr(cat, "fetch_error", None) or "").strip()
            except Exception as e:
                has = False
                cat = None
                err = str(e)[:160]
            elapsed = time.monotonic() - t0
            if not err and elapsed >= overall - 0.05 and not has:
                # defensive: should already be set by fetch_catalog
                err = err or f"检查更新超时（{overall:.0f}s）"

            def done(
                has_new=has,
                catalog=cat,
                error=err,
                status=st,
                took=elapsed,
            ):
                self._silent_update_running = False
                self._update_badge_on = has_new
                self._apply_update_nav_badge()
                if catalog is not None and hasattr(self, "_store_page"):
                    try:
                        self._store_page.catalog = catalog
                        self._store_page._render_update_card()
                    except Exception:
                        pass
                # Annotate card if remote failed / timed out (even with cache)
                if error and hasattr(self, "_store_page"):
                    try:
                        lbl = self._store_page.lbl_gui_status
                        if lbl is not None and not has_new:
                            base = ""
                            try:
                                base = str(lbl.cget("text") or "")
                            except Exception:
                                base = ""
                            tip = (
                                f"自动检查未拉到最新清单（{took:.1f}s）：{error}\n"
                                "可点「检查更新」重试；国内访问 CNB 一般很快，"
                                "若总超时请检查代理/防火墙。"
                            )
                            if "超时" in error or "timeout" in error.lower():
                                tip = (
                                    f"检查更新超时（{overall:.0f}s 内未完成）。\n"
                                    "国内从 CNB 拉清单通常只需几秒；可点「检查更新」重试，"
                                    "或检查网络/代理是否拦截 cnb.cool。"
                                )
                            if base and "已是最新" in base:
                                lbl.configure(
                                    text=base + "\n" + tip,
                                    fg=TM_WARN,
                                )
                            elif not has_new:
                                lbl.configure(text=tip, fg=TM_WARN)
                    except Exception:
                        pass
                if has_new:
                    remote = str(status.get("remote") or "").strip()
                    notes = str(status.get("notes") or "").strip()
                    rem_d = str(
                        status.get("remote_display")
                        or display_version(remote)
                        or remote
                    ).strip()
                    loc_d = str(
                        status.get("local_display")
                        or display_version(str(status.get("local") or ""))
                        or status.get("local")
                        or ""
                    ).strip()
                    try:
                        self._set_status_visual(
                            "idle",
                            "发现软件更新" + (f" {rem_d}" if rem_d else ""),
                            "可立即下载应用，完成后可自动重启",
                        )
                    except Exception:
                        pass
                    self._prompt_update_available(
                        remote=rem_d,
                        notes=notes,
                        local=loc_d,
                        package_type=str(status.get("package_type") or ""),
                        action=str(status.get("action") or ""),
                    )
                elif error and not catalog:
                    try:
                        if hasattr(self, "lbl_online"):
                            self.lbl_online.configure(
                                text="更新检查失败（可稍后在设置里重试）",
                                fg=TM_META,
                            )
                    except Exception:
                        pass
                elif not has_new and not error and hasattr(self, "_store_page"):
                    # Successful auto-check, already latest — status already rendered
                    try:
                        if self._store_page.lbl_gui_status is not None:
                            # ensure we don't leave "正在自动检查"
                            pass
                    except Exception:
                        pass

            try:
                self.root.after(0, done)
            except Exception:
                self._silent_update_running = False

        threading.Thread(target=work, daemon=True, name="tm-silent-update").start()

        # Watchdog: if thread hung past overall+2s, still unlock UI flag + tip
        def _watchdog():
            if not getattr(self, "_silent_update_running", False):
                return
            self._silent_update_running = False
            try:
                if hasattr(self, "_store_page") and self._store_page.lbl_gui_status:
                    self._store_page.lbl_gui_status.configure(
                        text=(
                            f"检查更新超时（>{overall:.0f}s）。\n"
                            "请点「检查更新」重试；若反复超时，检查是否访问不了 cnb.cool。"
                        ),
                        fg=TM_WARN,
                    )
            except Exception:
                pass

        try:
            self.root.after(int((overall + 2) * 1000), _watchdog)
        except Exception:
            pass

    def _prompt_update_available(
        self,
        *,
        remote: str = "",
        notes: str = "",
        local: str = "",
        package_type: str = "",
        action: str = "",
    ) -> None:
        """One-shot session popup when auto-check finds a newer package.

        Yes → jump to 设置 and start download/apply (skip second confirm).
        After apply, user is asked whether to auto-restart (see MainApp).
        """
        if getattr(self, "_update_prompt_shown", False):
            return
        self._update_prompt_shown = True
        ver_line = f"{local or '?'} → {remote or '?'}" if remote else "有可用增量更新"
        note_part = (notes[:320] + "…") if len(notes) > 320 else (notes or "（无更新说明）")
        is_full = (
            str(package_type or "").lower() in ("full_package", "full")
            or str(action or "") == "external"
        )
        if is_full:
            body = (
                f"发现全量更新提示：{ver_line}\n\n"
                f"{note_part}\n\n"
                "全量包不能在软件内覆盖安装。是否打开「设置 → 在线更新」查看说明？"
            ).strip()
        else:
            body = (
                f"发现软件更新：{ver_line}\n\n"
                f"{note_part}\n\n"
                "是否立即下载并应用增量更新？\n"
                "（应用完成后可选择自动重启，或稍后手动重启）"
            ).strip()

        def ask():
            try:
                from tkinter import messagebox

                yes = messagebox.askyesno("发现软件更新", body, parent=self.root)
            except Exception:
                return
            if not yes:
                return
            try:
                self.show_page("settings")
            except Exception:
                pass

            def _offer_apply():
                try:
                    if not hasattr(self, "_store_page") or self._store_page is None:
                        return
                    if is_full:
                        # Open external full-package help if available
                        try:
                            self._store_page.open_full_package_help()
                        except Exception:
                            pass
                        return
                    try:
                        from launcher.online.gui_update import check_gui_update

                        st = check_gui_update(self._store_page.catalog)
                        if not st.get("available"):
                            return
                    except Exception:
                        pass
                    self._store_page.apply_gui(skip_confirm=True)
                except Exception:
                    pass

            try:
                self.root.after(220, _offer_apply)
            except Exception:
                pass

        try:
            # Slight delay so first paint / onboarding don't cover the dialog
            self.root.after(400, ask)
        except Exception:
            pass

    def _prompt_restart_after_update(self, *, n_files: int = 0) -> None:
        """After gui_patch apply: ask auto-restart vs manual."""
        try:
            from tkinter import messagebox

            yes = messagebox.askyesno(
                "更新完成",
                (
                    f"更新已应用（{n_files} 个文件）。\n\n"
                    "需要重启软件后新版本才会完全生效。\n\n"
                    "是否立即自动重启？\n\n"
                    "选「否」可稍后自行关闭并重新打开。"
                ),
                parent=self.root,
            )
        except Exception:
            return
        if yes:
            self._restart_app_now()
        else:
            try:
                from tkinter import messagebox

                messagebox.showinfo(
                    "更新完成",
                    "已选择稍后手动重启。\n请在方便时关闭并重新打开软件。",
                    parent=self.root,
                )
            except Exception:
                pass

    def _restart_app_now(self) -> None:
        """Schedule delayed relaunch then force-exit (releases single-instance mutex)."""
        try:
            from launcher.app_relaunch import schedule_self_relaunch

            schedule_self_relaunch(delay_s=1.6)
        except Exception as e:
            try:
                from tkinter import messagebox

                messagebox.showwarning(
                    "自动重启失败",
                    f"无法安排自动重启：{e}\n\n请手动关闭并重新打开软件。",
                    parent=self.root,
                )
            except Exception:
                pass
            return
        try:
            self._on_close(force_exit=True)
        except Exception:
            try:
                import os

                os._exit(0)
            except Exception:
                pass

    def _apply_update_nav_badge(self) -> None:
        # 在线更新 now lives inside 设置 — badge the 设置 nav item instead
        btn = self.nav_btns.get("settings")
        if not btn:
            return
        try:
            if self._update_badge_on:
                btn.configure(text="设置·新")
            else:
                btn.configure(text="设置")
            if self._current_page == "settings":
                btn.set_active(True)
        except Exception:
            pass


