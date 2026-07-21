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
            "HomePageMixin",
            "ModelsPageMixin",
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
            "_page_home",
            "_page_models",
            "_page_more",
            "_page_settings",
            "show_page",
            "_select_model",
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
