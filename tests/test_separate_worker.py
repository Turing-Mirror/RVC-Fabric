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
        # tools 必须在最前：`import pymss` 才能对上 VR 的 alias_submodules。
        mod = _load_worker()
        saved = list(sys.path)
        try:
            sys.path[:] = [str(ROOT / "Runtime" / "python39.zip")] + _drop_product_paths(saved)
            mod.setup_sys_path()
            self.assertEqual(Path(sys.path[0]).resolve(), TOOLS.resolve())
            self.assertEqual(Path(sys.path[1]).resolve(), ROOT.resolve())
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

    def test_alias_submodules_accepts_the_tools_prefix(self):
        # 不 import pymss 包本身（会拉 torch）。只测名字改写。
        path = TOOLS / "pymss" / "modules" / "_core_shims.py"
        spec = importlib.util.spec_from_file_location("tm_pymss_shims", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        self.assertEqual(
            mod._as_pymss_module("tools.pymss.modules.vocal_remover.uvr_lib_v5"),
            "pymss.modules.vocal_remover.uvr_lib_v5",
        )
        self.assertEqual(
            mod._as_pymss_module("pymss.modules.vocal_remover.uvr_lib_v5"),
            "pymss.modules.vocal_remover.uvr_lib_v5",
        )

    def test_worker_imports_pymss_as_the_top_level_package(self):
        src = WORKER.read_text(encoding="utf-8")
        self.assertIn("from pymss.model_registry import create_separator", src)
        self.assertNotIn("from tools.pymss", src)

    def test_resolve_model_finds_a_flat_file_by_basename(self):
        # 权重如果没按 catalog relpath 摆（平铺在 model_dir），也不能判失踪。
        import tempfile

        reg = _load_registry()
        reg.load_model_catalog.cache_clear()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "4_HP-Vocal-UVR.pth").write_bytes(b"x")
            (root / "4_HP-Vocal-UVR.yaml").write_text("x", encoding="utf-8")
            resolved = reg.resolve_model(
                "4_HP-Vocal-UVR.pth",
                model_dir=root,
                require_supported=False,
                require_exists=True,
            )
            self.assertTrue(Path(resolved["model_path"]).is_file())
            self.assertEqual(Path(resolved["model_path"]).name, "4_HP-Vocal-UVR.pth")


class AllExtrasModelsTests(unittest.TestCase):
    """广场上架的每一份分离模型都要能解析，不能只认 HP3/HP4。"""

    def _extras_basenames(self):
        extras = ROOT / "CNB-GIT-RELEASE" / "catalog-src" / "extras"
        names = []
        if not extras.is_dir():
            self.skipTest("no catalog-src/extras on this clone")
        for p in extras.glob("pymss-*.yaml"):
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("- name:") or line.startswith("name:"):
                    rel = line.split(":", 1)[1].strip()
                    if rel.endswith(".pth"):
                        names.append(Path(rel.replace("\\", "/")).name)
        return names

    def test_every_extra_has_vr_metadata_and_param_json(self):
        names = self._extras_basenames()
        self.assertGreaterEqual(len(names), 20)
        path = TOOLS / "pymss" / "modules" / "vocal_remover" / "vr_models.py"
        spec = importlib.util.spec_from_file_location("tm_vr_models", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        pdir = TOOLS / "pymss_core" / "resources" / "vr_modelparams"
        for name in names:
            data = mod.get_vr_model_metadata(name)
            self.assertEqual(data["model_name"], name)
            param = data["vr_model_param"]
            self.assertTrue(
                (pdir / ("%s.json" % param)).is_file(),
                "%s -> %s.json missing" % (name, param),
            )
            # 换盘符 / 大小写也不能炸
            data2 = mod.get_vr_model_metadata("D:/models/" + name.upper())
            self.assertEqual(data2["vr_model_param"], param)

    def test_every_extra_is_in_the_pymss_catalog(self):
        reg = _load_registry()
        reg.load_model_catalog.cache_clear()
        for name in self._extras_basenames():
            entry = reg.get_model_entry(name)
            self.assertTrue(entry.relpath.replace("\\", "/").endswith(name))


if __name__ == "__main__":
    unittest.main()
