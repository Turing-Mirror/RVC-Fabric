"""Publish signed RVC installers to Cloudflare R2 and push catalog metadata to CNB.

Run after the GitHub release is public. Both public installer names are verified
by SHA-256 and size before older versioned installers are deleted. Without
--publish, only prepare the catalog in a temporary clone.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import yaml

from release_storage import R2Publisher, installer_url


PRODUCT = "Turing-Mirror/RVC-Fabric"
CNB = "Turing-Mirror/RVC-Fabric-Releases"
ORIGIN = f"https://cnb.cool/{CNB}"
FIXED_NAME = "RVC_Fabric_Setup.exe"
ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / "app/package.json").read_text(encoding="utf-8"))["version"]
NAME = URL = ""


def use_version(version):
    global VERSION, NAME, URL
    VERSION = version
    NAME = f"RVC-Fabric-Setup-{VERSION}.exe"
    URL = installer_url("rvc-fabric", NAME)


def version_key(value):
    return tuple(map(int, value.split(".")))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))



def command_env(args):
    """Git uses CNB CLI credentials independently from artifact publishing."""
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "PYTHONUTF8": "1"}
    if str(args[0]) == "git":
        env.pop("CNB_TOKEN", None)
    return env

def run(*args, cwd=None, capture=False):
    result = subprocess.run(args, cwd=cwd, check=True, text=True, encoding="utf-8",
                            stdout=subprocess.PIPE if capture else None,
                            env=command_env(args))
    return result.stdout.strip() if capture else None


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
    return signed, manifest, release["publishedAt"]


def prepare_catalog(repo, scratch, signed, manifest, published_at):
    src = repo / "catalog-src"
    app_file, setup_file = src / "app.yaml", src / "setup.yaml"
    app = yaml.safe_load(app_file.read_text(encoding="utf-8"))
    setup = yaml.safe_load(setup_file.read_text(encoding="utf-8"))
    current = read_json(repo / "index.json")["app"]["gui"]
    if current["version"] == VERSION:
        old_platform = read_json(repo / "updater.json")["platforms"]["windows-x86_64"]
        if (current["sha256"] != signed["sha256"] or current["size_bytes"] != signed["size_bytes"]
                or old_platform["signature"] != signed["signature"]):
            raise ValueError("The existing CNB release differs from the signed Setup.")
    if not (version_key(current["version"]) <= version_key(VERSION)
            and app["version"] == current["version"] == setup["version"]):
        raise ValueError("The CNB catalog has changed. Check its release before continuing.")
    date = published_at[:10].replace("-", "")[2:]
    lines = [re.sub(r"^[-*]\s+", "", line.strip()) for line in manifest["notes"].splitlines() if line.strip()]
    body = "\n".join(lines)
    relative = "setup/" + NAME
    fields = dict(version=VERSION, file=relative, channel="release", release_tag="setup",
                  sha256=signed["sha256"], size_bytes=signed["size_bytes"], notes=body)
    app.update(version=VERSION, released=date)
    app["gui"].update(fields, url=URL)
    setup.update(fields, released=date, url=URL)
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
    entries = yaml.safe_load(text)["entries"]
    if not any(str(item["version"]) == VERSION for item in entries):
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


def mirror_setup(directory, signed):
    R2Publisher("rvc-fabric", "RVC-Fabric-Setup-", FIXED_NAME).publish(
        directory / NAME, VERSION, signed["sha256"], signed["size_bytes"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="Publish installers to R2 and push catalog metadata to CNB")
    parser.add_argument("--version", default=VERSION, help="Release version (default: app/package.json)")
    args = parser.parse_args()
    use_version(args.version)
    with tempfile.TemporaryDirectory(prefix="rvc-update-") as temp:
        scratch = Path(temp)
        signed, manifest, published_at = verify_release(scratch)
        repo = scratch / "catalog"
        git = ("git", "-c", "credential.helper=", "-c", "credential.helper=!cnb git-credential")
        run(*git, "clone", "--depth", "1", "--branch", "main", ORIGIN, repo)
        files = prepare_catalog(repo, scratch, signed, manifest, published_at)
        if not args.publish:
            print("Checked the signed release and prepared the CNB catalog locally.")
            return
        mirror_setup(scratch, signed)
        run(*git, "add", "--", *files, cwd=repo)
        if run(*git, "diff", "--cached", "--name-only", cwd=repo, capture=True):
            run(*git, "commit", "-m", f"Release RVC Fabric {VERSION}", cwd=repo)
            run(*git, "push", "origin", "HEAD:main", cwd=repo)
        print(f"Cloudflare provides RVC Fabric {VERSION}; catalog metadata is published on CNB.")


if __name__ == "__main__":
    main()
