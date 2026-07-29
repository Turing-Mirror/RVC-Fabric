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
from typing import Any, MutableMapping, Optional

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


def _probe_env(cwd: Path) -> dict:
    """Env for Runtime probe — strip PyInstaller host pollution (same spirit as worker)."""
    try:
        from launcher.win_util import _env_for_runtime_python

        env = _env_for_runtime_python()
    except Exception:
        env = dict(os.environ)
        for k in list(env.keys()):
            ku = k.upper()
            if ku.startswith("PYTHON") or ku in {
                "_MEIPASS",
                "TCL_LIBRARY",
                "TK_LIBRARY",
                "TIX_LIBRARY",
            }:
                del env[k]
    # Probe raw capability — do not force DML/CUDA preference into the probe process
    for k in ("TM_USE_DML", "TM_ACCEL", "TM_ACCEL_RESOLVED"):
        env.pop(k, None)
    env["PYTHONPATH"] = str(cwd)
    env["PYTHONNOUSERSITE"] = "1"
    env["TM_VOICE_ROOT"] = str(cwd)
    return env


def probe_inprocess() -> dict[str, Any]:
    """Probe CUDA/DML in the current process (no child, no black console).

    Main app already runs under Runtime\\pythonw.exe, so torch is importable here.
    Spawning Runtime\\python.exe for this was the flash titled \"…\\python.exe\".
    """
    out: dict[str, Any] = {
        "torch": None,
        "cuda": False,
        "cuda_name": "",
        "cuda_ver": None,
        "dml": False,
        "dml_name": "",
        "dml_count": 0,
        "error": "",
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
            # Reject incompatible compute capability (e.g. RTX 5060 sm_120 + cu118 torch)
            cap_ok, cap_reason = _cuda_capability_compatible(torch)
            if not cap_ok:
                out["cuda"] = False
                out["cuda_name"] = ""
                out["error"] = cap_reason
    except Exception as e:
        out["error"] = "torch:" + str(e)
    try:
        import torch_directml  # type: ignore

        n = int(torch_directml.device_count())
        out["dml_count"] = n
        out["dml"] = n >= 1
        if n >= 1:
            try:
                out["dml_name"] = str(
                    torch_directml.device_name(torch_directml.default_device())
                )
            except Exception:
                out["dml_name"] = "DirectML"
    except Exception:
        pass
    return out


def _running_under_runtime(root: Path) -> bool:
    """True if this interpreter lives under package Runtime/."""
    try:
        exe = Path(sys.executable).resolve()
        for name in ("Runtime", "runtime"):
            rt = (Path(root) / name).resolve()
            if rt.is_dir() and (rt == exe.parent or rt in exe.parents):
                return True
    except Exception:
        pass
    return False


def _probe_log(cwd: Path, msg: str) -> None:
    """Append one line to User_Data/logs/gpu_probe.log (best-effort)."""
    try:
        log_dir = Path(cwd) / "User_Data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "gpu_probe.log", "a", encoding="utf-8", errors="replace") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass


def _cuda_capability_compatible(torch_module: Any) -> tuple[bool, str]:
    """Check if the CUDA device's compute capability is supported by torch.

    torch.cuda.is_available() only checks driver + device presence. RTX 50-series
    (Blackwell, sm_120) + torch cu118 (max sm_90) reports is_available()=True but
    crashes natively on kernel execution (no kernel image for sm_120).

    Compatibility rule: a cubin for sm_{A}{B} runs on device (X, Y) when A == X
    and B <= Y (forward-compat within the same major version). Cross-major does
    NOT work; PTX JIT is unreliable across generations. This avoids false-
    positive on RTX 40-series (sm_89), which runs fine on cu118 via sm_86 cubin.
    Returns (compatible, reason).
    """
    try:
        if not torch_module.cuda.is_available():
            return (True, "")
        cap = torch_module.cuda.get_device_capability(0)
        dev_major, dev_minor = int(cap[0]), int(cap[1])
        arch_list = list(torch_module.cuda.get_arch_list())

        def _parse_sm(s: str):
            if not s.startswith("sm_"):
                return None
            digits = s[3:]
            if not digits.isdigit() or len(digits) < 2:
                return None
            return (int(digits[:-1]), int(digits[-1]))

        for s in arch_list:
            parsed = _parse_sm(s)
            if parsed is None:
                continue
            a_major, a_minor = parsed
            if a_major == dev_major and a_minor <= dev_minor:
                return (True, "")

        name = str(torch_module.cuda.get_device_name(0))
        reason = (
            f"{name} (sm_{dev_major}{dev_minor}) incompatible with PyTorch "
            f"(supports {', '.join(arch_list)}); 50-series needs nvidia50 variant"
        )
        return (False, reason)
    except Exception:
        return (True, "")


def probe_via_runtime_python(python_exe: Path, cwd: Path) -> dict[str, Any]:
    """Subprocess probe under Runtime.

    Prefer ``python.exe`` + CREATE_NO_WINDOW (stdout/stderr reliable).
    Also write JSON to a temp file so a silent crash still leaves a trail.
    Avoid relying on pythonw stdout alone (can be empty on some hosts).
    """
    pe = Path(python_exe)
    # Prefer console python with hidden window — capture works; no black box.
    if pe.name.lower() == "pythonw.exe":
        py_console = pe.with_name("python.exe")
        if py_console.is_file():
            pe = py_console
    if not pe.is_file():
        return {"error": f"probe python missing: {python_exe}", "cuda": False, "dml": False}

    cwd = Path(cwd)
    out_file = cwd / "User_Data" / "runtime_control" / "gpu_probe.json"
    try:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        if out_file.is_file():
            out_file.unlink()
    except Exception:
        pass

    # Write result to file (and print) so we can recover if stdout is lost.
    code = r"""
import json, sys
out = {
  "torch": None, "cuda": False, "cuda_name": "", "cuda_ver": None,
  "dml": False, "dml_name": "", "dml_count": 0, "error": ""
}
def _cap_compat(torch_module):
    try:
        if not torch_module.cuda.is_available():
            return (True, "")
        cap = torch_module.cuda.get_device_capability(0)
        dev_major, dev_minor = int(cap[0]), int(cap[1])
        arch_list = list(torch_module.cuda.get_arch_list())
        def _parse_sm(s):
            if not s.startswith("sm_"):
                return None
            digits = s[3:]
            if not digits.isdigit() or len(digits) < 2:
                return None
            return (int(digits[:-1]), int(digits[-1]))
        for s in arch_list:
            parsed = _parse_sm(s)
            if parsed is None:
                continue
            a_major, a_minor = parsed
            if a_major == dev_major and a_minor <= dev_minor:
                return (True, "")
        name = str(torch_module.cuda.get_device_name(0))
        reason = (
            "%s (sm_%d%d) incompatible with PyTorch (supports %s); "
            "50-series needs nvidia50 variant"
        ) % (name, dev_major, dev_minor, ", ".join(arch_list))
        return (False, reason)
    except Exception:
        return (True, "")
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
        cap_ok, cap_reason = _cap_compat(torch)
        if not cap_ok:
            out["cuda"] = False
            out["cuda_name"] = ""
            out["error"] = cap_reason
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
payload = json.dumps(out, ensure_ascii=False)
print(payload)
try:
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        f.write(payload)
except Exception:
    pass
"""
    try:
        env = _probe_env(cwd)
        kw: dict[str, Any] = {
            "cwd": str(cwd),
            "capture_output": True,
            "text": True,
            "timeout": 120,
            "env": env,
        }
        if sys.platform == "win32":
            kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0
                kw["startupinfo"] = si
            except Exception:
                pass
        r = subprocess.run(
            [str(pe), "-c", code, str(out_file)],
            **kw,
        )
        # 1) stdout JSON
        data: Optional[dict[str, Any]] = None
        line = (r.stdout or "").strip().splitlines()
        if line:
            try:
                data = json.loads(line[-1])
            except json.JSONDecodeError:
                data = None
        # 2) file fallback
        if data is None and out_file.is_file():
            try:
                data = json.loads(out_file.read_text(encoding="utf-8"))
            except Exception:
                data = None
        if isinstance(data, dict) and (
            data.get("torch") is not None or data.get("error") or data.get("cuda") or data.get("dml")
        ):
            _probe_log(
                cwd,
                f"probe ok pe={pe.name} rc={r.returncode} "
                f"torch={data.get('torch')} cuda={data.get('cuda')} dml={data.get('dml')} "
                f"err={data.get('error')!r}",
            )
            return data

        err_bits = [
            f"empty probe rc={r.returncode}",
            f"pe={pe.name}",
        ]
        if r.stderr:
            err_bits.append((r.stderr or "").strip()[:160])
        if r.stdout:
            err_bits.append("stdout=" + (r.stdout or "").strip()[:80])
        err = " | ".join(err_bits)[:200]
        _probe_log(cwd, f"probe fail {err}")
        return {"error": err, "cuda": False, "dml": False}
    except subprocess.TimeoutExpired:
        _probe_log(cwd, "probe timeout 120s")
        return {"error": "probe timeout (torch load >120s)", "cuda": False, "dml": False}
    except Exception as e:
        _probe_log(cwd, f"probe exception {e}")
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
            if "intel" in low and (
                "uhd" in low or "iris" in low or "arc" in low or "graphics" in low
            ):
                info["has_intel_gpu"] = True
                info["vendors"].append("intel")
    except Exception:
        pass
    return info


def _probe_hard_rejects_cuda(probe: dict[str, Any]) -> bool:
    """True when probe positively ruled out CUDA (e.g. 50-series on cu118).

    Empty / failed probes (``empty probe rc=1``) are *not* hard rejects — the
    NVIDIA shipping pack should still prefer CUDA; the worker re-detects.
    """
    err = str(probe.get("error") or "")
    if "incompatible with PyTorch" in err or "50-series needs" in err:
        return True
    return False


def resolve_backend(
    preference: str = "auto",
    *,
    probe: Optional[dict[str, Any]] = None,
    wmi: Optional[dict[str, Any]] = None,
    package_variant: str | None = None,
) -> dict[str, Any]:
    """Return resolved backend: cuda | dml | cpu plus labels for UI."""
    pref = normalize_accel(preference)
    probe = probe or {}
    wmi = wmi or {}
    has_cuda = bool(probe.get("cuda"))
    has_dml = bool(probe.get("dml"))
    var = (package_variant or "").strip().lower()
    # NVIDIA shipping packs: empty probe must not force UI/env to CPU
    # (diag_20260727_151048: RTX 3050 + nvidia pack, probe empty → resolved=cpu
    # while worker still found cuda:0 and ran fine).
    nvidia_pack = var in ("nvidia", "nvidia50")
    trust_nvidia_cuda = nvidia_pack and not _probe_hard_rejects_cuda(probe)

    if pref == "cuda":
        if has_cuda or trust_nvidia_cuda:
            backend = "cuda"
        else:
            backend = "cpu"
    elif pref == "dml":
        # Prefer DML when pack is AMD even if probe failed (Config may still work)
        if has_dml:
            backend = "dml"
        elif var == "amd":
            backend = "dml"
        else:
            backend = "cpu"
    elif pref == "cpu":
        backend = "cpu"
    else:
        # auto — CUDA first, else DirectML, else CPU
        if has_cuda:
            backend = "cuda"
        elif has_dml:
            backend = "dml"
        elif var == "amd":
            # AMD shipping pack: default try DML even if probe was empty
            backend = "dml"
        elif trust_nvidia_cuda:
            backend = "cuda"
        elif wmi.get("has_amd") or wmi.get("has_intel_gpu"):
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
        if not has_cuda and trust_nvidia_cuda:
            detail = (detail + " · 探测未确认").strip(" ·")
    elif backend == "dml":
        detail = str(probe.get("dml_name") or "DirectML")
        if not has_dml and var == "amd":
            detail = (detail + " · 探测未确认").strip(" ·")
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


def apply_backend_env(
    env: MutableMapping[str, str], resolved: dict[str, Any]
) -> MutableMapping[str, str]:
    """Set TM_* backend keys **in place** on *env* (works with os.environ).

    Returns the same mapping for chaining.
    """
    backend = str(resolved.get("backend") or "cpu")
    env["TM_ACCEL"] = str(resolved.get("preference") or "auto")
    env["TM_ACCEL_RESOLVED"] = backend
    env["TM_USE_DML"] = "1" if backend == "dml" else "0"
    return env


def detect_full(root: Path, preference: str = "auto") -> dict[str, Any]:
    """Full detection — in-process under Runtime (no Runtime\\python.exe child)."""
    from launcher.paths import find_python  # late import

    wmi = probe_via_wmi()
    probe: dict[str, Any] = {}
    if _running_under_runtime(root):
        # App/worker already on Runtime pythonw — probe here, zero console windows
        probe = probe_inprocess()
    else:
        py = None
        for cand in (
            root / "Runtime" / "pythonw.exe",
            root / "runtime" / "pythonw.exe",
        ):
            if cand.is_file():
                py = cand
                break
        if py is None:
            try:
                p = find_python(prefer_windowed=True)
                if p and Path(p).name.lower() == "pythonw.exe" and Path(p).is_file():
                    py = Path(p)
            except Exception:
                pass
        if py is not None:
            probe = probe_via_runtime_python(py, root)
        else:
            probe = probe_inprocess()

    package_variant = None
    try:
        from launcher.package_meta import load_package_meta

        package_variant = str(load_package_meta(root).get("variant") or "")
    except Exception:
        package_variant = None

    resolved = resolve_backend(
        preference,
        probe=probe,
        wmi=wmi,
        package_variant=package_variant,
    )
    resolved["probe"] = probe
    resolved["wmi"] = wmi
    resolved["package_variant"] = package_variant or ""
    return resolved
