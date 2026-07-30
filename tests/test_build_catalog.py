# -*- coding: utf-8 -*-
"""scripts/build_catalog.py 单元测试 — YAML 源编译 / 自动补全 / 契约回环。

fixture 在 tmpdir 里造一个迷你 CNB-GIT-RELEASE（假制品文件 + catalog-src），
不触网、不动真实仓库。宿主机需要 PyYAML（与脚本一致）。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import yaml
except ImportError:  # pragma: no cover — host python without PyYAML
    raise unittest.SkipTest("PyYAML not installed; build_catalog is maintainer-only")


def _load_build_catalog():
    path = ROOT / "scripts" / "build_catalog.py"
    spec = importlib.util.spec_from_file_location("tm_build_catalog", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bc = _load_build_catalog()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _w(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha(data)


def _y(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def make_fixture(tmp: Path) -> "bc.Paths":
    """迷你 CNB 仓：制品 + catalog-src；返回 Paths（bundled 也指向 tmp）。"""
    cnb = tmp / "cnb"
    paths = bc.Paths(cnb=cnb, bundled=tmp / "online_catalog.json")

    _w(cnb / "voices" / "kiki" / "kiki-v2.zip", b"KIKI" * 600)
    _w(cnb / "voices" / "tomori" / "tomori-v1.zip", b"TOMORI" * 700)
    _w(cnb / "ch-banner" / "kiki.jpg", b"\xff\xd8JPG" * 40)
    _w(cnb / "ch-banner" / "tomori.jpg", b"\xff\xd8JPG" * 41)
    _w(cnb / "assets" / "core" / "engine-core-1.zip", b"CORE" * 900)
    _w(cnb / "vbcable" / "vbcable-setup.zip", b"VB" * 500)
    _w(cnb / "setup" / "RVC_Fabric_Setup.exe", b"MZSETUP" * 300)
    _w(cnb / "runtime" / "nvidia" / "runtime-nvidia-1.tar", b"NV" * 1000)
    _w(cnb / "runtime" / "amd" / "runtime-amd-1.tar", b"AMD" * 1000)
    _w(cnb / "runtime" / "nvidia50" / "runtime-nvidia50-1.tar", b"NV50" * 1000)

    src = paths.src
    _y(src / "meta.yaml", {"product": "RVC Fabric", "note": "n", "runtime_release_tag": "RVC-runtime"})
    _y(
        src / "app.yaml",
        {
            "version": "1.2.0",
            "channel": "stable",
            "gui": {
                "version": "1.2.0",
                "sha256": "a" * 64,
                "min_app_version": "1.1.0",
                "notes": "notes",
            },
        },
    )
    _y(src / "community.yaml", {"qq_group": "123", "qq_link": "", "sharepoint_full": "", "note": "c"})
    _y(
        src / "engine-core.yaml",
        {"file": "assets/core/engine-core-1.zip", "version": "1", "released": "260722", "channel": "lfs"},
    )
    _y(
        src / "vbcable.yaml",
        {"display_name": "VB-Cable Setup Pack", "file": "vbcable/vbcable-setup.zip",
         "version": "1.0.0", "released": "260722", "channel": "lfs"},
    )
    _y(
        src / "setup.yaml",
        {"display_name": "RVC Fabric Setup", "file": "setup/RVC_Fabric_Setup.exe",
         "version": "1.2.0", "released": "260723", "channel": "lfs"},
    )
    for variant, ch in (("nvidia", "release"), ("amd", "lfs"), ("nvidia50", "release")):
        _y(
            src / "runtimes" / f"{variant}.yaml",
            {
                "variant": variant,
                "label": variant.upper(),
                "version": "2026.07.21",
                "released": "260721",
                "channel": ch,
                "parts": [{"file": f"runtime/{variant}/runtime-{variant}-1.tar"}],
            },
        )
    _y(
        src / "voices" / "kiki.yaml",
        {"id": "kiki", "name": "kikiV1", "tag": "少女音", "series": "RVC原版",
         "author": "RVC Fabric", "date": "260721", "version": "2",
         "description": "d", "file": "voices/kiki/kiki-v2.zip",
         "cover": "ch-banner/kiki.jpg"},
    )
    _y(
        src / "voices" / "tomori.yaml",
        {"id": "tomori", "name": "高松灯", "tag": "少女音", "series": "MyGO!!!!!",
         "author": "望月星逸", "date": "260723", "version": "1",
         "description": "高松灯 · MyGO!!!!!", "file": "voices/tomori/tomori-v1.zip",
         "cover": "ch-banner/tomori.jpg"},
    )
    return paths


class BuildOutputsTests(unittest.TestCase):
    def test_build_structure_and_autofill(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_fixture(Path(td))
            rc = bc.cmd_build(paths)
            self.assertEqual(rc, 0)
            index = json.loads(paths.index_out.read_text(encoding="utf-8"))
            snippet = json.loads(paths.snippet_out.read_text(encoding="utf-8"))
            bundled = json.loads(paths.bundled_out.read_text(encoding="utf-8"))

            # 顶层键（index schema 2）
            for key in (
                "schema", "format", "packages", "app", "community", "voices",
                "runtime_release_tag", "runtimes", "manifest_urls",
                "engine_core", "vbcable",
            ):
                self.assertIn(key, index)
            self.assertEqual(index["schema"], 2)
            self.assertEqual(snippet["schema"], 1)
            self.assertEqual(bundled["schema"], 1)
            # packages 五数组齐全
            for kind in ("setup", "gui_patch", "engine_core", "runtime", "vbcable"):
                self.assertIn(kind, index["packages"])
            self.assertEqual(len(index["packages"]["runtime"]), 3)

            # 自动补全：sha256/size 来自本地制品
            kiki_zip = paths.cnb / "voices" / "kiki" / "kiki-v2.zip"
            want = _sha(kiki_zip.read_bytes())
            voices = {v["id"]: v for v in index["voices"]}
            self.assertEqual(voices["kiki"]["sha256"], want)
            self.assertEqual(voices["kiki"]["size_bytes"], kiki_zip.stat().st_size)
            self.assertEqual(voices["kiki"]["pack_url"], f"{bc.LFS}/{want}")
            self.assertIn("ch-banner/kiki.jpg", voices["kiki"]["cover_url"])
            # series 透传三份产物
            self.assertEqual(voices["kiki"]["series"], "RVC原版")
            self.assertEqual(
                {v["id"]: v.get("series") for v in bundled["voices"]}["tomori"],
                "MyGO!!!!!",
            )
            # 边车已生成
            self.assertTrue((paths.cnb / "voices" / "kiki" / "kiki-v2.zip.sha256").is_file())

            # release 通道 URL 含 release_tag；lfs 通道 URL 是 LFS 形态
            nv = index["runtimes"]["nvidia"]["parts"][0]
            self.assertIn("/-/releases/download/RVC-runtime/", nv["urls"][0])
            amd = index["runtimes"]["amd"]["parts"][0]
            self.assertIn("/-/lfs/", amd["urls"][0])
            self.assertIn("runtime/amd/", amd["sha256_urls"][0])

            # gui：url 由锁定 sha256 推导
            self.assertEqual(index["app"]["gui"]["url"], f"{bc.LFS}/{'a' * 64}")

            # 无 changelog.yaml 时仍写出空 changelog.json
            cl = json.loads(paths.changelog_out.read_text(encoding="utf-8"))
            self.assertEqual(cl.get("schema"), 1)
            self.assertEqual(cl.get("entries"), [])

            # 音色排序：date 升序
            self.assertEqual([v["id"] for v in index["voices"]], ["kiki", "tomori"])

    def test_changelog_overrides_gui_notes(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_fixture(Path(td))
            _y(
                paths.src / "changelog.yaml",
                {
                    "entries": [
                        {
                            "version": "1.2.0",
                            "date": "260723",
                            "highlights": ["h1"],
                            "body": "from-changelog-body",
                        }
                    ]
                },
            )
            self.assertEqual(bc.cmd_build(paths), 0)
            index = json.loads(paths.index_out.read_text(encoding="utf-8"))
            self.assertEqual(index["app"]["gui"]["notes"], "from-changelog-body")
            cl = json.loads(paths.changelog_out.read_text(encoding="utf-8"))
            self.assertEqual(len(cl["entries"]), 1)
            self.assertEqual(cl["entries"][0]["version"], "1.2.0")
            plaza = json.loads(paths.plaza_out.read_text(encoding="utf-8"))
            release_ids = [
                it["id"] for it in plaza["items"] if str(it["id"]).startswith("release-")
            ]
            self.assertIn("release-1.2.0", release_ids)

    def test_roundtrip_real_client_parsers(self):
        """产物必须能被真实客户端解析器读出来。

        解析器现在是 Rust（app/src-tauri 的 catalog-check）。没有 Rust 工具链
        时跳过，而不是假装通过——build_catalog 自身会在报告里给出同样的警告。
        """
        import subprocess

        exe = bc._client_checker()
        if not exe:
            self.skipTest("catalog-check 不可用（需要 Rust 工具链）")
        with tempfile.TemporaryDirectory() as td:
            paths = make_fixture(Path(td))
            self.assertEqual(bc.cmd_build(paths), 0)
            plaza = json.loads(paths.plaza_out.read_text(encoding="utf-8"))
        out = subprocess.run(
            [str(exe), "plaza"],
            input=json.dumps(plaza),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        parsed = json.loads(out.stdout)
        self.assertEqual(parsed["count"], len(plaza.get("items") or []))

    def test_build_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_fixture(Path(td))
            self.assertEqual(bc.cmd_build(paths), 0)
            first = paths.index_out.read_text(encoding="utf-8")
            self.assertEqual(bc.cmd_build(paths), 0)
            self.assertEqual(paths.index_out.read_text(encoding="utf-8"), first)


class PinnedValueTests(unittest.TestCase):
    def test_pinned_sha_wins_with_warning(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_fixture(Path(td))
            pinned = "b" * 64
            _y(
                paths.src / "voices" / "kiki.yaml",
                {"id": "kiki", "name": "kikiV1", "date": "260721",
                 "file": "voices/kiki/kiki-v2.zip", "cover": "ch-banner/kiki.jpg",
                 "sha256": pinned, "size_bytes": 999},
            )
            outputs, rep = bc._compile_all(paths)
            self.assertIsNotNone(outputs)
            voices = {v["id"]: v for v in outputs["index"]["voices"]}
            self.assertEqual(voices["kiki"]["sha256"], pinned)
            self.assertEqual(voices["kiki"]["size_bytes"], 999)
            self.assertTrue(any("锁定值" in w for w in rep.warnings))

    def test_missing_artifact_with_pin_is_warning_only(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_fixture(Path(td))
            _y(
                paths.src / "voices" / "gone.yaml",
                {"id": "gone", "name": "gone", "date": "260724",
                 "file": "voices/gone/gone-v1.zip", "cover": "ch-banner/kiki.jpg",
                 "sha256": "c" * 64, "size_bytes": 1},
            )
            outputs, rep = bc._compile_all(paths)
            self.assertIsNotNone(outputs)
            self.assertFalse(rep.errors)
            self.assertTrue(any("本地缺制品" in w for w in rep.warnings))


class CheckFailureTests(unittest.TestCase):
    def test_voice_missing_file_and_sha_fails(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_fixture(Path(td))
            _y(paths.src / "voices" / "bad.yaml", {"id": "bad", "date": "260724"})
            self.assertEqual(bc.cmd_check(paths), 1)

    def test_channel_url_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_fixture(Path(td))
            _y(
                paths.src / "runtimes" / "amd.yaml",
                {
                    "variant": "amd", "label": "AMD", "version": "1",
                    "released": "260721", "channel": "lfs",
                    "parts": [{
                        "file": "runtime/amd/runtime-amd-1.tar",
                        "urls": ["https://cnb.cool/x/-/releases/download/T/runtime-amd-1.tar"],
                    }],
                },
            )
            self.assertEqual(bc.cmd_check(paths), 1)

    def test_gui_url_without_sha_fails(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_fixture(Path(td))
            _y(
                paths.src / "app.yaml",
                {"version": "1.2.0", "gui": {"version": "1.2.0",
                 "url": "https://cnb.cool/x/-/lfs/" + "d" * 64}},
            )
            self.assertEqual(bc.cmd_check(paths), 1)

    def test_bad_date_fails(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_fixture(Path(td))
            _y(
                paths.src / "voices" / "kiki.yaml",
                {"id": "kiki", "date": "next tuesday",
                 "file": "voices/kiki/kiki-v2.zip"},
            )
            self.assertEqual(bc.cmd_check(paths), 1)

    def test_good_fixture_check_passes(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_fixture(Path(td))
            self.assertEqual(bc.cmd_check(paths), 0)


class InitTests(unittest.TestCase):
    def _make_live_index(self, paths: "bc.Paths") -> None:
        """在 fixture 上先 build 一次，把产物当「线上真值」，清掉源目录。"""
        self.assertEqual(bc.cmd_build(paths), 0)
        import shutil

        shutil.rmtree(paths.src)

    def test_init_from_live_index_rebuilds_equivalent(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_fixture(Path(td))
            before = None
            self.assertEqual(bc.cmd_build(paths), 0)
            before = json.loads(paths.index_out.read_text(encoding="utf-8"))
            import shutil

            shutil.rmtree(paths.src)
            self.assertEqual(bc.cmd_init(paths), 0)
            self.assertTrue((paths.src / "voices" / "kiki.yaml").is_file())
            self.assertEqual(bc.cmd_build(paths), 0)
            after = json.loads(paths.index_out.read_text(encoding="utf-8"))
            # 语义等价：音色/packages 不缩水，series 保留
            self.assertEqual(
                [v["id"] for v in after["voices"]],
                [v["id"] for v in before["voices"]],
            )
            self.assertEqual(
                {v["id"]: v.get("series") for v in after["voices"]},
                {v["id"]: v.get("series") for v in before["voices"]},
            )
            for kind in ("setup", "engine_core", "runtime", "vbcable"):
                self.assertEqual(
                    len(after["packages"][kind]), len(before["packages"][kind]), kind
                )
            self.assertEqual(after["runtimes"].keys(), before["runtimes"].keys())

    def test_init_refuses_existing_src(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_fixture(Path(td))
            self.assertEqual(bc.cmd_init(paths), 2)

    def test_init_autotags_mygo_series_from_description(self):
        with tempfile.TemporaryDirectory() as td:
            paths = make_fixture(Path(td))
            self.assertEqual(bc.cmd_build(paths), 0)
            # 去掉 tomori 的 series（模拟线上 index 没有 series 字段）
            index = json.loads(paths.index_out.read_text(encoding="utf-8"))
            for v in index["voices"]:
                v.pop("series", None)
            paths.index_out.write_text(
                json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            import shutil

            shutil.rmtree(paths.src)
            if paths.bundled_out.is_file():
                paths.bundled_out.unlink()  # 无 bundled series 可并 → 只能靠描述
            self.assertEqual(bc.cmd_init(paths), 0)
            tomori = yaml.safe_load(
                (paths.src / "voices" / "tomori.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(tomori.get("series"), "MyGO!!!!!")


if __name__ == "__main__":
    unittest.main()
