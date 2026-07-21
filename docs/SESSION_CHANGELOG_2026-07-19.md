# 本对话全量改动总结（2026-07-19）

> **用途**：记录本次协作对话中完成的全部设计、适配、修复与功能开发。  
> **分支**：`tm-release`（相对 `org/tm-release` 约 11 个提交）  
> **产品**：（历史会话）现产品名 **RVC Fabric**；当时为 RVC 底座 + launcher + 无窗 realtime_worker

---

## 0. 一句话总览

在已有「单窗口实时变声」产品路径上，本对话完成了：

1. **项目进度梳理**（文档/代码对照，未改代码）  
2. **自动化测试初始化** + **N 卡 / A 卡 / 50 系多包适配闭环**  
3. **启动器**体验与系统快捷（黑框说明、声音面板）  
4. **环境检测**分层（日常必需 vs 训练可选）  
5. **设置页最大化布局**修复  
6. **代码审查后的 GPU/进程/下载**硬伤修复  
7. **变声后专业 DSP 效果链**（噪声门 / 压缩 / 5 段 EQ）  
8. **可自定义快捷键**（切换音色 / 启停 / 音高；可选 Windows 全局热键）

---

## 1. 提交时间线（本对话相关）

| Commit | 主题 |
|--------|------|
| `13891b5` | 自动化测试 + AMD/50 系打包与选包适配 |
| `baa6e8f` | 启动器：黑框说明 + 系统快捷页（声音设备） |
| `2ba0498` | 环境检测分层；下载 scope 拆分 |
| `07cc6bc` / `d82f413` | 检测弹窗文案精简 |
| `819091e` / `7b964ba` | 设置页最大化铺满宽度 + issue2 截图 |
| `541c633` | 审查修复：GPU env / 探测 / 加速切换重启 worker 等 |
| `641c628` | 后级 DSP 效果链（门/压缩/EQ） |
| `cefd5ad` | RVC Forge 效果参考截图 issue3 |

（更早的会话提交如 CONTEXT_HANDOFF、多包 GPU 骨架等见仓库历史；下文以**本对话落地内容**为主。）

---

## 2. 进度梳理（对话开篇）

### 结论（当时）

- **已成型**：白无垢主界面、无窗 worker、单窗启停、监听自己、Index、热更新、N 卡打包能力。  
- **缺口（后已补）**：A 卡 / 50 系 Runtime 适配未闭环；测试几乎为空；`dist` 落后源码。  
- **本机资源**：三套 RVCMAX 均已具备  
  - `RVCMAX_Nvidia_xiaoyuan`（cu118）  
  - `RVCMAX_AMD_xiaoyuan`（CPU + DirectML）  
  - `RVCMAX_Nvidia50x0_xiaoyuan`（cu128）

### 架构（未改方向）

```text
变声器.exe / main_app.py
  → User_Data/runtime_control/*.json
  → Runtime\pythonw + tools/realtime_worker.py
  → gui_v1 (TM_REALTIME_WORKER=1) + rtrvc
```

---

## 3. 自动化测试 + 显卡多包适配

### 3.1 测试入口

- **`scripts/run_tests.bat`**：优先使用 `Runtime\python.exe`  
- 用例目录：`tests/test_*.py`  
- 本对话后全量约 **53** 项（含 Runtime 冒烟，约 3 分钟）

### 3.2 新增/增强测试文件

| 文件 | 覆盖 |
|------|------|
| `tests/test_package_meta.py` | 发行包 meta / 默认加速 |
| `tests/test_gpu_backend.py` | 后端解析、`apply_backend_env` 原地写 |
| `tests/test_build_variants.py` | nvidia 排除 50 系、prefer_dir |
| `tests/test_config_accel.py` | 首启 accel 继承 package_meta |
| `tests/test_env_setup.py` | 环境分层、简报 |
| `tests/test_runtime_smoke.py` | 三套 Runtime 的 CUDA/DML 特征（可选） |
| `tests/test_download_models.py` | 下载最小体积判定 |
| `tests/test_dsp_fx.py` | 噪声门 / 压缩 / EQ / 链 |

### 3.3 构建与同步（官方多包方式）

| 变体 | prefer_dir | 默认加速 |
|------|------------|----------|
| `nvidia` | `RVCMAX_Nvidia_xiaoyuan` | cuda（排除目录名含 50） |
| `amd` | `RVCMAX_AMD_xiaoyuan` | dml |
| `nvidia50` | `RVCMAX_Nvidia50x0_xiaoyuan` | cuda |

**改动要点**：

- `scripts/build_release.py`：`prefer_dir`、`exclude_keys`、多 core 回退拷 `rmvpe.onnx`、修复 `package_meta` 导入、**禁止**误用 `REPO/Runtime` junction 打 N 卡包  
- `scripts/sync_from_rvcmax.py`：`--variant nvidia|amd|nvidia50`、`--force-runtime`、写 `User_Data/dev_variant.txt`  
- `scripts/dev/_env.bat`：按 `TM_VARIANT` / `dev_variant.txt` 选 Runtime；amd 默认 DML 环境变量  
- UI：`package_meta` 标签、加速状态与混包提示  

**构建示例**：

```bat
set TEMP=L:\My Project\Grok\TEMP_BUILD
set TMP=%TEMP%
python scripts/build_release.py --clean --variant nvidia
python scripts/build_release.py --clean --variant amd
python scripts/build_release.py --clean --variant nvidia50
```

**开发切换 Runtime**：

```bat
python scripts/sync_from_rvcmax.py --variant amd --force-runtime
```

文档同步：`docs/发行包-显卡分版.md`、`docs/CONTEXT_HANDOFF.md`、`docs/项目结构.md`。

---

## 4. 启动器（bootstrap）

### 4.1 首页「首次设置」

- 增加说明：**初次启动/检测时短暂黑框属正常**（绿色 Runtime 加载，非报错）  
- 卡片文案：检测与部署 →「日常必需 · 可选训练」  

### 4.2 第二页「系统快捷」

- 导航：**首次设置 | 系统快捷**  
- **声音设备**：打开系统经典「声音」面板（`control mmsys.cpl`）— 播放/录制列表，**不是**设备管理器  
- 实现：`launcher/win_util.open_windows_sound_panel()`  

### 4.3 环境检测与下载

**分层**：

| 层级 | 内容 | 是否挡住「环境正常」 |
|------|------|----------------------|
| core | Runtime/Python、Hubert、RMVPE、torch、SoundDevice；AMD 包另含 torch_directml | 是 |
| soft | 音色数量、rmvpe.onnx 等 | 否 |
| training | 训练底模、UVR、Gradio、Faiss | 否 |

**下载**（`tools/download_models.py --scope`）：

- `core`：hubert + rmvpe（+ 可选 rmvpe.onnx）— **默认**  
- `training`：pretrained / v2  
- `uvr`：伴奏分离  
- `all`：全量  

**交互**：短状态报告 + 最多一次确认；训练资源**可选、默认不强迫下载**。  
**防抖**：`_deploy_busy` 防止连点并行下载。  
**完整性**：跳过条件改为最小体积 + Content-Length 校验（避免坏文件永久 skip）。

---

## 5. 主界面 UI 修复

### 5.1 设置页最大化留白（issue2）

**问题**：Canvas 内层宽度不随窗口变，卡片贴左、右侧大片空白。  

**修复**（`launcher/main_app.py`）：

- Canvas `Configure` 时 `itemconfigure(width=视口宽)`  
- 滑条取消过短固定 length，横向 expand  
- 说明文字 `wraplength` reflow  
- 滚轮绑定在 canvas/子树，**不用** `unbind_all`  

### 5.2 发行包信息

- 设置页显示「发行包：NVIDIA CUDA / AMD DirectML / …」  
- 加速后端变更提示勿混用 Runtime  

---

## 6. 代码审查与硬伤修复

审查范围：本对话多提交的 launcher / 打包 / 下载 / 测试。

### 6.1 必修复（已做）

| 问题 | 修复 |
|------|------|
| `apply_backend_env` 只改副本，主进程丢 `TM_*` | **原地**写入传入 mapping（含 `os.environ`） |
| Runtime 探测继承 PyInstaller 宿主 PYTHON 污染 | 探测用 `_env_for_runtime_python` 清洗，并去掉强制 TM_* |
| 改「加速后端」不重启 worker | `_force_restart_worker_for_backend()` 停流 + quit + 清孤儿 |
| AMD 探测失败落到 CPU | `package_variant=amd` 时 auto/dml 仍优先 DML |

### 6.2 建议项（已做）

- 下载最小体积 / Content-Length  
- 部署 busy 锁  
- nvidia 构建不回退 `REPO/Runtime`  
- 设置页滚轮作用域  
- AMD 包检测 `torch_directml`（core）  
- `app_config.json` 原子写（`atomic_write_json`）  

---

## 7. 后级 DSP 效果链（对齐 RVC Forge「内置效果」能力，非抄 UI）

### 7.1 选型

| 方案 | 结论 |
|------|------|
| Spotify Pedalboard | 质量高但 Runtime 未装、打包风险 → **不默认依赖** |
| OpenVoiceChanger | MIT 效果清单可参考，整嵌 Web 栈成本高 → **不嵌** |
| **自研 numpy 流式 DSP** | Runtime 已有 numpy → **采用** |

### 7.2 音频路径

```text
麦 → [可选] TorchGate 输入降噪
  → RVC 推理
  → [可选] TorchGate 输出降噪
  → [新] RealtimeFxChain：噪声门 → 压缩 → 5 段 EQ → 输出增益
  → RMS 混合 / CABLE / 监听
```

- 仅 `function == vc` 时跑链  
- **默认 `fx_enabled=false`**，关闭时与改前听感一致  
- 运行中参数可热更新  

### 7.3 模块与文件

| 路径 | 说明 |
|------|------|
| `tools/dsp_fx.py` | NoiseGate / Compressor / GraphicEQ / RealtimeFxChain |
| `gui_v1.py` | 推理后接入、worker hot 字段 |
| `launcher/config_store.py` | `fx_*` 默认与同步到 inuse config |
| `launcher/main_app.py` | 设置页「声音效果（变声后 · 可选）」 |
| `tests/test_dsp_fx.py` | 单元测试 |

### 7.4 EQ 预设

| key | 界面含义 |
|-----|----------|
| flat | 平直 |
| vocal_front | 人声前倾 |
| warm | 温暖饱满 |
| bright | 清晰明亮 |
| de_nasal | 消除鼻音 |
| thick | 低沉厚实 |

频点：60 / 250 / 1k / 4k / 8k Hz，±12 dB。

### 7.5 明确未做（P2）

- 混响、后级半音变调、云端声线、Forge 风格 UI  

参考截图：`docs/reference-screenshots/issue3.png`。

---

## 8. 主要改动文件清单

### 产品壳

- `launcher/bootstrap.py`  
- `launcher/main_app.py`  
- `launcher/env_setup.py`  
- `launcher/gpu_backend.py`  
- `launcher/config_store.py`  
- `launcher/win_util.py`  
- `launcher/package_meta.py`（沿用/配合）  

### 引擎

- `gui_v1.py`  
- `tools/dsp_fx.py`（新）  
- `tools/download_models.py`  
- `tools/realtime_worker.py`（既有入口，经 gui_v1）  

### 脚本

- `scripts/build_release.py`  
- `scripts/sync_from_rvcmax.py`  
- `scripts/run_tests.bat`  
- `scripts/dev/_env.bat`  

### 测试

- `tests/test_*.py`（多项新增）  

### 文档 / 截图

- `docs/CONTEXT_HANDOFF.md`  
- `docs/发行包-显卡分版.md`  
- `docs/项目结构.md`  
- `docs/reference-screenshots/issue2.png`、`issue3.png`  
- **本文** `docs/SESSION_CHANGELOG_2026-07-19.md`  

---

## 9. 使用与验收速查

### 开发

```bat
scripts\run_tests.bat
start.bat              REM 启动器
start_app.bat          REM 主界面
python scripts\sync_from_rvcmax.py --variant nvidia --force-runtime
```

### 用户向

1. 启动器：首次说明黑框正常；系统快捷 → 声音设备  
2. 检测与部署：只盯日常必需；训练资源可选下  
3. 变声器设置：设备 / 加速 / **声音效果**（默认关）  
4. 开黑：门+压缩+轻 EQ 可按需开  

### 发行

- 改 launcher 壳逻辑需 **重打** `启动器.exe` / `变声器.exe`  
- 仅改 `gui_v1.py` / `tools/dsp_fx.py` 可拷入 dist 试听  
- 多包：`--variant nvidia|amd|nvidia50` 全量构建  

---

## 10. 后续可选工作

| 优先级 | 项 |
|--------|-----|
| 高 | 三变体全量 exe 包实机验收（N / A / 50） |
| 高 | 带 DSP 开启的听感与延迟摸底 |
| 中 | 混响 / 限制器增强（P2） |
| 中 | 推送到 `org` / 是否同步 `origin` |
| 低 | 原版面板与主界面运行状态双向同步 |

---

## 11. 约束回顾（全程遵守）

- 白无垢 UI，无未请求的 AI 渐变 / 粉紫壳  
- 无 emoji（除非要求）  
- 文档在 `docs/`；任务结束 commit  
- 中文与文件 UTF-8；Windows PowerShell  
- 大体积 Runtime / dist **不进 Git**  

---

*文档生成：本对话结束时汇总。若后续继续开发，可在本文末追加日期小节，或新开 `SESSION_CHANGELOG_YYYY-MM-DD.md`。*
