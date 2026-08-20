# -*- coding: utf-8 -*-
"""A / I 卡（DirectML）上那两个必炸的点，钉在这里。

26.8.20 的用户诊断包：AMD 核显、DirectML 后端，8 次「语音转换」全部失败。前 4 次
是已修的 version_counter，升到 1.5.4 之后错误后移到 hubert：

    fairseq/modules/grad_multiply.py:13  res = x.new(x)
    RuntimeError: new(): expected key in DispatchKeySet(CPU, CUDA, ...)
                  but got: PrivateUse1

补丁本身早就写了，但只打在实时（rtrvc）和训练（extract_feature_print）两条路上，
离线文件转换用的 ``load_hubert`` 一直没打——A 卡上这个功能等于从来没通过，只有
实时引擎正开着、转换复用常驻进程的热路径才碰巧是好的。

用户换 crepe 想绕开，撞上第二个：torchcrepe 装权重是
``torch.load(map_location=device)``，torch 反序列化不认 privateuseone。

这里不需要 torch / fairseq：补丁函数只认「有 GradMultiply 的模块」，拿替身喂。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infer.lib import dml_compat  # noqa: E402


class FakeTensor:
    """只认得 clone / detach，够 GradMultiply 用。"""

    def __init__(self, tag="x"):
        self.tag = tag
        self.cloned = False
        self.detached = False

    def clone(self):
        out = FakeTensor(self.tag)
        out.cloned = True
        return out

    def detach(self):
        self.detached = True
        return self

    def new(self, _x):  # DirectML 上就是这一句抛 PrivateUse1
        raise RuntimeError(
            "new(): expected key in DispatchKeySet(CPU, CUDA, HIP, XLA, MPS, "
            "IPU, XPU, HPU, Lazy, Meta) but got: PrivateUse1"
        )


def fake_fairseq():
    """一份最小的 fairseq 替身，forward 还是官方那个会炸的写法。"""

    class GradMultiply:
        @staticmethod
        def forward(ctx, x, scale):
            ctx.scale = scale
            return x.new(x)

    grad_multiply = SimpleNamespace(GradMultiply=GradMultiply)
    modules = SimpleNamespace(grad_multiply=grad_multiply)
    return SimpleNamespace(modules=modules)


class DeviceDetection(unittest.TestCase):
    def test_privateuseone_is_dml(self):
        self.assertTrue(dml_compat.is_dml_device("privateuseone:0"))
        self.assertTrue(dml_compat.is_dml_device("PrivateUseOne:1"))

    def test_other_devices_are_not(self):
        for dev in ("cpu", "cuda:0", "mps", "", None):
            self.assertFalse(dml_compat.is_dml_device(dev), dev)

    def test_config_flag_wins(self):
        self.assertTrue(dml_compat.wants_dml(SimpleNamespace(dml=True, device="cpu")))

    def test_device_string_is_the_fallback(self):
        # DirectML 起不来时 config 会把设备退回 cpu，但也有调用方只传得出设备。
        self.assertTrue(
            dml_compat.wants_dml(SimpleNamespace(dml=False, device="privateuseone:0"))
        )

    def test_nvidia_config_is_left_alone(self):
        self.assertFalse(dml_compat.wants_dml(SimpleNamespace(dml=False, device="cuda:0")))
        self.assertFalse(dml_compat.wants_dml(None))


class GradMultiplyPatch(unittest.TestCase):
    def test_unpatched_forward_blows_up(self):
        # 替身得真能复现那条报错，否则下面的测试什么都没证明。
        fq = fake_fairseq()
        with self.assertRaises(RuntimeError) as caught:
            fq.modules.grad_multiply.GradMultiply.forward(SimpleNamespace(), FakeTensor(), 0.1)
        self.assertIn("PrivateUse1", str(caught.exception))

    def test_patched_forward_returns_a_detached_clone(self):
        fq = fake_fairseq()
        self.assertTrue(dml_compat.patch_fairseq_grad_multiply(fq))
        ctx = SimpleNamespace()
        out = fq.modules.grad_multiply.GradMultiply.forward(ctx, FakeTensor("feat"), 0.1)
        self.assertEqual(ctx.scale, 0.1)
        self.assertEqual(out.tag, "feat")
        self.assertTrue(out.cloned)
        self.assertTrue(out.detached)

    def test_patch_is_idempotent(self):
        fq = fake_fairseq()
        dml_compat.patch_fairseq_grad_multiply(fq)
        first = fq.modules.grad_multiply.GradMultiply.forward
        self.assertTrue(dml_compat.patch_fairseq_grad_multiply(fq))
        self.assertIs(fq.modules.grad_multiply.GradMultiply.forward, first)

    def test_missing_fairseq_structure_does_not_raise(self):
        self.assertFalse(dml_compat.patch_fairseq_grad_multiply(SimpleNamespace()))

    def test_apply_for_skips_non_dml(self):
        fq = fake_fairseq()
        before = fq.modules.grad_multiply.GradMultiply.forward
        self.assertFalse(
            dml_compat.apply_for(SimpleNamespace(dml=False, device="cuda:0"), fairseq_module=fq)
        )
        self.assertIs(fq.modules.grad_multiply.GradMultiply.forward, before)

    def test_apply_for_patches_dml(self):
        fq = fake_fairseq()
        self.assertTrue(
            dml_compat.apply_for(
                SimpleNamespace(dml=True, device="privateuseone:0"), fairseq_module=fq
            )
        )
        self.assertIsNot(
            fq.modules.grad_multiply.GradMultiply.forward, fake_fairseq().modules.grad_multiply.GradMultiply.forward
        )


class OfflineLoadHubertPatches(unittest.TestCase):
    """离线转换这条路必须自己打补丁——漏的就是它。"""

    def setUp(self):
        self.fake = fake_fairseq()
        self.fake.checkpoint_utils = SimpleNamespace(
            load_model_ensemble_and_task=lambda *a, **k: ([], None, None)
        )
        self._saved = sys.modules.get("fairseq")
        sys.modules["fairseq"] = self.fake

    def tearDown(self):
        if self._saved is None:
            sys.modules.pop("fairseq", None)
        else:
            sys.modules["fairseq"] = self._saved

    def _load(self, config):
        from infer.modules.vc.utils import load_hubert

        # 补丁必须在读权重之前打上，所以这里不需要真的有 hubert_base.pt：
        # 找不到文件时抛 FileNotFoundError，补丁却应该已经在了。
        try:
            load_hubert(config)
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def test_dml_config_gets_the_patch_before_loading(self):
        self._load(SimpleNamespace(dml=True, device="privateuseone:0", is_half=False))
        ctx = SimpleNamespace()
        out = self.fake.modules.grad_multiply.GradMultiply.forward(ctx, FakeTensor(), 0.1)
        self.assertTrue(out.detached)  # 没打补丁的话上面这句会抛 PrivateUse1

    def test_cuda_config_is_left_alone(self):
        self._load(SimpleNamespace(dml=False, device="cuda:0", is_half=True))
        with self.assertRaises(RuntimeError):
            self.fake.modules.grad_multiply.GradMultiply.forward(
                SimpleNamespace(), FakeTensor(), 0.1
            )


class CrepeDevice(unittest.TestCase):
    def test_dml_falls_back_to_cpu(self):
        self.assertEqual(dml_compat.crepe_device("privateuseone:0"), "cpu")

    def test_other_devices_stay(self):
        self.assertEqual(dml_compat.crepe_device("cuda:0"), "cuda:0")
        self.assertEqual(dml_compat.crepe_device("cpu"), "cpu")


if __name__ == "__main__":
    unittest.main()
