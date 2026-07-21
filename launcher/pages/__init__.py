# -*- coding: utf-8 -*-
"""Page-builder mixins split out of the main_app monolith.

Each mixin holds one page's Tk builders + handlers and is composed into
MainApp. They share the same instance (self), so cross-page attributes and
methods resolve at runtime via the composed class.
"""

from launcher.pages.home_page import HomePageMixin
from launcher.pages.hotkeys_page import HotkeysMixin
from launcher.pages.models_page import ModelsPageMixin
from launcher.pages.monitor_mixin import MonitorMixin
from launcher.pages.more_page import MorePageMixin
from launcher.pages.onboarding_page import OnboardingMixin
from launcher.pages.profiles_page import ProfilesMixin
from launcher.pages.realtime_control import RealtimeControlMixin
from launcher.pages.settings_page import SettingsPageMixin

__all__ = [
    "HomePageMixin",
    "HotkeysMixin",
    "ModelsPageMixin",
    "MonitorMixin",
    "MorePageMixin",
    "OnboardingMixin",
    "ProfilesMixin",
    "RealtimeControlMixin",
    "SettingsPageMixin",
]
