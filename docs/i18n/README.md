# RVC Fabric 文案与 i18n

## 分工（重要）

| 角色 | 读什么 | 产出什么 |
|---|---|---|
| **翻译 AI** | **[`给翻译AI.md`](./给翻译AI.md)** + `app/i18n/locales/zh-CN.json` | 完整目标语言 JSON（如 `en-US.json`） |
| **开发 AI / 工程** | 代码 + 本文 + `app/i18n/README.md` | 接入 `t()`、注册语言、修 bug、合并 JSON |

翻译 **不要** 改 `app/src`、Rust、脚本；只交语言包。

---

## 运行时语言包（真相）

| 文件 | 说明 |
|---|---|
| [`app/i18n/locales/zh-CN.json`](../../app/i18n/locales/zh-CN.json) | 中文源（含语义 key + `s.<hash>` 批量串） |
| [`app/i18n/locales/en-US.json`](../../app/i18n/locales/en-US.json) | 英语（语义段已有样例；`s` 区待译） |
| 安装目录 | `shell-i18n/locales/`（与引擎 Gradio `i18n/` 无关） |

用户切换：设置 → 外观 → 界面语言（`ui_locale`）。

---

## 开发用：文案抽取表（非翻译入口）

改代码后重跑：

```bat
python scripts\dev\extract_i18n_strings.py
python scripts\dev\build_i18n_catalog.py
```

| 文件 | 用途 |
|---|---|
| [01-frontend.md](./01-frontend.md) | 前端仍硬编码的中文（应对账） |
| [02-shell-rust.md](./02-shell-rust.md) | Rust 侧残留 |
| [03-engine-python.md](./03-engine-python.md) | 引擎入口 |
| [04-unique-index.md](./04-unique-index.md) | 去重索引 |
| [keys-draft.md](./keys-draft.md) / [.json](./keys-draft.json) | 未语义化草案 |

兼容旧表：[界面文案总表.md](../界面文案总表.md)。

---

## 工程维护（开发）

```bat
python scripts\dev\migrate_i18n_all.py --dry-run
python scripts\dev\fix_i18n_migrate.py
```

新语言注册：见 `app/i18n/README.md`（types + Rust `supported` + 资源目录）。
