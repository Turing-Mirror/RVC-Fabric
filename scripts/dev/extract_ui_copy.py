# -*- coding: utf-8 -*-
"""把界面上能看到的中文文案全部抽出来，生成一份可逐句修改的总表。

为什么要脚本而不是手抄一份：文案会跟着功能改，手抄的表第二天就对不上了。
这个脚本可以随时重跑，改完文案再跑一次就知道哪些还没动。

用法::

    python scripts/dev/extract_ui_copy.py            # 生成 docs/界面文案总表.md
    python scripts/dev/extract_ui_copy.py --check    # 只报告新增/失效条目，不写文件

抽取范围是 `app/src/` 下的 .tsx / .ts —— 也就是壳层界面。引擎那边（Python）
的报错文案是另一套，不在这份表里。

**注意**：注释里的中文不算文案。代码注释是写给维护者看的，混进来会让这张表
噪声大到没法用，所以按行剔除 `//` 和 `/* */`。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "app" / "src"
OUT = ROOT / "docs" / "界面文案总表.md"

CJK = re.compile(r"[\u4e00-\u9fff]")

# 界面分区：文件 → 用户看到的名字。顺序就是表里的章节顺序。
SECTIONS: list[tuple[str, str]] = [
    ("components/TitleBar.tsx", "标题栏"),
    ("components/Dock.tsx", "底栏（常驻控制条）"),
    ("pages/HomePage.tsx", "首页"),
    ("pages/ModelsPage.tsx", "模型页"),
    ("components/StoreDialog.tsx", "社区音色（商店弹窗）"),
    ("pages/PlazaPage.tsx", "广场"),
    ("components/AdBanner.tsx", "广场投放条"),
    ("pages/SettingsPage.tsx", "设置页"),
    ("lib/config.ts", "设置页 · 问号里的说明"),
    ("pages/MorePage.tsx", "其他页"),
    ("components/SeparateDialog.tsx", "人声分离弹窗"),
    ("components/TrainDialog.tsx", "训练音色弹窗"),
    ("components/ExtrasDialog.tsx", "下载模型弹窗"),
    ("components/ProvisionGate.tsx", "首次运行 · 补全运行环境"),
    ("pages/HelpPage.tsx", "说明页"),
    ("components/ErrorBoundary.tsx", "崩溃兜底页"),
    ("components/controls.tsx", "通用控件"),
    ("components/ui.tsx", "通用版式"),
    ("lib/engine.ts", "引擎状态文案"),
    ("lib/plaza.ts", "广场数据层文案"),
    ("lib/voices.ts", "音色数据层文案"),
    ("lib/nav.ts", "导航项名称"),
    ("App.tsx", "全局提示与对话框"),
    ("hooks/useEngine.ts", "引擎启停提示"),
]


def strip_comments(text: str) -> str:
    """去掉注释，但保留行数（用空行占位），这样行号还能对上源码。"""
    out = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    lines = []
    for ln in out.split("\n"):
        # 只处理行首就是注释的情况。行尾的 // 可能出现在字符串里（URL），
        # 粗暴地砍会把 https:// 后面的文案一起砍掉。
        if ln.lstrip().startswith("//"):
            lines.append("")
        else:
            lines.append(ln)
    return "\n".join(lines)


# 字符串字面量：单引号 / 双引号 / 反引号
LITERAL = re.compile(r"""(?<![\w$])(['"`])((?:\\.|(?!\1)[^\\])*)\1""", re.S)
# JSX 里裸露的文字：>文字<
JSX_TEXT = re.compile(r">([^<>{}\n][^<>{}]*)<")


def extract(path: Path) -> list[tuple[int, str]]:
    raw = path.read_text(encoding="utf-8")
    text = strip_comments(raw)
    found: list[tuple[int, str]] = []
    seen: set[str] = set()

    def add(pos: int, s: str) -> None:
        s = s.strip()
        if not s or not CJK.search(s):
            return
        # className 里偶尔有中文？没有。但模板串里的 ${} 要留着，
        # 让人知道这句是拼出来的。
        if s in seen:
            return
        seen.add(s)
        found.append((text.count("\n", 0, pos) + 1, s))

    for m in LITERAL.finditer(text):
        add(m.start(), m.group(2))
    for m in JSX_TEXT.finditer(text):
        add(m.start(), m.group(1))

    found.sort(key=lambda x: x[0])
    return found


def md_escape(s: str) -> str:
    """表格里 | 会断列；换行要变成 <br> 否则整行塌掉。"""
    return s.replace("\\n", "<br>").replace("|", "\\|").replace("\n", "<br>")


def build() -> tuple[str, int]:
    parts: list[str] = [
        "# 界面文案总表",
        "",
        "软件里用户能看到的每一句中文，按界面分区列在这里。",
        "",
        "**怎么改**：在「改成」那一列写新文案，留空表示不改。改完把这份文件给我，",
        "我按表改代码。`位置` 是源码文件和行号，只是给我定位用的，你不用管。",
        "",
        "**注意**：",
        "",
        "- 带 `${...}` 的是拼接出来的句子，`${}` 里的东西是运行时才知道的值"
        "（版本号、文件名、数量），改的时候把它原样留着。",
        "- 同一句话在多处出现只列一次，改一处就是全改。",
        "- 这份表由 `scripts/dev/extract_ui_copy.py` 生成，改完代码重跑一次就能对账。",
        "",
        "---",
        "",
    ]
    total = 0
    for rel, title in SECTIONS:
        p = SRC / rel
        if not p.is_file():
            continue
        rows = extract(p)
        if not rows:
            continue
        total += len(rows)
        parts.append(f"## {title}")
        parts.append("")
        parts.append(f"<sub>`app/src/{rel}`</sub>")
        parts.append("")
        parts.append("| 位置 | 现在的文案 | 改成 |")
        parts.append("|---|---|---|")
        for line, s in rows:
            parts.append(f"| {line} | {md_escape(s)} |  |")
        parts.append("")

    # 没有登记在 SECTIONS 里的文件也要报出来，不然新加的界面会被漏掉
    known = {r for r, _ in SECTIONS}
    missed = []
    for p in sorted(SRC.rglob("*.ts*")):
        rel = p.relative_to(SRC).as_posix()
        if rel in known or p.suffix not in (".ts", ".tsx"):
            continue
        if extract(p):
            missed.append(rel)
    if missed:
        parts.append("## 未登记的文件")
        parts.append("")
        parts.append("这些文件里也有中文但没登记进分区表，"
                     "说明 `extract_ui_copy.py` 的 SECTIONS 该补了：")
        parts.append("")
        for rel in missed:
            parts.append(f"- `app/src/{rel}`")
        parts.append("")

    return "\n".join(parts) + "\n", total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="只报告数量，不写文件")
    args = ap.parse_args()

    text, total = build()
    if args.check:
        print(f"共 {total} 条文案")
        if OUT.is_file() and OUT.read_text(encoding="utf-8") == text:
            print("总表是最新的")
            return 0
        print(f"总表与代码不一致，重跑一次生成：{OUT.relative_to(ROOT)}")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"已写出 {OUT.relative_to(ROOT)}（{total} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
