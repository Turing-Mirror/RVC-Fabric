<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="320">

# RVC Fabric

<!-- lang-nav -->
[简体中文](./README.md)　·　[繁體中文](./README_zh-TW.md)　·　[English](./README_en.md)　·　[日本語](./README_ja.md)　·　[한국어](./README_ko.md)　·　[Español](./README_es.md)　·　Français　·　[Русский](./README_ru.md)
<!-- lang-nav -->

**Client de bureau de modification vocale par IA en temps réel haute performance**

<!-- screenshots -->
<img src="assets/screenshots/home.png" alt="Home" width="32%">
<img src="assets/screenshots/settings.png" alt="Settings" width="32%">
<img src="assets/screenshots/misc.png" alt="More" width="32%">
<!-- screenshots -->

Profondément personnalisé à partir de [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) · Développé et maintenu par [Turing Mirror](https://github.com/Turing-Mirror)

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

[Dépôt GitHub](https://github.com/Turing-Mirror/RVC-Fabric) · [Téléchargement CNB](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**Réseaux sociaux**　[Bilibili @Turing Mirror](https://space.bilibili.com/3546871148579062)　·　[Douyin @Turing Mirror](https://v.douyin.com/6NxXcrKK9cc) (ID Douyin `TuringMirror`)　·　[Xiaohongshu @Turing Mirror](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094) (ID Xiaohongshu `TuringMirror`)　·　Groupe QQ @Communauté Turing Mirror (N° de groupe `1077458748`)

<!-- qq-group -->
<img src="assets/brand/qq_group.jpg" alt="Code QR du groupe QQ" width="200">
<!-- qq-group -->

**Sponsorisation et promotion**　[Moitié prix le premier mois · Serveur cloud / Cloud de jeu / Serveur panel avec un bon rapport qualité-prix · Rainyun](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## Introduction du projet

RVC Fabric est un logiciel de bureau de modification vocale par IA en temps réel pour Windows, prêt à l'emploi : pas besoin d'installer vous-même Python, PyTorch, ni d'ouvrir un navigateur pour accéder à la page Gradio. Il suffit de l'installer pour modifier votre voix.

Pour jouer avec des amis, discuter en vocal, interagir en direct, ou produire de l'audio — conversion vocale en temps réel à faible latence et haute fidélité, un seul logiciel suffit.

## Fonctionnalités principales

- **Modification vocale en temps réel** : Inférence en temps réel à faible latence, changement fluide de voix pendant la modification vocale, bascule en un clic « Modification vocale en temps réel / Voix originale (Bypass) ».
- **Chaîne d'effets DSP** : Noise gate (porte de bruit) en post-traitement, compresseur dynamique et égaliseur paramétrique à 5 bandes intégrés, support des préréglages et de l'ajustement fin.
- **Gestion des voix et des préréglages** : Bibliothèque de voix sous forme de grille, liaison de la bibliothèque de caractéristiques de récupération .index, les préréglages de paramètres peuvent être sauvegardés, importés, exportés et partagés.
- **Place communautaire des voix** : Boutique à double source (source officielle Turing Mirror + sources ouvertes tierces), téléchargement simultané multi-thread, reprise des téléchargements interrompus.
- **Boîte à outils audio intégrée** :
  - **Séparation vocale** : Basé sur le modèle de séparation PyMSS, extraction rapide de la voix a cappella et de l'accompagnement.
  - **Synthèse vocale** : Saisie de texte pour générer de la voix, et conversion automatique vers la voix cible (TTS + RVC).
  - **Entraînement vocal** : Panneau d'entraînement intégré, entraînement de voix exclusives en un clic (nécessite une carte graphique NVIDIA).
- **Accélération matérielle entièrement automatique** : Identification automatique de NVIDIA CUDA (y compris la série RTX 50) et AMD / Intel (DirectML), avec téléchargement du runtime de calcul correspondant.

## Démarrage rapide

### 1. Installation et initialisation

1. Téléchargez `RVC_Fabric_Setup.exe` depuis la [page Releases](https://github.com/Turing-Mirror/RVC-Fabric/releases) ;
2. Exécutez le programme d'installation (il est recommandé de l'installer dans un chemin uniquement en anglais) ;
3. Lancez le logiciel et suivez le guide pour terminer automatiquement l'identification du matériel, la complétion du runtime et l'installation de la carte son virtuelle.

### 2. Routage audio (Méthode de la carte son virtuelle)

Pour que les personnes dans un jeu, QQ, Discord ou un logiciel de streaming en direct entendent la voix modifiée, la carte son virtuelle VB-Cable doit faire le relais au milieu :

| Élément de configuration | Choix recommandé | Description |
| :--- | :--- | :--- |
| **Entrée du logiciel** | Microphone réel | Capture la voix parlée d'origine |
| **Sortie du logiciel** | **CABLE Input** | Envoie le résultat de la modification vocale dans la carte son virtuelle |
| **Écoute (Facultatif)** | Écouteurs physiques / Haut-parleurs | Écoute locale en temps réel de l'effet de modification vocale |
| **Microphone du jeu / vocal** | **CABLE Output** | Logiciel tiers recevant l'effet de modification vocale |
| **Lecture par défaut de Windows** | Écouteurs physiques (Ne pas choisir CABLE) | Assure la lecture normale des autres sons du système |

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
- **Packager le programme d'installation (NSIS)** : `cd app && npm run tauri:build`
- **Packager la version hors ligne complète** : `python scripts\build_release.py --variant nvidia|amd|nvidia50`
- **Construire le catalogue en ligne** : `python scripts\build_catalog.py build --diff`

## Licence open source et clause de non-responsabilité

- Le code source de ce projet est sous licence open source [MIT License](./LICENSE).
- Les poids des modèles, les packs vocaux et les ressources tierces sont soumis à leurs accords de licence d'origine.
- **Clause de non-responsabilité** : N'utilisez pas ce logiciel pour usurper une identité, frauder, harceler ou pour tout usage illégal non autorisé. Avant d'utiliser la voix de quelqu'un d'autre pour l'entraînement ou la conversion, vous devez obtenir l'autorisation explicite du titulaire des droits. L'utilisateur est seul responsable de toutes les conséquences juridiques découlant d'une utilisation non conforme.

## Remerciements

Merci aux excellents projets open source suivants pour leur support technique à RVC Fabric :

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — Algorithmes de base et base en amont
- [ContentVec](https://github.com/auspicious3000/contentvec) · [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) · [RMVPE](https://github.com/Dream-High/RMVPE) — Modèles acoustiques de base et algorithmes de hauteur
- [faiss](https://github.com/facebookresearch/faiss) · [TorchGate](https://github.com/timsainb/TorchGate) — Récupération et réduction du bruit en temps réel
- [FCPE](https://github.com/CNChTu/FCPE) · [Parselmouth](https://github.com/YannickJadoul/Parselmouth) · [torchcrepe](https://github.com/maxrmorrison/torchcrepe) — Algorithmes de hauteur optionnels
- [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) (Modèles de séparation basés sur UVR, via PyMSS) · [FFmpeg](https://github.com/FFmpeg/FFmpeg) — Séparation vocale et traitement audio
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — Carte son virtuelle (Indispensable pour entendre la voix modifiée dans le jeu)
