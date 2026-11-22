"""Exercise local Beta publication ordering without touching GitHub or CNB."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("beta_release", ROOT / "scripts/beta_release.py")
beta = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(beta)


class FakeFeed:
    def __init__(self, events):
        self.data = None
        self.fail = False
        self.events = events
        self.advances = []
        self.fail_public = False
        self.public_checks = 0

    def read(self):
        return json.loads(self.data) if self.data is not None else None

    def advance(self, path):
        if self.fail:
            raise RuntimeError("simulated Git push rejection")
        self.data = path.read_bytes()
        self.advances.append(self.data)
        self.events.append(("push", beta.FEED_REF))

    def verify_public(self):
        self.public_checks += 1
        if self.fail_public:
            raise RuntimeError("Git pointer exists, but public verification is incomplete")
        self.events.append(("verify-public", beta.FEED_REF))


class FakeCNB:
    def __init__(self):
        self.release = {"id": "123", "tag_name": beta.TAG, "prerelease": True,
                        "is_latest": False, "assets": []}
        self.files = {}
        self.uploads = []
        self.deleted = []
        self.fail_name = None
        self.events = []
        self.feed = FakeFeed(self.events)

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
        self.events.append(("upload", path.name))
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
        for path in beta.package_files(directory, record["version"]):
            client.put(path.name, path.read_bytes())
        client.feed.data = (directory / beta.FEED_NAME).read_bytes()

    def publish(self, directory, record, client):
        return beta.publish(directory, record, client=client, feed_store=client.feed)

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

    def test_rejects_artifact_with_old_or_missing_compiled_updater_endpoint(self):
        directory, record = self.package(1)
        for endpoint in (None, beta.PUBLIC + beta.FEED_NAME):
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(ValueError, "updater endpoint"):
                beta.verify_record(directory, {**record, "updater_endpoint": endpoint})

    def test_uploads_verified_package_before_mutable_feed(self):
        directory, record = self.package(2)
        client = FakeCNB()
        with patch.object(beta, "public_download", side_effect=client.download):
            self.assertEqual(self.publish(directory, record, client), "published")
        self.assertEqual(client.events[-2:], [("push", beta.FEED_REF), ("verify-public", beta.FEED_REF)])
        self.assertTrue(all(not overwrite for _, overwrite in client.uploads))
        self.assertNotIn(beta.FEED_NAME, client.files)
        self.assertEqual(json.loads(client.feed.data)["version"], record["version"])

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
            self.assertEqual(self.publish(directory, record, client), "published")
        self.assertEqual(client.events[-2:], [("push", beta.FEED_REF), ("verify-public", beta.FEED_REF)])
        self.assertNotIn(beta.FEED_NAME, client.files)
        feed = json.loads(client.feed.data)
        self.assertEqual(feed["channel"], "beta")
        self.assertEqual(feed["data_schema"], record["data_schema"])
        self.assertEqual(feed["min_stable_version"], record["min_stable_version"])

    def test_failed_package_upload_preserves_previous_feed(self):
        older, old_record = self.package(1)
        newer, new_record = self.package(2)
        client = FakeCNB()
        self.seed(client, older, old_record)
        original = client.feed.data
        client.fail_name = new_record["installer"] + ".sig"
        with patch.object(beta, "public_download", side_effect=client.download):
            with self.assertRaisesRegex(RuntimeError, "interruption"):
                self.publish(newer, new_record, client)
        self.assertEqual(client.feed.data, original)

    def test_failed_git_push_preserves_previous_feed_and_skips_cleanup(self):
        older, old_record = self.package(1)
        newer, new_record = self.package(2)
        client = FakeCNB()
        self.seed(client, older, old_record)
        original = client.feed.data
        client.feed.fail = True
        with patch.object(beta, "public_download", side_effect=client.download):
            with self.assertRaisesRegex(RuntimeError, "Git push rejection"):
                self.publish(newer, new_record, client)
        self.assertEqual(client.feed.data, original)
        self.assertEqual(client.deleted, [])
        self.assertEqual(client.feed.advances, [])
        self.assertNotIn(beta.FEED_NAME, client.files)

    def test_public_verification_failure_skips_cleanup_and_retry_confirms_existing_feed(self):
        older, old_record = self.package(1)
        newer, new_record = self.package(2)
        client = FakeCNB()
        self.seed(client, older, old_record)
        client.feed.fail_public = True
        with patch.object(beta, "public_download", side_effect=client.download):
            with self.assertRaisesRegex(RuntimeError, "public verification is incomplete"):
                self.publish(newer, new_record, client)
            self.assertEqual(client.deleted, [])
            self.assertEqual(len(client.feed.advances), 1)
            uploads = list(client.uploads)
            client.feed.fail_public = False
            self.assertEqual(self.publish(newer, new_record, client), "already-published")
        self.assertEqual(client.uploads, uploads)
        self.assertEqual(len(client.feed.advances), 1)
        self.assertEqual(client.feed.public_checks, 2)

    def test_older_run_cannot_replace_newer_feed(self):
        older, old_record = self.package(2)
        newer, new_record = self.package(10)
        client = FakeCNB()
        self.seed(client, newer, new_record)
        with patch.object(beta, "public_download", side_effect=client.download):
            with self.assertRaisesRegex(ValueError, "older Beta"):
                self.publish(older, old_record, client)
        self.assertEqual(client.uploads, [])

    def test_same_published_source_skips_new_run_without_upload_or_cleanup(self):
        older, old_record = self.package(1)
        newer, new_record = self.package(2, commit=old_record["source_commit"])
        client = FakeCNB()
        self.seed(client, older, old_record)
        original = copy.deepcopy(client.files)
        with patch.object(beta, "public_download", side_effect=client.download) as download:
            self.assertEqual(self.publish(newer, new_record, client), "already-published-source")
        download.assert_any_call(beta.record_name(old_record["version"]),
                                 len(original[beta.record_name(old_record["version"])]))
        self.assertEqual(client.uploads, [])
        self.assertEqual(client.deleted, [])
        self.assertEqual(client.files, original)
        self.assertEqual(client.feed.advances, [])
        self.assertEqual(client.feed.public_checks, 1)

    def test_corrupt_current_build_record_cannot_skip_or_publish(self):
        older, old_record = self.package(1)
        newer, new_record = self.package(2, commit=old_record["source_commit"])
        client = FakeCNB()
        self.seed(client, older, old_record)
        name = beta.record_name(old_record["version"])
        client.files[name] = b"X" * len(client.files[name])
        with patch.object(beta, "public_download", side_effect=client.download):
            with self.assertRaisesRegex(ValueError, "build record download"):
                self.publish(newer, new_record, client)
        self.assertEqual(client.uploads, [])
        self.assertEqual(client.deleted, [])

    def test_same_source_requires_matching_compatibility_fields(self):
        directory, record = self.package(1)
        client = FakeCNB()
        self.seed(client, directory, record)
        feed = json.loads(client.feed.data)
        with patch.object(beta, "public_download", side_effect=client.download):
            self.assertTrue(beta.same_published_source(client.get_release(), feed, record))
            for field, value in (("data_schema", 2), ("min_stable_version", "1.8.1"),
                                 ("target", "windows-aarch64"), ("channel", "stable"),
                                 ("updater_endpoint", beta.PUBLIC + beta.FEED_NAME)):
                with self.subTest(field=field):
                    self.assertFalse(beta.same_published_source(
                        client.get_release(), feed, {**record, field: value}))

    def test_published_version_is_idempotent_but_cannot_change_bytes(self):
        directory, record = self.package(2)
        client = FakeCNB()
        self.seed(client, directory, record)
        with patch.object(beta, "public_download", side_effect=client.download):
            self.assertEqual(self.publish(directory, record, client), "already-published")
            (directory / record["installer"]).write_bytes(b"different")
            with self.assertRaisesRegex(ValueError, "different installer"):
                self.publish(directory, record, client)
        self.assertEqual(client.uploads, [])

    def test_retry_resumes_existing_identical_package(self):
        directory, record = self.package(2)
        client = FakeCNB()
        for path in beta.package_files(directory, record["version"])[:2]:
            client.put(path.name, path.read_bytes())
        with patch.object(beta, "public_download", side_effect=client.download):
            self.assertEqual(self.publish(directory, record, client), "published")
        uploaded = {name for name, _ in client.uploads}
        self.assertNotIn(record["installer"], uploaded)
        self.assertNotIn(beta.FEED_NAME, uploaded)
        self.assertEqual(len(client.feed.advances), 1)

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


@unittest.skipUnless(shutil.which("git"), "Git is required")
class AtomicGitFeed(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.remote = self.root / "release.git"
        subprocess.run(["git", "init", "--bare", "--quiet", str(self.remote)], check=True,
                       capture_output=True)
        self.remote_patch = patch.object(beta, "FEED_GIT_REMOTE", str(self.remote))
        self.remote_patch.start()
        self.addCleanup(self.remote_patch.stop)

    def manifest(self, number):
        path = self.root / str(number) / beta.FEED_NAME
        beta.write_json(path, {"channel": "beta", "version": f"1.8.2-beta.{number}"})
        return path

    def test_first_push_is_an_orphan_with_only_the_beta_manifest(self):
        with beta.GitFeed() as feed:
            self.assertIsNone(feed.read())
            feed.advance(self.manifest(1))
        result = subprocess.run(["git", "--git-dir", str(self.remote), "ls-tree", "--name-only",
                                 beta.FEED_REF], check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), beta.FEED_NAME)
        with beta.GitFeed() as feed:
            self.assertEqual(feed.read()["version"], "1.8.2-beta.1")
            class PublicResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    pass

                def read(self, _limit):
                    return json.dumps(feed.read()).encode("utf-8")

            with patch.object(beta.urllib.request, "urlopen", return_value=PublicResponse()) as public:
                feed.verify_public()
            request = public.call_args.args[0]
            self.assertFalse(request.has_header("Authorization"))
            self.assertEqual(request.get_header("Cache-control"), "no-cache")

    def test_competing_push_is_rejected_without_force_or_changing_remote_feed(self):
        with beta.GitFeed() as first:
            first.advance(self.manifest(1))
        with beta.GitFeed() as stale, beta.GitFeed() as current:
            current.advance(self.manifest(2))
            with self.assertRaisesRegex(RuntimeError, "Git operation failed"):
                stale.advance(self.manifest(3))
        with beta.GitFeed() as verified:
            self.assertEqual(verified.read()["version"], "1.8.2-beta.2")

    def test_refuses_a_stable_branch_or_wrong_active_ref(self):
        for branch in ("main", "tm-release", "refs/heads/beta-updates"):
            with self.subTest(branch=branch), self.assertRaises(ValueError):
                beta.GitFeed(branch=branch)
        with beta.GitFeed() as feed:
            feed.run("symbolic-ref", "HEAD", "refs/heads/main")
            with self.assertRaisesRegex(ValueError, "outside beta-updates"):
                feed.advance(self.manifest(1))


if __name__ == "__main__":
    unittest.main()
