# -*- coding: utf-8 -*-
"""Device auto-pick must not steal the hardware mic for NVIDIA Broadcast."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.device_pick import (
    fill_missing_devices,
    is_virtual_capture_name,
    pick_default_input,
    pick_default_output,
    resolve_device_name,
)


INPUTS = [
    "Microsoft Sound Mapper - Input",
    "Voicemeeter Out B1 (VB-Audio Vo",
    "麦克风 (NVIDIA Broadcast)",
    "CABLE Output (VB-Audio Virtual ",
    "麦克风 (Realtek(R) Audio)",
]

OUTPUTS = [
    "Microsoft Sound Mapper - Output",
    "CABLE Input (VB-Audio Virtual C",
    "扬声器 (Realtek(R) Audio)",
]


class VirtualCaptureTests(unittest.TestCase):
    def test_broadcast_is_virtual(self):
        self.assertTrue(is_virtual_capture_name("麦克风 (NVIDIA Broadcast)"))
        self.assertFalse(is_virtual_capture_name("麦克风 (Realtek(R) Audio)"))


class PickDefaultTests(unittest.TestCase):
    def test_prefers_realtek_over_broadcast(self):
        self.assertEqual(pick_default_input(INPUTS), "麦克风 (Realtek(R) Audio)")

    def test_cable_input_for_output(self):
        self.assertEqual(
            pick_default_output(OUTPUTS), "CABLE Input (VB-Audio Virtual C"
        )

    def test_prefers_cable_input_over_16ch(self):
        both = [
            "扬声器 (Realtek(R) Audio)",
            "CABLE In 16ch (VB-Audio Virtual",
            "CABLE Input (VB-Audio Virtual C",
        ]
        self.assertEqual(
            pick_default_output(both), "CABLE Input (VB-Audio Virtual C"
        )

    def test_16ch_is_not_a_stand_in_for_cable_input(self):
        """diag 26.8.29/210251：列表只剩 16ch 时不要顶上普通 CABLE。"""
        only_16 = [
            "扬声器 (Realtek(R) Audio)",
            "CABLE In 16ch (VB-Audio Virtual",
        ]
        self.assertEqual(pick_default_output(only_16), "")


class ResolveTests(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(
            resolve_device_name("麦克风 (Realtek(R) Audio)", INPUTS),
            "麦克风 (Realtek(R) Audio)",
        )

    def test_truncated_mme_prefix(self):
        self.assertEqual(
            resolve_device_name("CABLE Input (VB-Audio Virtual C", OUTPUTS),
            "CABLE Input (VB-Audio Virtual C",
        )

    def test_does_not_collapse_two_mics_to_the_first(self):
        self.assertEqual(
            resolve_device_name("麦克风 (Realtek(R) Audio)", INPUTS),
            "麦克风 (Realtek(R) Audio)",
        )
        self.assertNotEqual(
            resolve_device_name("麦克风 (Realtek(R) Audio)", INPUTS),
            "麦克风 (NVIDIA Broadcast)",
        )

    def test_speaker_to_headphone_same_hardware_token(self):
        """插拔耳机后扬声器/耳机改名，监听配置不能整段失效。"""
        outs = [
            "CABLE Input (VB-Audio Virtual C",
            "耳机 (3- KM-HIFI-384KHZ)",
            "扬声器 (Realtek(R) Audio)",
        ]
        self.assertEqual(
            resolve_device_name("扬声器 (3- KM-HIFI-384KHZ)", outs),
            "耳机 (3- KM-HIFI-384KHZ)",
        )


class FillMissingTests(unittest.TestCase):
    def test_keeps_saved_realtek_when_output_name_is_truncated(self):
        inn, out, notes = fill_missing_devices(
            "麦克风 (Realtek(R) Audio)",
            "CABLE Input (VB-Audio Virtual C",
            INPUTS,
            OUTPUTS,
        )
        self.assertEqual(inn, "麦克风 (Realtek(R) Audio)")
        self.assertEqual(out, "CABLE Input (VB-Audio Virtual C")
        self.assertEqual(notes, [])

    def test_output_mismatch_does_not_repick_input(self):
        inn, out, notes = fill_missing_devices(
            "麦克风 (Realtek(R) Audio)",
            "Some Dead Output",
            INPUTS,
            OUTPUTS,
        )
        self.assertEqual(inn, "麦克风 (Realtek(R) Audio)")
        self.assertEqual(out, "CABLE Input (VB-Audio Virtual C")
        self.assertTrue(any("output" in n for n in notes))

    def test_empty_saved_picks_hardware_mic(self):
        inn, _out, _notes = fill_missing_devices("", "", INPUTS, OUTPUTS)
        self.assertEqual(inn, "麦克风 (Realtek(R) Audio)")


class PickDefaultNoCableTests(unittest.TestCase):
    """主输出找不到 CABLE 时必须返回空，不能拿耳机/扬声器顶上。

    26.8.19/3：CABLE 瞬时不在设备列表里，旧逻辑把变声主输出补成了
    HyperX 耳机 —— 变声结果直接进耳机，用户从此一直听到自己的声音。
    """

    def test_no_cable_means_no_output_not_headphones(self):
        outs = ["耳机 (HyperX Cloud III)", "扬声器 (Realtek(R) Audio)"]
        self.assertEqual(pick_default_output(outs), "")

    def test_saved_cable_input_does_not_resolve_to_16ch(self):
        """截断的 CABLE Input 不能 startswith 对上 CABLE In 16ch。"""
        only_16 = ["CABLE In 16ch (VB-Audio Virtual", "扬声器 (Realtek(R) Audio)"]
        self.assertIsNone(
            resolve_device_name("CABLE Input (VB-Audio Virtual C", only_16)
        )

    def test_fill_missing_returns_empty_output_when_no_cable(self):
        inn, out, notes = fill_missing_devices(
            "麦克风 (Realtek(R) Audio)",
            "CABLE Input (VB-Audio Virtual C",
            INPUTS,
            ["耳机 (HyperX Cloud III)"],
        )
        self.assertEqual(inn, "麦克风 (Realtek(R) Audio)")
        self.assertEqual(out, "")
        self.assertTrue(any("output" in n for n in notes))

    def test_fill_missing_does_not_swap_input_for_16ch(self):
        inn, out, notes = fill_missing_devices(
            "麦克风 (Realtek(R) Audio)",
            "CABLE Input (VB-Audio Virtual C",
            INPUTS,
            ["CABLE In 16ch (VB-Audio Virtual", "扬声器 (Realtek(R) Audio)"],
        )
        self.assertEqual(inn, "麦克风 (Realtek(R) Audio)")
        self.assertEqual(out, "")
        self.assertTrue(any("output" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
