# Turing Mirror 变声器 — 完整上下文交接

> **用途**  
> 1. 新开 Grok / 协作者对话：先读本文再动代码。  
> 2. 在 GitHub 上看仓库的人：了解产品定位、架构、已做事项与坑。  
> **生成 / 最后大更新**：2026-07-19（本对话全量整理）  
> **工作区**：`L:\My project\Grok`  
> **当前分支**：`tm-release`  
> **组织仓库**：https://github.com/Turing-Mirror/TuringMirror-Voice （private，`org` remote）  
> **个人镜像**：https://github.com/xiaoyanjiee/TuringMirror-Voice （`origin`）

---

## 0. 30 秒读懂

| 项 | 内容 |
|----|------|
| 产品 | **Turing Mirror 变声器**（图灵之镜网站配套本地变声器） |
| 底座 | 官方 RVC WebUI + 实时 `gui_v1.py`，**不重写算法** |
| 体验目标 | 像 B 站 RVCMAX：解压 → 启动器 → 桌面图标 → 开黑变声；日常**不**靠 bat |
| UI | 内容库壳 + 舞台焦点（`docs/UI-AESTHETIC-DESIGN.md` §0）；`launcher/theme.py` + `launcher/ui/`；禁止霓虹/RVCMAX 粉紫/照抄 BA 蓝 |
| 参考包 | `RVCMAX/RVCMAX_Nvidia_xiaoyuan`（布局/Runtime，不抄皮） |
| 日常主路径 | 主界面选音色 → 设置设备 → **开启变声**（后台无窗 worker，**不必开原版 RVC 窗**） |
| 发行 | 全量包在 `dist/`（gitignore）；**Git 含什么见 `docs/仓库内容说明.md`** |

---

## 1. 产品定位与非目标

### 要做

- 本地实时变声（游戏 / QQ / Discord + VB-Cable）
- 白无垢壳：`launcher/`（bootstrap + main_app）
- 用户数据在 `User_Data/models`，预置音色目录结构对齐 RVCMAX
- 高级：原版实时面板、训练/翻唱 WebUI

### 不要做

- 不做第二套 RVCMAX 粉紫 Electron 壳
- 不擅自改白无垢皮肤
- 不把 `RVCMAX/`、`Runtime/`、`dist/` 当源码主树提交
- 中途不过度加合规脚手架（Agents 约定）

---

## 2. 架构（必懂）

```
┌─────────────────────────────────────┐
│  变声器.exe / launcher/main_app.py   │  白无垢 UI：首页/模型/设置/其他
│  设置写 User_Data/app_config.json   │
│  + 同步 configs/inuse/config.json   │
└──────────────┬──────────────────────┘
               │ JSON 命令：User_Data/runtime_control/
               │ command.json / status.json / worker.pid
               ▼
┌─────────────────────────────────────┐
│  Runtime\pythonw + tools/realtime_  │
│  worker.py → gui_v1 (TM_REALTIME_   │
│  WORKER=1 无窗模式)                 │
│  rtrvc + AudioIoProcess             │
└─────────────────────────────────────┘

可选：原版 gui_v1 有窗面板（高级调试）
可选：infer-web.py WebUI（训练/翻唱）
```

**为什么不能把 torch 塞进 变声器.exe？**  
exe 用主机 **Python 3.13** PyInstaller 打包；推理必须在 **Runtime 3.9 + CUDA/DML** 里跑。直接 Popen 易被 `_MEIPASS` 污染 → 用 VBS / 清洗 env。

### 关键路径

| 路径 | 职责 |
|------|------|
| `launcher/main_app.py` | 日常 UI、启停变声、设置、状态徽章 |
| `launcher/theme.py` / `launcher/ui/` | 壳层 token 与可复用控件（封面卡等） |
| `launcher/online/` + `ui/store_page.py` | 在线更新 GUI / 音色库（SharePoint·GitHub 直链）；完整包外链 QQ/SharePoint |
| `launcher/bootstrap.py` | 首次：快捷方式、VBCABLE、环境 |
| `launcher/realtime_client.py` | 启停 worker、单实例、清孤儿进程 |
| `launcher/realtime_protocol.py` | 文件 IPC |
| `launcher/gpu_backend.py` | CUDA / DirectML 检测与偏好 |
| `launcher/package_meta.py` | 发行包变体标记（nvidia/amd/50） |
| `launcher/catalog.py` | `User_Data/models` 扫描、index 绑定 |
| `launcher/config_store.py` | app 配置 + 同步 inuse |
| `tools/realtime_worker.py` | 无窗入口（runpy gui_v1） |
| `gui_v1.py` | 实时引擎；worker 模式无 FreeSimpleGUI 窗 |
| `infer/lib/rtrvc.py` | 实时推理；无 index 不崩 |
| `configs/config.py` | 设备：CUDA / `--dml` DirectML / CPU |
| `scripts/build_release.py` | 一键发行包，`--variant nvidia\|amd\|nvidia50` |

---

## 3. 本对话完成的功能与修复（按主题）

### 3.1 单窗口日常变声（替代「必须开两个窗」）

- **需求**：把原版实时 GUI 的参数/设备/启停搬进主界面，变声仍用 RVC 引擎；保留原版面板入口。
- **实现**：无窗 `realtime_worker` + 文件协议；设置页补齐阈值/Index/性能/设备等。
- **热更新**：pitch、formant、index_rate、降噪开关、模式等（对齐 gui_v1 event_handler）。
- **冷参数**：设备、block_time、换模型/index 等需停再开。

### 3.2 停止变声 / 多进程灾难（严重 bug）

**现象**：停不干净、叠多个 worker、任务管理器一堆 `pythonw`、循环监听音频。

**原因**：

1. VBS 父进程秒退 → 客户端以为 worker 死了 → 反复拉起。  
2. `update_devices` 只清 `flag_vc`，**不拆** `AudioIoProcess` → 声卡仍被占。  
3. 主进程崩溃后 harvest 子进程成孤儿。

**修复**：`stop_stream` 始终 teardown；`worker.pid` 单实例；停止失败则 `taskkill /T`；紧急「强制结束变声引擎」；清孤儿时**不杀** `main_app`。

### 3.3 设置与音色

- **Index**：设置页可浏览/扫描/清除 `.index`，写入音色目录 `config.json`（特征检索库，不是训练底模）。  
- **模式**：「输出变声」= 正常变声；「输入监听」= 原麦旁路测接线；`?` 悬停说明。  
- **边变声边听自己**：主输出仍给 CABLE；可选**监听设备=耳机**，第二路 `OutputStream` 放变声结果。

### 3.4 延迟显示 `114514542ms`

- 原版 `AudioIoProcess.latency` 初值是梗数字 **114514 秒**，未测到真实声卡延迟就被读出。  
- 已改为 `-1` 未就绪、等待后刷新、界面过滤离谱值；状态徽章「变声中」更显眼（仍白无垢：素墨+淡面，无霓虹）。

### 3.5 空配置 JSONDecodeError（error3）

- `configs/inuse/config.json` 被中断写入变成 **0 字节** → 再启动解析失败。  
- 原子写 + 读空自动修复；worker 用 `pythonw` 避免黑控制台。

### 3.6 显卡 / 官方 A 卡 I 卡（重要澄清）

官方 README「A 卡 I 卡加速支持」**不是只加 `--dml` 参数**：

1. **单独环境**：`requirements-dml.txt` 或 HF **`RVC1006AMD_Intel.7z`**（torch-directml、onnxruntime-directml 等）  
2. **再**启动 `--dml` / `go-*-dml.bat`  
3. 另需 **rmvpe.onnx**（DML 音高）

Linux AMD 是 ROCm，不是 Windows DML。

**本产品目标**（与官方一致）：

| 发行目录 | variant | Runtime |
|----------|---------|---------|
| `TuringMirror_Voice_Nvidia` | nvidia | N 卡 CUDA |
| `TuringMirror_Voice_AMD` | amd | A/I DirectML（待 RVCMAX A 卡包） |
| `TuringMirror_Voice_Nvidia50` | nvidia50 | 50 系 CUDA（待 RVCMAX 50 包） |

- 构建：`python scripts/build_release.py --clean --variant nvidia|amd|nvidia50`  
- `package_meta.json` 标记变体与默认加速  
- 包内「加速后端」下拉仅微调；**禁止混用各包 Runtime**  
- 详见 `docs/发行包-显卡分版.md`

**当前本机参考**：仅有 `RVCMAX/RVCMAX_Nvidia_xiaoyuan`。A 卡 / 50 系包用户表示会下载，到位后再打对应全量包。

### 3.7 构建与磁盘

- C 盘紧：打包时 **`TEMP/TMP` → `L:\My project\Grok\TEMP_BUILD`**  
- 全量包路径示例：`L:\My project\Grok\dist\TuringMirror_Voice\`（或 `_Nvidia` 等）  
- `--skip-runtime` 仅增量调试用；正式应用 **全量** 且不 skip  
- 曾中断的 clean 会导致半成品；完整全量约 6 分钟（Runtime ~5.6GB）

### 3.8 Git / GitHub

| Remote | URL |
|--------|-----|
| `org` | https://github.com/Turing-Mirror/TuringMirror-Voice.git （组织，主推） |
| `origin` | https://github.com/xiaoyanjiee/TuringMirror-Voice.git |
| `upstream` | 官方 RVC WebUI |

- 分支：`tm-release`（组织库默认分支）  
- **Git 含什么 / 不含什么**：见 `docs/仓库内容说明.md`（无大体积 Runtime/发行包/权重进库）  
- 单文件 GitHub 硬限 100MB；当前已跟踪文件均远小于限制，无需 LFS  

---

## 4. 用户动线（验收用）

1. 解压发行包（英文路径优先）  
2. **启动器.exe** → 快捷方式 + 装 VB-Cable  
3. **变声器.exe** → 等「正在连接变声引擎」（琥珀）→ 引擎待命  
4. 设置：输入=真麦，输出=CABLE Input；可选监听耳机 +「变声时监听自己」  
5. 选音色 → **开启变声**（首次 20–40s，无 RVC 蓝窗）  
6. 游戏麦克风=CABLE Output  
7. 停止应真停；异常用「其他 → 强制结束变声引擎」

---

## 5. 虚拟声卡接线（客服/用户）

| 位置 | 设备 |
|------|------|
| 软件输入 | 真实麦克风 |
| 软件输出 | **CABLE Input** |
| 软件监听（可选） | 耳机/音箱（非 CABLE） |
| 游戏/QQ 麦克风 | **CABLE Output** |
| Windows 默认播放 | 耳机（不要 CABLE） |

---

## 6. 文档索引

| 文档 | 内容 |
|------|------|
| `docs/仓库内容说明.md` | **Git 含什么 / 不含什么**（clone ≠ 完整安装包） |
| `docs/UI-AESTHETIC-DESIGN.md` | 白无垢硬约束 |
| `docs/项目结构.md` | 目录角色 |
| `docs/发布布局与角色分工.md` | 发布岗位分工 |
| `docs/发行版打包与用户使用.md` | 打包命令与用户路径 |
| `docs/发行包-显卡分版.md` | N/A/50 多包方案与官方真相 |
| `docs/大众版使用说明.md` | 面向用户 |
| `docs/RVC_ANALYSIS.md` | 早期引擎/安全分析 |
| `docs/reference-screenshots/` | 问题截图（error/issue） |
| `docs/CONTEXT_HANDOFF.md` | **本文** |
| `docs/在线更新与音色库.md` | catalog JSON、直链、GUI zip 白名单 |

---

## 7. 约束（Agents / 用户偏好）

- 无 emoji（除非要求）；无未请求的 AI 渐变 UI  
- UI 气质见 UI-AESTHETIC-DESIGN §0；中文/文件 UTF-8；PowerShell  
- 任务结束 **git commit**；文档只放 `docs/`  
- 回答在聊天，不写进 App  
- `gh` 用 Windows 凭据（非沙箱）  
- 删除仅限本工作区  

---

## 8. 待办 / 下一棒

| 优先级 | 项 |
|--------|-----|
| 高 | **三套 RVCMAX Runtime 已在本机**（`RVCMAX_Nvidia_xiaoyuan` / `RVCMAX_AMD_xiaoyuan` / `RVCMAX_Nvidia50x0_xiaoyuan`）。用 `build_release.py --variant nvidia\|amd\|nvidia50` 打正式全量 exe 包并实机验收 |
| 高 | 实机验收：单窗口启停、监听自己；N 卡 CUDA；A 卡包 DML；50 系机 cu128 Runtime |
| 中 | 开发切换 Runtime：`python scripts/sync_from_rvcmax.py --variant amd --force-runtime`（写 `User_Data/dev_variant.txt`） |
| 中 | 产品单测：`scripts/run_tests.bat`（含可选 Runtime 冒烟） |
| 中 | 若改 launcher 逻辑需 **重打 exe**；仅改 `gui_v1`/`rtrvc` 可拷贝进 dist |
| 中 | 是否同步 push `origin`（个人仓） |
| 低 | 主界面「运行中」与面板停止双向同步仍可再打磨；中文路径限制（原版） |

---

## 9. 新对话建议开场（复制即用）

```text
工作区：L:\My project\Grok
先读：docs/CONTEXT_HANDOFF.md（完整交接）
分支：tm-release → remote org = Turing-Mirror/TuringMirror-Voice
产品：RVC 底座 + 白无垢 launcher + 无窗 realtime_worker + 多包 GPU 方案
发行：scripts/build_release.py --variant nvidia|amd|nvidia50；TEMP 用 L 盘
约束：不改未要求的 UI；PowerShell；改完 commit；大文件不进 git
当前：三套 RVCMAX Runtime 已齐；代码/单测/选包适配完成；用 build_release --variant 打全量 exe 并实机验
```

---

## 10. 一句话状态

**N 卡产品路径已成型；A 卡 / 50 系按官方多包方式适配完成（选包、package_meta、默认加速、sync --variant、单测）。**  
官方 A/I = **整包 DML Runtime + `--dml`**；50 系 = **独立 cu128 Runtime**。本机参考包已齐，下一步是按变体打全量发行包并实机验收。
