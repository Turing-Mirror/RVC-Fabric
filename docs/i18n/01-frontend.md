# 前端界面文案（React）

来源：`app/src/**/*.{ts,tsx}`。注释中的中文已排除。

带 `${...}` 的是运行时拼接句，翻译时保留占位符。

由 `scripts/dev/extract_i18n_strings.py` 生成，勿手改后期望持久。

---

## 首页

<sub>`app/src/pages/HomePage.tsx`</sub>

| # | 行号 | 原文（zh-CN） | 备注 / 目标译文 |
|---:|---:|---|---|
| 1 | 120 | 音色切换失败：${String(e)} |  |

## 社区音色（广场内嵌）

<sub>`app/src/components/StoreSection.tsx`</sub>

| # | 行号 | 原文（zh-CN） | 备注 / 目标译文 |
|---:|---:|---|---|
| 1 | 124 | ${p.message \|\| p.phase \|\| "下载中"} ${<br>          p.percent != null ? |  |
| 2 | 260 | 确定删除已下载的音色文件吗？<br><br>${s?.file \|\| v.name}<br><br>删除后如需使用需重新下载。 |  |

## 广场

<sub>`app/src/pages/PlazaPage.tsx`</sub>

| # | 行号 | 原文（zh-CN） | 备注 / 目标译文 |
|---:|---:|---|---|
| 1 | 96 | 第 ${cur + 1} / ${total} 页 |  |

## 说明页

<sub>`app/src/pages/HelpPage.tsx`</sub>

| # | 行号 | 原文（zh-CN） | 备注 / 目标译文 |
|---:|---:|---|---|
| 1 | 186 | 失败：${String(e)} |  |

## 其他页

<sub>`app/src/pages/MorePage.tsx`</sub>

| # | 行号 | 原文（zh-CN） | 备注 / 目标译文 |
|---:|---:|---|---|
| 1 | 70 | 保存失败：${String(e)} |  |
| 2 | 91 | 启动失败：${String(e)} |  |
| 3 | 100 | ${label}完成：${r?.path ?? ""}${note} |  |
| 4 | 102 | ${label}失败：${String(e)} |  |
| 5 | 126 | 生成诊断包完成：${r?.path ?? ""}${note} |  |
| 6 | 128 | 生成诊断包失败：${String(e)} |  |

## 独立工具窗口 · 外壳

<sub>`app/src/components/ToolWindow.tsx`</sub>

| # | 行号 | 原文（zh-CN） | 备注 / 目标译文 |
|---:|---:|---|---|
| 1 | 37 | 使用「${TITLES[kind]}」前，需要先下载引擎资源（hubert / rmvpe / ffmpeg，约 720 MB）。下载完成后即可打开工具。 |  |

## 人声分离窗口

<sub>`app/src/components/SeparatePanel.tsx`</sub>

| # | 行号 | 原文（zh-CN） | 备注 / 目标译文 |
|---:|---:|---|---|
| 1 | 98 | 完成，输出 ${r.files?.length ?? 0} 个文件 |  |

## 训练音色窗口

<sub>`app/src/components/TrainPanel.tsx`</sub>

| # | 行号 | 原文（zh-CN） | 备注 / 目标译文 |
|---:|---:|---|---|
| 1 | 153 | 训练完成：${r.weights ?? ""} |  |

## 语音转换 / 合成窗口

<sub>`app/src/components/TtsPanel.tsx`</sub>

| # | 行号 | 原文（zh-CN） | 备注 / 目标译文 |
|---:|---:|---|---|
| 1 | 131 | 引擎资源未补全（缺 ${(st.engine_core_missing \|\| []).join("、") \|\| "hubert/rmvpe"}）。请先在主界面完成引擎资源下载。 |  |
| 2 | 153 | 完成 ${r.files?.length ?? 0} 个文件${r.output ? |  |
| 3 | 362 | 合成完成：${r.file ?? ""} |  |

## 下载模型弹窗

<sub>`app/src/components/ExtrasDialog.tsx`</sub>

| # | 行号 | 原文（zh-CN） | 备注 / 目标译文 |
|---:|---:|---|---|
| 1 | 309 | 当前缺少：${assets.engine_core_missing.join("、")} |  |

## 首次运行 · 补全运行环境

<sub>`app/src/components/ProvisionGate.tsx`</sub>

| # | 行号 | 原文（zh-CN） | 备注 / 目标译文 |
|---:|---:|---|---|
| 1 | 41 | ${m} 分 ${s % 60} 秒 |  |
| 2 | 42 | ${Math.floor(m / 60)} 小时 ${m % 60} 分 |  |

## 全局提示与对话框

<sub>`app/src/App.tsx`</sub>

| # | 行号 | 原文（zh-CN） | 备注 / 目标译文 |
|---:|---:|---|---|
| 1 | 99 | 当前版本 ${String(r.local)}，需先更新至 ${String(<br>          r.min_app_version,<br>        )} 才能继续 |  |
| 2 | 108 | 已是最新版本 ${String(r.local)}（${clockNow()} 检查） |  |
| 3 | 112 | 发现新版本 ${String(r.remote)}，当前 ${String(r.local)} |  |
| 4 | 121 | 正在下载程序更新 ${String(r.remote)}… |  |
| 5 | 125 | 已更新至 ${String(b.version ?? r.remote)}，重启程序后生效 |  |
| 6 | 130 | 正在下载界面更新 ${String(r.remote)}… |  |
| 7 | 135 | 已更新至 ${String(r.remote)}，重启程序后生效 |  |
| 8 | 147 | 检查更新失败：${String(e)} |  |
| 9 | 193 | 更新失败：${String(e)} |  |
| 10 | 807 | 当前版本 ${updateOffer.local}。${<br>                updateOffer.notes \|\|<br>                "更新会在后台下载，不影响变声使用；下载完成后重启软件即可生效。"<br>              } |  |

