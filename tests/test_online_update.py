# -*- coding: utf-8 -*-
"""Unit tests for online catalog / packages (no network)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.online.catalog import (
    OnlineCatalog,
    compare_versions,
    load_bundled_catalog,
)
from launcher.online.downloader import (
    _has_requests,
    _session,
    cnb_lfs_object_url,
    is_git_lfs_pointer_bytes,
    is_github_url,
    normalize_cnb_url,
    normalize_github_url,
    parse_git_lfs_pointer_oid,
    prefer_cnb_lfs_url,
)
from launcher.online.gui_update import (
    apply_gui_patch_zip,
    check_gui_update,
    download_and_apply_gui,
)
from launcher.online.package_spec import (
    PKG_FULL,
    PKG_GUI_PATCH,
    PKG_VOICE_PACK,
    detect_zip_package_type,
    normalize_package_type,
)
from launcher.online.safe_zip import UnsafeZipError, safe_extract_zip
from launcher.online.voice_install import install_voice_pack_zip
from launcher.online.catalog import VoiceEntry


class CatalogFetchTests(unittest.TestCase):
    def test_fetch_catalog_overall_timeout_sets_error(self):
        """Slow URLs must not hang forever; fetch_error is set for UI."""
        import time
        from unittest import mock

        from launcher.online import catalog as cat_mod

        def _slow(*_a, **_k):
            time.sleep(0.3)
            raise RuntimeError("slow")

        with mock.patch.object(
            cat_mod, "DEFAULT_MANIFEST_URLS", ["https://example.invalid/x"]
        ):
            with mock.patch(
                "launcher.online.downloader.fetch_bytes_simple",
                side_effect=_slow,
            ):
                t0 = time.monotonic()
                out = cat_mod.fetch_catalog(
                    ["https://example.invalid/a"],
                    timeout=2,
                    overall_timeout=0.45,
                )
                elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 2.0)
        # Fallback catalog + error string for the settings card timeout hint
        self.assertTrue(
            bool(out.fetch_error) or out.source in ("bundled", "cache", "merged")
        )

    def test_fetch_bytes_simple_rejects_empty_url(self):
        from launcher.online.downloader import DownloadError, fetch_bytes_simple

        with self.assertRaises(DownloadError):
            fetch_bytes_simple("")


class VersionTests(unittest.TestCase):
    def test_compare(self):
        self.assertEqual(compare_versions("1.0.0", "1.0.1"), -1)
        self.assertEqual(compare_versions("1.1.0", "1.0.9"), 1)
        self.assertEqual(compare_versions("1.1.0", "1.1.0"), 0)

    def test_part_suffix_is_prerelease(self):
        # partN 预发布 < 同基础正式版；part 序号大者较新
        self.assertEqual(compare_versions("1.1.2-part1", "1.1.2"), -1)
        self.assertEqual(compare_versions("1.1.2", "1.1.2-part1"), 1)
        self.assertEqual(compare_versions("1.1.2-part1", "1.1.2-part2"), -1)
        self.assertEqual(compare_versions("1.1.2-part1", "1.1.2-part1"), 0)
        # 基础版本不同时 part 后缀不影响大小关系
        self.assertEqual(compare_versions("1.1.2-part1", "1.1.1"), 1)
        self.assertEqual(compare_versions("1.1.2-part9", "1.1.3"), -1)

    def test_legacy_digit_only_client_sees_pure_patch(self):
        """Old shells without -partN semantics: re.findall(r'\\d+') only.

        1.1.2-part1 → [1,1,2,1] looked *newer* than 1.1.2, so users stuck.
        Shipping pure 1.1.4 → [1,1,4] still wins under digit-only compare.
        """
        import re

        def legacy(a: str, b: str) -> int:
            pa = [int(x) for x in re.findall(r"\d+", a or "0")] or [0]
            pb = [int(x) for x in re.findall(r"\d+", b or "0")] or [0]
            n = max(len(pa), len(pb))
            pa += [0] * (n - len(pa))
            pb += [0] * (n - len(pb))
            return (pa > pb) - (pa < pb)

        # Why part1 users never saw 1.1.2
        self.assertEqual(legacy("1.1.2-part1", "1.1.2"), 1)
        # Pure next release unblocks them without upgrading the comparator
        self.assertEqual(legacy("1.1.2-part1", "1.1.4"), -1)
        self.assertEqual(compare_versions("1.1.2-part1", "1.1.4"), -1)


class CnbUrlTests(unittest.TestCase):
    def test_blob_to_git_raw(self):
        blob = (
            "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/"
            "-/blob/main/voices/guanguan/guanguan-v2.zip"
        )
        raw = normalize_cnb_url(blob)
        self.assertEqual(
            raw,
            "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/"
            "-/git/raw/main/voices/guanguan/guanguan-v2.zip",
        )

    def test_git_raw_unchanged(self):
        u = (
            "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/"
            "-/git/raw/main/catalog/online_catalog.snippet.json"
        )
        self.assertEqual(normalize_cnb_url(u), u)

    def test_lfs_pointer_detect(self):
        ptr = (
            b"version https://git-lfs.github.com/spec/v1\n"
            b"oid sha256:be1bdb2cec1b6110f404dbc08e6672f3d39ba6846aba9ef58267e892c57d9367\n"
            b"size 51006400\n"
        )
        self.assertTrue(is_git_lfs_pointer_bytes(ptr))
        self.assertFalse(is_git_lfs_pointer_bytes(b"PK\x03\x04fakezip"))
        self.assertEqual(
            parse_git_lfs_pointer_oid(ptr),
            "be1bdb2cec1b6110f404dbc08e6672f3d39ba6846aba9ef58267e892c57d9367",
        )

    def test_cnb_lfs_object_url(self):
        oid = "dfb9a54afe78a95b32f1742090bd55541c28a205f3f958884247e4a454e2aeb3"
        self.assertEqual(
            cnb_lfs_object_url("Turing-Mirror", "RVC-Fabric-Releases", oid),
            f"https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/lfs/{oid}",
        )

    def test_session_optional_without_requests(self):
        # 启动器补全 Runtime 时允许无 requests；_session 不得抛错
        s = _session()
        if not _has_requests():
            self.assertIsNone(s)
        else:
            self.assertIsNotNone(s)
        oid = "dfb9a54afe78a95b32f1742090bd55541c28a205f3f958884247e4a454e2aeb3"
        raw = (
            "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/"
            "-/git/raw/main/voices/guanguan/guanguan-v2.zip"
        )
        self.assertEqual(
            prefer_cnb_lfs_url(raw, oid),
            f"https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/lfs/{oid}",
        )

    def test_prefer_cnb_lfs_does_not_rewrite_release_urls(self):
        """Runtime nvidia/nvidia50 must stay on Release, not dead LFS rewrite."""
        oid = "d76ac4e8140490bda1abac8df2718bfec95f8a696c8a5ba730a5e7e901421d9b"
        rel = (
            "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/"
            "-/releases/download/RVC-runtime/runtime-nvidia-2026.07.21.tar"
        )
        self.assertEqual(prefer_cnb_lfs_url(rel, oid), rel)
        rel50 = (
            "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/"
            "-/releases/download/RVC-runtime/runtime-nvidia50-2026.07.21.tar"
        )
        oid50 = "a828e13e23589447f25b16b9314b6d730a1a7701e973613bc97d80a026102489"
        self.assertEqual(prefer_cnb_lfs_url(rel50, oid50), rel50)

    def test_index_json_voice_meta(self):
        from pathlib import Path

        from launcher.online.catalog import OnlineCatalog

        p = Path(__file__).resolve().parents[1] / "CNB-GIT-RELEASE" / "index.json"
        if not p.is_file():
            self.skipTest("CNB-GIT-RELEASE/index.json not present")
        data = json.loads(p.read_text(encoding="utf-8"))
        cat = OnlineCatalog.from_dict(data, source="index")
        self.assertGreaterEqual(len(cat.voices), 1)
        v = cat.voices[0]
        self.assertTrue(v.author)
        self.assertTrue(v.date)
        self.assertIn("ch-banner", v.cover_url)


class CatalogTests(unittest.TestCase):
    def test_bundled_loads(self):
        cat = load_bundled_catalog()
        self.assertIsInstance(cat, OnlineCatalog)

    def test_from_dict_voices_pack_or_pth(self):
        data = {
            "schema": 1,
            "app": {
                "version": "2.0.0",
                "gui": {
                    "package_type": "gui_patch",
                    "version": "2.0.0",
                    "url": "https://x/a.zip",
                },
            },
            "voices": [
                {"id": "a", "name": "A", "pack_url": "https://x/a.zip"},
                {"id": "b", "name": "B", "pth_url": "https://x/b.pth"},
                {"id": "c", "name": "C"},  # no url
            ],
        }
        cat = OnlineCatalog.from_dict(data, source="test")
        self.assertEqual(len(cat.voices), 2)
        st = check_gui_update(cat, local_version="1.0.0")
        self.assertTrue(st["available"])
        self.assertEqual(st["package_type"], PKG_GUI_PATCH)
        self.assertEqual(st["action"], "apply_patch")

    def test_full_package_action(self):
        data = {
            "app": {
                "version": "3.0.0",
                "gui": {
                    "package_type": "full_package",
                    "version": "3.0.0",
                    "url": "https://sharepoint/full",
                },
            }
        }
        cat = OnlineCatalog.from_dict(data)
        st = check_gui_update(cat, local_version="1.0.0")
        self.assertTrue(st["available"])
        self.assertEqual(st["action"], "external")
        self.assertEqual(st["package_type"], PKG_FULL)


class GithubUrlTests(unittest.TestCase):
    def test_blob_to_raw(self):
        u = normalize_github_url("https://github.com/org/repo/blob/main/path/file.pth")
        self.assertIn("raw.githubusercontent.com", u)

    def test_is_github(self):
        self.assertTrue(is_github_url("https://github.com/a/b"))
        self.assertFalse(is_github_url("https://example.com/x"))


class PackageDetectTests(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(normalize_package_type("incremental"), PKG_GUI_PATCH)
        self.assertEqual(normalize_package_type("full"), PKG_FULL)
        self.assertEqual(normalize_package_type("voice_zip"), PKG_VOICE_PACK)

    def test_detect_gui_and_full(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            gui_z = root / "gui.zip"
            with zipfile.ZipFile(gui_z, "w") as zf:
                zf.writestr(
                    "tm_package.json",
                    json.dumps({"package_type": "gui_patch", "version": "1"}),
                )
                zf.writestr("launcher/x.py", "print(1)\n")
            self.assertEqual(detect_zip_package_type(gui_z), PKG_GUI_PATCH)

            full_z = root / "full.zip"
            with zipfile.ZipFile(full_z, "w") as zf:
                zf.writestr("Runtime/python.exe", b"fake")
                zf.writestr("launcher/x.py", "x")
            self.assertEqual(detect_zip_package_type(full_z), PKG_FULL)

    def test_apply_patch_blocks_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            zpath = root / "p.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr(
                    "tm_package.json",
                    json.dumps({"package_type": "gui_patch", "version": "9.9.9"}),
                )
                zf.writestr("launcher/hello_test.txt", "ok")
                zf.writestr("Runtime/evil.bin", "nope")
            result = apply_gui_patch_zip(zpath, root=root)
            self.assertIn("launcher/hello_test.txt", result["written"])
            self.assertFalse((root / "Runtime" / "evil.bin").is_file())

    def test_apply_rejects_full(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            zpath = root / "full.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr(
                    "tm_package.json",
                    json.dumps({"package_type": "full_package"}),
                )
                zf.writestr("Runtime/python.exe", b"x")
            with self.assertRaises(Exception) as ctx:
                apply_gui_patch_zip(zpath, root=root)
            self.assertIn("全量", str(ctx.exception))


class VoicePackTests(unittest.TestCase):
    def test_install_voice_zip(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            models = td_path / "models"
            zpath = td_path / "v.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr(
                    "tm_package.json",
                    json.dumps(
                        {
                            "package_type": "voice_pack",
                            "voice_id": "demo",
                            "name": "Demo",
                        }
                    ),
                )
                zf.writestr("demo.pth", b"x" * 60_000)
                zf.writestr("cover.png", b"\x89PNG" + b"\x00" * 600)
                zf.writestr(
                    "config.json",
                    json.dumps({"name": "DemoVoice", "tag": "测试"}),
                )
            info = install_voice_pack_zip(zpath, voice_id="demo", models_root=models)
            self.assertTrue(Path(info["path"]).is_file())
            self.assertTrue((models / "demo" / "config.json").is_file())
            cfg = json.loads(
                (models / "demo" / "config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(cfg["name"], "DemoVoice")

    def test_has_download_pack_url(self):
        v = VoiceEntry.from_dict(
            {"id": "x", "name": "X", "pack_url": "https://example.com/a.zip"}
        )
        self.assertTrue(v.has_download())
        self.assertFalse(VoiceEntry.from_dict({"id": "y", "name": "Y"}).has_download())

    def test_install_voice_zip_keeps_series(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            models = td_path / "models"
            zpath = td_path / "v.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("mygo.pth", b"x" * 60_000)
                zf.writestr(
                    "config.json",
                    json.dumps({"name": "灯", "series": "Mygo"}),
                )
            info = install_voice_pack_zip(
                zpath, voice_id="mygo-tomori", models_root=models
            )
            cfg = json.loads(
                (Path(info["dir"]) / "config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(cfg.get("series"), "Mygo")

    def test_install_voice_zip_bad_pack_does_not_wipe_existing(self):
        """Validate before wipe: a bad zip must not destroy an installed voice."""
        from launcher.online.downloader import DownloadError

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            models = td_path / "models"
            dest = models / "keep-me"
            dest.mkdir(parents=True)
            keep = dest / "good.pth"
            keep.write_bytes(b"y" * 60_000)
            (dest / "config.json").write_text(
                json.dumps({"name": "Keep"}), encoding="utf-8"
            )
            bad = td_path / "bad.zip"
            # Valid zip but no .pth → validation fails after extract
            with zipfile.ZipFile(bad, "w") as zf:
                zf.writestr("readme.txt", "no model here")
            with self.assertRaises(DownloadError):
                install_voice_pack_zip(bad, voice_id="keep-me", models_root=models)
            self.assertTrue(keep.is_file(), "existing pth must survive bad pack")
            self.assertTrue((dest / "config.json").is_file())


class VoiceSeriesTests(unittest.TestCase):
    def test_from_dict_reads_series_aliases(self):
        for key in ("series", "series_name", "collection"):
            v = VoiceEntry.from_dict(
                {"id": "a", "name": "A", "pth_url": "https://x/a.pth", key: "VOCALOID"}
            )
            self.assertEqual(v.series, "VOCALOID")
        v = VoiceEntry.from_dict({"id": "b", "name": "B", "pth_url": "https://x/b.pth"})
        self.assertEqual(v.series, "")

    def test_group_voices_by_series(self):
        from launcher.online.catalog import group_voices_by_series

        def mk(i, series=""):
            return VoiceEntry.from_dict(
                {"id": i, "name": i, "pth_url": f"https://x/{i}.pth", "series": series}
            )

        voices = [
            mk("solo1"),
            mk("tomori", "Mygo"),
            mk("miku", "VOCALOID"),
            mk("anon", "Mygo"),
            mk("solo2"),
        ]
        groups = group_voices_by_series(voices)
        self.assertEqual([g[0] for g in groups], ["", "Mygo", "VOCALOID"])
        self.assertEqual([v.id for v in groups[0][1]], ["solo1", "solo2"])
        self.assertEqual([v.id for v in groups[1][1]], ["tomori", "anon"])
        self.assertEqual([v.id for v in groups[2][1]], ["miku"])

    def test_group_all_ungrouped_single_group(self):
        from launcher.online.catalog import group_voices_by_series

        voices = [
            VoiceEntry.from_dict({"id": i, "name": i, "pth_url": f"https://x/{i}.pth"})
            for i in ("a", "b")
        ]
        groups = group_voices_by_series(voices)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][0], "")


class SafeZipTests(unittest.TestCase):
    def test_reject_zip_slip(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            zpath = td_path / "evil.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("../evil.txt", "nope")
                zf.writestr("ok.txt", "yes")
            dest = td_path / "out"
            dest.mkdir()
            with self.assertRaises(UnsafeZipError):
                safe_extract_zip(zpath, dest)

    def test_safe_member_ok(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            zpath = td_path / "ok.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("folder/a.txt", "hello")
            dest = td_path / "out"
            dest.mkdir()
            written = safe_extract_zip(zpath, dest)
            self.assertTrue((dest / "folder" / "a.txt").is_file())
            self.assertTrue(any("a.txt" in w for w in written))


class GuiShaPolicyTests(unittest.TestCase):
    def test_require_sha256(self):
        from launcher.online.catalog import GuiUpdate
        from launcher.online.downloader import DownloadError

        gui = GuiUpdate(version="9.9.9", url="https://example.com/p.zip", sha256="")
        with self.assertRaises(DownloadError) as ctx:
            download_and_apply_gui(gui, require_sha256=True)
        self.assertIn("sha256", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
