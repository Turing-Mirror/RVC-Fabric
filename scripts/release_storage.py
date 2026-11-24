"""Cloudflare R2 installer storage; catalog and runtime publishing stay separate."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

CDN_BASE = "https://cdn.turingmirror.com/f"
BUCKET = "trm-releases"
MIME = "application/vnd.microsoft.portable-executable"


def installer_url(slug: str, name: str) -> str:
    return f"{CDN_BASE}/{slug}/{quote(name)}"


def download_identity(url: str) -> tuple[str, int] | None:
    """Hash the actual response bytes; Content-Length alone is not verification."""
    try:
        with urlopen(Request(url, headers={"User-Agent": "Fabric-release", "Cache-Control": "no-cache"}), timeout=120) as response:
            digest, size = hashlib.sha256(), 0
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
            return digest.hexdigest(), size
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


class R2Publisher:
    def __init__(self, slug: str, name_prefix: str, fixed_name: str, *, bucket: str = BUCKET):
        self.slug, self.name_prefix, self.fixed_name, self.bucket = slug, name_prefix, fixed_name, bucket
        self.account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        self.headers = None

    def wrangler(self, *args: str, capture: bool = False):
        executable = os.environ.get("TRM_WRANGLER") or shutil.which("wrangler")
        if not executable:
            local = Path(__file__).resolve().parents[2] / "TRM-Nexus/services/community/node_modules/wrangler/bin/wrangler.js"
            if not local.is_file():
                raise RuntimeError("Install Wrangler or set TRM_WRANGLER to its executable or wrangler.js.")
            executable = str(local)
        command = (["node", executable] if executable.endswith(".js") else [executable]) + list(args)
        result = subprocess.run(command, check=True, text=True, encoding="utf-8",
                                stdout=subprocess.PIPE if capture else None,
                                env={**os.environ, "WRANGLER_SEND_METRICS": "false",
                                     **({"CLOUDFLARE_ACCOUNT_ID": self.account} if self.account else {})})
        return result.stdout.strip() if capture else None

    def authenticate(self):
        # Capture credentials in memory only; never print or persist the response.
        auth = json.loads(self.wrangler("auth", "token", "--json", capture=True))
        if auth["type"] == "api_key":
            self.headers = {"X-Auth-Key": auth["key"], "X-Auth-Email": auth["email"]}
        else:
            self.headers = {"Authorization": "Bearer " + auth["token"]}
        if not self.account:
            identity = json.loads(self.wrangler("whoami", "--json", capture=True))
            accounts = identity.get("accounts", [])
            if len(accounts) != 1:
                raise ValueError("Set CLOUDFLARE_ACCOUNT_ID to the account containing the release bucket.")
            self.account = accounts[0]["id"]

    def list_keys(self) -> list[str]:
        if self.headers is None:
            self.authenticate()
        endpoint = f"https://api.cloudflare.com/client/v4/accounts/{self.account}/r2/buckets/{quote(self.bucket)}/objects"
        query = {"prefix": self.slug + "/", "per_page": 1000}
        keys = []
        while True:
            with urlopen(Request(endpoint + "?" + urlencode(query), headers=self.headers), timeout=60) as response:
                page = json.load(response)
            if not page.get("success"):
                raise RuntimeError("Cloudflare could not list release objects.")
            keys.extend(item["key"] for item in page["result"])
            info = page.get("result_info") or {}
            if not info.get("is_truncated"):
                return keys
            cursor = info.get("cursor")
            if not cursor or cursor == query.get("cursor"):
                raise RuntimeError("Cloudflare returned an incomplete object listing.")
            query["cursor"] = cursor

    def publish(self, installer: Path, version: str, sha256: str, size_bytes: int):
        name = f"{self.name_prefix}{version}.exe"
        if not re.fullmatch(r"\d+\.\d+\.\d+", version) or installer.name != name:
            raise ValueError("The installer name must contain its stable release version.")
        with installer.open("rb") as stream:
            local = hashlib.file_digest(stream, "sha256").hexdigest(), installer.stat().st_size
        expected = sha256, size_bytes
        if local != expected:
            raise ValueError("The local installer differs from the signed release.")
        keys = self.list_keys()
        pattern = re.compile(re.escape(f"{self.slug}/{self.name_prefix}") + r"(\d+\.\d+\.\d+)\.exe")
        current_version = tuple(map(int, version.split(".")))
        obsolete = []
        for key in keys:
            match = pattern.fullmatch(key)
            if match and key != f"{self.slug}/{name}":
                if tuple(map(int, match[1].split("."))) > current_version:
                    raise ValueError("R2 already contains a newer release: " + key)
                obsolete.append(key)
        for target in (name, self.fixed_name):
            url = installer_url(self.slug, target)
            remote = download_identity(url)
            if remote != expected:
                if remote is not None and target == name:
                    raise ValueError("The versioned R2 installer already has different bytes: " + target)
                self.wrangler("r2", "object", "put", f"{self.bucket}/{self.slug}/{target}",
                              "--file", str(installer), "--content-type", MIME, "--remote")
                if download_identity(url) != expected:
                    raise ValueError("The CDN installer hash or size differs: " + target)
        # Both public downloads have passed before any old version is removed.
        for key in obsolete:
            self.wrangler("r2", "object", "delete", f"{self.bucket}/{key}", "--remote")


MS_SITE = "https://modelscope.cn"


class ModelScopeMirror:
    """Backup copy of a signed installer in a ModelScope model repo.

    The resolve URL pins the commit, so the address never changes once listed.
    Uploads go through the `ms-hub` CLI and its saved login; set TRM_MS_HUB to
    use another executable.
    """

    def __init__(self, repo: str, folder: str):
        self.repo, self.folder = repo, folder.strip("/")

    def listing(self) -> list[dict]:
        query = urlencode({"Revision": "master", "Recursive": "true", "Root": self.folder})
        request = Request(f"{MS_SITE}/api/v1/models/{self.repo}/repo/files?{query}",
                          headers={"User-Agent": "Fabric-release"})
        with urlopen(request, timeout=60) as response:
            return json.load(response)["Data"]["Files"] or []

    def find(self, name: str, sha256: str, size_bytes: int) -> str | None:
        path = f"{self.folder}/{name}"
        for item in self.listing():
            if (item.get("Type") == "blob" and item.get("Path") == path and item.get("Revision")
                    and (item.get("Sha256") or "").lower() == sha256.lower()
                    and int(item.get("Size") or -1) == size_bytes):
                return f"{MS_SITE}/models/{self.repo}/resolve/{item['Revision']}/{quote(path)}"
        return None

    def publish(self, installer: Path, version: str, sha256: str, size_bytes: int, *, attempts: int = 10) -> str:
        url = self.find(installer.name, sha256, size_bytes)
        if url:
            return url
        executable = os.environ.get("TRM_MS_HUB") or shutil.which("ms-hub")
        if not executable:
            raise RuntimeError("Install the ms-hub CLI or set TRM_MS_HUB.")
        subprocess.run([executable, "upload", self.repo, str(installer), f"{self.folder}/{installer.name}",
                        "--repo-type", "model", "--commit-message", f"Add {installer.name}",
                        "--disable-tqdm"], check=True)
        for attempt in range(attempts):
            url = self.find(installer.name, sha256, size_bytes)
            if url:
                identity = download_identity(url)
                if identity != (sha256, size_bytes):
                    raise ValueError("The ModelScope installer has different bytes: " + url)
                return url
            time.sleep(min(30, 5 * (attempt + 1)))
        raise RuntimeError(f"ModelScope does not list {self.folder}/{installer.name} after upload.")
