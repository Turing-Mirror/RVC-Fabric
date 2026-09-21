# -*- coding: utf-8 -*-
"""scripts/run_tests.bat 是 Windows 上跑单测的入口，必须真的能被 cmd.exe 解析。

审计 2026-09-15 复现：仓库里这份 .bat 是 LF 行尾，cmd.exe 按 CRLF 切块解析，
注释和引号被粘成命令，入口直接 exit 9009（'unit'、'.exe"' 不是命令）。
这里钉住两件事：行尾必须是 CRLF（.gitattributes 也声明了），以及脚本本身
仍然做真实发现、透出真实退出码 —— 不许用假通过掩盖。
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "scripts" / "run_tests.bat"
GITATTR = ROOT / ".gitattributes"


class RunTestsBatTests(unittest.TestCase):
    def test_batch_file_uses_crlf_line_endings(self):
        data = BAT.read_bytes()
        self.assertTrue(data, "run_tests.bat 不能为空")
        body = data.rstrip(b"\r\n")
        self.assertNotIn(
            b"\n", body.replace(b"\r\n", b""), "存在裸 LF，cmd.exe 会误解析"
        )

    def test_gitattributes_pins_bat_to_crlf(self):
        text = GITATTR.read_text(encoding="utf-8")
        bat_rule = any(
            line.split()[:1] == ["*.bat"] and "eol=crlf" in line
            for line in text.splitlines()
            if line.strip() and not line.startswith("#")
        )
        self.assertTrue(bat_rule, ".gitattributes 必须给 *.bat 钉 eol=crlf")

    def test_entry_runs_real_discovery_with_runtime_python(self):
        text = BAT.read_text(encoding="utf-8")
        self.assertIn(r'Runtime\python.exe', text, "应优先用内置 Runtime 解释器")
        self.assertIn("unittest discover", text)
        self.assertIn("PYTHONPATH", text, "嵌入式 Runtime 需要显式 PYTHONPATH")
        # 退出码必须透传：测试失败时入口不能报成功。
        self.assertIn("set ERR=%errorlevel%", text)
        self.assertIn("exit /b %ERR%", text)


if __name__ == "__main__":
    unittest.main()
