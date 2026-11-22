"""Prepare the disposable CI checkout for an independently numbered Beta build."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
STABLE = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")
BETA = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-beta\.([1-9]\d*)\Z")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def next_version(stable: str, number: int) -> str:
    match = STABLE.fullmatch(stable)
    if not match or number < 1:
        raise ValueError("Beta requires a stable source version and a positive build number")
    major, minor, patch = map(int, match.groups())
    if max(major, minor, patch + 1) > 65535:
        raise ValueError("The Beta target does not fit Windows version resources")
    return f"{major}.{minor}.{patch + 1}-beta.{number}"


def replace_one(text: str, pattern: str, replacement: str) -> str:
    result, count = re.subn(pattern, lambda _: replacement, text, count=1, flags=re.M)
    if count != 1:
        raise ValueError("Missing application version declaration")
    return result


def prepare(root: Path, number: int) -> str:
    """Change only application versions in a checkout, never dependency versions."""
    package_path = root / "app/package.json"
    package = read_json(package_path)
    stable = package["version"]
    version = next_version(stable, number)
    config_path = root / "app/src-tauri/tauri.conf.json"
    config = read_json(config_path)
    lock_path = root / "app/package-lock.json"
    lock = read_json(lock_path)
    if config["version"] != stable or lock["version"] != stable or lock["packages"][""]["version"] != stable:
        raise ValueError("Source application versions are inconsistent")

    cargo_path = root / "app/src-tauri/Cargo.toml"
    cargo = cargo_path.read_text(encoding="utf-8")
    cargo = replace_one(cargo, rf'^version = "{re.escape(stable)}"$', f'version = "{version}"')
    cargo_lock_path = root / "app/src-tauri/Cargo.lock"
    cargo_lock = cargo_lock_path.read_text(encoding="utf-8")
    cargo_lock = replace_one(
        cargo_lock, rf'^name = "rvc-fabric"\nversion = "{re.escape(stable)}"$',
        f'name = "rvc-fabric"\nversion = "{version}"',
    )
    inno_path = root / "scripts/installer/RVC_Fabric_Setup.iss"
    inno = replace_one(
        inno_path.read_text(encoding="utf-8-sig"),
        rf'^#define MyAppVersion "{re.escape(stable)}"$', f'#define MyAppVersion "{version}"',
    )
    shell_path = root / "scripts/shell_version.py"
    shell = replace_one(
        shell_path.read_text(encoding="utf-8"),
        rf'^APP_VERSION: str = "{re.escape(stable)}"$', f'APP_VERSION: str = "{version}"',
    )
    shell = replace_one(shell, r'^APP_CHANNEL: str = "stable"$', 'APP_CHANNEL: str = "beta"')

    package["version"] = version
    lock["version"] = lock["packages"][""]["version"] = version
    config["version"] = version
    config["bundle"]["createUpdaterArtifacts"] = False
    config["bundle"]["windows"]["allowDowngrades"] = True
    for path, data in ((package_path, package), (lock_path, lock), (config_path, config)):
        write_json(path, data)
    for path, text in ((cargo_path, cargo), (cargo_lock_path, cargo_lock), (inno_path, inno), (shell_path, shell)):
        path.write_text(text, encoding="utf-8")
    validate(root, version)
    return version


def validate(root: Path, version: str) -> None:
    if not BETA.fullmatch(version):
        raise ValueError("Use X.Y.Z-beta.N without hashes or build metadata")
    for relative in ("app/package.json", "app/src-tauri/tauri.conf.json", "app/package-lock.json"):
        if read_json(root / relative)["version"] != version:
            raise ValueError("Beta application versions are inconsistent")
    lock = read_json(root / "app/package-lock.json")
    if lock["packages"][""]["version"] != version:
        raise ValueError("Beta npm lock root version is inconsistent")
    for relative, pattern in (
        ("app/src-tauri/Cargo.toml", rf'^version = "{re.escape(version)}"$'),
        ("app/src-tauri/Cargo.lock", rf'^name = "rvc-fabric"\nversion = "{re.escape(version)}"$'),
        ("scripts/installer/RVC_Fabric_Setup.iss", rf'^#define MyAppVersion "{re.escape(version)}"$'),
        ("scripts/shell_version.py", rf'^APP_VERSION: str = "{re.escape(version)}"$'),
    ):
        if not re.search(pattern, (root / relative).read_text(encoding="utf-8-sig"), re.M):
            raise ValueError(f"Beta version is missing from {relative}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--number", type=int, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    version = prepare(args.root, args.number)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"version={version}\n")
    print(version)


if __name__ == "__main__":
    main()
