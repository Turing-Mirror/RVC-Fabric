# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

**RVC Fabric** — a Windows desktop realtime voice-changer product built *on top of* upstream RVC WebUI
(`RVC-Project/Retrieval-based-Voice-Conversion-WebUI`). The engine (`infer/`, `configs/`, `gui_v1.py`,
`infer-web.py`, `tools/`) is upstream code; the product shell (`launcher/`) is this fork's own work.
**Do not rewrite RVC algorithms** — changes belong in the shell unless fixing an actual engine bug.

Working branch is `tm-release`; the primary remote is `fabric` (`Turing-Mirror/RVC-Fabric`), not `origin`.
Release artifacts live on CNB (`Turing-Mirror/RVC-Fabric-Releases`, mirrored locally as `CNB-GIT-RELEASE/`).

Project docs are Chinese and live in `docs/`. Read `docs/CONTEXT_HANDOFF.md` first — it is the
maintained handoff doc; `docs/项目结构.md`, `docs/Setup安装与补全.md`, `docs/在线更新与音色库.md`,
`docs/LAUNCHER_DECOMPOSITION.md` and `docs/UI-AESTHETIC-DESIGN.md` cover the rest.

## Commands

```bat
:: Product unit tests (uses Runtime\python.exe if present, else host python)
scripts\run_tests.bat
python -m unittest discover -s tests -p "test_*.py" -v
python -m unittest tests.test_gpu_backend -v                       :: single TestCase module
python -m unittest tests.test_gpu_backend.GpuBackendTests.test_x -v :: single test
python -m pytest tests\test_profiles.py -k round_trips             :: function-style modules

:: Dev launch — never `python launcher/main_app.py` bare except when debugging
OpenApp.vbs      / start_app.bat     :: main app  (launcher/main_app.py)
OpenSetup.vbs    / start.bat         :: launcher  (launcher/bootstrap.py)
scripts\dev\go-web.bat               :: engine WebUI (infer-web.py)
scripts\dev\go-realtime-gui.bat      :: engine realtime GUI (gui_v1.py)

:: Pull Runtime + weights + models from the local RVCMAX reference pack (junction, no multi-GB copy)
python scripts\sync_from_rvcmax.py --variant nvidia|amd|nvidia50

:: Packaging (packaging machine only — needs a full CPython with Tcl/Tk, e.g. `py -3.13`)
python scripts\build_setup.py --clean                          :: thin Inno Setup installer → dist\
python scripts\build_release.py --variant nvidia|amd|nvidia50  :: full offline pack → dist\
python scripts\build_release.py --skip-exe --skip-runtime      :: layout-only dry run
python scripts\pack_gui_patch.py --version 1.2.0 --out dist\gui_patch_1.2.0.zip
python scripts\pack_voice_pack.py --id kiki --name ... --pth ... --out dist\kiki_voice.zip
python scripts\gen_runtime_integrity.py --runtime <dir> --variant nvidia --version YYYY.MM.DD --out ... --alias
python scripts\build_catalog.py build --diff  :: CNB-GIT-RELEASE/catalog-src/*.yaml → index.json + snippet + configs/online_catalog.json（三份生成物勿手改）
python scripts\build_catalog.py check         :: 只校验（含回环过真实客户端解析器），CI 可用
```

Two test styles coexist, and the difference matters: most files are `unittest.TestCase`, but
`test_profiles`, `test_launcher_extracted`, `test_catalog_filter`, `test_index_bindings`,
`test_multipart_download`, `test_collect_diagnostics` and `test_perf_report` are bare pytest
functions — **`unittest discover` silently collects zero tests from them**, so run pytest too before
trusting a green run. Tests needing the ML stack (`test_realtime_math`, `test_benchmark_realtime`)
soft-skip when pytest is absent so the suite stays green on a host without torch; run them with
`Runtime\python.exe -m pytest tests -k realtime_math`.

Upstream CI (`.github/workflows/`) runs `black .` on `main`/`dev` — keep new Python black-formatted.

## Architecture: two processes, one file protocol

This is the single most important thing to understand.

```
变声器.exe / launcher/main_app.py      PyInstaller shell, host Python 3.13, Tk UI
   │                                   NO torch / numpy / audio libs available here
   │  JSON files under User_Data/runtime_control/
   ▼
Runtime\pythonw.exe tools/realtime_worker.py   Runtime Python 3.9 + CUDA or DirectML
   → runpy gui_v1.py with TM_REALTIME_WORKER=1 → rtrvc + AudioIoProcess
```

The shell cannot host torch (PyInstaller-frozen 3.13); inference must run in the embedded 3.9 Runtime.
Consequences that bite:

- **Anything imported by the frozen shell must import cleanly without numpy/torch.** Modules shared
  with the worker (e.g. `tools/dsp_fx.py`) import numpy *lazily*; constants stay pure Python. A
  top-level `import numpy` in a settings-page dependency crashes the released exe.
- Workers are launched with **pythonw only** (no console window), through `launcher/win_util.py`'s
  `_env_for_runtime_python()`, which strips host pollution (`PYTHONHOME`, `PYTHONPATH`, `_MEIPASS`).
  GPU probing happens **in-process in the Runtime** (`launcher/gpu_backend.py`) — never spawn a
  `python.exe` just to probe, it flashes a black window.
- **Exactly one worker process may exist.** `launcher/realtime_client.py` tracks it via
  `status.json` / `worker.pid` and sweeps orphans, with `_KEEP_CMDLINE` guarding against killing
  `main_app` / `bootstrap` / `infer-web`.
- Protocol contract is in `launcher/realtime_protocol.py`: `HOT_KEYS` can be changed live;
  `COLD_KEYS` (device, model path, block time, …) require stop + start.
- pythonw has no console, so the worker tees stdout/stderr to `User_Data/logs/realtime_worker.log`.
  That log is the first place to look for "engine error / pid=0".

## Shell layout (`launcher/`)

`main_app.py` is a ~930-line shell class composed from mixins — it was split out of a 4460-line
monolith, and `docs/LAUNCHER_DECOMPOSITION.md` documents the rules for continuing that split:

- `launcher/pages/*` — one mixin per page/capability (`SettingsPageMixin`, `RealtimeControlMixin`,
  `DockVoiceMixin`, `ModelsPageMixin`, `HotkeysMixin`, …), all combined into `class MainApp(...)`.
  Mixins share one `self`; **public method names, signatures and `self.*` key names are load-bearing**
  because settings/hotkeys resolve them at runtime. Move a cohesive block, don't rewrite behaviour.
- `main_app.py` keeps only lifecycle, chrome (`_build_chrome`/`show_page`), model selection
  (`_select_model`/`_shift_model`), and engine entry points.
- Pure logic that must be unit-testable lives in **Tk-free** modules: `app_presets.py`,
  `voice_history.py`, `audio_devices.py`, `profiles.py`, `hotkeys.py`, `catalog.py`.
  Adding a mixin? Add it to `tests/test_main_app_composition.py` (MRO + method presence, no window).
- `launcher/paths.py` derives `ROOT` for both dev (repo root) and frozen release (exe dir) and is
  the only place that decides `Runtime/`, `User_Data/`, `MODELS_DIR`. Use it; don't recompute paths.
- `launcher/bootstrap.py` is the first-run helper (启动器): shortcut, VB-Cable, Runtime provisioning.
  `launcher/setup_app.py` is **deprecated** — the real installer is Inno Setup.

## Distribution model

The Setup installer is a **thin shell**: launcher + main app + engine source only. Everything heavy is
downloaded by the launcher from CNB after install:

| Piece | Where | Note |
|---|---|---|
| Runtime (Python + torch) | CNB, per GPU variant `nvidia` / `amd` / `nvidia50` | several GB |
| engine-core (hubert, rmvpe, ffmpeg, ffprobe) | CNB LFS, `assets/core/engine-core-*.zip` | shared by all variants |
| VB-Cable, community voice packs | CNB LFS | |

Downloads go through `launcher/online/multipart.py` (multi-connection HTTP Range, `.part` resume,
falls back to single connection). After provisioning, `launcher/runtime_integrity.py` does a
Steam-style verify (file hashes + `import torch` smoke) against `runtime/<variant>/integrity-*.json`,
with an offline fallback in `configs/runtime_integrity/<variant>.json`.

In-app update packages are typed in `launcher/online/package_spec.py` (the authority for the
whitelist): `gui_patch` merges into the install, `voice_pack` installs under `User_Data/models/<id>/`,
`full_package` is **never** merged in-process — it only opens a browser link.

`build_release.py --variant` builds full offline packs; `build_setup.py` reuses its helpers
(`copy_engine`, `shell_pyinstaller_args`, …) for the thin installer.

## Gotchas that have already caused shipped bugs

- **Packaging with a stripped Python breaks tkinter.** `ensure_shell_ui_deps()` hard-fails if the
  packaging interpreter lacks `tkinter`/`_tkinter` or looks like an IDE-agent embedded Python; the
  build also aborts if PyInstaller's warn file still reports missing tkinter, and uses `--noupx`
  (UPX-compressed `pythonXY.dll` fails to load on user machines). Do not weaken these checks.
- **`configs/inuse/config.json` must never contain dev-machine absolute paths** (`L:\…`).
  `sanitize_inuse_config` cleans it at build time and `ensure_clean_inuse_config` at startup.
- **Cover images**: `User_Data/ch-banner/<id>.jpg`, and `config.json` stores the *relative* path
  (`ch-banner/...`) — absolute drive letters are forbidden.
- **Editing `launcher/` does not change the release** until the exe is rebuilt (or a `gui_patch` is
  packed and published).
- **Model loading**: `.pth` files from the community are untrusted pickles — go through
  `infer/lib/safe_load.py` (`weights_only` + path confined under an allowed root), never bare
  `torch.load`. Zip installs go through `launcher/online/safe_zip.py`.
- **AMD/Intel is an environment, not a flag.** DirectML needs the AMD Runtime (torch-directml,
  onnxruntime-directml, `rmvpe.onnx`) *plus* `--dml` / `TM_ACCEL=dml`; flipping the accel setting on a
  CUDA Runtime does not work. See the docstring in `launcher/gpu_backend.py` and `configs/config.py`.

## Conventions

- Windows-first; PowerShell; UTF-8 for all files. Chinese product copy, English code comments.
- UI palette tokens live in `launcher/theme.py` (Schale light-blue, primary `#1289f0`). Forbidden
  colors (RVCMAX pink/purple, teal/cyan accents, neon gradients) are enforced by
  `theme.forbidden_chrome_hexes()` + `tests/test_catalog_theme.py`. Don't restyle the shell's
  character on your own initiative; no emoji unless asked.
- Reusable widgets belong in `launcher/ui/widgets.py`, not inlined in `main_app.py`.
- Docs go in `docs/`. Runtime, `dist/`, `build/`, `RVCMAX/`, large weights, ffmpeg binaries and user
  data stay out of git (`docs/仓库内容说明.md` is the authoritative list; keep it in sync with
  `.gitignore`). Evaluate anything approaching 50–100 MB before committing.
