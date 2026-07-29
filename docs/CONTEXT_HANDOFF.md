# RVC Fabric — 完整上下文交接

> **用途**  
> 1. 新开 Grok / 协作者对话：先读本文再动代码。  
> 2. 在 GitHub 上看仓库的人：了解产品定位、架构、已做事项与坑。  
> **最后大更新**：2026-07-28  
> **工作区**：`L:\My Project\Grok`  
> **当前分支**：`tm-release`（相对 `fabric/tm-release` 可能超前：广场页 `0800079` 等）  
> **壳版本**：1.1.2  
> **主推 remote**：`fabric` → https://github.com/Turing-Mirror/RVC-Fabric.git  
> **组织旧仓**：`org` → TuringMirror-Voice（历史；以 fabric 为准）  
> **个人镜像**：`origin` → xiaoyanjiee/TuringMirror-Voice  
> **上游 RVC**：`upstream` → RVC-Project/Retrieval-based-Voice-Conversion-WebUI  
> **CNB 制品**：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases（本机 `CNB-GIT-RELEASE/`）  

---

## 0. 30 秒读懂

| 项 | 内容 |
|----|------|
| 产品名 | **RVC Fabric**（界面文案 / 桌面快捷方式；`launcher/theme.py` 的 `APP_*`） |
| 底座 | 官方 RVC WebUI + 实时 `gui_v1.py`，**不重写算法** |
| 体验目标 | **Setup 安装壳** → **启动器补全 Runtime** → 主界面 → 社区音色 → 变声 |
| Setup | **Inno 薄包**（壳层：启动器+主界面+源码配置）；**不含** Runtime / engine-core / VB-Cable |
| Runtime | **仅 CNB**（按显卡分版）；启动器下载 |
| engine-core | **仅 CNB LFS** `assets/core/engine-core-*.zip`（hubert+rmvpe+ffmpeg+ffprobe，全卡共用） |
| 启动器下载 | `launcher/online/multipart.py`：多连接 Range + 断点续传；`provision_progress` 流程 UI |
| 在线索引 | CNB 仓根 **`index.json`**（主）+ **`ch-banner/`** 封面；`packages` 按 YYMMDD 命名 Setup/gui/runtime；文档 `docs/CNB-index索引与封面.md` |
| 本地封面 | **`User_Data/ch-banner/<id>.jpg`**；`config.json` 只写相对路径 `ch-banner/...`（禁止绝对盘符） |
| 音色包 | zip 内 **`config.json`** 含 name/author/author_url/date/cover；模型页与社区下载显示作者与封面 |
| UI | Schale 浅蓝 token（`theme.py`）；禁止 AI 渐变 / RVCMAX 粉紫 / 青绿 |
| 参考包 | `RVCMAX/RVCMAX_*`（布局/Runtime，不抄皮） |
| 日常主路径 | 主界面选音色 → 设置设备 → **开启变声**（后台无窗 worker） |
| 配置档案 | 每音色 `.tmvp`（`launcher/profiles.py` + 模型页面板） |
| 咨询包 | 调参服务 zip；进件漏斗「申请专业优化」 |
| 发行全量 | `scripts/build_release.py --variant nvidia\|amd\|nvidia50` → `dist/` |
| Git 含什么 | **`docs/仓库内容说明.md`** |

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
| `launcher/main_app.py` | 壳骨架 + mixin 组合（约 1180 行） |
| `launcher/pages/*` | Home / Models / **Plaza** / Settings / More / Hotkeys / Monitor / Realtime / Dock / Onboarding / Profiles / Consult |
| `launcher/online/plaza.py` | 广场 feed 解析/过滤/缓存（Tk-free）；运营见 `docs/广场页与内容运营.md` |
| `launcher/theme.py` | 产品名 `RVC Fabric`、色板 token、`px()` HiDPI、`meta_font` |
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
- **咨询包**（样本 + 档案 + 环境 + 可选模型文件 → `User_Data/consult_packs/`）  
- **main_app 拆分**为多 mixin（见 LAUNCHER_DECOMPOSITION）  
- **产品更名 RVC Fabric**，去掉 voice.local / 英文装饰眉题、「复制全文」等  
- **启动**：pythonw + 进程内 GPU 探测；引擎待命仍预热 worker；修复设置页 `@staticmethod` 闪退、bootstrap 语法错误  
- **诊断包升级（2026-07-27）**：「其他」页「生成诊断包」可先跑一次快速性能测试（`launcher/perf_bench.py` 在 Runtime 无窗跑 `tools/benchmark_realtime.py`，用户当前音色+设置，约 1 分钟）；结果 `perf_reports/bench_*.json` 连同 CPU/内存/系统等机型字段一起进包，用于收集各机型性能样本（详见 `docs/PERF_NOTES.md` §4）  
- **社区下载改版（2026-07-27）**：首页按上传时间从晚到早分页（每页 5 个、页码+跳页）；新增「系列专区」折叠视图；移除「完整包与社群」卡片；RVC 原版 4 音色作者规范为「RVC」；**并发下载**（2 路 + 等待队列，按钮即状态：下载安装/待下载/NN%/重新下载）；MyGO 5 音色标题改中文角色名（千早爱音/高松灯/长崎爽世/椎名立希/要乐奈，拉丁 id 作副标）。**已随 v1.1.2 发布**（CNB gui_patch_1.1.2.zip，含 part1 诊断包与设置页整理；`compare_versions` 已支持 `-partN` 预发布语义——旧 part1 客户端因本地旧比较代码收不到 1.1.2 提示，属已知小尾巴）  
- **设置页整理（2026-07-27）**：设置页「声卡接线说明」改为「实体声卡连接说明」（虚拟声卡选法在设置页各项旁与「说明」页已覆盖，弹窗改讲 USB 直播声卡 / 调音台）；「打开原版实时面板」从设置页移到「其他」页（高级入口不再吸引新手）；全项目用词「接线」统一改为「连接」
- **文字清晰度 + 切页防闪（2026-07-27，6 提交 56aefac..bcb98a1）**：(a) 壳与启动器启动时声明 PMv2 DPI awareness + `tk scaling`（此前完全没有 → 125%/150% 屏整窗位图拉伸发糊）；像素常量统一过 `theme.px()`（100% 屏逐位零变化），控件 width/height 形参为设计单位由控件内部 px（防双重缩放契约写在 theme.py docstring）；win_geometry 持久化带 `win_dpi` 迁移。(b) 中文小字全部撤离 Cascadia Mono（无 CJK 字形逐字回退是截图发糊主因）；7pt 全部抬 8pt；≤9pt bold 抬 10pt；Combobox 配 sans 10；ASCII/CJK 双态文本走新 `theme.meta_font`。(c) `show_page` 由 pack_forget/pack 改 grid 叠放 + `tkraise`（消 unmap 白帧）；models/home 切页用渲染快照短路（宽度+选中音色+目录 mtime 戳，含每个音色子目录），数据变更点调 `_invalidate_catalog_views()`；settings `<Map>` 全树滚轮重绑改 show_page after_idle；help 首次 show 才自适应高度并解除 Configure 自激。**改动仅进 launcher/ 源码，需重打 exe 或发 gui_patch 才到用户**；125%/150% 实机验收待做（本机 96dpi 仅验证了零变化基线）。新增「广场」页时须遵守 grid+tkraise 与 px() 新架构（见 tests/test_dpi_scale.py 与 theme.py 注释）。  
- **广场页（2026-07-27）**：新增「广场」导航页（TRM/RVC Fabric 资讯 + 引流 + 赞助卡片）与模型页至多一条可关闭广告横幅；feed 为 CNB 仓根 `plaza.json`，独立于 index.json，运营改内容不发版（源 `catalog-src/plaza.yaml`，build_catalog 编译回环校验）。ad/sponsor 强制可关闭并带「广告」角标；点击统计只靠编译期给 url 盖 utm 参数，客户端**零遥测**。详见 `docs/广场页与内容运营.md`。  
- **自定义背景图（2026-07-28，P0/P1 跟进 07-29）**：设置 →「外观（背景图）」；不透明度/磨砂。PIL cover + GaussianBlur + blend（相对 `theme.TM_BG`）。Windows 透出用**专用 chromakey `#010203`**（禁止用 `TM_BG` 作色键，避免按钮被打穿）；仅 body/页根/滚动画布上色键。全窗重算后台线程，滑条 debounce 280ms。安装限 20MB / 最长边 4096，只认 `User_Data/wallpaper/`。UI：`WallpaperSettingsMixin`。实现：`launcher/ui/wallpaper.py`。P2 待办见 §8。

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

## 5. 虚拟声卡连接

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
| `docs/CONTEXT_HANDOFF.md` | **本文（交接主文档）** |
| `docs/仓库内容说明.md` | Git 含什么 / 不含什么 |
| `docs/项目结构.md` | 目录角色 + 引擎数据流 |
| `docs/发布布局与角色分工.md` | 发行角色 / RVCMAX 对照 |
| `docs/Setup安装与补全.md` | Setup 薄包 + Runtime 补全 |
| `docs/发行版打包与用户使用.md` | 打包与用户路径 |
| `docs/发行包-显卡分版.md` | N/A/50 分版 |
| `docs/在线更新与音色库.md` | 更新包 / 音色包规范 |
| `docs/CNB-index索引与封面.md` | CNB index / 封面 |
| `docs/广场页与内容运营.md` | plaza.json 投放（零遥测） |
| `docs/UI-AESTHETIC-DESIGN.md` | UI 约束（Schale 浅蓝） |
| `docs/LAUNCHER_DECOMPOSITION.md` | main_app 拆分规则 |
| `docs/PERF_NOTES.md` | 性能基准 + 后续推理路线 |
| `docs/审查缺陷清单.md` | 壳层审查 backlog（按条修） |
| `docs/大众版使用说明.md` | 用户说明 |
| `CLAUDE.md` | 协作者英文架构指引（与 handoff 同步） |

上游多语言 FAQ/Changelog（`docs/en` 等）仍属原版 RVC 文档，未全部改产品名。

**文档约定**：进度写入本文 §3 / §8；**不要**再新增 `SESSION_CHANGELOG_*`、`PLAN_YYYY-MM-DD_*`、
`REVIEW_BACKLOG_*` 等带日期英文散页。历史会话内容已吸收进本文与上表常驻手册。

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
| 高 | Setup → 启动器补全 → 主界面 实机验收 |
| 高 | ~~壳层审查 high×4~~ **已修**（2026-07-28）：worker.pid 身份校验 / 音色包先校验再覆盖 / open_bootstrap→启动器.exe / 全局热键独立线程 |
| 中 | 审查清单其余 medium/low（见 `docs/审查缺陷清单.md`）；#29 status.json 竞态写已修（2026-07-29，diag_20260727） |
| 中 | 改 launcher 后需重打 exe 或发 gui_patch 才能在发行包看到（含 DPI/广场） |
| 中 | 125%/150% HiDPI 实机验收（96dpi 仅验了零变化基线） |
| 中 | 三变体全量/Setup 实机验收矩阵（启停/切音色/热更/监听/强杀） |
| 低 | MagiaDC 向 UX 打磨（排在验收之后） |
| 低 | 旧壳 `compare_versions` 无 `-partN` 时可能收不到更新提示（已知小尾巴） |
| 低 | 推理侧可选路线见 `PERF_NOTES.md` §5（ONNX/DML 等） |
| 低 | **壁纸 P2**（见下） |

**审查 backlog**：`docs/审查缺陷清单.md`（high 已修；其余按条修）。

**壁纸功能 P2 待办**（P0/P1 已修于 2026-07-29）：

| 项 | 说明 |
|----|------|
| 预览与全窗双算 | 滑条拖动时仅刷新设置卡小预览；全窗在松手 / 更长 debounce 后再刷（进一步减负载） |
| GIF 说明 | 文案已写「静态图」；若需动图再单独立项（当前解码只取可用帧） |
| 缺 Pillow 提示 | 壳应有 Pillow；若处理失败，底栏/设置状态行给一句人话，勿静默空白 |
| 色键契约测试 | 自动化难绑真实 hwnd；至少保持 `WALLPAPER_CHROMAKEY != TM_BG/SURFACE` 单测 + 实机点选「选择图片」按钮 |
| 主线程预览 | 预览小图仍可主线程；大图 decode 若变慢再下放到 worker |

### 已知坑（已修，需重打主程序壳）

- **现象**：Runtime 补全成功，打开主程序闪退 / 控制台 `ModuleNotFoundError: No module named 'numpy'`，栈在 `settings_page` → `tools.dsp_fx`。
- **原因**：设置页为 EQ 文案导入 `tools.dsp_fx`；旧版该模块**顶层** `import numpy`。主程序是 **PyInstaller 壳**（无 numpy），numpy 只在 **Runtime 3.9** 给 worker 用。
- **修复**：`tools/dsp_fx.py` 改为惰性导入 numpy；`EQ_*` 常量纯 Python。改后需 **重打 `变声器.exe` / GUI 补丁** 才进用户包。

- **现象**：worker `status=starting` / `pid=0`，UI「引擎错误 · CPU · empty probe」。
- **原因**：Runtime 子进程起不来或探测失败；旧版崩溃无日志；发行包曾污染 `configs/inuse` 开发机路径。
- **修复**：worker/VBS 落盘崩溃日志；`inuse` 消毒；`_env_for_runtime_python` 深度清洗；**Runtime 完整性校验**（CNB `runtime/<variant>/integrity-*.json`）。**2026-07-29 跟进**（diag_20260727_151048）：nvidia 包在 probe 空失败时不再把 `TM_ACCEL_RESOLVED` 打成 cpu（与 amd 包信任 DML 对称）；worker 侧仍会真实探测 CUDA。

- **现象**：`realtime_worker.log` 刷 `PermissionError: [WinError 5] ... status.json.tmp -> status.json`（滑条热更/心跳写状态时）。
- **原因**：壳与 worker 并发写同一固定名 `.tmp`，Windows 读者占用目标文件时 `replace` 失败且无重试。
- **修复**：`realtime_protocol._write_json` 唯一临时名 + 重试 + 失败回退直写（审查 #29）。

- **现象（Kara / 最新 Setup）**：安装后一点启动器或主界面就  
  `ModuleNotFoundError: No module named 'tkinter'`（栈在 `bootstrap.py` / `main_app.py`）；  
  偶发 `Failed to load Python DLL …\python310.dll`（file being used by another process）。
- **原因**：壳 exe 曾用 **TRAE SOLO 等 IDE agent 内嵌精简 Python 3.10** 打包（路径含 `ModularData\ai-agent\vm\tools\python`），**无 tkinter/_tkinter**；PyInstaller 仅在 warn 写 missing 仍生成 exe。UPX 压 DLL + onefile 解压占用会加剧 DLL 加载失败。
- **修复**：`ensure_shell_ui_deps()` 打包前硬校验 tkinter；拒绝 agent 精简解释器；hidden-import 全量 tkinter 栈；warn 仍缺 tkinter 则中止；`--noupx`。必须用完整 CPython（如 `py -3.13`）重打 `RVC_Fabric_Setup.exe` 再发用户。

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

**RVC Fabric 功能侧已齐；Runtime 已在 CNB Release 就绪；安装动线为 Setup 薄包 + 启动器补 Runtime + 社区 LFS 音色。**  
下一步：**Setup → 补全 → 变声 实机验收**；代码真相以 `git log` + 源码为准。
