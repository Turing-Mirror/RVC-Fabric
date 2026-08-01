# -*- coding: utf-8 -*-
"""版本号必须四处一致。

发 1.3.1 的时候，版本号要改的地方有五处，漏了 update.rs 那一处，于是发出去
的包对外自称 1.3.0：「其他」页显示错、遥测把一整批用户记成上一版、广场的
版本定向全部落空。而这些症状只有装到 Windows 上才看得见 —— 在 Mac 上改源码
的人根本没机会发现。

update.rs 那一处已经改成 `env!("CARGO_PKG_VERSION")`，跟着 Cargo.toml 走，
不会再漏。剩下这四处是真的各写各的，只能靠这个测试盯着。

这个测试不需要 Windows，也不需要构建，`python -m unittest` 就能跑。
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CARGO_TOML = ROOT / "app" / "src-tauri" / "Cargo.toml"
TAURI_CONF = ROOT / "app" / "src-tauri" / "tauri.conf.json"
PACKAGE_JSON = ROOT / "app" / "package.json"
INNO_ISS = ROOT / "installer" / "RVC_Fabric_Setup.iss"
UPDATE_RS = ROOT / "app" / "src-tauri" / "src" / "update.rs"

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def cargo_version() -> str:
    # 只认 [package] 段里的第一个 version，依赖项里的 version 不算。
    text = CARGO_TOML.read_text(encoding="utf-8")
    in_package = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            in_package = s == "[package]"
            continue
        if in_package:
            m = re.match(r'version\s*=\s*"([^"]+)"', s)
            if m:
                return m.group(1)
    raise AssertionError("Cargo.toml 的 [package] 段里没找到 version")


def inno_version() -> str:
    text = INNO_ISS.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', text)
    assert m, "installer/RVC_Fabric_Setup.iss 里没找到 MyAppVersion"
    return m.group(1)


class TestVersionSync(unittest.TestCase):
    def test_all_sources_agree(self):
        got = {
            "Cargo.toml": cargo_version(),
            "tauri.conf.json": json.loads(TAURI_CONF.read_text(encoding="utf-8"))["version"],
            "package.json": json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["version"],
            "installer/RVC_Fabric_Setup.iss": inno_version(),
        }
        uniq = set(got.values())
        self.assertEqual(
            len(uniq),
            1,
            "版本号对不上，发版前必须改齐：\n"
            + "\n".join(f"  {k:32} {v}" for k, v in got.items()),
        )
        self.assertRegex(
            uniq.pop(), SEMVER, "版本号得是 x.y.z，别带 -hotfix / -part 后缀"
        )

    def test_app_version_is_derived_not_handwritten(self):
        """APP_VERSION 必须跟着 Cargo.toml 走，不能写死。

        写死过一次，代价是一整版发错版本号。这条测试就是不让它变回去。
        """
        src = UPDATE_RS.read_text(encoding="utf-8")
        m = re.search(r"pub const APP_VERSION: &str = ([^;]+);", src)
        self.assertIsNotNone(m, "update.rs 里找不到 APP_VERSION")
        expr = m.group(1).strip()
        self.assertEqual(
            expr,
            'env!("CARGO_PKG_VERSION")',
            f"APP_VERSION 被改成写死的了（现在是 {expr}）。"
            "写死就会漏改 —— 让它跟着 Cargo.toml 走。",
        )


if __name__ == "__main__":
    unittest.main()
