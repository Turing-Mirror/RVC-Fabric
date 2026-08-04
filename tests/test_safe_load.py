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

from infer.lib.safe_load import resolve_under_root, safe_model_path
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


if __name__ == "__main__":
    unittest.main()
