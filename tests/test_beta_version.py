"""Beta version preparation must leave stable source and dependency versions alone."""

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("beta_version", ROOT / "scripts/beta_version.py")
beta = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(beta)


class BetaVersions(unittest.TestCase):
    def test_next_patch_and_numeric_sequence(self):
        self.assertEqual(beta.next_version("1.8.1", 12), "1.8.2-beta.12")
        self.assertEqual(beta.next_version("1.9.0", 1), "1.9.1-beta.1")

    def test_rejects_invalid_or_unrepresentable_inputs(self):
        for version, number in (("abc1234", 1), ("1.8.1-beta.1", 2), ("01.8.1", 2),
                                ("1.8.1", 0), ("1.8.1", -1), ("1.8.65535", 1)):
            with self.subTest(version=version, number=number), self.assertRaises(ValueError):
                beta.next_version(version, number)

    def test_prepares_only_temporary_application_versions(self):
        relatives = (
            "app/package.json", "app/package-lock.json", "app/src-tauri/Cargo.toml",
            "app/src-tauri/Cargo.lock", "app/src-tauri/tauri.conf.json",
            "scripts/installer/RVC_Fabric_Setup.iss", "scripts/shell_version.py",
        )
        original = {relative: (ROOT / relative).read_bytes() for relative in relatives}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in relatives:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            stable = beta.read_json(root / "app/package.json")["version"]
            expected = beta.next_version(stable, 101)
            old_config = beta.read_json(root / "app/src-tauri/tauri.conf.json")
            old_lock = beta.read_json(root / "app/package-lock.json")
            self.assertEqual(beta.prepare(root, 101), expected)
            beta.validate(root, expected)
            new_lock = beta.read_json(root / "app/package-lock.json")
            self.assertEqual(old_lock["packages"]["node_modules/react"],
                             new_lock["packages"]["node_modules/react"])
            new_config = beta.read_json(root / "app/src-tauri/tauri.conf.json")
            self.assertEqual(new_config["plugins"]["updater"], old_config["plugins"]["updater"])
            self.assertTrue(new_config["bundle"]["windows"]["allowDowngrades"])
            self.assertFalse(new_config["bundle"]["createUpdaterArtifacts"])
            self.assertIn(f'APP_VERSION: str = "{expected}"',
                          (root / "scripts/shell_version.py").read_text(encoding="utf-8"))
            self.assertEqual((root / "app/src-tauri/Cargo.lock").read_text(encoding="utf-8").count(
                f'version = "{expected}"'), 1)
        for relative, content in original.items():
            self.assertEqual((ROOT / relative).read_bytes(), content)

    def test_rejects_inconsistent_source_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            beta.write_json(root / "app/package.json", {"version": "1.8.1"})
            beta.write_json(root / "app/package-lock.json", {
                "version": "1.8.0", "packages": {"": {"version": "1.8.0"}},
            })
            beta.write_json(root / "app/src-tauri/tauri.conf.json", {"version": "1.8.1"})
            before = (root / "app/package.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "inconsistent"):
                beta.prepare(root, 10)
            self.assertEqual((root / "app/package.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
