//! Resolve product root (dev repo or install dir next to the exe).

use std::path::{Path, PathBuf};

/// Walk from `start` upward looking for a product root marker.
fn looks_like_root(p: &Path) -> bool {
    let has_worker = p.join("tools").join("realtime_worker.py").is_file();
    let has_runtime = p.join("Runtime").join("pythonw.exe").is_file()
        || p.join("Runtime").join("python.exe").is_file()
        || p.join("runtime").join("pythonw.exe").is_file();
    let has_user = p.join("User_Data").is_dir() || p.join("UserData").is_dir();
    // Prefer trees that have the worker script; Runtime optional in pure-UI dev.
    has_worker && (has_runtime || has_user || p.join("gui_v1.py").is_file())
}

/// Product root: install dir (exe parent) or repo root (dev).
pub fn product_root() -> PathBuf {
    // 1) Env override (dev / packaging tests)
    if let Ok(v) = std::env::var("TM_VOICE_ROOT") {
        let p = PathBuf::from(v);
        if looks_like_root(&p) {
            return p;
        }
    }

    // 2) Walk up from current_exe (release: exe at root; dev: target/debug)
    if let Ok(exe) = std::env::current_exe() {
        let mut cur = exe.parent().map(|p| p.to_path_buf());
        for _ in 0..8 {
            if let Some(ref p) = cur {
                if looks_like_root(p) {
                    return p.clone();
                }
                // cargo run: .../app/src-tauri/target/debug → climb to repo
                if p.join("src-tauri").is_dir() && p.parent().map(looks_like_root) == Some(true) {
                    return p.parent().unwrap().to_path_buf();
                }
            }
            cur = cur.and_then(|p| p.parent().map(|x| x.to_path_buf()));
        }
    }

    // 3) CWD
    if let Ok(cwd) = std::env::current_dir() {
        if looks_like_root(&cwd) {
            return cwd;
        }
        // app/ working directory while running vite/tauri from app/
        if let Some(parent) = cwd.parent() {
            if looks_like_root(parent) {
                return parent.to_path_buf();
            }
        }
        // app/src-tauri
        if cwd.ends_with("src-tauri") {
            if let Some(repo) = cwd.parent().and_then(|p| p.parent()) {
                if looks_like_root(repo) {
                    return repo.to_path_buf();
                }
            }
        }
    }

    // Last resort: cwd (may fail later with clear errors)
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

pub fn user_data(root: &Path) -> PathBuf {
    if root.join("User_Data").is_dir() || !root.join("UserData").is_dir() {
        root.join("User_Data")
    } else {
        root.join("UserData")
    }
}

pub fn control_dir(root: &Path) -> PathBuf {
    user_data(root).join("runtime_control")
}

pub fn logs_dir(root: &Path) -> PathBuf {
    user_data(root).join("logs")
}

pub fn runtime_pythonw(root: &Path) -> Option<PathBuf> {
    for rel in [
        "Runtime/pythonw.exe",
        "runtime/pythonw.exe",
        "Runtime/python.exe",
        "runtime/python.exe",
    ] {
        let p = root.join(rel);
        if p.is_file() {
            return Some(p);
        }
    }
    None
}

pub fn worker_script(root: &Path) -> PathBuf {
    root.join("tools").join("realtime_worker.py")
}
