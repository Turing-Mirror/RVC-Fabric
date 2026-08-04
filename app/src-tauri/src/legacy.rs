//! The two advanced entries the Tk shell kept in 「其他」.
//!
//! * **原版实时面板** — `gui_v1.py`, the upstream FreeSimpleGUI realtime window.
//! * **原版 WebUI** — `infer-web.py`, the upstream training / inference Gradio
//!   app on 127.0.0.1:7897.
//!
//! Both were in the Python shell (`open_legacy_gui` / `open_webui`) and both
//! were lost in the migration: the panel button shipped with no handler at all
//! and the WebUI entry was simply absent. Neither is an everyday feature, but
//! removing them was not a decision anybody made.
//!
//! Cold start is 20–40s (torch/CUDA), so these return as soon as the process is
//! spawned and the UI says so rather than pretending it is instant.

use std::path::Path;
use std::process::{Command, Stdio};

use crate::{config, logging, paths, worker};

pub const WEBUI_PORT: u16 = 7897;
pub const WEBUI_URL: &str = "http://127.0.0.1:7897";

fn runtime_python(root: &Path, windowed: bool) -> Result<std::path::PathBuf, String> {
    let p = if windowed {
        paths::runtime_pythonw(root).or_else(|| paths::runtime_python(root))
    } else {
        paths::runtime_python(root).or_else(|| paths::runtime_pythonw(root))
    };
    p.ok_or_else(|| "Runtime 未就绪，请先在首次运行向导里补全运行时".to_string())
}

/// Spawn a Runtime-python process detached, with the shell's own Python-related
/// environment stripped (see `worker::env_for_runtime`).
fn spawn_detached(
    root: &Path,
    exe: &Path,
    args: &[String],
    log_name: &str,
    show_window: bool,
) -> Result<u32, String> {
    let env = worker::env_for_runtime(root);
    let log_path = paths::logs_dir(root).join(log_name);
    let _ = std::fs::create_dir_all(paths::logs_dir(root));
    let log_file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .ok();

    let mut cmd = Command::new(exe);
    cmd.args(args)
        .current_dir(root)
        .envs(&env)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(match log_file {
            Some(f) => Stdio::from(f),
            None => Stdio::null(),
        });

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // CREATE_NEW_PROCESS_GROUP so closing our window never takes it down.
        // CREATE_NO_WINDOW only when the child has no UI of its own — applying
        // it to the panel would hide the window the user just asked for.
        let mut flags = 0x0000_0200u32;
        if !show_window {
            flags |= 0x0800_0000;
        }
        cmd.creation_flags(flags);
    }
    #[cfg(not(windows))]
    let _ = show_window;

    let child = cmd.spawn().map_err(|e| format!("启动失败：{e}"))?;
    let pid = child.id();
    logging::shell_log!("启动 {}（pid {pid}），日志 {}", exe.display(), log_path.display());
    // Detached on purpose: it outlives us, and we never wait on it.
    std::mem::forget(child);
    Ok(pid)
}

/// 打开原版实时面板（gui_v1）。
pub fn open_realtime_panel(root: &Path) -> Result<serde_json::Value, String> {
    let script = root.join("gui_v1.py");
    if !script.is_file() {
        return Err(format!("找不到实时面板脚本：{}", script.display()));
    }
    // The panel reads configs/inuse/config.json, so the current voice and
    // parameters have to be on disk before it starts — same order as the Tk
    // shell's save_settings_silent() + _sync_model_to_realtime_gui().
    let cfg = config::read(root);
    if let Err(e) = config::sync_inuse(root, &cfg) {
        logging::shell_log!(crate::i18n::t("s.324ed94533"));
    }
    let py = runtime_python(root, true)?;
    let pid = spawn_detached(
        root,
        &py,
        &[script.to_string_lossy().into_owned()],
        "realtime_gui.log",
        true,
    )?;
    Ok(serde_json::json!({
        "ok": true,
        "pid": pid,
        "message": &crate::i18n::t("s.2bd41b71bb"),
    }))
}

/// 打开原版 WebUI（infer-web.py）。Returns the URL for the caller to open.
pub fn open_webui(root: &Path) -> Result<serde_json::Value, String> {
    let script = root.join("infer-web.py");
    if !script.is_file() {
        return Err(format!("找不到 WebUI 脚本：{}", script.display()));
    }
    let pyw = runtime_python(root, true)?;
    let py = runtime_python(root, false)?;

    let mut args = vec![
        script.to_string_lossy().into_owned(),
        "--pycmd".into(),
        py.to_string_lossy().into_owned(),
        "--port".into(),
        WEBUI_PORT.to_string(),
        "--noautoopen".into(),
    ];
    // Same switch the Python shell used: the DirectML build needs --dml or it
    // falls back to CPU and looks broken on AMD/Intel machines.
    if config::read(root)
        .get("accel")
        .and_then(|v| v.as_str())
        .map(|s| s.eq_ignore_ascii_case("dml"))
        .unwrap_or(false)
        || crate::provision::read_package_meta_variant(root).as_deref() == Some("amd")
    {
        args.push("--dml".into());
    }

    let pid = spawn_detached(root, &pyw, &args, "webui.log", false)?;
    Ok(serde_json::json!({
        "ok": true,
        "pid": pid,
        "url": WEBUI_URL,
        "message": &crate::i18n::t("s.c75f611a0a"),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_scripts_report_the_path() {
        let empty = std::env::temp_dir().join("rvcf-legacy-empty");
        let _ = std::fs::create_dir_all(&empty);
        let e = open_realtime_panel(&empty).unwrap_err();
        assert!(e.contains("gui_v1.py"), "got {e}");
        let e = open_webui(&empty).unwrap_err();
        assert!(e.contains("infer-web.py"), "got {e}");
    }

    #[test]
    fn webui_url_matches_the_port() {
        assert!(WEBUI_URL.ends_with(&WEBUI_PORT.to_string()));
    }
}
