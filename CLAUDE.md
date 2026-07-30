# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

**RVC Fabric** — a Windows desktop realtime voice-changer product built *on top of* upstream RVC WebUI
(`RVC-Project/Retrieval-based-Voice-Conversion-WebUI`). The engine (`infer/`, `configs/`, `gui_v1.py`,
`infer-web.py`, `tools/`) is upstream code; the product shell (`launcher/`) is this fork's own work.
**Do not rewrite RVC algorithms** — changes belong in the shell unless fixing an actual engine bug.

Working branch is `tm-release`; the primary remote is `fabric` (`Turing-Mirror/RVC-Fabric`), not `origin`.
Release artifacts live on CNB (`Turing-Mirror/RVC-Fabric-Releases`, mirrored locally as `CNB-GIT-RELEASE/`).
Current shipping shell version: **1.2.3** (Full; stable forms `X.Y.Z` or `X.Y.Z-hotfixN` — see `docs/在线更新与音色库.md` §0).

Project docs are Chinese and live in `docs/`. Read `docs/CONTEXT_HANDOFF.md` first — it is the
maintained handoff doc. Also relevant:

| Doc | Topic |
|-----|--------|
| `docs/项目结构.md` | Directory roles |
| `docs/Setup安装与补全.md` | Thin Setup + Runtime provision |
| `docs/在线更新与音色库.md` | Update packages + voice packs |
| `docs/LAUNCHER_DECOMPOSITION.md` | main_app mixin split rules |
| `docs/UI-AESTHETIC-DESIGN.md` | Schale palette / forbidden chrome |
| `docs/广场页与内容运营.md` | plaza.json feed + ops handbook |
| `docs/PERF_NOTES.md` | Perf bench + residual inference roadmap |
| `docs/审查缺陷清单.md` | Shell review backlog (high fixed; pick medium/low by item) |

## Commands

```bat
:: Product unit tests (uses Runtime\python.exe if present, else host python)
scripts\run_tests.bat
python -m unittest discover -s tests -p "test_*.py" -v
python -m unittest tests.test_gpu_backend -v                       :: single TestCase module
python -m unittest tests.test_gpu_backend.GpuBackendTests.test_x -v :: single test
python -m pytest tests -q                                          :: host 3.13 has pytest
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
python scripts\build_catalog.py build --diff  :: catalog-src → index + snippet + online_catalog + plaza + changelog.json（生成物勿手改）
python scripts\build_catalog.py check         :: 只校验（含回环过真实客户端解析器），CI 可用
```

Two test styles coexist, and the difference matters: most files are `unittest.TestCase`, but
`test_profiles`, `test_launcher_extracted`, `test_catalog_filter`, `test_index_bindings`,
`test_multipart_download`, `test_collect_diagnostics`, `test_perf_bench`, `test_perf_report`
(and similar bare-function modules) are pytest style — **`unittest discover` silently collects
zero tests from them**, so run pytest too before trusting a green run.

Tests needing the ML stack (`test_realtime_math`, `test_benchmark_realtime`) soft-skip when
numpy/torch are absent (guards probe the real deps via `find_spec`, never pytest —
a host with pytest but no numpy must stay green too). The product Runtime has no pytest, so run them
with `Runtime\python.exe -m unittest discover -s tests -p "test_realtime_math.py"`.

Notable newer unit suites: `tests/test_plaza.py` (feed parse/filter/stamp), `tests/test_dpi_scale.py`
(px() identity at 96dpi + DPI helpers), `tests/test_main_app_composition.py` (MRO + method contract
including PlazaPageMixin / page-switch snapshots).

Upstream CI (`.github/workflows/`) runs `black .` on `main`/`dev` — keep new Python black-formatted.
Host 3.13 already has pytest + black; Runtime 3.9 does not.

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

`main_app.py` is a ~1180-line shell class composed from mixins — it was split out of a 4460-line
monolith, and `docs/LAUNCHER_DECOMPOSITION.md` documents the rules for continuing that split:

- `launcher/pages/*` — one mixin per page/capability:
  `OnboardingMixin`, `HotkeysMixin`, `MonitorMixin`, `RealtimeControlMixin`, `DockVoiceMixin`,
  `ProfilesMixin`, `ConsultMixin`, `HomePageMixin`, `ModelsPageMixin`, **`PlazaPageMixin`**,
  `MorePageMixin`, `SettingsPageMixin`, … all combined into `class MainApp(...)`.
  Mixins share one `self`; **public method names, signatures and `self.*` key names are load-bearing**
  because settings/hotkeys resolve them at runtime. Move a cohesive block, don't rewrite behaviour.
- Nav order (product): 首页 · 模型 · **广场** · 设置 · 说明 · 其他（广场 = `Ctrl+5`）。
- `main_app.py` keeps lifecycle, chrome (`_build_chrome`/`show_page`), model selection
  (`_select_model`/`_shift_model`), and engine entry points.
- **Page switch**: all pages stay gridded in one cell; `show_page` only `tkraise`s (no
  pack_forget white flash). Catalog-heavy pages use render-snapshot short-circuit stamps
  (`_models_catalog_stamp`, plaza feed stamp, …); data mutation must call
  `_invalidate_catalog_views()` (or the page-local invalidator).
- Pure logic that must be unit-testable lives in **Tk-free** modules: `app_presets.py`,
  `voice_history.py`, `audio_devices.py`, `profiles.py`, `hotkeys.py`, `catalog.py`,
  `online/plaza.py`. Adding a mixin? Add it to `tests/test_main_app_composition.py`
  (MRO + method presence, no window).
- `launcher/paths.py` derives `ROOT` for both dev (repo root) and frozen release (exe dir) and is
  the only place that decides `Runtime/`, `User_Data/`, `MODELS_DIR`. Use it; don't recompute paths.
- `launcher/bootstrap.py` is the first-run helper (启动器): shortcut, VB-Cable, Runtime provisioning.
  `launcher/setup_app.py` is **deprecated** — the real installer is Inno Setup.

### HiDPI / typography (2026-07-27)

- Shell + bootstrap declare **PMv2 DPI awareness** at startup and set `tk scaling` from real DPI.
- Pixel layout constants go through **`theme.px()`** (identity at 96dpi). Widget `width`/`height`
  params that are design units are scaled inside the widget — do not double-`px()`.
- CJK captions must not use Cascadia Mono (missing CJK glyphs → per-char fallback blur).
  ASCII/CJK dual-mode text uses `theme.meta_font`. Minimum caption sizes: no 7pt; ≤9pt bold → 10pt.
- Window geometry persistence stores `win_dpi` for migration. See `tests/test_dpi_scale.py`.
- **Launcher source only until rebuilt**: edits under `launcher/` need a new exe or `gui_patch` to
  reach users. 125%/150% real-device acceptance still pending.

### Plaza feed (2026-07-27, commit `0800079`)

- Tk-free core: `launcher/online/plaza.py` — parse / filter (schedule window, version gate with
  `-partN`, placement) / sort / disk cache / image cache. Image hosts limited to **cnb.cool**.
- UI: `launcher/pages/plaza_page.py` (page + models-page dismissible ad banner + nav badge).
- Feed: CNB repo root **`plaza.json`**, independent of `index.json`. Source:
  `CNB-GIT-RELEASE/catalog-src/plaza.yaml` → `scripts/build_catalog.py` (4th artifact).
- **Zero telemetry**: click stats only via compile-time utm on ad/sponsor URLs. Future beacon work
  must stay inside `on_card_clicked` / `mark_seen` with a hard-coded endpoint — feed never names
  a report URL.
- Dismiss is permanent per card `id` (`plaza_dismissed` in app config); re-expose requires a new id.
- `feed_stamp` must cover **all** render fields or refresh short-circuits leave stale UI.
- Ops handbook: `docs/广场页与内容运营.md`.

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
`compare_versions` (`launcher/version.py`): base `X.Y.Z`, post-release `-hotfixN` (newer than bare base),
historical `-partN` prerelease (older than bare base; **do not ship new part on stable**). Same Full
never OTAs — always bump hotfix or base. Optional `build_id` is metadata only.

`build_release.py --variant` builds full offline packs; `build_setup.py` reuses its helpers
(`copy_engine`, `shell_pyinstaller_args`, …) for the thin installer.

Community store: concurrent downloads (2 workers + queue), paging by upload time, series zone;
see home/store UI + `launcher/ui/store_page.py`.

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
- **Diagnostics pack** (More page): can run a quick perf bench first (`launcher/perf_bench.py` →
  Runtime runs `tools/benchmark_realtime.py`), then bundles `perf_reports/bench_*.json` + machine
  info. Log tails matter when `realtime_worker.log` grows large (see review backlog).

## Parallel AI / interrupted work

- Other agents (glm / TRAE / Grok) may edit the same worktree while Claude is mid-session.
  Before committing, `git status` + per-file `git diff`, split ownership, then commit by logic.
  Temp dirs (`.trae/`, `TEMP_*`) stay out of git.
- Shell review backlog: `docs/审查缺陷清单.md` (high items fixed 2026-07-28). Pick items when
  fixing. Do not add dated SESSION_*/PLAN_*/REVIEW_* scatter docs — update
  `docs/CONTEXT_HANDOFF.md` instead.

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
- After each task, commit on `tm-release`; push to `fabric` only when asked (plaza commit may still
  be local-only relative to `fabric/tm-release`).
