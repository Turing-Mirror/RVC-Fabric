<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
[简体中文](./README.md)　·　[繁體中文](./README_zh-TW.md)　·　[English](./README_en.md)　·　日本語　·　[한국어](./README_ko.md)　·　[Español](./README_es.md)　·　[Français](./README_fr.md)　·　[Русский](./README_ru.md)
<!-- lang-nav -->

**高性能リアルタイムAIボイスチェンジャーデスクトップクライアント**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="Home" width="32%">
<img src="assets/screenshots/settings.png" alt="Settings" width="32%">
<img src="assets/screenshots/misc.png" alt="More" width="32%">
<!-- screenshots -->

[RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)をベースにディープカスタマイズ · [图灵镜 Turing Mirror](https://github.com/Turing-Mirror) が開発・メンテナンス

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[GitHub リポジトリ](https://github.com/Turing-Mirror/RVC-Fabric) · [CNB成果物ダウンロード](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**ソーシャルメディア**　[bilibili @图灵镜](https://space.bilibili.com/3546871148579062)　·　[抖音 @图灵镜](https://v.douyin.com/6NxXcrKK9cc)（抖音ID `TuringMirror`）　·　[小紅書 @图灵镜](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094)（小紅書ID `TuringMirror`）　·　QQ グループ @图灵镜社区（グループ番号 `1077458748`）

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="QQ グループの QR コード" width="200">
<!-- qq-group -->

**スポンサープロモーション**　[初月半額　·　高コスパクラウドサーバー / ゲームクラウド / パネルサーバー　·　雨云](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## プロジェクト概要

RVC FabricはWindows向けのリアルタイムAIボイスチェンジャーデスクトップソフトウェアで、すぐに使えます。PythonやPyTorchを自分でインストールする必要もなく、ブラウザを開いてGradioのページを操作する必要もありません。インストールすればすぐにボイスチェンジが可能です。

ゲームのマルチプレイ、ボイスチャット、ライブ配信での交流、音声制作まで、低遅延で高再現度のリアルタイム声質変換をこの一つのソフトウェアで完結させます。

## 主な特徴

- **リアルタイムボイスチェンジ**：低遅延のリアルタイム推論。ボイスチェンジ中にシームレスに音声を切り替え可能で、「リアルタイムボイスチェンジ / バイパス（原音）」をワンクリックで切り替え。
- **DSPエフェクトチェーン**：後段ノイズゲート、ダイナミックコンプレッサー、5バンドパラメトリックイコライザーを内蔵し、プリセットの適用と細かなチューニングに対応。
- **音声・プリセット管理**：グリッド化された音声ライブラリ、.index検索特徴ライブラリのバインド。パラメータのプリセット保存、インポート、エクスポート、共有が可能。
- **コミュニティ音声広場**：デュアルソースストア（图灵镜公式ソース + サードパーティオープンソース）、マルチスレッド同時ダウンロード、レジューム機能。
- **内蔵オーディオツールボックス**：
  - **ボーカル分離**：PyMSS分離モデルに基づき、ボーカルと伴奏を迅速に抽出。
  - **音声合成**：テキスト入力で音声を生成し、自動的にターゲットの音声に変換（TTS + RVC）。
  - **音声学習**：内蔵の学習パネルで、専用の音声をワンクリックで学習（NVIDIAグラフィックカードが必要）。
- **完全自動ハードウェアアクセラレーション**：NVIDIA CUDA（RTX 50シリーズを含む）とAMD / Intel（DirectML）を自動認識し、対応する計算ランタイムをダウンロード。

## クイックスタート

### 1. インストールと初期化

1. [Releases ページ](https://github.com/Turing-Mirror/RVC-Fabric/releases)から`RVC_Fabric_Setup.exe`をダウンロードします；
2. インストーラを実行します（英語のみのパスにインストールすることを推奨します）；
3. ソフトウェアを起動し、ガイドに従ってハードウェア認識、ランタイム補完、仮想サウンドカードのインストールを自動的に完了させます。

### 2. オーディオルーター（仮想サウンドカードの接続方法）

ゲーム、QQ、Discord、またはライブ配信ソフトウェアで他の人にボイスチェンジした声を聞かせるには、中間にVB-Cable仮想サウンドカードを挟む必要があります：

| 設定項目 | 推奨選択 | 説明 |
| :--- | :--- | :--- |
| **ソフトウェア入力** | 実際の物理マイク | 元の話し声をキャプチャ |
| **ソフトウェア出力** | **CABLE Input** | ボイスチェンジの結果を仮想サウンドカードに送る |
| **モニタリング（オプション）** | 物理ヘッドフォン / スピーカー | ローカルでリアルタイムにボイスチェンジ効果を試聴 |
| **ゲーム / ボイスチャットマイク** | **CABLE Output** | サードパーティソフトウェアがボイスチェンジ効果を受信 |
| **Windows デフォルト再生** | 物理ヘッドフォン（CABLEは選択しないでください） | システムの他のサウンドが正常に再生されることを保証 |

## 技術アーキテクチャと開発

### アーキテクチャ

RVC Fabricは **Tauri + Rust + React** のデスクトップシェルを採用し、バックグラウンドは **Python Worker** がすべての計算を担い、両者はJSONファイルプロトコルを通じて通信します：

```
RVC Fabric.exe (Tauri + Rust + React フロントエンドメインインターフェース)
    │
    ▼ JSON ファイルプロトコル (command.json / status.json / worker.pid)
Runtime\pythonw.exe tools/realtime_worker.py (Python 3.9 + CUDA / DirectML)
    └─> gui_v1.py (AudioIoProcess + rtrvc リアルタイム推論エンジン)
```

アップストリームの学習/推論WebUI（Gradio）は高度な機能としてパッケージに同梱されており、「その他」ページから開くことができます。

### 環境要件と開発

**環境要件**：Windows 10/11 · Node.js 20+ · Rust Stable · Python 3.13（開発スクリプト）

```bash
# 1. フロントエンドの依存関係をインストール
cd app
npm install

# 2. デスクトップ開発モードを起動 (WebView2 と MSVC ツールチェーンが必要)
npm run tauri:dev

# 3. UIブラウザプレビューのみを起動
npm run dev
```

### ビルドとテスト

- **単体テスト**：`scripts\run_tests.bat` を実行
- **インストーラのパッケージ化（NSIS）**：`cd app && npm run tauri:build`
- **完全なオフラインパッケージの作成**：`python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **オンラインカタログの構築**：`python scripts\build_catalog.py build --diff`

## オープンソースライセンスと免責事項

- 本プロジェクトのソースコードは [MIT License](./LICENSE) の下でオープンソース化されています。
- モデルの重み、音声パッケージ、サードパーティのリソースは、それぞれの元のライセンスに従います。
- **免責事項**：本ソフトウェアを身分偽装、詐欺、ハラスメント、または無許可の違法な目的で使用しないでください。他人の音声を使用して学習または変換を行う前に、元の権利者から明確な許可を得る必要があります。違反使用により生じるすべての法的結果は、ユーザー自身が負担するものとします。

## 謝辞

RVC Fabric に技術的サポートを提供してくださった以下の素晴らしいオープンソースプロジェクトに感謝します：

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — コアアルゴリズムとアップストリームの基礎
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — コア音響モデルとピッチアルゴリズム
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — 検索とリアルタイムノイズリダクション
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — オプションのピッチアルゴリズム
- [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui)（PyMSSで動作するUVR系分離モデル）· [FFmpeg](https://github.com/FFmpeg/FFmpeg) — ボーカル分離とオーディオ処理
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — 仮想サウンドカード（ゲーム内でボイスチェンジした声を聞くために使用）
