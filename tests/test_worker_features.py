"""Exercise the actual worker handlers without importing the desktop/audio stack."""
import ast
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, mock_open, patch

ROOT = Path(__file__).resolve().parents[1]
# 单跑本文件时也要找得到 tools/ —— 不靠别的测试先把仓库根塞进 sys.path。
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def handler(name, **globals_):
    tree = ast.parse((ROOT / "gui_v1.py").read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = dict(os=os, json=json, flag_vc=False, printt=lambda *a: None, **globals_)
    exec(compile(ast.Module(body=[node], type_ignores=[]), "gui_v1.py", "exec"), scope)
    return scope[name]


class WorkerFeatureTests(unittest.TestCase):
    def test_pitch_repair_can_be_enabled_and_disabled_in_the_worker(self):
        engine = SimpleNamespace(gui_config=SimpleNamespace(f0_repair=False),
                                 rvc=SimpleNamespace(f0_repair=False))
        apply = handler("_worker_apply_hot")
        for enabled in (True, False):
            apply(engine, {"f0_repair": enabled})
            self.assertEqual(engine.gui_config.f0_repair, enabled)
            self.assertEqual(engine.rvc.f0_repair, enabled)

    def test_prewarm_reads_the_saved_voice_before_the_first_stream(self):
        model = SimpleNamespace(tgt_sr=40000, net_g=object())
        loader = Mock(return_value=model)
        engine = SimpleNamespace(gui_config=SimpleNamespace(pth_path="", n_cpu=2), config=object())
        run = handler(
            "_cmd_prewarm",
            rvc_for_realtime=SimpleNamespace(RVC=loader),
            inp_q=None,
            opt_q=None,
            threading=threading,
            traceback=traceback,
        )
        saved = dict(pth_path="voice.pth", index_path="voice.index", pitch=12, formant=1.0, index_rate=0.6)
        with patch("builtins.open", mock_open(read_data=json.dumps(saved))), patch("os.path.isfile", return_value=True):
            run(engine)
            deadline = time.time() + 2
            while getattr(engine, "_prewarm_busy", False) and time.time() < deadline:
                time.sleep(0.01)
        self.assertEqual(loader.call_args.args[:6], (12, 1.0, "voice.pth", "voice.index", 0.6, 2))
        self.assertIs(engine._prewarmed, model)

    def test_repeated_oom_reaches_cpu_but_invalid_audio_does_not(self):
        from tools import sts_core as core
        for reason, fallback in (("CUDA out of memory", True), ("invalid audio", False)):
            vc = Mock()
            vc.vc_single.side_effect = RuntimeError(reason)
            opts = dict(pitch=0, f0method="rmvpe", index_path="", index_rate=0,
                        filter_radius=3, resample_sr=0, rms_mix_rate=0.25, protect=0.33,
                        on_stage=lambda *a: None, wavfile=Mock())
            with patch.object(core, "cuda_empty_cache"), patch.object(core, "move_models_to_cpu", return_value=True) as move:
                with self.assertRaises(RuntimeError):
                    core.convert_one_with_cpu_fallback(vc, Path("in.wav"), Path("out.wav"), **opts)
            self.assertEqual(move.called, fallback)


if __name__ == "__main__":
    unittest.main()
