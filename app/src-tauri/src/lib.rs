//! RVC Fabric shell (Tauri).
//!
//! Stage 2: manage Runtime realtime_worker via the existing JSON file protocol.

mod paths;
mod protocol;
mod worker;

use std::sync::Mutex;

use serde_json::{json, Map, Value};
use tauri::State;

struct AppState {
    root: std::path::PathBuf,
}

/// On-disk UI folder next to the exe when present: `<exe_dir>/frontend`.
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
    let g = state.lock().map_err(|e| e.to_string())?;
    Ok(g.root.to_string_lossy().into_owned())
}

#[tauri::command]
fn engine_status(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let g = state.lock().map_err(|e| e.to_string())?;
    Ok(worker::status_for_ui(&g.root))
}

#[tauri::command]
fn engine_ensure(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let g = state.lock().map_err(|e| e.to_string())?;
    Ok(worker::ensure_worker_and_devices(&g.root, 90_000))
}

#[tauri::command]
fn engine_start_worker(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let g = state.lock().map_err(|e| e.to_string())?;
    worker::start_worker(&g.root)?;
    Ok(worker::wait_worker_ready(&g.root, 90_000))
}

#[tauri::command]
fn engine_start_vc(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let g = state.lock().map_err(|e| e.to_string())?;
    worker::start_vc(&g.root)?;
    // Poll briefly for running / error
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(120);
    loop {
        let st = worker::status_for_ui(&g.root);
        let state_s = st.get("state").and_then(|v| v.as_str()).unwrap_or("");
        if state_s == "running" || state_s == "error" {
            return Ok(st);
        }
        if std::time::Instant::now() > deadline {
            return Ok(st);
        }
        std::thread::sleep(std::time::Duration::from_millis(300));
    }
}

#[tauri::command]
fn engine_stop_vc(state: State<'_, Mutex<AppState>>, force: Option<bool>) -> Result<Value, String> {
    let g = state.lock().map_err(|e| e.to_string())?;
    worker::stop_vc(&g.root, force.unwrap_or(true))?;
    Ok(worker::status_for_ui(&g.root))
}

#[tauri::command]
fn engine_force_kill(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let g = state.lock().map_err(|e| e.to_string())?;
    worker::kill_known_workers(&g.root);
    Ok(worker::status_for_ui(&g.root))
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
    let g = state.lock().map_err(|e| e.to_string())?;
    let mut payload = Map::new();
    if let Some(v) = pitch {
        payload.insert("pitch".into(), json!(v));
    }
    if let Some(v) = formant {
        payload.insert("formant".into(), json!(v));
    }
    if let Some(v) = function {
        // UI: "vc" | "bypass" → engine "vc" | "im"
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
    worker::set_hot(&g.root, payload)
}

#[tauri::command]
fn engine_list_devices(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let g = state.lock().map_err(|e| e.to_string())?;
    if !worker::is_worker_alive(&g.root) {
        worker::start_worker(&g.root)?;
        let st = worker::wait_worker_ready(&g.root, 90_000);
        if st.get("state").and_then(|v| v.as_str()) == Some("error") {
            return Ok(st);
        }
    }
    let _ = worker::send_command(&g.root, "list_devices", Map::new());
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(20);
    while std::time::Instant::now() < deadline {
        let st = worker::status_for_ui(&g.root);
        if st.get("input_devices").is_some() {
            return Ok(st);
        }
        std::thread::sleep(std::time::Duration::from_millis(200));
    }
    Ok(worker::status_for_ui(&g.root))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let root = paths::product_root();
    eprintln!("[rvc-fabric] product root: {}", root.display());

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
        ])
        .setup(move |_app| {
            // Pre-warm worker in background so device list is ready sooner.
            let root_bg = root.clone();
            std::thread::spawn(move || {
                let _ = worker::ensure_worker_and_devices(&root_bg, 90_000);
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running RVC Fabric");
}
