//! Tray, global hotkeys, diagnostics and consult packs.
//!
//! These are the pieces of the Python shell that live outside any page:
//! `launcher/tray.py`, `launcher/hotkeys.py`, the 「其他」page's diagnostics
//! bundle, and `launcher/consult_pack.py`.
//!
//! Hotkey combos match the old shell exactly — users have muscle memory:
//! Ctrl+F2 toggle, Ctrl+F3 mode, Ctrl+F5/F6 previous/next voice.

use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Stdio;

use serde_json::{json, Value};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager};

use crate::{config, paths, worker};

// ---------------------------------------------------------------------------
// Tray
// ---------------------------------------------------------------------------

/// Build the tray icon. Closing to tray is what keeps conversion running while
/// the window is out of the way, so the tray must always exist — not only when
/// the user picked "minimise to tray".
pub fn install_tray(app: &AppHandle) -> Result<(), String> {
    let show = MenuItem::with_id(app, "show", &crate::i18n::t("tray.show"), true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let toggle = MenuItem::with_id(
        app,
        "toggle",
        &crate::i18n::t("tray.toggle"),
        true,
        None::<&str>,
    )
    .map_err(|e| e.to_string())?;
    let quit = MenuItem::with_id(app, "quit", &crate::i18n::t("tray.quit"), true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let menu =
        Menu::with_items(app, &[&show, &toggle, &quit]).map_err(|e| e.to_string())?;

    TrayIconBuilder::with_id("main")
        .tooltip("RVC Fabric")
        .icon(
            app.default_window_icon()
                .cloned()
                .ok_or_else(|| crate::i18n::t("tray.missingIcon"))?,
        )
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(move |app, event| match event.id.as_ref() {
            "show" => focus_main(app),
            "toggle" => {
                let _ = app.emit("tray://toggle-vc", ());
            }
            "quit" => {
                // Stop the stream before leaving, otherwise the worker keeps
                // holding the audio device after the UI is gone.
                if let Some(root) = root_of(app) {
                    let _ = worker::stop_vc(&root, true);
                }
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            // Only the *left* button opens the window, and only on release.
            //
            // `TrayIconEvent::Click` fires for every button, right-click
            // included. On Windows the right-click menu is a tracked popup
            // owned by a hidden message window: focusing another window while
            // it is up makes Windows dismiss it. Reacting to the right-click
            // here is what made the menu flash and vanish. Matching on Down as
            // well would fire twice per click.
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                focus_main(&tray.app_handle().clone());
            }
        })
        .build(app)
        .map_err(|e| e.to_string())?;
    Ok(())
}

fn focus_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        // 显示器拔掉之后窗口会留在一块已经不存在的屏上。这时候「打开主界面」
        // 什么都不会发生，而托盘是用户此刻唯一的入口——先把它拉回来。只在整个
        // 窗口都不在任何屏上时才动，用户自己把窗口摆在哪块屏是他的事。
        crate::window_watch::rescue_if_offscreen(&w);
        let _ = w.set_focus();
    }
}

fn root_of(app: &AppHandle) -> Option<PathBuf> {
    app.try_state::<std::sync::Mutex<crate::AppState>>()
        // Poison-safe: on a poisoned state we still want the tray quit item to
        // be able to stop the worker.
        .map(|s| {
            s.lock()
                .unwrap_or_else(|e| e.into_inner())
                .root
                .clone()
        })
}

// ---------------------------------------------------------------------------
// Global hotkeys
// ---------------------------------------------------------------------------

/// 全局快捷键：配置键名、动作名、默认组合。
///
/// 前四个的默认值和旧的 Python 壳一样，用户有肌肉记忆，不能改。用户改过的
/// 组合存在配置里，这里只是缺省。
///
/// 收录标准只有一条：**这件事值不值得在窗口看不见的时候做**。全局快捷键是给
/// 正在游戏、正在直播、主界面缩在托盘里的人用的。改设置、翻音色库这些非得看着
/// 界面才能做的事，给它配快捷键没有意义。
pub const HOTKEYS: &[(&str, &str, &str)] = &[
    ("hotkey_toggle_vc", "toggle-vc", "CmdOrCtrl+F2"),
    ("hotkey_toggle_mode", "toggle-mode", "CmdOrCtrl+F3"),
    ("hotkey_prev_voice", "prev-voice", "CmdOrCtrl+F5"),
    ("hotkey_next_voice", "next-voice", "CmdOrCtrl+F6"),
    // 音高一次一个半音。开着黑发现音色偏高偏低，不用退出游戏调。
    ("hotkey_pitch_up", "pitch-up", "CmdOrCtrl+F7"),
    ("hotkey_pitch_down", "pitch-down", "CmdOrCtrl+F8"),
    // 监听自己。队友说你声音怪，想立刻听一耳朵自己现在是什么效果。
    ("hotkey_toggle_monitor", "toggle-monitor", "CmdOrCtrl+F9"),
    // 后期音效总开关。怀疑是压缩/均衡把声音搞糊了，一键旁路对比。
    ("hotkey_toggle_fx", "toggle-fx", "CmdOrCtrl+F10"),
    // 显示 / 隐藏主界面。缩在托盘里时这是唯一不用去点托盘图标的入口。
    ("hotkey_toggle_window", "toggle-window", "CmdOrCtrl+F11"),
];

/// 组合键的合法形状：零个或多个修饰键 + 一个主键，`+` 连接。
///
/// 注册失败的组合会被 Tauri 直接拒掉，但一个乱七八糟的字符串还可能让
/// on_shortcut 直接 panic —— 先自己筛一道。
fn combo_ok(s: &str) -> bool {
    let s = s.trim();
    if s.is_empty() || s.len() > 48 {
        return false;
    }
    let parts: Vec<&str> = s.split('+').map(str::trim).collect();
    if parts.len() > 5 || parts.iter().any(|p| p.is_empty()) {
        return false;
    }
    parts
        .iter()
        .all(|p| p.chars().all(|c| c.is_ascii_alphanumeric()))
}

/// 用户配的组合键，没配或配得不合法就用默认值。
fn combo_for(root: Option<&Path>, key: &str, fallback: &str) -> String {
    let Some(root) = root else {
        return fallback.to_string();
    };
    let v = config::read(root);
    let raw = v.get(key).and_then(|x| x.as_str()).unwrap_or("").trim();
    if combo_ok(raw) {
        raw.to_string()
    } else {
        fallback.to_string()
    }
}

/// 某个快捷键要不要抢成全局的。配置键是组合键的键名加 `_global`。
///
/// 默认 true —— 以前九个一律全局，改默认值等于悄悄拿走用户已经在用的功能。
///
/// 关掉之后这个组合就只在 RVC Fabric 是当前窗口时有效（由前端的 keydown
/// 兜着）。这件事有意义是因为全局快捷键是**独占**的：Ctrl+F7 被我们抢走之后，
/// 用户在别的软件里就再也按不出它原本的功能了。有人只想在切回本软件时用一下，
/// 不想为此把这个组合从整台机器上让出来。
pub fn global_for(root: Option<&Path>, key: &str) -> bool {
    let Some(root) = root else {
        return true;
    };
    config::read(root)
        .get(&format!("{key}_global"))
        .and_then(|x| x.as_bool())
        .unwrap_or(true)
}

/// 藏着就叫出来，已经在前面就收回托盘。
///
/// 「已经在前面」用 is_focused 判断，不用 is_visible：窗口可能可见但被游戏
/// 全屏盖住，那时候用户按这个键是想把它调出来，不是想让它消失。
fn toggle_main_window(app: &AppHandle) {
    let Some(w) = app.get_webview_window("main") else {
        return;
    };
    let up = w.is_visible().unwrap_or(false)
        && !w.is_minimized().unwrap_or(false)
        && w.is_focused().unwrap_or(false);
    if up {
        let _ = w.hide();
    } else {
        focus_main(app);
    }
}

/// Register or unregister the global hotkeys. Failing to grab a combo (another
/// app already owns it) must not break the rest — report and carry on.
pub fn apply_hotkeys(app: &AppHandle, enabled: bool) -> Value {
    use tauri_plugin_global_shortcut::GlobalShortcutExt;
    let gs = app.global_shortcut();
    let _ = gs.unregister_all();
    if !enabled {
        return json!({"enabled": false, "registered": [], "failed": []});
    }
    let root = root_of(app);
    let mut ok: Vec<String> = Vec::new();
    let mut failed: Vec<String> = Vec::new();
    // 用户特地设成「只在软件内」的那些。不注册全局，交给前端的 keydown。
    let mut local: Vec<String> = Vec::new();
    for (key, action, default) in HOTKEYS {
        let combo = combo_for(root.as_deref(), key, default);
        if !global_for(root.as_deref(), key) {
            local.push(combo);
            continue;
        }
        let handle = app.clone();
        let act = action.to_string();
        match gs.on_shortcut(combo.as_str(), move |_a, _s, _e| {
            // 显示 / 隐藏窗口在这里就地做完，不往前端发事件。
            //
            // 窗口藏起来的时候 webview 有可能被系统挂起，事件到不了前端 ——
            // 而「窗口是藏着的」恰恰是最需要这个快捷键的时候。发事件让前端
            // 把自己显示出来，等于让一个睡着的人自己叫醒自己。
            if act == "toggle-window" {
                toggle_main_window(&handle);
                return;
            }
            let _ = handle.emit(&format!("hotkey://{act}"), ());
        }) {
            Ok(()) => ok.push(combo),
            // 组合被别的程序占了就跳过这一个，其余的照常注册 —— 一个冲突
            // 不该让所有快捷键全废。界面上会把失败的那个标出来。
            Err(_) => failed.push(combo),
        }
    }
    json!({"enabled": true, "registered": ok, "failed": failed, "local": local})
}

// ---------------------------------------------------------------------------
// Diagnostics bundle
// ---------------------------------------------------------------------------

/// Run `tools/benchmark_realtime.py` in the Runtime, writing a JSON report into
/// `User_Data/perf_reports/`. Takes roughly a minute; callers must say so.
///
/// 以前写成 `--out <目录>` 且没传必填的 `--pth`，脚本一启动就 argparse 失败，
/// 诊断包里永远没有新性能报告——等于「直接生成诊断包」。
pub fn run_perf_bench(root: &Path) -> Result<PathBuf, String> {
    let py = paths::runtime_python(root)
        .or_else(|| paths::runtime_pythonw(root))
        .ok_or_else(|| crate::i18n::t("s.c8c05e7db7"))?;
    let script = root.join("tools").join("benchmark_realtime.py");
    if !script.is_file() {
        return Err(crate::i18n::t("s.c41c6ca117").into());
    }

    let cfg = config::read(root);
    let pth = cfg
        .get("pth_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    let pth = if !pth.is_empty() && Path::new(&pth).is_file() {
        pth
    } else {
        // 兜底 last_model_path（有时 pth_path 是相对路径或空）
        let alt = cfg
            .get("last_model_path")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim()
            .to_string();
        if alt.is_empty() || !Path::new(&alt).is_file() {
            return Err(crate::i18n::t("s.40019094c0").into());
        }
        alt
    };
    let index = cfg
        .get("index_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    let pitch = cfg
        .get("pitch")
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    let formant = cfg
        .get("formant")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0);
    let f0method = cfg
        .get("f0method")
        .and_then(|v| v.as_str())
        .unwrap_or("rmvpe");
    // harvest 在 bench 里不支持
    let f0method = if f0method == "harvest" {
        "rmvpe"
    } else {
        f0method
    };
    let block_time = cfg
        .get("block_time")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.25);
    let crossfade = cfg
        .get("crossfade_length")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.05);
    let extra = cfg
        .get("extra_time")
        .and_then(|v| v.as_f64())
        .unwrap_or(2.5);
    let index_rate = cfg
        .get("index_rate")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0);

    let out_dir = paths::user_data(root).join("perf_reports");
    std::fs::create_dir_all(&out_dir).map_err(|e| e.to_string())?;
    let stamp = now_stamp();
    let json_out = out_dir.join(format!("bench_{stamp}.json"));
    let log_path = paths::logs_dir(root).join("perf_bench.log");
    let _ = std::fs::create_dir_all(paths::logs_dir(root));
    let errfile = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .ok();

    let mut cmd = std::process::Command::new(py);
    cmd.arg(&script)
        .arg("--pth")
        .arg(&pth)
        .arg("--json-out")
        .arg(&json_out)
        .arg("--f0method")
        .arg(f0method)
        .arg("--pitch")
        .arg(pitch.to_string())
        .arg("--formant")
        .arg(formant.to_string())
        .arg("--block-time")
        .arg(block_time.to_string())
        .arg("--crossfade-time")
        .arg(crossfade.to_string())
        .arg("--extra-time")
        .arg(extra.to_string())
        // 诊断场景略减块数，控制在约一分钟内
        .arg("--n-blocks")
        .arg("120")
        .arg("--warmup")
        .arg("8")
        .current_dir(root)
        .envs(worker::env_for_runtime(root))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(match errfile {
            Some(f) => Stdio::from(f),
            None => Stdio::null(),
        });
    if !index.is_empty() && Path::new(&index).is_file() {
        cmd.arg("--index").arg(&index);
        if index_rate > 0.0 {
            cmd.arg("--index-rate").arg(index_rate.to_string());
        }
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    crate::logging::shell_log!(
        "perf bench: pth={} json={}",
        pth,
        json_out.display()
    );
    let status = cmd.status().map_err(|e| crate::i18n::te("s.84256012c6", &(e)))?;
    if !status.success() {
        return Err(crate::i18n::te(
            "s.470a002848",
            &status.code().map(|c| c.to_string()).unwrap_or_else(|| "?".into()),
        ));
    }
    if !json_out.is_file() {
        return Err(crate::i18n::t("s.f9e62f8c38").into());
    }
    Ok(json_out)
}

fn tail_bytes(path: &Path, max: usize) -> String {
    let Ok(data) = std::fs::read(path) else {
        return String::new();
    };
    let start = data.len().saturating_sub(max);
    String::from_utf8_lossy(&data[start..]).to_string()
}

/// Zip logs + machine info + effective settings into `User_Data/diagnostics/`.
///
/// `with_perf`：用户确认后才跑 bench。Log tails 有上限，避免几百 MB 的废包。
/// 返回 (zip 路径, 性能测试说明)。
pub fn build_diagnostics(root: &Path, with_perf: bool) -> Result<(PathBuf, String), String> {
    let perf_note = if with_perf {
        match run_perf_bench(root) {
            Ok(p) => crate::i18n::te("s.37f36c5824", &p.file_name().unwrap_or_default().to_string_lossy()),
            Err(e) => {
                crate::logging::shell_log!("perf bench failed: {e}");
                crate::i18n::te("s.eea9655c7b", &(e))
            }
        }
    } else {
        crate::i18n::t("s.733f7e7b3f")
    };

    let out_dir = paths::user_data(root).join("diagnostics");
    std::fs::create_dir_all(&out_dir).map_err(|e| e.to_string())?;
    let stamp = now_stamp();
    let out = out_dir.join(format!("diag_{stamp}.zip"));

    let file = std::fs::File::create(&out).map_err(|e| e.to_string())?;
    let mut zip = zip::ZipWriter::new(file);
    let opts: zip::write::FileOptions<'_, ()> =
        zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated);

    // machine + app info
    let info = json!({
        "app_version": crate::update::APP_VERSION,
        "os": std::env::consts::OS,
        "arch": std::env::consts::ARCH,
        "product_root": root.to_string_lossy(),
        "runtime_ready": paths::runtime_ready(root),
        "gpus": crate::provision::list_gpus(),
        "installed_variant": crate::provision::read_package_meta_variant(root),
        "engine_core_missing": crate::engine_assets::engine_core_missing(root),
        "ui_source": crate::ui_assets::source_label(),
        "worker_alive": worker::is_worker_alive(root),
        "status": worker::status_for_ui(root),
        "config": Value::Object(config::read(root)),
        "perf_note": perf_note,
        "generated_at": stamp,
    });
    zip.start_file("info.json", opts).map_err(|e| e.to_string())?;
    zip.write_all(serde_json::to_string_pretty(&info).unwrap_or_default().as_bytes())
        .map_err(|e| e.to_string())?;

    // log tails（含性能测试日志）
    let logs = paths::logs_dir(root);
    for name in [
        "realtime_worker.log",
        "provision.log",
        "shell.log",
        "perf_bench.log",
    ] {
        let p = logs.join(name);
        if p.is_file() {
            let text = tail_bytes(&p, 512 * 1024);
            zip.start_file(format!("logs/{name}"), opts)
                .map_err(|e| e.to_string())?;
            zip.write_all(text.as_bytes()).map_err(|e| e.to_string())?;
        }
    }

    // newest perf report, if any
    let perf = paths::user_data(root).join("perf_reports");
    if let Ok(rd) = std::fs::read_dir(&perf) {
        let mut files: Vec<PathBuf> = rd
            .filter_map(|e| e.ok().map(|e| e.path()))
            .filter(|p| p.extension().and_then(|x| x.to_str()) == Some("json"))
            .collect();
        files.sort();
        if let Some(p) = files.last() {
            if let Ok(text) = std::fs::read_to_string(p) {
                let name = p.file_name().unwrap_or_default().to_string_lossy().to_string();
                zip.start_file(format!("perf/{name}"), opts)
                    .map_err(|e| e.to_string())?;
                zip.write_all(text.as_bytes()).map_err(|e| e.to_string())?;
            }
        }
    }

    zip.finish().map_err(|e| e.to_string())?;
    Ok((out, perf_note))
}

// ---------------------------------------------------------------------------
// Consult pack (申请专业优化)
// ---------------------------------------------------------------------------

/// Bundle the current voice's config + profiles + environment so tuning can be
/// done off-machine. The model weights are large and are **not** included
/// unless the user explicitly asks — that is a separate, deliberate step.
pub fn build_consult_pack(root: &Path, note: &str) -> Result<PathBuf, String> {
    let out_dir = paths::user_data(root).join("consult_packs");
    std::fs::create_dir_all(&out_dir).map_err(|e| e.to_string())?;
    let stamp = now_stamp();
    let out = out_dir.join(format!("consult_{stamp}.zip"));

    let cfg = config::read(root);
    let pth = cfg.get("pth_path").and_then(|v| v.as_str()).unwrap_or("");
    let model_dir = if pth.is_empty() {
        None
    } else {
        Path::new(pth).parent().map(|p| p.to_path_buf())
    };

    let file = std::fs::File::create(&out).map_err(|e| e.to_string())?;
    let mut zip = zip::ZipWriter::new(file);
    let opts: zip::write::FileOptions<'_, ()> =
        zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated);

    let meta = json!({
        "app_version": crate::update::APP_VERSION,
        "note": note,
        "gpus": crate::provision::list_gpus(),
        "installed_variant": crate::provision::read_package_meta_variant(root),
        "config": Value::Object(cfg.clone()),
        "generated_at": stamp,
    });
    zip.start_file("consult.json", opts).map_err(|e| e.to_string())?;
    zip.write_all(serde_json::to_string_pretty(&meta).unwrap_or_default().as_bytes())
        .map_err(|e| e.to_string())?;

    // The voice's own config.json and any .tmvp profiles — small text files.
    if let Some(dir) = model_dir {
        for entry in std::fs::read_dir(&dir).into_iter().flatten().flatten() {
            let p = entry.path();
            let ext = p.extension().and_then(|x| x.to_str()).unwrap_or("");
            if ext == "json" || ext == "tmvp" {
                if let Ok(text) = std::fs::read_to_string(&p) {
                    let name = p.file_name().unwrap_or_default().to_string_lossy().to_string();
                    zip.start_file(format!("voice/{name}"), opts)
                        .map_err(|e| e.to_string())?;
                    zip.write_all(text.as_bytes()).map_err(|e| e.to_string())?;
                }
            }
        }
    }

    zip.finish().map_err(|e| e.to_string())?;
    Ok(out)
}

/// `YYYYMMDD_HHMMSS` in local time — same shape as the Python shell's
/// `diag_20260727_151048`. Support staff read these filenames; a unix epoch
/// integer tells them nothing.
fn now_stamp() -> String {
    chrono::Local::now().format("%Y%m%d_%H%M%S").to_string()
}

/// Reveal a file in the OS file manager.
pub fn reveal(path: &Path) -> Result<(), String> {
    let dir = path.parent().unwrap_or(path);
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("explorer")
            .arg(dir)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(dir)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(all(not(target_os = "windows"), not(target_os = "macos")))]
    {
        let _ = dir;
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Window close behaviour
// ---------------------------------------------------------------------------

/// Apply the saved `close_action` when the user closes the window.
///
/// * `tray` — hide, keep converting. That is the point of having a tray.
/// * `exit` — stop the stream, then quit.
/// * `ask`  — hand it to the UI, which offers the same two choices plus
///            「记住我的选择」, like the Tk shell.
pub fn install_close_handler(app: &AppHandle) {
    let Some(win) = app.get_webview_window("main") else {
        return;
    };
    let handle = app.clone();
    let w = win.clone();
    // Tracks the previous unanswered close prompt (see the "ask" branch).
    let last_ask: std::sync::Arc<std::sync::Mutex<Option<std::time::Instant>>> =
        std::sync::Arc::new(std::sync::Mutex::new(None));
    win.on_window_event(move |event| {
        // 尺寸变了：Win10 重裁圆角区域；最大化时拆掉系统厚框/描边（Vista 边）。
        if matches!(
            event,
            tauri::WindowEvent::Resized(_) | tauri::WindowEvent::ScaleFactorChanged { .. }
        ) {
            crate::window_watch::refresh_corners(&w);
        }
        let tauri::WindowEvent::CloseRequested { api, .. } = event else {
            return;
        };
        let action = root_of(&handle)
            .map(|r| {
                config::read(&r)
                    .get("close_action")
                    .and_then(|v| v.as_str())
                    .unwrap_or("ask")
                    .to_string()
            })
            .unwrap_or_else(|| "ask".into());

        match action.as_str() {
            "exit" => {
                if let Some(root) = root_of(&handle) {
                    let _ = worker::stop_vc(&root, true);
                }
            }
            "tray" => {
                api.prevent_close();
                let _ = w.hide();
            }
            _ => {
                // If the UI is wedged it can never answer, and the user would
                // be unable to close the window at all. Second attempt within
                // 10s falls back to a plain exit.
                api.prevent_close();
                let now = std::time::Instant::now();
                let mut last = last_ask.lock().unwrap_or_else(|e| e.into_inner());
                let stuck = last
                    .map(|t: std::time::Instant| now.duration_since(t).as_secs() < 10)
                    .unwrap_or(false);
                *last = Some(now);
                drop(last);
                if stuck {
                    if let Some(root) = root_of(&handle) {
                        let _ = worker::stop_vc(&root, true);
                    }
                    handle.exit(0);
                    return;
                }
                let _ = handle.emit("app://close-requested", ());
            }
        }
    });
}

/// Called by the UI once the user answered the close prompt.
pub fn finish_close(app: &AppHandle, to_tray: bool) {
    if to_tray {
        if let Some(w) = app.get_webview_window("main") {
            let _ = w.hide();
        }
        return;
    }
    if let Some(root) = root_of(app) {
        let _ = worker::stop_vc(&root, true);
        // 退出前清 TEMP：先停 worker 再删，避免文件被占用删不掉。
        let stats = crate::paths::clean_temps(&root);
        crate::paths::log_clean_stats(&crate::i18n::t("s.c5fcd5c0a9"), &root, &stats);
    }
    app.exit(0);
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 旧 Python 壳那四个的默认组合和顺序不许动 —— 用户有肌肉记忆。
    ///
    /// 后面新加的不在这条约束里（所以这里比的是前四个，不是整张表），但
    /// 新加的也不许挤到前面去，否则等于把老用户的键改了。
    #[test]
    fn the_original_four_hotkeys_keep_their_combos() {
        let combos: Vec<&str> = HOTKEYS.iter().take(4).map(|(_, _, d)| *d).collect();
        assert_eq!(
            combos,
            vec!["CmdOrCtrl+F2", "CmdOrCtrl+F3", "CmdOrCtrl+F5", "CmdOrCtrl+F6"]
        );
        let actions: Vec<&str> = HOTKEYS.iter().take(4).map(|(_, a, _)| *a).collect();
        assert_eq!(
            actions,
            vec!["toggle-vc", "toggle-mode", "prev-voice", "next-voice"]
        );
    }

    /// 配置里存的组合键要先筛一道再交给系统注册。
    #[test]
    fn combo_shapes_are_checked() {
        assert!(combo_ok("CmdOrCtrl+F2"));
        assert!(combo_ok("Alt+Shift+K"));
        assert!(combo_ok("F9"));
        assert!(!combo_ok(""), &crate::i18n::t("s.4d568e3db9"));
        assert!(!combo_ok("Ctrl+"), &crate::i18n::t("s.6b25a5378d"));
        assert!(!combo_ok("Ctrl++A"), &crate::i18n::t("s.5ff8d648a8"));
        assert!(!combo_ok("Ctrl+A+B+C+D+E"), &crate::i18n::t("s.b78ead0b6a"));
        assert!(!combo_ok("Ctrl+<script>"), &crate::i18n::t("s.36c2e47b48"));
        assert!(!combo_ok(&"A".repeat(60)), &crate::i18n::t("s.e110cd6caf"));
    }

    /// 配置里是垃圾值时必须退回默认，而不是注册一个乱七八糟的组合。
    #[test]
    fn bad_config_falls_back_to_default() {
        assert_eq!(combo_for(None, "hotkey_toggle_vc", "CmdOrCtrl+F2"), "CmdOrCtrl+F2");
    }

    #[test]
    fn log_tail_is_capped() {
        let p = std::env::temp_dir().join("rvcf-tail-test.log");
        std::fs::write(&p, "x".repeat(50_000)).unwrap();
        assert_eq!(tail_bytes(&p, 1000).len(), 1000);
        let _ = std::fs::remove_file(&p);
    }

    /// 快捷键的默认组合有三份拷贝：这里的 HOTKEYS、config::defaults()、
    /// 以及设置页 SettingsPage.tsx 的 HOTKEYS 数组。前两份能在这里对上，
    /// 第三份只能靠注释。
    ///
    /// 对不上的后果很隐蔽：设置页显示 F7，实际注册的是别的键，用户按着没反应
    /// 又看不出哪里错了。
    #[test]
    fn hotkey_defaults_match_the_config_defaults() {
        let d = crate::config::defaults();
        for (key, _action, default) in HOTKEYS {
            let got = d
                .get(*key)
                .and_then(|v| v.as_str())
                .unwrap_or_else(|| panic!(&crate::i18n::t("s.e64959c277")));
            assert_eq!(got, *default, &crate::i18n::t("s.a76352090e"));
        }
    }

    /// 每个快捷键都要有自己的 `_global` 开关，而且默认必须是 true。
    ///
    /// 默认值写错成 false 是个静默事故：九个快捷键一夜之间全变成「只在软件内
    /// 生效」，用户在游戏里按 Ctrl+F2 没反应，而界面上什么错都不会报。
    #[test]
    fn every_hotkey_has_a_global_switch_defaulting_to_on() {
        let d = crate::config::defaults();
        for (key, _action, _default) in HOTKEYS {
            let k = format!("{key}_global");
            let got = d
                .get(&k)
                .and_then(|v| v.as_bool())
                .unwrap_or_else(|| panic!(&crate::i18n::t("s.735eb4e9fd")));
            assert!(got, &crate::i18n::t("s.d4efcb94da"));
        }
    }

    /// 组合键必须过得了自己的校验。写错一个字符（比如 "Ctrl+F7" 而不是
    /// "CmdOrCtrl+F7"）会被 combo_for 当成非法值悄悄换成 fallback ——
    /// 而 fallback 就是它自己，于是永远注册不上，也没人报错。
    #[test]
    fn every_default_combo_is_well_formed() {
        for (key, _action, default) in HOTKEYS {
            assert!(combo_ok(default), &crate::i18n::t("s.d50071676d"));
        }
    }

    /// 动作名不能撞：撞了就是两个快捷键触发同一件事，另一件永远做不了。
    #[test]
    fn hotkey_keys_and_actions_are_unique() {
        let mut keys: Vec<&str> = HOTKEYS.iter().map(|h| h.0).collect();
        let n = keys.len();
        keys.sort_unstable();
        keys.dedup();
        assert_eq!(keys.len(), n, &crate::i18n::t("s.da544f6e8b"));

        let mut acts: Vec<&str> = HOTKEYS.iter().map(|h| h.1).collect();
        acts.sort_unstable();
        acts.dedup();
        assert_eq!(acts.len(), n, &crate::i18n::t("s.4dae253817"));
    }
}
