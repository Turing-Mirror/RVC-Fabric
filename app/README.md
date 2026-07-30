# RVC Fabric — Tauri shell (`app/`)

New product shell: **Tauri 2 + React + TypeScript + Tailwind**.  
Python remains only for the realtime inference worker (`Runtime\pythonw` + `tools/realtime_worker.py`).

Migration plan (private handoff): stage 1 scaffold → worker → provision → models/store → remaining pages → cutover.

## Dev

Requirements:

- Node 20+
- Rust stable (`x86_64-pc-windows-msvc`)
- **Visual Studio Build Tools** with “Desktop development with C++” (needs `link.exe`)
- Windows WebView2 runtime

```bat
cd app
npm install
npm run tauri:dev
```

UI-only (browser, no native chrome):

```bat
npm run dev
```

## Build

```bat
cd app
npm run tauri:build
```

Vite emits to `app/frontend/` (hot-update **strategy A**).  
`tauri.conf.json` points `frontendDist` at that folder and bundles it as install resource `frontend/`.

## Layout

| Path | Role |
|------|------|
| `src/` | React UI (pages, dock, nav, tokens) |
| `src-tauri/` | Rust host (window, later worker/provision) |
| `frontend/` | Build output — replaceable UI pack |

## Stage map

1. **Scaffold** (this) — window, 6-page nav, dock skeleton, strategy A paths  
2. Worker bridge — pythonw, devices, start/stop, hot keys, meter  
3. Runtime download / integrity / VB-Cable / first-run  
4. Models + community store + index + profiles  
5. Plaza, full settings, help, more, tray, diagnostics  
6. Drop Tk shell, Inno → Tauri artifact, version/ad rules  

**Rule:** only change UI implementation; keep product behaviour 1:1 with `launcher/pages/*`.
