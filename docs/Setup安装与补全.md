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

**用户动线**：Setup 装壳 → 启动器下 Runtime（分版）→ 下 engine-core（共用）→ 可选 VB-Cable → 主界面变声。

**下载体验（启动器）**：补全面板显示 **第 i/n 步**、剩余步骤、当前文件进度 / 速度 / ETA。大文件走 **多连接 HTTP Range**（默认最多 16 连接，可断点续传 `.part`）；服务器不支持 Range 时自动回落单连接。

---

## 安装器技术

- **Inno Setup 6**：`installer/RVC_Fabric_Setup.iss`
- 打包：`python scripts/build_setup.py`
- 本机 ISCC 示例：`K:\jihuang\Inno Setup 6\ISCC.exe`（或环境变量 `ISCC`）

### 用户机不需要 Python

| 角色 | 是什么 |
|------|--------|
| 用户拿到的 | `RVC_Fabric_Setup.exe` → 安装后的 `启动器.exe` / `变声器.exe` |
| 启动器.exe | **PyInstaller 自带嵌入式解释器**，并打包 `requests` 等下载依赖 |
| 系统 Python | **不需要**；用户没装 Python 也能点「补全运行环境」从 CNB 下 Runtime |
| 打包机 Python | **需要**（仅你这边打包用），且必须能 `pip install requests` 以便打进 exe |

若打包机漏装 requests，打出的启动器会在补全时失败——`build_setup.py` / `build_release.py` 已在打包前自动 `ensure_shell_download_deps()`。

---

## 用户动线

1. 下载并运行 `RVC_Fabric_Setup.exe`（薄包，仅壳层）
2. 选目录 + 显卡分版 → 安装启动器 / 主界面
3. **启动器**从 CNB 依次下载：**Runtime**（分版）→ **engine-core**（共用）→ VB-Cable 包
4. 主界面 → 新手指引 → 社区音色 → 变声

---

## 打包命令

```bat
set ISCC=K:\jihuang\Inno Setup 6\ISCC.exe
python scripts\build_setup.py --clean
```

产出：`dist\RVC_Fabric_Setup.exe`  

校验：payload / 安装目录下 **不得** 有 `Runtime\python.exe`，也 **不得** 有 hubert/rmvpe 大权重或 ffmpeg/ffprobe（这些走 CNB engine-core）。
