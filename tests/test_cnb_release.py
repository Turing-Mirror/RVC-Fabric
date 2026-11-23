from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.test_build_catalog import bc, make_fixture, _y

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cnb_release as release


class ReleaseCatalogTests(unittest.TestCase):
    def test_same_version_migrates_urls_and_preserves_changelog(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = make_fixture(root)
            release.use_version("1.2.0")
            _y(paths.src / "app.yaml", {"version": "1.2.0", "gui": {
                "version": "1.2.0", "package_type": "full_package", "kind": "exe",
                "sha256": "a" * 64, "size_bytes": 12,
                "url": release.ORIGIN + "/-/releases/download/setup/" + release.NAME}})
            _y(paths.src / "changelog.yaml", {"entries": [{"version": "1.2.0", "date": "261124", "body": "Change"}]})
            self.assertEqual(bc.cmd_build(paths), 0)
            manifest = {"version": "1.2.0", "notes": "Change", "pub_date": "2026-11-24T00:00:00Z",
                        "platforms": {"windows-x86_64": {"url": "old", "signature": "signature"}}}
            (paths.cnb / "updater.json").write_text(json.dumps(manifest))
            signed = {"sha256": "a" * 64, "size_bytes": 12, "signature": "signature"}
            for _ in range(2):
                release.prepare_catalog(paths.cnb, root, signed, deepcopy(manifest), manifest["pub_date"])
            app = release.read_json(paths.index_out)["app"]
            self.assertEqual(app["gui"]["url"], release.URL)
            self.assertNotIn("cnb.cool", json.dumps(app))
            self.assertEqual(len(release.read_json(paths.cnb / "changelog.json")["entries"]), 1)
            with self.assertRaisesRegex(ValueError, "differs"):
                release.prepare_catalog(paths.cnb, root, {**signed, "signature": "different"},
                                        deepcopy(manifest), manifest["pub_date"])

    def test_publish_retains_cnb_metadata_push(self):
        with patch.object(sys, "argv", ["release", "--publish", "--version", "1.2.0"]), \
             patch.object(release, "verify_release", return_value=({}, {}, "")), \
             patch.object(release, "prepare_catalog", return_value=["index.json"]), \
             patch.object(release, "mirror_setup") as mirror, \
             patch.object(release, "run", side_effect=[None, None, "index.json", None, None]) as run:
            release.main()
        mirror.assert_called_once()
        self.assertTrue(any("push" in call.args and "HEAD:main" in call.args for call in run.call_args_list))
