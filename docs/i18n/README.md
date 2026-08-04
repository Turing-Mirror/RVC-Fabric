# RVC Fabric 文案清单（i18n 准备）

> 本目录是 **软件用户可见文本的完整清单**，供国际化（i18n）对照、翻译与对账。  
> **由脚本生成**，改代码后请重跑：

```bat
python scripts\dev\extract_i18n_strings.py
```

## 分册

| 文件 | 范围 | 本次数 |
|---|---|---:|
| [01-frontend.md](./01-frontend.md) | React 界面 `app/src` | 639 |
| [02-shell-rust.md](./02-shell-rust.md) | Tauri/Rust 壳 `app/src-tauri/src` | 400 |
| [03-engine-python.md](./03-engine-python.md) | 引擎 / worker 入口（Python） | 264 |
| [04-unique-index.md](./04-unique-index.md) | 去重原文索引（翻译主表） | 1166 |
| **分册合计（可重复）** | | **1303** |

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
python scripts\dev\extract_i18n_strings.py --check
```
