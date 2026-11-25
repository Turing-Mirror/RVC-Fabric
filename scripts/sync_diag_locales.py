"""Synchronize the pinned diagnostics crate's flat catalogs into shell i18n.

Run with --check in CI. No translation is changed in this repository.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import os

# Next to this repository during development, or wherever FABRIC_DIAGNOSTICS_DIR points.
DEFAULT_CRATE = Path(os.environ.get("FABRIC_DIAGNOSTICS_DIR") or ROOT.parent / "fabric-diagnostics")


def nested_catalog(flat):
    result = {}
    for key, value in flat.items():
        if not key.startswith("diag."):
            raise ValueError(f"Unexpected diagnostic key: {key}")
        target = result
        parts = key.split(".")[1:]
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
    return result


def sync(crate=DEFAULT_CRATE, check=False):
    drift = []
    for source in sorted((crate / "locales").glob("*.json")):
        destination = ROOT / "app" / "i18n" / "locales" / source.name
        catalog = json.loads(destination.read_text(encoding="utf-8-sig"))
        expected = nested_catalog(json.loads(source.read_text(encoding="utf-8")))
        if catalog.get("diag") != expected:
            drift.append(source.name)
            if not check:
                catalog["diag"] = expected
                destination.write_text(
                    json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
    if not list((crate / "locales").glob("*.json")):
        raise FileNotFoundError(f"Diagnostics catalogs missing: {crate}")
    return drift


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--crate", type=Path, default=DEFAULT_CRATE)
    args = parser.parse_args()
    if not (args.crate / "locales").is_dir():
        # Nothing to compare against on a machine that only builds the app.
        print(f"Diagnostic locales not checked: {args.crate / 'locales'} not found.")
        raise SystemExit(0 if args.check else 1)
    changed = sync(args.crate, args.check)
    if changed:
        print(("Out of sync: " if args.check else "Synchronized: ") + ", ".join(changed))
    raise SystemExit(1 if args.check and changed else 0)
