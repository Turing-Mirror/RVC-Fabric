"""Prepare a local or CNB-built NSIS installer for the existing release process.

This downloads/stages and signs files locally. Publishing, archiving the previous
release, installing, and updating release-repository manifests remain separate.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "app/src-tauri/tauri.conf.json"
CNB_REPO = "Turing-Mirror/RVC-Fabric"


def tool(name: str) -> str:
    executable = shutil.which(name + ".cmd") or shutil.which(name)
    if not executable:
        raise RuntimeError(f"Required tool not found: {name}")
    return executable


def run_json(command: list[str], *, cwd: Path = REPO) -> object:
    result = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=300,
    )
    if result.returncode:
        # Do not echo CLI arguments, credential-bearing diagnostics, or signing env.
        raise RuntimeError(f"{Path(command[0]).name} failed (exit {result.returncode})")
    return json.loads(result.stdout)


def cnb(*args: str) -> object:
    result = run_json([tool("cnb"), *args, "--verbose"])
    if result.get("status") != 200:
        raise RuntimeError(f"CNB {args[0]} {args[1]} failed (status {result.get('status')})")
    return result["data"]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_asset(path: Path, asset: dict) -> None:
    if (asset.get("hash_algo") != "sha256" or
            path.stat().st_size != asset["size_in_byte"] or digest(path) != asset["hash_value"]):
        raise RuntimeError(f"CNB attachment size/hash mismatch: {path.name}")


def validate_candidate(metadata: dict, commit: str, version: str) -> str:
    name = f"RVC_Fabric_{version}_cnb-{commit[:12]}_x64-setup.exe"
    if (metadata.get("commit") != commit or metadata.get("version") != version or
            metadata.get("target") != "x86_64-pc-windows-msvc" or metadata.get("file") != name):
        raise RuntimeError("CNB candidate commit, version, target, or filename mismatch")
    return name


def verify_local_version(source: Path, version: str) -> None:
    """Read the signed PE's fixed version resource using the Windows API."""
    if os.name != "nt":
        raise RuntimeError("Local installer version inspection requires Windows")
    from ctypes import wintypes
    api = ctypes.WinDLL("version", use_last_error=True)
    api.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    api.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    api.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    api.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR,
                                  ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    size = api.GetFileVersionInfoSizeW(str(source), None)
    buffer = ctypes.create_string_buffer(size)
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if (not size or not api.GetFileVersionInfoW(str(source), 0, size, buffer) or
            not api.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)) or
            length.value < 52):
        raise RuntimeError("Cannot read local installer PE version resource")
    info = ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD * 13)).contents
    actual = (info[4] >> 16, info[4] & 65535, info[5] >> 16, info[5] & 65535)
    expected = tuple(int(part) for part in version.split(".")) + (0,)
    if info[0] != 0xFEEF04BD or actual != expected:
        raise RuntimeError(f"Local installer product version {actual} does not match {version}")


def download_candidate(commit: str, version: str, output: Path) -> tuple[Path, dict]:
    assets = {asset["name"]: asset for asset in cnb(
        "git", "get-commit-assets-by-sha", "--repo", CNB_REPO, "--sha1", commit,
    )}

    def download(name: str) -> Path:
        if name not in assets:
            raise RuntimeError(f"CNB attachment not found: {name}")
        data = cnb("git", "get-commit-assets", "--repo", CNB_REPO,
                   "--commit-id", commit, "--filename", name)
        destination = output / name
        content_type = assets[name]["content_type"].split(";")[0]
        if content_type == "application/json":
            destination.write_bytes((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        elif content_type == "text/plain":
            destination.write_bytes(data.encode("utf-8"))
        else:
            shutil.copyfile(data, destination)
        verify_asset(destination, assets[name])
        return destination

    metadata = json.loads(download("build-metadata.json").read_text(encoding="utf-8"))
    name = validate_candidate(metadata, commit, version)
    build_id = metadata.get("build_id", "")
    if not re.fullmatch(r"[a-zA-Z0-9-]+", build_id):
        raise RuntimeError("CNB build identifier missing or invalid")
    status = cnb("build", "get-build-status", "--repo", CNB_REPO, "--sn", build_id)
    if status.get("status") != "success":
        raise RuntimeError("CNB build did not complete successfully")
    source = download(name)
    sidecar = download(name + ".sha256").read_text(encoding="utf-8")
    if (source.stat().st_size != metadata["size"] or digest(source) != metadata["sha256"] or
            sidecar != f"{metadata['sha256']}  {name}\n"):
        raise RuntimeError("CNB candidate metadata or checksum sidecar mismatch")
    return source, metadata


def prepare(source: Path, output: Path, version: str, provenance: dict) -> dict:
    installer = output / f"RVC Fabric_{version}_x64-setup.exe"
    (output / "release-input.json").unlink(missing_ok=True)
    Path(str(installer) + ".sig").unlink(missing_ok=True)
    shutil.copyfile(source, installer)
    source_signature = Path(str(source) + ".sig")
    if source_signature.is_file():
        shutil.copyfile(source_signature, str(installer) + ".sig")
    else:
        if not (os.environ.get("TAURI_SIGNING_PRIVATE_KEY") or os.environ.get("TAURI_SIGNING_PRIVATE_KEY_PATH")):
            raise RuntimeError("Set the existing TAURI_SIGNING_PRIVATE_KEY_PATH or TAURI_SIGNING_PRIVATE_KEY locally")
        password = os.environ.get("TAURI_SIGNING_PRIVATE_KEY_PASSWORD")
        if password is None:
            raise RuntimeError("Set TAURI_SIGNING_PRIVATE_KEY_PASSWORD locally before signing")
        command = [tool("node"), str(REPO / "app/node_modules/@tauri-apps/cli/tauri.js"),
                   "signer", "sign", str(installer)]
        if password == "":
            command += ["--password", ""]  # Explicit empty value avoids an interactive prompt.
        result = subprocess.run(
            command,
            cwd=REPO / "app", capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
        if result.returncode:
            raise RuntimeError("Local updater signing failed; check local key and password settings")
    verification = run_json([
        tool("node"), str(REPO / "scripts/verify_setup_signature.mjs"), str(installer), str(CONFIG),
    ])
    if verification["sha256"] != digest(source):
        raise RuntimeError("Installer bytes changed while staging/signing")
    fixed = output / "RVC_Fabric_Setup.exe"
    shutil.copyfile(installer, fixed)
    for path in (installer, fixed):
        (output / (path.name + ".sha256")).write_text(
            f"{verification['sha256']}  {path.name}\n", encoding="utf-8",
        )
    result = {
        **provenance, **verification, "version": version,
        "installer": str(installer), "fixed_installer": str(fixed),
        "published_to_production": False,
    }
    (output / "release-input.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("local", "cnb"), required=True)
    parser.add_argument("--commit", help="Full CNB source commit; optional provenance for local builds")
    parser.add_argument("--installer", type=Path, help="Existing local NSIS installer")
    parser.add_argument("--out", type=Path, help="Release staging directory (default: dist/setup-release/<source>)")
    args = parser.parse_args()
    if args.commit and not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        parser.error("--commit must be a full lowercase Git SHA")
    if args.source == "cnb" and (not args.commit or args.installer):
        parser.error("CNB requires --commit and does not accept --installer")
    version = json.loads(CONFIG.read_text(encoding="utf-8"))["version"]
    label = f"cnb-{args.commit[:12]}" if args.source == "cnb" else "local"
    output = (args.out or REPO / "dist/setup-release" / label).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "release-input.json").unlink(missing_ok=True)
    provenance = {"build_source": args.source, "source_commit": args.commit}
    if args.source == "cnb":
        source, metadata = download_candidate(args.commit, version, output)
        provenance["build_id"] = metadata["build_id"]
    else:
        source = (args.installer or REPO / "app/src-tauri/target/release/bundle/nsis" /
                  f"RVC Fabric_{version}_x64-setup.exe").resolve()
        verify_local_version(source, version)
    if source.resolve() == output / f"RVC Fabric_{version}_x64-setup.exe":
        parser.error("--out must differ from the input installer's directory")
    result = prepare(source, output, version, provenance)
    print(json.dumps({**result, "signature": "[verified; see release-input.json]"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error)) from None
