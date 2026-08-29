# -*- coding: utf-8 -*-
"""faiss 索引读写对中文路径也要能用。

以前的做法是正面拒绝：faiss 的 C++ fopen 打不开非 ASCII 路径，那就让用户
把音色搬去纯英文目录。26.8.29/103223 的用户音色叫「伊蕾娜」，检索库明明
是空的，也被这条守卫挡在开启变声之外。现在的做法是解除限制：Python 自己
读字节，交给 faiss.deserialize_index —— 索引文件本来就是一段序列化字节。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infer.lib import faiss_io  # noqa: E402
from infer.lib.faiss_io import is_ascii_path, read_index, write_index  # noqa: E402

NON_ASCII_DIR_NAME = "新建文件夹(2)"
NON_ASCII_INDEX = (
    rf"C:\{NON_ASCII_DIR_NAME}\RVC Fabric\User_Data\models\伊蕾娜"
    r"\added_IVF933_Flat_nprobe_1.index"
)


class _FakeFaiss:
    """记录调用、按需要返回固定结果的 faiss 替身。"""

    def __init__(self, result=None, serialized=b"serialized-bytes"):
        self.calls = []
        self.result = result if result is not None else object()
        self.serialized = serialized

    def read_index(self, path):
        self.calls.append(("read_index", path))
        return self.result

    def write_index(self, index, path):
        self.calls.append(("write_index", index, path))

    def deserialize_index(self, array):
        self.calls.append(("deserialize_index", array.tobytes()))
        return self.result

    def serialize_index(self, index):
        self.calls.append(("serialize_index", index))
        import numpy as np

        return np.frombuffer(self.serialized, dtype=np.uint8)


class IsAsciiPathTests(unittest.TestCase):
    def test_ascii_is_ok(self):
        self.assertTrue(is_ascii_path(r"C:\RVCFabric\models\a.index"))

    def test_chinese_dir_is_not(self):
        self.assertFalse(is_ascii_path(NON_ASCII_INDEX))

    def test_empty_is_ascii(self):
        self.assertTrue(is_ascii_path(""))


class ReadIndexTests(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("faiss", None)

    def test_ascii_path_reads_via_faiss(self):
        fake = _FakeFaiss()
        sys.modules["faiss"] = fake
        src = r"C:\Models\tp-alice\index.index"
        got = read_index(src)
        self.assertIs(got, fake.result)
        self.assertEqual(fake.calls, [("read_index", src)])

    def test_non_ascii_path_reads_bytes(self):
        fake = _FakeFaiss()
        sys.modules["faiss"] = fake
        with tempfile.TemporaryDirectory(prefix=NON_ASCII_DIR_NAME) as tmp:
            src = Path(tmp) / "伊蕾娜.index"
            src.write_bytes(b"faiss-index-bytes")
            got = read_index(str(src))
        self.assertIs(got, fake.result)
        self.assertEqual(
            fake.calls, [("deserialize_index", b"faiss-index-bytes")]
        )

    def test_missing_non_ascii_file_raises_filenotfound(self):
        fake = _FakeFaiss()
        sys.modules["faiss"] = fake
        with tempfile.TemporaryDirectory(prefix=NON_ASCII_DIR_NAME) as tmp:
            src = Path(tmp) / "不存在.index"
            with self.assertRaises(FileNotFoundError):
                read_index(str(src))


class WriteIndexTests(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("faiss", None)

    def test_ascii_path_writes_via_faiss(self):
        fake = _FakeFaiss()
        sys.modules["faiss"] = fake
        index = object()
        dst = r"C:\Models\tp-alice\added.index"
        write_index(index, dst)
        self.assertEqual(fake.calls, [("write_index", index, dst)])

    def test_non_ascii_path_writes_serialized_bytes(self):
        fake = _FakeFaiss(serialized=b"index-payload")
        sys.modules["faiss"] = fake
        index = object()
        with tempfile.TemporaryDirectory(prefix=NON_ASCII_DIR_NAME) as tmp:
            dst = Path(tmp) / "伊蕾娜.index"
            write_index(index, str(dst))
            self.assertEqual(dst.read_bytes(), b"index-payload")
        self.assertEqual(fake.calls[0], ("serialize_index", index))


class RealFaissRoundtripTests(unittest.TestCase):
    """装了真 faiss 才跑：中文目录里写出去再读回来，索引得能查。"""

    def setUp(self):
        try:
            import faiss  # noqa: F401

            self.faiss = faiss
        except ImportError:
            self.skipTest("faiss not installed on this interpreter")

    def test_roundtrip_in_chinese_dir(self):
        import numpy as np

        with tempfile.TemporaryDirectory(prefix=NON_ASCII_DIR_NAME) as tmp:
            dst = Path(tmp) / "伊蕾娜.index"
            xs = np.random.RandomState(7).rand(64, 16).astype("float32")
            index = self.faiss.IndexFlatL2(16)
            index.add(xs)
            write_index(index, str(dst))
            got = read_index(str(dst))
            self.assertEqual(got.ntotal, 64)
            _, hit = got.search(xs[:1], 1)
            self.assertEqual(int(hit[0][0]), 0)


if __name__ == "__main__":
    unittest.main()
