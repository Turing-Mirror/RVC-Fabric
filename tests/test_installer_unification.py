"""安装包统一到 NSIS 之后，几条不能被悄悄改回去的约定。

背景：以前手动下载走 Inno 打的包，自动更新走 Tauri 打的 NSIS 包。两套并存的
后果是引擎侧的修复永远传不到走自动更新的用户手上 —— 那个包里根本没有引擎
文件。统一到 NSIS 一套之后，下面这些是新链路的承重墙。
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TAURI_CONF = REPO / "app" / "src-tauri" / "tauri.conf.json"
HOOKS = REPO / "app" / "src-tauri" / "installer-hooks.nsh"
PREP = REPO / "scripts" / "prepare_engine_payload.py"


def conf() -> dict:
    return json.loads(TAURI_CONF.read_text(encoding="utf-8"))


class EngineShipsWithTheInstaller(unittest.TestCase):
    def test_engine_files_are_in_resources(self):
        """引擎源码必须进安装包，否则自动更新的用户拿不到引擎侧的修复。"""
        res = conf()["bundle"]["resources"]
        targets = set(res.values())
        for needed in ("gui_v1.py", "tools", "infer", "configs", "i18n", "assets"):
            self.assertIn(needed, targets, f"{needed} 不在安装包里")

    def test_engine_comes_from_the_prepared_payload(self):
        """不能直接拷仓库目录。

        直接写 "../../assets" 看着能用，但发版机器只要跑过一次程序，
        assets/ 里就会多出三四百 MB 的模型权重，原封不动进安装包；
        configs/inuse/config.json 还会带上那台机器的绝对路径。
        必须走 prepare_engine_payload.py 筛过的负载。
        """
        res = conf()["bundle"]["resources"]
        for src in res:
            if src == "../frontend":
                continue
            self.assertTrue(
                src.startswith("engine-payload/"),
                f"{src} 绕过了引擎负载，直接拷仓库目录",
            )

    def test_prepare_script_exists(self):
        self.assertTrue(PREP.is_file(), "引擎负载准备脚本不见了")

    def test_prepare_script_is_wired_into_the_build(self):
        pkg = json.loads((REPO / "app" / "package.json").read_text(encoding="utf-8"))
        post = pkg["scripts"].get("postbuild", "")
        self.assertIn(
            "prepare_engine_payload.py",
            post,
            "postbuild 没接上负载准备脚本，构建出来的包会缺引擎文件",
        )


class InstallerHooks(unittest.TestCase):
    def test_hooks_file_has_a_bom(self):
        """钩子里有中文文件名（启动器.exe 等），NSIS 要 UTF-8 BOM 才认。"""
        self.assertEqual(HOOKS.read_bytes()[:3], b"\xef\xbb\xbf")

    def test_all_four_hooks_defined(self):
        text = HOOKS.read_text(encoding="utf-8-sig")
        for name in (
            "NSIS_HOOK_PREINSTALL",
            "NSIS_HOOK_POSTINSTALL",
            "NSIS_HOOK_PREUNINSTALL",
            "NSIS_HOOK_POSTUNINSTALL",
        ):
            self.assertIn(f"!macro {name}", text, f"缺少 {name}")

    def test_macros_are_balanced(self):
        lines = HOOKS.read_text(encoding="utf-8-sig").splitlines()
        opens = sum(1 for line in lines if line.strip().startswith("!macro "))
        closes = sum(1 for line in lines if line.strip() == "!macroend")
        self.assertEqual(opens, closes, "!macro 和 !macroend 不配对")

    def test_never_touches_user_data_or_runtime(self):
        """用户下了几个 GB 的运行时和自己的音色，删了找不回来。"""
        for line in HOOKS.read_text(encoding="utf-8-sig").splitlines():
            code = line.strip()
            if not code or code.startswith(";"):
                continue
            for danger in ("Runtime", "User_Data", "engine-core"):
                self.assertNotIn(danger, code, f"钩子碰了 {danger}：{code}")

    def test_never_recursively_deletes_the_install_dir(self):
        text = HOOKS.read_text(encoding="utf-8-sig")
        self.assertIsNone(
            re.search(r'RMDir\s+/r\s+"\$INSTDIR"\s*$', text, re.MULTILINE),
            "递归删整个安装目录会把用户的运行时和音色一起删掉",
        )

    def test_hooks_are_wired_into_the_config(self):
        nsis = conf()["bundle"]["windows"]["nsis"]
        self.assertEqual(nsis.get("installerHooks"), "installer-hooks.nsh")

    def test_install_mode_matches_the_registry_key_the_updater_reads(self):
        """currentUser 才会把安装目录写进 HKCU。

        改成 perMachine 会写去 HKLM，装到自定义目录的老用户升级时找不到
        原目录，当成全新安装落到 %LOCALAPPDATA%，几个 GB 的运行时要重下。
        """
        nsis = conf()["bundle"]["windows"]["nsis"]
        self.assertEqual(nsis.get("installMode"), "currentUser")

    def test_publisher_matches_the_registry_key_name(self):
        """NSIS 的注册表键名取自 publisher。

        publisher 不填的话 tauri-bundler 会拿 identifier 的第二段
        （com.turingmirror.rvcfabric → turingmirror），和 Turing-Mirror
        差一个连字符，注册表当成两个不同的键，升级就定位不到安装目录。
        """
        self.assertEqual(conf()["bundle"]["publisher"], "Turing-Mirror")


if __name__ == "__main__":
    unittest.main()
