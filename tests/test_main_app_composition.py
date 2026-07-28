# -*- coding: utf-8 -*-
"""Composition smoke: MainApp MRO exposes mixin methods (no Tk root / no Runtime)."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MainAppCompositionTests(unittest.TestCase):
    def test_import_and_mixin_methods(self):
        from launcher.main_app import MainApp

        names = [c.__name__ for c in MainApp.__mro__]
        for mixin in (
            "OnboardingMixin",
            "HotkeysMixin",
            "MonitorMixin",
            "RealtimeControlMixin",
            "DockVoiceMixin",
            "ProfilesMixin",
            "ConsultMixin",
            "HomePageMixin",
            "ModelsPageMixin",
            "PlazaPageMixin",
            "MorePageMixin",
            "SettingsPageMixin",
        ):
            self.assertIn(mixin, names)
        for meth in (
            "show_onboarding",
            "_maybe_show_onboarding",
            "_open_community_link",
            "toggle_vc",
            "_start_vc",
            "_stop_vc",
            "_tick_status",
            "_restart_vc_for_new_model",
            "_setup_hotkeys",
            "_dispatch_hotkey",
            "_build_hotkeys_settings_section",
            "show_hotkeys_help",
            "_toggle_monitor",
            "_refresh_monitor_hint",
            "_prefer_monitor_device",
            "_is_virtual_monitor_name",
            "_sync_bottom",
            "undo_voice_params",
            "_apply_model_voice_params",
            "_apply_active_profile",
            "open_consult_wizard",
            "_page_home",
            "_page_models",
            "_page_more",
            "_page_settings",
            "show_page",
            "_select_model",
            # page-switch snapshot contract (grid+tkraise refactor)
            "_show_models_page",
            "_invalidate_catalog_views",
            "_models_catalog_stamp",
            "_models_reflow_tick",
            "_carousel_reflow_tick",
            "_render_carousel",
            # 广场 page + models-page ad banner (PlazaPageMixin contract)
            "_page_plaza",
            "_show_plaza_page",
            "_plaza_reflow_tick",
            "_silent_fetch_plaza",
            "_apply_plaza_nav_badge",
            "_render_plaza",
            "_render_models_ad",
            # wallpaper (settings → 外观)
            "_build_wallpaper_settings_section",
            "_wallpaper_pick",
            "_wallpaper_clear",
            "_wallpaper_update_preview",
        ):
            self.assertTrue(
                callable(getattr(MainApp, meth, None)),
                msg=f"MainApp missing {meth}",
            )
        # Static monitor helper still works without an instance
        self.assertTrue(MainApp._is_virtual_monitor_name("CABLE Input"))
        self.assertFalse(MainApp._is_virtual_monitor_name("Realtek Headphones"))


if __name__ == "__main__":
    unittest.main()
