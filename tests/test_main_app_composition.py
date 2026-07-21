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
            "HomePageMixin",
            "SettingsPageMixin",
        ):
            self.assertIn(mixin, names)
        for meth in (
            "show_onboarding",
            "_maybe_show_onboarding",
            "_open_community_link",
            "toggle_vc",
            "_setup_hotkeys",
            "_dispatch_hotkey",
            "_build_hotkeys_settings_section",
            "show_hotkeys_help",
            "_toggle_monitor",
            "_page_home",
            "_page_settings",
        ):
            self.assertTrue(
                callable(getattr(MainApp, meth, None)),
                msg=f"MainApp missing {meth}",
            )


if __name__ == "__main__":
    unittest.main()
