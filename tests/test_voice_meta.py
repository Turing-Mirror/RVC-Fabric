# -*- coding: utf-8 -*-
"""Voice pack identity meta: name / author / author_url / date / cover / ch-banner."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher.online.package_spec import (
    normalize_voice_meta,
    normalize_yymmdd,
    voice_meta_template,
)


class VoiceMetaUnitTests(unittest.TestCase):
    def test_normalize_yymmdd(self):
        self.assertEqual(normalize_yymmdd("260722"), "260722")
        self.assertEqual(normalize_yymmdd("2026-07-22"), "260722")
        self.assertEqual(normalize_yymmdd("20260722"), "260722")
        self.assertEqual(normalize_yymmdd(""), "")

    def test_normalize_voice_meta_fields(self):
        m = normalize_voice_meta(
            {
                "name": "浅夏",
                "author": "作者A",
                "author_url": "https://example.com/a",
                "date": "2026-07-22",
                "cover": "art/cover.png",
                "url": "https://should.not/use",
            }
        )
        self.assertEqual(m["name"], "浅夏")
        self.assertEqual(m["author"], "作者A")
        self.assertEqual(m["author_url"], "https://example.com/a")
        self.assertEqual(m["date"], "260722")
        self.assertEqual(m["cover"], "art/cover.png")
        self.assertNotIn("url", m)

    def test_normalize_voice_meta_released_alias(self):
        m = normalize_voice_meta({"name": "x", "released": "260101", "author": "A"})
        self.assertEqual(m["date"], "260101")
        self.assertEqual(m["author"], "A")

    def test_voice_meta_template(self):
        t = voice_meta_template(
            name="kiki", author="TM", author_url="https://x", date="260101"
        )
        self.assertEqual(t["name"], "kiki")
        self.assertEqual(t["author"], "TM")
        self.assertEqual(t["date"], "260101")
        self.assertEqual(t["cover"], "cover.jpg")


class VoiceInstallChBannerTests(unittest.TestCase):
    def test_install_zip_writes_ch_banner_cover(self):
        from launcher import paths as paths_mod
        from launcher.catalog import list_models_in_user_data, resolve_cover_path
        from launcher.online.voice_install import install_voice_pack_zip

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            banner = td_path / "ch-banner"
            banner.mkdir()
            with mock.patch.object(paths_mod, "CH_BANNER_DIR", banner), mock.patch.object(
                paths_mod, "USER_DATA", td_path
            ), mock.patch.object(paths_mod, "ROOT", td_path):
                root = td_path / "pack"
                root.mkdir()
                pth = root / "kiki.pth"
                pth.write_bytes(b"x" * 60_000)
                cover = root / "cover.jpg"
                cover.write_bytes(b"\xff\xd8\xff" + b"y" * 600)
                (root / "config.json").write_text(
                    json.dumps(
                        {
                            "name": "浅夏",
                            "author": "作者B",
                            "author_url": "https://example.com/b",
                            "date": "260715",
                            "cover": "cover.jpg",
                            "tag": "少女音",
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                zpath = td_path / "kiki.zip"
                with zipfile.ZipFile(zpath, "w") as zf:
                    for f in root.iterdir():
                        zf.write(f, f.name)

                models = td_path / "models"
                info = install_voice_pack_zip(
                    zpath, voice_id="kiki", models_root=models
                )
                dest = Path(info["dir"])
                cfg = json.loads((dest / "config.json").read_text(encoding="utf-8"))
                self.assertEqual(cfg["name"], "浅夏")
                self.assertEqual(cfg["author"], "作者B")
                self.assertEqual(cfg["date"], "260715")
                self.assertTrue(
                    str(cfg.get("cover") or "").replace("\\", "/").startswith(
                        "ch-banner/"
                    )
                )
                listed = {m["name"]: m for m in list_models_in_user_data(models)}
                self.assertEqual(listed["浅夏"]["author"], "作者B")
                r = resolve_cover_path(
                    cfg["cover"], model_dir=dest, voice_id="kiki"
                )
                self.assertTrue(r and Path(r).is_file())

    def test_resolve_cover_from_local_ch_banner(self):
        from launcher import paths as paths_mod
        from launcher.catalog import resolve_cover_path

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            banner = td_path / "ch-banner"
            banner.mkdir()
            img = banner / "demo.jpg"
            img.write_bytes(b"\xff\xd8\xff" + b"z" * 100)
            with mock.patch.object(paths_mod, "CH_BANNER_DIR", banner), mock.patch.object(
                paths_mod, "ROOT", td_path
            ):
                self.assertTrue(
                    Path(resolve_cover_path("ch-banner/demo.jpg")).is_file()
                )
                self.assertTrue(
                    Path(resolve_cover_path("demo.jpg", voice_id="demo")).is_file()
                )


if __name__ == "__main__":
    unittest.main()
