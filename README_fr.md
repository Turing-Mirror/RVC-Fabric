<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
[简体中文](./README.md)　·　[繁體中文](./README_zh-TW.md)　·　[English](./README_en.md)　·　[日本語](./README_ja.md)　·　[한국어](./README_ko.md)　·　[Español](./README_es.md)　·　Français　·　[Русский](./README_ru.md)
<!-- lang-nav -->

**Changeur de voix en temps réel et lecteur de sons pour Windows**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="RVC Fabric écran d’accueil et commandes de conversion en temps réel" width="32%">
<img src="assets/screenshots/settings.png" alt="RVC Fabric écran des paramètres" width="32%">
<img src="assets/screenshots/misc.png" alt="RVC Fabric écran des outils supplémentaires" width="32%">
<!-- screenshots -->

[Site officiel](https://www.turingmirror.com/en/products/rvc-fabric/) · [Télécharger pour Windows](https://cdn.turingmirror.com/d/rvc-fabric-setup)

Le projet est basé sur [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) et maintenu par [Turing Mirror](https://github.com/Turing-Mirror).

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[Dépôt GitHub](https://github.com/Turing-Mirror/RVC-Fabric) · [Téléchargement CNB](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**Réseaux sociaux**　[Bilibili @Turing Mirror](https://space.bilibili.com/3546871148579062)　·　[Douyin @Turing Mirror](https://v.douyin.com/6NxXcrKK9cc) (ID Douyin `TuringMirror`)　·　[Xiaohongshu @Turing Mirror](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094) (ID Xiaohongshu `TuringMirror`)　·　[YouTube @Turing Mirror](https://www.youtube.com/@TuringMirror) (identifiant YouTube `@TuringMirror`)　·　Groupe QQ @Communauté Turing Mirror (N° de groupe `1077458748`)

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="Code QR du groupe QQ" width="200">
<!-- qq-group -->

**Sponsorisation et promotion**　[Serveurs Rainyun : 50 % de réduction le premier mois](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## Introduction du projet

RVC Fabric est une application Windows gratuite et open source développée par Turing Mirror. Elle permet de changer de voix et de diffuser de la musique ou des effets dans QQ, Discord et le chat vocal des jeux, ainsi que de mélanger voix et accompagnement en direct. Sa bibliothèque audio propose la gestion de clips et la lecture par raccourcis clavier. Elle comprend aussi la gestion des modèles de voix, la séparation vocale et l’entraînement de modèles.

## Fonctionnalités principales

- Diffusez de la musique, des effets ou des clips sélectionnés dans le chat vocal avec le son du microphone converti. La lecture prend en charge la superposition, les boucles, un volume indépendant et les raccourcis globaux.
- Convertit la voix du microphone en temps réel et permet de revenir à la voix d’origine. La latence dépend du matériel, du modèle et des réglages audio.
- Comprend une porte de bruit, un compresseur et un égaliseur paramétrique à cinq bandes.
- Permet de gérer les modèles et les préréglages, et de télécharger des voix depuis les sources officielles ou tierces.
- Propose la séparation vocale, la synthèse vocale et l’entraînement de modèles. L’interface d’entraînement actuelle nécessite un GPU NVIDIA.
- Prend en charge NVIDIA CUDA et l’accélération DirectML pour les GPU AMD et Intel.

## Chat vocal et musique dans les jeux

1. Installez RVC Fabric et configurez les composants nécessaires. Installez le périphérique audio virtuel VB-Cable, puis redémarrez l’ordinateur.
2. Dans les réglages audio, sélectionnez votre microphone physique et CABLE Input comme sortie. Dans QQ, Discord ou le jeu, choisissez CABLE Output comme microphone.
3. Importez de la musique ou des effets dans la bibliothèque audio, puis double-cliquez sur une entrée pour la diffuser dans le chat vocal. Pour changer de voix pendant la lecture, sélectionnez un modèle et lancez la conversion. Les deux signaux sont mélangés dans la même sortie.
4. Choisissez un casque pour l’écoute locale et activez le retour de la musique si nécessaire. Attribuez des raccourcis globaux aux clips habituels pour les lire, les mettre en pause ou les arrêter pendant le jeu.

## Architecture technique et développement

### Architecture

RVC Fabric utilise l'interface de bureau **Tauri + Rust + React**, l'arrière-plan avec **Python Worker** s'occupe de tous les calculs, les deux communiquent via le protocole de fichiers JSON :

```
RVC Fabric.exe (Interface principale front-end Tauri + Rust + React)
    │
    ▼ Protocole de fichiers JSON (command.json / status.json / worker.pid)
Runtime\pythonw.exe tools/realtime_worker.py (Python 3.9 + CUDA / DirectML)
    └─> gui_v1.py (AudioIoProcess + moteur d'inférence en temps réel rtrvc)
```

L'interface web d'entraînement / d'inférence en amont (Gradio) est conservée en tant que fonctionnalité avancée, accessible depuis la page « Autre ».

### Prérequis de l'environnement et développement

**Prérequis de l'environnement** : Windows 10/11 · Node.js 20+ · Rust Stable · Python 3.13 (scripts de développement)

```bash
# 1. Installer les dépendances du front-end
cd app
npm install

# 2. Lancer le mode développement du client de bureau (Nécessite WebView2 et la chaîne d'outils MSVC)
npm run tauri:dev

# 3. Lancer uniquement l'aperçu UI dans le navigateur
npm run dev
```

### Build et tests

- **Tests unitaires** : Exécutez `scripts\run_tests.bat`
- **Tests unitaires du frontend** : `cd app && npm test`
- **Packager le programme d'installation (NSIS)** : `cd app && npm run tauri:build`
- **Packager la version hors ligne complète** : `python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **Construire le catalogue en ligne** : `python scripts\build_catalog.py build --diff`

## Licence du code source et autorisation d’utilisation des voix

- Le code source de ce projet est sous licence open source [MIT License](./LICENSE).
- Les poids des modèles, les packs vocaux et les ressources tierces sont soumis à leurs accords de licence d'origine.
- Obtenez l’autorisation du titulaire des droits avant d’utiliser la voix d’autrui pour l’entraînement ou la conversion.

## Remerciements

Merci aux excellents projets open source suivants pour leur support technique à RVC Fabric :

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Algorithmes de base et base en amont
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — Modèles acoustiques de base et algorithmes de hauteur
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — Récupération et réduction du bruit en temps réel
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — Algorithmes de hauteur optionnels
- [PyMSS](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Moteur de séparation vocale (suit RVC en amont ; remplace UVR5) · [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) — Source des modèles de séparation · [FFmpeg](https://github.com/FFmpeg/FFmpeg) — Traitement audio
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — Périphérique audio virtuel qui transmet la voix convertie aux jeux et aux applications vocales
