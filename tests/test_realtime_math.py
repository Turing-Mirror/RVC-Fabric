# -*- coding: utf-8 -*-
"""Math-equivalence checks for inference-side optimizations.

These verify that the GPU index blend and the vectorized RMVPE decode produce
the same numbers as the original CPU/loop implementations. They need pytest +
Runtime stack (torch etc.). Without pytest, unittest discover soft-skips so
the product suite stays green on hosts without ML deps:

    scripts\\run_tests.bat  (or Runtime\\python.exe -m pytest tests -k realtime_math)
"""

from __future__ import annotations

import importlib.util
import types
import unittest

_HAS_PYTEST = importlib.util.find_spec("pytest") is not None


def _reference_index_blend(q, bank, np):
    """Original CPU faiss path semantics with exact (non-IVF) search."""
    d = ((q[:, None, :] - bank[None, :, :]) ** 2).sum(-1)  # squared L2
    ix = np.argsort(d, axis=1)[:, :8]
    score = np.take_along_axis(d, ix, axis=1)
    weight = np.square(1.0 / np.maximum(score, 1e-4))
    weight /= weight.sum(axis=1, keepdims=True) + 1e-8
    return np.sum(bank[ix] * weight[:, :, None], axis=1)


def _reference_local_average_cents(cents_mapping, salience, thred, np):
    """Verbatim copy of the original per-frame loop implementation."""
    center = np.argmax(salience, axis=1)
    salience = np.pad(salience, ((0, 0), (4, 4)))
    center += 4
    todo_salience = []
    todo_cents_mapping = []
    starts = center - 4
    ends = center + 5
    for idx in range(salience.shape[0]):
        todo_salience.append(salience[:, starts[idx] : ends[idx]][idx])
        todo_cents_mapping.append(cents_mapping[starts[idx] : ends[idx]])
    todo_salience = np.array(todo_salience)
    todo_cents_mapping = np.array(todo_cents_mapping)
    product_sum = np.sum(todo_salience * todo_cents_mapping, 1)
    weight_sum = np.sum(todo_salience, 1)
    devided = product_sum / weight_sum
    maxx = np.max(salience, axis=1)
    devided[maxx <= thred] = 0
    return devided


def _reference_f0_post(f0, mel_min, mel_max, np):
    """Original masked-assignment implementation of get_f0_post."""
    f0_mel = 1127 * np.log(1 + f0 / 700)
    mask = f0_mel > 0
    f0_mel[mask] = (f0_mel[mask] - mel_min) * 254 / (mel_max - mel_min) + 1
    f0_mel[f0_mel <= 1] = 1
    f0_mel[f0_mel > 255] = 255
    return np.rint(f0_mel).astype(np.int64)


@unittest.skipUnless(_HAS_PYTEST, "pytest not installed")
class RealtimeMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pytest

        cls.pytest = pytest
        cls.np = pytest.importorskip("numpy")
        cls.torch = pytest.importorskip("torch")

    def test_index_blend_gpu_matches_cpu_reference(self):
        from infer.lib.rtrvc import RVC

        np, torch = self.np, self.torch
        rng = np.random.default_rng(7)
        bank = rng.standard_normal((64, 12)).astype(np.float32)
        q = rng.standard_normal((5, 12)).astype(np.float32)

        ns = types.SimpleNamespace(
            _index_bank=torch.from_numpy(bank),  # fp32 on CPU: dtype-adaptive code path
            _index_bank_sq=torch.from_numpy(np.square(bank).sum(axis=1)),
        )
        got = RVC._index_blend_gpu(ns, torch.from_numpy(q)).numpy()
        ref = _reference_index_blend(q, bank, np)
        self.assertTrue(np.allclose(got, ref, rtol=1e-4, atol=1e-5))

    def test_rmvpe_decode_matches_loop_reference(self):
        self.pytest.importorskip("librosa")
        from infer.lib.rmvpe import RMVPE

        np = self.np
        cents_mapping = np.pad(20 * np.arange(360) + 1997.3794084376191, (4, 4))
        ns = types.SimpleNamespace(cents_mapping=cents_mapping)

        rng = np.random.default_rng(11)
        salience = rng.random((40, 360)).astype(np.float32)
        salience[3] *= 1e-4  # below-threshold frame must decode to 0
        # peaks at the edges exercise the padded window
        salience[5, 0] = 5.0
        salience[7, 359] = 5.0

        got = RMVPE.to_local_average_cents(ns, salience.copy(), thred=0.03)
        ref = _reference_local_average_cents(
            cents_mapping, salience.copy(), 0.03, np
        )
        self.assertTrue(
            np.allclose(got, ref, rtol=1e-6, atol=1e-8, equal_nan=True)
        )

    def test_get_f0_post_branchless_matches_reference(self):
        from infer.lib.rtrvc import RVC

        np = self.np
        f0_min, f0_max = 50, 1100
        ns = types.SimpleNamespace(
            device="cpu",
            f0_mel_min=1127 * np.log(1 + f0_min / 700),
            f0_mel_max=1127 * np.log(1 + f0_max / 700),
        )
        rng = np.random.default_rng(3)
        f0 = rng.uniform(0, 1200, size=200).astype(np.float32)
        f0[::7] = 0.0  # unvoiced frames

        coarse, f0_out = RVC.get_f0_post(ns, f0.copy())
        # reference in fp32 to mirror get_f0_post's .float() pipeline
        ref = _reference_f0_post(
            f0.astype(np.float32).copy(), ns.f0_mel_min, ns.f0_mel_max, np
        )
        self.assertTrue(np.array_equal(coarse.numpy(), ref))
        self.assertTrue(np.allclose(f0_out.numpy(), f0, rtol=1e-6))


if __name__ == "__main__":
    unittest.main()
