# Setup 安装与环境补全

产品名：**RVC Fabric**  
制品仓：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases  

## 职责边界（勿混淆）

| 内容 | 放哪里 | 说明 |
|------|--------|------|
| **Runtime**（绿色 Python / torch） | **仅 CNB**（按显卡：nvidia / amd / nvidia50） | 体积数 GB；启动器下载 |
| **engine-core**（hubert / rmvpe / ffmpeg / ffprobe） | **仅 CNB LFS**（`assets/core/engine-core-*.zip`） | **全显卡共用**；启动器在 Runtime 之后下载 |
| 软件壳、启动器、主界面、引擎源码 | **Setup 薄包** | Inno Setup → `RVC_Fabric_Setup.exe` |
| VB-Cable | **CNB LFS** | Runtime/engine-core 后再下 |
| 社区音色 voice_pack | CNB LFS | 软件内「社区下载」 |

**用户动线**：Setup 装壳 → 启动器下 Runtime（分版）→ **完整性校验**（关键文件 + torch 导入）→ 下 engine-core（共用）→ 可选 VB-Cable → 主界面变声。

### Runtime 完整性（类 Steam 校验）

| 项 | 说明 |
|----|------|
| 清单生成 | `python scripts/gen_runtime_integrity.py --runtime <Runtime目录> --variant nvidia --version 2026.07.21 --out CNB-GIT-RELEASE/runtime/nvidia/integrity-2026.07.21.json --alias` |
| 上传 CNB | 小 JSON 走 git raw：`runtime/<variant>/integrity-<version>.json`（及 `integrity.json` 别名） |
| 软件拉取 | 补全 Runtime 后自动校验；主界面「其他 → 校验 Runtime 完整性」可手动重跑 |
| 本地报告 | `User_Data/logs/runtime_integrity_last.json` |
| 离线兜底 | `configs/runtime_integrity/<variant>.json`（打进 Setup 壳时可选） |

### 发行包禁止污染

- `configs/inuse/config.json` **不得**含开发机绝对路径（`L:\…` 等）
- Setup 打包时 `sanitize_inuse_config` 强制写入干净模板
- 启动时 `ensure_clean_inuse_config` 会清掉外盘绝对路径

**下载体验（启动器）**：补全面板显示 **第 i/n 步**、剩余步骤、当前文件进度 / 速度 / ETA。大文件走 **多连接 HTTP Range**（默认最多 16 连接，可断点续传 `.part`）；服务器不支持 Range 时自动回落单连接。

---

## 安装器技术

- **Inno Setup 6**：`installer/RVC_Fabric_Setup.iss`
- 打包：`python scripts/build_setup.py`
- 本机 ISCC 示例：`C:\Program Files (x86)\Inno Setup 6\ISCC.exe`（或环境变量 `ISCC`）

### 用户机不需要 Python

| 角色 | 是什么 |
|------|--------|
| 用户拿到的 | `RVC_Fabric_Setup.exe` → 安装后的 `启动器.exe` / `变声器.exe` |
| 启动器.exe | **PyInstaller 自带嵌入式解释器**，并打包 `requests`、**tkinter/Tcl-Tk** 等 |
| 系统 Python | **不需要**；用户没装 Python 也能点「补全运行环境」从 CNB 下 Runtime |
| 打包机 Python | **需要完整 CPython**（含 Tcl/Tk），且能 `pip install requests Pillow` |

打包前会跑：

- `ensure_shell_download_deps()`：缺 requests/Pillow 则自动装  
- `ensure_shell_ui_deps()`：**硬失败**若无 `tkinter` / `_tkinter`，或解释器路径像 IDE agent 精简 Python  
- Analysis 后若 warn 仍有 `missing module named tkinter` → **中止打包**（禁止发出坏壳）  
- `--noupx`：避免 UPX 压 `pythonXY.dll` 后用户机 LoadLibrary / 文件占用失败  

### 已知坑（Kara 报告，2026-07）

| 现象 | 原因 | 处理 |
|------|------|------|
| `ModuleNotFoundError: No module named 'tkinter'`（`bootstrap` / `main_app`） | 用 **TRAE 等 IDE 自带精简 Python 3.10** 打包，stdlib 无 tkinter；PyInstaller 只 warn 仍产出 exe | 用本机完整 CPython（如 3.13）重打 Setup；脚本已拦截 |
| `Failed to load Python DLL … python310.dll`（being used by another process） | onefile 解压 `_MEI*` 时 DLL 被占用，或 UPX 压 DLL | 关杀软/旧进程后重开；打包已 `--noupx` |
| 旧版「引擎错误 · empty probe」 | worker 起不来 / inuse 污染开发机路径 | 完整性校验 + inuse 消毒（见 CONTEXT_HANDOFF） |

**正确打包**：

```bat
REM 不要用 TRAE/Cursor agent 内嵌 python
py -3.13 scripts\build_setup.py --clean
```

---

## 用户动线

1. 下载并运行 `RVC_Fabric_Setup.exe`（薄包，仅壳层）
2. 选目录 + 显卡分版 → 安装启动器 / 主界面
3. **启动器**从 CNB 依次下载：**Runtime**（分版）→ **engine-core**（共用）→ VB-Cable 包
4. 主界面 → 新手指引 → 社区音色 → 变声

---

## 打包命令

```bat
set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
python scripts\build_setup.py --clean
```

产出：`dist\RVC_Fabric_Setup.exe`  

校验：payload / 安装目录下 **不得** 有 `Runtime\python.exe`，也 **不得** 有 hubert/rmvpe 大权重或 ffmpeg/ffprobe（这些走 CNB engine-core）。
