# -*- coding: utf-8 -*-
"""separate_worker path setup — Runtime python39._pth hides the script dir."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
WORKER = TOOLS / "separate_worker.py"


def _load_worker():
    spec = importlib.util.spec_from_file_location("tm_separate_worker", WORKER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _drop_product_paths(paths: list[str]) -> list[str]:
    drop = {ROOT.resolve(), TOOLS.resolve()}
    out = []
    for p in paths:
        try:
            if Path(p).resolve() in drop:
                continue
        except OSError:
            pass
        out.append(p)
    return out


class SetupPathTests(unittest.TestCase):
    def test_setup_puts_root_and_tools_on_path(self):
        # Isolated Runtime leaves sys.path as [python39.zip, Runtime, site-packages].
        # The worker must put both the product root (`tools.pymss`) and tools/
        # (`pymss_core`) on sys.path itself.
        mod = _load_worker()
        saved = list(sys.path)
        try:
            sys.path[:] = [str(ROOT / "Runtime" / "python39.zip")] + _drop_product_paths(saved)
            mod.setup_sys_path()
            self.assertEqual(Path(sys.path[0]).resolve(), ROOT.resolve())
            self.assertEqual(Path(sys.path[1]).resolve(), TOOLS.resolve())
        finally:
            sys.path[:] = saved

    def test_pymss_core_is_findable_after_setup(self):
        # Do not import the package: pymss_core.__init__ pulls torch.
        mod = _load_worker()
        saved = list(sys.path)
        try:
            sys.path[:] = [str(ROOT / "Runtime" / "python39.zip")] + _drop_product_paths(saved)
            self.assertIsNone(importlib.util.find_spec("pymss_core"))
            mod.setup_sys_path()
            spec = importlib.util.find_spec("pymss_core")
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.origin)
            self.assertTrue(
                Path(spec.origin).resolve().parent.samefile(TOOLS / "pymss_core")
            )
        finally:
            sys.path[:] = saved


if __name__ == "__main__":
    unittest.main()
