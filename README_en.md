<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
[简体中文](./README.md)　·　[繁體中文](./README_zh-TW.md)　·　English　·　[日本語](./README_ja.md)　·　[한국어](./README_ko.md)　·　[Español](./README_es.md)　·　[Français](./README_fr.md)　·　[Русский](./README_ru.md)
<!-- lang-nav -->

**High-Performance Real-time AI Voice Changer Desktop Client**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="Home" width="32%">
<img src="assets/screenshots/settings.png" alt="Settings" width="32%">
<img src="assets/screenshots/misc.png" alt="More" width="32%">
<!-- screenshots -->

Deeply customized based on [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) · Developed and maintained by [Turing Mirror](https://github.com/Turing-Mirror)

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[GitHub Repository](https://github.com/Turing-Mirror/RVC-Fabric) · [CNB Artifacts Download](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**Social Media**　[Bilibili @Turing Mirror](https://space.bilibili.com/3546871148579062)　·　[Douyin @Turing Mirror](https://v.douyin.com/6NxXcrKK9cc) (Douyin ID `TuringMirror`)　·　[Xiaohongshu @Turing Mirror](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094) (Xiaohongshu ID `TuringMirror`)　·　QQ Group @Turing Mirror Community (Group ID `1077458748`)

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="QQ group QR code" width="200">
<!-- qq-group -->

**Sponsorship & Promotion**　[50% off for the first month · Cost-effective Cloud Server / Game Cloud / Panel Server · RainYun](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## Project Introduction

RVC Fabric is a real-time AI voice changer desktop software for Windows, ready to use out of the box: no need to install Python or PyTorch yourself, and no need to open a browser to click on Gradio pages. You can change your voice immediately after installation.

Gaming with friends, voice chat, live interactive streaming, audio production—low latency, high fidelity real-time voice conversion, all done with one software.

## Core Features

- **Real-time Voice Changing**: Low latency real-time inference, seamless switching of voices during conversion, one-click switch between "Real-time Voice Changing / Bypass".
- **DSP Effect Chain**: Built-in post-level noise gate, dynamic compressor, and 5-band parametric equalizer, supporting preset application and fine tuning.
- **Voice and Preset Management**: Grid-based voice library, .index retrieval feature library binding, parameter presets can be saved, imported, exported, and shared.
- **Community Voice Square**: Dual-source store (Turing Mirror official source + third-party open source), multi-threaded concurrent download, resumable download.
- **Built-in Audio Toolkit**:
  - **Vocal Separation**: Based on the PyMSS separation model, quickly extract dry vocals and accompaniment.
  - **Speech Synthesis**: Input text to generate speech, and automatically convert it to the target voice (TTS + RVC).
  - **Voice Training**: Built-in training panel, one-click training of exclusive voices (requires NVIDIA graphics card).
- **Fully Automatic Hardware Acceleration**: Automatic recognition of NVIDIA CUDA (including RTX 50 series) and AMD / Intel (DirectML), and download the corresponding computing runtime.

## Quick Start

### 1. Installation and Initialization

1. Download `RVC_Fabric_Setup.exe` from the [Releases page](https://github.com/Turing-Mirror/RVC-Fabric/releases);
2. Run the installer (it is recommended to install to a pure English path);
3. Start the software and follow the guide to automatically complete hardware recognition, runtime completion, and virtual sound card installation.

### 2. Audio Routing (Virtual Sound Card Setup)

To let people in games, QQ, Discord, or live streaming software hear the changed voice, you need the VB-Cable virtual sound card to route the audio:

| Configuration Item | Recommended Selection | Description |
| :--- | :--- | :--- |
| **Software Input** | Real Microphone | Capture original speaking voice |
| **Software Output** | **CABLE Input** | Send the changed voice result to the virtual sound card |
| **Monitor (Optional)** | Physical Headphones / Speakers | Listen to the voice changing effect locally in real time |
| **Game / Voice Chat Microphone** | **CABLE Output** | Third-party software receives the voice changing effect |
| **Windows Default Playback** | Physical Headphones (Do NOT select CABLE) | Ensure normal playback of other system sounds |

## Technical Architecture and Development

### Architecture

RVC Fabric uses a **Tauri + Rust + React** desktop shell, with all computations handled by a background **Python Worker**. The two communicate via JSON file protocol:

```
RVC Fabric.exe (Tauri + Rust + React frontend main interface)
    │
    ▼ JSON file protocol (command.json / status.json / worker.pid)
Runtime\pythonw.exe tools/realtime_worker.py (Python 3.9 + CUDA / DirectML)
    └─> gui_v1.py (AudioIoProcess + rtrvc real-time inference engine)
```

The upstream training / inference WebUI (Gradio) is kept with the package as an advanced feature, which can be opened from the "Other" page.

### Environmental Requirements and Development

**Environmental Requirements**: Windows 10/11 · Node.js 20+ · Rust Stable · Python 3.13 (development scripts)

```bash
# 1. Install frontend dependencies
cd app
npm install

# 2. Start desktop development mode (requires WebView2 and MSVC toolchain)
npm run tauri:dev

# 3. Only start UI browser preview
npm run dev
```

### Build and Test

- **Unit Tests**: Run `scripts\run_tests.bat`
- **Package Installer (NSIS)**: `cd app && npm run tauri:build`
- **Package Full Offline Release**: `python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **Build Online Catalog**: `python scripts\build_catalog.py build --diff`

## Open Source License and Disclaimer

- The source code of this project is open-sourced under the [MIT License](./LICENSE).
- Model weights, voice packages, and third-party resources follow their original licensing agreements.
- **Disclaimer**: Do not use this software for identity fraud, impersonation, or any other illegal purpose. Obtain the rights holder's authorization before training on or converting someone else's voice. Users are responsible for complying with local laws and regulations.

## Acknowledgements

Thanks to the following excellent open-source projects for providing technical support to RVC Fabric:

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Core algorithms and upstream foundation
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — Core acoustic models and pitch algorithms
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — Retrieval and real-time noise reduction
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — Optional pitch algorithms
- [PyMSS](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Vocal separation engine (follows upstream RVC; replaces UVR5) · [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) — Separation model source · [FFmpeg](https://github.com/FFmpeg/FFmpeg) — Audio processing
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — Virtual sound card (makes the changed voice heard in games)
