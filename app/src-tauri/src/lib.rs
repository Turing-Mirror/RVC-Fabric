//! RVC Fabric shell (Tauri).
//!
//! Stages 1–4: window/UI, worker bridge, Runtime provision, voice catalog & store.

pub mod catalog;
mod config;
mod download;
mod engine_assets;
mod extract;
mod legacy;
mod logging;
pub mod paths;
pub mod plaza;
mod protocol;
mod provision;
mod shell_extras;
mod store;
mod telemetry;
mod ui_assets;
pub mod update;
mod voices;
mod worker;

use std::path::PathBuf;
use std::sync::Mutex;

use serde_json::{json, Map, Value};
use tauri::{AppHandle, Emitter, State};

struct AppState {
    root: PathBuf,
}

fn root_clone(state: &State<'_, Mutex<AppState>>) -> Result<PathBuf, String> {
    let g = state.lock().map_err(|e| e.to_string())?;
    Ok(g.root.clone())
}

/// engine-core / VB-Cable readiness for the first-run gate.
#[tauri::command]
fn assets_status(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    Ok(engine_assets::assets_status(&root_clone(&state)?))
}

#[tauri::command]
async fn assets_ensure_engine_core(
    state: State<'_, Mutex<AppState>>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let cancel = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    tauri::async_runtime::spawn_blocking(move || {
        engine_assets::ensure_engine_core(&root, cancel).map(|_| json!({"ok": true}))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn assets_ensure_vbcable(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let cancel = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    tauri::async_runtime::spawn_blocking(move || {
        engine_assets::ensure_vbcable_pack(&root, cancel).map(|_| json!({"ok": true}))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn assets_install_vbcable(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    engine_assets::install_vbcable(&root_clone(&state)?)?;
    Ok(json!({"ok": true}))
}

/// Full effective settings (defaults overlaid with saved values).
#[tauri::command]
fn config_get(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    Ok(Value::Object(config::read(&root_clone(&state)?)))
}

/// Which keys belong to which settings group, and which are hot vs cold.
#[tauri::command]
fn config_describe() -> Value {
    config::describe()
}

/// Merge a patch, persist, mirror into inuse, and push hot keys to a running
/// stream. Returns `needs_restart` for the cold keys the UI must warn about.
#[tauri::command]
fn config_set(
    state: State<'_, Mutex<AppState>>,
    patch: Map<String, Value>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let out = config::update(&root, patch)?;
    if let Some(hot) = out.get("hot").and_then(|v| v.as_object()) {
        if !hot.is_empty() && worker::is_worker_alive(&root) {
            let _ = worker::set_hot(&root, hot.clone());
        }
    }
    Ok(out)
}

/// Native image picker for the wallpaper setting. Returns the chosen path or
/// null when the user cancels; size/dimension limits are enforced on apply.
#[tauri::command]
fn pick_wallpaper() -> Option<String> {
    rfd::FileDialog::new()
        .add_filter("图片", &["jpg", "jpeg", "png", "webp", "bmp"])
        .set_title("选择背景图")
        .pick_file()
        .map(|p| p.to_string_lossy().into_owned())
}

/// Ask the catalog whether a newer build exists.
#[tauri::command]
async fn update_check() -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(|| update::check(12))
        .await
        .map_err(|e| e.to_string())?
}

/// Download a gui_patch and swap the external frontend/ directory.
#[tauri::command]
async fn update_apply(
    state: State<'_, Mutex<AppState>>,
    url: String,
    sha256: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let cancel = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    tauri::async_runtime::spawn_blocking(move || {
        update::apply_gui_patch(&root, &url, &sha256, cancel)
            .map(|p| json!({"ok": true, "path": p.to_string_lossy(), "restart_required": true}))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Register / unregister the global hotkeys.
#[tauri::command]
fn hotkeys_apply(app: AppHandle, enabled: bool) -> Value {
    shell_extras::apply_hotkeys(&app, enabled)
}

/// Zip logs + machine info + settings for support.
#[tauri::command]
async fn diagnostics_build(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        shell_extras::build_diagnostics(&root).map(|p| {
            let _ = shell_extras::reveal(&p);
            json!({"ok": true, "path": p.to_string_lossy()})
        })
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Bundle the current voice's config + profiles for paid tuning.
#[tauri::command]
async fn consult_build(
    state: State<'_, Mutex<AppState>>,
    note: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        shell_extras::build_consult_pack(&root, &note).map(|p| {
            let _ = shell_extras::reveal(&p);
            json!({"ok": true, "path": p.to_string_lossy()})
        })
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Open a folder under User_Data in the file manager.
#[tauri::command]
fn reveal_user_dir(state: State<'_, Mutex<AppState>>, name: String) -> Result<(), String> {
    let root = root_clone(&state)?;
    let dir = paths::user_data(&root).join(name);
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    shell_extras::reveal(&dir.join("x"))
}

/// Opt-in daily ping. No-op when the user has not agreed.
#[tauri::command]
async fn telemetry_tick(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let accel = provision::read_package_meta_variant(&root).unwrap_or_else(|| "unknown".into());
    tauri::async_runtime::spawn_blocking(move || {
        Ok(telemetry::tick(&root, update::APP_VERSION, &accel))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// The UI answered the close prompt.
#[tauri::command]
fn close_finish(app: AppHandle, to_tray: bool) {
    shell_extras::finish_close(&app, to_tray);
}

/// Strategy B: replace the exe through the signed updater feed.
#[tauri::command]
async fn update_app(app: AppHandle) -> Result<Value, String> {
    update::run_app_updater(&app).await
}

#[tauri::command]
fn ui_source() -> String {
    ui_assets::source_label()
}

/// Shipping version. The 「其他」page had this typed in as a literal, so it
/// would quietly disagree with the binary after any bump.
#[tauri::command]
fn shell_version() -> &'static str {
    update::APP_VERSION
}

/// Reported by the UI on first paint. Turns "the window is blank" from an
/// unfalsifiable user report into a line in `shell.log`.
#[tauri::command]
fn ui_ready() {
    ui_assets::mark_ui_ready();
}

/// Anything the UI's own error screen wants to show, written to `shell.log`.
/// Frontend exceptions otherwise die inside the webview console, which nobody
/// on a user's machine can open.
#[tauri::command]
fn ui_log(line: String) {
    // Bound it: an error loop must not be able to fill the disk one message at
    // a time.
    let line: String = line.chars().take(2000).collect();
    // Rate-limit too. This command is synchronous, which means it runs inline
    // on the thread that receives IPC — the window's own UI thread on Windows —
    // and it touches the disk. A frontend stuck in an error loop calling it
    // would freeze the window rather than report the problem.
    static GATE: Mutex<Option<(std::time::Instant, u32)>> = Mutex::new(None);
    const PER_WINDOW: u32 = 30;
    let window = std::time::Duration::from_secs(10);
    let mut g = GATE.lock().unwrap_or_else(|e| e.into_inner());
    let (since, count) = match *g {
        Some((t, n)) if t.elapsed() < window => (t, n),
        _ => (std::time::Instant::now(), 0),
    };
    *g = Some((since, count + 1));
    drop(g);
    match count {
        n if n < PER_WINDOW => logging::shell_log!("[ui] {line}"),
        n if n == PER_WINDOW => {
            logging::shell_log!("[ui] 前端日志过快（10 秒内超过 {PER_WINDOW} 条），本轮后续省略")
        }
        _ => {}
    }
}

/// Plaza feed + changelog, already filtered for this version and today's date.
///
/// `plaza.rs` had no caller at all: the page shipped hardcoded placeholder
/// cards and a stale 1.2.4 changelog while the parser, the cnb.cool image
/// restriction and the placement rules all sat unused.
#[tauri::command]
async fn plaza_fetch(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        let (items, changelog, errors) = plaza::fetch(12);
        let today = plaza::today_yymmdd();
        let dismissed = config::dismissed_ads(&root);
        // Plaza placements are never dismissible — that rule lives in the
        // parser, so an empty `dismissed` list here would be equivalent. Pass
        // it anyway so the two placements go through one code path.
        let feed = plaza::visible_items(
            &items,
            plaza::PLACEMENT_PLAZA,
            update::APP_VERSION,
            &today,
            &dismissed,
        );
        let banner = plaza::pick_models_banner(&items, update::APP_VERSION, &today, &dismissed);
        // Newest dated row decides the tab dot. Undated rows carry no "new"
        // signal — otherwise an evergreen sponsor slot would keep the dot lit
        // forever, which is exactly the old hardcoded behaviour.
        let newest = feed
            .iter()
            .map(|it| it.date.as_str())
            .filter(|d| !d.is_empty())
            .max()
            .unwrap_or("")
            .to_string();
        let unread = !newest.is_empty() && newest > config::plaza_seen(&root);
        Ok(json!({
            "items": feed,
            "banner": banner,
            "changelog": changelog,
            "errors": errors,
            "app_version": update::APP_VERSION,
            "newest": newest,
            "unread": unread,
        }))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// The user opened the plaza — clear the tab dot up to `newest`.
#[tauri::command]
fn plaza_mark_seen(state: State<'_, Mutex<AppState>>, newest: String) -> Result<(), String> {
    config::set_plaza_seen(&root_clone(&state)?, &newest)
}

/// Remember a dismissed models-page banner so it stays gone across restarts.
#[tauri::command]
fn plaza_dismiss(state: State<'_, Mutex<AppState>>, id: String) -> Result<(), String> {
    config::dismiss_ad(&root_clone(&state)?, &id)
}

/// Open a link in the user's own browser. Restricted to http/https so a feed
/// can never hand us a `file://` or a shell scheme to launch.
#[tauri::command]
fn open_external(app: AppHandle, url: String) -> Result<(), String> {
    let ok = url.starts_with("https://") || url.starts_with("http://");
    if !ok {
        return Err("只允许打开 http/https 链接".into());
    }
    use tauri_plugin_opener::OpenerExt;
    app.opener()
        .open_url(url, None::<&str>)
        .map_err(|e| e.to_string())
}

/// 「其他」page → 打开原版实时面板（gui_v1）。
#[tauri::command]
async fn legacy_open_panel(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || legacy::open_realtime_panel(&root))
        .await
        .map_err(|e| e.to_string())?
}

/// 「其他」page → 打开原版 WebUI（infer-web.py）。
#[tauri::command]
async fn legacy_open_webui(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || legacy::open_webui(&root))
        .await
        .map_err(|e| e.to_string())?
}

/// Path of the shell log, for the 「其他」page's "打开日志" action.
#[tauri::command]
fn log_path() -> Option<String> {
    logging::path().map(|p| p.to_string_lossy().into_owned())
}

#[tauri::command]
fn product_root(state: State<'_, Mutex<AppState>>) -> Result<String, String> {
    Ok(root_clone(&state)?.to_string_lossy().into_owned())
}

#[tauri::command]
fn engine_status(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    Ok(worker::status_for_ui(&root))
}

#[tauri::command]
async fn engine_ensure(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    if !paths::runtime_ready(&root) {
        let mut st = worker::status_for_ui(&root);
        if let Some(obj) = st.as_object_mut() {
            obj.insert("state".into(), json!("idle"));
            obj.insert("error".into(), json!("Runtime 未就绪，请先补全运行时"));
            obj.insert("worker_alive".into(), json!(false));
        }
        return Ok(st);
    }
    // Called on app start and waits up to 90s for the worker. Inline, that is
    // a 90-second freeze on the first launch after an install.
    tauri::async_runtime::spawn_blocking(move || {
        Ok(worker::ensure_worker_and_devices(&root, 90_000))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn engine_start_worker(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    if !paths::runtime_ready(&root) {
        return Ok(json!({"state": "error", "error": "Runtime 未就绪（缺少 torch）", "pid": 0}));
    }
    // Waits up to 90s for the worker to come up. A sync command runs inline on
    // the IPC thread, so that wait froze the whole window.
    tauri::async_runtime::spawn_blocking(move || {
        worker::start_worker(&root)?;
        Ok(worker::wait_worker_ready(&root, 90_000))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn engine_start_vc(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    if !paths::runtime_ready(&root) {
        return Ok(json!({"state": "error", "error": "Runtime 未就绪，无法开启变声", "pid": 0}));
    }
    // The cold start is 20–40s (torch/CUDA) and the wait allows up to 180s.
    // Run it off the IPC thread or the window is frozen for that whole time —
    // no status updates, no way to press 停止.
    tauri::async_runtime::spawn_blocking(move || {
        worker::start_vc(&root)?;
        Ok(worker::wait_vc_running(&root, 180_000))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn engine_stop_vc(
    state: State<'_, Mutex<AppState>>,
    force: Option<bool>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let f = force.unwrap_or(true);
    tauri::async_runtime::spawn_blocking(move || {
        worker::stop_vc(&root, f)?;
        Ok(worker::status_for_ui(&root))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn engine_force_kill(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        worker::kill_known_workers(&root);
        Ok(worker::status_for_ui(&root))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn engine_set_hot(
    state: State<'_, Mutex<AppState>>,
    pitch: Option<i32>,
    formant: Option<f64>,
    function: Option<String>,
    threhold: Option<f64>,
    index_rate: Option<f64>,
    rms_mix_rate: Option<f64>,
) -> Result<u64, String> {
    let root = root_clone(&state)?;
    let mut payload = Map::new();
    if let Some(v) = pitch {
        payload.insert("pitch".into(), json!(v));
    }
    if let Some(v) = formant {
        payload.insert("formant".into(), json!(v));
    }
    if let Some(v) = function {
        let f = if v == "bypass" || v == "im" {
            "im"
        } else {
            "vc"
        };
        payload.insert("function".into(), json!(f));
    }
    if let Some(v) = threhold {
        payload.insert("threhold".into(), json!(v));
    }
    if let Some(v) = index_rate {
        payload.insert("index_rate".into(), json!(v));
    }
    if let Some(v) = rms_mix_rate {
        payload.insert("rms_mix_rate".into(), json!(v));
    }
    if payload.is_empty() {
        return Err("no hot keys".into());
    }
    worker::set_hot(&root, payload)
}

#[tauri::command]
async fn engine_list_devices(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // Starts the worker if needed (up to 90s) and then polls for up to 20s.
    tauri::async_runtime::spawn_blocking(move || list_devices_blocking(root))
        .await
        .map_err(|e| e.to_string())?
}

fn list_devices_blocking(root: std::path::PathBuf) -> Result<Value, String> {
    let root = &root;
    if !paths::runtime_ready(&root) {
        return Ok(json!({
            "state": "error",
            "error": "Runtime 未就绪",
            "input_devices": [],
            "output_devices": [],
            "hostapis": []
        }));
    }
    if !worker::is_worker_alive(&root) {
        worker::start_worker(&root)?;
        let st = worker::wait_worker_ready(&root, 90_000);
        if st.get("state").and_then(|v| v.as_str()) == Some("error") {
            return Ok(st);
        }
    }
    let _ = worker::send_command(&root, "list_devices", Map::new());
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(20);
    while std::time::Instant::now() < deadline {
        let st = worker::status_for_ui(&root);
        let has = st
            .get("input_devices")
            .and_then(|v| v.as_array())
            .map(|a| !a.is_empty())
            .unwrap_or(false);
        if has {
            return Ok(st);
        }
        std::thread::sleep(std::time::Duration::from_millis(200));
    }
    Ok(worker::status_for_ui(&root))
}

#[tauri::command]
async fn provision_status(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // Async + spawn_blocking because this resolves a runtime spec, which can
    // reach CNB. A sync command runs on the IPC thread, so an unreachable or
    // slow host froze the window on startup for as long as the request took.
    tauri::async_runtime::spawn_blocking(move || {
        let t = std::time::Instant::now();
        let v = provision::provision_status(&root);
        // This is the first thing a fresh install calls and the gate cannot
        // draw without it, so a slow answer looks exactly like a hang. Say so.
        let ms = t.elapsed().as_millis();
        if ms > 1500 {
            logging::shell_log!("provision_status 用了 {ms} ms");
        }
        Ok(v)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn provision_start(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    variant: String,
    force: Option<bool>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let f = force.unwrap_or(false);
    // This downloads and extracts several GB. Run inline it occupied the IPC
    // path for the whole transfer, which meant the 取消 button's own invoke
    // could not be delivered — the user could watch the progress bar but not
    // stop it.
    tauri::async_runtime::spawn_blocking(move || {
        provision::run_provision(app, root, variant, f)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn provision_cancel() -> Result<(), String> {
    provision::cancel_provision();
    Ok(())
}

// ----- Stage 4: voices + store ------------------------------------------------

#[tauri::command]
async fn voices_list(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // Walks the whole voice library; a large one is a visible stall on the IPC
    // thread.
    tauri::async_runtime::spawn_blocking(move || Ok(voices::list_voices(&root)))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn voices_select(
    state: State<'_, Mutex<AppState>>,
    path: Option<String>,
    dir: Option<String>,
    name: Option<String>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::select_voice(
        &root,
        path.as_deref().unwrap_or(""),
        dir.as_deref().unwrap_or(""),
        name.as_deref().unwrap_or(""),
    )
}

#[tauri::command]
async fn voices_current(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        Ok(voices::current_selection_summary(&root))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn voices_index_list(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::list_index_bindings(&root, &model_dir)
}

#[tauri::command]
fn voices_index_use(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
    index_path: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::set_active_index(&root, &model_dir, &index_path)
}

#[tauri::command]
fn voices_index_bind(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
    index_src: Option<String>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let src = match index_src.filter(|s| !s.is_empty()) {
        Some(s) => s,
        None => voices::pick_index_file().ok_or_else(|| "已取消".to_string())?,
    };
    voices::bind_index_file(&root, &model_dir, &src)
}

#[tauri::command]
fn voices_index_unbind(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
    index_path: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::unbind_index(&root, &model_dir, &index_path)
}

#[tauri::command]
fn voices_profiles_list(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::list_profiles(&root, &model_dir)
}

#[tauri::command]
fn voices_profile_use(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
    profile_id: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::set_active_profile(&root, &model_dir, &profile_id)
}

#[tauri::command]
fn voices_profile_save(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
    name: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::save_current_as_profile(&root, &model_dir, &name)
}

#[tauri::command]
fn voices_profile_delete(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
    profile_id: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::delete_profile(&root, &model_dir, &profile_id)
}

#[tauri::command]
fn voices_profile_import(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::import_profile(&root, &model_dir)
}

#[tauri::command]
fn voices_profile_export(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::export_active_profile(&root, &model_dir)
}

#[tauri::command]
async fn voices_import(
    state: State<'_, Mutex<AppState>>,
    paths: Option<Vec<String>>,
    current_model_dir: Option<String>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // The picker stays here (native dialogs want the main thread); only the
    // copying, which can be gigabytes, moves off.
    let files = match paths.filter(|p| !p.is_empty()) {
        Some(p) => p,
        None => {
            let picked = voices::pick_import_files();
            if picked.is_empty() {
                return Err("已取消".into());
            }
            picked
        }
    };
    tauri::async_runtime::spawn_blocking(move || {
        voices::import_files(&root, &files, current_model_dir.as_deref())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn voices_delete(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || voices::delete_voice(&root, &model_dir))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn voices_rename(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
    new_name: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::rename_voice(&root, &model_dir, &new_name)
}

#[tauri::command]
async fn voices_promote(
    state: State<'_, Mutex<AppState>>,
    pth_path: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // Copies a multi-hundred-MB .pth.
    tauri::async_runtime::spawn_blocking(move || voices::promote_legacy(&root, &pth_path))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn voices_open_dir(state: State<'_, Mutex<AppState>>) -> Result<(), String> {
    let root = root_clone(&state)?;
    voices::open_models_dir(&root)
}

#[tauri::command]
async fn store_catalog(
    state: State<'_, Mutex<AppState>>,
    prefer_remote: Option<bool>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let remote = prefer_remote.unwrap_or(true);
    // Network fetch — never on the IPC thread.
    tauri::async_runtime::spawn_blocking(move || {
        Ok(store::fetch_store_catalog(&root, remote))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn store_install(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    entry: Value,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // Downloads and unpacks a voice pack. Same reason as provision_start: the
    // per-voice 取消 is its own invoke and has to be able to get through.
    tauri::async_runtime::spawn_blocking(move || store::install_voice_entry(app, root, entry))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn store_cancel(voice_id: Option<String>) -> Result<(), String> {
    // Empty / omitted id cancels everything in flight.
    store::cancel_store_download(voice_id.as_deref().unwrap_or(""));
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let root = paths::product_root();
    // Before anything else: a release build has no console, so without this the
    // rest of these lines would go nowhere.
    logging::init(&root);
    logging::shell_log!("=== RVC Fabric {} 启动 ===", update::APP_VERSION);
    logging::shell_log!("product root: {}", root.display());
    logging::shell_log!("runtime_ready={}", paths::runtime_ready(&root));
    logging::shell_log!(
        "exe: {}",
        std::env::current_exe()
            .map(|p| p.display().to_string())
            .unwrap_or_else(|e| format!("<unknown: {e}>"))
    );
    logging::shell_log!("UI source: {}", ui_assets::source_label());

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_updater::Builder::new().build())
        // OTA strategy A: serve the UI through fabric:// so the frontend/ dir
        // next to the exe can replace the shipped UI without a new exe.
        .register_uri_scheme_protocol(ui_assets::SCHEME, |ctx, req| {
            ui_assets::serve(ctx.app_handle(), req)
        })
        .manage(Mutex::new(AppState { root: root.clone() }))
        .invoke_handler(tauri::generate_handler![
            ui_source,
            shell_version,
            ui_ready,
            ui_log,
            log_path,
            legacy_open_panel,
            legacy_open_webui,
            plaza_fetch,
            plaza_dismiss,
            plaza_mark_seen,
            open_external,
            config_get,
            config_describe,
            config_set,
            pick_wallpaper,
            update_check,
            update_apply,
            update_app,
            hotkeys_apply,
            diagnostics_build,
            consult_build,
            reveal_user_dir,
            telemetry_tick,
            close_finish,
            assets_status,
            assets_ensure_engine_core,
            assets_ensure_vbcable,
            assets_install_vbcable,
            product_root,
            engine_status,
            engine_ensure,
            engine_start_worker,
            engine_start_vc,
            engine_stop_vc,
            engine_force_kill,
            engine_set_hot,
            engine_list_devices,
            provision_status,
            provision_start,
            provision_cancel,
            voices_list,
            voices_select,
            voices_current,
            voices_index_list,
            voices_index_use,
            voices_index_bind,
            voices_index_unbind,
            voices_profiles_list,
            voices_profile_use,
            voices_profile_save,
            voices_profile_delete,
            voices_profile_import,
            voices_profile_export,
            voices_import,
            voices_delete,
            voices_rename,
            voices_promote,
            voices_open_dir,
            store_catalog,
            store_install,
            store_cancel,
        ])
        .setup(move |app| {
            // Window URL must use the custom scheme registered above.
            // WebView2 cannot register non-standard schemes at all, so wry
            // rewrites `fabric://localhost/x` to `http://fabric.localhost/x`
            // and intercepts that; Windows is spelled out here to match what
            // the webview will actually report as its origin.
            #[cfg(windows)]
            let url = format!("http://{}.localhost/index.html", ui_assets::SCHEME);
            #[cfg(not(windows))]
            let url = format!("{}://localhost/index.html", ui_assets::SCHEME);
            logging::shell_log!("window url: {url}");
            tauri::WebviewWindowBuilder::new(
                app,
                "main",
                tauri::WebviewUrl::CustomProtocol(url.parse().expect("fabric url")),
            )
            .title("RVC Fabric")
            .inner_size(1180.0, 780.0)
            .min_inner_size(880.0, 640.0)
            .resizable(true)
            .decorations(false)
            .center()
            .build()?;

            // A blank window is the one failure the user cannot describe and we
            // cannot see. If the UI never reports back, say so in the log with
            // everything needed to tell "assets missing" from "script threw".
            {
                let h = app.handle().clone();
                std::thread::spawn(move || {
                    std::thread::sleep(std::time::Duration::from_secs(12));
                    if !ui_assets::ui_reported_ready() {
                        logging::shell_log!(
                            "警告：12 秒内界面没有挂载（白屏）。UI 来源 {} · 已处理 {} 个资源请求 · 404 {} 次",
                            ui_assets::source_label(),
                            ui_assets::served_count(),
                            ui_assets::not_found_count(),
                        );
                        let _ = h.emit("app://ui-stalled", ());
                    }
                });
            }

            // "打开就未响应" is the one report that carries no information: the
            // window is frozen, so the UI cannot say anything and neither can
            // any command it would have called. Ping the event loop from a
            // plain thread instead. If these lines are absent from a log that
            // ends mid-session, the loop stopped pumping and the cause is on
            // the Rust side; if they keep appearing, the shell is alive and the
            // webview is what wedged. Either way the next report starts from a
            // fact instead of a guess.
            {
                let h = app.handle().clone();
                std::thread::spawn(move || {
                    let mut stalled = false;
                    loop {
                        std::thread::sleep(std::time::Duration::from_secs(15));
                        let (tx, rx) = std::sync::mpsc::channel();
                        if h.run_on_main_thread(move || {
                            let _ = tx.send(());
                        })
                        .is_err()
                        {
                            return; // app is shutting down
                        }
                        let ok = rx
                            .recv_timeout(std::time::Duration::from_secs(10))
                            .is_ok();
                        if !ok && !stalled {
                            logging::shell_log!("警告：主线程 10 秒没有响应，窗口此刻是卡住的");
                            stalled = true;
                        } else if ok && stalled {
                            logging::shell_log!("主线程已恢复");
                            stalled = false;
                        }
                    }
                });
            }

            // Regenerate configs/inuse/config.json from app_config on every
            // start. Setup ships a clean template that overwrites the installed
            // one, so without this an upgrade looks like "my devices were
            // reset" — the real settings are in User_Data and just never got
            // written back down to the engine.
            {
                let cfg = config::read(&root);
                if let Err(e) = config::sync_inuse(&root, &cfg) {
                    logging::shell_log!("inuse sync failed: {e}");
                }
            }

            shell_extras::install_close_handler(app.handle());
            // Tray always exists: closing to tray is what keeps conversion
            // running while the window is away.
            if let Err(e) = shell_extras::install_tray(app.handle()) {
                logging::shell_log!("tray unavailable: {e}");
            }
            // Restore the saved hotkey preference.
            let want_hotkeys = config::read(&root)
                .get("hotkeys_enabled")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let _ = shell_extras::apply_hotkeys(app.handle(), want_hotkeys);

            let root_bg = root.clone();
            std::thread::spawn(move || {
                if paths::runtime_ready(&root_bg) {
                    let _ = worker::ensure_worker_and_devices(&root_bg, 90_000);
                } else {
                    logging::shell_log!("skip worker prewarm: Runtime not ready");
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running RVC Fabric");
}
