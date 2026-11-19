"""Publish the final RVC Fabric update for clients that read the CNB catalog."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import yaml

from publish_asset import ensure_release, upload


VERSION = "1.8.0"
NAME = f"RVC-Fabric-Setup-{VERSION}.exe"
PRODUCT = "Turing-Mirror/RVC-Fabric"
CNB = "Turing-Mirror/RVC-Fabric-Releases"
ORIGIN = f"https://cnb.cool/{CNB}"
ASSETS = f"{ORIGIN}/-/releases/download/setup/"
FIXED_NAME = "RVC_Fabric_Setup.exe"
URL = ASSETS + NAME
SITE = "https://www.turingmirror.com/releases/rvc-fabric/"
ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def run(*args, cwd=None, capture=False):
    result = subprocess.run(args, cwd=cwd, check=True, text=True, encoding="utf-8",
                            stdout=subprocess.PIPE if capture else None,
                            env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "PYTHONUTF8": "1"})
    return result.stdout.strip() if capture else None


def open_release_url(url, timeout):
    request = Request(url, headers={"User-Agent": f"RVC-Fabric/{VERSION}"})
    return urlopen(request, timeout=timeout)


def verify_release(directory):
    tag = "v" + VERSION
    release = json.loads(run("gh", "release", "view", tag, "--repo", PRODUCT, "--json",
                             "tagName,isDraft,isPrerelease,publishedAt", capture=True))
    if release["tagName"] != tag or release["isDraft"] or release["isPrerelease"] or not release["publishedAt"]:
        raise ValueError("Publish the stable GitHub release first.")
    files = [NAME, NAME + ".sig", NAME + ".sha256", "updater.json"]
    run("gh", "release", "download", tag, "--repo", PRODUCT, "--dir", directory,
        *[arg for file in files for arg in ("--pattern", file)])
    signed = json.loads(run("node", ROOT / "scripts/verify_setup_signature.mjs", directory / NAME,
                            ROOT / "app/src-tauri/tauri.conf.json", capture=True))
    manifest = read_json(directory / "updater.json")
    platform = manifest["platforms"]["windows-x86_64"]
    checksum = (directory / (NAME + ".sha256")).read_text(encoding="utf-8-sig").strip()
    github_url = f"https://github.com/{PRODUCT}/releases/download/{tag}/{NAME}"
    if (manifest["version"] != VERSION or platform["url"] != github_url
            or platform["signature"] != signed["signature"] or manifest["pub_date"] != signed["pub_date"]
            or checksum != signed["sha256"] + "  " + NAME):
        raise ValueError("The signed Setup and its GitHub release files do not match.")
    with open_release_url(SITE + "app.json", timeout=30) as response:
        current = json.load(response)["app"]
    if (tuple(map(int, current["version"].split("."))) < tuple(map(int, VERSION.split(".")))
            or (current["version"] == VERSION and current["gui"]["sha256"] != signed["sha256"])):
        raise ValueError("Update the website to the signed release before updating legacy clients.")
    return signed, manifest, release["publishedAt"]


def prepare_catalog(repo, scratch, signed, manifest, published_at):
    src = repo / "catalog-src"
    app_file, setup_file = src / "app.yaml", src / "setup.yaml"
    app = yaml.safe_load(app_file.read_text(encoding="utf-8"))
    setup = yaml.safe_load(setup_file.read_text(encoding="utf-8"))
    current = read_json(repo / "index.json")["app"]["gui"]
    if current["version"] == VERSION:
        old_platform = read_json(repo / "updater.json")["platforms"]["windows-x86_64"]
        if current["sha256"] != signed["sha256"] or current["url"] != URL or old_platform != {"url": URL, "signature": signed["signature"]}:
            raise ValueError("The existing CNB release differs from the signed Setup.")
        return []
    if current["version"] != "1.7.2" or app["version"] != "1.7.2" or setup["version"] != "1.7.2":
        raise ValueError("The CNB catalog has changed. Check its release before continuing.")
    date = published_at[:10].replace("-", "")[2:]
    lines = [re.sub(r"^[-*]\s+", "", line.strip()) for line in manifest["notes"].splitlines() if line.strip()]
    body = "\n".join(lines)
    relative = "setup/" + NAME
    fields = dict(version=VERSION, file=relative, channel="release", release_tag="setup",
                  sha256=signed["sha256"], size_bytes=signed["size_bytes"], notes=body)
    app.update(version=VERSION, released=date)
    app["gui"].update(fields, url=URL)
    setup.update(fields, released=date, file="setup/" + FIXED_NAME, url=ASSETS + FIXED_NAME)
    for path, data in [(app_file, app), (setup_file, setup)]:
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    for name in (NAME, FIXED_NAME):
        sidecar = repo / "setup" / (name + ".sha256")
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(signed["sha256"] + "  " + name + "\n", encoding="ascii")
    changes = src / "changelog.yaml"
    text = changes.read_text(encoding="utf-8")
    marker = re.search(r"(?m)^entries:[ \t]*$", text)
    if not marker:
        raise ValueError("Missing changelog entries.")
    entry = dict(version=VERSION, date=date, title=VERSION, body=body, highlights=lines)
    text = text[:marker.end()] + "\n" + yaml.safe_dump([entry], allow_unicode=True, sort_keys=False).rstrip() + text[marker.end():]
    changes.write_text(text, encoding="utf-8")
    run(sys.executable, ROOT / "scripts/build_catalog.py", "--cnb", repo,
        "--bundled", scratch / "bundled.json", "build")
    for path in [repo / "index.json", repo / "catalog/online_catalog.snippet.json"]:
        gui = read_json(path)["app"]["gui"]
        if (gui["version"], gui["url"], gui["sha256"], gui["size_bytes"]) != (VERSION, URL, signed["sha256"], signed["size_bytes"]):
            raise ValueError("Legacy catalog mismatch: " + path.name)
    manifest["platforms"]["windows-x86_64"]["url"] = URL
    (repo / "updater.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ["catalog-src/app.yaml", "catalog-src/setup.yaml", "catalog-src/changelog.yaml",
            relative + ".sha256", "setup/" + FIXED_NAME + ".sha256", "index.json", "catalog/online_catalog.snippet.json", "changelog.json", "updater.json"]


def remote_sha256(url):
    try:
        with open_release_url(url, timeout=90) as response:
            return hashlib.file_digest(response, "sha256").hexdigest()
    except HTTPError as error:
        if error.code == 404:
            return None
        raise


def mirror_setup(directory, signed, previous_fixed_hash):
    release_id = None
    expected = signed["sha256"]
    for name in (NAME, FIXED_NAME):
        url = ASSETS + name
        current = remote_sha256(url)
        if current == expected:
            continue
        if current is not None and (name != FIXED_NAME or current != previous_fixed_hash):
            raise ValueError("Unexpected existing CNB file: " + name)
        if release_id is None:
            release_id = ensure_release(CNB, "setup", "")
        path = directory / name
        if name == FIXED_NAME:
            shutil.copyfile(directory / NAME, path)
        uploaded = upload(CNB, release_id, path)
        if uploaded["sha256"] != expected or remote_sha256(url) != expected:
            raise ValueError("The CNB download does not match the signed Setup: " + name)


def load_cnb_token():
    if os.environ.get("CNB_TOKEN"):
        return
    token_file = Path.home() / ".cnb" / "agent-token"
    if not token_file.is_file():
        return
    line = token_file.read_text(encoding="utf-8-sig").strip()
    assignment = re.fullmatch(r"""(?:export\s+)?CNB_TOKEN\s*=\s*(['"]?)([^'"\s]+)\1""", line)
    if assignment:
        os.environ["CNB_TOKEN"] = assignment.group(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="Upload the signed Setup and publish the CNB catalog")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="rvc-update-") as temp:
        scratch = Path(temp)
        signed, manifest, published_at = verify_release(scratch)
        repo = scratch / "catalog"
        if args.publish:
            load_cnb_token()
        git = ("git", "-c", "credential.helper=", "-c", "credential.helper=!cnb git-credential")
        run(*git, "clone", "--depth", "1", "--branch", "main", ORIGIN, repo)
        previous_fixed_hash = (repo / "setup" / (FIXED_NAME + ".sha256")).read_text(encoding="ascii").split()[0]
        files = prepare_catalog(repo, scratch, signed, manifest, published_at)
        if not args.publish:
            print("Checked the signed release and prepared the CNB catalog locally.")
            return
        mirror_setup(scratch, signed, previous_fixed_hash)
        if files:
            run(*git, "add", "--", *files, cwd=repo)
            run(*git, "commit", "-m", "Release RVC Fabric 1.8.0 for existing installations", cwd=repo)
            run(*git, "push", "origin", "HEAD:main", cwd=repo)
        print("CNB provides the final update to RVC Fabric 1.8.0.")


if __name__ == "__main__":
    main()
