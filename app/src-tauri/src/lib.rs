//! RVC Fabric shell (Tauri).
//!
//! Stage 1: window + React UI host.
//! Stage 2+: spawn Runtime pythonw worker, provision, catalog, etc.
//!
//! ## Hot-update strategy A (frontend out-of-band)
//!
//! - Vite builds into `app/frontend/` (`build.outDir`).
//! - `tauri.conf.json` → `build.frontendDist = "../frontend"`.
//! - Bundle resources also copy that tree as install-dir `frontend/`, so a
//!   later `gui_patch`-style drop can replace the UI folder without a full
//!   Rust rebuild. Packaging scripts (stage 6) own the ship layout.
//! - `frontend_dir` command reports the preferred on-disk folder for diagnostics.

use std::path::PathBuf;

/// Preferred on-disk UI folder: `<exe_dir>/frontend` when present.
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
                eprintln!("[rvc-fabric] strategy-A frontend present: {}", dir.display());
            } else {
                eprintln!("[rvc-fabric] UI via bundled frontendDist (../frontend)");
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running RVC Fabric");
}
