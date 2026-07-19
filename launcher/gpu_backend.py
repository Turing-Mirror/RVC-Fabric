# -*- coding: utf-8 -*-
"""GPU backend selection — official RVC is environment + switch, not a flag alone.

Official Windows A/I support (README + Changelog)::

  1. **Different install** — ``pip install -r requirements-dml.txt``
     or HF ``RVC1006AMD_Intel.7z`` green Runtime
     (torch + torch-directml, onnxruntime-directml; rmvpe.onnx for DML F0)
  2. **Then** launch with ``--dml`` / go-*-dml.bat so Config uses
     ``torch_directml.device()`` and swaps onnxruntime folders

N-card: requirements.txt / Nvidia 7z + CUDA torch, no --dml.

Shipping: separate full packs (package_meta.json). In-pack ``accel_backend``
only fine-tunes; AMD users should use the AMD pack Runtime, not only flip dml
on a pure CUDA environment.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

# auto | cuda | dml | cpu
VALID = frozenset({"auto", "cuda", "dml", "cpu"})


def normalize_accel(value: str | None) -> str:
    v = (value or "auto").strip().lower()
    if v in ("directml", "amd", "intel"):
        return "dml"
    if v in ("nvidia", "gpu"):
        return "cuda"
    if v not in VALID:
        return "auto"
    return v


def probe_via_runtime_python(python_exe: Path, cwd: Path) -> dict[str, Any]:
    """Run a short probe in Runtime Python (accurate CUDA/DML)."""
    code = r"""
import json
out = {
  "torch": None, "cuda": False, "cuda_name": "", "cuda_ver": None,
  "dml": False, "dml_name": "", "dml_count": 0, "error": ""
}
try:
    import torch
    out["torch"] = str(getattr(torch, "__version__", ""))
    out["cuda"] = bool(torch.cuda.is_available())
    out["cuda_ver"] = getattr(torch.version, "cuda", None)
    if out["cuda"]:
        try:
            out["cuda_name"] = torch.cuda.get_device_name(0)
        except Exception as e:
            out["error"] = "cuda_name:" + str(e)
except Exception as e:
    out["error"] = "torch:" + str(e)
try:
    import torch_directml
    n = int(torch_directml.device_count())
    out["dml_count"] = n
    out["dml"] = n >= 1
    if n >= 1:
        try:
            out["dml_name"] = str(torch_directml.device_name(torch_directml.default_device()))
        except Exception:
            out["dml_name"] = "DirectML"
except Exception:
    pass
print(json.dumps(out, ensure_ascii=False))
"""
    try:
        r = subprocess.run(
            [str(python_exe), "-c", code],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=90,
            env={
                **os.environ,
                "PYTHONPATH": str(cwd),
                "PYTHONNOUSERSITE": "1",
            },
        )
        line = (r.stdout or "").strip().splitlines()
        if not line:
            return {"error": (r.stderr or "empty probe")[:200], "cuda": False, "dml": False}
        return json.loads(line[-1])
    except Exception as e:
        return {"error": str(e), "cuda": False, "dml": False}


def probe_via_wmi() -> dict[str, Any]:
    """Lightweight vendor hint without torch (host process)."""
    info: dict[str, Any] = {
        "vendors": [],
        "names": [],
        "has_nvidia": False,
        "has_amd": False,
        "has_intel_gpu": False,
    }
    if sys.platform != "win32":
        return info
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | "
                "Select-Object -ExpandProperty Name",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
        names = [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]
        info["names"] = names
        for n in names:
            low = n.lower()
            if "nvidia" in low or "geforce" in low or "quadro" in low or "rtx" in low:
                info["has_nvidia"] = True
                info["vendors"].append("nvidia")
            if "amd" in low or "radeon" in low:
                info["has_amd"] = True
                info["vendors"].append("amd")
            if "intel" in low and ("uhd" in low or "iris" in low or "arc" in low or "graphics" in low):
                info["has_intel_gpu"] = True
                info["vendors"].append("intel")
    except Exception:
        pass
    return info


def resolve_backend(
    preference: str = "auto",
    *,
    probe: Optional[dict[str, Any]] = None,
    wmi: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Return resolved backend: cuda | dml | cpu plus labels for UI."""
    pref = normalize_accel(preference)
    probe = probe or {}
    wmi = wmi or {}
    has_cuda = bool(probe.get("cuda"))
    has_dml = bool(probe.get("dml"))

    if pref == "cuda":
        backend = "cuda" if has_cuda else ("cpu" if not has_dml else "cuda")  # force attempt
        if not has_cuda:
            backend = "cpu"
    elif pref == "dml":
        backend = "dml" if has_dml else "cpu"
    elif pref == "cpu":
        backend = "cpu"
    else:
        # auto — official spirit: CUDA first, else DirectML, else CPU
        if has_cuda:
            backend = "cuda"
        elif has_dml:
            backend = "dml"
        elif wmi.get("has_amd") or wmi.get("has_intel_gpu"):
            # Package may still have dml libs; try dml if import said no but vendor is A/I
            backend = "dml" if has_dml else "cpu"
        else:
            backend = "cpu"

    labels = {
        "cuda": "NVIDIA CUDA",
        "dml": "AMD/Intel DirectML",
        "cpu": "CPU",
    }
    detail = ""
    if backend == "cuda":
        detail = str(probe.get("cuda_name") or "")
    elif backend == "dml":
        detail = str(probe.get("dml_name") or "DirectML")
    elif probe.get("error"):
        detail = str(probe.get("error"))[:80]

    return {
        "preference": pref,
        "backend": backend,
        "use_dml": backend == "dml",
        "label": labels.get(backend, backend),
        "detail": detail,
        "has_cuda": has_cuda,
        "has_dml": has_dml,
        "torch": probe.get("torch"),
        "wmi_names": wmi.get("names") or [],
    }


def apply_backend_env(env: dict, resolved: dict[str, Any]) -> dict:
    """Mutate env for child Runtime processes (gui_v1 / worker / webui)."""
    env = dict(env)
    backend = resolved.get("backend") or "cpu"
    env["TM_ACCEL"] = str(resolved.get("preference") or "auto")
    env["TM_ACCEL_RESOLVED"] = backend
    if backend == "dml":
        env["TM_USE_DML"] = "1"
    else:
        env["TM_USE_DML"] = "0"
    return env


def detect_full(root: Path, preference: str = "auto") -> dict[str, Any]:
    """Full detection using Runtime python if present."""
    from launcher.paths import find_python  # late import

    wmi = probe_via_wmi()
    py = None
    for cand in (
        root / "Runtime" / "python.exe",
        root / "runtime" / "python.exe",
    ):
        if cand.is_file():
            py = cand
            break
    if py is None:
        try:
            p = find_python(prefer_windowed=False)
            if p and "python" in Path(p).name.lower():
                py = Path(p)
        except Exception:
            pass
    probe: dict[str, Any] = {}
    if py and py.is_file():
        probe = probe_via_runtime_python(py, root)
    resolved = resolve_backend(preference, probe=probe, wmi=wmi)
    resolved["probe"] = probe
    resolved["wmi"] = wmi
    return resolved
