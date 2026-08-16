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


def _load_registry():
    # 不要 ``import tools.pymss``：包的 __init__ 会拉 torch。
    path = TOOLS / "pymss" / "model_registry.py"
    spec = importlib.util.spec_from_file_location("tm_pymss_model_registry", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class CatalogLoadTests(unittest.TestCase):
    """26.8.16：Runtime 3.9 上 resources.files('pymss.resources') 读清单炸了。"""

    def test_catalog_loads_from_the_vendored_file(self):
        reg = _load_registry()
        reg.load_model_catalog.cache_clear()
        catalog = reg._resource_file("model_catalog.json")
        self.assertTrue(catalog.is_file(), catalog)
        data = reg.load_model_catalog()
        names = {m.name for m in data["models"]}
        self.assertIn("4_HP-Vocal-UVR.pth", names)
        entry = reg.get_model_entry("4_HP-Vocal-UVR.pth")
        self.assertTrue(entry.relpath.endswith("4_HP-Vocal-UVR.pth"))

    def test_catalog_loader_does_not_import_importlib_resources(self):
        src = (TOOLS / "pymss" / "model_registry.py").read_text(encoding="utf-8")
        self.assertNotIn("from importlib", src)
        self.assertNotIn("import importlib", src)

    def test_vr_params_live_on_disk(self):
        # 人声提取那几个 UVR 模型下一步会读这份 json。路径必须是真目录。
        core = TOOLS / "pymss_core" / "resources" / "vr_modelparams"
        local = TOOLS / "pymss" / "resources" / "vr_modelparams"
        self.assertTrue(core.is_dir() or local.is_dir())
        found = core if core.is_dir() else local
        self.assertTrue(
            any(found.glob("*.json")),
            "vr_modelparams has no json files",
        )

    def test_vr_separator_does_not_use_importlib_resources(self):
        src = (
            TOOLS / "pymss" / "modules" / "vocal_remover" / "vr_separator.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("from importlib.resources", src)


if __name__ == "__main__":
    unittest.main()
