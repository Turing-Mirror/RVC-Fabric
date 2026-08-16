<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
简体中文　·　[繁體中文](./README_zh-TW.md)　·　[English](./README_en.md)　·　[日本語](./README_ja.md)　·　[한국어](./README_ko.md)　·　[Español](./README_es.md)　·　[Français](./README_fr.md)　·　[Русский](./README_ru.md)
<!-- lang-nav -->

**高性能实时 AI 变声桌面客户端**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="Home" width="32%">
<img src="assets/screenshots/settings.png" alt="Settings" width="32%">
<img src="assets/screenshots/misc.png" alt="More" width="32%">
<!-- screenshots -->

基于 [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) 深度定制 · 由 [图灵镜 Turing Mirror](https://github.com/Turing-Mirror) 开发维护

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[GitHub 仓库](https://github.com/Turing-Mirror/RVC-Fabric) · [CNB 制品下载](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**社媒**　[哔哩哔哩 @图灵镜](https://space.bilibili.com/3546871148579062)　·　[抖音 @图灵镜](https://v.douyin.com/6NxXcrKK9cc)（抖音号 `TuringMirror`）　·　[小红书 @图灵镜](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094)（小红书号 `TuringMirror`）　·　QQ 群 @图灵镜社区（群号 `1077458748`）

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="QQ 群二维码" width="200">
<!-- qq-group -->

**赞助推广**　[首月五折　·　性价比云服务器 / 游戏云 / 面板服　·　雨云](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## 项目简介

RVC Fabric 是面向 Windows 的实时 AI 变声桌面软件，开箱即用：不需要自己装 Python、PyTorch，也不用开浏览器点 Gradio 页面，安装完就能变声。

游戏开黑、语音连麦、直播互动、音频制作——低延迟、高还原的实时声线转换，一个软件全搞定。

## 核心特性

- **实时变声**：低延迟实时推理，变声中可无缝切换音色，「实时变声 / 旁路原声 (Bypass)」一键切换。
- **DSP 效果链**：内置后级噪声门、动态压缩器与 5 段参数均衡器，支持预设套用与精细调音。
- **音色与预设管理**：网格化音色库、.index 检索特征库绑定，参数预设可保存、导入、导出分享。
- **社区音色广场**：双源商店（图灵镜官方源 + 第三方开放源），多线程并发下载、断点续传。
- **内置音频工具箱**：
  - **人声分离**：基于 PyMSS 分离模型，快速提取干声与伴奏。
  - **语音合成**：输入文本生成语音，并自动转换为目标音色（TTS + RVC）。
  - **音色训练**：内置训练面板，一键训练专属音色（需 NVIDIA 显卡）。
- **全自动硬件加速**：NVIDIA CUDA（含 RTX 50 系列）与 AMD / Intel（DirectML）自动识别，并下载对应的计算运行时。

## 快速开始

### 1. 安装与初始化

1. 从 [Releases 页面](https://github.com/Turing-Mirror/RVC-Fabric/releases) 下载 `RVC_Fabric_Setup.exe`；
2. 运行安装程序（建议安装到纯英文路径）；
3. 启动软件，跟随引导自动完成硬件识别、运行时补全与虚拟声卡安装。

### 2. 音频路由（虚拟声卡接法）

想让游戏、QQ、Discord 或直播软件里的人听到变声，需要 VB-Cable 虚拟声卡在中间转一手：

| 配置项 | 推荐选择 | 说明 |
| :--- | :--- | :--- |
| **软件输入** | 真实麦克风 | 采集原始说话声音 |
| **软件输出** | **CABLE Input** | 把变声结果送进虚拟声卡 |
| **监听（可选）** | 物理耳机 / 音箱 | 本地实时试听变声效果 |
| **游戏 / 语音麦克风** | **CABLE Output** | 第三方软件接收变声效果 |
| **Windows 默认播放** | 物理耳机（不要选 CABLE） | 保证系统其他声音正常播放 |

## 技术架构与开发

### 架构

RVC Fabric 采用 **Tauri + Rust + React** 桌面外壳，后台由 **Python Worker** 承担全部计算，两者通过 JSON 文件协议通信：

```
RVC Fabric.exe (Tauri + Rust + React 前端主界面)
    │
    ▼ JSON 文件协议 (command.json / status.json / worker.pid)
Runtime\pythonw.exe tools/realtime_worker.py (Python 3.9 + CUDA / DirectML)
    └─> gui_v1.py (AudioIoProcess + rtrvc 实时推理引擎)
```

上游训练 / 推理 WebUI（Gradio）作为高级功能随包保留，可从「其他」页打开。

### 环境要求与开发

**环境要求**：Windows 10/11 · Node.js 20+ · Rust Stable · Python 3.13（开发脚本）

```bash
# 1. 安装前端依赖
cd app
npm install

# 2. 启动桌面端开发模式 (需要 WebView2 与 MSVC 工具链)
npm run tauri:dev

# 3. 仅启动 UI 浏览器预览
npm run dev
```

### 构建与测试

- **单元测试**：运行 `scripts\run_tests.bat`
- **打包安装程序（NSIS）**：`cd app && npm run tauri:build`
- **打包全量离线包**：`python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **构建在线清单**：`python scripts\build_catalog.py build --diff`

## 开源许可与免责声明

- 本项目源码采用 [MIT License](./LICENSE) 许可协议开源。
- 模型权重、音色包及第三方资源遵循其原始许可协议。
- **免责声明**：请勿将本软件用于伪造身份、欺诈或其他违法用途。使用他人声音进行训练或转换前，请取得原权利人授权。使用者应遵守当地法律法规。

## 致谢

感谢以下优秀开源项目为 RVC Fabric 提供的技术支持：

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — 核心算法与上游基础
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — 核心声学模型与音高算法
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — 检索与实时降噪
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — 可选音高算法
- [PyMSS](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — 人声分离引擎（跟随上游 RVC，已取代 UVR5）· [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) — 分离模型来源 · [FFmpeg](https://github.com/FFmpeg/FFmpeg) — 音频处理
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — 虚拟声卡（游戏里听到变声靠它）
