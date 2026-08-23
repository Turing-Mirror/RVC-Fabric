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

import ast
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


class HotPathSurvivesStopStream(unittest.TestCase):
    """非 N 卡上热路径必须真的接得上——它以前是死的。

    `gui_v1.stop_stream` 在 `torch.cuda.is_available()` 为假时会把 self.rvc /
    resampler / tg 一并置空：DML 没有 empty_cache，只能靠 del + gc 把显存还回去。
    而 `_worker_convert` 以前是先停流、再去取常驻模型，于是 A / I 卡上顺序注定
    是「先清空、后来取」，`_sts_resident_vc` 永远看见 rvc is None，永远报「实时
    引擎里没有已加载的音色」退回冷路径。

    后果有两层：热路径省下的那二十几秒在这些机器上从来没生效过；而且「先开实时
    变声再做文件转换」这个绕过 DirectML 缺陷的办法在 A 卡上根本不成立——用户
    照做了还是失败（26.8.20 反馈）。

    这条测试只钉顺序：取常驻模型必须发生在停流之前。跑 gui_v1 需要 torch /
    sounddevice，装不上，所以按 AST 读源码（tests/test_dsp_voice.py 也是这么干的）。
    """

    def _worker_convert_body(self):
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.FunctionDef) and node.name == "_worker_convert":
                return node
        self.fail("gui_v1 里找不到 _worker_convert")

    def _first_line(self, node, predicate):
        hits = [n.lineno for n in ast.walk(node) if predicate(n)]
        return min(hits) if hits else None

    def test_resident_model_is_taken_before_the_stream_stops(self):
        fn = self._worker_convert_body()

        def is_call_to(name):
            def check(n):
                return (
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == name
                )

            return check

        resident = self._first_line(fn, is_call_to("_sts_resident_vc"))
        stop = self._first_line(fn, is_call_to("stop_stream"))
        self.assertIsNotNone(resident, "_worker_convert 没取常驻模型")
        self.assertIsNotNone(stop, "_worker_convert 没停实时流")
        self.assertLess(
            resident,
            stop,
            "stop_stream 在非 N 卡上会清掉 self.rvc，必须等常驻模型取到手之后再停",
        )


class CrepeDevice(unittest.TestCase):
    def test_dml_falls_back_to_cpu(self):
        self.assertEqual(dml_compat.crepe_device("privateuseone:0"), "cpu")

    def test_other_devices_stay(self):
        self.assertEqual(dml_compat.crepe_device("cuda:0"), "cuda:0")
        self.assertEqual(dml_compat.crepe_device("cpu"), "cpu")


class StsWorkerPatches(unittest.TestCase):
    """语音转换冷路径走 sts_worker，必须自己打补丁、自己留 CPU 兜底。

    26.8.22/4：Intel Iris Xe、DirectML、1.5.4。用户没开实时变声（热路径
    rvc is None 是常态），四次「开始转换」全进冷路径，全挂 GradMultiply
    PrivateUse1。load_hubert 里那份补丁是对的，但冷路径入口漏打 —— 跟
    26.8.21 TTS 走 infer_cli 是同一类漏。规则：新的冷路径入口必须显式接
    dml_compat，不能只靠下游某层顺手打一下。
    """

    def _main_body(self):
        """找到「装模型」的那个函数 —— 按行为找，不按名字找。

        这条守卫钉的是「建 VC 之前必须先 apply_for」。以前它写死了函数名
        main，装模型的代码一挪到别的函数里，守卫就悄悄变成永远通过。改成
        认「谁调了 VC(...)」，重构挪窝也拦得住。
        """
        src = (ROOT / "tools" / "sts_worker.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id == "VC"
                ):
                    return node, src
        self.fail("tools/sts_worker.py 里找不到建 VC 的函数")

    def test_applies_dml_compat_before_loading_models(self):
        fn, src = self._main_body()
        self.assertIn("apply_for", src)
        apply_line = None
        vc_line = None
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name == "apply_for" and apply_line is None:
                    apply_line = node.lineno
                if name == "VC" and vc_line is None:
                    vc_line = node.lineno
        self.assertIsNotNone(apply_line, "装模型的函数里没调 apply_for")
        self.assertIsNotNone(vc_line, "装模型的函数里没建 VC")
        self.assertLess(apply_line, vc_line, "apply_for 必须在加载模型之前")

    def test_keeps_cpu_fallback_on(self):
        # 冷路径走 run_batch，默认 allow_cpu_fallback=True。热路径才需要关掉。
        # 这里钉的是「别把开关带 False 传进去」——带了就等于 A/I 卡再撞算子
        # 缺口时整批陪葬，26.8.22/4 就会原样重演。
        _fn, src = self._main_body()
        self.assertIn("run_batch", src)
        self.assertNotIn("allow_cpu_fallback=False", src)
        self.assertNotIn("allow_cpu_fallback = False", src)


class TtsInferCliPatches(unittest.TestCase):
    """文字合成第二步走 infer_cli，必须自己打补丁、自己接 CPU 兜底。

    26.8.21 用户日志：SAPI 成功写出 tts_raw.wav，随后 infer_cli 在 hubert
    GradMultiply 上抛 PrivateUse1，整次换音色失败。这条 CLI 不经过
    sts_worker，load_hubert 的补丁不够——还得在 Config 之后显式 apply_for，
    并且撞上别的 DirectML 缺口时能退 CPU（跟 STS 批量同一份函数）。
    """

    def _main_body(self):
        src = (ROOT / "tools" / "infer_cli.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                return node, src
        self.fail("tools/infer_cli.py 里找不到 main")

    def test_applies_dml_compat_before_loading_models(self):
        fn, src = self._main_body()
        self.assertIn("apply_for", src)
        # apply_for 必须出现在 VC(config) / get_vc 之前。
        apply_line = None
        vc_line = None
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name == "apply_for" and apply_line is None:
                    apply_line = node.lineno
                if name == "VC" and vc_line is None:
                    vc_line = node.lineno
        self.assertIsNotNone(apply_line, "infer_cli.main 没调 apply_for")
        self.assertIsNotNone(vc_line, "infer_cli.main 没建 VC")
        self.assertLess(apply_line, vc_line, "apply_for 必须在加载模型之前")

    def test_uses_shared_cpu_fallback(self):
        _fn, src = self._main_body()
        self.assertIn("convert_one_with_cpu_fallback", src)
        self.assertIn("friendly_error", src)


if __name__ == "__main__":
    unittest.main()
