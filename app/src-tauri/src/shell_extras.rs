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

use serde_json::{json, Value};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager};

use crate::{config, paths, worker};

// ---------------------------------------------------------------------------
// Tray
// ---------------------------------------------------------------------------

/// Build the tray icon. Closing to tray is what keeps conversion running while
/// the window is out of the way, so the tray must always exist — not only when
/// the user picked "minimise to tray".
pub fn install_tray(app: &AppHandle) -> Result<(), String> {
    let show = MenuItem::with_id(app, "show", "打开主界面", true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let toggle = MenuItem::with_id(app, "toggle", "开启 / 停止变声", true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let menu =
        Menu::with_items(app, &[&show, &toggle, &quit]).map_err(|e| e.to_string())?;

    TrayIconBuilder::with_id("main")
        .tooltip("RVC Fabric")
        .icon(app.default_window_icon().cloned().ok_or("缺少托盘图标")?)
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
            if let TrayIconEvent::Click { .. } = event {
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
        let _ = w.set_focus();
    }
}

fn root_of(app: &AppHandle) -> Option<PathBuf> {
    app.try_state::<std::sync::Mutex<crate::AppState>>()
        .and_then(|s| s.lock().ok().map(|g| g.root.clone()))
}

// ---------------------------------------------------------------------------
// Global hotkeys
// ---------------------------------------------------------------------------

/// Same combos as the Python shell.
pub const HOTKEYS: &[(&str, &str)] = &[
    ("CmdOrCtrl+F2", "toggle-vc"),
    ("CmdOrCtrl+F3", "toggle-mode"),
    ("CmdOrCtrl+F5", "prev-voice"),
    ("CmdOrCtrl+F6", "next-voice"),
];

/// Register or unregister the global hotkeys. Failing to grab a combo (another
/// app already owns it) must not break the rest — report and carry on.
pub fn apply_hotkeys(app: &AppHandle, enabled: bool) -> Value {
    use tauri_plugin_global_shortcut::GlobalShortcutExt;
    let gs = app.global_shortcut();
    let _ = gs.unregister_all();
    if !enabled {
        return json!({"enabled": false, "registered": [], "failed": []});
    }
    let mut ok: Vec<&str> = Vec::new();
    let mut failed: Vec<&str> = Vec::new();
    for (combo, action) in HOTKEYS {
        let handle = app.clone();
        let act = action.to_string();
        match gs.on_shortcut(*combo, move |_a, _s, _e| {
            let _ = handle.emit(&format!("hotkey://{act}"), ());
        }) {
            Ok(()) => ok.push(combo),
            Err(_) => failed.push(combo),
        }
    }
    json!({"enabled": true, "registered": ok, "failed": failed})
}

// ---------------------------------------------------------------------------
// Diagnostics bundle
// ---------------------------------------------------------------------------

/// Run `tools/benchmark_realtime.py` in the Runtime, writing into
/// `User_Data/perf_reports/`. Takes roughly a minute; callers must say so.
pub fn run_perf_bench(root: &Path) -> Result<(), String> {
    let py = paths::runtime_pythonw(root)
        .or_else(|| paths::runtime_python(root))
        .ok_or("Runtime 未就绪，跳过性能测试")?;
    let script = root.join("tools").join("benchmark_realtime.py");
    if !script.is_file() {
        return Err("找不到 benchmark_realtime.py".into());
    }
    let out_dir = paths::user_data(root).join("perf_reports");
    std::fs::create_dir_all(&out_dir).map_err(|e| e.to_string())?;

    let mut cmd = std::process::Command::new(py);
    cmd.arg(&script).arg("--out").arg(&out_dir).current_dir(root);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // CREATE_NO_WINDOW — never flash a console at the user.
        cmd.creation_flags(0x0800_0000);
    }
    let status = cmd.status().map_err(|e| format!("性能测试启动失败：{e}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("性能测试退出码 {:?}", status.code()))
    }
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
/// Log tails are capped: `realtime_worker.log` grows large and a multi-hundred-MB
/// bundle is useless to everyone.
pub fn build_diagnostics(root: &Path) -> Result<PathBuf, String> {
    // The Tk shell ran a short benchmark first so the bundle carries a fresh
    // sample from *this* machine, not whatever happened to be lying around.
    // Best-effort: a machine without a Runtime still gets a usable bundle.
    if let Err(e) = run_perf_bench(root) {
        eprintln!("[rvc-fabric] perf bench skipped: {e}");
    }
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
        "generated_at": stamp,
    });
    zip.start_file("info.json", opts).map_err(|e| e.to_string())?;
    zip.write_all(serde_json::to_string_pretty(&info).unwrap_or_default().as_bytes())
        .map_err(|e| e.to_string())?;

    // log tails
    let logs = paths::logs_dir(root);
    for name in ["realtime_worker.log", "provision.log", "shell.log"] {
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
    Ok(out)
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
    win.on_window_event(move |event| {
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
                api.prevent_close();
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
    }
    app.exit(0);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hotkey_combos_match_the_old_shell() {
        let combos: Vec<&str> = HOTKEYS.iter().map(|(c, _)| *c).collect();
        assert_eq!(
            combos,
            vec!["CmdOrCtrl+F2", "CmdOrCtrl+F3", "CmdOrCtrl+F5", "CmdOrCtrl+F6"]
        );
    }

    #[test]
    fn log_tail_is_capped() {
        let p = std::env::temp_dir().join("rvcf-tail-test.log");
        std::fs::write(&p, "x".repeat(50_000)).unwrap();
        assert_eq!(tail_bytes(&p, 1000).len(), 1000);
        let _ = std::fs::remove_file(&p);
    }
}
