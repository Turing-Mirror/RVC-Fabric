# -*- coding: utf-8 -*-
"""Smoke: MainApp constructs and builds every page without NameError.

Guards against settings-split regressions (missing imports in section mixins).
Requires a display (Tk); skipped only if Tk root cannot be created.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _tk_available() -> bool:
    try:
        import tkinter as tk

        r = tk.Tk()
        r.withdraw()
        r.destroy()
        return True
    except Exception:
        return False


@unittest.skipUnless(_tk_available(), "Tk display not available")
class MainAppStartupTests(unittest.TestCase):
    def test_main_app_builds_all_pages(self):
        from launcher.main_app import MainApp

        app = MainApp()
        try:
            self.assertTrue(hasattr(app, "pages"))
            for key in ("home", "models", "plaza", "settings", "help", "more"):
                self.assertIn(key, app.pages, msg=f"missing page {key}")
            # Default after construct: 首页 on top (not last-gridded 其他)
            self.assertEqual(app._current_page, "home")
            # Navigate each page (show_page hooks must not throw)
            for key in ("home", "models", "plaza", "settings", "help", "more"):
                app.show_page(key)
                self.assertEqual(app._current_page, key)
            app.show_page("home")
            self.assertEqual(app._current_page, "home")
            # Settings section builders left critical widgets behind
            self.assertTrue(hasattr(app, "var_hostapi"))
            self.assertTrue(hasattr(app, "var_fx_enabled"))
            self.assertTrue(hasattr(app, "var_close_action"))
            self.assertTrue(hasattr(app, "cmb_accel"))
            # Shared handlers still bound
            self.assertTrue(callable(app.save_settings_silent))
            self.assertTrue(callable(app.reload_devices))
            self.assertTrue(callable(app._on_hot_param))
            app.save_settings_silent()
        finally:
            try:
                app.root.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
