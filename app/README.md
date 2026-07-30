# RVC Fabric desktop shell (`app/`)

Tauri 2 + React + TypeScript + Tailwind UI host for RVC Fabric.
Realtime inference still runs in the embedded Runtime (`pythonw` + `tools/realtime_worker.py`).

The classic Tk shell remains under `launcher/` until this host is feature-complete.

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

Product behaviour should stay aligned with the existing shell under `launcher/`.

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

## Runtime provision (stage 3)

- `provision_status` — Runtime ready? GPU recommend (WMI, no torch).
- `provision_start` / `provision_cancel` — download from CNB (Range resume +
  sha256) into `User_Data/update_cache/runtime`, safe-extract to `Runtime/`,
  write `package_meta.json`. Progress events: `provision-progress`.
- First-run UI: `ProvisionGate` when Runtime is missing.
