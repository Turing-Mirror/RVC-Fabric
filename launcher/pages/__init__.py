# -*- coding: utf-8 -*-
"""Page-builder mixins split out of the main_app monolith.

Each mixin holds one page's Tk builders + handlers and is composed into
MainApp. They share the same instance (self), so cross-page attributes and
methods resolve at runtime via the composed class.
"""

from launcher.pages.consult_page import ConsultMixin
from launcher.pages.dock_voice import DockVoiceMixin
from launcher.pages.home_page import HomePageMixin
from launcher.pages.hotkeys_page import HotkeysMixin
from launcher.pages.index_panel import IndexPanelMixin
from launcher.pages.models_page import ModelsPageMixin
from launcher.pages.monitor_mixin import MonitorMixin
from launcher.pages.more_page import MorePageMixin
from launcher.pages.onboarding_page import OnboardingMixin
from launcher.pages.plaza_page import PlazaPageMixin
from launcher.pages.profiles_page import ProfilesMixin
from launcher.pages.realtime_control import RealtimeControlMixin
from launcher.pages.settings_accel import SettingsAccelMixin
from launcher.pages.settings_devices import SettingsDevicesMixin
from launcher.pages.settings_general import SettingsGeneralMixin
from launcher.pages.settings_index import SettingsIndexMixin
from launcher.pages.settings_page import SettingsPageMixin
from launcher.pages.settings_perf_dsp import SettingsPerfDspMixin
from launcher.pages.settings_updates import SettingsUpdatesMixin
from launcher.pages.settings_voice import SettingsVoiceParamsMixin
from launcher.pages.wallpaper_settings import WallpaperSettingsMixin

__all__ = [
    "ConsultMixin",
    "DockVoiceMixin",
    "HomePageMixin",
    "HotkeysMixin",
    "IndexPanelMixin",
    "ModelsPageMixin",
    "MonitorMixin",
    "MorePageMixin",
    "OnboardingMixin",
    "PlazaPageMixin",
    "ProfilesMixin",
    "RealtimeControlMixin",
    "SettingsAccelMixin",
    "SettingsDevicesMixin",
    "SettingsGeneralMixin",
    "SettingsIndexMixin",
    "SettingsPageMixin",
    "SettingsPerfDspMixin",
    "SettingsUpdatesMixin",
    "SettingsVoiceParamsMixin",
    "WallpaperSettingsMixin",
]
