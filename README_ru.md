<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
[简体中文](./README.md)　·　[繁體中文](./README_zh-TW.md)　·　[English](./README_en.md)　·　[日本語](./README_ja.md)　·　[한국어](./README_ko.md)　·　[Español](./README_es.md)　·　[Français](./README_fr.md)　·　Русский
<!-- lang-nav -->

**Высокопроизводительный настольный клиент для изменения голоса с помощью ИИ в реальном времени**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="Home" width="32%">
<img src="assets/screenshots/settings.png" alt="Settings" width="32%">
<img src="assets/screenshots/misc.png" alt="More" width="32%">
<!-- screenshots -->

Глубоко настроен на основе [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) · Разработано и поддерживается [Turing Mirror](https://github.com/Turing-Mirror)

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[Репозиторий GitHub](https://github.com/Turing-Mirror/RVC-Fabric) · [Загрузка артефактов CNB](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**Социальные сети**　[Bilibili @Turing Mirror](https://space.bilibili.com/3546871148579062)　·　[Douyin @Turing Mirror](https://v.douyin.com/6NxXcrKK9cc) (Douyin ID `TuringMirror`)　·　[Xiaohongshu @Turing Mirror](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094) (Xiaohongshu ID `TuringMirror`)　·　Группа QQ @Сообщество Turing Mirror (Номер группы `1077458748`)

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="QR-код группы QQ" width="200">
<!-- qq-group -->

**Спонсорство и продвижение**　[Скидка 50% на первый месяц · Облачный сервер с высокой производительностью / Игровое облако / Панельный сервер · Rainyun](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## О проекте

RVC Fabric — это программное обеспечение для рабочего стола Windows для изменения голоса с помощью ИИ в реальном времени, готовое к использованию прямо из коробки: вам не нужно самостоятельно устанавливать Python, PyTorch или открывать браузер, чтобы нажимать на страницы Gradio. Вы можете изменять свой голос сразу после установки.

Игры с друзьями, голосовые звонки, интерактивные трансляции, создание аудио — преобразование голоса в реальном времени с низкой задержкой и высокой точностью, все в одной программе.

## Основные возможности

- **Изменение голоса в реальном времени**: Низкая задержка вывода в реальном времени, бесшовное переключение тембров во время изменения голоса, переключение между «Изменение голоса в реальном времени / Исходный голос (Bypass)» одним нажатием.
- **Цепочка эффектов DSP**: Встроенный шумовой гейт, динамический компрессор и 5-полосный параметрический эквалайзер с поддержкой применения пресетов и точной настройки.
- **Управление тембрами и пресетами**: Сеточная библиотека тембров, привязка библиотеки характеристик поиска .index, параметры пресетов можно сохранять, импортировать, экспортировать и делиться ими.
- **Площадь тембров сообщества**: Магазин с двумя источниками (официальный источник Turing Mirror + открытые сторонние источники), многопоточное параллельное скачивание, возобновление скачивания после прерывания.
- **Встроенный набор инструментов для аудио**:
  - **Разделение вокала**: Быстрое извлечение чистого голоса и аккомпанемента с использованием модели разделения PyMSS.
  - **Синтез речи**: Ввод текста для генерации речи и автоматического преобразования в целевой тембр (TTS + RVC).
  - **Тренировка тембра**: Встроенная панель обучения для создания эксклюзивных тембров одним кликом (требуется видеокарта NVIDIA).
- **Полностью автоматическое аппаратное ускорение**: Автоматическое распознавание NVIDIA CUDA (включая серию RTX 50) и AMD / Intel (DirectML), а также загрузка соответствующей среды выполнения вычислений.

## Быстрый старт

### 1. Установка и инициализация

1. Загрузите `RVC_Fabric_Setup.exe` со [страницы Releases](https://github.com/Turing-Mirror/RVC-Fabric/releases);
2. Запустите программу установки (рекомендуется устанавливать по пути, содержащему только английские символы);
3. Запустите программу и следуйте инструкциям для автоматического завершения идентификации оборудования, установки среды выполнения и виртуальной звуковой карты.

### 2. Маршрутизация звука (Подключение виртуальной звуковой карты)

Чтобы люди в играх, QQ, Discord или программах для трансляций слышали измененный голос, вам нужна виртуальная звуковая карта VB-Cable в качестве посредника:

| Настройка | Рекомендуемый выбор | Описание |
| :--- | :--- | :--- |
| **Вход программы** | Реальный микрофон | Захват исходного голоса |
| **Выход программы** | **CABLE Input** | Отправка результата изменения голоса на виртуальную звуковую карту |
| **Прослушивание (дополнительно)** | Физические наушники / динамики | Локальное прослушивание эффекта изменения голоса в реальном времени |
| **Микрофон в игре / голосовом чате** | **CABLE Output** | Сторонние программы получают измененный голос |
| **Воспроизведение Windows по умолчанию** | Физические наушники (не выбирайте CABLE) | Обеспечение нормального воспроизведения других звуков системы |

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
- **Сборка программы установки (NSIS)**: `cd app && npm run tauri:build`
- **Сборка полного оффлайн-пакета**: `python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **Сборка онлайн-каталога**: `python scripts\build_catalog.py build --diff`

## Открытая лицензия и отказ от ответственности

- Исходный код этого проекта открыт под лицензией [MIT License](./LICENSE).
- Веса моделей, пакеты тембров и сторонние ресурсы регулируются их первоначальными лицензионными соглашениями.
- **Отказ от ответственности**: Не используйте это программное обеспечение для подделки личности, мошенничества или других незаконных целей. Перед обучением или преобразованием чужого голоса получите разрешение правообладателя. Пользователи обязаны соблюдать местные законы и нормативные акты.

## Благодарности

Спасибо следующим выдающимся проектам с открытым исходным кодом за техническую поддержку RVC Fabric:

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Основные алгоритмы и вышестоящая основа
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — Основные акустические модели и алгоритмы высоты тона
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — Поиск и шумоподавление в реальном времени
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — Опциональные алгоритмы высоты тона
- [PyMSS](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Движок разделения вокала (следует за upstream RVC, заменил UVR5) · [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) — Источник моделей разделения · [FFmpeg](https://github.com/FFmpeg/FFmpeg) — Обработка звука
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — Виртуальная звуковая карта (именно благодаря ей вы слышите измененный голос в игре)
