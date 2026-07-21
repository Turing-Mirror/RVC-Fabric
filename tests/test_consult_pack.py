# -*- coding: utf-8 -*-
"""launcher.consult_pack — consult zip assembly (no torch / no Tk)."""

from __future__ import annotations

import json
import os
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher import profiles as P
from launcher.consult_pack import (
    ConsultPackError,
    build_model_meta,
    fabric_match_reasons,
    has_fabric_publisher_mark,
    is_fabric_model,
    pack_consult_zip,
    resolve_profile,
)


def _write(path, data: bytes = b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _make_model(tmp: Path, *, fabric: bool, with_index: bool = False, active_profile: bool = False):
    root = tmp / "pkg"
    mdir = root / "User_Data" / "models" / "hero"
    mdir.mkdir(parents=True)
    _write(str(mdir / "hero.pth"), b"PTH" * 100)
    if with_index:
        _write(str(mdir / "hero.index"), b"IDX" * 50)
    side = {
        "name": "HeroVoice",
        "file": "hero.pth",
        "tag": "角色",
        "pitch": 3,
        "formant": 0.1,
        "source": "online_pack" if fabric else "user_import",
    }
    if fabric:
        side["online_id"] = "hero_v1"
    if with_index:
        side["index"] = str(mdir / "hero.index")
    (mdir / "config.json").write_text(
        json.dumps(side, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if active_profile:
        prof = P.make_profile(
            "测试档案",
            voice={"pitch": 7, "f0method": "rmvpe"},
            fx={"fx_enabled": True},
            perf={"block_time": 0.22},
            source="self",
            for_model="HeroVoice",
        )
        P.save_profile(str(mdir), prof)
        P.set_active_profile_id(str(mdir), prof["id"])
    dry = root / "dry.wav"
    wet = root / "wet.wav"
    dry.write_bytes(b"RIFF" + b"\0" * 64)
    wet.write_bytes(b"RIFF" + b"\0" * 80)
    return str(root), str(mdir), str(dry), str(wet)


class ConsultPackTests(unittest.TestCase):
    def test_is_fabric_model(self):
        self.assertTrue(is_fabric_model({"online_id": "x"}))
        self.assertTrue(is_fabric_model({"source": "online_pack"}))
        self.assertTrue(is_fabric_model({"source": "online_files"}))
        self.assertTrue(is_fabric_model({"publisher": "rvc_fabric"}))
        self.assertTrue(is_fabric_model({"fabric_official": True}))
        self.assertTrue(
            is_fabric_model(
                {"online_id": "kiki"}, catalog_ids={"kiki", "guanguan"}
            )
        )
        self.assertIn(
            "catalog_id_match",
            fabric_match_reasons(
                {"online_id": "kiki"}, catalog_ids={"kiki"}
            ),
        )
        self.assertTrue(has_fabric_publisher_mark({"publisher": "RVC-Fabric"}))
        self.assertFalse(is_fabric_model({"source": "user_import"}))
        self.assertFalse(is_fabric_model({}))
        self.assertFalse(is_fabric_model(None))

    def test_build_model_meta_fabric(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root, mdir, _, _ = _make_model(Path(td), fabric=True, with_index=True)
            meta = build_model_meta(mdir)
            self.assertTrue(meta["is_fabric_catalog"])
            self.assertEqual(meta["online_id"], "hero_v1")
            self.assertEqual(meta["file"], "hero.pth")
            self.assertEqual(meta["index_file"], "hero.index")
            self.assertTrue(meta.get("fabric_match"))

    def test_resolve_profile_active_vs_snapshot(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _, mdir, _, _ = _make_model(base / "a", fabric=False, active_profile=True)
            prof, tag = resolve_profile(mdir, {"pitch": 1})
            self.assertEqual(tag, "active")
            self.assertEqual(prof["voice"].get("pitch"), 7)

            _, mdir2, _, _ = _make_model(base / "b", fabric=False, active_profile=False)
            prof2, tag2 = resolve_profile(
                mdir2, {"pitch": 5, "f0method": "fcpe"}, character_name="角色A"
            )
            self.assertEqual(tag2, "snapshot")
            self.assertEqual(prof2["voice"].get("pitch"), 5)
            self.assertIn("咨询快照", prof2["name"])

    def test_pack_fabric_without_models(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root, mdir, dry, wet = _make_model(Path(td), fabric=True, with_index=True)
            zpath = pack_consult_zip(
                root,
                model_dir=mdir,
                character_name="测试角色",
                dry_path=dry,
                wet_path=wet,
                include_model_files=False,
                notes="hello",
                app_version="1.1.0",
            )
            self.assertTrue(os.path.isfile(zpath))
            with zipfile.ZipFile(zpath) as zf:
                names = set(zf.namelist())
                self.assertIn("manifest.json", names)
                self.assertIn("env.json", names)
                self.assertIn("profile.tmvp", names)
                self.assertIn("model_meta.json", names)
                self.assertIn("README.txt", names)
                self.assertIn("samples/dry_original.wav", names)
                self.assertIn("samples/wet_converted.wav", names)
                self.assertFalse(any(n.startswith("models/") for n in names))
                man = json.loads(zf.read("manifest.json"))
            self.assertEqual(man["kind"], "consult_pack")
            self.assertEqual(man["character_name"], "测试角色")
            self.assertEqual(man["model"]["online_id"], "hero_v1")
            self.assertTrue(man["model"]["is_fabric_catalog"])
            self.assertFalse(man["include_model_files"])
            self.assertEqual(man["notes"], "hello")

    def test_pack_user_with_model_files(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root, mdir, dry, wet = _make_model(Path(td), fabric=False, with_index=True)
            zpath = pack_consult_zip(
                root,
                model_dir=mdir,
                character_name="自备",
                dry_path=dry,
                wet_path=wet,
                include_model_files=True,
            )
            with zipfile.ZipFile(zpath) as zf:
                names = set(zf.namelist())
                self.assertIn("models/hero.pth", names)
                self.assertIn("models/hero.index", names)
                man = json.loads(zf.read("manifest.json"))
            self.assertTrue(man["include_model_files"])
            self.assertFalse(man["model"]["is_fabric_catalog"])

    def test_pack_missing_dry_raises(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root, mdir, dry, wet = _make_model(Path(td), fabric=False)
            with self.assertRaises(ConsultPackError):
                pack_consult_zip(
                    root,
                    model_dir=mdir,
                    character_name="x",
                    dry_path=os.path.join(td, "nope.wav"),
                    wet_path=wet,
                )

    def test_pack_same_file_raises(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root, mdir, dry, wet = _make_model(Path(td), fabric=False)
            with self.assertRaises(ConsultPackError):
                pack_consult_zip(
                    root,
                    model_dir=mdir,
                    character_name="x",
                    dry_path=dry,
                    wet_path=dry,
                )

    def test_pack_include_models_but_no_pth_raises(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root, mdir, dry, wet = _make_model(Path(td), fabric=False)
            os.remove(os.path.join(mdir, "hero.pth"))
            with self.assertRaises(ConsultPackError):
                pack_consult_zip(
                    root,
                    model_dir=mdir,
                    character_name="x",
                    dry_path=dry,
                    wet_path=wet,
                    include_model_files=True,
                )

    def test_pack_includes_perf_when_present(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root, mdir, dry, wet = _make_model(Path(td), fabric=True)
            perf_dir = os.path.join(root, "User_Data", "perf_reports")
            os.makedirs(perf_dir, exist_ok=True)
            with open(os.path.join(perf_dir, "perf_test.json"), "w", encoding="utf-8") as f:
                json.dump({"summary": {"n": 1}}, f)
            zpath = pack_consult_zip(
                root,
                model_dir=mdir,
                character_name="p",
                dry_path=dry,
                wet_path=wet,
            )
            with zipfile.ZipFile(zpath) as zf:
                self.assertTrue(any(n.startswith("perf/") for n in zf.namelist()))


if __name__ == "__main__":
    unittest.main()
