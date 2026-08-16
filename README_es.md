<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
[简体中文](./README.md)　·　[繁體中文](./README_zh-TW.md)　·　[English](./README_en.md)　·　[日本語](./README_ja.md)　·　[한국어](./README_ko.md)　·　Español　·　[Français](./README_fr.md)　·　[Русский](./README_ru.md)
<!-- lang-nav -->

**Cliente de escritorio de alto rendimiento para el cambio de voz con IA en tiempo real**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="Home" width="32%">
<img src="assets/screenshots/settings.png" alt="Settings" width="32%">
<img src="assets/screenshots/misc.png" alt="More" width="32%">
<!-- screenshots -->

Personalización profunda basada en [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) · Desarrollado y mantenido por [Turing Mirror](https://github.com/Turing-Mirror)

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[Repositorio de GitHub](https://github.com/Turing-Mirror/RVC-Fabric) · [Descargar artefactos CNB](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**Redes sociales**　[Bilibili @Turing Mirror](https://space.bilibili.com/3546871148579062)　·　[Douyin @Turing Mirror](https://v.douyin.com/6NxXcrKK9cc) (ID de Douyin `TuringMirror`)　·　[Xiaohongshu @Turing Mirror](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094) (ID de Xiaohongshu `TuringMirror`)　·　Grupo de QQ @Comunidad Turing Mirror (ID de grupo `1077458748`)

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="Código QR del grupo de QQ" width="200">
<!-- qq-group -->

**Patrocinio**　[50% de descuento en el primer mes · Servidores en la nube rentables / Nube de juegos / Servidores de panel · Rainyun](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## Introducción al proyecto

RVC Fabric es un software de escritorio para Windows de cambio de voz con IA en tiempo real, listo para usar: no necesita instalar Python o PyTorch usted mismo, ni necesita abrir un navegador para hacer clic en la página de Gradio, puede cambiar su voz inmediatamente después de la instalación.

Juegos en equipo, chats de voz, interacción en transmisiones en vivo, producción de audio: conversión de voz en tiempo real con baja latencia y alta fidelidad, todo en un solo software.

## Características principales

- **Cambio de voz en tiempo real**: Inferencia en tiempo real de baja latencia, cambio de voz sin problemas durante la conversión, cambio de un solo clic entre "Cambio de voz en tiempo real / Voz original (Bypass)".
- **Cadena de efectos DSP**: Puerta de ruido post-nivel incorporada, compresor dinámico y ecualizador paramétrico de 5 bandas, soporta la aplicación de presets y la sintonización fina.
- **Gestión de voces y presets**: Biblioteca de voces en cuadrícula, enlace de biblioteca de características de recuperación .index, los presets de parámetros se pueden guardar, importar y exportar para compartir.
- **Plaza de voces de la comunidad**: Tienda de doble fuente (fuente oficial de Turing Mirror + fuentes abiertas de terceros), descarga concurrente multihilo, reanudación de la descarga.
- **Caja de herramientas de audio incorporada**:
  - **Separación de voz**: Basada en el modelo de separación PyMSS, extrae rápidamente la voz seca y el acompañamiento.
  - **Síntesis de voz**: Introduce texto para generar voz y convertirla automáticamente a la voz objetivo (TTS + RVC).
  - **Entrenamiento de voz**: Panel de entrenamiento incorporado, entrenamiento de un solo clic para una voz exclusiva (requiere tarjeta gráfica NVIDIA).
- **Aceleración de hardware totalmente automática**: Reconocimiento automático de NVIDIA CUDA (incluida la serie RTX 50) y AMD / Intel (DirectML), y descarga del tiempo de ejecución de cálculo correspondiente.

## Inicio rápido

### 1. Instalación e inicialización

1. Descargue `RVC_Fabric_Setup.exe` desde la [página de Releases](https://github.com/Turing-Mirror/RVC-Fabric/releases);
2. Ejecute el instalador (se recomienda instalar en una ruta puramente en inglés);
3. Inicie el software, siga la guía para completar automáticamente el reconocimiento de hardware, la finalización del tiempo de ejecución y la instalación de la tarjeta de sonido virtual.

### 2. Enrutamiento de audio (Conexión de la tarjeta de sonido virtual)

Si desea que la gente escuche la voz cambiada en juegos, QQ, Discord o software de transmisión en vivo, necesita que la tarjeta de sonido virtual VB-Cable haga la transferencia en el medio:

| Configuración | Selección recomendada | Descripción |
| :--- | :--- | :--- |
| **Entrada de software** | Micrófono real | Captura la voz hablada original |
| **Salida de software** | **CABLE Input** | Envía el resultado del cambio de voz a la tarjeta de sonido virtual |
| **Monitor (opcional)** | Auriculares / altavoces físicos | Escucha local en tiempo real del efecto de cambio de voz |
| **Micrófono de juego / voz** | **CABLE Output** | El software de terceros recibe el efecto de cambio de voz |
| **Reproducción predeterminada de Windows** | Auriculares físicos (No elija CABLE) | Asegura la reproducción normal de otros sonidos del sistema |

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
- **Empaquetar instalador (NSIS)**: `cd app && npm run tauri:build`
- **Empaquetar paquete offline completo**: `python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **Construir manifiesto en línea**: `python scripts\build_catalog.py build --diff`

## Licencia de código abierto y descargo de responsabilidad

- El código fuente de este proyecto es de código abierto bajo la [Licencia MIT](./LICENSE).
- Los pesos del modelo, los paquetes de voz y los recursos de terceros siguen sus acuerdos de licencia originales.
- **Descargo de responsabilidad**: No utilice este software para suplantación de identidad, fraude u otros fines ilegales. Obtenga la autorización del titular de los derechos antes de entrenar o convertir la voz de otra persona. Los usuarios son responsables de cumplir con las leyes y regulaciones locales.

## Agradecimientos

Agradecemos a los siguientes excelentes proyectos de código abierto por brindar soporte técnico para RVC Fabric:

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Algoritmo central y base superior
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — Modelos acústicos centrales y algoritmos de tono
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — Recuperación y reducción de ruido en tiempo real
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — Algoritmos de tono opcionales
- [PyMSS](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Motor de separación vocal (sigue a RVC original; sustituye a UVR5) · [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) — Origen de los modelos de separación · [FFmpeg](https://github.com/FFmpeg/FFmpeg) — Procesamiento de audio
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — Tarjeta de sonido virtual (Escuchar el cambio de voz en el juego depende de esto)
