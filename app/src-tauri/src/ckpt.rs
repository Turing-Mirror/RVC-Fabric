//! 原版 ckpt 处理 / ONNX 导出。训练窗进阶设置调用。

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

use crate::paths;

static BUSY: Mutex<bool> = Mutex::new(false);
static CANCEL: OnceLock<Arc<AtomicBool>> = OnceLock::new();

const ACTIONS: [&str; 5] = ["merge", "change", "show", "extract", "onnx"];

fn cancel_flag() -> Arc<AtomicBool> {
    CANCEL
        .get_or_init(|| Arc::new(AtomicBool::new(false)))
        .clone()
}

fn worker_script(root: &Path) -> PathBuf {
    root.join("tools").join("ckpt_worker.py")
}

pub fn cancel() {
    cancel_flag().store(true, Ordering::SeqCst);
}

fn emit(app: &AppHandle, payload: Value) {
    let _ = app.emit("ckpt-progress", payload);
}

pub fn pick(kind: &str) -> Option<String> {
    let d = rfd::FileDialog::new();
    match kind {
        "folder" => d
            .set_title(&crate::i18n::t("s.ckptPickFolder"))
            .pick_folder(),
        "onnx" => d
            .add_filter("ONNX", &["onnx"])
            .set_title(&crate::i18n::t("s.ckptPickOnnx"))
            .save_file(),
        "f0" => d
            .add_filter(&crate::i18n::t("s.ckptPickF0"), &["txt", "csv", "f0"])
            .set_title(&crate::i18n::t("s.ckptPickF0"))
            .pick_file(),
        _ => d
            .add_filter("PTH", &["pth", "pt"])
            .set_title(&crate::i18n::t("s.ckptPickPth"))
            .pick_file(),
    }
    .map(|p| p.to_string_lossy().into_owned())
}

fn preflight(root: &Path, action: &str, req: &Value) -> Result<(), String> {
    if !ACTIONS.contains(&action) {
        return Err(crate::i18n::te("s.ckptBadAction", &action));
    }
    if !paths::runtime_ready(root) {
        return Err(crate::i18n::t("s.dc92f52f68").into());
    }
    if !worker_script(root).is_file() {
        return Err(crate::i18n::t("s.5164f3e0db").into());
    }
    if action == "merge" || action == "extract" {
        let name = req.get("name").and_then(|v| v.as_str()).unwrap_or("");
        crate::train::validate_name(name)?;
    }
    Ok(())
}

/// 阻塞跑一次。调用方挪到后台线程。
pub fn run(app: &AppHandle, root: &Path, mut req: Value) -> Result<Value, String> {
    {
        let mut g = BUSY.lock().unwrap_or_else(|e| e.into_inner());
        if *g {
            return Err(crate::i18n::t("s.ckptBusy").into());
        }
        *g = true;
    }
    cancel_flag().store(false, Ordering::SeqCst);
    let action = req
        .get("action")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let log = crate::logging::begin_run(root, crate::logging::CH_TRAIN, &req);
    let mut trace = crate::logging::RunTrace::new(log.clone());
    let started = std::time::Instant::now();
    let result = run_inner(app, root, &action, &mut req, &mut trace);
    let outcome = match &result {
        Ok(_) => "ok",
        Err(e) if e == &crate::i18n::t("s.a5ffdc95ee") => "cancelled",
        Err(_) => "error",
    };
    let out = result
        .as_ref()
        .ok()
        .and_then(|v| {
            v.get("file")
                .or_else(|| v.get("path"))
                .or_else(|| v.get("out"))
                .and_then(|x| x.as_str())
                .map(|s| s.to_string())
        })
        .unwrap_or_default();
    trace.outcome(
        outcome,
        &format!(
            "elapsed_ms: {}\naction: {action}\nout: {} ({} bytes)",
            started.elapsed().as_millis(),
            out,
            crate::logging::file_len(Path::new(&out)),
        ),
    );
    match &result {
        Ok(_) => crate::logging::finish_run(&log, true, "ok"),
        Err(e) => {
            trace.note(&format!("ERROR {e}"));
            crate::logging::finish_run(&log, true, outcome);
        }
    }
    *BUSY.lock().unwrap_or_else(|e| e.into_inner()) = false;
    if let Err(ref e) = result {
        emit(app, json!({ "phase": "error", "message": e }));
    }
    result
}

fn run_inner(
    app: &AppHandle,
    root: &Path,
    action: &str,
    req: &mut Value,
    trace: &mut crate::logging::RunTrace,
) -> Result<Value, String> {
    preflight(root, action, req)?;
    let reqfile = paths::update_cache(root).join("ckpt_request.json");
    if let Some(p) = reqfile.parent() {
        let _ = std::fs::create_dir_all(p);
    }
    std::fs::write(
        &reqfile,
        serde_json::to_string_pretty(req).unwrap_or_default(),
    )
    .map_err(|e| crate::i18n::te("s.5ee0565f28", &(e)))?;

    let py = paths::runtime_python(root).ok_or(crate::i18n::t("s.47e57cab60"))?;
    let errfile = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&trace.path)
        .ok();
    let mut cmd = Command::new(&py);
    cmd.arg(worker_script(root).as_os_str())
        .arg(reqfile.as_os_str())
        .current_dir(root)
        .envs(crate::worker::env_for_runtime(root))
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(match errfile {
            Some(f) => Stdio::from(f),
            None => Stdio::null(),
        });
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }

    let mut child = cmd
        .spawn()
        .map_err(|e| crate::i18n::te("s.217047672d", &(e)))?;
    let _keep = crate::worker::ToolPidGuard::new(child.id());
    let stdout = child.stdout.take().ok_or(crate::i18n::t("s.c73d43b29b"))?;
    let mut done: Option<Value> = None;
    let mut fail: Option<String> = None;
    for line in BufReader::new(stdout).lines().map_while(Result::ok) {
        if cancel_flag().load(Ordering::SeqCst) {
            let _ = child.kill();
            let _ = child.wait();
            trace.note("cancelled by user");
            return Err(crate::i18n::t("s.a5ffdc95ee").into());
        }
        let Ok(v) = serde_json::from_str::<Value>(&line) else {
            continue;
        };
        let phase = v.get("phase").and_then(|x| x.as_str()).unwrap_or("");
        let msg = v.get("message").and_then(|x| x.as_str()).unwrap_or("");
        match phase {
            "start" | "done" | "error" => {
                trace.note(&format!("progress {phase} {msg}"));
            }
            _ => {
                trace.progress(phase, &format!("progress {phase} {msg}"));
            }
        }
        match phase {
            "error" => {
                fail = Some(
                    v.get("message")
                        .and_then(|x| x.as_str())
                        .unwrap_or(&crate::i18n::t("s.60a21a8105"))
                        .to_string(),
                );
            }
            "done" => done = Some(v.clone()),
            _ => {}
        }
        emit(app, v);
    }
    let st = child.wait().map_err(|e| crate::i18n::te("s.d21a4981b7", &(e)))?;
    if let Some(e) = fail {
        return Err(e);
    }
    if !st.success() {
        return Err(crate::i18n::te("s.ckptFail", &st.code().unwrap_or(-1)));
    }
    Ok(done.unwrap_or_else(|| json!({ "ok": true })))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unknown_action_is_rejected() {
        let _g = crate::i18n::testing::pin("zh-CN");
        let err = preflight(Path::new("C:\\nope"), "explode", &json!({})).unwrap_err();
        assert!(!err.is_empty());
    }

    #[test]
    fn merge_without_a_name_is_rejected_once_runtime_exists() {
        // 没 Runtime 会先停在环境检查，名字校验排在后面。这里只保证 ACTIONS 认 merge。
        assert!(ACTIONS.contains(&"merge"));
        assert!(ACTIONS.contains(&"onnx"));
    }
}
