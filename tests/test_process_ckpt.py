# -*- coding: utf-8 -*-
"""savee 必须能把非 ASCII 的实验名落成权重文件。

26.8.20/4：实验名「诗歌剧」，200 轮训完，torch 的 PyTorchFileWriter 在
那台机器上打不开中文文件名，最终权重没落地 —— 界面只说「没找到 pth」，
用户以为整场白训。修复是先写 ASCII 临时名再 os.replace 过去。
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

try:
    import torch

    HAS_TORCH = True
except Exception:
    HAS_TORCH = False

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load():
    path = ROOT / "infer" / "lib" / "train" / "process_ckpt.py"
    spec = importlib.util.spec_from_file_location("tm_process_ckpt", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hps():
    return SimpleNamespace(
        data=SimpleNamespace(filter_length=1024, sampling_rate=48000),
        model=SimpleNamespace(
            inter_channels=1,
            hidden_channels=1,
            filter_channels=1,
            n_heads=1,
            n_layers=1,
            kernel_size=1,
            p_dropout=0.0,
            resblock=1,
            resblock_kernel_sizes=[1],
            resblock_dilation_sizes=[1],
            upsample_rates=[1],
            upsample_initial_channel=1,
            upsample_kernel_sizes=[1],
            spk_embed_dim=1,
            gin_channels=1,
        ),
    )


@unittest.skipUnless(HAS_TORCH, "process_ckpt imports torch")
class SaveeTests(unittest.TestCase):
    def test_non_ascii_name_lands_and_no_tmp_left_behind(self):
        mod = _load()
        ckpt = {"gen.0.weight": torch.zeros(1)}
        with tempfile.TemporaryDirectory() as td:
            old = os.getcwd()
            os.chdir(td)
            try:
                r = mod.savee(ckpt, "48k", 1, "诗歌剧", 200, "v2", _hps())
            finally:
                os.chdir(old)

            self.assertEqual(r, "Success.", r)
            weights = Path(td) / "assets" / "weights"
            self.assertTrue(
                (weights / "诗歌剧.pth").is_file(), "中文文件名的权重必须落地"
            )
            leftovers = list(weights.glob("_save_tmp_*"))
            self.assertEqual(leftovers, [], "临时文件不能留在 weights 里")

    def test_weights_dir_is_created_even_on_a_clean_tree(self):
        mod = _load()
        ckpt = {"gen.0.weight": torch.zeros(1)}
        with tempfile.TemporaryDirectory() as td:
            old = os.getcwd()
            os.chdir(td)
            try:
                r = mod.savee(ckpt, "48k", 1, "ascii-name", 10, "v2", _hps())
            finally:
                os.chdir(old)

            self.assertEqual(r, "Success.", r)
            self.assertTrue((Path(td) / "assets" / "weights" / "ascii-name.pth").is_file())


if __name__ == "__main__":
    unittest.main()
