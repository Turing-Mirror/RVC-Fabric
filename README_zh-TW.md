<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
[简体中文](./README.md)　·　繁體中文　·　[English](./README_en.md)　·　[日本語](./README_ja.md)　·　[한국어](./README_ko.md)　·　[Español](./README_es.md)　·　[Français](./README_fr.md)　·　[Русский](./README_ru.md)
<!-- lang-nav -->

**Windows 即時 AI 語音轉換與模型訓練工作台**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="RVC Fabric 主畫面與即時變聲控制" width="32%">
<img src="assets/screenshots/settings.png" alt="RVC Fabric 設定頁面" width="32%">
<img src="assets/screenshots/misc.png" alt="RVC Fabric 其他功能頁面" width="32%">
<!-- screenshots -->

截圖為儲存庫保存的歷史介面，記錄於 2026 年 8 月。目前介面可能有所不同。

[官網](https://www.turingmirror.com/zh-hant/products/rvc-fabric/)

[使用指南](https://www.turingmirror.com/zh-hant/guides/rvc-fabric/)

[下載 Windows 版](https://cdn.turingmirror.com/d/rvc-fabric-setup)

基於 [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) 深度客製化 · 由 [圖靈鏡 Turing Mirror](https://github.com/Turing-Mirror) 開發維護

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[GitHub 倉庫](https://github.com/Turing-Mirror/RVC-Fabric) · [CNB 製品下載](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**社群媒體**　[嗶哩嗶哩 @圖靈鏡](https://space.bilibili.com/3546871148579062)　·　[抖音 @圖靈鏡](https://v.douyin.com/6NxXcrKK9cc)（抖音號 `TuringMirror`）　·　[小紅書 @圖靈鏡](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094)（小紅書號 `TuringMirror`）　·　[YouTube @圖靈鏡](https://www.youtube.com/@TuringMirror)（YouTube 帳號 `@TuringMirror`）　·　QQ 群 @圖靈鏡社區（群號 `1077458748`）

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="QQ 群 QR Code" width="200">
<!-- qq-group -->

**贊助推廣**　[首月五折　·　高性價比雲端伺服器 / 遊戲雲 / 面板服　·　雨雲](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## 專案簡介

RVC Fabric 是圖靈鏡開發的免費開源 Windows 桌面軟體，提供即時語音轉換、音色管理、人聲分離和模型訓練，適用於語音通話、直播與音訊製作。首次使用需設定執行環境並下載或匯入音色模型。

## 核心特性

- 將麥克風輸入轉換為所選音色，支援切換原聲、ASIO 通道選擇和獨立監聽。實際延遲取決於硬體、模型與音訊設定。
- 內建噪聲門、壓縮器與 5 段參數等化器，支援預設套用與精細調音。
- 音色庫支援關聯 .index 特徵檔案，並可儲存、匯入和匯出參數預設。
- 可從圖靈鏡和第三方來源取得音色模型，支援下載進度管理與中斷後繼續下載。
- 提供人聲分離、文字轉語音和音色訓練工具。訓練精靈包含音訊切分、音高與特徵擷取、模型訓練和索引匯出。
- 支援 NVIDIA CUDA，以及 AMD 和 Intel 顯示卡的 DirectML 加速。安裝引導可辨識硬體並設定對應的執行環境。

截至 2026 年 11 月 7 日，海王星分支包含手機配對、本機 API 和 MCP 介面。手機配對由手機擷取音訊，桌面端執行語音轉換；這些分支功能是否包含於下載版本，應以該版本的發行說明為準。

## 快速開始

1. 執行 RVC_Fabric_Setup.exe，建議安裝到純英文路徑。
2. 依照引導設定執行環境，下載或匯入音色模型。需要向其他軟體傳送聲音時，安裝 VB-Cable 虛擬音效卡。安裝後需重新啟動電腦。
3. 將軟體輸出設為 CABLE Input，並將 QQ、Discord 或直播軟體的輸入設為 CABLE Output。

## 技術架構與開發

### 架構

RVC Fabric 採用 **Tauri + Rust + React** 桌面外殼，後台由 **Python Worker** 承擔全部運算，兩者透過 JSON 檔案協議通訊：

```
RVC Fabric.exe (Tauri + Rust + React 前端主介面)
    │
    ▼ JSON 檔案協議 (command.json / status.json / worker.pid)
Runtime\pythonw.exe tools/realtime_worker.py (Python 3.9 + CUDA / DirectML)
    └─> gui_v1.py (AudioIoProcess + rtrvc 即時推理引擎)
```

上游訓練 / 推理 WebUI（Gradio）作為進階功能隨包保留，可從「其他」頁開啟。

### 環境要求與開發

**環境要求**：Windows 10/11 · Node.js 20+ · Rust Stable · Python 3.13（開發腳本）

```bash
# 1. 安裝前端依賴
cd app
npm install

# 2. 啟動桌面端開發模式 (需要 WebView2 與 MSVC 工具鏈)
npm run tauri:dev

# 3. 僅啟動 UI 瀏覽器預覽
npm run dev
```

### 建置與測試

- **單元測試**：執行 `scripts\run_tests.bat`
- **前端單元測試**：`cd app && npm test`
- **打包安裝程式（NSIS）**：`cd app && npm run tauri:build`
- **打包全量離線包**：`python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **建置線上清單**：`python scripts\build_catalog.py build --diff`

## 開源許可與免責聲明

- 本專案原始碼採用 [MIT License](./LICENSE) 許可協議開源。
- 模型權重、音色包及第三方資源遵循其原始許可協議。
- **免責聲明**：請勿將本軟體用於偽造身份、欺詐或其他違法用途。使用他人聲音進行訓練或轉換前，請取得原權利人授權。使用者應遵守當地法律法規。

## 致謝

感謝以下優秀開源專案為 RVC Fabric 提供的技術支援：

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — 核心演算法與上游基礎
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — 核心聲學模型與音高演算法
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — 檢索與即時降噪
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — 可選音高演算法
- [PyMSS](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — 人聲分離引擎（跟隨上游 RVC，已取代 UVR5）· [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) — 分離模型來源 · [FFmpeg](https://github.com/FFmpeg/FFmpeg) — 音訊處理
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — 虛擬音效卡（把變聲結果送入遊戲/語音軟體）
