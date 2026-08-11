"""RMVPE 长音频分片推理的等价性测试。

分片是为了让 3GB 显卡不 OOM，但分片本身不许改变结果。E2E 的 fc 头第一层是
双向 GRU（infer/lib/rmvpe.py），时间轴上前后都有依赖，所以切片必须带重叠、
只保留中段。这里用两个替身模型验证：

* 卷积替身：感受野 65 帧 < 128 帧上下文，分片结果必须和整段**完全**一致；
* 双向 GRU 替身：隐藏状态靠 128 帧预热收敛，分片结果必须和整段**近似**一致。

需要 torch，没装就整体跳过（Mac 开发机上没有）。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import torch
    import torch.nn as nn

    HAVE_TORCH = True
except Exception:  # pragma: no cover - 开发机没装 torch
    HAVE_TORCH = False


N_MELS = 128
N_CLASS = 360


if HAVE_TORCH:

    class ConvStub(nn.Module):
        """时间轴上局部依赖：感受野 65 帧。"""

        def __init__(self) -> None:
            super().__init__()
            self.conv = nn.Conv1d(N_MELS, N_CLASS, kernel_size=65, padding=32)

        def forward(self, mel):  # (B, n_mels, T) -> (B, T, N_CLASS)
            return self.conv(mel).transpose(1, 2)

    class BiGruStub(nn.Module):
        """时间轴上全局依赖，和真模型的 fc 头同构。"""

        def __init__(self) -> None:
            super().__init__()
            self.gru = nn.GRU(N_MELS, 64, num_layers=1, batch_first=True, bidirectional=True)
            self.fc = nn.Linear(128, N_CLASS)

        def forward(self, mel):  # (B, n_mels, T) -> (B, T, N_CLASS)
            x = mel.transpose(1, 2)
            return self.fc(self.gru(x)[0])


def _make_rmvpe(model):
    """绕开 __init__（会去磁盘读 rmvpe.pt），只装配 mel2hidden 需要的字段。"""
    from infer.lib.rmvpe import RMVPE

    obj = RMVPE.__new__(RMVPE)
    obj.device = "cpu"
    obj.is_half = False
    obj.model = model
    return obj


@unittest.skipUnless(HAVE_TORCH, "需要 torch")
class Mel2HiddenChunkingTests(unittest.TestCase):
    # 3200 帧 = 32 s @ hop 160 / 16 kHz，跨 4 个 1024 帧分片。
    N_FRAMES = 3200

    def _mel(self):
        torch.manual_seed(0)
        return torch.randn(1, N_MELS, self.N_FRAMES)

    def _reference(self, rmvpe, mel):
        """整段一次过，作为基准。"""
        with torch.no_grad():
            n_pad = 32 * ((mel.shape[-1] - 1) // 32 + 1) - mel.shape[-1]
            padded = torch.nn.functional.pad(mel, (0, n_pad)) if n_pad else mel
            return rmvpe._mel2hidden_chunk(padded)[:, : mel.shape[-1]]

    def test_shape_and_local_model_is_exact(self):
        torch.manual_seed(1)
        rmvpe = _make_rmvpe(ConvStub().eval())
        mel = self._mel()
        got = rmvpe.mel2hidden(mel)
        self.assertEqual(tuple(got.shape), (1, self.N_FRAMES, N_CLASS))
        want = self._reference(rmvpe, mel)
        # 感受野落在上下文里，分片不该带来任何差异。
        self.assertTrue(torch.allclose(got, want, atol=1e-5), "分片改变了局部模型的输出")

    def test_bidirectional_rnn_converges(self):
        torch.manual_seed(2)
        rmvpe = _make_rmvpe(BiGruStub().eval())
        mel = self._mel()
        got = rmvpe.mel2hidden(mel)
        want = self._reference(rmvpe, mel)
        err = (got - want).abs().max().item()
        # 128 帧预热后残差应当远小于输出量级；没有重叠时这里是 1e-1 量级。
        self.assertLess(err, 1e-3, f"双向 RNN 在分片边界没收敛，最大误差 {err}")

    def test_short_clip_takes_single_shot_path(self):
        torch.manual_seed(3)
        rmvpe = _make_rmvpe(ConvStub().eval())
        mel = torch.randn(1, N_MELS, 500)
        got = rmvpe.mel2hidden(mel)
        self.assertEqual(tuple(got.shape), (1, 500, N_CLASS))
        self.assertTrue(torch.allclose(got, self._reference(rmvpe, mel), atol=1e-6))


if __name__ == "__main__":
    unittest.main()
