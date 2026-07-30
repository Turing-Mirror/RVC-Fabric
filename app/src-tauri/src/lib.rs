//! RVC Fabric shell (Tauri).
//!
//! Stages 1–4: window/UI, worker bridge, Runtime provision, voice catalog & store.

pub mod catalog;
mod config;
mod download;
mod engine_assets;
mod extract;
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
use tauri::{AppHandle, State};

struct AppState {
    root: PathBuf,
}

fn root_clone(state: &State<'_, Mutex<AppState>>) -> Result<PathBuf, String> {
    let g = state.lock().map_err(|e| e.to_string())?;
    Ok(g.root.clone())
}

#[tauri::command]
fn frontend_dir() -> Option<String> {
    ui_assets::external_dir().map(|p| p.to_string_lossy().into_owned())
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
fn engine_ensure(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
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
    Ok(worker::ensure_worker_and_devices(&root, 90_000))
}

#[tauri::command]
fn engine_start_worker(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    if !paths::runtime_ready(&root) {
        return Ok(json!({"state": "error", "error": "Runtime 未就绪（缺少 torch）", "pid": 0}));
    }
    worker::start_worker(&root)?;
    Ok(worker::wait_worker_ready(&root, 90_000))
}

#[tauri::command]
fn engine_start_vc(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    if !paths::runtime_ready(&root) {
        return Ok(json!({"state": "error", "error": "Runtime 未就绪，无法开启变声", "pid": 0}));
    }
    worker::start_vc(&root)?;
    Ok(worker::wait_vc_running(&root, 180_000))
}

#[tauri::command]
fn engine_stop_vc(state: State<'_, Mutex<AppState>>, force: Option<bool>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    worker::stop_vc(&root, force.unwrap_or(true))?;
    Ok(worker::status_for_ui(&root))
}

#[tauri::command]
fn engine_force_kill(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    worker::kill_known_workers(&root);
    Ok(worker::status_for_ui(&root))
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
fn engine_list_devices(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
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
fn provision_status(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    Ok(provision::provision_status(&root))
}

#[tauri::command]
fn provision_start(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    variant: String,
    force: Option<bool>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // Long-running: spawn so command returns after completion without blocking other
    // invokes on the same thread — Tauri runs commands async; we still do work here
    // but never hold AppState.
    provision::run_provision(app, root, variant, force.unwrap_or(false))
}

#[tauri::command]
fn provision_cancel() -> Result<(), String> {
    provision::cancel_provision();
    Ok(())
}

// ----- Stage 4: voices + store ------------------------------------------------

#[tauri::command]
fn voices_list(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    Ok(voices::list_voices(&root))
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
fn voices_current(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    Ok(voices::current_selection_summary(&root))
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
fn voices_import(
    state: State<'_, Mutex<AppState>>,
    paths: Option<Vec<String>>,
    current_model_dir: Option<String>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
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
    voices::import_files(
        &root,
        &files,
        current_model_dir.as_deref(),
    )
}

#[tauri::command]
fn voices_delete(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::delete_voice(&root, &model_dir)
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
fn voices_promote(
    state: State<'_, Mutex<AppState>>,
    pth_path: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::promote_legacy(&root, &pth_path)
}

#[tauri::command]
fn voices_open_dir(state: State<'_, Mutex<AppState>>) -> Result<(), String> {
    let root = root_clone(&state)?;
    voices::open_models_dir(&root)
}

#[tauri::command]
fn store_catalog(
    state: State<'_, Mutex<AppState>>,
    prefer_remote: Option<bool>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    Ok(store::fetch_store_catalog(
        &root,
        prefer_remote.unwrap_or(true),
    ))
}

#[tauri::command]
fn store_install(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    entry: Value,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    store::install_voice_entry(app, root, entry)
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
    eprintln!("[rvc-fabric] product root: {}", root.display());
    eprintln!(
        "[rvc-fabric] runtime_ready={}",
        paths::runtime_ready(&root)
    );

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
            frontend_dir,
            ui_source,
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
            // Window is built here (not in tauri.conf.json) because its URL must
            // be the fabric:// scheme registered above.
            let url = format!("{}://localhost/index.html", ui_assets::SCHEME);
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
            eprintln!("[rvc-fabric] UI source: {}", ui_assets::source_label());

            // Regenerate configs/inuse/config.json from app_config on every
            // start. Setup ships a clean template that overwrites the installed
            // one, so without this an upgrade looks like "my devices were
            // reset" — the real settings are in User_Data and just never got
            // written back down to the engine.
            {
                let cfg = config::read(&root);
                if let Err(e) = config::sync_inuse(&root, &cfg) {
                    eprintln!("[rvc-fabric] inuse sync failed: {e}");
                }
            }

            shell_extras::install_close_handler(app.handle());
            // Tray always exists: closing to tray is what keeps conversion
            // running while the window is away.
            if let Err(e) = shell_extras::install_tray(app.handle()) {
                eprintln!("[rvc-fabric] tray unavailable: {e}");
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
                    eprintln!("[rvc-fabric] skip worker prewarm: Runtime not ready");
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running RVC Fabric");
}
