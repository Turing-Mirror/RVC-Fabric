# Turing Mirror Voice — 上下文交接文档

> **用途**：新开对话时让 AI / 协作者快速接上当前工程状态。  
> **生成日期**：2026-07-19  
> **工作区**：`L:\My project\Grok`  
> **当前分支**：`tm-release`（本地相对 `origin/main` **ahead 3**，见下文 Git）

---

## 1. 产品是什么

| 项 | 说明 |
|----|------|
| 产品名 | **Turing Mirror 变声器**（图灵之镜配套，不是再做一套 RVCMAX 粉紫皮） |
| 技术底座 | RVC-Project WebUI + 实时 `gui_v1.py`（FreeSimpleGUI） |
| 目标体验 | 对齐 B 站 RVCMAX：**exe/快捷方式 → GUI**，用户无需装系统 Python、不靠 bat 日常使用 |
| 皮肤 | `docs/UI-AESTHETIC-DESIGN.md`「**白无垢**」（米白 `#f4f1ea` + 墨色强调），**不要**自作 AI 蓝紫/金渐变 |
| 参考布局 | RVCMAX 角色分工（启动器 / 日常 App / Runtime / User_Data / VBCABLE），**不像素级抄 UI** |

用户已装 **VB-Cable / VoiceMeeter** 一类虚拟声卡；训练/翻唱 WebUI 是高级路径，日常主路径是 **实时变声**。

---

## 2. 目录与角色（发布树）

发布成品（已构建）：

```
L:\My project\Grok\dist\TuringMirror_Voice\
  启动器.exe / TM_Setup.exe     # 首次部署 / 环境与 VBCABLE 引导
  变声器.exe / TM_Voice.exe     # 日常主程序（PyInstaller onefile，host Python 3.13 打包）
  Runtime\                      # 嵌入式 Python 3.9.13 + torch/CUDA（约 5.6GB）
  User_Data\models\             # 音色目录（1/kikiV1, 2/keruanV1, 3/guanguanV1, 4/youzhanv2-xi）
  VBCABLE\                      # 虚拟声卡安装包
  gui_v1.py                     # 高级实时面板（由 Runtime 启动，不进 exe 本体）
  launcher\                     # 源码副本 + OpenRealtime.vbs
  assets\, infer\, configs\, …  # 引擎
  使用说明.txt
```

| 角色 | 开发 | 发布 |
|------|------|------|
| 首次助手 | `launcher/bootstrap.py` | `启动器.exe` / `TM_Setup.exe` |
| 日常 App | `launcher/main_app.py` | `变声器.exe` / `TM_Voice.exe` |
| 实时面板 | `gui_v1.py` + Runtime | 同上，经 VBS/`pythonw` 拉起 |
| 引擎 | 仓库根 | 包根 |
| 用户数据 | `User_Data/` | 包内 `User_Data/` |

**开发启动（无系统 Python 依赖）**：

- `OpenApp.vbs` / `start_app.bat` → Runtime `pythonw` + `launcher/main_app.py`
- `OpenSetup.vbs` → bootstrap  
- 仓库根 `Runtime` 多为 **junction** → `RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime`

**参考整合包路径**（同步 Runtime/模型/VBCABLE）：

- `L:\My project\Grok\RVCMAX\RVCMAX_Nvidia_xiaoyuan\`  
- 脚本：`scripts/sync_from_rvcmax.py` / `.bat`

---

## 3. Git / 远程

| 项 | 值 |
|----|-----|
| 私有仓库 | `https://github.com/xiaoyanjiee/TuringMirror-Voice.git`（`origin`） |
| 上游 RVC | `https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git`（`upstream`） |
| 当前分支 | `tm-release` @ `e5a52d5` |
| 与 origin | **ahead 3**（`5b26411` `c6b9f17` `e5a52d5` 尚未 push） |
| 远程 `main` | 当初 **orphan 快照** `3c99726`（浅克隆/对象缺失后 force 推的精简历史） |
| 本地完整改进线 | `local/improvements` @ `a3742b8`（更长历史；与 orphan 远程不是同一条线） |
| `main` 本地 | 跟踪 `upstream/main`（官方 RVC） |

**近期关键提交（tm-release）：**

1. `e5a52d5` — 无 index 不崩、开启变声自动开始转换、声卡说明  
2. `c6b9f17` — 发布版用 VBS 拉实时面板（对齐 bat）  
3. `5b26411` — 去掉误导「已载入音色」阻塞框、日志与置前  

**未提交：** `TEMP_BUILD/`、`scripts/dev/_env_trace.bat`（可忽略或清理）

**CI：** 私有仓曾红：`fairseq`/`omegaconf` 冲突 + fail-fast 取消其它 Python job；用户只问过含义，**未要求修绿**。

---

## 4. 关键代码地图

| 路径 | 职责 |
|------|------|
| `launcher/main_app.py` | 白无垢主 UI：首页/音色/设置；`toggle_vc` / `open_legacy_gui` |
| `launcher/bootstrap.py` | 首次部署、Runtime/模型/VBCABLE 检测 |
| `launcher/paths.py` | `ROOT` 检测（frozen → exe 旁）；`find_python` 优先 Runtime |
| `launcher/win_util.py` | 无黑框启动；**`start_legacy_realtime_gui`**（VBS 优先 + 清洗 env） |
| `launcher/OpenRealtime.vbs` | 发布/开发统一：`Runtime\pythonw.exe gui_v1.py` |
| `launcher/config_store.py` | `User_Data/app_config.json` + 同步 `configs/inuse/config.json` |
| `launcher/catalog.py` | `User_Data/models` 目录扫描、index 搜索 |
| `launcher/theme.py` | 白无垢 token |
| `gui_v1.py` | 高级实时面板；`TM_AUTO_START_VC=1` 时自动「开始音频转换」 |
| `infer/lib/rtrvc.py` | 实时推理；**index 缺失时不得 faiss 崩溃** |
| `scripts/build_release.py` | 一键打包（engine + Runtime + models + VBCABLE + PyInstaller） |

---

## 5. 已踩坑与已修结论（必读）

### 5.1 发布版高级面板「打不开 / 任务管理器无进程」

- **现象**：开发 bat 正常；`变声器.exe` 点高级面板只见提示或无 `pythonw`。  
- **原因**：PyInstaller **3.13 onefile** 进程里直接 `Popen(Runtime 3.9 pythonw)` + `CREATE_NO_WINDOW`/环境继承不可靠。  
- **修复**：与 bat 相同路径 → `wscript` + `launcher/OpenRealtime.vbs`；`_env_for_runtime_python()` 去掉 `PYTHONHOME`/`_MEIPASS` 等污染。  
- **注意**：改 `main_app`/`win_util` **必须重打 TM_Voice.exe**；只拷 `.py` 到 dist **不够**（逻辑在 frozen exe 内）。`gui_v1.py`/`rtrvc.py` 在包根/Runtime 侧，拷贝即生效。

### 5.2 「开始音频转换」一点就崩

- **原因**：`configs/inuse/config.json` 残留  
  `index_path: "logs/kikiV1.index"`（不存在）+ `index_rate: 0.5`  
  → `faiss.read_index` 抛错，FreeSimpleGUI 整窗退出。  
- **现状**：多数目录音色 **只有 .pth、没有 .index**（正常）。  
- **修复**：`set_values`/同步配置清空无效 index 并 `index_rate=0`；`rtrvc` 读 index 做存在性与 try/except；启动失败 `popup_error` 不直接 exit。

### 5.3 「开启变声」还要再手动点转换

- **旧行为**：只启动面板。  
- **现行为**：`toggle_vc` 设 `TM_AUTO_START_VC=1`，`gui_v1._try_auto_start_vc()` 加载后自动 `start_vc`。  
- 「打开高级实时面板」**不**自动开始（清掉该 env）。

### 5.4 误导 UX

- 曾弹出「已载入当前音色」成功框，面板却要 20–40s 才出窗 → 用户以为坏了。  
- 已改为状态栏文案 + 窗口出现后置前（标题 **`RVC - GUI`**）。

### 5.5 其它历史坑

- 路径含空格 `My project`：bat 重定向/日志路径必须加引号。  
- 中文 bat 编码：日常用 **VBS + ASCII bat**。  
- Agent 会话启动的 GUI 可能不在用户桌面：用 `OpenApp.vbs` / `wscript`。  
- 主 UI「使用中」勿用 disabled Button，用 Label。  
- 模型列表按 stem 去重，避免 kikiV1 重复。  
- 实时模型路径：写入 `configs/inuse/config.json` 的 **绝对路径**（面板只在启动时读）。

---

## 6. 虚拟声卡接线（给用户/客服）

| 位置 | 设备 |
|------|------|
| 实时面板 **输入** | 真实麦克风（不要 CABLE） |
| 实时面板 **输出** | **CABLE Input**（或 VoiceMeeter Input） |
| 游戏/QQ/Discord **麦克风** | **CABLE Output** |
| Windows 默认播放 | 耳机/音箱（不要 CABLE） |
| WASAPI 独占 | 不要勾（除非懂） |

链路：`真麦 → 本软件变声 → CABLE Input → 对面从 CABLE Output 听`。

主界面设置页有文案 +「声卡接线说明」按钮。

---

## 7. 构建与磁盘

```text
# 完整包（Runtime 很大）
python scripts/build_release.py --clean --out dist\TuringMirror_Voice

# 只更新 exe + 引擎拷贝，不重拷 Runtime（常用）
python scripts/build_release.py --skip-runtime --out dist\TuringMirror_Voice
```

- **大文件在 L:**（工程与 dist）。  
- **默认 TEMP 在 C:**；打包前建议：  
  `$env:TEMP = $env:TMP = 'L:\My project\Grok\TEMP_BUILD'`  
- 主机 PyInstaller：**Python 3.13**；Runtime 内解释器：**3.9.13 + cu118**。  
- GPU 记录：GTX 1060 **3GB**，config 会 force fp32。  
- 上次重建 exe 时间戳约 **2026-07-19 16:16**（`TM_Voice.exe` / `变声器.exe`）。  
- dist 里可能残留调试用 `frozen_probe.exe`，可删。  
- **L 盘空间曾极紧**；交接时约 C: 8GB / L: 67GB free（以实机为准）。

日志：

- `User_Data/logs/realtime_gui.log`  
- `User_Data/logs/realtime_gui_vbs.log`  

---

## 8. 工作约定（Agents / 用户偏好）

来自 `C:\Users\21627\.grok\Agents.md` 与对话：

- 无 emoji；无未请求的 AI 渐变色 UI。  
- **严格继承现有设计**；不擅自改皮肤。  
- 中文/文件 UTF-8；PowerShell 语法。  
- 任务结束 **git commit**；文档放 `docs/`。  
- 回答在聊天里，不写进 App。  
- 根 agent 直接干活；子 agent 禁止再嵌套委派。  
- **不要**中途过度加合规/安全脚手架。  
- `gh` 在沙箱外跑（Windows 凭据）。  
- 删除范围仅限本 Grok 工作区（用户曾指定 RVC 专用目录）。

---

## 9. 待办 / 风险（下一对话可跟）

| 优先级 | 项 |
|--------|----|
| 高 | 用户验收：**发布版** 开启变声 + 自动转换 + 不崩；确认游戏软件听到变声 |
| 高 | 若仍崩：收 `realtime_gui.log` / 面板错误弹窗；查 AudioIoProcess 设备占用、显存 OOM |
| 中 | `git push origin tm-release`（或合并策略）——本地 ahead 3 未推 |
| 中 | CI 绿：fairseq/omegaconf + fail-fast（用户未强求） |
| 中 | 音色若有官方 `.index`，拷入模型目录并写 sidecar，提升相似度 |
| 低 | 清理 dist `frozen_probe.exe`、`TEMP_BUILD/` |
| 低 | 主界面「开启变声」与面板「停止」状态双向同步仍弱（停面板后主按钮可能仍显示运行中） |
| 低 | `gui_v1` 中文路径限制仍在（pth/index 不可含中文路径字符） |

**未完成的产品化**（早期清单，部分已做）：真·一键包用户路径基本可用；端到端「开黑听感」需用户机再验；训练 WebUI 仍是高级入口。

---

## 10. 新对话建议开场（复制即用）

```text
工作区：L:\My project\Grok
先读：docs/CONTEXT_HANDOFF.md
当前分支 tm-release @ e5a52d5（origin/main 可能落后 3 个本地提交）
产品：Turing Mirror 变声器 = RVC 底座 + 白无垢 launcher + Runtime 发布树
发布目录：dist\TuringMirror_Voice
关键修复：OpenRealtime.vbs 启面板；无 index 不崩；TM_AUTO_START_VC 自动开始转换
约束：不改未要求的 UI 风格；PowerShell；改完 commit；文档只放 docs/
```

---

## 11. 相关文档索引

| 文档 | 内容 |
|------|------|
| `docs/UI-AESTHETIC-DESIGN.md` | 白无垢设计 |
| `docs/发布布局与角色分工.md` | RVCMAX 角色对照 |
| `docs/发行版打包与用户使用.md` | 打包与用户路径 |
| `docs/RVC_ANALYSIS.md` | 早期引擎分析 |
| `docs/B站与官方整合包形态.md` | B 站形态参考 |
| `docs/大众版使用说明.md` | 面向用户说明 |

---

## 12. 一句话状态

**发布树已能构建；实时面板在 exe 下应经 VBS 启动；无 index 不应再秒崩；开启变声应自动开始转换。**  
下一棒优先：**用户实机听感验收 + 未 push 的 3 个 commit 是否推送 + 残余设备/停止状态体验。**
