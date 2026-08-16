# -*- coding: utf-8 -*-
"""DSP 变声预设的单测。

常量与读写部分是纯 stdlib，不需要 numpy —— 冻结的主程序壳要拿它列预设画界面。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.dsp_presets import (  # noqa: E402
    BUILTIN,
    BUILTIN_DIR,
    BUILTIN_IDS,
    delete_user_preset,
    get_preset,
    is_valid_id,
    list_presets,
    save_user_preset,
)
from tools.dsp_voice import EFFECT_SPECS  # noqa: E402

try:
    import numpy as np

    _HAS_NP = True
except ImportError:
    _HAS_NP = False


class BuiltinTests(unittest.TestCase):
    def test_ids_are_unique_and_valid(self):
        ids = [p["id"] for p in BUILTIN]
        self.assertEqual(len(ids), len(set(ids)), "内置预设 id 有重复")
        for pid in ids:
            self.assertTrue(is_valid_id(pid), pid)

    def test_every_builtin_has_name_desc_and_params(self):
        for p in BUILTIN:
            self.assertTrue(p.get("name"), p["id"])
            self.assertTrue(p.get("desc"), p["id"])
            self.assertTrue(p.get("params"), f"{p['id']} 没有参数，等于什么都不做")

    def test_params_only_reference_real_effects(self):
        for p in BUILTIN:
            for effect, values in p["params"].items():
                self.assertIn(effect, EFFECT_SPECS, f"{p['id']} 用了不存在的 {effect}")
                for key in values:
                    self.assertIn(
                        key, EFFECT_SPECS[effect]["params"],
                        f"{p['id']}.{effect} 用了不存在的参数 {key}",
                    )

    def test_params_are_within_range(self):
        """越界的内置预设会被静默钳回去，那就跟作者写的不是一回事了。"""
        for p in BUILTIN:
            for effect, values in p["params"].items():
                ranges = EFFECT_SPECS[effect]["ranges"]
                for key, v in values.items():
                    lo, hi = ranges[key]
                    self.assertGreaterEqual(float(v), lo, f"{p['id']}.{effect}.{key}")
                    self.assertLessEqual(float(v), hi, f"{p['id']}.{effect}.{key}")

    def test_json_files_shipped_and_match(self):
        """configs/dsp_presets 里的文件要跟代码里的清单对得上。

        壳（Rust）读的是文件，引擎读的是这份清单；两边走散的话，界面上列出来
        的预设和实际生效的参数就不是一回事。
        """
        self.assertTrue(BUILTIN_DIR.is_dir(), f"缺目录 {BUILTIN_DIR}")
        on_disk = {f.stem for f in BUILTIN_DIR.glob("*.json")}
        self.assertEqual(on_disk, set(BUILTIN_IDS), "文件与清单对不上")
        for p in BUILTIN:
            body = json.loads((BUILTIN_DIR / f"{p['id']}.json").read_text("utf-8"))
            self.assertEqual(body["name"], p["name"], p["id"])
            self.assertEqual(body["params"], p["params"], p["id"])

    def test_gender_presets_compensate_formants(self):
        """变调会带走共振峰。男女互换必须反向配平，否则就是花栗鼠/巨人。"""
        m2f = next(p for p in BUILTIN if p["id"] == "male_to_female")
        self.assertGreater(m2f["params"]["pitch"]["semitones"], 0)
        self.assertLess(m2f["params"]["formant"]["shift"], 0)
        f2m = next(p for p in BUILTIN if p["id"] == "female_to_male")
        self.assertLess(f2m["params"]["pitch"]["semitones"], 0)
        self.assertGreater(f2m["params"]["formant"]["shift"], 0)

    def test_robot_and_alien_stay_intelligible(self):
        robot = next(p for p in BUILTIN if p["id"] == "robot")
        self.assertLessEqual(robot["params"]["ring"]["mix"], 0.4)
        alien = next(p for p in BUILTIN if p["id"] == "alien")
        self.assertLessEqual(alien["params"]["ring"]["mix"], 0.3)

    def test_chipmunk_and_child_do_not_stack_formant(self):
        for pid in ("chipmunk", "child", "giant"):
            p = next(x for x in BUILTIN if x["id"] == pid)
            self.assertNotIn("formant", p["params"], pid)

    def test_no_preset_is_a_no_op(self):
        for p in BUILTIN:
            changed = {
                e: v
                for e, v in p["params"].items()
                if v != EFFECT_SPECS[e]["params"]
            }
            self.assertTrue(changed, f"{p['id']} 的参数全是默认值，听起来没变化")


class EffectSpecFileTests(unittest.TestCase):
    """configs/dsp_effects.json 必须跟引擎侧 EFFECT_SPECS 一致。

    壳画滑条要范围，但**不能自己抄一份** —— 抄了就一定会走散：界面上能拉到的
    值引擎那边会被静默钳回去，用户看到的和听到的对不上，而且从哪一侧都查不出
    原因。所以生成一份给壳读，并用这条测试盯着它别过期。
    """

    PATH = ROOT / "configs" / "dsp_effects.json"

    def test_file_exists(self):
        self.assertTrue(self.PATH.is_file(), f"缺 {self.PATH}")

    def test_matches_engine_specs(self):
        from tools.dsp_voice import CHAIN_ORDER

        data = json.loads(self.PATH.read_text(encoding="utf-8"))
        self.assertEqual(data["order"], list(CHAIN_ORDER), "效果器顺序对不上")
        self.assertEqual(set(data["effects"]), set(EFFECT_SPECS), "效果器清单对不上")
        for name, spec in EFFECT_SPECS.items():
            got = data["effects"][name]
            self.assertEqual(got["params"], spec["params"], f"{name} 默认值对不上")
            for key, rng in spec["ranges"].items():
                self.assertEqual(
                    tuple(got["ranges"][key]), tuple(rng), f"{name}.{key} 范围对不上"
                )

    def test_every_param_has_a_ui_label(self):
        """壳给每个参数画一行，没标签的会露出 raw key。"""
        src = (ROOT / "app" / "src" / "components" / "DspPresetEditor.tsx").read_text(
            encoding="utf-8"
        )
        for name, spec in EFFECT_SPECS.items():
            for key in spec["params"]:
                self.assertIn(f"{key}:", src, f"编辑器没有 {name}.{key} 的标签")


class IdValidationTests(unittest.TestCase):
    def test_accepts_plain_ids(self):
        for good in ("robot", "male_to_female", "a1_2", "x"):
            self.assertTrue(is_valid_id(good), good)

    def test_rejects_traversal_and_odd_names(self):
        """id 同时是文件名，穿越必须挡住。"""
        for bad in ("", "Robot", "my preset", "../../config", "a/b", "a\\b",
                    "x" * 49, "中文", "a.b"):
            self.assertFalse(is_valid_id(bad), bad)


class UserPresetTests(unittest.TestCase):
    def test_save_list_get_delete(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            save_user_preset("mine", "我的", {"pitch": {"semitones": 5.0}}, root)
            got = get_preset("mine", root)
            self.assertIsNotNone(got)
            self.assertEqual(got["name"], "我的")
            self.assertEqual(got["source"], "user")
            self.assertEqual(got["params"]["pitch"]["semitones"], 5.0)
            self.assertTrue(delete_user_preset("mine", root))
            self.assertIsNone(get_preset("mine", root))

    def test_delete_missing_is_false_not_raise(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(delete_user_preset("nope", Path(td)))

    def test_save_rejects_bad_id(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                save_user_preset("../evil", "x", {"pitch": {"semitones": 1}}, Path(td))

    def test_out_of_range_params_are_clamped_on_save(self):
        """预设可以手写、可以从广场下载，不能信。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            save_user_preset("wild", "野的", {"pitch": {"semitones": 999}}, root)
            got = get_preset("wild", root)
            self.assertEqual(got["params"]["pitch"]["semitones"], 24.0)

    def test_unknown_effects_are_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            save_user_preset(
                "odd", "怪的", {"pitch": {"semitones": 2}, "nope": {"x": 1}}, root
            )
            got = get_preset("odd", root)
            self.assertIn("pitch", got["params"])
            self.assertNotIn("nope", got["params"])

    def test_user_overrides_builtin_of_the_same_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            save_user_preset("robot", "我的机器人", {"pitch": {"semitones": 3}}, root)
            got = get_preset("robot", root)
            self.assertEqual(got["name"], "我的机器人")
            self.assertEqual(got["source"], "user")

    def test_broken_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            d = root / "User_Data" / "dsp_presets"
            d.mkdir(parents=True)
            (d / "ok.json").write_text('{"params":{"pitch":{"semitones":1}}}', "utf-8")
            (d / "broken.json").write_text("{ not json", "utf-8")
            (d / "noparams.json").write_text('{"name":"x"}', "utf-8")
            ids = {p["id"] for p in list_presets(root) if p["source"] == "user"}
            self.assertEqual(ids, {"ok"})


@unittest.skipUnless(_HAS_NP, "需要 numpy")
class PresetsActuallySoundDifferentTests(unittest.TestCase):
    """每个内置预设都得真的改变声音，而且不能爆音、不能出 NaN。"""

    SR = 48000
    BLOCK = 1024

    def test_all_builtin_presets_run_clean(self):
        from tools.dsp_voice import VoiceChain

        n = self.BLOCK * 8
        t = np.arange(n) / self.SR
        rng = np.random.default_rng(4)
        x = (0.3 * np.sin(2 * np.pi * 180 * t) + 0.05 * rng.standard_normal(n)).astype(
            np.float32
        )
        dry = np.tanh(x.astype(np.float64))
        for p in BUILTIN:
            c = VoiceChain(p["params"])
            y = np.concatenate(
                [c.process(x[i : i + self.BLOCK], self.SR)
                 for i in range(0, n, self.BLOCK)]
            )
            self.assertEqual(y.shape, x.shape, p["id"])
            self.assertTrue(np.isfinite(y).all(), f"{p['id']} 出了 NaN/Inf")
            self.assertLessEqual(float(np.abs(y).max()), 1.0 + 1e-5, f"{p['id']} 爆音")
            self.assertGreater(
                float(np.abs(y - dry).max()), 1e-4, f"{p['id']} 听起来跟没开一样"
            )


if __name__ == "__main__":
    unittest.main()
