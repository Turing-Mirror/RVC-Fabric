# 开发用脚本（非发行入口）

| 文件 | 作用 |
|------|------|
| **`check_test_env.ps1`** | 检查 Node/Rust/MSVC/ISCC/Runtime 是否就绪 |
| **`tauri-dev.bat`** | **开发版主入口**（先 vcvars 再 `npm run tauri:dev`） |
| **`build_setup.bat`** | 打 `dist\RVC_Fabric_Setup.exe`（`--clean`） |
| **`run_smoke_tests.bat`** | 环境检查 + Python/Rust 单测 |
| **`TEST_CHECKLIST.md`** | 开发版 + Setup 人工验收清单 |
| `go-web.bat` | 上游 Gradio WebUI |
| `go-realtime-gui.bat` | 上游实时 GUI（需 Runtime） |

## 你现在要测什么

1. **开发版（仓库根 Runtime + 源码）**  
   `scripts\dev\tauri-dev.bat`

2. **Setup 从零全流程**  
   `scripts\dev\build_setup.bat`  
   → 安装 `dist\RVC_Fabric_Setup.exe`  
   → 按 `TEST_CHECKLIST.md` §B 勾选

## 注意

- 发行物是 **Tauri** 单一 `RVC Fabric.exe`，不再有启动器.exe / 变声器.exe。  
- 直接 `npm run tauri:dev` 容易因缺 MSVC `link.exe` 失败；请用 `tauri-dev.bat`。  
- 产品根：开发时 = 仓库根；安装后 = exe 所在目录。
