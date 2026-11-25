"""The app must ship the pinned crate's exact eight-language diagnostic copy."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import sync_diag_locales as catalog


class DiagnosticLocaleTests(unittest.TestCase):
    @unittest.skipUnless((catalog.DEFAULT_CRATE / "locales").is_dir(), "diagnostics crate not checked out")
    def test_shipping_catalogs_match_the_crate(self):
        self.assertEqual(catalog.sync(check=True), [])

    def test_check_detects_drift_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "crate" / "locales"
            target = root / "app" / "i18n" / "locales"
            source.mkdir(parents=True)
            target.mkdir(parents=True)
            (source / "zh-CN.json").write_text(json.dumps({"diag.title.training": "expected"}), encoding="utf-8")
            destination = target / "zh-CN.json"
            destination.write_text(json.dumps({"diag": {"title": {"training": "changed"}}}), encoding="utf-8")
            before = destination.read_bytes()
            with patch.object(catalog, "ROOT", root):
                self.assertEqual(catalog.sync(root / "crate", check=True), ["zh-CN.json"])
            self.assertEqual(destination.read_bytes(), before)
