//! RVC Fabric shell (Tauri).
//!
//! Hosts the React UI and will manage the Runtime inference worker.
//! UI assets are built into `frontend/` (`frontendDist`); packaging may ship
//! that folder next to the exe so the UI pack can be replaced without a full
//! binary rebuild.

use std::path::PathBuf;

/// On-disk UI folder next to the exe when present: `<exe_dir>/frontend`.
#[tauri::command]
fn frontend_dir() -> Option<String> {
    external_frontend_dir().map(|p| p.to_string_lossy().into_owned())
}

fn external_frontend_dir() -> Option<PathBuf> {
    let mut dir = std::env::current_exe().ok()?;
    dir.pop();
    let fe = dir.join("frontend");
    if fe.join("index.html").is_file() {
        Some(fe)
    } else {
        None
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![frontend_dir])
        .setup(|_app| {
            if let Some(dir) = external_frontend_dir() {
                eprintln!("[rvc-fabric] frontend dir: {}", dir.display());
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running RVC Fabric");
}
