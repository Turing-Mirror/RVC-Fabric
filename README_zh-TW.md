<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
[简体中文](./README.md)　·　繁體中文　·　[English](./README_en.md)　·　[日本語](./README_ja.md)　·　[한국어](./README_ko.md)　·　[Español](./README_es.md)　·　[Français](./README_fr.md)　·　[Русский](./README_ru.md)
<!-- lang-nav -->

**高效能即時 AI 變聲桌面用戶端**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="Home" width="32%">
<img src="assets/screenshots/settings.png" alt="Settings" width="32%">
<img src="assets/screenshots/misc.png" alt="More" width="32%">
<!-- screenshots -->

基於 [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) 深度客製化 · 由 [圖靈鏡 Turing Mirror](https://github.com/Turing-Mirror) 開發維護

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[GitHub 倉庫](https://github.com/Turing-Mirror/RVC-Fabric) · [CNB 製品下載](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**社群媒體**　[嗶哩嗶哩 @圖靈鏡](https://space.bilibili.com/3546871148579062)　·　[抖音 @圖靈鏡](https://v.douyin.com/6NxXcrKK9cc)（抖音號 `TuringMirror`）　·　[小紅書 @圖靈鏡](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094)（小紅書號 `TuringMirror`）

**贊助推廣**　[首月五折　·　高性價比雲端伺服器 / 遊戲雲 / 面板服　·　雨雲](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## 專案簡介

RVC Fabric 是面向 Windows 的即時 AI 變聲桌面軟體，開箱即用：不需要自己裝 Python、PyTorch，也不用開瀏覽器點 Gradio 頁面，安裝完就能變聲。

遊戲開黑、語音連麥、直播互動、音訊製作——低延遲、高還原的即時聲線轉換，一個軟體全搞定。

## 核心特性

- **即時變聲**：低延遲即時推理，變聲中可無縫切換音色，「即時變聲 / 旁路原聲 (Bypass)」一鍵切換。
- **DSP 效果鏈**：內建後級雜訊閘、動態壓縮器與 5 段參數等化器，支援預設套用與精細調音。
- **音色與預設管理**：網格化音色庫、.index 檢索特徵庫綁定，參數預設可儲存、匯入、匯出分享。
- **社群音色廣場**：雙源商店（圖靈鏡官方源 + 第三方開放源），多執行緒並發下載、斷點續傳。
- **內建音訊工具箱**：
  - **人聲分離**：基於 PyMSS 分離模型，快速提取乾聲與伴奏。
  - **語音合成**：輸入文字產生語音，並自動轉換為目標音色（TTS + RVC）。
  - **音色訓練**：內建訓練面板，一鍵訓練專屬音色（需 NVIDIA 顯示卡）。
- **全自動硬體加速**：NVIDIA CUDA（含 RTX 50 系列）與 AMD / Intel（DirectML）自動識別，並下載對應的運算執行階段。

## 快速開始

### 1. 安裝與初始化

1. 從 [Releases 頁面](https://github.com/Turing-Mirror/RVC-Fabric/releases) 下載 `RVC_Fabric_Setup.exe`；
2. 執行安裝程式（建議安裝到純英文路徑）；
3. 啟動軟體，跟隨引導自動完成硬體識別、執行階段補全與虛擬音效卡安裝。

### 2. 音訊路由（虛擬音效卡接法）

想讓遊戲、QQ、Discord 或直播軟體裡的人聽到變聲，需要 VB-Cable 虛擬音效卡在中間轉一手：

| 配置項 | 推薦選擇 | 說明 |
| :--- | :--- | :--- |
| **軟體輸入** | 真實麥克風 | 擷取原始說話聲音 |
| **軟體輸出** | **CABLE Input** | 把變聲結果送進虛擬音效卡 |
| **監聽（可選）** | 實體耳機 / 喇叭 | 本地即時試聽變聲效果 |
| **遊戲 / 語音麥克風** | **CABLE Output** | 第三方軟體接收變聲效果 |
| **Windows 預設播放** | 實體耳機（不要選 CABLE） | 保證系統其他聲音正常播放 |

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
- **打包安裝程式（NSIS）**：`cd app && npm run tauri:build`
- **打包全量離線包**：`python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **建置線上清單**：`python scripts\build_catalog.py build --diff`

## 開源許可與免責聲明

- 本專案原始碼採用 [MIT License](./LICENSE) 許可協議開源。
- 模型權重、音色包及第三方資源遵循其原始許可協議。
- **免責聲明**：請勿將本軟體用於偽造身份、欺詐、騷擾或任何未經授權的違法用途。使用他人聲音進行訓練或轉換前，須取得原權利人明確授權。因違規使用產生的一切法律後果由使用者自行承擔。

## 致謝

感謝以下優秀開源專案為 RVC Fabric 提供的技術支援：

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — 核心演算法與上游基礎
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — 核心聲學模型與音高演算法
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — 檢索與即時降噪
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — 可選音高演算法
- [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui)（UVR 系分離模型，經 PyMSS 執行）· [FFmpeg](https://github.com/FFmpeg/FFmpeg) — 人聲分離與音訊處理
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — 虛擬音效卡（遊戲裡聽到變聲靠它）
