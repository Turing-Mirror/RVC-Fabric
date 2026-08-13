//! Product log book.
//!
//! Release builds have no console (`windows_subsystem = "windows"`), so
//! diagnostics have to live on disk. Layout (same idea as VS Code / Chromium
//! channel folders — not one ever-growing file, not a folder per click)::
//!
//! ```text
//! User_Data/logs/
//!   shell/2026-08-13.log     daily stream (window, IPC)
//!   worker/2026-08-13.log    realtime worker
//!   sts/sts_YYYYMMDD_HHMMSS.log   one file per conversion
//!   tts/   separate/   train/   bench/
//! ```
//!
//! Retention is 48 hours by file mtime, swept on startup. Job runs that
//! finish cleanly may delete their own file; failures stay until they age out.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::Duration;

use serde_json::Value;

static LOG_PATH: std::sync::OnceLock<Option<PathBuf>> = std::sync::OnceLock::new();
/// Serialises appends. Writes are small and rare; contention is not a concern.
static WRITE_LOCK: Mutex<()> = Mutex::new(());

/// Keep a single daily file readable. One previous sibling is enough.
const MAX_BYTES: u64 = 2 * 1024 * 1024;
/// User-facing policy: two days. Checked on every launch (and after job logs).
pub const RETAIN: Duration = Duration::from_secs(2 * 24 * 3600);

pub const CH_SHELL: &str = "shell";
pub const CH_WORKER: &str = "worker";
pub const CH_STS: &str = "sts";
pub const CH_TTS: &str = "tts";
pub const CH_SEPARATE: &str = "separate";
pub const CH_TRAIN: &str = "train";
pub const CH_BENCH: &str = "bench";

/// Point the logger at the product root. Safe to call once; later calls are
/// ignored so a stray caller cannot redirect the log mid-session.
pub fn init(root: &Path) {
    let dir = crate::paths::logs_dir(root);
    let _ = fs::create_dir_all(dir.join(CH_SHELL));
    let today = daily_path(root, CH_SHELL);
    let _ = LOG_PATH.set(Some(today));
    let _ = sweep(root);
}

/// Current shell daily file, if `init` has run.
pub fn path() -> Option<PathBuf> {
    LOG_PATH.get().cloned().flatten()
}

pub fn channel_dir(root: &Path, channel: &str) -> PathBuf {
    crate::paths::logs_dir(root).join(channel)
}

pub fn daily_path(root: &Path, channel: &str) -> PathBuf {
    let dir = channel_dir(root, channel);
    let _ = fs::create_dir_all(&dir);
    let day = chrono::Local::now().format("%Y-%m-%d");
    dir.join(format!("{day}.log"))
}

/// One-shot job log (`sts/sts_20260813_220015.log`).
pub fn run_path(root: &Path, channel: &str) -> PathBuf {
    let dir = channel_dir(root, channel);
    let _ = fs::create_dir_all(&dir);
    let stamp = chrono::Local::now().format("%Y%m%d_%H%M%S");
    let mut path = dir.join(format!("{channel}_{stamp}.log"));
    if path.exists() {
        path = dir.join(format!("{channel}_{stamp}_{}.log", std::process::id()));
    }
    path
}

fn rotate_if_huge(p: &Path) {
    if fs::metadata(p).map(|m| m.len()).unwrap_or(0) > MAX_BYTES {
        let _ = fs::rename(p, p.with_extension("log.1"));
    }
}

/// Append one stamped line to a file. Never panics.
pub fn append_file(path: &Path, line: &str) {
    let _guard = WRITE_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(dir) = path.parent() {
        let _ = fs::create_dir_all(dir);
    }
    rotate_if_huge(path);
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(f, "{line}");
    }
}

pub fn append_daily(root: &Path, channel: &str, line: &str) {
    let stamp = chrono::Local::now().format("%Y-%m-%d %H:%M:%S%.3f");
    append_file(&daily_path(root, channel), &format!("{stamp} {line}"));
}

/// Start a job log: header + pretty JSON request. Always created so a
/// preflight failure still leaves a timestamped file (the old single `sts.log`
/// missed those — UI said "see the log", file had nothing for that hour).
pub fn begin_run(root: &Path, channel: &str, payload: &Value) -> PathBuf {
    let path = run_path(root, channel);
    let stamp = chrono::Local::now().format("%Y-%m-%d %H:%M:%S");
    let body = serde_json::to_string_pretty(payload).unwrap_or_else(|_| "{}".into());
    append_file(
        &path,
        &format!("=== {channel} run {stamp} ===\n{body}\n=== stderr / notes ==="),
    );
    path
}

pub fn note_run(path: &Path, line: &str) {
    let stamp = chrono::Local::now().format("%Y-%m-%d %H:%M:%S");
    append_file(path, &format!("{stamp} {line}"));
}

/// End a job log. `keep` = failure / cancel / skipped files.
pub fn finish_run(path: &Path, keep: bool, summary: &str) {
    if keep {
        note_run(path, &format!("=== kept ({summary}) ==="));
        return;
    }
    let _ = fs::remove_file(path);
}

/// Delete `*.log` / `*.log.1` under `User_Data/logs` older than [`RETAIN`].
/// Leaves json sidecars (integrity probes) alone.
pub fn sweep(root: &Path) -> usize {
    let dir = crate::paths::logs_dir(root);
    let cutoff = std::time::SystemTime::now()
        .checked_sub(RETAIN)
        .unwrap_or(std::time::UNIX_EPOCH);
    sweep_dir(&dir, cutoff)
}

fn sweep_dir(dir: &Path, cutoff: std::time::SystemTime) -> usize {
    let Ok(rd) = fs::read_dir(dir) else {
        return 0;
    };
    let mut n = 0;
    for e in rd.flatten() {
        let p = e.path();
        if p.is_dir() {
            n += sweep_dir(&p, cutoff);
            continue;
        }
        let name = p
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        let is_log = name.ends_with(".log") || name.ends_with(".log.1");
        if !is_log {
            continue;
        }
        let older = fs::metadata(&p)
            .and_then(|m| m.modified())
            .map(|t| t < cutoff)
            .unwrap_or(false);
        if older && fs::remove_file(&p).is_ok() {
            n += 1;
        }
    }
    n
}

/// Append one line. Never panics and never blocks on failure — logging must not
/// be able to take the app down.
pub fn write(line: &str) {
    // Keep dev runs readable in the terminal; on Windows release this goes
    // nowhere, which is the whole reason the file below exists.
    eprintln!("[rvc-fabric] {line}");

    let Some(p) = path() else {
        return;
    };
    let stamp = chrono::Local::now().format("%Y-%m-%d %H:%M:%S%.3f");
    append_file(&p, &format!("{stamp} {line}"));
}

/// `log!("…{x}")` — same formatting as `format!`.
macro_rules! shell_log {
    // Literal format (original style)
    ($fmt:literal $($arg:tt)*) => {
        $crate::logging::write(&format!($fmt $($arg)*))
    };
    // Runtime string (i18n::t / String / &str) — no extra format args
    ($msg:expr) => {
        $crate::logging::write(&format!("{}", $msg))
    };
}
pub(crate) use shell_log;

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::{Duration, SystemTime};

    #[test]
    fn writing_without_init_is_a_no_op() {
        // init() is never called in unit tests; this must not panic.
        write("hello from a test");
    }

    #[test]
    fn rotation_threshold_is_sane() {
        assert!(MAX_BYTES >= 512 * 1024, "too small to hold a startup trace");
    }

    #[test]
    fn retain_is_two_days() {
        assert_eq!(RETAIN, Duration::from_secs(2 * 24 * 3600));
    }

    #[test]
    fn sweep_keeps_fresh_logs_and_json() {
        let td = std::env::temp_dir().join(format!(
            "rvcf-log-sweep-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&td);
        fs::create_dir_all(td.join("sts")).unwrap();
        let fresh = td.join("sts").join("sts_new.log");
        let json = td.join("runtime_integrity_last.json");
        fs::write(&fresh, b"new").unwrap();
        fs::write(&json, b"{}").unwrap();
        // Cutoff far in the past: nothing is "old".
        let n = sweep_dir(&td, SystemTime::UNIX_EPOCH);
        assert_eq!(n, 0);
        assert!(fresh.exists());
        assert!(json.exists());
        let _ = fs::remove_dir_all(&td);
    }
}
