# -*- coding: utf-8 -*-
"""Unit tests for launcher.gpu_backend (mocked probe, no torch)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launcher.gpu_backend import (
    apply_backend_env,
    normalize_accel,
    resolve_backend,
)


class NormalizeTests(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(normalize_accel("directml"), "dml")
        self.assertEqual(normalize_accel("AMD"), "dml")
        self.assertEqual(normalize_accel("intel"), "dml")
        self.assertEqual(normalize_accel("nvidia"), "cuda")
        self.assertEqual(normalize_accel("GPU"), "cuda")
        self.assertEqual(normalize_accel("bogus"), "auto")
        self.assertEqual(normalize_accel(None), "auto")


class ResolveBackendTests(unittest.TestCase):
    def test_auto_prefers_cuda(self):
        r = resolve_backend(
            "auto",
            probe={"cuda": True, "cuda_name": "RTX", "dml": True},
            wmi={},
        )
        self.assertEqual(r["backend"], "cuda")
        self.assertFalse(r["use_dml"])

    def test_auto_falls_to_dml(self):
        r = resolve_backend(
            "auto",
            probe={"cuda": False, "dml": True, "dml_name": "Radeon"},
            wmi={"has_amd": True},
        )
        self.assertEqual(r["backend"], "dml")
        self.assertTrue(r["use_dml"])

    def test_force_dml_without_dml_goes_cpu(self):
        r = resolve_backend("dml", probe={"cuda": True, "dml": False}, wmi={})
        self.assertEqual(r["backend"], "cpu")

    def test_force_cuda_without_cuda_goes_cpu(self):
        r = resolve_backend("cuda", probe={"cuda": False, "dml": True}, wmi={})
        self.assertEqual(r["backend"], "cpu")

    def test_nvidia_pack_trusts_cuda_when_probe_empty(self):
        """diag_20260727: empty probe on nvidia pack must not force CPU."""
        empty = {
            "cuda": False,
            "dml": False,
            "error": "empty probe rc=1 | pe=python.exe",
        }
        r = resolve_backend(
            "cuda", probe=empty, wmi={}, package_variant="nvidia"
        )
        self.assertEqual(r["backend"], "cuda")
        self.assertIn("探测未确认", r["detail"])
        r_auto = resolve_backend(
            "auto", probe=empty, wmi={}, package_variant="nvidia"
        )
        self.assertEqual(r_auto["backend"], "cuda")

    def test_nvidia_pack_still_rejects_capability_mismatch(self):
        bad = {
            "cuda": False,
            "dml": False,
            "error": (
                "NVIDIA GeForce RTX 5060 (sm_120) incompatible with PyTorch "
                "(supports sm_37, sm_50, sm_60, sm_61, sm_70, sm_75, sm_80, "
                "sm_86, sm_90); 50-series needs nvidia50 variant"
            ),
        }
        r = resolve_backend(
            "cuda", probe=bad, wmi={}, package_variant="nvidia"
        )
        self.assertEqual(r["backend"], "cpu")

    def test_cpu(self):
        r = resolve_backend("cpu", probe={"cuda": True, "dml": True}, wmi={})
        self.assertEqual(r["backend"], "cpu")
        self.assertFalse(r["use_dml"])


class ApplyEnvTests(unittest.TestCase):
    def test_dml_env_inplace(self):
        env = {}
        out = apply_backend_env(
            env,
            {"backend": "dml", "preference": "dml", "use_dml": True},
        )
        self.assertIs(out, env)  # same object — mutates in place
        self.assertEqual(env["TM_USE_DML"], "1")
        self.assertEqual(env["TM_ACCEL"], "dml")
        self.assertEqual(env["TM_ACCEL_RESOLVED"], "dml")

    def test_cuda_env_overwrites(self):
        env = {"TM_USE_DML": "1"}
        apply_backend_env(env, {"backend": "cuda", "preference": "auto"})
        self.assertEqual(env["TM_USE_DML"], "0")
        self.assertEqual(env["TM_ACCEL_RESOLVED"], "cuda")

    def test_amd_pack_prefers_dml_when_probe_empty(self):
        r = resolve_backend(
            "auto",
            probe={"cuda": False, "dml": False},
            wmi={},
            package_variant="amd",
        )
        self.assertEqual(r["backend"], "dml")
        self.assertTrue(r["use_dml"])


if __name__ == "__main__":
    unittest.main()
