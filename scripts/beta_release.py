"""Verify a signed GitHub Beta artifact and optionally publish it locally to CNB.

Cloud builds call --prepare after signing. Local use defaults to a download and
verification only; --publish uploads immutable setup-beta attachments, then
advances the updater pointer through the independent beta-updates Git branch.
CNB authentication is delegated to the installed CLI, never copied to GitHub.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from beta_version import BETA, ROOT, read_json, write_json


SOURCE_REPO = "Turing-Mirror/RVC-Fabric"
CNB_REPO = "Turing-Mirror/RVC-Fabric-Releases"
TAG = "setup-beta"
ARTIFACT = "RVC Fabric Beta x64"
FEED_NAME = "updater-beta.json"
FEED_BRANCH = "beta-updates"
FEED_REF = "refs/heads/" + FEED_BRANCH
FEED_GIT_REMOTE = f"https://cnb.cool/{CNB_REPO}.git"
PUBLIC = f"https://cnb.cool/{CNB_REPO}/-/releases/download/{TAG}/"
ALLOWED_BRANCHES = {"tm-release", "codex/beta-channel"}
USER_AGENT = "RVC-Fabric-Beta-Publisher"


def version_key(version: str) -> tuple[int, ...]:
    match = BETA.fullmatch(version)
    if not match:
        raise ValueError("Use a plain X.Y.Z-beta.N version")
    return tuple(map(int, match.groups()))


def installer_name(version: str) -> str:
    version_key(version)
    return f"RVC-Fabric-Setup-{version}.exe"


def record_name(version: str) -> str:
    version_key(version)
    return f"build-{version}.json"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def executable(name: str) -> str:
    found = shutil.which(name + ".cmd") or shutil.which(name)
    if found:
        return found
    if name == "cnb":
        candidate = Path.home() / ".cnb/bin/cnb.exe"
    elif name == "gh":
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "GitHub CLI/gh.exe"
    else:
        raise RuntimeError(f"Required executable is missing: {name}")
    if not candidate.is_file():
        raise RuntimeError(f"Required executable is missing: {name}")
    return str(candidate)


def run_json(command: list[str], *, timeout: int = 300) -> dict:
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{Path(command[0]).name} timed out") from None
    if result.returncode:
        # CLI diagnostics may include temporary signed URLs or local credentials.
        raise RuntimeError(f"{Path(command[0]).name} failed (exit {result.returncode})")
    return json.loads(result.stdout)


def inspect_pe(path: Path, version: str) -> None:
    """PE numeric versions omit prerelease; the string must retain beta.N."""
    if os.name != "nt":
        raise RuntimeError("Installer version inspection requires Windows")
    from ctypes import wintypes
    api = ctypes.WinDLL("version", use_last_error=True)
    api.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    api.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    api.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR,
                                 ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    size = api.GetFileVersionInfoSizeW(str(path), None)
    buffer = ctypes.create_string_buffer(size)
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if (not size or not api.GetFileVersionInfoW(str(path), 0, size, buffer) or
            not api.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)) or
            length.value < 52):
        raise ValueError("Cannot inspect installer version resources")
    info = ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD * 13)).contents
    actual = (info[4] >> 16, info[4] & 65535, info[5] >> 16, info[5] & 65535)
    if info[0] != 0xFEEF04BD or actual != version_key(version)[:3] + (0,):
        raise ValueError("Installer numeric product version does not match Beta")
    if not api.VerQueryValueW(buffer, "\\VarFileInfo\\Translation", ctypes.byref(pointer), ctypes.byref(length)):
        raise ValueError("Installer version translation is missing")
    words = ctypes.cast(pointer, ctypes.POINTER(wintypes.WORD))
    query = f"\\StringFileInfo\\{words[0]:04x}{words[1]:04x}\\ProductVersion"
    if not api.VerQueryValueW(buffer, query, ctypes.byref(pointer), ctypes.byref(length)):
        raise ValueError("Installer string product version is missing")
    if ctypes.wstring_at(pointer, max(0, length.value - 1)) != version:
        raise ValueError("Installer string version does not match Beta")


def verify_installer(path: Path, channels_path: Path = ROOT / "app/src-tauri/update-channels.json") -> dict:
    return run_json([executable("node"), str(ROOT / "scripts/beta_verify.mjs"),
                     str(path.resolve()), str(channels_path.resolve())])


def prepare_metadata(directory: Path, version: str, commit: str, run_id: str,
                     *, channels_path: Path = ROOT / "app/src-tauri/update-channels.json") -> dict:
    version_key(version)
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(r"[1-9]\d*", run_id):
        raise ValueError("Missing complete source/build identity")
    installer = directory / installer_name(version)
    inspect_pe(installer, version)
    signed = verify_installer(installer, channels_path)
    sidecar = installer.with_name(installer.name + ".sha256")
    expected = signed["sha256"] + "  " + installer.name
    if sidecar.read_text(encoding="utf-8-sig").strip() != expected:
        raise ValueError("Installer checksum sidecar mismatch")
    channels = read_json(channels_path)
    record = {
        "version": version, "channel": "beta", "source_commit": commit,
        "run_id": run_id, "run_number": version_key(version)[3],
        "run_url": f"https://github.com/{SOURCE_REPO}/actions/runs/{run_id}",
        "target": "windows-x86_64", "installer": installer.name,
        "size_bytes": signed["size_bytes"], "sha256": signed["sha256"],
        "pub_date": signed["pub_date"], "data_schema": channels["data_schema"],
        "min_stable_version": channels["minimum_stable_version"],
        "updater_endpoint": channels["beta"]["endpoint"],
    }
    write_json(directory / record_name(version), record)
    feed = {
        "version": version, "channel": "beta", "data_schema": record["data_schema"],
        "min_stable_version": record["min_stable_version"], "pub_date": signed["pub_date"],
        "notes": f"RVC Fabric {version}\n\n自动构建的 Beta 预览版。可在“在线更新”页切换回正式版。",
        "platforms": {"windows-x86_64": {"url": PUBLIC + installer.name, "signature": signed["signature"]}},
    }
    write_json(directory / FEED_NAME, feed)
    return record


def verify_record(directory: Path, record: dict, *, run: dict | None = None) -> None:
    version = record["version"]
    channels = read_json(ROOT / "app/src-tauri/update-channels.json")
    if record.get("updater_endpoint") != channels["beta"]["endpoint"]:
        raise ValueError("Beta artifact updater endpoint does not match this client")
    installer = directory / installer_name(version)
    if record["installer"] != installer.name or record["channel"] != "beta" or record["target"] != "windows-x86_64":
        raise ValueError("Beta artifact identity is inconsistent")
    if run is not None and (str(record["run_id"]) != str(run["id"]) or record["source_commit"] != run["head_sha"]
                            or record["run_number"] != run["run_number"]):
        raise ValueError("Beta artifact does not match the selected GitHub run")
    if record["run_number"] != version_key(version)[3]:
        raise ValueError("Beta build number does not match its version")
    if installer.stat().st_size != record["size_bytes"] or digest(installer) != record["sha256"]:
        raise ValueError("Beta artifact installer bytes are inconsistent")
    inspect_pe(installer, version)
    signed = verify_installer(installer)
    if (signed["sha256"] != record["sha256"] or signed["pub_date"] != record["pub_date"] or
            (directory / (installer.name + ".sha256")).read_text(encoding="utf-8-sig").strip()
            != record["sha256"] + "  " + installer.name):
        raise ValueError("Beta artifact signature or checksum is inconsistent")
    feed = read_json(directory / FEED_NAME)
    expected_platform = {"url": PUBLIC + installer.name, "signature": signed["signature"]}
    if (record.get("data_schema") != channels["data_schema"] or
            record.get("min_stable_version") != channels["minimum_stable_version"] or
            feed.get("version") != version or feed.get("channel") != "beta" or
            feed.get("pub_date") != signed["pub_date"] or
            feed.get("data_schema") != channels["data_schema"] or
            feed.get("min_stable_version") != channels["minimum_stable_version"] or
            feed.get("platforms", {}).get("windows-x86_64") != expected_platform):
        raise ValueError("Beta updater feed does not match the verified package")


def fetch_run(run_id: str, destination: Path) -> dict:
    if not re.fullmatch(r"[1-9]\d*", run_id):
        raise ValueError("Use a numeric GitHub Actions run ID")
    gh = executable("gh")
    run = run_json([gh, "api", f"repos/{SOURCE_REPO}/actions/runs/{run_id}"])
    if (run.get("status") != "completed" or run.get("conclusion") != "success" or
            run.get("path", "").split("@")[0] != ".github/workflows/windows-beta.yml" or
            run.get("head_branch") not in ALLOWED_BRANCHES or
            run.get("event") not in {"push", "workflow_dispatch"}):
        raise ValueError("Select a successful trusted Beta workflow run")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rvc-beta-download-") as scratch:
        command = [gh, "run", "download", run_id, "--repo", SOURCE_REPO,
                   "--name", ARTIFACT, "--dir", scratch]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=600)
        if result.returncode:
            raise RuntimeError("Unable to download the signed Beta artifact")
        staging = Path(scratch)
        records = list(staging.glob("build-*-beta.*.json"))
        if len(records) != 1:
            raise ValueError("Expected exactly one Beta build record")
        record = read_json(records[0])
        verify_record(staging, record, run=run)
        for path in package_files(staging, record["version"]) + [staging / FEED_NAME]:
            output = destination / path.name
            if output.exists() and digest(output) != digest(path):
                raise ValueError("The local destination already contains a different Beta artifact")
            shutil.copyfile(path, output)
    return record


class CNBError(RuntimeError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"CNB operation failed (HTTP {status})")


class CNBClient:
    """Use current local CLI credentials; do not inspect credential files."""

    def call(self, command: str, *arguments: str, data: dict | None = None):
        args = [executable("cnb"), "releases", command, "--repo", CNB_REPO, *arguments, "--verbose"]
        if data is not None:
            args += ["--data", json.dumps(data, ensure_ascii=False)]
        result = run_json(args)
        status = result.get("status", 0)
        if status not in {200, 201, 204}:
            raise CNBError(status)
        return result.get("data")

    def get_release(self):
        try:
            return self.call("get-release-by-tag", "--tag", TAG)
        except CNBError as error:
            if error.status == 404:
                return None
            raise

    def create_release(self):
        return self.call("post-release", data={
            "tag_name": TAG, "target_commitish": "main", "name": "RVC Fabric Beta 安装包",
            "body": "Beta 预览版。正式版下载请使用 setup，当前 Beta 版本以附件及更新清单为准。",
            "prerelease": True, "draft": False, "make_latest": "false",
        })

    def patch_release(self, release_id: str):
        return self.call("patch-release", "--release-id", release_id,
                         data={"prerelease": True, "make_latest": "false"})

    def upload(self, release_id: str, path: Path, *, overwrite: bool):
        if overwrite or path.name == FEED_NAME:
            raise ValueError("Beta Release attachments are immutable; the feed belongs in Git")
        result = self.call("post-release-asset-upload-url", "--release-id", release_id, data={
            "asset_name": path.name, "size": path.stat().st_size, "overwrite": overwrite, "ttl": 0,
        })
        upload_url = result["upload_url"]
        verify = urllib.parse.urlsplit(result["verify_url"])
        match = re.search(r"/asset-upload-confirmation/([^/]+)/(.+)", verify.path)
        if urllib.parse.urlsplit(upload_url).scheme != "https" or not match:
            raise ValueError("CNB returned an invalid upload descriptor")
        token = urllib.parse.unquote(match[1])
        asset_path = urllib.parse.unquote(match[2])
        expected_path = f"/{CNB_REPO}/-/releases/download/{TAG}/{path.name}"
        if asset_path != expected_path:
            raise ValueError("CNB returned an unexpected Beta upload path")
        try:
            with path.open("rb") as stream:
                request = urllib.request.Request(upload_url, data=stream, method="PUT", headers={
                    "Content-Length": str(path.stat().st_size), "User-Agent": USER_AGENT,
                })
                with urllib.request.urlopen(request, timeout=180) as response:
                    if response.status not in {200, 201, 204}:
                        raise RuntimeError("CNB upload did not complete")
        except (urllib.error.URLError, OSError):
            # Never print presigned URLs, even on transport errors.
            raise RuntimeError("CNB attachment upload failed; query remote state before retrying") from None
        self.call("post-release-asset-upload-confirmation", "--release-id", release_id,
                  "--upload-token", token, "--asset-path", asset_path, "--ttl", "0")

    def delete(self, release_id: str, asset_id: str):
        return self.call("delete-release-asset", "--release-id", release_id, "--asset-id", asset_id)


def public_download(name: str, expected_size: int | None = None) -> bytes:
    url = PUBLIC + urllib.parse.quote(name, safe="")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            limit = expected_size + 1 if expected_size is not None else 2 * 1024 * 1024
            data = response.read(limit)
    except urllib.error.HTTPError as error:
        raise CNBError(error.code) from None
    except (urllib.error.URLError, OSError):
        raise RuntimeError("Unable to verify the public CNB attachment download") from None
    if expected_size is not None and len(data) != expected_size:
        raise ValueError("Public CNB attachment length mismatch")
    return data


def package_files(directory: Path, version: str) -> list[Path]:
    name = installer_name(version)
    return [directory / name, directory / (name + ".sig"), directory / (name + ".sha256"),
            directory / record_name(version)]


def assets_by_name(release: dict) -> dict:
    if release.get("tag_name") != TAG:
        raise ValueError("Refusing to modify a release outside setup-beta")
    return {asset["name"]: asset for asset in (release.get("assets") or [])}


def asset_matches(asset: dict, path: Path) -> bool:
    return (asset.get("hash_algo") == "sha256" and asset.get("hash_value") == digest(path) and
            asset.get("size", asset.get("size_in_byte")) == path.stat().st_size)


def wait_for_asset(client: CNBClient, path: Path) -> dict:
    for delay in (0, 2, 5, 10, 20):
        if delay:
            time.sleep(delay)
        release = client.get_release()
        asset = assets_by_name(release).get(path.name)
        if asset is not None and asset_matches(asset, path):
            downloaded = public_download(path.name, path.stat().st_size)
            if hashlib.sha256(downloaded).hexdigest() == digest(path):
                return release
    raise ValueError("CNB server or public download does not match the verified Beta attachment")


class GitFeed:
    """A disposable checkout that can only fast-forward beta-updates."""

    def __init__(self, branch: str = FEED_BRANCH):
        if branch != FEED_BRANCH:
            raise ValueError("Only the beta-updates branch may hold the Beta feed")
        self.temporary = None
        self.root = None
        self.env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}

    def run(self, *arguments: str, accepted=(0,)) -> subprocess.CompletedProcess:
        command = [executable("git")]
        if self.env.get("CNB_TOKEN"):
            # Use only the explicit token through askpass, not a stale helper.
            command += ["-c", "credential.helper=", "-c", "credential.username=cnb"]
        command += list(arguments)
        try:
            result = subprocess.run(command, cwd=self.root, env=self.env, capture_output=True,
                                    text=True, encoding="utf-8", timeout=180)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Beta feed Git operation timed out; verify remote state before retrying") from None
        if result.returncode not in accepted:
            raise RuntimeError("Beta feed Git operation failed; verify remote state before retrying")
        return result

    def __enter__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rvc-beta-feed-")
        scratch = Path(self.temporary.name)
        self.root = scratch / "repository"
        self.root.mkdir()
        if self.env.get("CNB_TOKEN"):
            askpass = scratch / "askpass.sh"
            askpass.write_text(
                '#!/bin/sh\ncase "$1" in\n*sername*) printf "%s\\n" "cnb" ;;\n'
                '*) printf "%s\\n" "$CNB_TOKEN" ;;\nesac\n', encoding="utf-8",
            )
            askpass.chmod(0o700)
            self.env["GIT_ASKPASS"] = str(askpass)
        try:
            self.run("init", "--quiet")
            self.run("remote", "add", "origin", FEED_GIT_REMOTE)
            exists = self.run("ls-remote", "--exit-code", "origin", FEED_REF, accepted=(0, 2))
            if exists.returncode == 0:
                self.run("fetch", "--quiet", "--no-tags", "origin", FEED_REF)
                self.run("checkout", "--quiet", "-b", FEED_BRANCH, "FETCH_HEAD")
            else:
                self.run("checkout", "--quiet", "--orphan", FEED_BRANCH)
            return self
        except Exception:
            self.temporary.cleanup()
            raise

    def __exit__(self, *_):
        if self.temporary is not None:
            self.temporary.cleanup()

    def read(self) -> dict | None:
        path = self.root / FEED_NAME
        return read_json(path) if path.is_file() else None

    def advance(self, path: Path) -> None:
        if self.run("symbolic-ref", "HEAD").stdout.strip() != FEED_REF:
            raise ValueError("Refusing to push a feed outside beta-updates")
        feed = read_json(path)
        version_key(feed["version"])
        if feed.get("channel") != "beta" or path.name != FEED_NAME:
            raise ValueError("Only the Beta updater manifest may be committed")
        write_json(self.root / FEED_NAME, feed)
        self.run("add", "--", FEED_NAME)
        self.run("-c", "user.name=RVC Fabric Beta Publisher", "-c", "user.email=beta@turingmirror.com",
                 "-c", "commit.gpgSign=false", "commit", "--quiet", "-m", f"Publish Beta {feed['version']}",
                 "--", FEED_NAME)
        # A concurrent publisher changes the remote parent and this normal push
        # fails rather than replacing their pointer. Never use force/lease.
        self.run("push", "origin", "HEAD:" + FEED_REF)

    def verify_public(self) -> None:
        expected = self.read()
        endpoint = read_json(ROOT / "app/src-tauri/update-channels.json")["beta"]["endpoint"]
        if urllib.parse.urlsplit(endpoint).scheme != "https":
            raise ValueError("The public Beta feed requires HTTPS")
        for delay in (0, 2, 5, 10):
            if delay:
                time.sleep(delay)
            request = urllib.request.Request(endpoint, headers={
                "User-Agent": USER_AGENT, "Cache-Control": "no-cache",
            })
            try:
                # This is deliberately anonymous: a client must be able to read
                # the pointer without any local CLI or Git credentials.
                with urllib.request.urlopen(request, timeout=30) as response:
                    actual = json.loads(response.read(2 * 1024 * 1024))
                if actual == expected:
                    return
            except (urllib.error.URLError, OSError, ValueError):
                pass
        raise RuntimeError("Beta feed Git pointer exists, but public verification is incomplete; retry publication")


def current_feed(store) -> dict | None:
    feed = store.read()
    if feed is None:
        return None
    version_key(feed["version"])
    if feed.get("channel") != "beta":
        raise ValueError("Current Beta feed has an unexpected channel")
    return feed


def same_published_source(release: dict, feed: dict, candidate: dict) -> bool:
    """Do not publish another build of the currently served, compatible source."""
    name = record_name(feed["version"])
    asset = assets_by_name(release).get(name)
    if asset is None:
        return False
    size = asset.get("size", asset.get("size_in_byte"))
    if not isinstance(size, int) or size < 0 or asset.get("hash_algo") != "sha256":
        raise ValueError("Current Beta build record cannot be verified")
    data = public_download(name, size)
    if len(data) != size or hashlib.sha256(data).hexdigest() != asset.get("hash_value"):
        raise ValueError("Current Beta build record download is stale or corrupt; retry later")
    previous = json.loads(data)
    if (previous.get("version") != feed["version"] or
            previous.get("installer") != installer_name(feed["version"]) or
            any(previous.get(field) != feed.get(field)
                for field in ("channel", "data_schema", "min_stable_version"))):
        raise ValueError("Current Beta build record and updater feed disagree")
    source = previous.get("source_commit")
    return (isinstance(source, str) and re.fullmatch(r"[0-9a-f]{40}", source) is not None and
            source == candidate.get("source_commit") and
            all(previous.get(field) == candidate.get(field)
                for field in ("channel", "target", "data_schema", "min_stable_version", "updater_endpoint")))


def cleanup(client: CNBClient, release: dict, current: str, keep: int = 10) -> None:
    groups: dict[str, list[dict]] = {}
    pattern = re.compile(r"(?:RVC-Fabric-Setup-(.+)\.exe(?:\.sig|\.sha256)?|build-(.+)\.json)\Z")
    for asset in assets_by_name(release).values():
        match = pattern.fullmatch(asset["name"])
        if match:
            version = match[1] or match[2]
            if BETA.fullmatch(version):
                groups.setdefault(version, []).append(asset)
    retain = set(sorted(groups, key=version_key, reverse=True)[:keep]) | {current}
    for version, assets in groups.items():
        if version not in retain:
            for asset in assets:
                client.delete(str(release["id"]), str(asset["id"]))


@contextmanager
def publication_lock():
    """Prevent two local publishers from racing the mutable update pointer."""
    if os.name == "nt":
        from ctypes import wintypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        api.CreateMutexW.restype = wintypes.HANDLE
        api.ReleaseMutex.argtypes = [wintypes.HANDLE]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.CreateMutexW(None, True, "Local\\RVCFabricBetaPublisher")
        already_exists = ctypes.get_last_error() == 183
        if not handle or already_exists:
            if handle:
                api.CloseHandle(handle)
            raise RuntimeError("Another local Beta publication is already running")
        try:
            yield
        finally:
            api.ReleaseMutex(handle)
            api.CloseHandle(handle)
    else:
        import fcntl
        with (Path(tempfile.gettempdir()) / "rvc-fabric-beta-publisher.lock").open("a") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another local Beta publication is already running") from None
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def publish(directory: Path, record: dict, *, client: CNBClient | None = None,
            keep: int = 10, feed_store=None) -> str:
    with publication_lock():
        if feed_store is not None:
            return publish_locked(directory, record, client=client, keep=keep, feed_store=feed_store)
        with GitFeed() as store:
            return publish_locked(directory, record, client=client, keep=keep, feed_store=store)


def publish_locked(directory: Path, record: dict, *, client: CNBClient | None = None,
                   keep: int = 10, feed_store) -> str:
    if keep < 2:
        raise ValueError("Keep at least the current and previous Beta")
    client = client or CNBClient()
    version = record["version"]
    release = client.get_release()
    if release is None:
        release = client.create_release()
    existing = assets_by_name(release)
    current = current_feed(feed_store)
    if current is not None:
        if version_key(version) == version_key(current["version"]):
            remote = existing.get(installer_name(version))
            if remote is None or not asset_matches(remote, directory / installer_name(version)):
                raise ValueError("The published Beta version has different installer bytes")
            feed_store.verify_public()
            return "already-published"
        if same_published_source(release, current, record):
            feed_store.verify_public()
            return "already-published-source"
        if version_key(version) < version_key(current["version"]):
            raise ValueError("This older Beta cannot replace the newer published feed")

    # A rerun may re-sign identical installer bytes with a new signing timestamp.
    # Reuse the already uploaded, valid original signature instead of replacing it.
    installer = directory / installer_name(version)
    remote_installer = existing.get(installer.name)
    if remote_installer is not None and not asset_matches(remote_installer, installer):
        raise ValueError("An immutable Beta installer already exists with different bytes")
    signature_name = installer.name + ".sig"
    if signature_name in existing:
        signature = public_download(signature_name, existing[signature_name].get("size"))
        original = (directory / signature_name).read_bytes()
        (directory / signature_name).write_bytes(signature)
        try:
            verify_installer(installer)
        except Exception:
            (directory / signature_name).write_bytes(original)
            raise
        record = prepare_metadata(directory, version, record["source_commit"], str(record["run_id"]))

    client.patch_release(str(release["id"]))
    release = client.get_release()
    if release.get("prerelease") is not True or release.get("is_latest") is not False:
        raise ValueError("CNB Beta must remain a non-Latest prerelease")
    for path in package_files(directory, version):
        remote = existing.get(path.name)
        if remote is not None and not asset_matches(remote, path):
            raise ValueError("An immutable Beta attachment already exists with different content")
        if remote is None:
            client.upload(str(release["id"]), path, overwrite=False)
        release = wait_for_asset(client, path)

    # The Git checkout holds the original parent. A normal push atomically
    # advances that ref or refuses a competing publisher's newer parent.
    current = current_feed(feed_store)
    if current is not None and version_key(current["version"]) >= version_key(version):
        raise ValueError("The Beta feed advanced during publication; leaving it unchanged")
    feed = directory / FEED_NAME
    feed_store.advance(feed)
    feed_store.verify_public()
    try:
        cleanup(client, release, version, keep)
    except (RuntimeError, ValueError):
        print("Published Beta successfully; old attachment cleanup can be retried separately.")
    return "published"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="Successful GitHub Beta Actions run ID")
    parser.add_argument("--directory", type=Path, help="Local output directory")
    parser.add_argument("--publish", action="store_true", help="Upload locally to independent CNB Beta release")
    parser.add_argument("--prepare", action="store_true", help="CI only: verify signed installer and create metadata")
    parser.add_argument("--version", help="CI Beta version")
    parser.add_argument("--commit", help="CI complete source commit")
    parser.add_argument("--keep", type=int, default=10)
    args = parser.parse_args()
    directory = (args.directory or ROOT / "dist/beta" / ("run-" + args.run_id)).resolve()
    if args.prepare:
        if args.publish or not args.version or not args.commit or not args.directory:
            parser.error("--prepare requires --version, --commit, --directory and cannot publish")
        record = prepare_metadata(directory, args.version, args.commit, args.run_id)
    else:
        if args.version or args.commit:
            parser.error("Local publication derives version and source from the signed Actions artifact")
        record = fetch_run(args.run_id, directory)
        verify_record(directory, record)
        if args.publish:
            result = publish(directory, record, keep=args.keep)
            print(f"CNB Beta {result}: {record['version']}")
        else:
            print("Verified locally. Add --publish to upload this Beta to CNB.")
    print(f"Verified {record['version']} ({record['size_bytes']} bytes): {directory}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error)) from None
