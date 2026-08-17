# -*- coding: utf-8 -*-
"""无模型 DSP 变声的单测（不需要声卡、不需要 torch）。

常量部分必须在没有 numpy 的环境下也能 import —— 冻结的主程序壳要拿它画界面，
但壳里没有 numpy。
"""

from __future__ import annotations

import math
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.dsp_voice import (  # noqa: E402
    CHAIN_ORDER,
    EFFECT_SPECS,
    clamp_params,
    default_chain,
    semitones_to_ratio,
)

try:
    import numpy as np

    _HAS_NP = True
except ImportError:
    _HAS_NP = False

SR = 48000
BLOCK = 1024

# 每个效果器一组「确实在干活」的参数，给通用测试轮着用。
ACTIVE = {
    "pitch": {"semitones": 7.0},
    "formant": {"shift": -4.0},
    "whisper": {"amount": 0.7},
    "robot": {"amount": 0.5, "freq": 80.0},
    "ring": {"freq": 80.0, "mix": 0.8},
    "tremolo": {"rate": 6.0, "depth": 0.6},
    "vibrato": {"rate": 6.0, "depth": 25.0},
    "chorus": {"depth": 0.7},
    "bitcrush": {"bits": 5, "downsample": 6},
    "drive": {"amount": 0.6},
    "radio": {"mix": 0.9, "noise": 0.1},
    "echo": {"mix": 0.5},
    "reverb": {"mix": 0.5, "size": 0.7},
}


class ConstantsWithoutNumpyTests(unittest.TestCase):
    def test_chain_order_covers_every_effect(self):
        self.assertEqual(set(CHAIN_ORDER), set(EFFECT_SPECS))
        self.assertEqual(len(CHAIN_ORDER), len(EFFECT_SPECS))

    def test_every_spec_has_label_and_ranges(self):
        for name, spec in EFFECT_SPECS.items():
            self.assertTrue(spec.get("label"), name)
            self.assertTrue(spec.get("params"), name)
            for key in spec["params"]:
                self.assertIn(key, spec.get("ranges", {}), f"{name}.{key} 缺范围")

    def test_default_chain_equals_spec_defaults(self):
        d = default_chain()
        for name, spec in EFFECT_SPECS.items():
            self.assertEqual(d[name], spec["params"])

    def test_semitones_to_ratio(self):
        self.assertAlmostEqual(semitones_to_ratio(0), 1.0)
        self.assertAlmostEqual(semitones_to_ratio(12), 2.0)
        self.assertAlmostEqual(semitones_to_ratio(-12), 0.5)

    def test_clamp_rejects_out_of_range(self):
        got = clamp_params("pitch", {"semitones": 999})
        self.assertEqual(got["semitones"], 24.0)
        got = clamp_params("pitch", {"semitones": -999})
        self.assertEqual(got["semitones"], -24.0)

    def test_clamp_rejects_garbage(self):
        """预设可以手写、可以从广场下载，不能信。"""
        for bad in ({"semitones": "abc"}, {"semitones": None}, {"semitones": float("nan")},
                    {"semitones": float("inf")}):
            got = clamp_params("pitch", bad)
            self.assertEqual(got["semitones"], 0.0, bad)

    def test_clamp_keeps_int_params_int(self):
        got = clamp_params("bitcrush", {"bits": 5.7, "downsample": 3.2})
        self.assertIsInstance(got["bits"], int)
        self.assertIsInstance(got["downsample"], int)
        self.assertEqual(got["bits"], 6)

    def test_clamp_fills_missing_with_defaults(self):
        got = clamp_params("radio", {"mix": 0.5})
        self.assertEqual(got["mix"], 0.5)
        self.assertEqual(got["low"], EFFECT_SPECS["radio"]["params"]["low"])

    def test_clamp_unknown_effect_is_empty(self):
        self.assertEqual(clamp_params("nope", {"x": 1}), {})


class ShellContractTests(unittest.TestCase):
    """壳层、引擎、模板三边必须认得同一批 dsp 键。

    fx 那条链就是这么掉过一次的：引擎一直支持，壳的 HOT_KEYS 里一个都没有，
    于是设置写进去了、永远推不到 worker。静态看两边都「正常」，只有对着列表
    比才看得出来。
    """

    KEYS = ("dsp_enabled", "dsp_preset", "dsp_params")

    def _rust_hot_keys(self):
        src = (ROOT / "app" / "src-tauri" / "src" / "config.rs").read_text(
            encoding="utf-8"
        )
        head = "pub const HOT_KEYS: &[&str] = &["
        start = src.index(head) + len(head)
        body = src[start : src.index("];", start)]
        return {p.split('"')[1] for p in body.splitlines() if p.count('"') >= 2}

    def test_dsp_keys_are_shell_hot_keys(self):
        """必须是热键：换预设不该重开流，DSP 模式的卖点就是即时。"""
        rust = self._rust_hot_keys()
        missing = [k for k in self.KEYS if k not in rust]
        self.assertEqual(missing, [], f"壳层 HOT_KEYS 缺：{missing}")

    def test_dsp_keys_are_not_cold_keys(self):
        src = (ROOT / "app" / "src-tauri" / "src" / "config.rs").read_text(
            encoding="utf-8"
        )
        head = "pub const COLD_KEYS: &[&str] = &["
        start = src.index(head) + len(head)
        body = src[start : src.index("];", start)]
        cold = {p.split('"')[1] for p in body.splitlines() if p.count('"') >= 2}
        clash = [k for k in self.KEYS if k in cold]
        self.assertEqual(clash, [], f"这些键同时被列成冷键：{clash}")

    def test_engine_set_hot_actually_accepts_them(self):
        """光进 HOT_KEYS 不够 —— 命令签名里没有的参数 Tauri 会直接丢掉。

        踩过：三个键都在 HOT_KEYS 里、config.rs 有默认值、引擎侧也读了，
        但 engine_set_hot 的参数列表里没有，于是模型页点预设一点反应都没有。
        静态看每一处都「对」，只有把签名也对进来才看得出。
        """
        src = (ROOT / "app" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
        head = "fn engine_set_hot("
        body = src[src.index(head) : src.index(") -> Result<u64, String> {", src.index(head))]
        for key in self.KEYS:
            self.assertIn(f"{key}:", body, f"engine_set_hot 签名里没有 {key}")
            self.assertIn(f'"{key}".into()', src, f"engine_set_hot 没把 {key} 放进 payload")

    def test_fx_function_is_not_folded_into_vc(self):
        """function 传 "fx" 不能被折成 "vc"，那等于 DSP 模式永远起不来。"""
        src = (ROOT / "app" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
        self.assertIn('"fx" => "fx"', src)

    def test_rust_defaults_exist(self):
        src = (ROOT / "app" / "src-tauri" / "src" / "config.rs").read_text(
            encoding="utf-8"
        )
        for key in self.KEYS:
            self.assertIn(f'"{key}".into()', src, f"config.rs defaults() 里没有 {key}")

    def test_inuse_template_has_them(self):
        from scripts.inuse_template import CLEAN_INUSE as DEFAULTS

        for key in self.KEYS:
            self.assertIn(key, DEFAULTS, f"inuse 模板缺 {key}")
        self.assertFalse(DEFAULTS["dsp_enabled"], "DSP 默认必须是关的")

    def test_engine_reads_them(self):
        """gui_v1 得真的从配置里读这三个键，光有默认值不算通。"""
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        for key in self.KEYS:
            self.assertIn(f'data.get("{key}")', src, f"gui_v1 没从配置读 {key}")

    def test_engine_allows_start_without_a_model(self):
        """开了 DSP 就该能不选音色直接开声 —— 这是整个模式的前提。"""
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        self.assertIn("dsp_only", src)
        self.assertIn('self.function = "fx"', src)

    def test_apply_hot_keeps_fx_when_rvc_is_missing(self):
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        self.assertIn('payload["function"] in ("vc", "im", "fx")', src)
        self.assertIn('nxt == "vc"', src)
        self.assertIn('nxt = "fx"', src)
        # 二选一：有 RVC 也不能把 fx 折回 vc，否则停完 DSP 又跳回 RVC。
        self.assertNotIn('nxt == "fx" and rvc is not None', src)

    def test_attaching_a_model_leaves_pure_dsp_mode(self):
        """选音色就是切到 RVC：关掉 DSP，function 走 vc。"""
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        body = src[src.index("def _attach_rvc") : src.index("def _apply_pending_model")]
        self.assertIn("self.dsp_only = False", body)
        self.assertIn("dsp_enabled = False", body)
        self.assertIn('self.function = "vc"', body)

    def test_dropping_the_voice_reaches_a_running_engine(self):
        """丢掉音色是热操作，不能只写配置。

        只清 app_config / inuse 的话，转着的 worker 手里还攥着 RVC 实例，
        界面上音色没了、耳朵里还是那个音色。
        """
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        self.assertIn('payload.get("drop_model")', src)
        body = src[src.index("def _worker_drop_model") : src.index("def _ckpt_tgt_sr")]
        self.assertIn("self.rvc = None", body)
        self.assertIn("self._pending_model = None", body)  # 排队中的换模型也要取消
        self.assertIn("self.dsp_only = True", body)

        worker = (ROOT / "app" / "src-tauri" / "src" / "worker.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("pub fn drop_model", worker)
        voices = (ROOT / "app" / "src-tauri" / "src" / "voices.rs").read_text(
            encoding="utf-8"
        )
        clear = voices[voices.index("pub fn clear_voice") :][:600]
        self.assertIn("worker::drop_model", clear)

    def test_selecting_a_voice_clears_dsp_params(self):
        voices = (ROOT / "app" / "src-tauri" / "src" / "voices.rs").read_text(
            encoding="utf-8"
        )
        body = voices[voices.index("pub fn select_voice") : voices.index(
            "pub fn clear_voice"
        )]
        self.assertIn('"dsp_params"', body)
        self.assertIn("dsp_enabled", body)
        self.assertIn('json!("vc")', body)

    def test_leftover_dsp_params_do_not_force_dsp_start(self):
        """残留的预设/参数不能把「换回 RVC」按成 DSP。

        以前这条还断言 `start_vc` 里有 `elif pth:` —— 那是在锁一份**重复的
        判定**。判定在链路上被算了六遍、四套规则，就是「DSP 之后换不回 RVC」
        的根子。现在判定只有 `_resolve_dsp` 一家，`start_vc` 读它定下来的
        `_dsp_resolved`，所以这里改成断言那个唯一性。
        """
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        resolve = src[src.index("def _resolve_dsp") : src.index("def set_values")]
        self.assertIn("if enabled:", resolve)
        self.assertIn("elif pth", resolve)
        # set_values 必须把结论记下来，供其余地方读。
        self.assertIn("self._dsp_resolved = bool(dsp_on)", src)
        start = src[src.index("def start_vc") : src.index("def ", src.index("def start_vc") + 1)]
        self.assertIn("_dsp_resolved", start)
        # 别再从常驻内存状态自己推判定：gui_config.dsp_enabled 和 self.function
        # 跑过一次纯 DSP 之后就一直是 True / "fx"。
        #
        # 只禁「拿它们当判据」这一件事。函数后半段那句
        # `if self.function == "fx": self.function = "vc"` 是 RVC 路径把残留的
        # fx 归一回来，是对的，不能一并禁掉。
        self.assertNotIn('enabled = bool(getattr(self.gui_config, "dsp_enabled"', start)
        self.assertNotIn('str(getattr(self, "function", "") or "") == "fx"', start)
        rust = (ROOT / "app" / "src-tauri" / "src" / "config.rs").read_text(
            encoding="utf-8"
        )
        fn = rust[rust.index("pub fn wants_dsp") : rust.index("pub fn prepare_vc_start")]
        self.assertIn('Some("vc")', fn)
        self.assertIn("pth", fn)

    def test_start_is_exclusive_dsp_or_rvc(self):
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        self.assertIn("def _engine_core_ready", src)
        self.assertIn("def _start_dsp_only", src)
        self.assertIn("def audio_infer_dsp", src)
        start = src[src.index("def start_vc") : src.index("def ", src.index("def start_vc") + 1)]
        self.assertIn("self.dsp_only = dsp_on", start)
        self.assertIn("_start_dsp_only", start)
        dsp = src[src.index("def _start_dsp_only") : src.index("def start_vc")]
        self.assertIn('self.gui_config.pth_path = ""', dsp)
        self.assertIn("dsp start preset", dsp)
        self.assertIn("VC_OPENING_STREAM", dsp)
        self.assertNotIn("VC_LOADING_MODEL", dsp)
        self.assertIn("getattr(self.rvc, \"tgt_sr\"", src)

    def test_start_vc_hot_push_uses_fx_when_dsp_only(self):
        src = (ROOT / "app" / "src-tauri" / "src" / "worker.rs").read_text(
            encoding="utf-8"
        )
        start = src.index("pub fn start_vc")
        body = src[start : src.index("pub fn wait_vc_running", start)]
        self.assertIn("wait_worker_ready", body)
        self.assertNotIn("engine_core_ready", body)
        # 纯 DSP 必须把开关塞进 start 本体，不能只靠 inuse 文件。
        #
        # 这几个键以前是在 start_vc 和 push_running_hot 里各拼一遍，判定条件
        # 还和 config::wants_dsp 不一样（更松）—— 壳按 wants_dsp 选了 RVC
        # worker，却在载荷里说 function=fx，RVC 就永远起不来。现在两边共用
        # dsp_command_fields，所以这里断言的是「都走那一个生成器」。
        self.assertIn("dsp_command_fields", body)
        self.assertIn("send_command(root, \"start\"", body)
        # 纯 DSP 不能按 torch 的 100 秒去等
        self.assertIn("20_000", body)
        self.assertIn("WorkerKind::Dsp", body)
        # 热推必须在起流成功之后，否则失败的 start 会被 set 盖成「参数已应用」
        self.assertIn("pub fn push_running_hot", src)
        hot = src[src.index("pub fn push_running_hot") : src.index(
            "pub fn wait_vc_running"
        )]
        self.assertIn("dsp_command_fields", hot)
        # 生成器本体：判定必须来自 wants_dsp，且非 DSP 时把开关明确写成 false
        # （不能只是不提 —— worker 的 gui_config 是常驻的）。
        gen = src[src.index("pub fn dsp_command_fields") : src.index(
            "pub fn start_vc"
        )]
        self.assertIn("crate::config::wants_dsp", gen)
        self.assertIn('json!("fx")', gen)
        self.assertIn("dsp_params", gen)
        self.assertIn('out.insert("dsp_enabled".into(), json!(false))', gen)
        # 松规则不许回来：判定只能问 wants_dsp，不能自己看有没有预设/参数。
        self.assertNotIn("|| !dsp_preset.is_empty()", src)
        self.assertNotIn("|| dsp_params_on", src)
        lib = (ROOT / "app" / "src-tauri" / "src" / "lib.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("push_running_hot", lib)
        self.assertIn('Some("running")', lib)

    def test_worker_start_merges_dsp_from_start_command(self):
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        body = src[src.index("def _worker_start") : src.index("def _worker_stop")]
        self.assertIn('for k in ("dsp_enabled", "dsp_preset", "dsp_params", "function")', body)
        self.assertIn("start values pth=", body)
        self.assertNotIn('i18n("请选择pth文件")', src)

    def test_idle_set_does_not_overwrite_start_error(self):
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        loop = src[src.index("action == \"set\"") :]
        self.assertIn("elif flag_vc:", loop)
        self.assertIn("没在跑", loop)

    def test_homepage_does_not_fake_a_selected_voice(self):
        src = (ROOT / "app" / "src" / "pages" / "HomePage.tsx").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("const current = selected ??", src)
        self.assertIn("const current = selected;", src)

    def test_dsp_activate_keeps_last_model(self):
        src = (ROOT / "app" / "src-tauri" / "src" / "config.rs").read_text(
            encoding="utf-8"
        )
        fn = src[src.index("pub fn write_dsp_on") : src.index("pub fn write_dsp_off")]
        self.assertNotIn('"last_model"', fn)
        self.assertIn('"pth_path"', fn)
        self.assertIn("last_model_pth", src[src.index("pub fn write_dsp_off") :])

    def test_toggle_run_refuses_without_voice_or_dsp(self):
        src = (ROOT / "app" / "src" / "hooks" / "useEngine.ts").read_text(
            encoding="utf-8"
        )
        self.assertIn("last_model_path", src)
        self.assertIn("msg.vc.need_model", src)
        self.assertNotIn("function: modeRef.current === \"bypass\" ? \"im\" : \"vc\"", src)

    def test_dsp_worker_exists_and_skips_torch(self):
        """纯 DSP 必须有一条不 import torch 的进程，否则还是得等 RVC 引擎。"""
        path = ROOT / "tools" / "dsp_worker.py"
        self.assertTrue(path.is_file(), path)
        src = path.read_text(encoding="utf-8")
        self.assertNotIn("import torch", src)
        self.assertNotIn("from torch", src)
        self.assertNotIn("rvc_for_realtime", src)
        self.assertIn('worker_kind": "dsp"', src)
        self.assertIn("VoiceChain", src)
        rust = (ROOT / "app" / "src-tauri" / "src" / "worker.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("dsp_worker_script", rust)
        self.assertIn("pub fn start_worker_kind", rust)
        paths = (ROOT / "app" / "src-tauri" / "src" / "paths.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("dsp_worker.py", paths)

    def test_ui_does_not_say_infer_on_dsp(self):
        src = (ROOT / "app" / "src" / "lib" / "engine.ts").read_text(encoding="utf-8")
        self.assertIn("delayLineDsp", src)
        zh = (ROOT / "app" / "i18n" / "locales" / "zh-CN.json").read_text(
            encoding="utf-8"
        )
        self.assertIn('"delayLineDsp"', zh)
        self.assertIn("处理 {infer}", zh)

    def test_set_hot_does_not_wipe_last_model(self):
        rust = (ROOT / "app" / "src-tauri" / "src" / "lib.rs").read_text(
            encoding="utf-8"
        )
        body = rust[rust.index("fn engine_set_hot") : rust.index("fn engine_swap_model")]
        self.assertNotIn('"last_model"', body)
        self.assertNotIn("last_model_path", body)

    def test_toggle_run_skips_engine_core_for_dsp_only(self):
        src = (ROOT / "app" / "src" / "hooks" / "useEngine.ts").read_text(
            encoding="utf-8"
        )
        self.assertIn("dspOnly", src)
        self.assertIn("!dspOnly", src)
        self.assertIn("activateDsp", src)
        self.assertIn("dsp_preset", src)
        self.assertNotIn("!hasPth || !coreReady", src)
        self.assertNotIn("isEngineCoreReady", src)

    def test_worker_honors_start_issued_during_import(self):
        worker = (ROOT / "tools" / "realtime_worker.py").read_text(encoding="utf-8")
        self.assertIn("worker_boot_ts", worker)
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        self.assertIn("worker_boot_ts", src)
        self.assertIn("last_seq - 1", src)

    def test_apply_dsp_always_sends_fx_and_clears_voice(self):
        src = (ROOT / "app" / "src" / "pages" / "ModelsPage.tsx").read_text(
            encoding="utf-8"
        )
        apply = src[src.index("const applyDsp") : src.index("useEffect", src.index("const applyDsp"))]
        self.assertIn("activateDsp", apply)
        self.assertIn("deactivateDsp", apply)
        rust = (ROOT / "app" / "src-tauri" / "src" / "lib.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("fn dsp_activate", rust)
        self.assertIn("fn dsp_deactivate", rust)
        dsp = (ROOT / "app" / "src-tauri" / "src" / "dsp.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("pub fn activate", dsp)
        self.assertIn("write_dsp_on", dsp)

    def test_start_accepts_fx_function_as_dsp(self):
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        self.assertIn("def _resolve_dsp", src)
        self.assertIn("get_preset", src)
        body = src[src.index("def set_values") : src.index("def _load_fx_from_values")]
        self.assertIn("请先选用一个 DSP 预设", body)
        self.assertIn('"function"', src[src.index("def _values_from_config_file") :])

    def test_sts_reveal_uses_the_chosen_folder(self):
        src = (ROOT / "app" / "src" / "components" / "TtsPanel.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn('invoke("sts_reveal"', src)
        self.assertIn("lastDestRef", src)
        self.assertNotIn("s.out_dir", src)
        rust = (ROOT / "app" / "src-tauri" / "src" / "lib.rs").read_text(
            encoding="utf-8"
        )
        sig = rust[rust.index("fn sts_reveal") : rust.index("fn tts_status")]
        self.assertIn("path:", sig)
        self.assertIn("reveal_output", sig)

    def test_tool_downloads_never_open_in_the_tool_window(self):
        src = (ROOT / "app" / "src" / "lib" / "downloadModels.ts").read_text(
            encoding="utf-8"
        )
        self.assertIn('label === "main"', src)
        self.assertIn("tools_open_downloads", src)
        self.assertIn("filter:", src)
        rust = (ROOT / "app" / "src-tauri" / "src" / "lib.rs").read_text(
            encoding="utf-8"
        )
        sig = rust[rust.index("fn tools_open_downloads") : rust.index(
            "tool_window::focus_main_downloads"
        )]
        self.assertIn("filter:", sig)
        sep = (ROOT / "app" / "src" / "components" / "SeparatePanel.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn('filter: "separate"', sep)
        self.assertNotIn("ExtrasDialog", sep)
        train = (ROOT / "app" / "src" / "components" / "TrainPanel.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn('filter: "train"', train)
        self.assertNotIn("ExtrasDialog", train)

    def test_plaza_does_not_host_dsp(self):
        src = (ROOT / "app" / "src" / "pages" / "PlazaPage.tsx").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("DspPlazaSection", src)
        self.assertFalse(
            (ROOT / "app" / "src" / "components" / "DspPlazaSection.tsx").is_file()
        )

    def test_voices_clear_is_wired(self):
        lib = (ROOT / "app" / "src-tauri" / "src" / "lib.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("fn voices_clear", lib)
        self.assertIn("voices_clear,", lib)
        voices = (ROOT / "app" / "src-tauri" / "src" / "voices.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("pub fn clear_voice", voices)
        cfg = (ROOT / "app" / "src-tauri" / "src" / "config.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("pub fn force_clear_model_paths", cfg)


def _tone(f0=200.0, secs=1.0, harmonics=25):
    """谐波丰富的周期信号 —— 基频和共振峰都能量出来。"""
    n = int(SR * secs)
    t = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, harmonics))
    return (x * 0.1).astype(np.float32)


def _noisy(secs=0.5, seed=1):
    rng = np.random.default_rng(seed)
    n = int(SR * secs)
    t = np.arange(n) / SR
    return (0.3 * np.sin(2 * np.pi * 180 * t) + 0.05 * rng.standard_normal(n)).astype(
        np.float32
    )


def _blocks(chain, x, n=BLOCK):
    return np.concatenate([chain.process(x[i : i + n], SR) for i in range(0, len(x), n)])


def _est_f0(y, lo_hz=60.0, hi_hz=900.0):
    """自相关估基频。只看中段，避开启动瞬态。"""
    seg = y[len(y) // 3 : len(y) // 3 * 2].astype(np.float64)
    seg = seg - seg.mean()
    ac = np.correlate(seg, seg, "full")[len(seg) - 1 :]
    lo, hi = int(SR / hi_hz), int(SR / lo_hz)
    return SR / (lo + int(np.argmax(ac[lo:hi])))


def _centroid(y):
    seg = y[len(y) // 3 : len(y) // 3 * 2].astype(np.float64)
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    freqs = np.fft.rfftfreq(len(seg), 1.0 / SR)
    return float((spec * freqs).sum() / max(spec.sum(), 1e-12))


@unittest.skipUnless(_HAS_NP, "需要 numpy")
class EveryEffectTests(unittest.TestCase):
    """所有效果器的共同契约。"""

    def _chain(self, name):
        from tools.dsp_voice import VoiceChain

        return VoiceChain({name: ACTIVE[name]})

    def test_shape_and_finite(self):
        x = _noisy()
        for name in CHAIN_ORDER:
            y = _blocks(self._chain(name), x)
            self.assertEqual(y.shape, x.shape, name)
            self.assertTrue(np.isfinite(y).all(), f"{name} 出了 NaN/Inf")

    def test_tremolo_wobbles_amplitude(self):
        from tools.dsp_voice import VoiceChain

        n = SR // 2
        x = (0.4 * np.sin(2 * np.pi * 220 * np.arange(n) / SR)).astype(np.float32)
        y = _blocks(VoiceChain({"tremolo": {"rate": 8.0, "depth": 1.0}}), x)
        env = np.abs(y[SR // 8 :]).reshape(-1, 200).mean(axis=1)
        self.assertGreater(env.max() / max(env.min(), 1e-6), 2.0, "振幅没晃起来")

    def test_robotizer_imprints_the_carrier(self):
        from tools.dsp_voice import VoiceChain

        n = SR // 2
        x = (0.25 * np.sin(2 * np.pi * 180 * np.arange(n) / SR)).astype(np.float32)
        y = _blocks(VoiceChain({"robot": {"amount": 1.0, "freq": 80.0}}), x)
        spec = np.abs(np.fft.rfft(y[SR // 8 : SR // 8 + 8192].astype(np.float64)))
        freqs = np.fft.rfftfreq(8192, 1.0 / SR)
        k80 = int(np.argmin(np.abs(freqs - 80.0)))
        self.assertGreater(spec[k80], spec.mean() * 4, "载波 80Hz 没印上去")

    def test_pitch_leaves_fricative_noise_closer_to_dry(self):
        """升调不该把齿音也拉成金属丝。"""
        from tools.dsp_voice import VoiceChain

        rng = np.random.default_rng(3)
        noise = rng.standard_normal(SR // 2).astype(np.float32) * 0.15
        wet = _blocks(VoiceChain({"pitch": {"semitones": 8.0}}), noise)
        err = float(np.mean(np.abs(wet - noise)))
        self.assertLess(err, 0.12)

    def test_never_clips(self):
        """任何一档拉满都不该爆音。"""
        x = _noisy() * 3.0
        for name in CHAIN_ORDER:
            y = _blocks(self._chain(name), x)
            self.assertLessEqual(float(np.abs(y).max()), 1.0 + 1e-5, name)

    def test_block_size_independent(self):
        """1024 / 512 / 480 分块结果必须一致 —— 用户的块长是可调的。

        块长不是 hop 的整数倍时（480 不是 128 的倍数）尤其要成立，
        帧对不齐就会在块边界丢样本，听感是周期性的咔哒。

        pitch 除外：WSOLA 每帧的起点是按互相关搜出来的，搜索窗里有多少前瞻
        取决于输入是怎么分块喂进来的，所以逐样本不可能一致。它的块长无关性
        由 PitchShiftTests 按「音高一致、无掉音」来验。
        """
        x = _noisy(secs=0.4, seed=9)
        for name in CHAIN_ORDER:
            if name == "pitch":
                continue
            a = _blocks(self._chain(name), x, 1024)
            for blk in (512, 480):
                b = _blocks(self._chain(name), x, blk)
                np.testing.assert_allclose(
                    a, b, rtol=0, atol=1e-6, err_msg=f"{name} 块长 {blk} 结果不一致"
                )

    def test_default_params_are_bypass(self):
        """默认参数下每个效果器必须是直通，否则「没开效果」也会改声音。"""
        from tools.dsp_voice import VoiceChain

        x = _noisy(secs=0.2, seed=4)
        y = _blocks(VoiceChain(), x)
        # 整条链末尾有 tanh 软限幅，小信号下近似恒等
        np.testing.assert_allclose(y, np.tanh(x.astype(np.float64)), rtol=0, atol=1e-6)

    def test_reset_restores_initial_output(self):
        c = self._chain("echo")
        x = _noisy(secs=0.2, seed=6)
        first = _blocks(c, x)
        c.reset()
        again = _blocks(c, x)
        np.testing.assert_allclose(first, again, rtol=0, atol=1e-6)

    def test_active_lists_only_changed_effects(self):
        from tools.dsp_voice import VoiceChain

        c = VoiceChain({"pitch": {"semitones": 5}, "echo": {"mix": 0.4}})
        self.assertEqual(set(c.active()), {"pitch", "echo"})
        self.assertEqual(VoiceChain().active(), [])


@unittest.skipUnless(_HAS_NP, "需要 numpy")
class PitchShiftTests(unittest.TestCase):
    """变调必须准，而且不许有掉音。"""

    F0 = 200.0

    def test_semitones_land_on_the_right_frequency(self):
        """整个 ±24 半音范围都要准，两头尤其。

        -24 半音（ratio 0.25）时分析跳距会长到超过帧长，前后帧不再重叠、中间
        还漏掉一段输入 —— 修之前这一档出来是 905Hz，跟目标的 50Hz 毫无关系。
        合成跳距要跟着 ratio 一起缩，并把 Hann 的窗和补回去。
        """
        x = _tone(self.F0)
        from tools.dsp_voice import VoiceChain

        for st in (-24, -19, -12, -5, 3, 7, 12, 19, 24):
            y = _blocks(VoiceChain({"pitch": {"semitones": st}}), x)
            want = self.F0 * semitones_to_ratio(st)
            got = _est_f0(y, lo_hz=40.0, hi_hz=1200.0)
            self.assertLess(
                abs(got - want) / want, 0.07,
                f"{st:+d} 半音: 得到 {got:.1f}Hz，应为 {want:.1f}Hz",
            )

    def test_level_is_stable_across_the_range(self):
        """跳距一变，Hann 的窗和就不是 1 了。不补偿的话音量随设置乱跳。"""
        from tools.dsp_voice import VoiceChain

        x = _tone(self.F0)
        peaks = []
        for st in (-24, -12, -5, 7, 12, 24):
            y = _blocks(VoiceChain({"pitch": {"semitones": st}}), x)
            peaks.append(float(np.abs(y[SR // 3 :]).max()))
        self.assertLess(max(peaks) / min(peaks), 1.5, f"各档音量差太多：{peaks}")

    def test_no_dropouts_on_sustained_tone(self):
        """最初那版双抽头延迟线变调器在持续音上会整段归零（梳状抵消）。

        WSOLA 就是为了修这个换的。这条测试守着它别被换回去。
        """
        x = _tone(self.F0)
        from tools.dsp_voice import VoiceChain

        for st in (-12, -5, 7, 12):
            y = _blocks(VoiceChain({"pitch": {"semitones": st}}), x)
            body = y[SR // 4 :]
            body = body[: len(body) // 200 * 200]
            env = np.abs(body).reshape(-1, 200).max(axis=1)
            holes = int((env < 1e-3).sum())
            self.assertEqual(holes, 0, f"{st:+d} 半音有 {holes} 段静默")

    def test_same_pitch_regardless_of_block_size(self):
        """块长换来换去，出来的音高必须一样，也不许掉音。

        WSOLA 的帧起点是搜出来的，逐样本不可能跟块长无关（见 EveryEffectTests
        里那条的说明），但听感必须一致。
        """
        from tools.dsp_voice import VoiceChain

        x = _tone(self.F0)
        for st in (-24, -12, -5, 7, 12, 24):
            want = self.F0 * semitones_to_ratio(st)
            for blk in (1024, 512, 480, 333, 256):
                y = _blocks(VoiceChain({"pitch": {"semitones": st}}), x, blk)
                got = _est_f0(y, lo_hz=40.0, hi_hz=1200.0)
                self.assertLess(
                    abs(got - want) / want, 0.07,
                    f"{st:+d} 半音 / 块长 {blk}: 得到 {got:.1f}Hz，应为 {want:.1f}Hz",
                )
                body = y[SR // 3 : SR // 3 * 2]
                env = np.abs(body[: len(body) // 200 * 200]).reshape(-1, 200).max(axis=1)
                self.assertEqual(int((env < 1e-3).sum()), 0, f"{st:+d} / {blk} 有掉音")

    def test_buffers_stay_bounded(self):
        """内部缓冲必须有上界，不能只涨不落。

        踩过三次坑，每次现象都是「先卡音、后吃内存」：
        1. 读指针飘到 _out_valid 之外，压缩算出的位移超过有效长度
        2. 压缩时把整条尾巴照搬，容量随 _stretch_more 的翻倍扩容只涨不落
        3. 预热那条早退路径跳过压缩，欠载周期性打回预热，_out_valid 逐次抬高
        """
        from tools.dsp_voice import VoiceChain

        x = _noisy(secs=6.0, seed=2)
        for st in (-12, -5, 7, 12):
            c = VoiceChain({"pitch": {"semitones": st}})
            fx = c._fx["pitch"]
            out_peak = in_peak = 0
            for i in range(0, len(x), BLOCK):
                c.process(x[i : i + BLOCK], SR)
                out_peak = max(out_peak, fx._out_buf.shape[0])
                in_peak = max(in_peak, fx._in_buf.shape[0])
            # 一帧约 1008 点；十几帧的量级是合理的，几十万就是漏了
            self.assertLess(out_peak, fx._frame * 16, f"{st:+d} 输出缓冲 {out_peak}")
            self.assertLess(in_peak, fx._frame * 16, f"{st:+d} 输入缓冲 {in_peak}")


@unittest.skipUnless(_HAS_NP, "需要 numpy")
class FormantTests(unittest.TestCase):
    """共振峰独立于音高 —— 这是 Clownfish 做不到、我们要赢的那一点。"""

    F0 = 200.0

    def test_formant_shift_leaves_pitch_alone(self):
        from tools.dsp_voice import VoiceChain

        x = _tone(self.F0)
        for st in (-6, 6):
            y = _blocks(VoiceChain({"formant": {"shift": st}}), x)
            got = _est_f0(y)
            self.assertLess(
                abs(got - self.F0) / self.F0, 0.05,
                f"共振峰搬 {st:+d} 半音把基频带到了 {got:.1f}Hz",
            )

    def test_formant_shift_moves_the_envelope(self):
        from tools.dsp_voice import VoiceChain

        x = _tone(self.F0)
        base = _centroid(_blocks(VoiceChain(), x))
        up = _centroid(_blocks(VoiceChain({"formant": {"shift": 6}}), x))
        down = _centroid(_blocks(VoiceChain({"formant": {"shift": -6}}), x))
        self.assertGreater(up, base * 1.1, "共振峰上移没让谱重心上去")
        self.assertLess(down, base * 0.95, "共振峰下移没让谱重心下来")

    def test_pitch_up_with_formant_compensation_is_darker(self):
        """升八度 + 共振峰降八度 = 音高上去了，嗓子还是原来那把。

        没有配平的话谱重心会跟着音高一起窜上去（就是花栗鼠）。
        """
        from tools.dsp_voice import VoiceChain

        x = _tone(self.F0)
        raw = _blocks(VoiceChain({"pitch": {"semitones": 12}}), x)
        fixed = _blocks(
            VoiceChain({"pitch": {"semitones": 12}, "formant": {"shift": -12}}), x
        )
        self.assertLess(abs(_est_f0(fixed) - self.F0 * 2) / (self.F0 * 2), 0.06)
        self.assertLess(_centroid(fixed), _centroid(raw) * 0.9, "配平没把亮度压回去")


@unittest.skipUnless(_HAS_NP, "需要 numpy")
class PresetSwitchTests(unittest.TestCase):
    """换预设是**替换**，不是叠加。

    `dsp_params` 热推的永远是一整份预设。以前 apply() 只更新提到的那些效果器，
    于是从「音高 +7」换到「回声」，回声接在还没退下去的 +7 上 —— 用户越换越怪，
    而且没有任何办法换回去（只有关掉 DSP 重开）。编辑器里删掉一个效果器同理，
    删了跟没删一样。
    """

    def test_switching_presets_drops_the_previous_effects(self):
        from tools.dsp_voice import VoiceChain

        c = VoiceChain({"pitch": {"semitones": 7.0}})
        self.assertEqual(c.active(), ["pitch"])
        c.apply({"echo": {"time_ms": 200.0, "feedback": 0.3, "mix": 0.5}})
        self.assertEqual(c.active(), ["echo"], "上一个预设的效果器还挂着")
        self.assertEqual(c.params["pitch"]["semitones"], 0.0)

    def test_removing_an_effect_actually_removes_it(self):
        from tools.dsp_voice import VoiceChain

        full = {"pitch": {"semitones": 5.0}, "drive": {"amount": 0.6}}
        c = VoiceChain(full)
        self.assertEqual(sorted(c.active()), ["drive", "pitch"])
        c.apply({"pitch": {"semitones": 5.0}})  # 编辑器里删掉 drive
        self.assertEqual(c.active(), ["pitch"])

    def test_switching_is_audible_not_just_bookkeeping(self):
        """`active()` 只是账面。真正要保证的是听感上那一层没了。"""
        from tools.dsp_voice import VoiceChain

        x = _tone(f0=200.0, secs=0.5)
        moved = VoiceChain({"pitch": {"semitones": 7.0}})
        _blocks(moved, x)
        moved.apply({"drive": {"amount": 0.5}})
        after = _blocks(moved, x)
        # 切走之后基频应当回到原位，而不是停在 +7 半音（约 300Hz）
        self.assertAlmostEqual(_est_f0(after), 200.0, delta=12.0)


class EchoSliderTests(unittest.TestCase):
    """拖 time_ms 不该把攒着的回声清掉。

    缓冲区原来是按当前 time_ms 分配的 —— 动一下滑条就换一个清零的新缓冲区，
    回声当场消失，一串咔哒。编辑器上那根推子 80ms 推一次，拖一次就是几十下。
    """

    def test_delay_lands_where_the_parameter_says(self):
        from tools.dsp_voice import Echo

        for ms in (50.0, 180.0, 400.0):
            e = Echo(time_ms=ms, feedback=0.0, mix=1.0)
            x = np.zeros(SR, dtype=np.float32)
            x[0] = 1.0
            y = _blocks(e, x, n=480)
            self.assertEqual(int(np.argmax(np.abs(y))), int(SR * ms * 0.001), ms)

    def test_changing_the_time_keeps_the_tail(self):
        from tools.dsp_voice import Echo

        e = Echo(time_ms=200.0, feedback=0.5, mix=1.0)
        x = (0.5 * np.sin(2 * np.pi * 300 * np.arange(SR // 2) / SR)).astype(np.float32)
        _blocks(e, x, n=480)
        before = float(np.abs(e._buf).max())
        e.time_ms = 210.0
        e.process(np.zeros(480, dtype=np.float32), SR)
        self.assertGreater(float(np.abs(e._buf).max()), before * 0.5, "回声被清空了")


class BlockSizeInvarianceTests(unittest.TestCase):
    """同一段音频切成 1024 或 480 一块，结果必须一样。

    设备给的块长不是我们能选的（WASAPI 独占能给出 480、333 这种），任何把状态
    和块长绑在一起的写法在真机上都会露出来，而在 1024 的测试里永远看不见。
    """

    def test_every_effect_is_block_size_agnostic(self):
        from tools.dsp_voice import VoiceChain

        x = _tone(f0=180.0, secs=1.0)
        for name in CHAIN_ORDER:
            if name == "pitch":
                # WSOLA 的相关性搜索本来就跟切块位置有关，波形对不齐是正常的；
                # 它该守的契约是「音高准」，那条在 PitchShiftTests 里。
                continue
            outs = []
            for bs in (1024, 480):
                c = VoiceChain({name: ACTIVE[name]})
                c.reset()
                outs.append(_blocks(c, x, n=bs))
            self.assertLess(
                float(np.max(np.abs(outs[0] - outs[1]))), 1e-3, f"{name} 跟块长有关"
            )


class IndividualEffectTests(unittest.TestCase):
    def test_bitcrush_quantizes(self):
        from tools.dsp_voice import VoiceChain

        x = _noisy(secs=0.2, seed=8)
        y = _blocks(VoiceChain({"bitcrush": {"bits": 4, "downsample": 1}}), x)
        # 4 bit → 台阶数远少于原始样本数
        self.assertLess(len(np.unique(np.round(y, 5))), 40)

    def test_ring_mod_creates_sidebands(self):
        from tools.dsp_voice import VoiceChain

        x = (0.3 * np.sin(2 * np.pi * 500 * np.arange(SR // 2) / SR)).astype(np.float32)
        y = _blocks(VoiceChain({"ring": {"freq": 120, "mix": 1.0}}), x)
        spec = np.abs(np.fft.rfft(y[SR // 8 : SR // 8 + 8192].astype(np.float64)))
        freqs = np.fft.rfftfreq(8192, 1.0 / SR)
        # 380Hz 和 620Hz 应该冒出来
        for want in (380.0, 620.0):
            k = int(np.argmin(np.abs(freqs - want)))
            self.assertGreater(spec[k], spec.mean() * 5, f"{want}Hz 边带没出现")

    def test_radio_kills_lows_and_highs(self):
        from tools.dsp_voice import VoiceChain

        n = SR // 2
        t = np.arange(n) / SR
        x = (0.3 * np.sin(2 * np.pi * 80 * t) + 0.3 * np.sin(2 * np.pi * 1500 * t)
             + 0.3 * np.sin(2 * np.pi * 9000 * t)).astype(np.float32)
        y = _blocks(VoiceChain({"radio": {"mix": 1.0}}), x)
        seg = y[SR // 8 : SR // 8 + 8192].astype(np.float64)
        spec = np.abs(np.fft.rfft(seg * np.hanning(8192)))
        freqs = np.fft.rfftfreq(8192, 1.0 / SR)

        def at(f):
            return spec[int(np.argmin(np.abs(freqs - f)))]

        self.assertLess(at(80.0), at(1500.0) * 0.3, "80Hz 没被限带滤掉")
        self.assertLess(at(9000.0), at(1500.0) * 0.3, "9kHz 没被限带滤掉")

    def test_echo_repeats_after_the_delay(self):
        from tools.dsp_voice import VoiceChain

        n = SR
        x = np.zeros(n, dtype=np.float32)
        x[100:200] = 0.8  # 一声脉冲
        y = _blocks(VoiceChain({"echo": {"time_ms": 100.0, "mix": 1.0, "feedback": 0.5}}), x)
        delay = int(SR * 0.1)
        # 一个延迟之后应当还有能量
        self.assertGreater(float(np.abs(y[delay : delay + 300]).max()), 0.05)

    def test_drive_adds_harmonics(self):
        from tools.dsp_voice import VoiceChain

        n = SR // 2
        x = (0.3 * np.sin(2 * np.pi * 300 * np.arange(n) / SR)).astype(np.float32)
        y = _blocks(VoiceChain({"drive": {"amount": 0.9}}), x)
        spec = np.abs(np.fft.rfft(y[SR // 8 : SR // 8 + 8192].astype(np.float64)))
        freqs = np.fft.rfftfreq(8192, 1.0 / SR)
        k3 = int(np.argmin(np.abs(freqs - 900.0)))
        self.assertGreater(spec[k3], spec.mean() * 5, "过载没有产生三次谐波")

    def test_whisper_flattens_harmonic_structure(self):
        from tools.dsp_voice import VoiceChain

        x = _tone(220.0, secs=0.5)
        dry = _blocks(VoiceChain(), x)
        wet = _blocks(VoiceChain({"whisper": {"amount": 1.0}}), x)

        def peakiness(y):
            seg = y[SR // 6 : SR // 6 + 8192].astype(np.float64)
            spec = np.abs(np.fft.rfft(seg * np.hanning(8192)))
            return float(spec.max() / max(spec.mean(), 1e-12))

        self.assertLess(peakiness(wet), peakiness(dry) * 0.8, "耳语没打散谐波")


@unittest.skipUnless(_HAS_NP, "需要 numpy")
class ChainBudgetTests(unittest.TestCase):
    """十一个效果器全开也要留够余量 —— 这条链跑在音频回调线程上。"""

    def test_all_effects_on_under_15_percent(self):
        from tools.dsp_voice import VoiceChain

        budget_ms = BLOCK / SR * 1000.0
        c = VoiceChain(ACTIVE)
        x = _noisy(secs=1.0, seed=12)
        for i in range(0, 8 * BLOCK, BLOCK):
            c.process(x[i : i + BLOCK], SR)
        times = []
        for i in range(8 * BLOCK, len(x) - BLOCK, BLOCK):
            t0 = time.perf_counter()
            c.process(x[i : i + BLOCK], SR)
            times.append((time.perf_counter() - t0) * 1000.0)
        median = sorted(times)[len(times) // 2]
        self.assertLess(
            median,
            budget_ms * 0.15,
            f"全开占了块预算的 {median / budget_ms * 100:.1f}%"
            f"（{median:.2f}ms / {budget_ms:.2f}ms），上限 15%",
        )


if __name__ == "__main__":
    unittest.main()
