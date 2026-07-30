//! RVC Fabric shell (Tauri).
//!
//! Stages 1–3: window/UI, worker bridge, Runtime provision (download/extract).

mod catalog;
mod download;
mod extract;
mod paths;
mod protocol;
mod provision;
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
    let mut dir = std::env::current_exe().ok()?;
    dir.pop();
    let fe = dir.join("frontend");
    if fe.join("index.html").is_file() {
        Some(fe.to_string_lossy().into_owned())
    } else {
        None
    }
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
        .manage(Mutex::new(AppState { root: root.clone() }))
        .invoke_handler(tauri::generate_handler![
            frontend_dir,
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
        ])
        .setup(move |_app| {
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
