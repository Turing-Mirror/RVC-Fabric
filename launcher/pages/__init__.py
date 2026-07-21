# -*- coding: utf-8 -*-
"""Page-builder mixins split out of the main_app monolith.

Each mixin holds one page's Tk builders + handlers and is composed into
MainApp. They share the same instance (self), so cross-page attributes and
methods resolve at runtime via the composed class.
"""

from launcher.pages.home_page import HomePageMixin
from launcher.pages.models_page import ModelsPageMixin
from launcher.pages.more_page import MorePageMixin
from launcher.pages.profiles_page import ProfilesMixin
from launcher.pages.settings_page import SettingsPageMixin

__all__ = [
    "HomePageMixin",
    "ModelsPageMixin",
    "MorePageMixin",
    "ProfilesMixin",
    "SettingsPageMixin",
]
