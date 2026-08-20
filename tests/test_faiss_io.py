# -*- coding: utf-8 -*-
"""中文路径必须正面拒绝，不能偷偷拷到临时目录再读。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infer.lib.faiss_io import (  # noqa: E402
    NonAsciiPathError,
    is_ascii_path,
    read_index,
    require_ascii_path,
)

NON_ASCII_INDEX = (
    r"D:\新建文件夹 (2)\RVC Fabric\User_Data\models\tp-alice"
    r"\added_IVF933_Flat_nprobe_1_TendouAlice_v2.index"
)


class _FakeFaiss:
    def __init__(self):
        self.calls = []
        self.result = object()

    def read_index(self, path):
        self.calls.append(path)
        return self.result


class RequireAsciiPathTests(unittest.TestCase):
    def test_ascii_is_ok(self):
        self.assertTrue(is_ascii_path(r"C:\RVCFabric\models\a.index"))
        require_ascii_path(r"C:\RVCFabric\models\a.index")

    def test_empty_is_ok(self):
        require_ascii_path("")
        require_ascii_path(None)  # type: ignore[arg-type]

    def test_chinese_dir_raises(self):
        with self.assertRaises(NonAsciiPathError) as cm:
            require_ascii_path(NON_ASCII_INDEX)
        msg = str(cm.exception)
        self.assertIn("中文", msg)
        self.assertIn("D:\\RVCFabric", msg)
        self.assertIn("新建文件夹", msg)


class ReadIndexTests(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("faiss", None)

    def test_ascii_path_reads(self):
        fake = _FakeFaiss()
        sys.modules["faiss"] = fake
        src = r"C:\Models\tp-alice\index.index"
        got = read_index(src)
        self.assertIs(got, fake.result)
        self.assertEqual(fake.calls, [src])

    def test_non_ascii_path_raises_without_copying(self):
        fake = _FakeFaiss()
        sys.modules["faiss"] = fake
        with self.assertRaises(NonAsciiPathError):
            read_index(NON_ASCII_INDEX)
        self.assertEqual(fake.calls, [])


if __name__ == "__main__":
    unittest.main()
