<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
[简体中文](./README.md)　·　繁體中文　·　[English](./README_en.md)　·　[日本語](./README_ja.md)　·　[한국어](./README_ko.md)　·　[Español](./README_es.md)　·　[Français](./README_fr.md)　·　[Русский](./README_ru.md)
<!-- lang-nav -->

**Windows 即時變聲與語音音效播放軟體**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="RVC Fabric 主畫面與即時變聲控制" width="32%">
<img src="assets/screenshots/settings.png" alt="RVC Fabric 設定頁面" width="32%">
<img src="assets/screenshots/misc.png" alt="RVC Fabric 其他功能頁面" width="32%">
<!-- screenshots -->

[官網](https://www.turingmirror.com/zh-hant/products/rvc-fabric/) · [下載 Windows 版](https://cdn.turingmirror.com/d/rvc-fabric-setup)

以 [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) 為基礎開發，由 [圖靈鏡 Turing Mirror](https://github.com/Turing-Mirror) 維護。

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[GitHub 倉庫](https://github.com/Turing-Mirror/RVC-Fabric) · [CNB 製品下載](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**社群媒體**　[嗶哩嗶哩 @圖靈鏡](https://space.bilibili.com/3546871148579062)　·　[抖音 @圖靈鏡](https://v.douyin.com/6NxXcrKK9cc)（抖音號 `TuringMirror`）　·　[小紅書 @圖靈鏡](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094)（小紅書號 `TuringMirror`）　·　[YouTube @圖靈鏡](https://www.youtube.com/@TuringMirror)（YouTube 帳號 `@TuringMirror`）　·　QQ 群 @圖靈鏡社區（群號 `1077458748`）

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="QQ 群 QR Code" width="200">
<!-- qq-group -->

**贊助推廣**　[雨雲伺服器首月五折](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## 專案簡介

RVC Fabric 是圖靈鏡開發的免費開源 Windows 軟體，可在 QQ、Discord 和遊戲語音中即時變聲、播放音樂和音效，也可在直播中混合人聲與伴奏。內建音訊庫支援片段管理與快捷鍵播放，並提供音色模型管理、人聲分離和模型訓練。

## 核心特性

- 音訊庫可將音樂、音效或選定片段播放到語音，與變聲後的麥克風聲音同時輸出，支援疊加、循環、獨立音量和全域快捷鍵。
- 將麥克風輸入轉換為所選音色，支援切換原聲、ASIO 通道選擇和獨立監聽。實際延遲取決於硬體、模型與音訊設定。
- 內建噪聲門、壓縮器與 5 段參數等化器，支援預設套用與精細調音。
- 音色庫支援關聯 .index 特徵檔案，並可儲存、匯入和匯出參數預設。
- 可從圖靈鏡和第三方來源取得音色模型，支援下載進度管理與中斷後繼續下載。
- 提供人聲分離、文字轉語音和音色訓練工具。訓練精靈包含音訊切分、音高與特徵擷取、模型訓練和索引匯出。
- 支援 NVIDIA CUDA，以及 AMD 和 Intel 顯示卡的 DirectML 加速。安裝引導可辨識硬體並設定對應的執行環境。

## 語音聊天與遊戲內播放音樂

1. 安裝 RVC Fabric，依照引導設定所需元件。安裝 VB-Cable 虛擬音效卡後重新啟動電腦。
2. 在「裝置與音訊」中選擇實際麥克風，將輸出設為 CABLE Input；在 QQ、Discord 或遊戲的語音設定中，將麥克風設為 CABLE Output。
3. 開啟「音訊」，匯入音樂或音效，按兩下項目即可播放到語音。需要邊播放音樂邊變聲時，選擇音色模型並開啟變聲，兩路聲音會混合輸出。
4. 將本機監聽裝置設為耳機，視需要開啟音樂監聽。可為常用片段設定全域快捷鍵，在遊戲中控制播放、暫停和停止。

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

## 開源授權與聲音授權

- 本專案原始碼採用 [MIT License](./LICENSE) 許可協議開源。
- 模型權重、音色包及第三方資源遵循其原始許可協議。
- 使用他人聲音進行訓練或轉換前，請取得聲音權利人的授權。

## 致謝

感謝以下優秀開源專案為 RVC Fabric 提供的技術支援：

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — 核心演算法與上游基礎
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — 核心聲學模型與音高演算法
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — 檢索與即時降噪
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — 可選音高演算法
- [PyMSS](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — 人聲分離引擎（跟隨上游 RVC，已取代 UVR5）· [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) — 分離模型來源 · [FFmpeg](https://github.com/FFmpeg/FFmpeg) — 音訊處理
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — 虛擬音效卡（把變聲結果送入遊戲/語音軟體）
