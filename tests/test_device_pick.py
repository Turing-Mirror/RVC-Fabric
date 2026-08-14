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


if __name__ == "__main__":
    unittest.main()
