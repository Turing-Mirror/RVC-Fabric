# -*- coding: utf-8 -*-
"""N01 / B-04：与系统其他音频共存的静态钉住。

用户报告：软件启动、预热、开启变声时 TeamSpeak 闭麦、音乐卡住。本机没有
复现条件，只能把代码层面确定的两个机理钉死：

1. 设备列表刷新不得停流。实时流活在 AudioIoProcess 子进程里，worker /
   dsp_worker 进程的 ``sd`` 只做查询；PortAudio 的 _terminate/_initialize
   也只管本进程。update_devices 里的 ``stop_stream()`` 是无谓地杀掉
   用户正在用的变声流 —— 状态却还写着 running。
2. 进程优先级按阶段提升。启动/导入/预热是几十秒的重活，全程 HIGH 会挤占
   TeamSpeak、播放器这类软件的音频线程；HIGH 只在开流之后才该出现。
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _func_node(src: str, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name}")


def _calls(node: ast.AST) -> list:
    out = []
    for n in ast.walk(node):
        f = getattr(n, "func", None)
        if isinstance(n, ast.Call) and isinstance(f, ast.Attribute):
            out.append((n.lineno, f.attr))
        elif isinstance(n, ast.Call) and isinstance(f, ast.Name):
            out.append((n.lineno, f.id))
    return out


class UpdateDevicesDoesNotStopStreams(unittest.TestCase):
    """设备枚举只读列表，不碰任何流（gui_v1 与 dsp_worker 同一规矩）。"""

    def _check(self, path: Path, label: str):
        src = path.read_text(encoding="utf-8")
        fn = _func_node(src, "update_devices")
        names = [name for _, name in _calls(fn)]
        self.assertNotIn(
            "stop_stream",
            names,
            f"{label}: update_devices 不得调用 stop_stream（刷新列表 ≠ 停流）",
        )

    def test_gui_v1(self):
        self._check(ROOT / "gui_v1.py", "gui_v1")

    def test_dsp_worker(self):
        self._check(ROOT / "tools" / "dsp_worker.py", "dsp_worker")

    def test_reinit_is_idle_only(self):
        """_terminate/_initialize 重建的是本进程 PortAudio —— 本进程还开着
        监听流时重建会把它弄坏，所以只能在完全空闲时做。"""
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        fn = _func_node(src, "update_devices")
        calls = _calls(fn)
        term = next(l for l, name in calls if name == "_terminate")
        init = next(l for l, name in calls if name == "_initialize")
        query = next(l for l, name in calls if name == "query_devices")
        self.assertLess(term, init, "必须先 _terminate 再 _initialize")
        self.assertLess(init, query, "重建必须在 query_devices 之前")
        # busy 守卫要把重建整个包住：找包住 _terminate 调用的 If。
        busy_if = None
        for n in ast.walk(fn):
            if not isinstance(n, ast.If):
                continue
            for sub in ast.walk(n):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "_terminate"
                ):
                    busy_if = n
        self.assertIsNotNone(busy_if, "_terminate 必须在一个条件分支里，不能无条件执行")
        cond = ast.dump(busy_if.test)
        for guard in ("audio_proc", "monitor_stream"):
            self.assertIn(guard, ast.dump(fn), f"忙闲判定要检查 {guard}")


class PriorityIsStaged(unittest.TestCase):
    """启动/预热不拿 HIGH；HIGH 只在开流之后。"""

    def test_worker_boot_is_not_high(self):
        src = (ROOT / "tools" / "realtime_worker.py").read_text(encoding="utf-8")
        fn = _func_node(src, "main")
        boosts = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "boost_current_process"
        ]
        self.assertTrue(boosts, "worker 启动仍要抬优先级（压 EcoQoS）")
        for b in boosts:
            self.assertFalse(
                any(k.arg == "high" and isinstance(k.value, ast.Constant) and k.value.value
                    for k in b.keywords),
                "启动阶段不得用 high=True —— 加载几十秒会挤占其他软件音频",
            )

    def test_stream_start_escalates_to_high(self):
        src = (ROOT / "gui_v1.py").read_text(encoding="utf-8")
        fn = _func_node(src, "start_stream")
        boosts = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "boost_current_process"
        ]
        self.assertTrue(
            any(
                k.arg == "high" and isinstance(k.value, ast.Constant) and k.value.value
                for b in boosts
                for k in b.keywords
            ),
            "开流后必须升回 HIGH（实时约束从这里才成立）",
        )
        # 升级必须发生在 audio_proc.start() 之后：流没起来不算有实时约束。
        start_calls = [
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "start"
        ]
        boost_lines = [b.lineno for b in boosts]
        self.assertTrue(
            any(bl > sl for bl in boost_lines for sl in start_calls),
            "boost(high=True) 要在流启动之后调用",
        )

    def test_boost_allows_escalation(self):
        """win_realtime 的守护必须允许 later high=True 再升一级。"""
        src = (ROOT / "tools" / "win_realtime.py").read_text(encoding="utf-8")
        fn = _func_node(src, "boost_current_process")
        self.assertIn(
            "_boost_level",
            ast.dump(fn),
            "优先级要用可升级的级别守护（一次性布尔会让开流升不上 HIGH）",
        )


if __name__ == "__main__":
    unittest.main()
