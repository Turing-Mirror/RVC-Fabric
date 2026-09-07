# 开发用脚本（非发行入口）

| 文件 | 作用 |
|------|------|
| **`check_test_env.ps1`** | 检查 Node/Rust/MSVC/ISCC/Runtime 是否就绪 |
| **`tauri-dev.bat`** | **开发版主入口**（设置产品根和隔离 Cargo 缓存后运行 `npm.cmd run tauri:dev`） |
| **`build_setup.bat`** | 打 `dist\RVC_Fabric_Setup.exe`（`--clean`） |
| **`run_smoke_tests.bat`** | 环境检查 + Python/Rust 单测 |
| **`TEST_CHECKLIST.md`** | 开发版 + Setup 人工验收清单 |

## 你现在要测什么

1. **开发版（仓库根 Runtime + 源码）**  
   `scripts\dev\tauri-dev.bat`

2. **Setup 从零全流程**  
   `scripts\dev\build_setup.bat`  
   → 安装 `dist\RVC_Fabric_Setup.exe`  
   → 按 `TEST_CHECKLIST.md` §B 勾选

## 注意

- 发行物是 **Tauri** 单一 `RVC Fabric.exe`，不再有启动器.exe / 变声器.exe。  
- `tauri-dev.bat` 不写死某台机器的 VS 路径；请在已配置 C++ 工具链的终端中运行。
- 产品根：开发时 = 仓库根；安装后 = exe 所在目录。
