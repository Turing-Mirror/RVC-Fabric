# -*- coding: utf-8 -*-
"""前端 invoke 的参数必须都在 Rust 命令的签名里。

**签名里没有的参数 Tauri 是直接丢掉的** —— 不报错、不警告，那个值就是没传到。

这条测试是踩了坑之后加的：`dsp_enabled` / `dsp_preset` / `dsp_params` 三个键
在 config::HOT_KEYS 里、config.rs 有默认值、inuse 模板有、引擎侧也读了，
唯独 `engine_set_hot` 的参数列表里没有。于是模型页点一个 DSP 预设，
配置没写、worker 没收到，一点反应都没有；而静态看每一处都「对」。

Tauri 会把 JS 的 camelCase 自动转成 Rust 的 snake_case，所以两种写法都算通过。

纯 stdlib，不需要 node 或 cargo。
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUST_DIR = ROOT / "app" / "src-tauri" / "src"
TS_DIR = ROOT / "app" / "src"

# 这些是 Tauri 自己注入的，前端从来不传。
INJECTED = {"app", "state", "window", "webview"}


def _strip_comments(s: str) -> str:
    """只去行注释。

    **不要**顺手加一条 `/\\*.*?\\*/` 去块注释：源码里有
    `"application/json,text/plain,*/*"` 这样的字符串，里面的 `*/` 会跟后面某处
    真正的 `/*` 配上对，中间一大段（含几十个 `#[tauri::command]`）就被吃掉了，
    于是这套检查静悄悄地什么都没查还一路绿。踩过一次，别再加回来。

    去行注释是有必要的：参数上方常有 `// Optional override: …` 这样的说明，
    不去掉的话「逗号后面紧跟参数名」这条匹配会漏掉那个参数。
    """
    return re.sub(r"//[^\n]*", "", s)


def _snake(x: str) -> str:
    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), x)


def command_signatures() -> dict[str, set[str]]:
    """命令名 → 参数名集合。括号靠配对扫，泛型里的尖括号不影响。"""
    src = _strip_comments(
        "\n".join(p.read_text(encoding="utf-8") for p in sorted(RUST_DIR.glob("*.rs")))
    )
    out: dict[str, set[str]] = {}
    for m in re.finditer(
        r"#\[tauri::command\]\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*\(", src
    ):
        i = m.end()
        depth, j = 1, i
        while j < len(src) and depth:
            if src[j] == "(":
                depth += 1
            elif src[j] == ")":
                depth -= 1
            j += 1
        args = src[i : j - 1]
        out[m.group(1)] = set(re.findall(r"(?:^|,)\s*(\w+)\s*:", args))
    return out


def invoke_calls() -> list[tuple[str, set[str]]]:
    """(命令名, 前端传的键)。只看字面量对象的那些调用。"""
    src = "\n".join(p.read_text(encoding="utf-8") for p in sorted(TS_DIR.rglob("*.ts*")))
    calls = []
    for m in re.finditer(r'invoke(?:<[^>]*>)?\(\s*"(\w+)"\s*,\s*\{([^{}]*)\}', src):
        body = m.group(2)
        keys = set(re.findall(r"(\w+)\s*:", body)) | set(
            re.findall(r"^\s*(\w+)\s*,?\s*$", body, re.M)
        )
        calls.append((m.group(1), {k for k in keys if k}))
    return calls


class TauriCommandContractTests(unittest.TestCase):
    def setUp(self):
        self.sigs = command_signatures()

    def test_found_the_commands(self):
        """正则要是失灵了，这条测试会变成「什么都没查」还一路绿。"""
        self.assertGreater(len(self.sigs), 50, "没扫到命令，正则可能失灵了")
        self.assertIn("engine_set_hot", self.sigs)

    def test_every_invoked_arg_exists_in_the_signature(self):
        problems = []
        for cmd, keys in invoke_calls():
            params = self.sigs.get(cmd)
            if params is None:
                continue  # 命令名是变量拼出来的那种，跳过
            for k in sorted(keys):
                if k in params or _snake(k) in params:
                    continue
                problems.append(f"{cmd}(…, {{{k}}}) —— 签名里没有，这个值会被丢掉")
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_dsp_hot_keys_reach_the_engine(self):
        """DSP 三个键的完整链路：签名 → payload。这就是当初漏掉的那一环。"""
        params = self.sigs["engine_set_hot"]
        for k in ("dsp_enabled", "dsp_preset", "dsp_params"):
            self.assertIn(k, params, f"engine_set_hot 签名里没有 {k}")
        src = (RUST_DIR / "lib.rs").read_text(encoding="utf-8")
        for k in ("dsp_enabled", "dsp_preset", "dsp_params"):
            self.assertIn(f'"{k}".into()', src, f"{k} 没被放进 payload")

    def test_no_command_is_registered_twice(self):
        """invoke_handler 里重名会编译报错，但两个同名 fn 分散在不同文件里不会。"""
        src = _strip_comments(
            "\n".join(p.read_text(encoding="utf-8") for p in sorted(RUST_DIR.glob("*.rs")))
        )
        names = re.findall(
            r"#\[tauri::command\]\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", src
        )
        dupes = sorted({n for n in names if names.count(n) > 1})
        self.assertEqual(dupes, [], f"命令重名：{dupes}")

    def test_every_command_is_registered(self):
        """写了 #[tauri::command] 但忘了挂进 invoke_handler，前端调用只会报
        「command not found」，而那条错误往往被 .catch(() => {}) 吞掉。"""
        lib = (RUST_DIR / "lib.rs").read_text(encoding="utf-8")
        m = re.search(r"generate_handler!\s*\[(.*?)\]", lib, re.S)
        self.assertIsNotNone(m, "没找到 generate_handler!")
        registered = set(re.findall(r"(\w+)", m.group(1)))
        missing = sorted(c for c in self.sigs if c not in registered)
        self.assertEqual(missing, [], f"这些命令没挂进 invoke_handler：{missing}")


if __name__ == "__main__":
    unittest.main()
