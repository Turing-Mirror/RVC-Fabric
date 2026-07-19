# -*- coding: utf-8 -*-
"""Optional smoke: probe local RVCMAX Runtimes (skip if missing).

Official matrix expectations:
  - nvidia: CUDA torch
  - amd: no CUDA, torch_directml available
  - nvidia50: CUDA (typically cu12x), may lack DirectML
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PACKS = {
    "nvidia": ROOT / "RVCMAX" / "RVCMAX_Nvidia_xiaoyuan" / "Runtime" / "python.exe",
    "amd": ROOT / "RVCMAX" / "RVCMAX_AMD_xiaoyuan" / "Runtime" / "python.exe",
    "nvidia50": ROOT
    / "RVCMAX"
    / "RVCMAX_Nvidia50x0_xiaoyuan"
    / "Runtime"
    / "python.exe",
}

PROBE = r"""
import json
out = {"torch": None, "cuda": False, "cuda_ver": None, "dml": False, "error": ""}
try:
    import torch
    out["torch"] = str(getattr(torch, "__version__", ""))
    out["cuda"] = bool(torch.cuda.is_available())
    out["cuda_ver"] = getattr(torch.version, "cuda", None)
except Exception as e:
    out["error"] = "torch:" + str(e)
try:
    import torch_directml
    out["dml"] = int(torch_directml.device_count()) >= 1
except Exception:
    out["dml"] = False
print(json.dumps(out))
"""


def _probe(py: Path) -> dict:
    r = subprocess.run(
        [str(py), "-c", PROBE],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "probe failed")[:400])
    line = (r.stdout or "").strip().splitlines()
    if not line:
        raise RuntimeError("empty probe")
    return json.loads(line[-1])


@unittest.skipUnless(any(p.is_file() for p in PACKS.values()), "no RVCMAX Runtimes")
class RuntimeSmokeTests(unittest.TestCase):
    def test_nvidia_has_cuda(self):
        py = PACKS["nvidia"]
        if not py.is_file():
            self.skipTest("no nvidia Runtime")
        info = _probe(py)
        self.assertFalse(info.get("error"), msg=info)
        self.assertTrue(info.get("cuda"), msg=info)
        self.assertIn("cu", (info.get("torch") or "").lower())

    def test_amd_is_dml_not_cuda(self):
        py = PACKS["amd"]
        if not py.is_file():
            self.skipTest("no amd Runtime")
        info = _probe(py)
        self.assertFalse(info.get("error"), msg=info)
        self.assertFalse(info.get("cuda"), msg=f"AMD pack should be CPU+DML: {info}")
        self.assertTrue(info.get("dml"), msg=f"AMD pack needs torch_directml: {info}")

    def test_nvidia50_has_cuda(self):
        py = PACKS["nvidia50"]
        if not py.is_file():
            self.skipTest("no nvidia50 Runtime")
        info = _probe(py)
        self.assertFalse(info.get("error"), msg=info)
        self.assertTrue(info.get("cuda"), msg=info)
        # 50-series packs ship newer CUDA (12.x) — soft check
        ver = str(info.get("cuda_ver") or "")
        if ver:
            major = int(ver.split(".")[0])
            self.assertGreaterEqual(major, 12, msg=info)


if __name__ == "__main__":
    unittest.main()
