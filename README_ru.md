<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
[简体中文](./README.md)　·　[繁體中文](./README_zh-TW.md)　·　[English](./README_en.md)　·　[日本語](./README_ja.md)　·　[한국어](./README_ko.md)　·　[Español](./README_es.md)　·　[Français](./README_fr.md)　·　Русский
<!-- lang-nav -->

**Изменение голоса в реальном времени и саундборд для Windows**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="RVC Fabric главный экран и управление преобразованием голоса" width="32%">
<img src="assets/screenshots/settings.png" alt="RVC Fabric экран настроек" width="32%">
<img src="assets/screenshots/misc.png" alt="RVC Fabric экран дополнительных инструментов" width="32%">
<!-- screenshots -->

[Официальный сайт](https://www.turingmirror.com/en/products/rvc-fabric/) · [Руководство (на английском)](https://www.turingmirror.com/en/guides/rvc-fabric/) · [Скачать для Windows](https://cdn.turingmirror.com/d/rvc-fabric-setup)

Проект основан на [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) и поддерживается [Turing Mirror](https://github.com/Turing-Mirror).

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[Репозиторий GitHub](https://github.com/Turing-Mirror/RVC-Fabric) · [Загрузка артефактов CNB](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**Социальные сети**　[Bilibili @Turing Mirror](https://space.bilibili.com/3546871148579062)　·　[Douyin @Turing Mirror](https://v.douyin.com/6NxXcrKK9cc) (Douyin ID `TuringMirror`)　·　[Xiaohongshu @Turing Mirror](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094) (Xiaohongshu ID `TuringMirror`)　·　[YouTube @Turing Mirror](https://www.youtube.com/@TuringMirror) (аккаунт YouTube `@TuringMirror`)　·　Группа QQ @Сообщество Turing Mirror (Номер группы `1077458748`)

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="QR-код группы QQ" width="200">
<!-- qq-group -->

**Спонсорство и продвижение**　[Серверы Rainyun: скидка 50 % на первый месяц](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## О проекте

RVC Fabric — бесплатное приложение с открытым исходным кодом для Windows от Turing Mirror. Оно позволяет менять голос и воспроизводить музыку или звуковые эффекты в QQ, Discord и голосовом чате игр, а также смешивать голос с музыкальным сопровождением во время трансляции. Аудиотека поддерживает работу с фрагментами и воспроизведение по горячим клавишам. Также доступны управление голосовыми моделями, отделение вокала и обучение моделей.

## Основные возможности

- Воспроизводите музыку, эффекты или выбранные фрагменты в голосовом чате вместе с преобразованным звуком микрофона. Поддерживаются наложение, повтор, отдельная регулировка громкости и глобальные горячие клавиши.
- Преобразует голос с микрофона в реальном времени и позволяет переключаться на исходный голос. Задержка зависит от оборудования, модели и настроек звука.
- Включает шумовой гейт, компрессор и пятиполосный параметрический эквалайзер.
- Позволяет управлять моделями и пресетами, загружать голоса из официальных и сторонних источников.
- Предоставляет разделение вокала, синтез речи и обучение моделей. Текущий интерфейс обучения требует GPU NVIDIA.
- Поддерживает NVIDIA CUDA и ускорение DirectML для GPU AMD и Intel.

Ветка разработки Neptune также предоставляет сопряжение с телефоном, локальный API и интерфейс MCP. Звук, записанный на телефоне, преобразуется на компьютере.

## Голосовой чат и музыка в играх

1. Установите RVC Fabric и настройте необходимые компоненты. Установите виртуальное аудиоустройство VB-Cable и перезагрузите компьютер.
2. В настройках аудиоустройств выберите физический микрофон и выход CABLE Input. В QQ, Discord или игре выберите CABLE Output в качестве микрофона.
3. Добавьте музыку или эффекты в аудиотеку и дважды щёлкните запись, чтобы воспроизвести её в голосовом чате. Чтобы одновременно менять голос, выберите голосовую модель и запустите преобразование. Оба сигнала смешиваются на одном выходе.
4. Для локального прослушивания выберите наушники и при необходимости включите прослушивание музыки. Назначьте глобальные горячие клавиши для частых фрагментов, чтобы запускать, приостанавливать и останавливать их во время игры.

## Техническая архитектура и разработка

### Архитектура

RVC Fabric использует настольную оболочку на базе **Tauri + Rust + React**, а фоновый **Python Worker** выполняет все вычисления. Они обмениваются данными через файловый протокол JSON:

```
RVC Fabric.exe (Frontend интерфейс Tauri + Rust + React)
    │
    ▼ Файловый протокол JSON (command.json / status.json / worker.pid)
Runtime\pythonw.exe tools/realtime_worker.py (Python 3.9 + CUDA / DirectML)
    └─> gui_v1.py (AudioIoProcess + механизм вывода в реальном времени rtrvc)
```

Вышестоящий WebUI для обучения / вывода (Gradio) сохраняется в пакете как расширенная функция и может быть открыт на вкладке «Другое».

### Требования к среде и разработка

**Требования к среде**: Windows 10/11 · Node.js 20+ · Rust Stable · Python 3.13 (скрипты разработки)

```bash
# 1. Установка зависимостей фронтенда
cd app
npm install

# 2. Запуск режима разработки настольной версии (требуются WebView2 и набор инструментов MSVC)
npm run tauri:dev

# 3. Запуск только предварительного просмотра UI в браузере
npm run dev
```

### Сборка и тестирование

- **Модульные тесты**: Запустите `scripts\run_tests.bat`
- **Тесты фронтенда**: `cd app && npm test`
- **Сборка программы установки (NSIS)**: `cd app && npm run tauri:build`
- **Сборка полного оффлайн-пакета**: `python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **Сборка онлайн-каталога**: `python scripts\build_catalog.py build --diff`

## Лицензия исходного кода и разрешение на использование голоса

- Исходный код этого проекта открыт под лицензией [MIT License](./LICENSE).
- Веса моделей, пакеты тембров и сторонние ресурсы регулируются их первоначальными лицензионными соглашениями.
- Перед использованием чужого голоса для обучения или преобразования получите разрешение правообладателя.

## Благодарности

Спасибо следующим выдающимся проектам с открытым исходным кодом за техническую поддержку RVC Fabric:

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Основные алгоритмы и вышестоящая основа
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — Основные акустические модели и алгоритмы высоты тона
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — Поиск и шумоподавление в реальном времени
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — Опциональные алгоритмы высоты тона
- [PyMSS](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Движок разделения вокала (следует за upstream RVC, заменил UVR5) · [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) — Источник моделей разделения · [FFmpeg](https://github.com/FFmpeg/FFmpeg) — Обработка звука
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — Виртуальное аудиоустройство для передачи преобразованного голоса в игры и приложения для общения
