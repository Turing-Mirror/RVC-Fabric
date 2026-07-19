# 本对话全量改动总结（2026-07-20）

> **用途**：记录本协作对话中完成的进度梳理、功能开发与体验修复，供交接与回看。  
> **分支**：`tm-release`（对话结束时相对 `org/tm-release` 约 **ahead 29**）  
> **产品**：Turing Mirror 变声器（RVC 底座 + 内容库壳 launcher + 无窗 `realtime_worker`）  
> **相关文档**：`docs/CONTEXT_HANDOFF.md`（总交接）、`docs/SESSION_CHANGELOG_2026-07-19.md`（前一会话）、`docs/UI-AESTHETIC-DESIGN.md`（壳层美学）

---

## 0. 一句话总览

在已成型的「单窗口实时变声」产品路径上，本对话完成了：

1. **进度同步**（读文档 + 代码结构，对齐当前架构与缺口）  
2. **可自定义快捷键**（切音色 / 启停 / 音高；可选全局热键）  
3. **「监听自己」修复**（虚拟设备误选 + 更稳的第二路播放）  
4. **底栏常用控制 + 按音色保存参数**（变声/原声、音高/共鸣/阈值）  
5. **窗口与底栏布局加宽**；**SoftSlider**（Pillow 抗锯齿）与防抖动  
6. **音色参数撤销 / 重做 / 恢复默认**（Ctrl+Z / Y / 0）  
7. **设置页可读性**（对比度、`?` 徽章、去掉与悬停重复的小字）  
8. **关闭卡顿修复**（快速退出 worker，不再 UI 线程傻等十几秒）

---

## 1. 对话起点：项目上下文（当时结论）

### 1.1 产品架构（未改方向）

```text
变声器.exe / launcher/main_app.py
  → User_Data/app_config.json + configs/inuse/config.json
  → User_Data/runtime_control/*.json（文件 IPC）
  → Runtime\pythonw + tools/realtime_worker.py
  → gui_v1 (TM_REALTIME_WORKER=1) + rtrvc + AudioIoProcess
```

### 1.2 当时已成型能力（承接 07-19 及更早）

| 能力 | 说明 |
|------|------|
| 单窗口日常变声 | 无窗 worker，不必开原版 RVC 窗 |
| 设置页 | 设备 / 音高 / Index / 性能 / DSP 效果链 |
| 多包 GPU | nvidia / amd / nvidia50 + package_meta |
| 自动化测试 | `tests/test_*.py` + `scripts/run_tests.bat` |
| 在线更新骨架 | `launcher/online/` + 更新页（本对话期间亦有相关提交） |

### 1.3 本对话用户诉求演进

| 顺序 | 诉求 |
|------|------|
| 1 | 完整看代码与文档，同步进度 → 做快捷键（如快速切音色） |
| 2 | 监听自己开了但听不到变声 |
| 3 | 底栏放常用功能；热更新参数；**按音色单独保存** |
| 4 | 更新页滚不动；默认窗口太挤 |
| 5 | 再加宽；底栏布局参考 Schale / LyricsKara；滑条样式 |
| 6 | 底栏字被裁切；滑条锯齿丑 |
| 7 | 滑条拖动底栏抖动；要撤销 / 恢复默认 |
| 8 | 设置小字不显眼；对照两仓库调对比度 |
| 9 | 小字与悬停重复 → 去掉小字、问号更显眼 |
| 10 | 关闭软件总卡一下 |
| 11 | **总结本对话并写成文档**（本文） |

---

## 2. 提交时间线（本对话相关，按主题）

| Commit | 主题 |
|--------|------|
| `f8b7292` | 可自定义快捷键（切音色 / F5 启停 / 音高等） |
| `a67a878` | 修复「监听自己」：虚拟设备误选 + 回调队列播放 |
| `58356a4` | 底栏模式/音高/阈值 + **按音色** config.json 参数 |
| `72146a6` | 更新页滚轮 + 默认窗口加大 |
| `e384e32` | 更宽默认窗 + 播放器式底栏分区 + SoftSlider |
| `930b532` | 底栏文字裁切 + Pillow 2× 抗锯齿滑条 |
| `5089b9d` | 滑条拖动不抖底栏；撤销/重做/默认 |
| `73fdaa2` | 设置标签/说明对比度（TM_HELP 等） |
| `e6c4106` | 去掉与 `?` 重复的说明小字；问号徽章 |
| `29035a2` | **快速退出**：关闭不再长时间阻塞 UI |

（同分支上另有在线更新 / 帮助页等相邻提交，见 `git log`；本文以本对话明确落地项为主。）

---

## 3. 功能与修复分项

### 3.1 可自定义快捷键

| 项 | 内容 |
|----|------|
| 模块 | `launcher/hotkeys.py` |
| 配置 | `app_config.json` → `hotkeys` / `global_hotkeys` / `hotkey_restart_on_model_switch` |
| 默认 | ←/→ 切音色，F5 启停，Ctrl+↑↓ 音高，Ctrl+Alt+1–9 直选，F1 说明，Ctrl+B 变声/原声 |
| 设置页 | 录制 / 清空 / 恢复默认；可选 **全局热键**（纯方向键不会注册为全局） |
| 行为 | 变声中切音色默认自动重启引擎加载新模型 |

### 3.2 「监听自己」修复

| 项 | 内容 |
|----|------|
| 现象 | 开了监听但耳机无声 |
| 根因 | 监听设备落到 **Steam Streaming Speakers** 等虚拟端；`write` 失败被静默吞掉 |
| 修复 | 自动纠正虚拟目标 → 真实耳机；callback + 队列；设备 native 采样率；UI 警告 |
| 代码 | 主要 `gui_v1.py` 监听流；`main_app` 设备优选 / 提示 |

**正确接线（不变）**：主输出 = CABLE Input；监听 = 真耳机/音箱。

### 3.3 底栏常用控制 + 按音色参数

| 项 | 内容 |
|----|------|
| 底栏分区 | NOW PLAYING \| MODE（输出变声 / 原声旁路）\| 音高·共鸣·阈值 \| 启停·状态 \| EDIT（撤销等） |
| 热更新 | 模式 / 音高 / 共鸣 / 阈值运行中可推送 worker |
| 按音色保存 | `User_Data/models/<名>/config.json`：`pitch` / `formant` / `threhold` / `index_rate` / `rms_mix_rate` / `f0method` |
| 模块 | `launcher/catalog.py`：`save_model_voice_params` / `get_model_voice_params` |

### 3.4 布局与 SoftSlider

| 项 | 内容 |
|----|------|
| 默认窗口 | 约 **1320×900**（主题常量 `DEFAULT_WIN_*`）；最小约 1100×740 |
| 底栏高度 | `BOTTOM_HEIGHT` ≈ **168**，避免字被裁切 |
| SoftSlider | Pillow 2× 超采样圆角轨 + 拖柄；固定高度，避免拖动 reflow |
| 防抖 | 拖动中不整栏 `_sync_bottom`；数值标签固定列宽 |

### 3.5 撤销 / 重做 / 默认

| 操作 | 快捷键 | 说明 |
|------|--------|------|
| 撤销 | Ctrl+Z | 音色参数（音高/共鸣/阈值等快照） |
| 重做 | Ctrl+Y | |
| 恢复默认 | Ctrl+0 | 音高 0、共鸣 0、阈值 -60 |
| 底栏 | EDIT 区按钮 | 与快捷键一致 |

滑条按下时写入撤销栈；切换音色清空栈。

### 3.6 设置页文案与 `?`

| 项 | 内容 |
|----|------|
| 对比度 | `TM_INK_MUTED` 加深；新增 `TM_HELP`；`TM_META` 略加深（见 `theme.py` / UI 文档） |
| 去重 | **去掉**与悬停重复的 `tip_line` 说明小字 |
| 问号 | `help_mark`：青绿底 + 描边徽章，悬停仍用 `HoverTip` |
| 仍保留 | 状态类短句（监听当前设备、index 是否绑定、设备区接线一句） |

### 3.7 更新页滚轮

| 项 | 内容 |
|----|------|
| 问题 | `docs/reference-screenshots/error4.png`：更新页滚轮无效 |
| 修复 | `store_page` 递归绑定滚轮 + 刷新后 rebind + reflow |

### 3.8 关闭卡顿

| 项 | 内容 |
|----|------|
| 原因 | UI 线程同步 `stop_vc`(最长 ~8s) + `quit_worker`(~8s) + PowerShell 全量扫进程 |
| 修复 | `shutdown_workers_for_exit`：先 `withdraw` 窗口 → 快写配置 → 短软等 + 杀已知 PID + **短超时**孤儿扫描（约 1.2s 量级） |
| 代码 | `realtime_client.shutdown_workers_for_exit`；`main_app._on_close` |

---

## 4. 关键路径（本对话新增/加重）

| 路径 | 职责 |
|------|------|
| `launcher/hotkeys.py` | 快捷键定义、解析、全局热键 |
| `launcher/catalog.py` | 按音色读写 voice 参数 |
| `launcher/ui/widgets.py` | `SoftSlider` / `ParamTile` |
| `launcher/ui/store_page.py` | 更新页滚动 |
| `launcher/theme.py` | 窗口尺寸、底栏高度、对比度 token |
| `launcher/realtime_client.py` | `shutdown_workers_for_exit`、孤儿扫描超时 |
| `gui_v1.py` | 监听流打开/写入/设备纠正 |
| `tests/test_hotkeys.py` | 快捷键单测 |
| `tests/test_catalog_theme.py` | 目录 + 主题对比度 |

---

## 5. 配置与数据

### 5.1 `User_Data/app_config.json`（节选）

- `hotkeys` / `global_hotkeys` / `hotkey_restart_on_model_switch`  
- `monitor_enabled` / `monitor_device`  
- `function`：`vc` | `im`  
- 全局默认 pitch/formant 等（会与当前音色同步）

### 5.2 音色侧 `User_Data/models/<名>/config.json`

- 可选：`pitch` / `formant` / `threhold` / `index_rate` / `rms_mix_rate` / `f0method`  
- 切换音色时加载；调节时写回  

---

## 6. 验收清单（用户向）

1. 选音色 → 开变声 → 耳机/游戏接线正确  
2. **监听自己**：监听设备 = 真耳机（非 Steam/CABLE）  
3. 底栏：输出变声 / 原声旁路；拖音高不抖底栏；Ctrl+Z 可撤销  
4. 设置：`?` 悬停有说明，下方不再重复长文  
5. 更新页：卡片上滚轮可滚  
6. 关闭窗口：应较快消失，不应再「卡死」十几秒  

开发跑 UI：`Runtime\pythonw.exe launcher\main_app.py`（或现有 dev 入口）。  
**发行包**需重打 exe 才能带上 launcher 改动。

---

## 7. 参考与约束

- UI 方法借鉴：**Schale-Library**（库感卡片/分区）、**LyricsKara**（now-playing / meta 字阶）— **不抄 BA 蓝霓虹 / RVCMAX 粉紫**  
- Agents：改完 commit；文档只放 `docs/`；UTF-8；PowerShell  

---

## 8. 待办 / 下一棒（对话结束时）

| 优先级 | 项 |
|--------|-----|
| 高 | 按 variant 打全量 exe 并实机验收（含新底栏 / 监听 / 快捷键 / 关闭速度） |
| 中 | 全局热键与游戏按键冲突时的默认组合再打磨 |
| 中 | 关闭后若极少数机器仍有孤儿进程，可再收紧 `scan_timeout` 或改用更快枚举 |
| 低 | 帮助页 / 在线更新与正式清单 URL 运营配置 |

---

## 9. 新对话建议开场

```text
工作区：L:\My project\Grok
先读：docs/CONTEXT_HANDOFF.md + docs/SESSION_CHANGELOG_2026-07-20.md
分支：tm-release
近况：快捷键、监听修复、底栏+按音色参数、SoftSlider、撤销、设置?徽章、快速退出
约束：不改未要求的 UI 气质；PowerShell；改完 commit
```

---

## 10. 一句话状态

**日常变声主路径 + 底栏热控 + 按音色参数 + 快捷键 + 监听自听已可用；关闭与更新页滚动/设置可读性已修。**  
下一步以 **分显卡全量包实机验收** 为主。
