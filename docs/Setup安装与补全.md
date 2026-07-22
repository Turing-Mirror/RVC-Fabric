# Setup 安装与环境补全

产品名：**RVC Fabric**  
制品仓：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases  

## 安装器技术（不要自写）

| 角色 | 技术 | 说明 |
|------|------|------|
| **Setup.exe** | **Inno Setup 6** | 业界常用 Windows 安装器（选目录、快捷方式、卸载、任务页选显卡） |
| 脚本 | `installer/RVC_Fabric_Setup.iss` | 唯一正式安装器定义 |
| 启动器 | 现有 `launcher/bootstrap.py` → `启动器.exe` | 安装**之后**补全 Runtime（CNB Release） |
| 主界面 | 现有 `launcher/main_app.py` → `变声器.exe` | 日常变声 |

**不要**用自写 Tk/PyInstaller「Setup 向导」代替 Inno。  
`launcher/setup_app.py` 已废弃，仅保留测试/应急。

同类可选技术（本仓库未采用）：NSIS、WiX/MSI、Advanced Installer。Inno 对独立软件体积与中文任务页足够，且免费。

---

## 定稿用户动线

1. 下载 **`RVC_Fabric_Setup.exe`**（Inno 打出的安装器）  
2. 运行 Setup → 选安装目录 → **选显卡分版** → 创建快捷方式  
3. 完成后打开 **启动器** → 自动从 CNB **Release** 下载 Runtime  
4. 主界面 → 新手指引 → 社区下载音色（CNB **LFS**）→ 变声 → 调参/优化/进群  

## 分发约定

| 内容 | 通道 |
|------|------|
| Setup.exe | CNB `setup/`（LFS 或 Release 均可） |
| Runtime | CNB **Release** 标签 `RVC-runtime` |
| 音色 | CNB Git LFS `…/-/lfs/<sha256>` |

---

## 打包机：打 Setup

1. 安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php)  
2. 仓库根目录：

```bat
python scripts/build_setup.py --clean
```

产出：

- `dist/RVC_Fabric_Setup_payload/` — 薄包内容（无 Runtime）  
- `dist/RVC_Fabric_Setup.exe` — **用户下载的安装器**  
- `dist/Setup.exe` — 同上别名  

拷到 CNB 暂存：

```bat
python scripts/build_setup.py --copy-cnb
```

仅准备 payload、本机暂无 Inno：

```bat
python scripts/build_setup.py --payload-only
```

环境变量 `ISCC` 可指向非默认路径的 `ISCC.exe`。

---

## 职责边界

```text
Inno Setup          装文件、快捷方式、卸载、写入 package_meta / setup_pending
启动器 bootstrap    检测 Runtime → CNB 下载解压 → 声卡/快捷方式/打开主界面
主界面 main_app     变声、社区音色、档案、咨询包…
```

关键代码：

| 路径 | 职责 |
|------|------|
| `installer/RVC_Fabric_Setup.iss` | 正式 Setup |
| `scripts/build_setup.py` | payload + 调 ISCC |
| `launcher/bootstrap.py` | 启动器 / Runtime 补全 |
| `launcher/cnb_sources.py` | CNB URL / 清单 |
| `launcher/runtime_provision.py` | 下载与解压 Runtime |

---

## 开发调试（不经 Inno）

```bat
python launcher\bootstrap.py
```

或 `OpenSetup.vbs`。  
有 Runtime 时再开主界面：`OpenApp.vbs`。
