# -*- coding: utf-8 -*-
"""F1 回归钉：显式 CPU 请求必须真的走 CPU。

- extract_f0_rmvpe_dml.py：cpu 时不许 import torch_directml（CPU 运行时没这个包）。
- extract_feature_print.py：device=="cpu" 时不许偷偷升回 cuda/mps。
- train_worker.stage_f0：非 cuda 的 rmvpe 必须把 device 传给子脚本。
"""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "infer" / "modules" / "train" / "extract"
TRAIN_DIR = ROOT / "infer" / "modules" / "train"


def _top_level_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


class TrainCpuRouteTest(unittest.TestCase):
    def test_cpu_rmvpe_never_needs_torch_directml(self):
        path = EXTRACT / "extract_f0_rmvpe_dml.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # 顶层不许出现无条件的 torch_directml import —— 只能活在
        # 非 cpu 分支里。
        self.assertNotIn(
            "torch_directml",
            _top_level_imports(path),
            "顶层 import torch_directml 会让纯 CPU 请求直接崩在 import 上",
        )
        src = path.read_text(encoding="utf-8")
        self.assertIn('== "cpu"', src, "必须认 argv 里的显式 cpu")
        self.assertIn(
            'sys.argv[2]', src, "device 要从命令行参数进来，不能写死 dml"
        )

    def test_feature_extract_honors_explicit_cpu(self):
        src = (TRAIN_DIR / "extract_feature_print.py").read_text(encoding="utf-8")
        self.assertIn(
            'if device != "cpu"',
            src,
            "显式 cpu 不能再被 torch.cuda.is_available() 偷偷升回 cuda",
        )

    def test_train_worker_passes_device_to_the_rmvpe_dml_script(self):
        src = (ROOT / "tools" / "train_worker.py").read_text(encoding="utf-8")
        i = src.index("extract_f0_rmvpe_dml.py")
        tail = src[i : i + 300]
        self.assertIn(
            'req["device"]',
            tail,
            "stage_f0 的非 cuda rmvpe 分支必须把 device 递给子脚本",
        )


if __name__ == "__main__":
    unittest.main()
