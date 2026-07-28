# -*- coding: utf-8 -*-
"""Settings: silent GUI update check + nav badge."""

from __future__ import annotations

import threading

from launcher.theme import TM_META


class SettingsUpdatesMixin:
    def _silent_check_updates(self) -> None:
        """Background catalog fetch on startup; refresh settings update card + nav badge.

        Previously only flipped the「设置·新」badge and never re-rendered the
        online-update card, so users saw a permanent「点击检查更新」and believed
        auto-check did nothing.
        """

        def work():
            has = False
            cat = None
            err = ""
            try:
                from launcher.config_store import load_config
                from launcher.online.catalog import fetch_catalog
                from launcher.online.gui_update import check_gui_update

                urls = []
                u = str(load_config().get("update_manifest_url") or "").strip()
                if u:
                    urls.append(u)
                cat = fetch_catalog(urls, timeout=20)
                st = check_gui_update(cat)
                has = bool(st.get("available"))
            except Exception as e:
                has = False
                cat = None
                err = str(e)[:120]

            def done(has_new=has, catalog=cat, error=err):
                self._update_badge_on = has_new
                self._apply_update_nav_badge()
                if catalog is not None and hasattr(self, "_store_page"):
                    try:
                        self._store_page.catalog = catalog
                        self._store_page._render_update_card()
                    except Exception:
                        pass
                if has_new:
                    try:
                        remote = ""
                        if catalog is not None:
                            remote = (
                                catalog.gui.version or catalog.app_version or ""
                            ).strip()
                        self._set_status_visual(
                            "idle",
                            "发现软件更新" + (f" {remote}" if remote else ""),
                            "打开「设置 → 在线更新」可下载应用",
                        )
                    except Exception:
                        pass
                elif error and not catalog:
                    try:
                        # Soft notice only — don't block or look like an engine fault
                        if hasattr(self, "lbl_online"):
                            self.lbl_online.configure(
                                text="更新检查失败（可稍后在设置里重试）",
                                fg=TM_META,
                            )
                    except Exception:
                        pass

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()


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


