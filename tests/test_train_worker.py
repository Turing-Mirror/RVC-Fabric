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
        self.assertFalse(r["save_every_weights"])
        self.assertGreaterEqual(r["n_cpu"], 1)

    def test_rejects_unknown_f0_method(self):
        with self.assertRaises(SystemExit):
            with _Capture():
                tw.normalize({"exp": "x", "f0_method": "crepe"})

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


class TrainExitCodeTests(unittest.TestCase):
    def test_train_py_done_is_success(self):
        # train.py 正常结束是 os._exit(2333333)。当 0 以外全失败，
        # 权重其实已经写好，整次训练却报失败，索引也建不成。
        self.assertEqual(tw.TRAIN_PY_DONE, 2333333)
        self.assertIn(tw.TRAIN_PY_DONE, (0, tw.TRAIN_PY_DONE))


class MetaSrTests(unittest.TestCase):
    def test_meta_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            exp = Path(td)
            tw.write_meta(exp, {"sample_rate": "40k", "exp": "v"})
            self.assertEqual(tw.infer_sr(exp), "40k")

    def test_infer_sr_from_config_json(self):
        with tempfile.TemporaryDirectory() as td:
            exp = Path(td)
            (exp / "config.json").write_text(
                json.dumps({"data": {"sampling_rate": 32000}}), encoding="utf-8"
            )
            self.assertEqual(tw.infer_sr(exp), "32k")

    def test_infer_sr_from_gt_wav(self):
        with tempfile.TemporaryDirectory() as td:
            exp = Path(td)
            gt = exp / "0_gt_wavs"
            gt.mkdir()
            import wave as _wave
            with _wave.open(str(gt / "0_0.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(48000)
                w.writeframes(b"\x00\x00" * 16)
            self.assertEqual(tw.infer_sr(exp), "48k")

    def test_wipe_removes_stage_dirs_and_meta(self):
        with tempfile.TemporaryDirectory() as td:
            exp = Path(td)
            (exp / "1_16k_wavs").mkdir()
            (exp / "1_16k_wavs" / "a.wav").write_text("x")
            (exp / "filelist.txt").write_text("x")
            tw.write_meta(exp, {"sample_rate": "48k", "exp": "v"})
            tw.wipe_stage_dirs(exp)
            self.assertFalse((exp / "1_16k_wavs").exists())
            self.assertFalse((exp / "filelist.txt").exists())
            self.assertFalse((exp / "tm_meta.json").exists())


class PublishVoiceTests(unittest.TestCase):
    def test_copies_pth_and_index_into_user_models(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            weights = root / "assets" / "weights" / "v.pth"
            weights.parent.mkdir(parents=True)
            weights.write_bytes(b"pth")
            idx = root / "logs" / "v" / "added.index"
            idx.parent.mkdir(parents=True)
            idx.write_bytes(b"idx")
            dest = tw.publish_voice(
                root, {"exp": "v", "sample_rate": "48k"}, weights, idx
            )
            self.assertIsNotNone(dest)
            self.assertTrue((root / "User_Data" / "models" / "v" / "v.pth").is_file())
            self.assertTrue((root / "User_Data" / "models" / "v" / "added.index").is_file())
            side = json.loads(
                (root / "User_Data" / "models" / "v" / "config.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(side["source"], "trained")
            self.assertEqual(side["sample_rate"], "48k")


class RmvpeGateTests(unittest.TestCase):
    def test_rmvpe_ok_rejects_missing_and_tiny(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertFalse(tw.rmvpe_ok(root))
            d = root / "assets" / "rmvpe"
            d.mkdir(parents=True)
            (d / "rmvpe.pt").write_bytes(b"half")
            self.assertFalse(tw.rmvpe_ok(root))
            (d / "rmvpe.pt").write_bytes(b"x" * 1_000_001)
            self.assertTrue(tw.rmvpe_ok(root))


class ExtractF0PrintImportTests(unittest.TestCase):
    """harvest/pm 走 extract_f0_print，Windows spawn 会重新 import 这个文件。"""

    def test_argv_is_not_read_at_import(self):
        src = (
            ROOT / "infer" / "modules" / "train" / "extract" / "extract_f0_print.py"
        ).read_text(encoding="utf-8")
        head, sep, _tail = src.partition('if __name__ == "__main__"')
        self.assertTrue(sep, "extract_f0_print.py must keep a __main__ guard")
        # main() 里读 argv 没问题；模块顶层一读，spawn 子进程就会死。
        for line in head.splitlines():
            if not line or line[0] in " \t#" or line.startswith(("def ", "class ")):
                continue
            self.assertNotIn(
                "sys.argv[",
                line,
                "module-level argv will crash Windows spawn children: %s" % line,
            )


class CountAudioTests(unittest.TestCase):
    def test_counts_nested_audio_only(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "sub").mkdir()
            (d / "sub" / "a.wav").write_text("x")
            (d / "sub" / "note.txt").write_text("x")
            (d / "cover.jpg").write_text("x")
            self.assertEqual(tw.count_audio(d), 1)


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


class ArtifactSnapshotTests(unittest.TestCase):
    """取消/失败时必须能从快照判断：有没有可用音色、卡在哪一步。"""

    def _exp(self, td: Path, *, slices=0, f0=0, feat=0, epoch=None, final=False, ckpt=None):
        root = td
        exp = root / "logs" / "voice"
        exp.mkdir(parents=True)
        for name, n in (("1_16k_wavs", slices), ("2a_f0", f0), ("3_feature768", feat)):
            d = exp / name
            d.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                (d / ("%s.bin" % i)).write_text("x")
        if epoch is not None:
            (exp / "train.log").write_text(
                "====> Epoch: %d [t] | (0:00:01)\n" % epoch, encoding="utf-8"
            )
        if final:
            w = root / "assets" / "weights"
            w.mkdir(parents=True)
            (w / "voice.pth").write_bytes(b"pth")
        if ckpt:
            (exp / ckpt).write_bytes(b"g")
        return root, exp

    def test_nothing_on_disk_is_unusable(self):
        with tempfile.TemporaryDirectory() as td:
            root, exp = self._exp(Path(td))
            snap = tw.artifact_snapshot(exp, root, {"exp": "voice"})
            self.assertEqual(snap["usable"], "none")
            self.assertEqual(snap["counts"]["1_16k_wavs"], 0)
            self.assertIsNone(snap["latest_epoch"])

    def test_slices_without_weights_are_not_a_voice(self):
        with tempfile.TemporaryDirectory() as td:
            root, exp = self._exp(Path(td), slices=12)
            snap = tw.artifact_snapshot(exp, root, {"exp": "voice"})
            self.assertEqual(snap["usable"], "slices_only")
            self.assertEqual(snap["counts"]["1_16k_wavs"], 12)

    def test_an_intermediate_ckpt_counts(self):
        with tempfile.TemporaryDirectory() as td:
            root, exp = self._exp(Path(td), slices=12, epoch=2, ckpt="G_2.pth")
            snap = tw.artifact_snapshot(exp, root, {"exp": "voice"})
            self.assertEqual(snap["usable"], "intermediate")
            self.assertEqual(snap["latest_epoch"], 2)
            self.assertEqual([x["name"] for x in snap["exp_pths"]], ["G_2.pth"])

    def test_final_weights_win(self):
        with tempfile.TemporaryDirectory() as td:
            root, exp = self._exp(Path(td), slices=12, epoch=3, final=True, ckpt="G_3.pth")
            snap = tw.artifact_snapshot(exp, root, {"exp": "voice"})
            self.assertEqual(snap["usable"], "final")
            self.assertGreater(snap["final_weights_bytes"], 0)

    def test_latest_epoch_skips_garbage(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "train.log"
            p.write_text(
                "====> Epoch: not\n====> Epoch: 4 [t]\nnoise\n====> Epoch: 7 [t]\n",
                encoding="utf-8",
            )
            self.assertEqual(tw.latest_epoch_in_log(p), 7)

    def test_dump_log_tail_mentions_a_missing_file(self):
        buf = io.StringIO()
        real = sys.stderr
        sys.stderr = buf
        try:
            tw.dump_log_tail(Path("/definitely/not/here.log"), n=10)
        finally:
            sys.stderr = real
        self.assertIn("missing", buf.getvalue())


class ResumeCompletenessTests(unittest.TestCase):
    """半份产物不能算做完。

    26.8.20 用户诊断包：上一次在音高阶段被取消，2a_f0 里留下 616 份，切片有
    3884 份。续跑时旧判据是「目录非空就跳过」，于是音高整步跳过，filelist 取
    四类产物的交集只剩 618 行 —— 用户以为在拿 3884 条数据训练，实际只用了 16%，
    界面上没有任何提示。
    """

    def test_a_half_finished_stage_is_not_done(self):
        self.assertFalse(tw.stage_complete(616, 3884))

    def test_a_finished_stage_is_done(self):
        self.assertTrue(tw.stage_complete(3884, 3884))

    def test_more_outputs_than_slices_still_counts(self):
        # mute 之类的额外产物不该把「做完了」判成「没做完」。
        self.assertTrue(tw.stage_complete(3886, 3884))

    def test_nothing_at_all_is_not_done(self):
        self.assertFalse(tw.stage_complete(0, 3884))
        self.assertFalse(tw.stage_complete(0, 0))


class PreprocessSuccessCountTests(unittest.TestCase):
    """2038 个音频只切出 3 条，界面上却一个字都没有——那次是 ffmpeg 读不了文件。"""

    def _log(self, td, text):
        p = Path(td) / "preprocess.log"
        p.write_text(text, encoding="utf-8")
        return p

    def test_counts_only_success_lines(self):
        with tempfile.TemporaryDirectory() as td:
            log = self._log(td, "\n".join([
                "start preprocess",
                "D:\\a\\1.wav\t-> Success",
                "D:\\a\\2.wav\t-> Traceback (most recent call last):",
                "  File \"audio.py\", line 44, in load_audio",
                "ffmpeg._run.Error: ffmpeg error",
                "D:\\a\\3.wav\t-> Success",
                "end preprocess",
            ]))
            self.assertEqual(tw.count_preprocess_ok(log), 2)

    def test_missing_log_is_zero(self):
        self.assertEqual(tw.count_preprocess_ok(Path("/definitely/not/here.log")), 0)


class TrainOomDetectionTests(unittest.TestCase):
    """「训练结束但没找到 xxx.pth」对用户毫无指向，显存不足要直说。"""

    # 用户日志里的原文。
    OOM = (
        "torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 20.00 MiB "
        "(GPU 0; 8.00 GiB total capacity; 2.00 GiB already allocated; 4.84 GiB free; "
        "2.04 GiB reserved in total by PyTorch)"
    )

    def _log(self, td, text):
        p = Path(td) / "train.log"
        p.write_text(text, encoding="utf-8")
        return p

    def test_recognizes_the_real_message(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertTrue(tw.log_has_oom(self._log(td, "INFO:voice:start\n" + self.OOM)))

    def test_a_healthy_log_is_not_oom(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(
                tw.log_has_oom(self._log(td, "====> Epoch: 12 [t] | (0:00:01)\n"))
            )

    def test_only_the_tail_counts(self):
        # 上一轮的显存不足不该栽给这一轮：只看最后 8000 字。
        with tempfile.TemporaryDirectory() as td:
            text = self.OOM + "\n" + ("====> Epoch: 1 [t]\n" * 900)
            self.assertFalse(tw.log_has_oom(self._log(td, text)))

    def test_missing_log_is_not_oom(self):
        self.assertFalse(tw.log_has_oom(Path("/definitely/not/here.log")))


class SnapshotPublishedPathTests(unittest.TestCase):
    """用户设了输出目录时，音色不在 User_Data 下，诊断包不能永远报 0 字节。"""

    def _tree(self, td):
        root = Path(td) / "root"
        (root / "logs" / "voice").mkdir(parents=True)
        return root, root / "logs" / "voice"

    def test_custom_output_dir_is_where_we_look(self):
        with tempfile.TemporaryDirectory() as td:
            root, exp = self._tree(td)
            out = Path(td) / "E" / "voices"
            (out / "voice").mkdir(parents=True)
            (out / "voice" / "voice.pth").write_bytes(b"published")
            snap = tw.artifact_snapshot(
                exp, root, {"exp": "voice", "output_dir": str(out)}
            )
            self.assertEqual(snap["published_bytes"], len(b"published"))
            self.assertEqual(snap["usable"], "final")

    def test_default_location_still_works(self):
        with tempfile.TemporaryDirectory() as td:
            root, exp = self._tree(td)
            d = root / "User_Data" / "models" / "voice"
            d.mkdir(parents=True)
            (d / "voice.pth").write_bytes(b"published")
            snap = tw.artifact_snapshot(exp, root, {"exp": "voice", "output_dir": ""})
            self.assertEqual(snap["published_bytes"], len(b"published"))


class TrainPartialWarningUiTests(unittest.TestCase):
    """半份产物的 skip 下一拍就是 stage，必须写到 msg 上才看得到。"""

    def test_panel_keeps_skip_text_on_msg(self):
        src = (ROOT / "app" / "src" / "components" / "TrainPanel.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn('phase === "skip"', src)
        self.assertIn("setMsg", src)


if __name__ == "__main__":
    unittest.main()
