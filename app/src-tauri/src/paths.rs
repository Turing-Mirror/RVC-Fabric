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
                if p.join("src-tauri").is_dir() {
                    if let Some(parent) = p.parent() {
                        if looks_like_root(parent) {
                            return parent.to_path_buf();
                        }
                    }
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

pub fn runtime_dir(root: &Path) -> PathBuf {
    if root.join("Runtime").is_dir() {
        root.join("Runtime")
    } else {
        root.join("runtime")
    }
}

/// Prefer pythonw (no console). Fall back to python.exe only if needed.
pub fn runtime_pythonw(root: &Path) -> Option<PathBuf> {
    let rt = runtime_dir(root);
    for name in ["pythonw.exe", "python.exe"] {
        let p = rt.join(name);
        if p.is_file() {
            return Some(p);
        }
    }
    None
}

pub fn runtime_python(root: &Path) -> Option<PathBuf> {
    let rt = runtime_dir(root);
    for name in ["python.exe", "pythonw.exe"] {
        let p = rt.join(name);
        if p.is_file() {
            return Some(p);
        }
    }
    None
}

/// True when Runtime looks usable (python + torch present), same spirit as
/// launcher.runtime_provision.runtime_ready.
pub fn runtime_ready(root: &Path) -> bool {
    let Some(py) = runtime_python(root) else {
        return false;
    };
    let site = py
        .parent()
        .map(|p| p.join("Lib").join("site-packages").join("torch").join("__init__.py"));
    site.map(|p| p.is_file()).unwrap_or(false)
}

pub fn worker_script(root: &Path) -> PathBuf {
    root.join("tools").join("realtime_worker.py")
}

pub fn package_meta_path(root: &Path) -> PathBuf {
    root.join("package_meta.json")
}

pub fn models_dir(root: &Path) -> PathBuf {
    user_data(root).join("models")
}

pub fn engine_weights(root: &Path) -> PathBuf {
    root.join("assets").join("weights")
}

pub fn ch_banner_dir(root: &Path) -> PathBuf {
    user_data(root).join("ch-banner")
}

pub fn app_config_path(root: &Path) -> PathBuf {
    user_data(root).join("app_config.json")
}

/// Engine-facing config the worker reads. Must never contain absolute paths
/// from a build machine — see config::sanitize_inuse.
pub fn inuse_config_path(root: &Path) -> PathBuf {
    root.join("configs").join("inuse").join("config.json")
}

pub fn update_cache(root: &Path) -> PathBuf {
    user_data(root).join("update_cache")
}

/// 安装根下的 TEMP：上游 RVC WebUI 把 `os.environ["TEMP"]` 指到这里，
/// 分离/转码中间文件会堆在里面；不清理就会一直涨。
pub fn temp_dir(root: &Path) -> PathBuf {
    root.join("TEMP")
}

pub fn ensure_user_dirs(root: &Path) -> std::io::Result<()> {
    fs_create_all(&user_data(root))?;
    fs_create_all(&models_dir(root))?;
    fs_create_all(&ch_banner_dir(root))?;
    fs_create_all(&update_cache(root))?;
    fs_create_all(&control_dir(root))?;
    fs_create_all(&logs_dir(root))?;
    fs_create_all(&temp_dir(root))?;
    Ok(())
}

/// 清理结果，方便日志核对「有没有真的清」。
#[derive(Debug, Default, Clone)]
pub struct CleanStats {
    pub removed_files: u64,
    pub removed_dirs: u64,
    pub failed: u64,
    pub freed_bytes: u64,
}

impl CleanStats {
    fn merge(&mut self, o: CleanStats) {
        self.removed_files += o.removed_files;
        self.removed_dirs += o.removed_dirs;
        self.failed += o.failed;
        self.freed_bytes += o.freed_bytes;
    }
}

/// 清临时垃圾。启动、退出、分离/训练结束都应调。
///
/// - `TEMP/`：引擎/UVR 中间产物。先整目录删，失败再逐文件删（锁占用时常见）。
/// - `User_Data/update_cache`：半截下载、OTA 暂存、一次性请求 json。
/// - 绝不碰 Runtime / models / app_config / 已装音色。
pub fn clean_temps(root: &Path) -> CleanStats {
    let mut stats = CleanStats::default();

    let temp = temp_dir(root);
    stats.merge(wipe_dir_contents(&temp, /*recreate*/ true));

    let cache = update_cache(root);
    // 半截下载 / 临时名
    stats.merge(remove_matching_files(&cache, |name| {
        let lower = name.to_ascii_lowercase();
        lower.ends_with(".part")
            || lower.ends_with(".tmp")
            || lower.ends_with(".download")
            || lower.ends_with(".reformatted.wav")
            || lower.ends_with(".crdownload")
    }));
    // OTA 暂存目录整清（装完就没用了）
    for sub in ["gui_stage", "frontend_stage", "runtime"] {
        let p = cache.join(sub);
        if p.is_dir() {
            stats.merge(wipe_dir_contents(&p, /*recreate*/ false));
            match std::fs::remove_dir_all(&p) {
                Ok(()) => stats.removed_dirs += 1,
                Err(_) => {
                    // 非空或占用：上面已尽量清空内容
                }
            }
        }
    }
    // 一次性工具请求
    for name in [
        "separate_request.json",
        "train_request.json",
        "tts_request.json",
        "tts_sapi.wav",
        "tts_out.wav",
        "sts_request.json",
    ] {
        let p = cache.join(name);
        if p.is_file() {
            let sz = p.metadata().map(|m| m.len()).unwrap_or(0);
            match std::fs::remove_file(&p) {
                Ok(()) => {
                    stats.removed_files += 1;
                    stats.freed_bytes += sz;
                }
                Err(_) => stats.failed += 1,
            }
        }
    }

    // 系统 TEMP 里可能残留我们以前没改 TEMP 环境时留下的文件
    stats.merge(clean_system_temp_leftovers());

    stats
}

/// 记录一次清理结果（启动/退出日志里能看见有没有真清）。
pub fn log_clean_stats(phase: &str, root: &Path, stats: &CleanStats) {
    crate::logging::shell_log!("临时清理（{phase}）root={}：删文件 {} 个、目录 {} 个，失败 {}，约 {:.1} MB",
        root.display(),
        stats.removed_files,
        stats.removed_dirs,
        stats.failed,
        stats.freed_bytes as f64 / (1024.0 * 1024.0),
    );
}

/// 清空目录内容。`recreate=true` 时保证目录存在（TEMP 用）。
fn wipe_dir_contents(dir: &Path, recreate: bool) -> CleanStats {
    let mut stats = CleanStats::default();
    if dir.is_dir() {
        // 先尝试整棵拔掉（最快，和官方 WebUI 一样）。
        match std::fs::remove_dir_all(dir) {
            Ok(()) => {
                // 整目录算作一次目录删除；具体文件数不必精确。
                stats.removed_dirs += 1;
            }
            Err(_) => {
                // 有文件被占用：逐个删，删不掉的留下记 failed。
                stats.merge(remove_tree_best_effort(dir));
            }
        }
    }
    if recreate {
        let _ = std::fs::create_dir_all(dir);
    }
    stats
}

/// 逐文件/子目录删除，锁住的跳过。
fn remove_tree_best_effort(dir: &Path) -> CleanStats {
    let mut stats = CleanStats::default();
    let Ok(rd) = std::fs::read_dir(dir) else {
        stats.failed += 1;
        return stats;
    };
    for e in rd.flatten() {
        let p = e.path();
        if p.is_dir() {
            stats.merge(remove_tree_best_effort(&p));
            match std::fs::remove_dir(&p) {
                Ok(()) => stats.removed_dirs += 1,
                Err(_) => {
                    // 非空：子项可能删失败
                    if std::fs::remove_dir_all(&p).is_ok() {
                        stats.removed_dirs += 1;
                    } else {
                        stats.failed += 1;
                    }
                }
            }
        } else {
            let sz = p.metadata().map(|m| m.len()).unwrap_or(0);
            match std::fs::remove_file(&p) {
                Ok(()) => {
                    stats.removed_files += 1;
                    stats.freed_bytes += sz;
                }
                Err(_) => stats.failed += 1,
            }
        }
    }
    stats
}

fn remove_matching_files(dir: &Path, pred: impl Fn(&str) -> bool + Copy) -> CleanStats {
    let mut stats = CleanStats::default();
    let Ok(rd) = std::fs::read_dir(dir) else {
        return stats;
    };
    for e in rd.flatten() {
        let p = e.path();
        if p.is_dir() {
            stats.merge(remove_matching_files(&p, pred));
            continue;
        }
        let Some(name) = p.file_name().and_then(|s| s.to_str()) else {
            continue;
        };
        if pred(name) {
            let sz = p.metadata().map(|m| m.len()).unwrap_or(0);
            match std::fs::remove_file(&p) {
                Ok(()) => {
                    stats.removed_files += 1;
                    stats.freed_bytes += sz;
                }
                Err(_) => stats.failed += 1,
            }
        }
    }
    stats
}

/// 系统 TEMP 里带我们特征的残留（改 TEMP 环境之前写进去的）。
fn clean_system_temp_leftovers() -> CleanStats {
    let mut stats = CleanStats::default();
    let sys = std::env::temp_dir();
    let Ok(rd) = std::fs::read_dir(&sys) else {
        return stats;
    };
    for e in rd.flatten() {
        let p = e.path();
        let Some(name) = p.file_name().and_then(|s| s.to_str()) else {
            continue;
        };
        let lower = name.to_ascii_lowercase();
        let ours = lower.starts_with("rvcf-")
            || lower.starts_with("rvc-fabric")
            || lower.ends_with(".reformatted.wav")
            || (lower.contains("rvc") && (lower.ends_with(".tmp") || lower.ends_with(".part")));
        if !ours {
            continue;
        }
        if p.is_dir() {
            match std::fs::remove_dir_all(&p) {
                Ok(()) => stats.removed_dirs += 1,
                Err(_) => stats.failed += 1,
            }
        } else {
            let sz = p.metadata().map(|m| m.len()).unwrap_or(0);
            match std::fs::remove_file(&p) {
                Ok(()) => {
                    stats.removed_files += 1;
                    stats.freed_bytes += sz;
                }
                Err(_) => stats.failed += 1,
            }
        }
    }
    stats
}

/// User-triggered cache wipe from the More page.
///
/// Deletes **regenerable** junk only: conversion TEMP, leftover downloads,
/// log files, and old diagnostic zips. Never touches Runtime, User_Data/models,
/// app_config, wallpaper, or installed voices.
pub fn clear_user_cache(root: &Path) -> CleanStats {
    let mut stats = clean_temps(root);
    stats.merge(clear_log_files(&logs_dir(root)));
    let diag = user_data(root).join("diagnostics");
    stats.merge(remove_matching_files(&diag, |name| {
        let lower = name.to_ascii_lowercase();
        lower.ends_with(".zip") || lower.ends_with(".tmp")
    }));
    // Recreate the log tree so the next write does not fail.
    let _ = fs_create_all(&logs_dir(root));
    stats
}

/// Approximate size of what [`clear_user_cache`] would remove.
pub fn cache_footprint(root: &Path) -> u64 {
    let mut n = dir_size_logs_only(&logs_dir(root));
    n += dir_size_best_effort(&temp_dir(root));
    n += dir_size_best_effort(&user_data(root).join("diagnostics"));
    n
}

fn dir_size_best_effort(dir: &Path) -> u64 {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return 0;
    };
    let mut n = 0u64;
    for e in rd.flatten() {
        let p = e.path();
        if p.is_dir() {
            n += dir_size_best_effort(&p);
        } else {
            n += p.metadata().map(|m| m.len()).unwrap_or(0);
        }
    }
    n
}

fn dir_size_logs_only(dir: &Path) -> u64 {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return 0;
    };
    let mut n = 0u64;
    for e in rd.flatten() {
        let p = e.path();
        if p.is_dir() {
            n += dir_size_logs_only(&p);
            continue;
        }
        let name = p
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        if name.ends_with(".log") || name.ends_with(".log.1") {
            n += p.metadata().map(|m| m.len()).unwrap_or(0);
        }
    }
    n
}

fn clear_log_files(dir: &Path) -> CleanStats {
    remove_matching_files(dir, |name| {
        let lower = name.to_ascii_lowercase();
        lower.ends_with(".log") || lower.ends_with(".log.1")
    })
}

fn fs_create_all(p: &Path) -> std::io::Result<()> {
    if !p.is_dir() {
        std::fs::create_dir_all(p)?;
    }
    Ok(())
}

#[cfg(test)]
mod cache_clear_tests {
    use super::*;

    #[test]
    fn clear_user_cache_drops_logs_keeps_models_and_config() {
        let td = std::env::temp_dir().join(format!(
            "rvcf-cache-clear-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&td);
        let logs = td.join("User_Data").join("logs").join("sts");
        let models = td.join("User_Data").join("models").join("Anon");
        std::fs::create_dir_all(&logs).unwrap();
        std::fs::create_dir_all(&models).unwrap();
        std::fs::write(logs.join("sts_fail.log"), b"boom").unwrap();
        std::fs::write(td.join("User_Data").join("app_config.json"), b"{}").unwrap();
        std::fs::write(models.join("a.pth"), b"pth").unwrap();
        std::fs::create_dir_all(td.join("TEMP")).unwrap();
        std::fs::write(td.join("TEMP").join("junk.bin"), b"xxxx").unwrap();

        let stats = clear_user_cache(&td);
        assert!(stats.removed_files >= 1);
        assert!(!logs.join("sts_fail.log").exists());
        assert!(models.join("a.pth").exists());
        assert!(td.join("User_Data").join("app_config.json").exists());
        let _ = std::fs::remove_dir_all(&td);
    }
}
