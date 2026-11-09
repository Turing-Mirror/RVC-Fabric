<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
[简体中文](./README.md)　·　[繁體中文](./README_zh-TW.md)　·　[English](./README_en.md)　·　日本語　·　[한국어](./README_ko.md)　·　[Español](./README_es.md)　·　[Français](./README_fr.md)　·　[Русский](./README_ru.md)
<!-- lang-nav -->

**Windows 向けリアルタイムボイスチェンジャー・サウンドボード**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="RVC Fabric ホーム画面とリアルタイム変換の操作" width="32%">
<img src="assets/screenshots/settings.png" alt="RVC Fabric 設定画面" width="32%">
<img src="assets/screenshots/misc.png" alt="RVC Fabric その他の機能の画面" width="32%">
<!-- screenshots -->

[公式サイト](https://www.turingmirror.com/ja/products/rvc-fabric/) · [Windows 版をダウンロード](https://cdn.turingmirror.com/d/rvc-fabric-setup)

[RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) を基に開発し、[图灵镜 Turing Mirror](https://github.com/Turing-Mirror) が保守しています。

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[GitHub リポジトリ](https://github.com/Turing-Mirror/RVC-Fabric) · [CNB成果物ダウンロード](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**ソーシャルメディア**　[bilibili @图灵镜](https://space.bilibili.com/3546871148579062)　·　[抖音 @图灵镜](https://v.douyin.com/6NxXcrKK9cc)（抖音ID `TuringMirror`）　·　[小紅書 @图灵镜](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094)（小紅書ID `TuringMirror`）　·　[YouTube @图灵镜](https://www.youtube.com/@TuringMirror)（YouTube ハンドル `@TuringMirror`）　·　QQ グループ @图灵镜社区（グループ番号 `1077458748`）

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="QQ グループの QR コード" width="200">
<!-- qq-group -->

**スポンサープロモーション**　[Rainyun のサーバーは初月半額](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## プロジェクト概要

RVC Fabric は Turing Mirror が開発する無料のオープンソース Windows アプリです。QQ、Discord、ゲーム内のボイスチャットで声を変えたり、音楽や効果音を流したりでき、配信では声と伴奏をミックスできます。音声ライブラリでのクリップ管理とショートカット再生に加え、ボイスモデル管理、ボーカル分離、モデル学習にも対応しています。

## 主な特徴

- 音楽、効果音、選択したクリップを変換後のマイク音声とともにボイスチャットへ出力できます。重ねて再生、ループ、個別の音量調整、グローバルショートカットに対応しています。
- マイク入力を選択したボイスに変換します。原音への切り替え、ASIO チャンネル選択、独立したモニタリングに対応しています。遅延はハードウェア、モデル、音声設定によって異なります。
- ノイズゲート、コンプレッサー、5 バンドパラメトリック EQ を内蔵しています。プリセットと個別の調整に対応しています。
- ボイスライブラリでは .index ファイルを関連付け、パラメータープリセットを保存、インポート、エクスポートできます。
- Kara251 とサードパーティの配布元からボイスモデルを取得できます。進捗の確認と中断したダウンロードの再開に対応しています。
- ボーカル分離、テキスト読み上げ、ボイス学習ツールを提供します。学習手順には音声分割、ピッチと特徴量の抽出、モデル学習、インデックスの書き出しが含まれます。
- NVIDIA CUDA と、AMD および Intel GPU の DirectML アクセラレーションに対応しています。セットアップでハードウェアを検出し、対応する実行環境を設定します。

## ボイスチャットとゲーム内での音楽再生

1. RVC Fabric をインストールし、必要なコンポーネントを設定します。仮想オーディオデバイス VB-Cable をインストールしたら、コンピューターを再起動します。
2. 音声デバイス設定で実際のマイクを選択し、出力を CABLE Input にします。QQ、Discord、ゲームの音声設定では、マイクを CABLE Output にします。
3. 音声ライブラリに音楽や効果音をインポートし、項目をダブルクリックしてボイスチャットへ再生します。音楽を流しながら変声するには、ボイスモデルを選択して変換を開始します。両方の音声が同じ出力にミックスされます。
4. ローカルモニタリングにはヘッドホンを選び、必要に応じて音楽のモニタリングを有効にします。よく使うクリップにグローバルショートカットを割り当てると、ゲーム中に再生、一時停止、停止を操作できます。

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
- **フロントエンド単体テスト**：`cd app && npm test`
- **インストーラのパッケージ化（NSIS）**：`cd app && npm run tauri:build`
- **完全なオフラインパッケージの作成**：`python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **オンラインカタログの構築**：`python scripts\build_catalog.py build --diff`

## ソースコードのライセンスと音声の利用許諾

- 本プロジェクトのソースコードは [MIT License](./LICENSE) の下でオープンソース化されています。
- モデルの重み、音声パッケージ、サードパーティのリソースは、それぞれの元のライセンスに従います。
- 他人の声を学習や変換に使う前に、権利者の許諾を得てください。

## 謝辞

RVC Fabric に技術的サポートを提供してくださった以下の素晴らしいオープンソースプロジェクトに感謝します：

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — コアアルゴリズムとアップストリームの基礎
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — コア音響モデルとピッチアルゴリズム
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — 検索とリアルタイムノイズリダクション
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — オプションのピッチアルゴリズム
- [PyMSS](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — ボーカル分離エンジン（上流 RVC に追随し UVR5 を置き換え）· [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) — 分離モデルの提供元 · [FFmpeg](https://github.com/FFmpeg/FFmpeg) — オーディオ処理
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — 仮想サウンドカード（ゲーム内でボイスチェンジした声を聞くために使用）
