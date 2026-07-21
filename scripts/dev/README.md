# 开发用启动脚本（非发行入口）

| 文件 | 作用 |
|------|------|
| `start.bat` | 首次设置启动器 |
| `start_app.bat` | 主界面 |
| `go-web.bat` | Gradio WebUI |
| `go-realtime-gui.bat` | 原版实时 GUI |

仓库根目录的 `start.bat` / `start_app.bat` 仅作薄封装，会转到这里。

**发给用户的发行版请用** `scripts\build_release.bat` 打出的安装包（产品名 **RVC Fabric**；壳 exe 多为 `启动器.exe` / `变声器.exe`）。  
开发调试优先仓库根目录 **`OpenApp.vbs` / `OpenSetup.vbs`**（无黑框）。
