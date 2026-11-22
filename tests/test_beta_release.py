"""Exercise local Beta publication ordering without touching GitHub or CNB."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("beta_release", ROOT / "scripts/beta_release.py")
beta = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(beta)


class FakeCNB:
    def __init__(self):
        self.release = {"id": "123", "tag_name": beta.TAG, "prerelease": True,
                        "is_latest": False, "assets": []}
        self.files = {}
        self.uploads = []
        self.deleted = []
        self.fail_name = None

    def get_release(self):
        return copy.deepcopy(self.release)

    def create_release(self):
        return self.get_release()

    def patch_release(self, release_id):
        self.assert_release(release_id)

    def assert_release(self, release_id):
        if release_id != "123":
            raise AssertionError("Changed a release other than Beta")

    def put(self, name, data):
        self.files[name] = data
        self.release["assets"] = [item for item in self.release["assets"] if item["name"] != name]
        self.release["assets"].append({
            "id": name, "name": name, "size": len(data), "hash_algo": "sha256",
            "hash_value": hashlib.sha256(data).hexdigest(),
        })

    def upload(self, release_id, path, *, overwrite):
        self.assert_release(release_id)
        if path.name == self.fail_name:
            raise RuntimeError("simulated upload interruption")
        if path.name in self.files and not overwrite:
            raise AssertionError("Tried to replace an immutable artifact")
        self.uploads.append((path.name, overwrite))
        self.put(path.name, path.read_bytes())

    def download(self, name, expected_size=None):
        data = self.files[name]
        if expected_size is not None and len(data) != expected_size:
            raise ValueError("wrong download size")
        return data

    def delete(self, release_id, asset_id):
        self.assert_release(release_id)
        self.deleted.append(asset_id)
        self.files.pop(asset_id)
        self.release["assets"] = [item for item in self.release["assets"] if item["id"] != asset_id]


class BetaPublication(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.pe = patch.object(beta, "inspect_pe")
        self.pe.start()
        self.addCleanup(self.pe.stop)
        self.signature = patch.object(beta, "verify_installer", side_effect=self.signed)
        self.signature.start()
        self.addCleanup(self.signature.stop)

    def signed(self, path, *args):
        return {"sha256": beta.digest(path), "size_bytes": path.stat().st_size,
                "pub_date": "2026-11-22T00:00:00Z", "signature": "fixture-signature"}

    def package(self, number, *, commit=None):
        version = f"1.8.2-beta.{number}"
        directory = self.root / str(number)
        directory.mkdir()
        installer = directory / beta.installer_name(version)
        installer.write_bytes(("installer " + version).encode("utf-8"))
        (directory / (installer.name + ".sig")).write_text("fixture-signature", encoding="utf-8")
        (directory / (installer.name + ".sha256")).write_text(
            beta.digest(installer) + "  " + installer.name + "\n", encoding="utf-8")
        record = beta.prepare_metadata(directory, version, commit or f"{number:040x}", str(number))
        return directory, record

    def seed(self, client, directory, record):
        for path in beta.package_files(directory, record["version"]) + [directory / beta.FEED_NAME]:
            client.put(path.name, path.read_bytes())

    def test_metadata_and_selected_run_identity_match(self):
        directory, record = self.package(12, commit="a" * 40)
        beta.verify_record(directory, record, run={"id": 12, "head_sha": "a" * 40, "run_number": 12})
        with self.assertRaisesRegex(ValueError, "selected GitHub"):
            beta.verify_record(directory, record, run={"id": 12, "head_sha": "b" * 40, "run_number": 12})
        self.assertEqual(beta.version_key("1.8.2-beta.10") > beta.version_key("1.8.2-beta.2"), True)

    def test_rejects_hash_versions_and_same_size_corruption(self):
        for version in ("abc1234", "1.8.2-beta.gabc1234", "1.8.2-beta.12+gabc1234", "1.8.2-beta.0"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                beta.installer_name(version)
        directory, record = self.package(1)
        installer = directory / record["installer"]
        installer.write_bytes(b"X" * installer.stat().st_size)
        with self.assertRaisesRegex(ValueError, "bytes"):
            beta.verify_record(directory, record)

    def test_rejects_feed_for_another_channel_or_package(self):
        directory, record = self.package(1)
        feed = beta.read_json(directory / beta.FEED_NAME)
        for field, value in (("channel", "stable"), ("version", "1.8.2-beta.2"), ("data_schema", 999)):
            beta.write_json(directory / beta.FEED_NAME, {**feed, field: value})
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "feed"):
                beta.verify_record(directory, record)

    def test_uploads_verified_package_before_mutable_feed(self):
        directory, record = self.package(2)
        client = FakeCNB()
        with patch.object(beta, "public_download", side_effect=client.download):
            self.assertEqual(beta.publish(directory, record, client=client), "published")
        self.assertEqual(client.uploads[-1], (beta.FEED_NAME, True))
        self.assertTrue(all(not overwrite for _, overwrite in client.uploads[:-1]))
        self.assertEqual(json.loads(client.files[beta.FEED_NAME])["version"], record["version"])

    def test_first_publication_accepts_cnb_nullable_empty_release_assets(self):
        directory, record = self.package(1)
        client = FakeCNB()
        client.release["assets"] = None
        self.assertEqual(beta.assets_by_name(client.get_release()), {})
        original_put = client.put

        def put(name, data):
            if client.release["assets"] is None:
                client.release["assets"] = []
            original_put(name, data)

        with patch.object(client, "put", side_effect=put), patch.object(
                beta, "public_download", side_effect=client.download):
            self.assertEqual(beta.publish(directory, record, client=client), "published")
        self.assertEqual(client.uploads[-1], (beta.FEED_NAME, True))
        feed = json.loads(client.files[beta.FEED_NAME])
        self.assertEqual(feed["channel"], "beta")
        self.assertEqual(feed["data_schema"], record["data_schema"])
        self.assertEqual(feed["min_stable_version"], record["min_stable_version"])

    def test_failed_package_upload_preserves_previous_feed(self):
        older, old_record = self.package(1)
        newer, new_record = self.package(2)
        client = FakeCNB()
        self.seed(client, older, old_record)
        original = client.files[beta.FEED_NAME]
        client.fail_name = new_record["installer"] + ".sig"
        with patch.object(beta, "public_download", side_effect=client.download):
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                beta.publish(newer, new_record, client=client)
        self.assertEqual(client.files[beta.FEED_NAME], original)

    def test_older_run_cannot_replace_newer_feed(self):
        older, old_record = self.package(2)
        newer, new_record = self.package(10)
        client = FakeCNB()
        self.seed(client, newer, new_record)
        with patch.object(beta, "public_download", side_effect=client.download):
            with self.assertRaisesRegex(ValueError, "older Beta"):
                beta.publish(older, old_record, client=client)
        self.assertEqual(client.uploads, [])

    def test_same_published_source_skips_new_run_without_upload_or_cleanup(self):
        older, old_record = self.package(1)
        newer, new_record = self.package(2, commit=old_record["source_commit"])
        client = FakeCNB()
        self.seed(client, older, old_record)
        original = copy.deepcopy(client.files)
        with patch.object(beta, "public_download", side_effect=client.download) as download:
            self.assertEqual(beta.publish(newer, new_record, client=client), "already-published-source")
        download.assert_any_call(beta.record_name(old_record["version"]),
                                 len(original[beta.record_name(old_record["version"])]))
        self.assertEqual(client.uploads, [])
        self.assertEqual(client.deleted, [])
        self.assertEqual(client.files, original)

    def test_corrupt_current_build_record_cannot_skip_or_publish(self):
        older, old_record = self.package(1)
        newer, new_record = self.package(2, commit=old_record["source_commit"])
        client = FakeCNB()
        self.seed(client, older, old_record)
        name = beta.record_name(old_record["version"])
        client.files[name] = b"X" * len(client.files[name])
        with patch.object(beta, "public_download", side_effect=client.download):
            with self.assertRaisesRegex(ValueError, "build record download"):
                beta.publish(newer, new_record, client=client)
        self.assertEqual(client.uploads, [])
        self.assertEqual(client.deleted, [])

    def test_same_source_requires_matching_compatibility_fields(self):
        directory, record = self.package(1)
        client = FakeCNB()
        self.seed(client, directory, record)
        feed = json.loads(client.files[beta.FEED_NAME])
        with patch.object(beta, "public_download", side_effect=client.download):
            self.assertTrue(beta.same_published_source(client.get_release(), feed, record))
            for field, value in (("data_schema", 2), ("min_stable_version", "1.8.1"),
                                 ("target", "windows-aarch64"), ("channel", "stable")):
                with self.subTest(field=field):
                    self.assertFalse(beta.same_published_source(
                        client.get_release(), feed, {**record, field: value}))

    def test_published_version_is_idempotent_but_cannot_change_bytes(self):
        directory, record = self.package(2)
        client = FakeCNB()
        self.seed(client, directory, record)
        with patch.object(beta, "public_download", side_effect=client.download):
            self.assertEqual(beta.publish(directory, record, client=client), "already-published")
            (directory / record["installer"]).write_bytes(b"different")
            with self.assertRaisesRegex(ValueError, "different installer"):
                beta.publish(directory, record, client=client)
        self.assertEqual(client.uploads, [])

    def test_retry_resumes_existing_identical_package(self):
        directory, record = self.package(2)
        client = FakeCNB()
        for path in beta.package_files(directory, record["version"])[:2]:
            client.put(path.name, path.read_bytes())
        with patch.object(beta, "public_download", side_effect=client.download):
            self.assertEqual(beta.publish(directory, record, client=client), "published")
        uploaded = {name for name, _ in client.uploads}
        self.assertNotIn(record["installer"], uploaded)
        self.assertIn(beta.FEED_NAME, uploaded)

    def test_cleanup_keeps_ten_recent_versions_and_current(self):
        client = FakeCNB()
        for number in range(1, 13):
            for name in (beta.installer_name(f"1.8.2-beta.{number}"), beta.record_name(f"1.8.2-beta.{number}")):
                client.put(name, name.encode("utf-8"))
        client.put("readme.txt", b"unrelated")
        beta.cleanup(client, client.get_release(), "1.8.2-beta.1", keep=10)
        self.assertIn(beta.installer_name("1.8.2-beta.1"), client.files)
        self.assertNotIn(beta.installer_name("1.8.2-beta.2"), client.files)
        self.assertIn(beta.installer_name("1.8.2-beta.3"), client.files)
        self.assertIn("readme.txt", client.files)

    def test_refuses_to_modify_a_non_beta_release(self):
        with self.assertRaisesRegex(ValueError, "outside setup-beta"):
            beta.assets_by_name({"tag_name": "setup", "assets": []})

    def test_local_publication_lock_rejects_overlapping_runs(self):
        with beta.publication_lock():
            with self.assertRaisesRegex(RuntimeError, "already running"):
                with beta.publication_lock():
                    self.fail("overlapping publisher obtained the lock")

    def test_cli_timeout_does_not_print_upload_credentials(self):
        command = ["cnb", "releases", "confirm", "--upload-token", "private-upload-token"]
        with patch.object(beta.subprocess, "run", side_effect=beta.subprocess.TimeoutExpired(command, 1)):
            with self.assertRaisesRegex(RuntimeError, "cnb timed out") as raised:
                beta.run_json(command, timeout=1)
        self.assertNotIn("private-upload-token", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
