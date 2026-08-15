# -*- coding: utf-8 -*-
"""tools/train_worker.py 单元测试 —— 只测不需要 torch 的部分。

训练本身没法在 CI 里跑（要 N 卡、要几小时），但**解析和拼装**这两件事错了
会让用户白等一整晚，所以它们必须有测试：进度读不出来 = 进度条不动；filelist
拼错 = 训练在最后一步炸。
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load():
    path = ROOT / "tools" / "train_worker.py"
    spec = importlib.util.spec_from_file_location("tm_train_worker", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tw = _load()


class _Capture:
    """接住 emit 打出去的 JSON 行。"""

    def __init__(self):
        self.buf = io.StringIO()
        self._real = sys.stdout

    def __enter__(self):
        sys.stdout = self.buf
        return self

    def __exit__(self, *a):
        sys.stdout = self._real

    def lines(self):
        return [json.loads(x) for x in self.buf.getvalue().splitlines() if x.strip()]


class NormalizeTests(unittest.TestCase):
    def test_rejects_names_that_would_break_a_path(self):
        for bad in ("", "   ", "a/b", "a\\b", "c:d", "x?y"):
            with self.assertRaises(SystemExit):
                with _Capture():
                    tw.normalize({"exp": bad})

    def test_rejects_an_unsupported_sample_rate(self):
        with self.assertRaises(SystemExit):
            with _Capture():
                tw.normalize({"exp": "x", "sample_rate": "96k"})

    def test_fills_sane_defaults(self):
        r = tw.normalize({"exp": " 小明 ", "dataset": "D:/data"})
        self.assertEqual(r["exp"], "小明")
        self.assertEqual(r["sample_rate"], "48k")
        self.assertEqual(r["total_epoch"], 200)
        self.assertEqual(r["f0_method"], "rmvpe")
        self.assertGreaterEqual(r["n_cpu"], 1)

    def test_zero_and_negative_counts_are_clamped(self):
        # 0 轮训练、0 batch 都会让下游脚本以除零或空 loader 崩掉。
        r = tw.normalize({"exp": "x", "total_epoch": 0, "batch_size": -3,
                          "save_every": 0, "n_cpu": 0})
        self.assertEqual(r["total_epoch"], 1)
        self.assertEqual(r["batch_size"], 1)
        self.assertEqual(r["save_every"], 1)
        self.assertEqual(r["n_cpu"], 1)

    def test_half_precision_follows_the_device(self):
        self.assertTrue(tw.normalize({"exp": "x", "device": "cuda"})["is_half"])
        self.assertFalse(tw.normalize({"exp": "x", "device": "cpu"})["is_half"])


class TrainLogTailTests(unittest.TestCase):
    """train.py 的 logger 只挂了 FileHandler —— epoch 行不会出现在 stdout 上，
    只能从 train.log 里读。这段解析错了进度条就永远停在 0%。"""

    def _tail_once(self, text: str, total=100):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "train.log"
            p.write_text(text, encoding="utf-8")
            t = tw.TrainLogTail(p, total, 4, 5)
            with _Capture() as cap:
                t._scan()
            return cap.lines()

    def test_reads_the_epoch_out_of_a_real_log_line(self):
        line = ("2026-08-01 10:00:00\tmyvoice\tINFO\t"
                "====> Epoch: 12 [2026-08-01 10:00:00] | (0:01:03)\n")
        out = self._tail_once(line)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["stage"], "train")
        self.assertEqual(out[0]["done"], 12)
        self.assertEqual(out[0]["total"], 100)

    def test_only_reports_forward_progress(self):
        text = "".join(
            "x\t====> Epoch: %d [t] | (0:00:01)\n" % e for e in (1, 2, 2, 1, 3)
        )
        out = self._tail_once(text)
        self.assertEqual([o["done"] for o in out], [1, 2, 3])

    def test_ignores_noise(self):
        text = "loading dataset\n50%|#####| 200/400 [00:10<00:10]\nEpoch: not a number\n"
        self.assertEqual(self._tail_once(text), [])

    def test_epoch_beyond_the_total_is_clamped(self):
        # 续跑时 train.py 从上次的轮数接着数，可能超过这次设的总轮数。
        # 不夹住就会画出 300% 的进度条。
        out = self._tail_once("x\t====> Epoch: 250 [t] | (0:00:01)\n", total=100)
        self.assertEqual(out[0]["done"], 100)

    def test_a_missing_log_is_not_an_error(self):
        # 训练刚起来的头几秒 train.log 还不存在，轮询不该炸。
        t = tw.TrainLogTail(Path("/definitely/not/here.log"), 10, 4, 5)
        with _Capture() as cap:
            t._scan()
        self.assertEqual(cap.lines(), [])


class WatcherJoinTests(unittest.TestCase):
    """进度线程 stop+join 不能把已经跑完的预处理打成崩溃。

    26.8.15/2：`self._stop = Event()` 盖掉 `Thread._stop()`，子进程其实已经
    退出，finally 里 join 却 TypeError: 'Event' object is not callable。
    """

    def test_thread_stop_method_is_still_callable(self):
        with tempfile.TemporaryDirectory() as td:
            w = tw.StageProgress("preprocess", 1, 5, Path(td), 1, "x")
            t = tw.TrainLogTail(Path(td) / "train.log", 10, 4, 5)
        self.assertTrue(callable(w._stop), "StageProgress shadowed Thread._stop")
        self.assertTrue(callable(t._stop), "TrainLogTail shadowed Thread._stop")

    def test_stage_progress_stop_then_join(self):
        with tempfile.TemporaryDirectory() as td:
            w = tw.StageProgress("preprocess", 1, 5, Path(td), 1, "x")
            w.start()
            w.stop()
            w.join(timeout=3)
            self.assertFalse(w.is_alive())

    def test_log_tail_stop_then_join(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "train.log"
            p.write_text("", encoding="utf-8")
            t = tw.TrainLogTail(p, 10, 4, 5)
            t.start()
            t.stop()
            t.join(timeout=3)
            self.assertFalse(t.is_alive())


class CountFilesTests(unittest.TestCase):
    def test_counts_only_files(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "sub").mkdir()
            (d / "a.wav").write_text("x")
            (d / "b.npy").write_text("x")
            self.assertEqual(tw.count_files(d), 2)
            self.assertEqual(tw.count_files(d, ".npy"), 1)

    def test_a_missing_dir_counts_zero(self):
        self.assertEqual(tw.count_files("/definitely/not/here"), 0)


class FilelistTests(unittest.TestCase):
    """filelist 拼错，训练会在最后一步（读数据）才炸，前面几十分钟全白费。"""

    def _fixture(self, td: Path, *, names=("0", "1"), with_mute=True):
        root = td
        exp = root / "logs" / "voice"
        for sub in ("0_gt_wavs", "3_feature768", "2a_f0", "2b-f0nsf"):
            (exp / sub).mkdir(parents=True)
        for n in names:
            (exp / "0_gt_wavs" / f"{n}.wav").write_text("x")
            (exp / "3_feature768" / f"{n}.npy").write_text("x")
            (exp / "2a_f0" / f"{n}.wav.npy").write_text("x")
            (exp / "2b-f0nsf" / f"{n}.wav.npy").write_text("x")
        if with_mute:
            m = root / "logs" / "mute" / "0_gt_wavs"
            m.mkdir(parents=True)
            (m / "mute48k.wav").write_text("x")
        return root, exp

    def test_appends_two_mute_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root, exp = self._fixture(Path(td))
            req = tw.normalize({"exp": "voice", "sample_rate": "48k"})
            with _Capture():
                n = tw.write_filelist(req, exp, root)
            self.assertEqual(n, 4)  # 2 条样本 + 2 条静音
            rows = (exp / "filelist.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 4)
            self.assertEqual(sum(1 for r in rows if "mute48k.wav" in r), 2)
            for r in rows:
                self.assertEqual(len(r.split("|")), 5)

    def test_missing_mute_fixture_fails_loudly(self):
        # logs/mute 不随 GUI 补丁下发，打包漏了就必须在这里就说清楚，
        # 而不是让 train.py 在读第 3 条数据时抛一个看不懂的 FileNotFound。
        with tempfile.TemporaryDirectory() as td:
            root, exp = self._fixture(Path(td), with_mute=False)
            req = tw.normalize({"exp": "voice", "sample_rate": "48k"})
            with self.assertRaises(SystemExit):
                with _Capture():
                    tw.write_filelist(req, exp, root)

    def test_no_overlapping_samples_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root, exp = self._fixture(Path(td), names=())
            req = tw.normalize({"exp": "voice", "sample_rate": "48k"})
            with self.assertRaises(SystemExit):
                with _Capture():
                    tw.write_filelist(req, exp, root)


if __name__ == "__main__":
    unittest.main()
