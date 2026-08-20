"""Unit tests for path safety and CLI helpers (no GPU / model weights required)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infer.lib.safe_load import (
    check_voice_ckpt,
    resolve_under_root,
    safe_model_path,
    safe_torch_load,
)
from infer.modules.vc.utils import get_index_path_from_model


def str2bool(value):
    """Mirror tools.infer_cli.str2bool without importing heavy CLI deps."""
    if isinstance(value, bool):
        return value
    v = str(value).strip().lower()
    if v in ("1", "true", "t", "yes", "y", "on"):
        return True
    if v in ("0", "false", "f", "no", "n", "off"):
        return False
    raise ValueError(f"expected a boolean, got {value!r}")


class ResolveUnderRootTests(unittest.TestCase):
    def test_basename_under_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "voice.pth").write_bytes(b"x")
            p = resolve_under_root(root, "voice.pth")
            self.assertEqual(p, (root / "voice.pth").resolve())

    def test_blocks_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "weights"
            root.mkdir()
            # Even with ../, only the basename is accepted under root
            p = resolve_under_root(root, "../../etc/passwd")
            self.assertEqual(p.name, "passwd")
            self.assertTrue(str(p).startswith(str(root.resolve())))

    def test_rejects_empty(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                resolve_under_root(td, "")
            with self.assertRaises(ValueError):
                resolve_under_root(td, "..")


class SafeModelPathTests(unittest.TestCase):
    def test_uses_weight_root(self):
        with tempfile.TemporaryDirectory() as td:
            path = safe_model_path(td, "a.pth")
            self.assertTrue(path.endswith("a.pth"))
            self.assertTrue(path.startswith(str(Path(td).resolve())))

    def test_empty_sid(self):
        with self.assertRaises(ValueError):
            safe_model_path("weights", "  ")


class Str2BoolTests(unittest.TestCase):
    def test_truthy(self):
        for v in ("true", "True", "1", "yes", "on"):
            self.assertTrue(str2bool(v))

    def test_falsey(self):
        for v in ("false", "False", "0", "no", "off"):
            self.assertFalse(str2bool(v))

    def test_invalid(self):
        with self.assertRaises(ValueError):
            str2bool("maybe")


class SafeTorchLoadFallbackTests(unittest.TestCase):
    """nvidia50 Runtime is PyTorch 2.6: weights_only=True rejects legacy tar."""

    def test_legacy_tar_error_falls_back(self):
        import sys
        import types

        calls = []

        def fake_load(path, map_location="cpu", weights_only=None):
            calls.append(weights_only)
            if weights_only is True:
                raise RuntimeError(
                    "Cannot use ``weights_only=True`` with files saved in "
                    "the legacy .tar format. In PyTorch 2.6, we changed the "
                    "default value of the `weights_only` argument."
                )
            return {"ok": True}

        fake_mod = types.ModuleType("torch")
        fake_mod.load = fake_load
        prev = sys.modules.get("torch")
        sys.modules["torch"] = fake_mod
        try:
            with tempfile.TemporaryDirectory() as td:
                path = Path(td) / "rmvpe.pt"
                path.write_bytes(b"not-a-real-checkpoint")
                got = safe_torch_load(path, map_location="cpu")
        finally:
            if prev is None:
                sys.modules.pop("torch", None)
            else:
                sys.modules["torch"] = prev
        self.assertEqual(got, {"ok": True})
        self.assertEqual(calls, [True, False])


class RmvpeLoadWiringTests(unittest.TestCase):
    def test_rmvpe_uses_safe_torch_load(self):
        src = (ROOT / "infer" / "lib" / "rmvpe.py").read_text(encoding="utf-8")
        self.assertIn("safe_torch_load", src)
        self.assertNotIn("torch.load(model_path", src)
        jit_src = (ROOT / "infer" / "lib" / "jit" / "get_rmvpe.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("safe_torch_load", jit_src)
        self.assertNotIn("torch.load(model_path", jit_src)

    def test_start_vc_does_not_swallow_warmup(self):
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        start = src[src.index("def start_vc") : src.index("def _on_rvc_progress")]
        warm = start.index("self._warmup_engine()")
        stream = start.index("self.start_stream()")
        between = start[warm:stream]
        self.assertNotIn("except Exception", between)


class GetIndexPathFromModelTests(unittest.TestCase):
    """STS/offline load used to crash when index_root env was missing."""

    def test_none_index_root_returns_empty(self):
        old = os.environ.pop("index_root", None)
        try:
            self.assertEqual(get_index_path_from_model("Anon-local.pth"), "")
            self.assertEqual(
                get_index_path_from_model(r"F:\RVC\User_Data\models\Anon\Anon-local.pth"),
                "",
            )
        finally:
            if old is not None:
                os.environ["index_root"] = old

    def test_missing_dir_returns_empty(self):
        os.environ["index_root"] = r"Z:\does\not\exist\index_root_test"
        try:
            self.assertEqual(get_index_path_from_model("foo.pth"), "")
        finally:
            os.environ.pop("index_root", None)

    def test_matches_stem_under_index_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nested = root / "exp" / "Anon"
            nested.mkdir(parents=True)
            idx = nested / "added_IVF_Anon-local.index"
            idx.write_bytes(b"x")
            os.environ["index_root"] = str(root)
            try:
                found = get_index_path_from_model(
                    r"F:\models\Anon\Anon-local.pth"
                )
                self.assertEqual(Path(found).resolve(), idx.resolve())
            finally:
                os.environ.pop("index_root", None)


class VoiceCkptShapeTests(unittest.TestCase):
    """选错 .pth 时说人话。

    音色模型是 {"weight": ..., "config": [...]}，训练存档是 {"model": ...,
    "optimizer": ..., "iteration": ...}。两者都叫 .pth，用户分不出来很正常。
    以前直接 cpt["config"][-1]，选错就收到「加载模型失败：'config'」——既没说
    错在哪也没说怎么办（26.8.20 用户诊断包里连着四次栽在同一个 G_35200.pth）。
    """

    def test_a_real_voice_model_passes(self):
        check_voice_ckpt({"weight": {}, "config": [1, 2, 3], "f0": 1}, "voice.pth")

    def test_a_training_checkpoint_says_so_and_points_somewhere(self):
        cpt = {"model": {}, "optimizer": {}, "iteration": 35200, "learning_rate": 1e-4}
        with self.assertRaises(RuntimeError) as caught:
            check_voice_ckpt(cpt, r"D:\models\G_35200\G_35200.pth")
        msg = str(caught.exception)
        self.assertIn("G_35200.pth", msg)
        self.assertIn("训练", msg)
        self.assertIn("模型提取", msg)  # 得告诉用户上哪儿去转

    def test_some_other_pth_says_what_is_missing(self):
        with self.assertRaises(RuntimeError) as caught:
            check_voice_ckpt({"state_dict": {}}, "hubert_base.pt")
        self.assertIn("weight", str(caught.exception))

    def test_not_even_a_dict(self):
        with self.assertRaises(RuntimeError):
            check_voice_ckpt([1, 2, 3], "weird.pth")

    def test_no_path_still_reads_ok(self):
        with self.assertRaises(RuntimeError) as caught:
            check_voice_ckpt({"model": {}})
        self.assertIn("所选文件", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
