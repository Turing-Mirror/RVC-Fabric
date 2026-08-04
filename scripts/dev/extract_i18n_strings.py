# -*- coding: utf-8 -*-
"""抽取软件用户可见中文文案，写入 docs/i18n/，供后续 i18n 对照与翻译。

覆盖三层：

1. 前端 React（app/src）—— 界面主文案
2. Rust 壳（app/src-tauri/src）—— 托盘、错误、进度、命令返回
3. Python 引擎（gui_v1 / tools 入口与 worker）—— status/日志里会冒到界面的句子

不抽：代码注释、pymss 内部算法库、RVCMAX/node_modules/target 等。

用法::

    python scripts/dev/extract_i18n_strings.py
    python scripts/dev/extract_i18n_strings.py --check

同时会刷新 docs/界面文案总表.md（前端表，兼容旧路径）。
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "docs" / "i18n"
LEGACY_FRONTEND_TABLE = ROOT / "docs" / "界面文案总表.md"

CJK = re.compile(r"[\u4e00-\u9fff]")
CODE_SMELL = re.compile(r"[;=]|=>|\?\s*[\"'`]")
JSX_TEXT = re.compile(r">([^<>{}]+)<")

# ---------------------------------------------------------------------------
# 前端分区
# ---------------------------------------------------------------------------

FRONTEND_SECTIONS: list[tuple[str, str]] = [
    ("components/TitleBar.tsx", "标题栏"),
    ("components/Dock.tsx", "底栏（常驻控制条）"),
    ("pages/HomePage.tsx", "首页"),
    ("pages/ModelsPage.tsx", "模型页"),
    ("components/StoreSection.tsx", "社区音色（广场内嵌）"),
    ("pages/PlazaPage.tsx", "广场"),
    ("components/AdBanner.tsx", "广场投放条"),
    ("components/PinnedRow.tsx", "广场置顶投放"),
    ("pages/SettingsPage.tsx", "设置页"),
    ("lib/config.ts", "设置页 · 问号说明"),
    ("lib/glossary.ts", "专有名词表"),
    ("lib/hotkeys.ts", "快捷键文案"),
    ("pages/HelpPage.tsx", "说明页"),
    ("pages/MorePage.tsx", "其他页"),
    ("components/ToolWindow.tsx", "独立工具窗口 · 外壳"),
    ("components/SeparatePanel.tsx", "人声分离窗口"),
    ("components/TrainPanel.tsx", "训练音色窗口"),
    ("components/TtsPanel.tsx", "语音转换 / 合成窗口"),
    ("components/ExtrasDialog.tsx", "下载模型弹窗"),
    ("components/ProvisionGate.tsx", "首次运行 · 补全运行环境"),
    ("components/MainGpuPicker.tsx", "主显卡选择"),
    ("components/Nudge.tsx", "邀请 / 关注浮层"),
    ("components/ErrorBoundary.tsx", "崩溃兜底页"),
    ("components/controls.tsx", "通用控件"),
    ("components/ui.tsx", "通用版式"),
    ("components/Tooltip.tsx", "提示气泡"),
    ("components/SegmentControl.tsx", "分段控件"),
    ("components/PageHost.tsx", "页面容器"),
    ("lib/engine.ts", "引擎状态文案"),
    ("lib/plaza.ts", "广场数据层"),
    ("lib/voices.ts", "音色数据层"),
    ("lib/nav.ts", "导航项名称"),
    ("lib/links.ts", "外链与关注文案"),
    ("lib/appearance.ts", "外观相关文案"),
    ("lib/downloadModels.ts", "下载模型入口"),
    ("App.tsx", "全局提示与对话框"),
    ("main.tsx", "启动入口"),
    ("hooks/useEngine.ts", "引擎启停提示"),
    ("hooks/useConfig.ts", "配置钩子提示"),
]

RUST_SECTIONS: list[tuple[str, str]] = [
    ("shell_extras.rs", "托盘 / 快捷键 / 诊断 / 咨询包"),
    ("worker.rs", "变声 worker 启停"),
    ("provision.rs", "运行时补全"),
    ("engine_assets.rs", "引擎资源 / VB-Cable"),
    ("extra_assets.rs", "扩展资源（分离模型 / 底模）"),
    ("download.rs", "下载器"),
    ("extract.rs", "解压"),
    ("update.rs", "检查更新"),
    ("store.rs", "社区商店后端"),
    ("voices.rs", "本地音色库"),
    ("config.rs", "配置同步与校验"),
    ("plaza.rs", "广场 feed 解析"),
    ("telemetry.rs", "遥测"),
    ("separate.rs", "人声分离任务"),
    ("train.rs", "训练任务"),
    ("tts.rs", "语音合成任务"),
    ("sts.rs", "音频变声任务"),
    ("tool_window.rs", "工具窗口"),
    ("legacy.rs", "打开旧版面板 / WebUI"),
    ("ui_assets.rs", "界面资源加载"),
    ("window_watch.rs", "窗口定位与圆角"),
    ("catalog.rs", "在线清单"),
    ("paths.rs", "路径与运行时探测"),
    ("lib.rs", "命令层进度与聚合文案"),
    ("logging.rs", "日志"),
]

PYTHON_PATHS: list[tuple[str, str]] = [
    ("gui_v1.py", "实时引擎主程序"),
    ("tools/realtime_worker.py", "实时 worker 入口"),
    ("tools/worker_protocol.py", "协议默认状态"),
    ("tools/audio_io_process.py", "音频 I/O 进程"),
    ("tools/dsp_fx.py", "DSP 效果链（含 EQ 预设名）"),
    ("tools/separate_worker.py", "人声分离 worker"),
    ("tools/train_worker.py", "训练 worker"),
    ("tools/sts_worker.py", "音频变声 worker"),
    ("tools/infer_cli.py", "离线推理 CLI"),
    ("tools/collect_diagnostics.py", "诊断收集"),
    ("tools/benchmark_realtime.py", "性能基准"),
    ("tools/perf_report.py", "性能报告"),
    ("tools/download_models.py", "模型下载（引擎侧）"),
    ("infer-web.py", "上游 WebUI 入口（高级）"),
]


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def line_starts(text: str) -> list[int]:
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def line_of(starts: list[int], pos: int) -> int:
    # binary search
    lo, hi = 0, len(starts) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if starts[mid] <= pos:
            lo = mid + 1
        else:
            hi = mid - 1
    return hi + 1


def md_escape(s: str) -> str:
    return s.replace("\\n", "<br>").replace("|", "\\|").replace("\n", "<br>")


def looks_like_code(s: str) -> bool:
    return bool(CODE_SMELL.search(s))


def blank_full_line_comments(text: str, prefixes: tuple[str, ...]) -> str:
    """整行以 prefix 开头的注释置空，保留换行以稳住行号。"""
    out = []
    for ln in text.split("\n"):
        st = ln.lstrip()
        if any(st.startswith(p) for p in prefixes):
            out.append("")
        else:
            out.append(ln)
    return "\n".join(out)


def blank_block_comments(text: str) -> str:
    """/* ... */ → 等长换行占位。"""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j < 0:
                out.append("\n" * text[i:].count("\n"))
                break
            out.append("\n" * text[i : j + 2].count("\n"))
            i = j + 2
            continue
        # 批量复制到下一注释
        nxt = text.find("/*", i)
        if nxt < 0:
            out.append(text[i:])
            break
        out.append(text[i:nxt])
        i = nxt
    return "".join(out)


# ---------------------------------------------------------------------------
# 通用字符串扫描（线性，无灾难回溯）
# ---------------------------------------------------------------------------


def scan_quoted_strings(
    text: str,
    *,
    allow_backtick: bool = False,
    allow_triple: bool = False,
    rust_raw: bool = False,
) -> list[tuple[int, str]]:
    """扫描源码中的字符串字面量，返回 (start_pos, content)。

    支持：'...' "..." `...`（可选） 三引号（可选） Rust raw r#"..."#
    """
    results: list[tuple[int, str]] = []
    i, n = 0, len(text)
    quotes = "'\""
    if allow_backtick:
        quotes += "`"

    while i < n:
        ch = text[i]

        # Rust raw: r"..." or r#"..."# or r##"..."##
        if rust_raw and ch in "rR":
            j = i + 1
            hashes = 0
            while j < n and text[j] == "#":
                hashes += 1
                j += 1
            if j < n and text[j] == '"':
                j += 1
                start_content = j
                close = '"' + ("#" * hashes)
                k = text.find(close, j)
                if k < 0:
                    break
                results.append((i, text[start_content:k]))
                i = k + len(close)
                continue

        # Python / generic triple quotes
        if allow_triple and text.startswith(('"""', "'''"), i):
            q = text[i : i + 3]
            j = i + 3
            k = text.find(q, j)
            if k < 0:
                break
            results.append((i, text[j:k]))
            i = k + 3
            continue

        # Also skip Python prefixes: u/r/b/f before quotes
        if ch in "uUrRbBfF" and i + 1 < n:
            # fr""" / rf" etc.
            p = i
            while p < n and text[p] in "uUrRbBfF":
                p += 1
            if allow_triple and p + 2 < n and text[p : p + 3] in ('"""', "'''"):
                q = text[p : p + 3]
                j = p + 3
                k = text.find(q, j)
                if k < 0:
                    break
                results.append((i, text[j:k]))
                i = k + 3
                continue
            if p < n and text[p] in "'\"":
                q = text[p]
                j = p + 1
                buf: list[str] = []
                while j < n:
                    c = text[j]
                    if c == "\\" and j + 1 < n:
                        buf.append(text[j : j + 2])
                        j += 2
                        continue
                    if c == q:
                        results.append((i, "".join(buf)))
                        i = j + 1
                        break
                    if c == "\n" and q != "`":
                        # unclosed single-line string
                        i = j
                        break
                    buf.append(c)
                    j += 1
                else:
                    break
                continue

        if ch in quotes:
            q = ch
            j = i + 1
            buf = []
            while j < n:
                c = text[j]
                if c == "\\" and j + 1 < n:
                    # keep escape sequence text for readability later
                    buf.append(text[j : j + 2])
                    j += 2
                    continue
                if c == q:
                    results.append((i, "".join(buf)))
                    i = j + 1
                    break
                if c == "\n" and q != "`":
                    i = j
                    break
                buf.append(c)
                j += 1
            else:
                break
            continue

        i += 1

    return results


def unescape_basic(s: str) -> str:
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        if s[i] == "\\" and i + 1 < n:
            nxt = s[i + 1]
            mapping = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "\\": "\\"}
            out.append(mapping.get(nxt, s[i : i + 2]))
            i += 2
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def filter_cjk(
    pairs: list[tuple[int, str]], text: str, *, max_len: int = 500
) -> list[tuple[int, str]]:
    starts = line_starts(text)
    found: list[tuple[int, str]] = []
    seen: set[str] = set()
    for pos, raw in pairs:
        s = unescape_basic(raw).strip()
        if not s or not CJK.search(s):
            continue
        if len(s) > max_len:
            s = s[:max_len] + "…"
        if s in seen:
            continue
        seen.add(s)
        found.append((line_of(starts, pos), s))
    found.sort(key=lambda x: x[0])
    return found


# ---------------------------------------------------------------------------
# 各语言抽取
# ---------------------------------------------------------------------------


def extract_frontend(path: Path) -> list[tuple[int, str]]:
    raw = path.read_text(encoding="utf-8")
    text = blank_full_line_comments(blank_block_comments(raw), ("//",))
    pairs = scan_quoted_strings(text, allow_backtick=True)
    rows = filter_cjk(pairs, text)
    # JSX 裸文本
    starts = line_starts(text)
    seen = {s for _, s in rows}
    extra: list[tuple[int, str]] = []
    for m in JSX_TEXT.finditer(text):
        body = " ".join(m.group(1).split())
        if not body or not CJK.search(body) or looks_like_code(body):
            continue
        if body in seen:
            continue
        seen.add(body)
        extra.append((line_of(starts, m.start()), body))
    rows.extend(extra)
    rows.sort(key=lambda x: x[0])
    return rows


def extract_rust(path: Path) -> list[tuple[int, str]]:
    raw = path.read_text(encoding="utf-8")
    text = blank_full_line_comments(blank_block_comments(raw), ("//",))
    pairs = scan_quoted_strings(text, rust_raw=True)
    return filter_cjk(pairs, text)


def extract_python(path: Path) -> list[tuple[int, str]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = blank_full_line_comments(raw, ("#",))
    pairs = scan_quoted_strings(text, allow_triple=True)
    return filter_cjk(pairs, text, max_len=500)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def section_table(
    title: str, rel_display: str, rows: list[tuple[int, str]]
) -> list[str]:
    if not rows:
        return []
    parts = [
        f"## {title}",
        "",
        f"<sub>`{rel_display}`</sub>",
        "",
        "| # | 行号 | 原文（zh-CN） | 备注 / 目标译文 |",
        "|---:|---:|---|---|",
    ]
    for i, (line, s) in enumerate(rows, 1):
        parts.append(f"| {i} | {line} | {md_escape(s)} |  |")
    parts.append("")
    return parts


def write_frontend() -> tuple[str, int, list[str]]:
    src = ROOT / "app" / "src"
    parts: list[str] = [
        "# 前端界面文案（React）",
        "",
        "来源：`app/src/**/*.{ts,tsx}`。注释中的中文已排除。",
        "",
        "带 `${...}` 的是运行时拼接句，翻译时保留占位符。",
        "",
        "由 `scripts/dev/extract_i18n_strings.py` 生成，勿手改后期望持久。",
        "",
        "---",
        "",
    ]
    total = 0
    known = {r for r, _ in FRONTEND_SECTIONS}
    for rel, title in FRONTEND_SECTIONS:
        p = src / rel
        if not p.is_file():
            continue
        rows = extract_frontend(p)
        if not rows:
            continue
        total += len(rows)
        parts.extend(section_table(title, f"app/src/{rel}", rows))

    missed = []
    for p in sorted(src.rglob("*.ts*")):
        if p.suffix not in (".ts", ".tsx"):
            continue
        rel = p.relative_to(src).as_posix()
        if rel in known:
            continue
        if extract_frontend(p):
            missed.append(rel)
    if missed:
        parts.append("## 未登记文件")
        parts.append("")
        parts.append("下列文件含中文但未进分区表，请补 `FRONTEND_SECTIONS`：")
        parts.append("")
        for rel in missed:
            parts.append(f"- `app/src/{rel}`")
        parts.append("")
    return "\n".join(parts) + "\n", total, missed


def write_rust() -> tuple[str, int]:
    src = ROOT / "app" / "src-tauri" / "src"
    parts: list[str] = [
        "# 壳层文案（Rust / Tauri）",
        "",
        "来源：`app/src-tauri/src/**/*.rs`。",
        "",
        "含：托盘菜单、错误返回、下载/补全进度、诊断包说明、命令层提示等。",
        "开发注释已尽量排除；若仍混入日志格式串，翻译时标「仅日志」即可。",
        "",
        "由 `scripts/dev/extract_i18n_strings.py` 生成。",
        "",
        "---",
        "",
    ]
    total = 0
    known = {r for r, _ in RUST_SECTIONS}
    seen_files: set[str] = set()
    for rel, title in RUST_SECTIONS:
        p = src / rel
        if not p.is_file():
            continue
        rows = extract_rust(p)
        seen_files.add(rel)
        if not rows:
            continue
        total += len(rows)
        parts.extend(section_table(title, f"app/src-tauri/src/{rel}", rows))

    for p in sorted(src.rglob("*.rs")):
        rel = p.relative_to(src).as_posix()
        if rel in known or rel in seen_files:
            continue
        rows = extract_rust(p)
        if rows:
            total += len(rows)
            parts.extend(
                section_table(f"其他 · {rel}", f"app/src-tauri/src/{rel}", rows)
            )
    return "\n".join(parts) + "\n", total


def write_python() -> tuple[str, int]:
    parts: list[str] = [
        "# 引擎侧文案（Python）",
        "",
        "来源：实时引擎与工具 worker 入口。",
        "",
        "多数经 `status.json` / 进度事件传到界面，或写入 `User_Data/logs/`。",
        "完整上游 WebUI（Gradio）字符串量极大，此处只收入口文件；",
        "若后续要做引擎全量 i18n，可再扩 `infer/`。",
        "",
        "由 `scripts/dev/extract_i18n_strings.py` 生成。",
        "",
        "---",
        "",
    ]
    total = 0
    for rel, title in PYTHON_PATHS:
        p = ROOT / rel
        if not p.is_file():
            continue
        rows = extract_python(p)
        if not rows:
            continue
        total += len(rows)
        parts.extend(section_table(title, rel, rows))
    return "\n".join(parts) + "\n", total


def write_legacy_frontend_table() -> tuple[str, int]:
    src = ROOT / "app" / "src"
    parts: list[str] = [
        "# 界面文案总表",
        "",
        "软件里用户能看到的每一句中文，按界面分区列在这里。",
        "",
        "> **i18n 主文档已迁到 [`docs/i18n/`](./i18n/README.md)**"
        "（前端 + Rust + 引擎，共分册）。本文件仍由脚本同步生成前端表，便于旧流程。",
        "",
        "**怎么改**：在「改成」那一列写新文案，留空表示不改。",
        "",
        "**注意**：",
        "",
        "- 带 `${...}` 的是拼接出来的句子，`${}` 里的东西是运行时才知道的值"
        "（版本号、文件名、数量），改的时候把它原样留着。",
        "- 同一句话在多处出现只列一次，改一处就是全改。",
        "- 由 `scripts/dev/extract_i18n_strings.py` 生成（亦兼容旧 `extract_ui_copy.py`）。",
        "",
        "---",
        "",
    ]
    n = 0
    for rel, title in FRONTEND_SECTIONS:
        p = src / rel
        if not p.is_file():
            continue
        rows = extract_frontend(p)
        if not rows:
            continue
        n += len(rows)
        parts.append(f"## {title}")
        parts.append("")
        parts.append(f"<sub>`app/src/{rel}`</sub>")
        parts.append("")
        parts.append("| 位置 | 现在的文案 | 改成 |")
        parts.append("|---|---|---|")
        for line, s in rows:
            parts.append(f"| {line} | {md_escape(s)} |  |")
        parts.append("")
    return "\n".join(parts) + "\n", n


def write_readme(fe: int, rs: int, py: int, uniq: int, missed: list[str]) -> str:
    body = f"""# RVC Fabric 文案清单（i18n 准备）

> 本目录是 **软件用户可见文本的完整清单**，供国际化（i18n）对照、翻译与对账。  
> **由脚本生成**，改代码后请重跑：

```bat
python scripts\\dev\\extract_i18n_strings.py
```

## 分册

| 文件 | 范围 | 本次数 |
|---|---|---:|
| [01-frontend.md](./01-frontend.md) | React 界面 `app/src` | {fe} |
| [02-shell-rust.md](./02-shell-rust.md) | Tauri/Rust 壳 `app/src-tauri/src` | {rs} |
| [03-engine-python.md](./03-engine-python.md) | 引擎 / worker 入口（Python） | {py} |
| [04-unique-index.md](./04-unique-index.md) | 去重原文索引（翻译主表） | {uniq} |
| **分册合计（可重复）** | | **{fe + rs + py}** |

兼容旧路径：[界面文案总表.md](../界面文案总表.md)（仅前端，格式含「改成」列）。

## 分层说明

```
用户眼睛看到的字
├── 前端 React          按钮、页标题、设置问号、商店、工具窗……
├── Rust 壳             托盘菜单、Err 提示、下载进度、诊断包、命令返回……
└── Python 引擎         status.json 状态句、worker 进度、部分 EQ 预设名……
```

**暂不纳入本目录的：**

- `i18n/locale/*.json` —— 上游 RVC WebUI（Gradio）旧 i18n，与现壳无关
- `CNB-GIT-RELEASE/catalog-src` —— 运营清单（音色名、更新日志）走内容仓
- 代码注释、开发白皮书

## 后续 i18n 建议（尚未实施）

1. 前端：抽 `app/src/i18n/` 或 `react-i18next`，key 按页面命名
2. Rust：`rust-i18n` / 自建 JSON，错误与托盘走同一套 locale
3. Python worker：status `message` 用消息码，由壳层按 locale 渲染（避免 Runtime 内塞多语言包）
4. 专有名词：`glossary.ts` 单独词条表，各语言统一释义

## 维护

- 新增界面文件含中文：把路径补进 `extract_i18n_strings.py` 的 `FRONTEND_SECTIONS`
- `--check`：只统计，不写盘

```bat
python scripts\\dev\\extract_i18n_strings.py --check
```
"""
    if missed:
        body += (
            "\n## 未登记前端文件\n\n"
            + "\n".join(f"- `app/src/{r}`" for r in missed)
            + "\n"
        )
    return body


def collect_all() -> list[tuple[str, str, int, str]]:
    rows: list[tuple[str, str, int, str]] = []
    src = ROOT / "app" / "src"
    for rel, _ in FRONTEND_SECTIONS:
        p = src / rel
        if not p.is_file():
            continue
        for line, s in extract_frontend(p):
            rows.append(("frontend", f"app/src/{rel}", line, s))
    # also unlisted frontend files
    known = {r for r, _ in FRONTEND_SECTIONS}
    for p in sorted(src.rglob("*.ts*")):
        if p.suffix not in (".ts", ".tsx"):
            continue
        rel = p.relative_to(src).as_posix()
        if rel in known:
            continue
        for line, s in extract_frontend(p):
            rows.append(("frontend", f"app/src/{rel}", line, s))

    rsrc = ROOT / "app" / "src-tauri" / "src"
    for p in sorted(rsrc.rglob("*.rs")):
        rel = p.relative_to(rsrc).as_posix()
        for line, s in extract_rust(p):
            rows.append(("rust", f"app/src-tauri/src/{rel}", line, s))

    for rel, _ in PYTHON_PATHS:
        p = ROOT / rel
        if not p.is_file():
            continue
        for line, s in extract_python(p):
            rows.append(("python", rel, line, s))
    return rows


def write_unique_index(all_rows: list[tuple[str, str, int, str]]) -> str:
    by_text: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    for layer, file, line, text in all_rows:
        by_text[text].append((layer, file, line))

    parts = [
        "# 去重原文索引",
        "",
        "同一句中文只出现一次；「出处」列出所有出现位置。",
        "翻译时可按本表建 key，避免同一句多种译法。",
        "",
        f"去重后共 **{len(by_text)}** 条（含前端 / Rust / 引擎）。",
        "",
        "| # | 原文（zh-CN） | 出现次数 | 出处（首条） |",
        "|---:|---|---:|---|",
    ]
    items = sorted(by_text.items(), key=lambda x: (-len(x[1]), x[0]))
    for i, (text, locs) in enumerate(items, 1):
        layer, file, line = locs[0]
        src = f"{layer} `{file}:{line}`"
        if len(locs) > 1:
            src += f" 等 {len(locs)} 处"
        parts.append(f"| {i} | {md_escape(text)} | {len(locs)} | {src} |")
    parts.append("")
    return "\n".join(parts) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="只报告数量，不写文件")
    args = ap.parse_args()

    fe_md, fe_n, missed = write_frontend()
    rs_md, rs_n = write_rust()
    py_md, py_n = write_python()
    all_rows = collect_all()
    uniq = len({r[3] for r in all_rows})
    index_md = write_unique_index(all_rows)
    readme = write_readme(fe_n, rs_n, py_n, uniq, missed)
    legacy, leg_n = write_legacy_frontend_table()

    print(
        f"前端 {fe_n} 条 · Rust {rs_n} 条 · Python {py_n} 条 · "
        f"去重 {uniq} 条 · 兼容表 {leg_n} 条"
    )
    if missed:
        print("未登记前端文件:", ", ".join(missed))

    if args.check:
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")
    (OUT_DIR / "01-frontend.md").write_text(fe_md, encoding="utf-8")
    (OUT_DIR / "02-shell-rust.md").write_text(rs_md, encoding="utf-8")
    (OUT_DIR / "03-engine-python.md").write_text(py_md, encoding="utf-8")
    (OUT_DIR / "04-unique-index.md").write_text(index_md, encoding="utf-8")
    LEGACY_FRONTEND_TABLE.write_text(legacy, encoding="utf-8")
    print(f"已写入 {OUT_DIR.relative_to(ROOT)}/ 与 docs/界面文案总表.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
