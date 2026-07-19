# -*- coding: utf-8 -*-
"""Unit tests for launcher.hotkeys (no GUI / no Windows register)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.hotkeys import (
    ACTION_BY_ID,
    DEFAULT_HOTKEYS,
    find_duplicate_bindings,
    format_help_text,
    merge_hotkeys,
    normalize_hotkey,
    to_tk_sequence,
    to_win_hotkey,
)


class NormalizeTests(unittest.TestCase):
    def test_basic_keys(self):
        self.assertEqual(normalize_hotkey("left"), "Left")
        self.assertEqual(normalize_hotkey("F5"), "F5")
        self.assertEqual(normalize_hotkey("ctrl+up"), "Ctrl+Up")
        self.assertEqual(normalize_hotkey("Control-Alt-1"), "Ctrl+Alt+1")

    def test_mod_order(self):
        self.assertEqual(normalize_hotkey("Shift+Ctrl+Alt+M"), "Ctrl+Alt+Shift+M")

    def test_empty(self):
        self.assertEqual(normalize_hotkey(""), "")
        self.assertEqual(normalize_hotkey("   "), "")


class TkSequenceTests(unittest.TestCase):
    def test_arrows(self):
        self.assertEqual(to_tk_sequence("Left"), "<Left>")
        self.assertEqual(to_tk_sequence("Right"), "<Right>")

    def test_function(self):
        self.assertEqual(to_tk_sequence("F5"), "<F5>")
        self.assertEqual(to_tk_sequence("F1"), "<F1>")

    def test_chord(self):
        self.assertEqual(to_tk_sequence("Ctrl+Up"), "<Control-Up>")
        self.assertEqual(to_tk_sequence("Ctrl+Alt+1"), "<Control-Alt-Key-1>")
        self.assertEqual(to_tk_sequence("Ctrl+M"), "<Control-Key-m>")


class WinHotkeyTests(unittest.TestCase):
    def test_f5(self):
        r = to_win_hotkey("F5")
        self.assertIsNotNone(r)
        flags, vk = r  # type: ignore
        self.assertEqual(vk, 0x74)
        self.assertTrue(flags & 0x4000)  # NOREPEAT

    def test_ctrl_up(self):
        r = to_win_hotkey("Ctrl+Up")
        self.assertIsNotNone(r)
        flags, vk = r  # type: ignore
        self.assertEqual(vk, 0x26)
        self.assertTrue(flags & 0x0002)  # CONTROL


class MergeTests(unittest.TestCase):
    def test_defaults(self):
        m = merge_hotkeys(None)
        self.assertEqual(m["toggle_vc"], "F5")
        self.assertEqual(m["prev_model"], "Left")

    def test_override_and_clear(self):
        m = merge_hotkeys({"toggle_vc": "F6", "prev_model": ""})
        self.assertEqual(m["toggle_vc"], "F6")
        self.assertEqual(m["prev_model"], "")
        # untouched stay default
        self.assertEqual(m["next_model"], DEFAULT_HOTKEYS["next_model"])

    def test_unknown_ignored(self):
        m = merge_hotkeys({"not_an_action": "F9"})
        self.assertNotIn("not_an_action", m)


class DupTests(unittest.TestCase):
    def test_collision(self):
        dups = find_duplicate_bindings(
            {"prev_model": "F5", "toggle_vc": "F5", "next_model": "Right"}
        )
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0][0], "F5")
        self.assertEqual(set(dups[0][1]), {"prev_model", "toggle_vc"})


class HelpTests(unittest.TestCase):
    def test_help_contains_actions(self):
        text = format_help_text({})
        self.assertIn("上一个音色", text)
        self.assertIn("F5", text)
        self.assertTrue(all(a.id in ACTION_BY_ID for a in ACTION_BY_ID.values()))


if __name__ == "__main__":
    unittest.main()
