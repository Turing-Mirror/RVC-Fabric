<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
[简体中文](./README.md)　·　[繁體中文](./README_zh-TW.md)　·　English　·　[日本語](./README_ja.md)　·　[한국어](./README_ko.md)　·　[Español](./README_es.md)　·　[Français](./README_fr.md)　·　[Русский](./README_ru.md)
<!-- lang-nav -->

**Real-time voice changer and soundboard for Windows**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="RVC Fabric home screen and real-time conversion controls" width="32%">
<img src="assets/screenshots/settings.png" alt="RVC Fabric settings screen" width="32%">
<img src="assets/screenshots/misc.png" alt="RVC Fabric additional tools screen" width="32%">
<!-- screenshots -->

[Website](https://www.turingmirror.com/en/products/rvc-fabric/) · [User guide](https://www.turingmirror.com/en/guides/rvc-fabric/) · [Download for Windows](https://cdn.turingmirror.com/d/rvc-fabric-setup)

Based on [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) and maintained by [Turing Mirror](https://github.com/Turing-Mirror).

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[GitHub Repository](https://github.com/Turing-Mirror/RVC-Fabric) · [CNB Artifacts Download](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**Social Media**　[Bilibili @Turing Mirror](https://space.bilibili.com/3546871148579062)　·　[Douyin @Turing Mirror](https://v.douyin.com/6NxXcrKK9cc) (Douyin ID `TuringMirror`)　·　[Xiaohongshu @Turing Mirror](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094) (Xiaohongshu ID `TuringMirror`)　·　[YouTube @Turing Mirror](https://www.youtube.com/@TuringMirror) (YouTube handle `@TuringMirror`)　·　QQ Group @Turing Mirror Community (Group ID `1077458748`)

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="QQ group QR code" width="200">
<!-- qq-group -->

**Sponsorship & Promotion**　[Rainyun servers: 50% off the first month](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## Project Introduction

RVC Fabric is a free, open-source Windows application developed by Turing Mirror. Change your voice and play music or sound effects in QQ, Discord and in-game voice chat, or mix your voice with backing tracks during a live stream. Its soundboard supports audio clips and hotkeys, alongside voice model management, vocal separation and model training.

## Core Features

- Play music, sound effects or selected clips into voice chat alongside your converted microphone audio, with overlapping playback, looping, separate volume control and global hotkeys.
- Converts microphone input to the selected voice, with original-voice bypass, ASIO channel selection and independent monitoring. Latency depends on hardware, the model and audio settings.
- Includes a noise gate, compressor and 5-band parametric EQ, with presets and individual adjustments.
- The voice library supports associated .index files and lets you save, import and export parameter presets.
- Download voice models from Turing Mirror and third-party sources, track progress and resume interrupted downloads.
- Provides vocal separation, text-to-speech and voice training tools. The training workflow covers audio slicing, pitch and feature extraction, model training and index export.
- Supports NVIDIA CUDA and DirectML acceleration for AMD and Intel GPUs. Setup detects hardware and configures the corresponding runtime.

The Neptune development branch also provides mobile pairing, a local API and an MCP interface. Audio captured on the phone is converted on the desktop.

## Voice chat and in-game music playback

1. Install RVC Fabric and configure the required components. Install the VB-Cable virtual audio device and restart your computer.
2. In the audio device settings, select your physical microphone and set the output to CABLE Input. Set the microphone in QQ, Discord or your game to CABLE Output.
3. Open the audio library, import music or sound effects, and double-click an entry to play it into voice chat. To change your voice while playing music, select a voice model and start conversion. Both signals are mixed into the same output.
4. Select headphones for local monitoring and enable music monitoring as needed. Assign global hotkeys to frequently used clips to play, pause and stop them while in a game.

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
- **Frontend unit tests**: `cd app && npm test`
- **Package Installer (NSIS)**: `cd app && npm run tauri:build`
- **Package Full Offline Release**: `python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **Build Online Catalog**: `python scripts\build_catalog.py build --diff`

## Source code and voice permissions

- The source code of this project is open-sourced under the [MIT License](./LICENSE).
- Model weights, voice packages, and third-party resources follow their original licensing agreements.
- Obtain the rights holder’s permission before training on or converting someone else’s voice.

## Acknowledgements

Thanks to the following excellent open-source projects for providing technical support to RVC Fabric:

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Core algorithms and upstream foundation
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — Core acoustic models and pitch algorithms
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — Retrieval and real-time noise reduction
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — Optional pitch algorithms
- [PyMSS](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Vocal separation engine (follows upstream RVC; replaces UVR5) · [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) — Separation model source · [FFmpeg](https://github.com/FFmpeg/FFmpeg) — Audio processing
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — Virtual sound card (routes the converted voice into games and voice apps)
