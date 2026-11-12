<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
[简体中文](./README.md)　·　[繁體中文](./README_zh-TW.md)　·　[English](./README_en.md)　·　[日本語](./README_ja.md)　·　한국어　·　[Español](./README_es.md)　·　[Français](./README_fr.md)　·　[Русский](./README_ru.md)
<!-- lang-nav -->

**Windows용 실시간 음성 변환 및 사운드보드**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="RVC Fabric 홈 화면 및 실시간 음성 변환 제어" width="32%">
<img src="assets/screenshots/settings.png" alt="RVC Fabric 설정 화면" width="32%">
<img src="assets/screenshots/misc.png" alt="RVC Fabric 추가 기능 화면" width="32%">
<!-- screenshots -->

[공식 웹사이트](https://www.turingmirror.com/en/products/rvc-fabric/) · [Windows용 다운로드](https://cdn.turingmirror.com/d/rvc-fabric-setup)

[RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)를 기반으로 개발되었으며 [Turing Mirror](https://github.com/Turing-Mirror)가 유지보수합니다.

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[GitHub 저장소](https://github.com/Turing-Mirror/RVC-Fabric) · [CNB 아티팩트 다운로드](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**소셜 미디어**　[Bilibili @TuringMirror](https://space.bilibili.com/3546871148579062)　·　[Douyin @TuringMirror](https://v.douyin.com/6NxXcrKK9cc) (Douyin ID `TuringMirror`)　·　[Xiaohongshu @TuringMirror](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094) (Xiaohongshu ID `TuringMirror`)　·　[YouTube @TuringMirror](https://www.youtube.com/@TuringMirror) (YouTube 핸들 `@TuringMirror`)　·　QQ 그룹 @TuringMirror 커뮤니티 (그룹 번호 `1077458748`)

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="QQ 그룹 QR 코드" width="200">
<!-- qq-group -->

**후원 프로모션**　[Rainyun 서버 첫 달 50% 할인](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## 프로젝트 소개

RVC Fabric은 Turing Mirror가 개발하는 무료 오픈 소스 Windows 앱입니다. QQ, Discord, 게임 내 음성 채팅에서 목소리를 바꾸고 음악이나 효과음을 재생하며, 방송에서는 목소리와 반주를 함께 출력할 수 있습니다. 오디오 라이브러리의 클립 관리와 단축키 재생 외에도 음성 모델 관리, 보컬 분리, 모델 학습을 제공합니다.

## 핵심 기능

- 음악, 효과음, 선택한 클립을 변환된 마이크 음성과 함께 음성 채팅으로 출력합니다. 겹쳐 재생, 반복, 별도 볼륨 조절, 전역 단축키를 지원합니다.
- 실시간으로 마이크 음성을 변환하고 원음으로 전환할 수 있습니다. 지연 시간은 하드웨어, 모델, 오디오 설정에 따라 달라집니다.
- 노이즈 게이트, 컴프레서, 5밴드 파라메트릭 이퀄라이저를 제공합니다.
- 음성 모델과 프리셋을 관리하고 공식 및 타사 배포처에서 모델을 다운로드할 수 있습니다.
- 보컬 분리, 텍스트 음성 합성, 모델 학습 도구를 제공합니다. 현재 학습 화면에서는 NVIDIA GPU가 필요합니다.
- NVIDIA CUDA 및 AMD와 Intel GPU의 DirectML 가속을 지원합니다.

## 음성 채팅과 게임 내 음악 재생

1. RVC Fabric을 설치하고 필요한 구성 요소를 설정합니다. VB-Cable 가상 오디오 장치를 설치한 뒤 컴퓨터를 다시 시작합니다.
2. 오디오 장치 설정에서 실제 마이크를 선택하고 출력을 CABLE Input으로 설정합니다. QQ, Discord 또는 게임의 마이크 입력은 CABLE Output으로 설정합니다.
3. 오디오 라이브러리에 음악이나 효과음을 가져온 뒤 항목을 두 번 클릭하면 음성 채팅으로 재생됩니다. 음악을 재생하면서 목소리도 바꾸려면 음성 모델을 선택하고 변환을 시작합니다. 두 소리가 같은 출력으로 믹싱됩니다.
4. 로컬 모니터링 장치로 헤드폰을 선택하고 필요에 따라 음악 모니터링을 켭니다. 자주 쓰는 클립에 전역 단축키를 지정하면 게임 중에도 재생, 일시 정지, 정지를 제어할 수 있습니다.

## 기술 아키텍처 및 개발

### 아키텍처

RVC Fabric은 **Tauri + Rust + React** 데스크톱 셸을 채택했으며, 백그라운드에서는 **Python Worker**가 모든 컴퓨팅을 담당하며, 둘은 JSON 파일 프로토콜을 통해 통신합니다:

```
RVC Fabric.exe (Tauri + Rust + React 프론트엔드 메인 인터페이스)
    │
    ▼ JSON 파일 프로토콜 (command.json / status.json / worker.pid)
Runtime\pythonw.exe tools/realtime_worker.py (Python 3.9 + CUDA / DirectML)
    └─> gui_v1.py (AudioIoProcess + rtrvc 실시간 추론 엔진)
```

업스트림 훈련 / 추론 WebUI (Gradio)는 고급 기능으로 패키지에 유지되며, 「기타」 페이지에서 열 수 있습니다.

### 환경 요구 사항 및 개발

**환경 요구 사항**: Windows 10/11 · Node.js 20+ · Rust Stable · Python 3.13 (개발 스크립트)

```bash
# 1. 프론트엔드 의존성 설치
cd app
npm install

# 2. 데스크톱 개발 모드 시작 (WebView2 및 MSVC 툴체인 필요)
npm run tauri:dev

# 3. UI 브라우저 미리보기만 시작
npm run dev
```

### 빌드 및 테스트

- **단위 테스트**: `scripts\run_tests.bat` 실행
- **프런트엔드 단위 테스트**: `cd app && npm test`
- **설치 프로그램 패키징 (NSIS)**: `cd app && npm run tauri:build`
- **전체 오프라인 패키지 패키징**: `python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **온라인 매니페스트 빌드**: `python scripts\build_catalog.py build --diff`

## 소스 코드 라이선스 및 음성 사용 허가

- 본 프로젝트의 소스 코드는 [MIT License](./LICENSE) 라이선스에 따라 오픈 소스로 제공됩니다.
- 모델 가중치, 음색 패키지 및 서드파티 리소스는 원래 라이선스를 따릅니다.
- 타인의 목소리를 학습하거나 변환하기 전에 권리자의 허가를 받으십시오.

## 감사의 글

RVC Fabric에 기술적 지원을 제공한 훌륭한 오픈 소스 프로젝트에 감사드립니다:

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — 핵심 알고리즘 및 업스트림 기초
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — 핵심 음향 모델 및 피치 알고리즘
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — 검색 및 실시간 노이즈 감소
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — 선택적 피치 알고리즘
- [PyMSS](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — 보컬 분리 엔진(상위 RVC를 따라 UVR5를 대체) · [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) — 분리 모델 출처 · [FFmpeg](https://github.com/FFmpeg/FFmpeg) — 오디오 처리
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — 가상 사운드 카드 (게임에서 변조된 목소리를 들을 수 있게 함)
