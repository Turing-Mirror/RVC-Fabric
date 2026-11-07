<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
[简体中文](./README.md)　·　[繁體中文](./README_zh-TW.md)　·　[English](./README_en.md)　·　[日本語](./README_ja.md)　·　[한국어](./README_ko.md)　·　Español　·　[Français](./README_fr.md)　·　[Русский](./README_ru.md)
<!-- lang-nav -->

**Conversión de voz con IA en tiempo real y entrenamiento de modelos para Windows**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="RVC Fabric pantalla de inicio y controles de conversión en tiempo real" width="32%">
<img src="assets/screenshots/settings.png" alt="RVC Fabric pantalla de ajustes" width="32%">
<img src="assets/screenshots/misc.png" alt="RVC Fabric pantalla de herramientas adicionales" width="32%">
<!-- screenshots -->

[Capturas oficiales (en inglés)](https://www.turingmirror.com/en/products/rvc-fabric/screenshots/)

Estas capturas se registraron en agosto de 2026.

[Sitio oficial](https://www.turingmirror.com/en/products/rvc-fabric/)

[Guía de uso (inglés)](https://www.turingmirror.com/en/guides/rvc-fabric/)

[Descargar para Windows](https://cdn.turingmirror.com/d/rvc-fabric-setup)

El proyecto está basado en [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) y lo mantiene [Turing Mirror](https://github.com/Turing-Mirror).

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[Repositorio de GitHub](https://github.com/Turing-Mirror/RVC-Fabric) · [Descargar artefactos CNB](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**Redes sociales**　[Bilibili @Turing Mirror](https://space.bilibili.com/3546871148579062)　·　[Douyin @Turing Mirror](https://v.douyin.com/6NxXcrKK9cc) (ID de Douyin `TuringMirror`)　·　[Xiaohongshu @Turing Mirror](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094) (ID de Xiaohongshu `TuringMirror`)　·　[YouTube @Turing Mirror](https://www.youtube.com/@TuringMirror) (ID de YouTube `@TuringMirror`)　·　Grupo de QQ @Comunidad Turing Mirror (ID de grupo `1077458748`)

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="Código QR del grupo de QQ" width="200">
<!-- qq-group -->

**Patrocinio**　[Servidores Rainyun: 50 % de descuento el primer mes](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## Introducción al proyecto

RVC Fabric es una aplicación de escritorio gratuita y de código abierto para Windows, desarrollada por Turing Mirror. Ofrece conversión de voz en tiempo real, gestión de voces, separación de voces y entrenamiento de modelos para llamadas, transmisiones y producción de audio. Antes del primer uso, configure el entorno de ejecución y descargue o importe un modelo de voz.

## Características principales

- Convierte la voz del micrófono en tiempo real y permite volver a la voz original. La latencia depende del hardware, el modelo y los ajustes de audio.
- Incluye puerta de ruido, compresor y ecualizador paramétrico de cinco bandas.
- Permite gestionar modelos y ajustes preestablecidos, y descargar voces de fuentes oficiales y de terceros.
- Ofrece separación de voces, síntesis de voz y entrenamiento de modelos. La interfaz de entrenamiento actual requiere una GPU NVIDIA.
- Admite NVIDIA CUDA y aceleración DirectML para GPU AMD e Intel.

A fecha de 7 de noviembre de 2026, la rama de desarrollo Neptune incluye vinculación móvil, una API local y una interfaz MCP. El teléfono captura el audio y el ordenador convierte la voz. Las notas de cada versión publicada describen sus funciones.

## Inicio rápido

1. Ejecute el instalador y siga las instrucciones para configurar el entorno de ejecución y preparar un modelo de voz.
2. Para enviar audio a otra aplicación, instale VB-Cable y reinicie el ordenador. Seleccione CABLE Input como salida de RVC Fabric y CABLE Output como entrada de la otra aplicación.

## Arquitectura técnica y desarrollo

### Arquitectura

RVC Fabric adopta un shell de escritorio de **Tauri + Rust + React**, el back-end de **Python Worker** asume todo el cálculo, y los dos se comunican a través del protocolo de archivo JSON:

```
RVC Fabric.exe (Tauri + Rust + React interfaz principal del front-end)
    │
    ▼ Protocolo de archivo JSON (command.json / status.json / worker.pid)
Runtime\pythonw.exe tools/realtime_worker.py (Python 3.9 + CUDA / DirectML)
    └─> gui_v1.py (AudioIoProcess + motor de inferencia en tiempo real rtrvc)
```

La WebUI de entrenamiento / inferencia superior (Gradio) se conserva con el paquete como una función avanzada, que se puede abrir desde la página "Otros".

### Requisitos del entorno y desarrollo

**Requisitos del entorno**: Windows 10/11 · Node.js 20+ · Rust Stable · Python 3.13 (Scripts de desarrollo)

```bash
# 1. Instalar dependencias del front-end
cd app
npm install

# 2. Iniciar el modo de desarrollo de escritorio (requiere WebView2 y la cadena de herramientas MSVC)
npm run tauri:dev

# 3. Solo iniciar la vista previa del navegador de la UI
npm run dev
```

### Construcción y pruebas

- **Pruebas unitarias**: Ejecute `scripts\run_tests.bat`
- **Pruebas unitarias del frontend**: `cd app && npm test`
- **Empaquetar instalador (NSIS)**: `cd app && npm run tauri:build`
- **Empaquetar paquete offline completo**: `python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **Construir manifiesto en línea**: `python scripts\build_catalog.py build --diff`

## Licencia del código fuente y autorización de uso de voces

- El código fuente de este proyecto es de código abierto bajo la [Licencia MIT](./LICENSE).
- Los pesos del modelo, los paquetes de voz y los recursos de terceros siguen sus acuerdos de licencia originales.
- Obtenga la autorización del titular de los derechos antes de utilizar la voz de otra persona para el entrenamiento o la conversión.

## Agradecimientos

Agradecemos a los siguientes excelentes proyectos de código abierto por brindar soporte técnico para RVC Fabric:

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Algoritmo central y base superior
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — Modelos acústicos centrales y algoritmos de tono
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — Recuperación y reducción de ruido en tiempo real
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — Algoritmos de tono opcionales
- [PyMSS](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Motor de separación vocal (sigue a RVC original; sustituye a UVR5) · [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) — Origen de los modelos de separación · [FFmpeg](https://github.com/FFmpeg/FFmpeg) — Procesamiento de audio
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — Dispositivo de audio virtual que envía la voz convertida a juegos y aplicaciones de voz
