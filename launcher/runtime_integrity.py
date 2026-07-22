# -*- coding: utf-8 -*-
"""Runtime integrity check (Steam-like file + import smoke).

Manifest JSON is produced by ``scripts/gen_runtime_integrity.py`` and published
on CNB under::

    runtime/<variant>/integrity-<version>.json

Launcher fetches it (or uses bundled fallback) and compares local Runtime.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from launcher.paths import ROOT, USER_DATA

LogCb = Callable[[str], None]

SCHEMA = 1

# Always checked even without remote manifest (minimal floor)
_BASELINE_REL_PATHS = (
    "python.exe",
    "pythonw.exe",
    "Lib/site-packages/torch/__init__.py",
    "Lib/site-packages/numpy/__init__.py",
)

_BASELINE_IMPORTS = (
    "torch",
    "numpy",
    "sounddevice",
    "librosa",
    "FreeSimpleGUI",
)


def _log(cb: Optional[LogCb], msg: str) -> None:
    if cb:
        try:
            cb(msg)
        except Exception:
            pass


def runtime_dir(root: Path | None = None) -> Path:
    base = Path(root or ROOT)
    for name in ("Runtime", "runtime"):
        d = base / name
        if d.is_dir():
            return d
    return base / "Runtime"


def integrity_report_path(root: Path | None = None) -> Path:
    return (root or ROOT) / "User_Data" / "logs" / "runtime_integrity_last.json"


def _sha256_file(path: Path, *, max_bytes: int = 64 * 1024 * 1024) -> Optional[str]:
    """Hash file; skip if larger than max_bytes (return None)."""
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > max_bytes:
        return None
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def file_fingerprint(path: Path) -> dict[str, Any]:
    st = path.stat()
    rec: dict[str, Any] = {
        "path": path.name,
        "size": int(st.st_size),
    }
    # hash small files only in local scan helpers
    if st.st_size <= 8 * 1024 * 1024:
        dig = _sha256_file(path, max_bytes=8 * 1024 * 1024)
        if dig:
            rec["sha256"] = dig
    return rec


def default_integrity_urls(variant: str, version: str) -> list[str]:
    from launcher.cnb_sources import CNB_RAW_MAIN

    var = (variant or "nvidia").strip().lower()
    ver = (version or "").strip()
    urls: list[str] = []
    if ver:
        urls.append(f"{CNB_RAW_MAIN}/runtime/{var}/integrity-{ver}.json")
    urls.append(f"{CNB_RAW_MAIN}/runtime/{var}/integrity.json")
    return urls


def fetch_integrity_manifest(
    *,
    variant: str,
    version: str = "",
    urls: Optional[list[str]] = None,
    timeout: float = 30.0,
) -> Optional[dict[str, Any]]:
    """Download integrity JSON from CNB (first success)."""
    candidates = list(urls or []) + default_integrity_urls(variant, version)
    # de-dupe preserve order
    seen: set[str] = set()
    ordered: list[str] = []
    for u in candidates:
        if u and u not in seen:
            seen.add(u)
            ordered.append(u)
    for url in ordered:
        try:
            req = Request(url, headers={"User-Agent": "RVC-Fabric-Integrity/1.0"})
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            data = json.loads(raw.decode("utf-8"))
            if isinstance(data, dict) and data.get("files") is not None:
                data["_source_url"] = url
                return data
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
            continue
    return None


def load_bundled_integrity(root: Path | None = None, variant: str = "nvidia") -> Optional[dict[str, Any]]:
    """Optional ship-with-shell: configs/runtime_integrity/<variant>.json"""
    base = Path(root or ROOT)
    for p in (
        base / "configs" / "runtime_integrity" / f"{variant}.json",
        base / "configs" / "runtime_integrity" / "default.json",
    ):
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data["_source_url"] = str(p)
                    return data
            except Exception:
                pass
    return None


def check_files(rt: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare declared files against local Runtime. Each item: path, ok, detail."""
    results: list[dict[str, Any]] = []
    files = manifest.get("files") or []
    if not isinstance(files, list):
        files = []
    # always include baseline
    declared_paths = {
        str(f.get("path") or "").replace("\\", "/")
        for f in files
        if isinstance(f, dict)
    }
    for rel in _BASELINE_REL_PATHS:
        if rel not in declared_paths:
            files = list(files) + [{"path": rel, "required": True}]

    for item in files:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("path") or "").replace("\\", "/").lstrip("/")
        if not rel or ".." in rel.split("/"):
            continue
        target = rt / Path(rel)
        rec: dict[str, Any] = {"path": rel, "ok": False, "detail": ""}
        if not target.is_file():
            rec["detail"] = "missing"
            results.append(rec)
            continue
        try:
            size = target.stat().st_size
        except OSError as e:
            rec["detail"] = f"stat: {e}"
            results.append(rec)
            continue
        exp_size = item.get("size")
        if exp_size is not None:
            try:
                if int(exp_size) != int(size):
                    rec["detail"] = f"size {size} != expected {exp_size}"
                    results.append(rec)
                    continue
            except (TypeError, ValueError):
                pass
        exp_hash = str(item.get("sha256") or "").strip().lower()
        if exp_hash:
            dig = _sha256_file(target, max_bytes=64 * 1024 * 1024)
            if dig is None:
                rec["detail"] = "sha256 skipped (file too large or unreadable)"
                # size already matched → soft ok if size present
                if exp_size is not None:
                    rec["ok"] = True
                    rec["detail"] = "size ok; hash skipped (large)"
                results.append(rec)
                continue
            if dig.lower() != exp_hash:
                rec["detail"] = "sha256 mismatch"
                results.append(rec)
                continue
        rec["ok"] = True
        rec["detail"] = "ok"
        results.append(rec)
    return results


def smoke_imports(
    root: Path,
    *,
    imports: Optional[list[str]] = None,
    expect_cuda: bool = False,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Run import smoke under Runtime with clean env (subprocess)."""
    from launcher.win_util import _env_for_runtime_python

    rt = runtime_dir(root)
    py = rt / "python.exe"
    if not py.is_file():
        return {"ok": False, "error": "Runtime/python.exe missing", "modules": {}}

    mods = list(imports or _BASELINE_IMPORTS)
    # script prints JSON
    code = r"""
import json, sys
out = {"modules": {}, "torch": None, "cuda": False, "cuda_name": "", "error": ""}
for name in sys.argv[1:]:
    try:
        __import__(name)
        out["modules"][name] = "ok"
    except Exception as e:
        out["modules"][name] = "%s: %s" % (type(e).__name__, e)
try:
    import torch
    out["torch"] = str(getattr(torch, "__version__", ""))
    out["cuda"] = bool(torch.cuda.is_available())
    if out["cuda"]:
        try:
            out["cuda_name"] = torch.cuda.get_device_name(0)
        except Exception as e:
            out["cuda_name"] = str(e)
except Exception as e:
    out["error"] = "torch:" + str(e)
print(json.dumps(out, ensure_ascii=False))
"""
    env = _env_for_runtime_python()
    # integrity probe must not inherit host GPU prefs that force broken paths
    for k in ("TM_USE_DML", "TM_ACCEL", "TM_ACCEL_RESOLVED"):
        env.pop(k, None)
    env["PYTHONPATH"] = str(root)
    env["PYTHONNOUSERSITE"] = "1"
    env["TM_VOICE_ROOT"] = str(root)
    kw: dict[str, Any] = {
        "cwd": str(root),
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "env": env,
    }
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000
    try:
        r = subprocess.run([str(py), "-c", code, *mods], **kw)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "import smoke timeout", "modules": {}}
    except Exception as e:
        return {"ok": False, "error": str(e), "modules": {}}

    data: dict[str, Any] = {}
    line = (r.stdout or "").strip().splitlines()
    if line:
        try:
            data = json.loads(line[-1])
        except json.JSONDecodeError:
            data = {
                "ok": False,
                "error": f"bad smoke stdout rc={r.returncode}: {(r.stdout or '')[:200]}",
                "modules": {},
            }
            if r.stderr:
                data["stderr"] = (r.stderr or "")[:300]
            return data
    else:
        return {
            "ok": False,
            "error": (r.stderr or f"empty smoke rc={r.returncode}")[:200],
            "modules": {},
        }

    modules = data.get("modules") or {}
    failed = [k for k, v in modules.items() if v != "ok"]
    ok = not failed and not data.get("error")
    if expect_cuda and not data.get("cuda"):
        ok = False
        data["error"] = (data.get("error") or "") + " cuda_not_available"
    data["ok"] = ok
    data["failed_imports"] = failed
    data["returncode"] = r.returncode
    return data


def verify_runtime(
    root: Path | None = None,
    *,
    variant: str = "",
    version: str = "",
    require_cuda: Optional[bool] = None,
    fetch_remote: bool = True,
    log: Optional[LogCb] = None,
) -> dict[str, Any]:
    """Full integrity check. Returns structured report with ok bool."""
    base = Path(root or ROOT)
    rt = runtime_dir(base)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "root": str(base),
        "runtime_dir": str(rt),
        "ok": False,
        "variant": variant,
        "version": version,
        "manifest_source": "",
        "files": [],
        "smoke": {},
        "errors": [],
        "warnings": [],
    }

    if not rt.is_dir():
        report["errors"].append("Runtime directory missing")
        _save_report(base, report)
        return report

    # resolve package meta if not given
    if not variant or not version:
        try:
            from launcher.package_meta import load_package_meta

            meta = load_package_meta(base)
            variant = variant or str(meta.get("variant") or "nvidia")
            version = version or str(
                meta.get("runtime_version") or meta.get("version") or ""
            )
        except Exception:
            variant = variant or "nvidia"
    report["variant"] = variant
    report["version"] = version

    if require_cuda is None:
        require_cuda = variant in ("nvidia", "nvidia50")

    manifest: Optional[dict[str, Any]] = None
    if fetch_remote:
        _log(log, f"拉取 Runtime 完整性清单（{variant} {version}）…")
        manifest = fetch_integrity_manifest(variant=variant, version=version)
    if manifest is None:
        manifest = load_bundled_integrity(base, variant)
    if manifest is None:
        # minimal synthetic manifest — file presence + smoke only
        report["warnings"].append("no remote/bundled integrity JSON; using baseline only")
        manifest = {
            "schema": SCHEMA,
            "variant": variant,
            "runtime_version": version,
            "files": [{"path": p, "required": True} for p in _BASELINE_REL_PATHS],
            "imports": list(_BASELINE_IMPORTS),
        }
    report["manifest_source"] = str(manifest.get("_source_url") or "baseline")

    _log(log, "校验关键文件…")
    file_results = check_files(rt, manifest)
    report["files"] = file_results
    # Hard fail: missing required files or sha256 mismatch
    # Soft: size-only mismatch (CNB tar vs reference pack may differ slightly)
    hard = []
    soft = []
    for f in file_results:
        if f.get("ok"):
            continue
        detail = str(f.get("detail") or "")
        if detail == "missing" or "sha256 mismatch" in detail:
            hard.append(f)
        else:
            soft.append(f)
    if hard:
        report["errors"].append(
            f"{len(hard)} critical file issue(s) "
            f"(e.g. {hard[0].get('path')}: {hard[0].get('detail')})"
        )
    if soft:
        report["warnings"].append(
            f"{len(soft)} size/stat warning(s) "
            f"(e.g. {soft[0].get('path')}: {soft[0].get('detail')})"
        )

    imports = manifest.get("imports") or list(_BASELINE_IMPORTS)
    if not isinstance(imports, list):
        imports = list(_BASELINE_IMPORTS)
    _log(log, "Runtime 导入探测（torch/numpy/…）…")
    smoke = smoke_imports(
        base,
        imports=[str(x) for x in imports],
        expect_cuda=bool(require_cuda),
    )
    report["smoke"] = smoke
    if not smoke.get("ok"):
        report["errors"].append(
            "import smoke failed: "
            + str(smoke.get("error") or smoke.get("failed_imports") or "unknown")
        )

    report["ok"] = not report["errors"]
    _save_report(base, report)
    if report["ok"]:
        _log(log, "Runtime 完整性校验通过")
    else:
        _log(log, "Runtime 完整性校验失败：" + "; ".join(report["errors"][:3]))
    return report


def _save_report(root: Path, report: dict[str, Any]) -> None:
    try:
        p = integrity_report_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def format_report_summary(report: dict[str, Any]) -> str:
    if report.get("ok"):
        smoke = report.get("smoke") or {}
        cuda = smoke.get("cuda")
        torch_v = smoke.get("torch") or "?"
        name = smoke.get("cuda_name") or ""
        line = f"Runtime 校验通过 · torch {torch_v}"
        if cuda:
            line += f" · CUDA {name}".rstrip()
        return line
    errs = report.get("errors") or ["unknown"]
    return "Runtime 校验失败：" + "；".join(str(e) for e in errs[:2])
