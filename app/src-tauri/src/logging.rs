//! Shell log file.
//!
//! Release builds set `windows_subsystem = "windows"`, which means the process
//! has no console attached and **everything written to stderr is discarded**.
//! Every diagnostic the shell printed was therefore invisible on exactly the
//! machines where it mattered — a user reporting "白屏" had nothing to send us
//! and we had nothing to read.
//!
//! So the shell writes to `User_Data/logs/shell.log` instead. That file is
//! already collected by the diagnostics bundle, so a report now carries the
//! reason the window was blank.

use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

static LOG_PATH: std::sync::OnceLock<Option<PathBuf>> = std::sync::OnceLock::new();
/// Serialises appends. Writes are small and rare; contention is not a concern.
static WRITE_LOCK: Mutex<()> = Mutex::new(());

/// Keep the log readable by a human pasting it into a report.
const MAX_BYTES: u64 = 2 * 1024 * 1024;

/// Point the logger at the product root. Safe to call once; later calls are
/// ignored so a stray caller cannot redirect the log mid-session.
pub fn init(root: &Path) {
    let dir = crate::paths::logs_dir(root);
    let _ = std::fs::create_dir_all(&dir);
    let _ = LOG_PATH.set(Some(dir.join("shell.log")));
}

/// Current log file, if `init` has run.
pub fn path() -> Option<PathBuf> {
    LOG_PATH.get().cloned().flatten()
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
    let _guard = WRITE_LOCK.lock().unwrap_or_else(|e| e.into_inner());

    // Single-step rotation: one previous file is enough to survive a restart
    // loop without letting the directory grow without bound.
    if std::fs::metadata(&p).map(|m| m.len()).unwrap_or(0) > MAX_BYTES {
        let _ = std::fs::rename(&p, p.with_extension("log.1"));
    }
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(&p) {
        let _ = writeln!(f, "{stamp} {line}");
    }
}

/// `log!("…{x}")` — same formatting as `format!`.
macro_rules! shell_log {
    ($($arg:tt)*) => {
        $crate::logging::write(&format!($($arg)*))
    };
}
pub(crate) use shell_log;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn writing_without_init_is_a_no_op() {
        // init() is never called in unit tests; this must not panic.
        write("hello from a test");
    }

    #[test]
    fn rotation_threshold_is_sane() {
        assert!(MAX_BYTES >= 512 * 1024, "too small to hold a startup trace");
    }
}
