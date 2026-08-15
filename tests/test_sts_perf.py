# -*- coding: utf-8 -*-
"""离线转换分段计时的单测。纯 stdlib。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.sts_perf import STAGES, StsTimer, load_latest  # noqa: E402


class TimerTests(unittest.TestCase):
    def test_stages_accumulate(self):
        t = StsTimer()
        with t.stage("model"):
            pass
        with t.stage("model"):
            pass
        with t.stage("convert"):
            pass
        s = t.summary()
        self.assertIn("model", s["stages_s"])
        self.assertIn("convert", s["stages_s"])

    def test_stage_records_even_when_body_raises(self):
        """加载阶段炸了，那一段的耗时照样要留下 —— 那正是要排查的场景。"""
        t = StsTimer()
        with self.assertRaises(ValueError):
            with t.stage("model"):
                raise ValueError("boom")
        self.assertIn("model", t.summary()["stages_s"])

    def test_add_is_equivalent(self):
        t = StsTimer()
        t.add("import", 1.5)
        t.add("import", 0.5)
        self.assertEqual(t.summary()["stages_s"]["import"], 2.0)

    def test_hot_flag_and_load_share(self):
        cold = StsTimer(hot=False)
        cold.add("import", 8.0)
        cold.add("model", 2.0)
        cold.add("convert", 1.0)
        s = cold.summary()
        self.assertFalse(s["hot"])
        # 加载占了 10/11，这正是「一条 5 秒语音要一分钟」的形状
        self.assertGreater(s["load_share"], 0.5)

        hot = StsTimer(hot=True)
        hot.add("convert", 1.0)
        self.assertTrue(hot.summary()["hot"])

    def test_other_s_catches_unmeasured_time(self):
        """没被任何 stage 圈住的时间要单独记，不然会以为已经量全了。"""
        t = StsTimer()
        t.add("convert", 0.0)
        self.assertIn("other_s", t.summary())
        self.assertGreaterEqual(t.summary()["other_s"], 0.0)

    def test_known_stage_names(self):
        for name in ("import", "config", "model", "hubert", "rmvpe", "convert", "write"):
            self.assertIn(name, STAGES)


class SaveTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            t = StsTimer(hot=True)
            t.add("convert", 2.0)
            path = t.save(td, extra={"total": 3, "ok": 3})
            self.assertTrue(path)
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertTrue(data["hot"])
            self.assertEqual(data["total"], 3)
            self.assertEqual(load_latest(td)["ok"], 3)

    def test_save_never_raises_on_bad_dir(self):
        """计时失败不该让转换失败。"""
        t = StsTimer()
        self.assertEqual(t.save("\x00not/a/dir"), "")

    def test_load_latest_missing_dir(self):
        self.assertIsNone(load_latest("/no/such/dir/for/sts/perf"))

    def test_prune_keeps_recent_only(self):
        with tempfile.TemporaryDirectory() as td:
            for i in range(40):
                p = Path(td) / f"sts_2026010{i % 10}_{i:06d}.json"
                p.write_text("{}", encoding="utf-8")
            StsTimer().save(td)
            left = list(Path(td).glob("sts_*.json"))
            self.assertLessEqual(len(left), 31)

    def test_extra_cannot_clobber_core_fields(self):
        t = StsTimer(hot=True)
        s = t.summary({"hot": False, "total_s": -1, "files": 2})
        self.assertTrue(s["hot"], "extra 不该盖掉核心字段")
        self.assertNotEqual(s["total_s"], -1)
        self.assertEqual(s["files"], 2)


class WiringTests(unittest.TestCase):
    """两条路都要计时，不然只有一半的数字，没法对比。"""

    def test_cold_path_times_the_load_stages(self):
        src = (ROOT / "tools" / "sts_worker.py").read_text(encoding="utf-8")
        for name in ("import", "config", "model", "hubert", "convert"):
            self.assertIn(f'_stage(timer, "{name}")', src, f"冷路径没量 {name}")

    def test_hot_path_times_too(self):
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        self.assertIn('_sts_stage(timer, "model")', src)
        self.assertIn('_sts_stage(timer, "convert")', src)
        self.assertIn("StsTimer(hot=True)", src)

    def test_reports_land_where_diagnostics_collects_them(self):
        """报告要落在诊断包会收的目录里，不然用户发不过来。"""
        diag = (ROOT / "tools" / "collect_diagnostics.py").read_text(encoding="utf-8")
        self.assertIn("User_Data/perf_reports", diag)
        for f in ("tools/sts_worker.py", "gui_v1.py"):
            src = (ROOT / f).read_text(encoding="utf-8")
            self.assertIn("perf_reports", src, f"{f} 没往 perf_reports 落")


if __name__ == "__main__":
    unittest.main()
