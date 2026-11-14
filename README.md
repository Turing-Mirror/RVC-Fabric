<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
简体中文　·　[繁體中文](./README_zh-TW.md)　·　[English](./README_en.md)　·　[日本語](./README_ja.md)　·　[한국어](./README_ko.md)　·　[Español](./README_es.md)　·　[Français](./README_fr.md)　·　[Русский](./README_ru.md)
<!-- lang-nav -->

**Windows 实时变声与语音音效播放软件**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="RVC Fabric 主界面与实时变声控制" width="32%">
<img src="assets/screenshots/settings.png" alt="RVC Fabric 设置页面" width="32%">
<img src="assets/screenshots/misc.png" alt="RVC Fabric 其他功能页面" width="32%">
<!-- screenshots -->

[官网](https://www.turingmirror.com/products/rvc-fabric/) · [下载 Windows 版](https://cdn.turingmirror.com/d/rvc-fabric-setup)

基于 [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) 开发，由 [图灵镜 Turing Mirror](https://github.com/Turing-Mirror) 维护。

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[GitHub 仓库](https://github.com/Turing-Mirror/RVC-Fabric) · [CNB 制品下载](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**社媒**　[哔哩哔哩 @图灵镜](https://space.bilibili.com/3546871148579062)　·　[抖音 @图灵镜](https://v.douyin.com/6NxXcrKK9cc)（抖音号 `TuringMirror`）　·　[小红书 @图灵镜](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094)（小红书号 `TuringMirror`）　·　[YouTube @图灵镜](https://www.youtube.com/@TuringMirror)（YouTube 号 `@TuringMirror`）　·　QQ 群 @图灵镜社区（群号 `1077458748`）

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="QQ 群二维码" width="200">
<!-- qq-group -->

**赞助推广**　[雨云服务器首月五折](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## 项目简介

RVC Fabric 是图灵镜开发的免费开源 Windows 软件，可在 QQ、Discord 和游戏语音中实时变声、播放音乐和音效，也可在直播中混合人声与伴奏。内置音频库支持片段管理与快捷键播放，并提供音色模型管理、人声分离和模型训练。

## 核心特性

- 音频库可将音乐、音效或选定片段播放到语音，与变声后的麦克风声音同时输出，支持叠加、循环、独立音量和全局快捷键。
- 将麦克风输入转换为所选音色，支持切换原声、ASIO 通道选择和独立监听。实际延迟取决于硬件、模型与音频设置。
- 内置噪声门、压缩器与 5 段参数均衡器，支持预设套用与精细调音。
- 音色库支持关联 .index 特征文件，并可保存、导入和导出参数预设。
- 可从 Kara251 和第三方来源下载获取音色模型，支持下载进度管理与中断后继续下载。
- 提供人声分离、文本转语音和音色训练工具。训练向导包含音频切分、音高与特征提取、模型训练和索引导出。
- 支持 NVIDIA CUDA，以及 AMD 和 Intel 显卡的 DirectML 加速。安装引导可识别硬件并配置对应的运行环境。

## 语音聊天与游戏内放歌

1. 安装 RVC Fabric，按引导配置所需组件。安装 VB-Cable 虚拟声卡后重启电脑。
2. 在「设备与音频」中选择实际麦克风，将输出设为 CABLE Input；在 QQ、Discord 或游戏的语音设置中，将麦克风设为 CABLE Output。
3. 打开「音频」，导入音乐或音效，双击条目即可播放到语音。需要边放歌边变声时，选择音色模型并开启变声，两路声音会混合输出。
4. 将本地监听设备设为耳机，按需开启音乐监听。可为常用片段设置全局快捷键，在游戏中控制播放、暂停和停止。

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
- **前端单元测试**：`cd app && npm test`
- **打包安装程序（NSIS）**：`cd app && npm run tauri:build`
- **打包全量离线包**：`python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **构建在线清单**：`python scripts\build_catalog.py build --diff`

## 开源许可与声音授权

- 本项目源码采用 [MIT License](./LICENSE) 许可协议开源。
- 模型权重、音色包及第三方资源遵循其原始许可协议。
- 使用他人声音进行训练或转换前，请取得声音权利人的授权。

## 致谢

感谢以下优秀开源项目为 RVC Fabric 提供的技术支持：

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — 核心算法与上游基础
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — 核心声学模型与音高算法
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — 检索与实时降噪
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — 可选音高算法
- [PyMSS](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — 人声分离引擎（跟随上游 RVC，已取代 UVR5）· [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) — 分离模型来源 · [FFmpeg](https://github.com/FFmpeg/FFmpeg) — 音频处理
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — 虚拟声卡（把变声结果送入游戏/语音软件）
