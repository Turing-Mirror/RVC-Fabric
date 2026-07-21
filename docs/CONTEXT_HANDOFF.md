# RVC Fabric — 完整上下文交接

> **用途**  
> 1. 新开 Grok / 协作者对话：先读本文再动代码。  
> 2. 在 GitHub 上看仓库的人：了解产品定位、架构、已做事项与坑。  
> **最后大更新**：2026-07-21  
> **工作区**：`L:\My Project\Grok`  
> **当前分支**：`tm-release`  
> **主推 remote**：`fabric` → https://github.com/Turing-Mirror/RVC-Fabric.git  
> **组织旧仓**：`org` → TuringMirror-Voice（历史；以 fabric 为准）  
> **个人镜像**：`origin` → xiaoyanjiee/TuringMirror-Voice  
> **上游 RVC**：`upstream` → RVC-Project/Retrieval-based-Voice-Conversion-WebUI  

---

## 0. 30 秒读懂

| 项 | 内容 |
|----|------|
| 产品名 | **RVC Fabric**（界面文案 / 桌面快捷方式；`launcher/theme.py` 的 `APP_*`） |
| 底座 | 官方 RVC WebUI + 实时 `gui_v1.py`，**不重写算法** |
| 体验目标 | 解压 → 启动器 → 桌面图标 → 开黑变声；日常**不**靠 bat |
| UI | Schale 浅蓝 token（`theme.py`）；禁止 AI 渐变 / RVCMAX 粉紫 / 青绿 |
| 参考包 | `RVCMAX/RVCMAX_*`（布局/Runtime，不抄皮） |
| 日常主路径 | 主界面选音色 → 设置设备 → **开启变声**（后台无窗 worker） |
| 底栏 | 变声/原声、音高·共鸣·阈值（热更新）、按音色保存；撤销/重做/默认 |
| 配置档案 | 每音色 `.tmvp`（`launcher/profiles.py` + 模型页面板） |
| 发行 | `scripts/build_release.py --variant nvidia\|amd\|nvidia50` → `dist/`（gitignore） |
| Git 含什么 | **`docs/仓库内容说明.md`** |
| launcher 拆分 | **`docs/LAUNCHER_DECOMPOSITION.md`** |

**发行包文件名（打包脚本现状）**：仍可能输出 `启动器.exe` / `变声器.exe` 与目录 `TuringMirror_Voice_*`——这是打包脚本命名；**产品显示名一律 RVC Fabric**。

---

## 1. 产品定位与非目标

### 要做

- 本地实时变声（游戏 / QQ / Discord + VB-Cable）
- 产品壳：`launcher/`（bootstrap + main_app 组合 mixin）
- 用户数据在 `User_Data/models`
- 高级：原版实时面板、训练/翻唱 WebUI

### 不要做

- 不做 RVCMAX 粉紫 Electron 壳  
- 不擅自改 UI 气质  
- 不把 `RVCMAX/`、`Runtime/`、`dist/` 当源码主树提交  
- 中途不过度加合规脚手架  

---

## 2. 架构（必懂）

```
┌─────────────────────────────────────┐
│  主界面 exe / launcher/main_app.py   │  RVC Fabric UI
│  设置 → User_Data/app_config.json   │
│  + 同步 configs/inuse/config.json   │
└──────────────┬──────────────────────┘
               │ JSON：User_Data/runtime_control/
               ▼
┌─────────────────────────────────────┐
│  Runtime\pythonw + realtime_worker  │
│  → gui_v1 (TM_REALTIME_WORKER=1)    │
│  rtrvc + AudioIoProcess             │
└─────────────────────────────────────┘
```

**为何 torch 不能塞进壳 exe？**  
壳可用主机 3.13 PyInstaller；推理必须在 **Runtime 3.9 + CUDA/DML**。用 VBS / 清洗 env，避免 `_MEIPASS` 污染。

### 关键路径

| 路径 | 职责 |
|------|------|
| `launcher/main_app.py` | 壳骨架 + mixin 组合（约 900+ 行） |
| `launcher/pages/*` | Home / Models / Settings / More / Hotkeys / Monitor / Realtime / Dock / Onboarding / Profiles |
| `launcher/theme.py` | 产品名 `RVC Fabric`、色板 token |
| `launcher/gpu_backend.py` | GPU 探测：**Runtime 进程内探测**，禁止为探测起 `python.exe` 黑窗 |
| `launcher/realtime_client.py` | worker 启停；预热引擎待命；只用 **pythonw** 起 worker |
| `gui_v1.py` | 实时引擎；**Harvest 仅当配置 f0method=harvest 时预热** |
| `OpenApp.vbs` / `OpenSetup.vbs` | 无黑框启动主界面 / 启动器 |
| `scripts/build_release.py` | 一键发行包 |

---

## 3. 近期已落地（相对 2026-07 中下旬）

- 单窗口日常变声、底栏热控、按音色参数、快捷键、监听自己、DSP 效果链  
- 在线更新 / 音色库（sha256、safe_zip）  
- 性能优化与本机 perf 报告  
- 配置档案 Plan A（`.tmvp`）  
- **main_app 拆分**为多 mixin（见 LAUNCHER_DECOMPOSITION）  
- **产品更名 RVC Fabric**，去掉 voice.local / 英文装饰眉题、「复制全文」等  
- **启动**：pythonw + 进程内 GPU 探测；引擎待命仍预热 worker；修复设置页 `@staticmethod` 闪退、bootstrap 语法错误  

---

## 4. 用户动线（验收）

1. 解压（优先英文路径）  
2. **启动器** → 快捷方式 + VB-Cable + 检测  
3. **主界面（RVC Fabric）** → 引擎待命  
4. 设置：输入=真麦，输出=CABLE Input；可选监听耳机  
5. 选音色 → **开启变声**  
6. 游戏麦克风=CABLE Output  

开发启动：`OpenApp.vbs` / `start_app.bat`（勿用裸 `python main_app.py` 除非调试）。

---

## 5. 虚拟声卡接线

| 位置 | 设备 |
|------|------|
| 软件输入 | 真实麦克风 |
| 软件输出 | **CABLE Input** |
| 监听（可选） | 耳机 |
| 游戏/QQ 麦 | **CABLE Output** |
| Windows 默认播放 | 耳机（不要 CABLE） |

---

## 6. 文档索引

| 文档 | 内容 |
|------|------|
| `docs/仓库内容说明.md` | Git 含什么 / 不含什么 |
| `docs/UI-AESTHETIC-DESIGN.md` | UI 约束（Schale 浅蓝） |
| `docs/项目结构.md` | 目录角色 |
| `docs/LAUNCHER_DECOMPOSITION.md` | main_app 拆分 |
| `docs/发行版打包与用户使用.md` | 打包与用户路径 |
| `docs/发行包-显卡分版.md` | N/A/50 分版 |
| `docs/大众版使用说明.md` | 用户说明 |
| `docs/在线更新与音色库.md` | 更新包规范 |
| `docs/CONTEXT_HANDOFF.md` | **本文** |

上游多语言 FAQ/Changelog（`docs/en` 等）仍属原版 RVC 文档，未全部改产品名。

---

## 7. 约束

- 无 emoji（除非要求）；无未请求的 AI 渐变 UI  
- 中文/文件 UTF-8；Windows PowerShell  
- 任务结束 commit；文档只放 `docs/`  
- 大体积 Runtime / dist / RVCMAX **不进 Git**  

---

## 8. 待办 / 下一棒

| 优先级 | 项 |
|--------|-----|
| 高 | 三变体全量 exe 实机验收（N / A / 50） |
| 中 | 打包脚本目录/exe 命名是否与 RVC Fabric 完全对齐（可选） |
| 中 | 改 launcher 后需重打 exe 才能在发行包看到 |
| 低 | MagiaDC 向 UX 打磨（排在验收之后） |

---

## 9. 新对话建议开场

```text
工作区：L:\My Project\Grok
产品：RVC Fabric（RVC 底座 + launcher 壳 + 无窗 worker）
先读：docs/CONTEXT_HANDOFF.md + git log -15
分支：tm-release → fabric = Turing-Mirror/RVC-Fabric
发行：scripts/build_release.py --variant nvidia|amd|nvidia50
约束：不擅自改 UI 气质；PowerShell；改完 commit；大文件不进 git
```

---

## 10. 一句话状态

**RVC Fabric 功能侧已齐（单窗变声、底栏、档案、更新、拆分壳层、静默启动与 GPU 进程内探测）。**  
下一步仍是 **分显卡全量 exe 实机验收**；代码真相以 `git log` + 源码为准。
