# Setup 安装与环境补全

产品名：**RVC Fabric**  
制品仓：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases  

## 职责边界（勿混淆）

| 内容 | 放哪里 | 说明 |
|------|--------|------|
| **Runtime**（绿色 Python / torch） | **仅 CNB**（`runtime/` + Release 标签 `RVC-runtime`） | 体积数 GB；安装后由**启动器**下载 |
| 软件壳、启动器、主界面 | **Setup 安装包** | Inno Setup 打进 `RVC_Fabric_Setup.exe` |
| hubert / rmvpe / ffmpeg 等 | **Setup 安装包** | 与 `build_release.copy_engine` 一致，**不是** CNB Runtime 的一部分 |
| 社区音色 voice_pack | CNB LFS（可选） | 软件内「社区下载」 |

**不要**把 hubert/ffmpeg 从 Setup 里删掉再指望 CNB 只传 Runtime 时能补上。  
CNB 上你上传的大环境 = **Runtime**；Setup 负责其余可安装文件。

---

## 安装器技术

- **Inno Setup 6**：`installer/RVC_Fabric_Setup.iss`
- 打包：`python scripts/build_setup.py`
- 本机 ISCC 示例：`C:\Program Files (x86)\Inno Setup 6\ISCC.exe`（或环境变量 `ISCC`）

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

1. 下载并运行 `RVC_Fabric_Setup.exe`
2. 选目录 + 显卡分版 → 安装壳层与引擎资源
3. **启动器**从 CNB 下载对应分版 **Runtime**
4. 主界面 → 新手指引 → 社区音色 → 变声

---

## 打包命令

```bat
set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
python scripts\build_setup.py --clean
```

产出：`dist\RVC_Fabric_Setup.exe`  

校验：payload / 安装目录下 **不得** 有 `Runtime\python.exe`；**应有** hubert / rmvpe / ffmpeg（若本机 RVCMAX 或 assets 已备齐）。
