# -*- coding: utf-8 -*-
"""Unit tests for release variant pack matching (fake dirs + real RVCMAX)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_build_release():
    path = ROOT / "scripts" / "build_release.py"
    spec = importlib.util.spec_from_file_location("tm_build_release", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


br = _load_build_release()


def _fake_pack(root: Path, name: str) -> Path:
    p = root / name
    rt = p / "Runtime"
    rt.mkdir(parents=True)
    (rt / "python.exe").write_bytes(b"fake")
    return p


class PackDirMatchesTests(unittest.TestCase):
    def test_nvidia_excludes_50(self):
        self.assertTrue(
            br.pack_dir_matches(
                "RVCMAX_Nvidia_xiaoyuan",
                name_keys=("nvidia",),
                exclude_keys=("50", "50x0"),
            )
        )
        self.assertFalse(
            br.pack_dir_matches(
                "RVCMAX_Nvidia50x0_xiaoyuan",
                name_keys=("nvidia",),
                exclude_keys=("50", "50x0"),
            )
        )

    def test_nvidia50_keys(self):
        self.assertTrue(
            br.pack_dir_matches(
                "RVCMAX_Nvidia50x0_xiaoyuan",
                name_keys=("50", "50x0"),
                exclude_keys=(),
            )
        )

    def test_amd_keys(self):
        self.assertTrue(
            br.pack_dir_matches(
                "RVCMAX_AMD_xiaoyuan",
                name_keys=("amd", "dml"),
                exclude_keys=(),
            )
        )


class FindPackFakeTreeTests(unittest.TestCase):
    def test_prefer_and_exclude(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _fake_pack(root, "RVCMAX_Nvidia50x0_xiaoyuan")
            _fake_pack(root, "RVCMAX_Nvidia_xiaoyuan")
            _fake_pack(root, "RVCMAX_AMD_xiaoyuan")

            n = br.find_rvcmax_pack_dir(
                ("nvidia", "cuda"),
                "RVCMAX_Nvidia_xiaoyuan",
                exclude_keys=("50", "50x0", "5xxx"),
                rvcmax_root=root,
            )
            self.assertIsNotNone(n)
            self.assertEqual(n.name, "RVCMAX_Nvidia_xiaoyuan")

            # Without prefer_dir, exclude still avoids 50
            n2 = br.find_rvcmax_pack_dir(
                ("nvidia",),
                "",
                exclude_keys=("50", "50x0"),
                rvcmax_root=root,
            )
            self.assertIsNotNone(n2)
            self.assertEqual(n2.name, "RVCMAX_Nvidia_xiaoyuan")

            a = br.find_rvcmax_pack_dir(
                ("amd", "dml"),
                "RVCMAX_AMD_xiaoyuan",
                rvcmax_root=root,
            )
            self.assertEqual(a.name, "RVCMAX_AMD_xiaoyuan")

            s50 = br.find_rvcmax_pack_dir(
                ("50", "50x0"),
                "RVCMAX_Nvidia50x0_xiaoyuan",
                rvcmax_root=root,
            )
            self.assertEqual(s50.name, "RVCMAX_Nvidia50x0_xiaoyuan")

    def test_variant_prefer_dirs_configured(self):
        self.assertEqual(
            br.VARIANTS["nvidia"]["prefer_dir"], "RVCMAX_Nvidia_xiaoyuan"
        )
        self.assertEqual(br.VARIANTS["amd"]["prefer_dir"], "RVCMAX_AMD_xiaoyuan")
        self.assertEqual(
            br.VARIANTS["nvidia50"]["prefer_dir"], "RVCMAX_Nvidia50x0_xiaoyuan"
        )
        self.assertIn("50", br.VARIANTS["nvidia"]["exclude_keys"])


class FindPackRealRvcmaxTests(unittest.TestCase):
    """If local RVCMAX packs exist, assert correct resolution."""

    def test_real_packs_if_present(self):
        root = ROOT / "RVCMAX"
        if not root.is_dir():
            self.skipTest("no RVCMAX/")
        for variant, expect_sub in (
            ("nvidia", "Nvidia_xiaoyuan"),
            ("amd", "AMD"),
            ("nvidia50", "50"),
        ):
            pack = br.find_pack_for_variant(variant, rvcmax_root=root)
            if pack is None:
                self.skipTest(f"no pack for {variant}")
            self.assertIn(expect_sub.lower(), pack.name.lower())
            self.assertTrue((pack / "Runtime" / "python.exe").is_file())
            if variant == "nvidia":
                self.assertNotIn("50x0", pack.name.lower())
                self.assertNotIn("nvidia50", pack.name.lower())


if __name__ == "__main__":
    unittest.main()
