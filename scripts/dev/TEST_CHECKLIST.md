# RVC Fabric 1.3.0 · 开发版 + Setup 测试清单

> 代码侧 Tauri 迁移：**主体已完成**（壳/补全/商店/设置/更新/删旧 Tk）。  
> 本清单用于你亲自验收「开发版」与「干净机 Setup 全流程」。  
> 日期基线：2026-07-31 · 版本 **1.3.0**

---

## 迁移完成了吗？

| 项 | 状态 |
|----|------|
| 单一 `RVC Fabric.exe`（Tauri） | 代码完成 |
| 删 Python/Tk 壳 | 代码完成 |
| 补全 Runtime / engine-core / VB-Cable | 代码完成 |
| 音色 / 商店 / 设置 / 托盘 / 热键 / 诊断 | 代码完成 |
| 界面 OTA（gui_patch） | 代码完成 |
| 整包签名更新（策略 B） | 代码有，**公钥/密钥未正式投产**，本轮可不测自动换 exe |
| **干净机实机矩阵** | **未完成 → 就是你要测的** |

结论：**可以按 1.3.0 做开发版与 Setup 验收**；测完前不要当「已正式发版」。

---

## 0. 先跑自动准备

在仓库根：

```bat
scripts\dev\check_test_env.ps1
scripts\dev\run_smoke_tests.bat
```

| 退出码 | 含义 |
|--------|------|
| 0 | 开发 + Setup 工具链就绪 |
| 2 | 开发环境缺东西（Node/Rust/MSVC…） |
| 3 | 开发可用，但 Inno/ISCC 未就绪 |

本机已确认过的路径示例：

- `F:\VS2022\BuildTools\...vcvars64.bat`
- `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`
- 仓库根已有 `Runtime\pythonw.exe`（开发版测变声用）

准备阶段已修/已验：

- `build_setup.py` 不再错误要求旧 `启动器.exe` / `变声器.exe`（否则 Setup 永远打不出）
- `provision.rs` 补上 `use std::process::Command`（否则 `tauri:dev` / `cargo test` 编不过）
- 环境检查脚本：`RESULT: DEV + SETUP env ready`
- Rust 单测：**35 passed**（`app/src-tauri`）

---

## A. 开发版测试

### A1. 启动

```bat
scripts\dev\tauri-dev.bat
```

不要直接 `npm run tauri:dev`（除非当前窗口已 call 过 vcvars，否则常缺 `link.exe`）。

期望：

- [ ] 弹出 RVC Fabric 窗口（不是浏览器-only）
- [ ] 六页导航可点：首页 · 广场 · 模型 · 设置 · 说明 · 其他
- [ ] 底栏有：模式分段、电平表、音高/共鸣、开启变声

### A2. 有 Runtime 时（仓库根已有 Runtime）

- [ ] 若已补全过：不应卡在 ProvisionGate；否则应能走完补全
- [ ] 模型页能看到本地音色（`User_Data\models`）
- [ ] 点首页卡片 /「使用」能切换音色
- [ ] **开启变声**后：麦克风说话，电平表动；延迟数字更新
- [ ] 热更音高/共鸣立即生效
- [ ] 输出变声 / 原声旁路可切换
- [ ] 停止变声后设备释放

### A3. 设置与其它

- [ ] 设置八个子标签都能改并保存（重开仍在）
- [ ] 冷键（设备等）改后提示需重新开启变声
- [ ] 说明页有虚拟声卡说明；有安装 VB-Cable 入口
- [ ] 其他页：检查更新、生成诊断包（约 1 分钟 bench）、界面来源一行
- [ ] 关窗：托盘 / 退出 / 询问；托盘菜单可开停变声
- [ ] 热键：Ctrl+F2 开关；F5/F6 切音色（若未禁用热键）

### A4. 商店（需网络）

- [ ] 社区音色列表能刷出
- [ ] 下载安装一个官方音色成功
- [ ] 取消某个下载不影响另一个（若测并发）

### A5. 日志位置（出问题先看）

| 文件 | 用途 |
|------|------|
| `User_Data\logs\realtime_worker.log` | worker 崩 / 起不来 |
| `User_Data\runtime_control\status.json` | 引擎状态 |
| `User_Data\app_config.json` | 界面设置真相 |
| 终端 tauri dev 输出 | Rust 命令错误 |

开发时产品根 = 仓库根（`TM_VOICE_ROOT` 由 `tauri-dev.bat` 设置）。

---

## B. Setup 全流程测试（模拟新用户）

### B1. 打安装包

```bat
scripts\dev\build_setup.bat
```

等价：

```bat
set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
call F:\VS2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat
python scripts\build_setup.py --clean
```

期望产物：

- [ ] `dist\RVC_Fabric_Setup.exe`
- [ ] `dist\RVC_Fabric_Setup_payload\RVC Fabric.exe`
- [ ] `dist\RVC_Fabric_Setup_payload\frontend\index.html`
- [ ] **没有** `启动器.exe` / `变声器.exe` / `launcher\pages`

可选拷到制品仓（不自动推送）：

```bat
scripts\dev\build_setup.bat --copy-cnb
```

### B2. 干净安装（推荐虚拟机或另一用户目录）

1. 卸载旧版 RVC Fabric（若有）
2. 删干净安装目录（默认常在 `%LocalAppData%\RVC Fabric`）
3. **不要**把开发机 `User_Data` 拷进去（测的是从零）
4. 双击 `dist\RVC_Fabric_Setup.exe` 安装
5. 只应出现一个快捷方式：**RVC Fabric**（不是启动器+变声器）

勾选：

- [ ] 安装完成能启动
- [ ] 安装目录有 `RVC Fabric.exe` + `frontend\` + `gui_v1.py` + `tools\`
- [ ] 无 Runtime 时出现 **补全面板**（ProvisionGate）

### B3. 首次补全（需能访问 CNB）

- [ ] 自动推荐 Runtime 类型（nvidia / nvidia50 / amd），可改选
- [ ] 下载 Runtime 进度可见，失败有可见错误（不是静默）
- [ ] engine-core 下载并就绪
- [ ] VB-Cable：失败应**不挡**进主界面；说明页可再装
- [ ] 全部必要项完成后能进主界面

### B4. 从零到出声

- [ ] 社区下载至少一个音色 **或** 导入本地 `.pth`
- [ ] 设置页选好输入麦 / 输出 CABLE Input / 监听耳机
- [ ] 开启变声，游戏或听诊里能听到变声（至少监听能听到）
- [ ] 关到托盘继续出声；托盘退出后 worker 停

### B5. 升级路径（若你有 1.2.x 旧装）

- [ ] 在旧目录上装 1.3.0 Setup
- [ ] 旧的 `启动器.exe` / `变声器.exe` 被清掉
- [ ] `Runtime\` 与 `User_Data\` 还在
- [ ] 设备与上次音色不丢（或合理从 app_config 恢复）
- [ ] 不会两个壳同时抢声卡

### B6. 安装后日志

`%LocalAppData%\RVC Fabric\User_Data\logs\`（若装在默认路径）

---

## C. 已知本轮可不卡死的项

| 项 | 说明 |
|----|------|
| 策略 B 自动换 exe | 需正式签名密钥；pubkey 现为空/占位 |
| 广告三类型角标像素级 | 解析规则已定，内容 feed 可后续 |
| Mac 上打 Windows 包 | 必须在本机 Windows 打 |

---

## D. 一键命令速查

| 目的 | 命令 |
|------|------|
| 查环境 | `scripts\dev\check_test_env.ps1` |
| 烟雾测试 | `scripts\dev\run_smoke_tests.bat` |
| 开发版 | `scripts\dev\tauri-dev.bat` |
| 仅 UI（无原生） | `cd app && npm run dev` |
| 打 Setup | `scripts\dev\build_setup.bat` |
| Python 测 | `scripts\run_tests.bat` 或 `python -m unittest discover -s tests -p "test_*.py" -v` |
| Rust 测 | `cd app\src-tauri && cargo test`（先 vcvars） |

测完请把失败项记下来（现象 + 日志片段 + 是否开发版/Setup），便于修。
