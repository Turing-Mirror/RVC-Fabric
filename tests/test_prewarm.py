# -*- coding: utf-8 -*-
"""提前载入音色（预热）。

用户点「开始变声」时最慢的一步是把权重读进显卡。软件启动之后空着的那段时间
正好可以做这件事，于是点下去就能说话。

默认关：预热会提前占住显卡内存，而多数人开着软件的时间远长于真正说话的时间。
"""

from __future__ import annotations

import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PrewarmTests(unittest.TestCase):
    def _read(self, rel: str) -> str:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_default_is_off(self):
        """它会提前占显卡内存，所以必须是用户自己打开的。"""
        cfg = self._read(os.path.join("app", "src-tauri", "src", "config.rs"))
        self.assertIn('m.insert("prewarm_on_start".into(), json!(false));', cfg)

    def test_the_engine_accepts_the_command(self):
        gui = self._read("gui_v1.py")
        self.assertIn('elif action == "prewarm":', gui)
        self.assertIn("def _cmd_prewarm(self)", gui)

    def test_starting_the_stream_reuses_what_was_preloaded(self):
        """预热完却不复用的话，这个开关就只是白占显存。"""
        gui = self._read("gui_v1.py")
        start = gui[gui.index("def start_vc"):]
        start = start[: start.index("rvc_for_realtime.RVC(")]
        self.assertIn('warm = getattr(self, "_prewarmed", None)', start)

    def test_prewarming_never_blocks_anything_else(self):
        """预热是额外的便利。它出任何问题都不该影响用户接下来的操作。"""
        gui = self._read("gui_v1.py")
        body = gui[gui.index("def _cmd_prewarm"):]
        body = body[: body.index("def _preload_pending_model")]
        self.assertIn("except Exception:", body)
        # 正在变声、没选音色、已经预热过，三种情况都直接跳过，不算失败。
        self.assertIn('if getattr(self, "flag_vc", False):', body)
        self.assertIn("os.path.isfile(pth)", body)

    def test_the_shell_only_asks_when_the_setting_is_on(self):
        lib = self._read(os.path.join("app", "src-tauri", "src", "lib.rs"))
        self.assertIn('.get("prewarm_on_start")', lib)
        self.assertIn('worker::send_command(&root_bg, "prewarm", Map::new())', lib)

    def test_prewarm_runs_after_device_enumeration(self):
        """设备列表是界面第一屏就要用的，预热只影响点开始之后等多久。

        顺序反了的话，用户会先看到一个一直转圈的设备列表。
        """
        lib = self._read(os.path.join("app", "src-tauri", "src", "lib.rs"))
        i_dev = lib.index("ensure_worker_and_devices(&root_bg")
        i_warm = lib.index('"prewarm", Map::new()')
        self.assertLess(i_dev, i_warm)

    def test_the_setting_is_visible_in_general(self):
        """写好了必须挂上。"""
        settings = self._read(os.path.join("app", "src", "pages", "SettingsPage.tsx"))
        self.assertIn('t("settings.prewarm")', settings)
        self.assertIn('c.set("prewarm_on_start", v, true)', settings)


if __name__ == "__main__":
    unittest.main()
