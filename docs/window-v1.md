# 最大化边距修复 v1

日期：2026-11-02。

## 行为

普通窗口继续使用原有无边框内容区。最大化时，内容区限制在目标显示器的可见工作区内，排除屏幕外的缩放边框。页面、标题栏、侧栏和底部控件的间距不做额外补偿；还原后回到原来的位置和大小。

## 实现

- 在 WM_NCCALCSIZE 中修正最大化的客户区矩形。按本次窗口提案所在显示器取工作区，使用物理坐标求交集，不写死边框厚度或缩放比例。
- 普通窗口保持原样，不恢复系统标题栏，不移除缩放样式，也不在最大化完成后强改外框。
- SetWindowSubclass 在 HWND 所属线程安装，先安装再改变边框样式。异步创建附属窗口时也遵循同一顺序。
- MSVC 构建为程序和原生测试嵌入 Common-Controls v6 依赖，与 Tauri 默认依赖一致。

Windows 客户区约定见 [WM_NCCALCSIZE](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-nccalcsize) 和 [NCCALCSIZE_PARAMS](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-nccalcsize_params)。线程限制见 [SetWindowSubclass](https://learn.microsoft.com/en-us/windows/win32/api/commctrl/nf-commctrl-setwindowsubclass)。

## 回归

在桌面壳的 Cargo.toml 所在目录运行：

```powershell
cargo test --locked --lib window_watch
cargo test --locked --lib frame_geometry -- --ignored --nocapture
```

纯几何用例覆盖隐藏边框、不同物理缩放尺寸、负坐标副屏、顶部或左侧任务栏。原生用例创建隔离 WebView 窗口，使用实际尺寸回调，检查主线程和后台线程初始化、最大化客户区等于工作区、连续三次还原后尺寸与位置不变。旧的 tool_frame_from_worker 过滤方式仍可运行此测试。

本次在 Windows 10 实测通过：12 项常规测试通过，原生窗口回归单独执行通过。主窗口与后台线程初始化窗口各连续最大化、还原三次，客户区均为 (0, 0, 1920, 1040)，与工作区完全一致，还原坐标与尺寸保持原值。

负坐标显示器、其他缩放尺寸和任务栏位置由纯几何用例验证；本次没有把它们表述为全部经过原生多屏目视验收。

这是桌面壳源代码修复；更新前端组件依赖不会替换产品中的 Rust 源文件。
