"""Cloud provenance and corruption checks for the local release handoff."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepare_setup_release.py"
SPEC = importlib.util.spec_from_file_location("prepare_setup_release", SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class CandidateValidationTests(unittest.TestCase):
    def setUp(self):
        self.commit = "a" * 40
        self.metadata = {
            "commit": self.commit, "version": "1.7.2", "target": "x86_64-pc-windows-msvc",
            "file": "RVC_Fabric_1.7.2_cnb-aaaaaaaaaaaa_x64-setup.exe",
        }

    def test_rejects_other_commit_version_target_and_path(self):
        for field, value in (("commit", "b" * 40), ("version", "1.7.1"),
                             ("target", "aarch64-pc-windows-msvc"), ("file", "../other.exe")):
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                release.validate_candidate({**self.metadata, field: value}, self.commit, "1.7.2")

    def test_accepts_exact_source_identity(self):
        self.assertEqual(release.validate_candidate(self.metadata, self.commit, "1.7.2"),
                         self.metadata["file"])

    def test_download_hash_detects_same_size_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "setup.exe"
            path.write_bytes(b"valid installer fixture")
            asset = {"hash_algo": "sha256", "size_in_byte": path.stat().st_size,
                     "hash_value": release.digest(path)}
            release.verify_asset(path, asset)
            path.write_bytes(b"wrong installer fixture")
            with self.assertRaises(RuntimeError):
                release.verify_asset(path, asset)

    def test_missing_key_does_not_leave_previous_release_metadata(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.exe"
            source.write_bytes(b"test")
            output = root / "out"
            output.mkdir()
            (output / "release-input.json").write_text('{"signature_verified":true}')
            (output / "RVC Fabric_1.7.2_x64-setup.exe.sig").write_text("stale signature")
            with patch.dict(release.os.environ, {}, clear=True), self.assertRaises(RuntimeError):
                release.prepare(source, output, "1.7.2", {})
            self.assertFalse((output / "release-input.json").exists())
            self.assertFalse((output / "RVC Fabric_1.7.2_x64-setup.exe.sig").exists())

    def test_failed_cloud_download_invalidates_previous_release_metadata(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            previous = output / "release-input.json"
            previous.write_text('{"signature_verified":true}')
            argv = ["prepare_setup_release.py", "--source", "cnb", "--commit", self.commit,
                    "--out", str(output)]
            with patch("sys.argv", argv), patch.object(
                    release, "download_candidate", side_effect=RuntimeError("download failed")):
                with self.assertRaisesRegex(RuntimeError, "download failed"):
                    release.main()
            self.assertFalse(previous.exists())


if __name__ == "__main__":
    unittest.main()
