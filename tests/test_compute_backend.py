# -*- coding: utf-8 -*-
"""挑显卡这件事上，两条都出过事故，钉在这里。

一是「主显卡」的序号：早先那份候选列表是从注册表的显示适配器枚举里筛出来的，
里面混着已禁用的卡和残留的驱动键，下标跟 CUDA 的下标对不上。用户选了第二块，
`CUDA_VISIBLE_DEVICES` 就指向一个不存在的设备，CUDA 报 0 设备、`is_available()`
变 false，整台机器上的 N 卡等于全部消失。序号那一半在 Rust 侧（provision.rs 的
`parse_nvidia_smi` 和 worker.rs 的越界校验），这里管的是落地之后的另一半。

二是 DirectML 的设备选择：原来直接用 `default_device()`，永远是 0 号。装了串流、
VR、远程桌面的机器上，0 号常常是一块虚拟显示适配器 —— 没有独立显存，模型压上去
就是显存不足，或者直接访问违例把进程带走。
"""

import unittest

from configs.accel import (
    auto_use_dml,
    first_real_adapter,
    looks_like_nvidia,
    nvidia_names_from_env,
    nvidia_present_without_cuda,
)


class DirectMLAdapterPick(unittest.TestCase):
    def test_virtual_adapters_are_skipped(self):
        names = [
            "GameViewer Virtual Display Adapter",
            "Meta Virtual Monitor",
            "NVIDIA GeForce GTX 1050 Ti",
            "Virtual Desktop Monitor",
            "Microsoft Basic Display Adapter",
            "NVIDIA GeForce RTX 3060",
        ]
        self.assertEqual(first_real_adapter(names), 2)

    def test_a_real_card_at_zero_stays_at_zero(self):
        self.assertEqual(
            first_real_adapter(["AMD Radeon RX 7900 XTX", "Parsec Virtual Display Adapter"]),
            0,
        )

    def test_integrated_graphics_count_as_real(self):
        # 核显是 DirectML 路径的正经目标，别把它当虚拟适配器筛掉。
        for name in [
            "Intel(R) UHD Graphics 770",
            "Intel(R) Arc(TM) A770 Graphics",
            "AMD Radeon(TM) Graphics",
        ]:
            self.assertEqual(first_real_adapter([name]), 0, name)

    def test_all_virtual_returns_none(self):
        # 全是虚拟的时候得说「没有」，由调用方决定退回 0；不能随便挑一个当真卡。
        names = ["Microsoft Basic Render Driver", "Citrix Indirect Display Adapter"]
        self.assertIsNone(first_real_adapter(names))

    def test_empty_names_are_not_picked(self):
        # 名字读不出来时补的是空串，不能因为「空串里不含关键词」就把它当真卡。
        self.assertEqual(first_real_adapter(["", "NVIDIA GeForce RTX 3060"]), 1)
        self.assertIsNone(first_real_adapter(["", ""]))


class NvidiaWithoutCuda(unittest.TestCase):
    """diag 26.9.6 落了灰的歌单：P106 在、CUDA 不起，不能自动改走核显 DirectML。"""

    def test_p106_counts_as_nvidia(self):
        self.assertTrue(looks_like_nvidia("NVIDIA P106-100 (RainCandy Technology)"))
        self.assertFalse(looks_like_nvidia("Intel(R) HD Graphics 4600"))

    def test_env_split(self):
        self.assertEqual(
            nvidia_names_from_env({"TM_NVIDIA_GPUS": "NVIDIA P106-100 (RainCandy Technology)"}),
            ["NVIDIA P106-100 (RainCandy Technology)"],
        )
        self.assertEqual(nvidia_names_from_env({"TM_NVIDIA_GPUS": ""}), [])

    def test_present_without_cuda(self):
        names = ["NVIDIA P106-100 (RainCandy Technology)"]
        self.assertTrue(nvidia_present_without_cuda(False, names))
        self.assertFalse(nvidia_present_without_cuda(True, names))
        self.assertFalse(nvidia_present_without_cuda(False, ["Intel(R) HD Graphics 4600"]))

    def test_auto_dml_skips_when_nvidia_listed_but_cuda_down(self):
        nv = ["NVIDIA P106-100 (RainCandy Technology)"]
        self.assertFalse(auto_use_dml(False, 2, nv))
        self.assertTrue(auto_use_dml(False, 2, []))
        self.assertFalse(auto_use_dml(True, 2, nv))
        self.assertFalse(auto_use_dml(False, 0, []))


if __name__ == "__main__":
    unittest.main()
