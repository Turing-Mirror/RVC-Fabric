# RVC Fabric desktop shell (`app/`)

Tauri 2 + React + TypeScript + Tailwind UI host for RVC Fabric.
Realtime inference still runs in the embedded Runtime (`pythonw` + `tools/realtime_worker.py`).

This host **is** the product shell (Tk / `launcher/` UI removed). Only the realtime
worker stays on Python under `Runtime\pythonw.exe`.

## Requirements

- Node 20+
- Rust stable (`x86_64-pc-windows-msvc`)
- Visual Studio Build Tools with “Desktop development with C++” (`link.exe`)
- Windows WebView2

## Dev

```bat
cd app
npm install
npm run tauri:dev
```

UI-only (browser, no native window chrome):

```bat
npm run dev
```

## Build

```bat
cd app
npm run tauri:build
```

Vite writes static assets to `app/frontend/`.  
`tauri.conf.json` sets `frontendDist` to that folder so the UI pack can be shipped and updated separately from the Rust binary.

## Layout

| Path | Role |
|------|------|
| `src/` | React UI |
| `src-tauri/` | Rust host |
| `frontend/` | Production UI build output (gitignored) |

Product behaviour and decisions: see internal `docs/项目白皮书.md` (gitignored).

## Worker bridge

The shell talks to `Runtime\\pythonw.exe tools\\realtime_worker.py` through the same
JSON files as the Tk shell (`User_Data/runtime_control/`). On Windows use the F: MSVC
env when building the native host:

```bat
call F:\VS2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat
set CARGO_TARGET_DIR=F:\VS2022\cargo-target
cd /d path\to\repo\app
npm run tauri:dev
```

## Voice catalog & community store

- `voices_list` / `voices_select` — local `User_Data/models` + legacy weights
- Index panel: bind / use / unbind `.index` (copied next to `.pth`)
- Profiles: list / switch / save / import / export `.tmvp`
- Import `.pth` / `.index` / `.zip`; delete / rename / promote legacy
- Community voices live on the **Plaza** page (dual-source catalog, series zone,
  third-party disclaimer). Multi-connection download via shared `download.rs`
  (`DownloadKind::VoicePack`). Display names follow `name_i18n` + UI locale.

## Runtime provision

- `provision_status` — Runtime ready? GPU recommend (WMI, no torch).
- `provision_start` / `provision_cancel` — download from CNB into
  `User_Data/update_cache/runtime`, safe-extract to `Runtime/`, write
  `package_meta.json`. Progress events: `provision-progress`.
- First-run UI: `LanguageGate` (locale) then `ProvisionGate` (Runtime + VB-Cable pack).
- **engine-core** (hubert / rmvpe / ffmpeg) is **on-demand** via Plaza → 下载模型
  (`assets_ensure_engine_core`), not part of the first Runtime gate.

### Shared downloader (`src-tauri/src/download.rs`)

Engine: **[ripget](https://github.com/sam0x17/ripget)** (MIT/Apache-2.0) —
multi-part HTTP Range downloads with retries and idle reconnect (aria2-style).
We do **not** reimplement range splitting; only adaptive thread count + product
glue (mirrors, sha256, cancel, `DownloadKind`).

Adaptive threads (`auto_connections`, same spirit as `launcher/online/multipart.py`):

| Size | Connections |
|------|-------------|
| &lt; 16 MiB | 1 |
| &lt; 64 MiB | 8 |
| ≥ 1 GiB | 16 (cap 32) |

`DownloadKind` — same API for all product artifacts:

| Kind | Use |
|------|-----|
| `Runtime` | provision (now) |
| `VoicePack` | community / official voice zip |
| `GuiPatch` | shell update packages |
| `Generic` | engine-core, VB-Cable, … |

```rust
download::download_request(DownloadRequest {
    urls, dest, expected_sha256, size_hint, connections: None, kind: DownloadKind::VoicePack,
}, cancel, Some(progress))?;
```
