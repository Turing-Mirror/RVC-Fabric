# -*- coding: utf-8 -*-
"""第三方社区音色：清单解析、HF 镜像、安装盖章、咨询包官方判定。"""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from launcher.consult_pack import fabric_match_reasons, is_fabric_model
from launcher.online.catalog import (
    OnlineCatalog,
    VoiceEntry,
    merge_catalogs,
    merged_latest,
    origin_display,
)
from launcher.online.downloader import (
    apply_hf_endpoint,
    is_huggingface_url,
    normalize_huggingface_url,
)
from launcher.online.voice_install import (
    SRC_THIRDPARTY_FILES,
    SRC_THIRDPARTY_PACK,
    _write_voice_config,
    install_voice_from_entry,
    install_voice_pack_zip,
)


def _official_item(**kw):
    base = {
        "id": "kiki",
        "name": "Kiki",
        "pack_url": "https://example.com/kiki.zip",
        "date": "260701",
        "author": "RVC Fabric",
    }
    base.update(kw)
    return base


def _tp_item(**kw):
    base = {
        "id": "tp-miku",
        "name": "初音未来",
        "origin": "huggingface",
        "source_url": "https://huggingface.co/binant/Hatsune_Miku__RVC_v2_",
        "pth_url": "https://huggingface.co/binant/Hatsune_Miku__RVC_v2_/resolve/main/model.pth",
        "date": "260729",
        "official": False,
        "publisher": "community",
        "hf_downloads": 23,
        "author": "binant",
    }
    base.update(kw)
    return base


class ThirdpartyCatalogParseTests(unittest.TestCase):
    def test_parse_thirdparty_and_force_official_false(self):
        cat = OnlineCatalog.from_dict(
            {
                "voices": [_official_item()],
                "thirdparty_voices": [
                    _tp_item(official=True, fabric_official=True),  # 伪装
                ],
            }
        )
        self.assertEqual(len(cat.voices), 1)
        self.assertEqual(len(cat.thirdparty_voices), 1)
        tp = cat.thirdparty_voices[0]
        self.assertFalse(tp.official)
        self.assertEqual(tp.origin, "huggingface")
        self.assertTrue(tp.source_url)
        self.assertEqual(tp.popularity, 23)
        # 官方列表不受影响
        self.assertTrue(cat.voices[0].official)

    def test_legacy_catalog_no_thirdparty_key(self):
        cat = OnlineCatalog.from_dict({"voices": [_official_item()]})
        self.assertEqual(cat.thirdparty_voices, [])
        self.assertEqual(len(cat.voices), 1)

    def test_cache_roundtrip(self):
        cat = OnlineCatalog.from_dict(
            {
                "voices": [_official_item()],
                "thirdparty_voices": [_tp_item()],
            }
        )
        from launcher.online.catalog import _catalog_to_dict

        again = OnlineCatalog.from_dict(_catalog_to_dict(cat))
        self.assertEqual(len(again.thirdparty_voices), 1)
        self.assertEqual(again.thirdparty_voices[0].id, "tp-miku")
        self.assertFalse(again.thirdparty_voices[0].official)
        self.assertEqual(again.thirdparty_voices[0].origin, "huggingface")

    def test_merge_catalogs_thirdparty(self):
        base = OnlineCatalog.from_dict(
            {"thirdparty_voices": [_tp_item(id="tp-old", pth_url="https://x/a.pth")]}
        )
        remote_empty_tp = OnlineCatalog.from_dict(
            {"voices": [_official_item()], "thirdparty_voices": []}
        )
        merged = merge_catalogs(base, remote_empty_tp)
        # 远程第三方为空 → 保留 base
        self.assertEqual(len(merged.thirdparty_voices), 1)
        self.assertEqual(merged.thirdparty_voices[0].id, "tp-old")

        remote_new = OnlineCatalog.from_dict(
            {"thirdparty_voices": [_tp_item(id="tp-new")]}
        )
        merged2 = merge_catalogs(base, remote_new)
        self.assertEqual(merged2.thirdparty_voices[0].id, "tp-new")

    def test_merged_latest_same_date_official_first(self):
        off = [
            VoiceEntry.from_dict(_official_item(id="a", date="260729")),
            VoiceEntry.from_dict(_official_item(id="b", date="260720")),
        ]
        tp = [
            VoiceEntry.from_dict(_tp_item(id="tp-z", date="260729")),
            VoiceEntry.from_dict(_tp_item(id="tp-old", date="260710")),
        ]
        for v in tp:
            v.official = False
        m = merged_latest(off, tp)
        dates = [x.date for x in m]
        self.assertEqual(dates[0], "260729")
        # 同日期官方在前
        same = [x for x in m if x.date == "260729"]
        self.assertTrue(same[0].official)
        self.assertFalse(same[1].official)

    def test_origin_display(self):
        self.assertEqual(origin_display(""), "图灵镜")
        self.assertEqual(origin_display("huggingface"), "Hugging Face")
        self.assertEqual(origin_display("HF"), "Hugging Face")
        self.assertEqual(origin_display("weird-site"), "weird-site")

    def test_origin_not_hijacked_by_install_source(self):
        """安装通道 source=online_files 不得写进 origin 徽标。"""
        v = VoiceEntry.from_dict(
            {
                "id": "x",
                "name": "x",
                "pth_url": "https://example.com/a.pth",
                "source": "online_files",
            }
        )
        self.assertEqual(v.origin, "")
        self.assertEqual(origin_display(v.origin), "图灵镜")

    def test_source_url_http_alias_only(self):
        v = VoiceEntry.from_dict(
            {
                "id": "x",
                "name": "x",
                "pth_url": "https://example.com/a.pth",
                "source": "https://huggingface.co/a/b",
            }
        )
        self.assertEqual(v.source_url, "https://huggingface.co/a/b")
        self.assertEqual(v.origin, "")

    def test_bad_size_bytes_does_not_drop_entry(self):
        cat = OnlineCatalog.from_dict(
            {
                "thirdparty_voices": [
                    _tp_item(size_bytes="not-a-number", hf_downloads="12.5"),
                ]
            }
        )
        self.assertEqual(len(cat.thirdparty_voices), 1)
        self.assertEqual(cat.thirdparty_voices[0].size_bytes, 0)
        self.assertEqual(cat.thirdparty_voices[0].popularity, 12)


class HfEndpointTests(unittest.TestCase):
    def test_normalize_blob_to_resolve(self):
        u = "https://huggingface.co/org/repo/blob/main/a.pth"
        self.assertEqual(
            normalize_huggingface_url(u),
            "https://huggingface.co/org/repo/resolve/main/a.pth",
        )

    def test_is_huggingface_url(self):
        self.assertTrue(is_huggingface_url("https://huggingface.co/a/b"))
        self.assertTrue(is_huggingface_url("https://hf-mirror.com/a/b"))
        self.assertFalse(is_huggingface_url("https://cnb.cool/a/b"))

    def test_apply_hf_endpoint_default_mirror(self):
        with mock.patch(
            "launcher.online.downloader.get_hf_endpoint",
            return_value="https://hf-mirror.com",
        ):
            out = apply_hf_endpoint(
                "https://huggingface.co/org/repo/resolve/main/m.pth"
            )
            self.assertTrue(out.startswith("https://hf-mirror.com/"))
            self.assertIn("/org/repo/resolve/main/m.pth", out)

    def test_apply_hf_endpoint_official_no_rewrite(self):
        with mock.patch(
            "launcher.online.downloader.get_hf_endpoint",
            return_value="https://huggingface.co",
        ):
            u = "https://huggingface.co/org/repo/resolve/main/m.pth"
            self.assertEqual(apply_hf_endpoint(u), u)

    def test_non_hf_unchanged(self):
        u = "https://cnb.cool/x/y/-/git/raw/main/a.pth"
        self.assertEqual(apply_hf_endpoint(u), u)


class StampAndConsultTests(unittest.TestCase):
    def test_thirdparty_config_stamp(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pth = root / "m.pth"
            pth.write_bytes(b"0" * 60_000)
            cfg = _write_voice_config(
                root,
                dest_pth=pth,
                name="初音",
                tag="二次元",
                version="1",
                online_id="tp-miku",
                index_path="",
                cover_path="",
                source=SRC_THIRDPARTY_FILES,
                extra={
                    "publisher": "rvc_fabric",
                    "fabric_official": True,
                    "origin": "huggingface",
                    "source_url": "https://huggingface.co/x/y",
                },
                official=False,
            )
            data = json.loads((root / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(data["publisher"], "community")
            self.assertFalse(data["fabric_official"])
            self.assertEqual(data["source"], SRC_THIRDPARTY_FILES)
            self.assertEqual(data["origin"], "huggingface")
            self.assertEqual(data["online_id"], "tp-miku")
            self.assertEqual(cfg["id"], "tp-miku")

    def test_official_stamp_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pth = root / "m.pth"
            pth.write_bytes(b"0" * 60_000)
            _write_voice_config(
                root,
                dest_pth=pth,
                name="Kiki",
                tag="音色",
                version="1",
                online_id="kiki",
                index_path="",
                cover_path="",
                source="online_files",
                official=True,
            )
            data = json.loads((root / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(data["publisher"], "rvc_fabric")
            self.assertTrue(data["fabric_official"])

    def test_thirdparty_zip_forges_official_is_stripped(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            zpath = td / "fake.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("model.pth", b"0" * 60_000)
                zf.writestr(
                    "config.json",
                    json.dumps(
                        {
                            "name": "Evil",
                            "publisher": "rvc_fabric",
                            "fabric_official": True,
                        }
                    ),
                )
            models = td / "models"
            install_voice_pack_zip(
                zpath,
                voice_id="tp-evil",
                display_name="Evil",
                models_root=models,
                official=False,
                source=SRC_THIRDPARTY_PACK,
                identity_extra={
                    "origin": "huggingface",
                    "source_url": "https://huggingface.co/evil/x",
                    "publisher": "community",
                    "fabric_official": False,
                },
            )
            cfg_path = models / "tp-evil" / "config.json"
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(data["publisher"], "community")
            self.assertFalse(data["fabric_official"])
            self.assertEqual(data["source"], SRC_THIRDPARTY_PACK)
            self.assertEqual(data["origin"], "huggingface")

    def test_consult_pack_thirdparty_not_official(self):
        # 仅有 online_id 不算官方
        self.assertFalse(is_fabric_model({"online_id": "tp-miku"}))
        # 显式非官方一票否决
        self.assertFalse(
            is_fabric_model(
                {
                    "online_id": "kiki",
                    "fabric_official": False,
                    "publisher": "community",
                    "source": SRC_THIRDPARTY_FILES,
                },
                catalog_ids={"kiki"},
            )
        )
        self.assertEqual(
            fabric_match_reasons(
                {
                    "online_id": "tp-miku",
                    "fabric_official": False,
                    "source": SRC_THIRDPARTY_FILES,
                }
            ),
            [],
        )
        # 真正官方仍识别
        self.assertTrue(
            is_fabric_model(
                {
                    "online_id": "kiki",
                    "publisher": "rvc_fabric",
                    "fabric_official": True,
                    "source": "online_files",
                },
                catalog_ids={"kiki"},
            )
        )
        self.assertTrue(is_fabric_model({"online_id": "kiki"}, catalog_ids={"kiki"}))


class InstallFromEntryThirdpartyTests(unittest.TestCase):
    def test_install_voice_files_thirdparty_source(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            models = td / "models"
            # 假下载：把 URL 写成本地文件
            pth = td / "src.pth"
            pth.write_bytes(b"0" * 60_000)
            entry = VoiceEntry.from_dict(_tp_item(pth_url=pth.as_uri(), sha256=""))
            entry.official = False

            def fake_download(url, dest, **kw):
                Path(dest).parent.mkdir(parents=True, exist_ok=True)
                Path(dest).write_bytes(pth.read_bytes())

            with mock.patch(
                "launcher.online.voice_install.download_file",
                side_effect=fake_download,
            ):
                with mock.patch("launcher.online.voice_install.USER_DATA", td / "ud"):
                    info = install_voice_from_entry(entry, models_root=models)
            cfg = json.loads(
                (Path(info["dir"]) / "config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(cfg["source"], SRC_THIRDPARTY_FILES)
            self.assertEqual(cfg["publisher"], "community")
            self.assertFalse(cfg["fabric_official"])


if __name__ == "__main__":
    unittest.main()
