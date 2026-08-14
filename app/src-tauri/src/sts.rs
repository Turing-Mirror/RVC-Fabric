//! 离线语音转换（Speech-to-Speech）：音频文件 → 目标音色。
//!
//! 对应官方 RVC WebUI「推理 / 批量推理」。与 `tts.rs`（文字 → SAPI → RVC）
//! 是两条线：STS 输入必须是声音，TTS 输入是文字。界面上同属「语音转换」
//! 工具窗，用分段控件切换。

use std::fs::OpenOptions;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

use serde_json::{json, Map, Value};
use tauri::{AppHandle, Emitter};

use crate::paths;

static BUSY: Mutex<bool> = Mutex::new(false);
static CANCEL: OnceLock<Arc<AtomicBool>> = OnceLock::new();
static REC_BUSY: Mutex<bool> = Mutex::new(false);
static REC_CANCEL: OnceLock<Arc<AtomicBool>> = OnceLock::new();
static REC_STOP: Mutex<Option<PathBuf>> = Mutex::new(None);

const AUDIO_EXT: &[&str] = &[
    "wav", "mp3", "flac", "ogg", "m4a", "aac", "wma", "opus", "webm",
];
const LIST_CAP: usize = 300;
const WALK_CAP: usize = 2000;
const LAST_INPUT: &str = "last_sts_input";
const LAST_OUTPUT: &str = "last_sts_output";
const MAX_RECORD_SEC: u64 = 30 * 60;

fn cancel_flag() -> Arc<AtomicBool> {
    CANCEL
        .get_or_init(|| Arc::new(AtomicBool::new(false)))
        .clone()
}

fn rec_cancel_flag() -> Arc<AtomicBool> {
    REC_CANCEL
        .get_or_init(|| Arc::new(AtomicBool::new(false)))
        .clone()
}

fn worker_script(root: &Path) -> PathBuf {
    root.join("tools").join("sts_worker.py")
}

fn record_script(root: &Path) -> PathBuf {
    root.join("tools").join("record_worker.py")
}

pub fn out_dir(root: &Path) -> PathBuf {
    paths::user_data(root).join("sts")
}

pub fn cancel() {
    cancel_flag().store(true, Ordering::SeqCst);
}

fn emit(app: &AppHandle, phase: &str, done: u64, total: u64, message: &str) {
    emit_full(app, phase, done, total, message, None, None, None, None, None, None);
}

#[allow(clippy::too_many_arguments)]
fn emit_full(
    app: &AppHandle,
    phase: &str,
    done: u64,
    total: u64,
    message: &str,
    pct: Option<u64>,
    step: Option<&str>,
    current: Option<u64>,
    ok: Option<u64>,
    skip: Option<u64>,
    file: Option<&str>,
) {
    emit_full_ex(
        app, phase, done, total, message, pct, step, current, ok, skip, file, None,
    );
}

#[allow(clippy::too_many_arguments)]
fn emit_full_ex(
    app: &AppHandle,
    phase: &str,
    done: u64,
    total: u64,
    message: &str,
    pct: Option<u64>,
    step: Option<&str>,
    current: Option<u64>,
    ok: Option<u64>,
    skip: Option<u64>,
    file: Option<&str>,
    reason: Option<&str>,
) {
    let mut body = json!({
        "phase": phase,
        "done": done,
        "total": total.max(1),
        "message": message,
    });
    if let Some(p) = pct {
        body["pct"] = json!(p.min(100));
    }
    if let Some(s) = step {
        if !s.is_empty() {
            body["step"] = json!(s);
        }
    }
    if let Some(c) = current {
        body["current"] = json!(c);
    }
    if let Some(o) = ok {
        body["ok"] = json!(o);
    }
    if let Some(s) = skip {
        body["skip"] = json!(s);
    }
    if let Some(f) = file {
        if !f.is_empty() {
            body["file"] = json!(f);
        }
    }
    if let Some(r) = reason {
        if !r.is_empty() {
            body["reason"] = json!(r);
        }
    }
    let _ = app.emit("sts-progress", body);
}

/// 当前能不能转、用哪个音色。
pub fn status(root: &Path) -> Value {
    let cfg = crate::config::read(root);
    let pth = cfg
        .get("pth_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let index = cfg
        .get("index_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let engine_ready = crate::engine_assets::engine_core_ready(root);
    let missing = if engine_ready {
        Vec::new()
    } else {
        crate::engine_assets::engine_core_missing(root)
    };
    json!({
        "runtime_ready": paths::runtime_ready(root),
        "engine_core_ready": engine_ready,
        "engine_core_missing": missing,
        "worker_present": worker_script(root).is_file(),
        "model_path": pth,
        "model_name": cfg.get("last_model_name").and_then(|v| v.as_str()).unwrap_or(""),
        "index_path": index,
        "pitch": cfg.get("pitch").and_then(|v| v.as_i64()).unwrap_or(0),
        "f0method": cfg.get("f0method").and_then(|v| v.as_str()).unwrap_or("rmvpe"),
        "index_rate": cfg.get("index_rate").and_then(|v| v.as_f64()).unwrap_or(0.75),
        "out_dir": out_dir(root).to_string_lossy(),
        "default_input_dir": default_input_dir(root).to_string_lossy(),
        "last_input": existing_path(cfg.get(LAST_INPUT).and_then(|v| v.as_str()).unwrap_or("")),
        "last_output": existing_path(cfg.get(LAST_OUTPUT).and_then(|v| v.as_str()).unwrap_or("")),
        "input_device": cfg.get("sg_input_device").and_then(|v| v.as_str()).unwrap_or(""),
        "recorder_present": record_script(root).is_file(),
        "recording": *REC_BUSY.lock().unwrap_or_else(|e| e.into_inner()),
        // 实时变声是否还占着显存。面板拿它决定要不要先问一句再开转。
        "worker_alive": crate::worker::is_worker_alive(root),
        "busy": *BUSY.lock().unwrap_or_else(|e| e.into_inner()),
    })
}

fn existing_path(raw: &str) -> String {
    let p = raw.trim();
    if p.is_empty() {
        return String::new();
    }
    if Path::new(p).exists() {
        p.to_string()
    } else {
        String::new()
    }
}

fn remember(root: &Path, key: &str, value: &str) {
    let v = value.trim();
    if v.is_empty() {
        return;
    }
    let mut patch = Map::new();
    patch.insert(key.to_string(), json!(v));
    let _ = crate::config::update(root, patch);
}

pub fn remember_input(root: &Path, path: &str) {
    remember(root, LAST_INPUT, path);
}

pub fn remember_output(root: &Path, path: &str) {
    remember(root, LAST_OUTPUT, path);
}

pub fn default_input_dir(root: &Path) -> PathBuf {
    paths::user_data(root).join("sts").join("input")
}

pub fn is_audio_path(path: &Path) -> bool {
    path.extension()
        .and_then(|e| e.to_str())
        .map(|e| AUDIO_EXT.iter().any(|x| e.eq_ignore_ascii_case(x)))
        .unwrap_or(false)
}

/// 录音和管理用的文件夹：选了文件夹就用它，选了文件就用它所在目录，
/// 都没选就落到默认输入目录。
pub fn resolve_input_dir(root: &Path, input: &str) -> PathBuf {
    let raw = input.trim();
    if raw.is_empty() {
        return default_input_dir(root);
    }
    let p = Path::new(raw);
    if p.is_dir() {
        return p.to_path_buf();
    }
    if p.is_file() {
        if let Some(parent) = p.parent() {
            if !parent.as_os_str().is_empty() {
                return parent.to_path_buf();
            }
        }
    }
    default_input_dir(root)
}

fn path_under(child: &Path, parent: &Path) -> bool {
    let Ok(c) = child.canonicalize() else {
        return false;
    };
    let Ok(p) = parent.canonicalize() else {
        return false;
    };
    c.starts_with(p)
}

/// 选输入：`folder=false` 选单个音频，`true` 选文件夹（批量）。
pub fn pick_input(folder: bool) -> Option<String> {
    let title = if folder {
        crate::i18n::t("s.46ffa5479e")
    } else {
        crate::i18n::t("s.79b552d700")
    };
    let dlg = rfd::FileDialog::new().set_title(&title);
    if folder {
        dlg.pick_folder().map(|p| p.to_string_lossy().into_owned())
    } else {
        let filter = crate::i18n::t("s.461189f186");
        dlg.add_filter(
            &filter,
            &["wav", "mp3", "flac", "ogg", "m4a", "aac", "wma", "opus"],
        )
        .pick_file()
        .map(|p| p.to_string_lossy().into_owned())
    }
}

pub fn pick_output() -> Option<String> {
    let title = crate::i18n::t("s.cb12ce77e7");
    rfd::FileDialog::new()
        .set_title(&title)
        .pick_folder()
        .map(|p| p.to_string_lossy().into_owned())
}

/// 列出输入文件夹里的音频（含子目录），按修改时间新→旧，最多 LIST_CAP。
pub fn list_input(root: &Path, input: &str) -> Value {
    let dir = resolve_input_dir(root, input);
    let exists = dir.is_dir();
    let mut files: Vec<(u64, Value)> = Vec::new();
    if exists {
        if let Ok(walk) = walk_audio(&dir) {
            files = walk;
        }
    }
    files.sort_by(|a, b| b.0.cmp(&a.0));
    let truncated = files.len() > LIST_CAP;
    if truncated {
        files.truncate(LIST_CAP);
    }
    json!({
        "dir": dir.to_string_lossy(),
        "exists": exists,
        "truncated": truncated,
        "files": files.into_iter().map(|(_, v)| v).collect::<Vec<_>>(),
    })
}

fn walk_audio(dir: &Path) -> std::io::Result<Vec<(u64, Value)>> {
    let mut out = Vec::new();
    let mut stack = vec![dir.to_path_buf()];
    while let Some(cur) = stack.pop() {
        let rd = match std::fs::read_dir(&cur) {
            Ok(r) => r,
            Err(_) => continue,
        };
        for ent in rd.flatten() {
            let path = ent.path();
            let ft = match ent.file_type() {
                Ok(t) => t,
                Err(_) => continue,
            };
            if ft.is_dir() {
                stack.push(path);
                continue;
            }
            if !ft.is_file() || !is_audio_path(&path) {
                continue;
            }
            let meta = match ent.metadata() {
                Ok(m) => m,
                Err(_) => continue,
            };
            let mtime = meta
                .modified()
                .ok()
                .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|d| d.as_secs())
                .unwrap_or(0);
            let rel = path
                .strip_prefix(dir)
                .map(|p| p.to_string_lossy().replace('\\', "/"))
                .unwrap_or_else(|_| {
                    path.file_name()
                        .map(|n| n.to_string_lossy().into_owned())
                        .unwrap_or_default()
                });
            let name = path
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_else(|| rel.clone());
            out.push((
                mtime,
                json!({
                    "name": name,
                    "rel": rel,
                    "path": path.to_string_lossy(),
                    "size": meta.len(),
                    "mtime": mtime,
                }),
            ));
            if out.len() >= WALK_CAP {
                return Ok(out);
            }
        }
    }
    Ok(out)
}

pub fn delete_input_file(root: &Path, input: &str, path: &str) -> Result<(), String> {
    let dir = resolve_input_dir(root, input);
    let file = Path::new(path);
    if !file.is_file() {
        return Err(crate::i18n::t("s.stsInputDirMissing"));
    }
    if !is_audio_path(file) || !path_under(file, &dir) {
        return Err(crate::i18n::t("s.stsDeleteUnsafe"));
    }
    std::fs::remove_file(file).map_err(|e| crate::i18n::te("s.stsDeleteFail", &e))?;
    Ok(())
}

pub fn reveal_path(path: &str) -> Result<(), String> {
    let p = Path::new(path);
    if p.is_dir() {
        std::fs::create_dir_all(p).map_err(|e| e.to_string())?;
        return crate::shell_extras::reveal(&p.join("x"));
    }
    if p.is_file() {
        return crate::shell_extras::reveal(p);
    }
    if let Some(parent) = p.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        return crate::shell_extras::reveal(&parent.join("x"));
    }
    Err(crate::i18n::t("s.stsInputDirMissing"))
}

pub fn cancel_record() {
    rec_cancel_flag().store(true, Ordering::SeqCst);
    if let Ok(g) = REC_STOP.lock() {
        if let Some(p) = g.as_ref() {
            let _ = std::fs::write(p, b"stop");
        }
    }
}

/// 在输入文件夹录一段 wav。阻塞到用户停止或超时。
pub fn record(app: &AppHandle, root: &Path, input: &str) -> Result<Value, String> {
    {
        let conv = *BUSY.lock().unwrap_or_else(|e| e.into_inner());
        if conv {
            return Err(crate::i18n::t("s.stsRecordBusy"));
        }
        let mut g = REC_BUSY.lock().unwrap_or_else(|e| e.into_inner());
        if *g {
            return Err(crate::i18n::t("s.stsRecordAlready"));
        }
        *g = true;
    }
    rec_cancel_flag().store(false, Ordering::SeqCst);
    let result = record_inner(app, root, input);
    *REC_STOP.lock().unwrap_or_else(|e| e.into_inner()) = None;
    *REC_BUSY.lock().unwrap_or_else(|e| e.into_inner()) = false;
    if let Err(ref e) = result {
        emit_record(app, "error", None, None, e);
    }
    result
}

fn emit_record(app: &AppHandle, phase: &str, db: Option<f64>, sec: Option<f64>, message: &str) {
    let mut body = json!({
        "phase": phase,
        "message": message,
    });
    if let Some(v) = db {
        body["db"] = json!(v);
    }
    if let Some(v) = sec {
        body["sec"] = json!(v);
    }
    let _ = app.emit("sts-record", body);
}

fn record_inner(app: &AppHandle, root: &Path, input: &str) -> Result<Value, String> {
    if !paths::runtime_ready(root) {
        return Err(crate::i18n::t("s.stsRecordNeedRuntime"));
    }
    let script = record_script(root);
    if !script.is_file() {
        return Err(crate::i18n::t("s.stsRecordNeedWorker"));
    }

    let dir = resolve_input_dir(root, input);
    std::fs::create_dir_all(&dir).map_err(|e| crate::i18n::te("s.stsRecordNoFolder", &e))?;
    remember_input(root, &dir.to_string_lossy());

    let stamp = chrono::Local::now().format("%Y%m%d_%H%M%S").to_string();
    let dest = unique_rec_path(&dir, &stamp);
    let cfg = crate::config::read(root);
    let device = cfg
        .get("sg_input_device")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let hostapi = cfg
        .get("sg_hostapi")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    let cache = paths::update_cache(root);
    let _ = std::fs::create_dir_all(&cache);
    let req = cache.join("record_request.json");
    let stop = cache.join("record_stop");
    let _ = std::fs::remove_file(&stop);
    *REC_STOP.lock().unwrap_or_else(|e| e.into_inner()) = Some(stop.clone());
    let payload = json!({
        "output": dest.to_string_lossy(),
        "device": device,
        "hostapi": hostapi,
        "stop_file": stop.to_string_lossy(),
        "max_sec": MAX_RECORD_SEC,
    });
    std::fs::write(&req, serde_json::to_string_pretty(&payload).unwrap_or_default())
        .map_err(|e| crate::i18n::te("s.5ee0565f28", &e))?;

    let py = paths::runtime_python(root).ok_or(crate::i18n::t("s.47e57cab60"))?;
    emit_record(app, "start", None, Some(0.0), &crate::i18n::t("s.stsRecordOpening"));

    let mut cmd = Command::new(&py);
    cmd.arg(script.as_os_str())
        .arg(req.as_os_str())
        .current_dir(root)
        .envs(crate::worker::env_for_runtime(root))
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }

    let mut child = cmd
        .spawn()
        .map_err(|e| crate::i18n::te("s.4f592d4fc2", &e))?;
    let _keep = crate::worker::ToolPidGuard::new(child.id());
    let stdout = match child.stdout.take() {
        Some(s) => s,
        None => {
            let _ = child.kill();
            return Err(crate::i18n::t("s.68759edc4b").into());
        }
    };

    let mut file_out = dest.to_string_lossy().into_owned();
    let mut sec_out = 0.0_f64;
    let mut fail: Option<String> = None;

    for line in BufReader::new(stdout).lines().map_while(Result::ok) {
        if rec_cancel_flag().load(Ordering::SeqCst) {
            let _ = std::fs::write(&stop, b"stop");
            // 给 worker 一点时间把 wav 头写完；还不退再杀。
            std::thread::sleep(std::time::Duration::from_millis(200));
            let _ = child.kill();
            let _ = child.wait();
            break;
        }
        let Ok(v) = serde_json::from_str::<Value>(&line) else {
            continue;
        };
        let phase = v.get("phase").and_then(|x| x.as_str()).unwrap_or("");
        let msg = v.get("message").and_then(|x| x.as_str()).unwrap_or("");
        let db = v.get("db").and_then(|x| x.as_f64());
        let sec = v.get("sec").and_then(|x| x.as_f64());
        match phase {
            "start" => {
                let fallback = crate::i18n::t("s.stsRecording");
                let text = if msg.is_empty() { fallback.as_str() } else { msg };
                emit_record(app, "start", None, sec.or(Some(0.0)), text);
            }
            "level" => {
                emit_record(app, "level", db, sec, msg);
            }
            "done" => {
                if let Some(f) = v.get("file").and_then(|x| x.as_str()) {
                    file_out = f.to_string();
                }
                if let Some(s) = sec {
                    sec_out = s;
                }
            }
            "error" => fail = Some(msg.to_string()),
            _ => {}
        }
    }

    if rec_cancel_flag().load(Ordering::SeqCst) {
        let _ = std::fs::write(&stop, b"stop");
    }
    let _ = child.wait();
    let _ = std::fs::remove_file(&stop);
    *REC_STOP.lock().unwrap_or_else(|e| e.into_inner()) = None;

    let cancelled = rec_cancel_flag().load(Ordering::SeqCst);
    if let Some(e) = fail {
        if cancelled {
            return Ok(json!({
                "ok": true,
                "file": "",
                "dir": dir.to_string_lossy(),
                "sec": 0,
                "cancelled": true,
            }));
        }
        return Err(e);
    }
    if !Path::new(&file_out).is_file() {
        if cancelled {
            return Ok(json!({
                "ok": true,
                "file": "",
                "dir": dir.to_string_lossy(),
                "sec": 0,
                "cancelled": true,
            }));
        }
        return Err(crate::i18n::t("s.stsRecordEmpty"));
    }
    remember_input(root, &dir.to_string_lossy());
    emit_record(app, "done", None, Some(sec_out), &file_out);
    Ok(json!({
        "ok": true,
        "file": file_out,
        "dir": dir.to_string_lossy(),
        "sec": sec_out,
    }))
}

fn unique_rec_path(dir: &Path, stamp: &str) -> PathBuf {
    let mut dest = dir.join(format!("rec_{stamp}.wav"));
    if !dest.exists() {
        return dest;
    }
    for n in 2..1000 {
        dest = dir.join(format!("rec_{stamp}_{n}.wav"));
        if !dest.exists() {
            return dest;
        }
    }
    dir.join(format!("rec_{stamp}_{}.wav", std::process::id()))
}

/// Resolve which .pth / .index this job should use.
///
/// Explicit paths from the tool panel win; empty falls back to the homepage
/// current voice in app_config. Does **not** rewrite the global selection —
/// offline conversion can use a different voice without switching realtime.
fn resolve_model(
    root: &Path,
    model_path: &str,
    index_path: &str,
) -> Result<(String, String), String> {
    let explicit = model_path.trim();
    if !explicit.is_empty() {
        if !Path::new(explicit).is_file() {
            return Err(crate::i18n::te("s.stsModelMissing", &explicit));
        }
        let idx = {
            let raw = index_path.trim();
            if !raw.is_empty() && Path::new(raw).is_file() {
                raw.to_string()
            } else {
                // Prefer the voice library's bound index for this pth.
                index_for_model_path(root, explicit)
            }
        };
        return Ok((explicit.to_string(), idx));
    }

    let cfg = crate::config::read(root);
    let pth = cfg
        .get("pth_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    if pth.is_empty() || !Path::new(&pth).is_file() {
        return Err(crate::i18n::t("s.e84378f99a").into());
    }
    let idx = cfg
        .get("index_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    Ok((pth, idx))
}

fn index_for_model_path(root: &Path, pth: &str) -> String {
    let cat = crate::voices::list_voices(root);
    let Some(models) = cat.get("models").and_then(|v| v.as_array()) else {
        return String::new();
    };
    for m in models {
        let mp = m.get("path").and_then(|v| v.as_str()).unwrap_or("");
        if mp == pth {
            let idx = m.get("index").and_then(|v| v.as_str()).unwrap_or("").trim();
            if !idx.is_empty() && Path::new(idx).is_file() {
                return idx.to_string();
            }
            break;
        }
    }
    String::new()
}

/// Full success = process ok, no error phase, no skipped files, at least one output.
fn sts_run_clean_success(files: &[String], skipped: &[Value]) -> bool {
    skipped.is_empty() && !files.is_empty()
}

/// 跑一次转换。阻塞。
pub fn run(
    app: &AppHandle,
    root: &Path,
    input: &str,
    output: &str,
    pitch: i32,
    f0method: &str,
    index_rate: f64,
    model_path: &str,
    index_path: &str,
) -> Result<Value, String> {
    {
        if *REC_BUSY.lock().unwrap_or_else(|e| e.into_inner()) {
            return Err(crate::i18n::t("s.stsRecordConvertBusy").into());
        }
        let mut g = BUSY.lock().unwrap_or_else(|e| e.into_inner());
        if *g {
            return Err(crate::i18n::t("s.6a025ac81b").into());
        }
        *g = true;
    }
    cancel_flag().store(false, Ordering::SeqCst);
    // Open the run log *before* preflight so a 22:00 "engine missing" still
    // leaves a file with that timestamp. The old single sts.log never saw those.
    let header = json!({
        "input": input,
        "output": output,
        "pitch": pitch,
        "f0method": f0method,
        "index_rate": index_rate,
        "model_path": model_path,
        "index_path": index_path,
    });
    let log_path = crate::logging::begin_run(root, crate::logging::CH_STS, &header);
    crate::logging::shell_log!(
        "sts run log {}",
        log_path
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("sts")
    );
    let result = run_inner(
        app,
        root,
        input,
        output,
        pitch,
        f0method,
        index_rate,
        model_path,
        index_path,
        &log_path,
    );
    match &result {
        Ok(v) => {
            let files = v
                .get("files")
                .and_then(|x| x.as_array())
                .map(|a| a.len())
                .unwrap_or(0);
            let skipped = v
                .get("skipped")
                .and_then(|x| x.as_array())
                .map(|a| a.len())
                .unwrap_or(0);
            crate::logging::finish_run(
                &log_path,
                true,
                if skipped > 0 || files == 0 {
                    "skipped or empty"
                } else {
                    "ok"
                },
            );
        }
        Err(e) => {
            crate::logging::note_run(&log_path, &format!("ERROR {e}"));
            crate::logging::finish_run(&log_path, true, "error");
        }
    }
    *BUSY.lock().unwrap_or_else(|e| e.into_inner()) = false;
    if let Err(ref e) = result {
        emit(app, "error", 0, 1, e);
    }
    result
}

fn run_inner(
    app: &AppHandle,
    root: &Path,
    input: &str,
    output: &str,
    pitch: i32,
    f0method: &str,
    index_rate: f64,
    model_path: &str,
    index_path: &str,
    log_path: &Path,
) -> Result<Value, String> {
    if !paths::runtime_ready(root) {
        return Err(crate::i18n::t("s.75b84a31d6").into());
    }
    if !crate::engine_assets::engine_core_ready(root) {
        let miss = crate::engine_assets::engine_core_missing(root).join("、");
        return Err(crate::i18n::te("s.5eb32f1350", &miss));
    }
    let script = worker_script(root);
    if !script.is_file() {
        return Err(crate::i18n::te("s.bc197d22e5", &(script.display())));
    }
    if input.trim().is_empty() {
        return Err(crate::i18n::t("s.e9c01e81cb").into());
    }
    let out = if output.trim().is_empty() {
        out_dir(root)
    } else {
        PathBuf::from(output.trim())
    };
    std::fs::create_dir_all(&out).map_err(|e| crate::i18n::te("s.e9ddef6eab", &(e)))?;

    // 离线转换要独占显存：hubert + net_g + rmvpe 同时上卡。实时 worker 若还
    // 活着（尤其是 3GB 级小卡），两边一抢就是 CUDA OOM。训练路径同理——工具
    // 窗开跑就先腾出 GPU；用户之后再点「开启变声」即可。
    if crate::worker::is_worker_alive(root) {
        let free_msg = crate::i18n::t("s.stsFreeVram");
        emit_full(
            app,
            "run",
            0,
            1,
            &free_msg,
            Some(0),
            Some("free_vram"),
            Some(0),
            Some(0),
            Some(0),
            None,
        );
        crate::worker::kill_known_workers(root);
        // 给驱动一点时间把进程显存真正吐回池子；立刻 spawn 下一份 python 时
        // 偶发还能看见「reserved >> free」。3GB 卡上 400ms 有时不够。
        std::thread::sleep(std::time::Duration::from_millis(700));
    }

    let (pth, index) = resolve_model(root, model_path, index_path)?;

    let req = paths::update_cache(root).join("sts_request.json");
    if let Some(p) = req.parent() {
        let _ = std::fs::create_dir_all(p);
    }
    let payload = json!({
        "input": input,
        "output": out.to_string_lossy(),
        "model": pth,
        "index": index,
        "pitch": pitch,
        "f0method": if f0method.trim().is_empty() { "rmvpe" } else { f0method },
        "index_rate": index_rate.clamp(0.0, 1.0),
        "filter_radius": 3,
        "resample_sr": 0,
        "rms_mix_rate": 1.0,
        "protect": 0.33,
    });
    std::fs::write(&req, serde_json::to_string_pretty(&payload).unwrap_or_default())
        .map_err(|e| crate::i18n::te("s.5ee0565f28", &(e)))?;

    let py = paths::runtime_python(root).ok_or(crate::i18n::t("s.47e57cab60"))?;
    let errfile = OpenOptions::new().create(true).append(true).open(log_path).ok();

    let mut cmd = Command::new(&py);
    cmd.arg(script.as_os_str())
        .arg(req.as_os_str())
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

    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            crate::logging::note_run(log_path, &format!("spawn failed: {e}"));
            return Err(crate::i18n::te("s.4f592d4fc2", &(e)));
        }
    };
    let _keep = crate::worker::ToolPidGuard::new(child.id());
    let stdout = match child.stdout.take() {
        Some(s) => s,
        None => {
            let _ = child.kill();
            return Err(crate::i18n::t("s.68759edc4b").into());
        }
    };
    let mut files: Vec<String> = Vec::new();
    let mut skipped: Vec<Value> = Vec::new();
    let mut fail: Option<String> = None;
    let mut total: u64 = 1;

    for line in BufReader::new(stdout).lines().map_while(Result::ok) {
        if cancel_flag().load(Ordering::SeqCst) {
            let _ = child.kill();
            let _ = child.wait();
            crate::logging::note_run(log_path, "cancelled by user");
            return Err(crate::i18n::t("s.a5ffdc95ee").into());
        }
        let Ok(v) = serde_json::from_str::<Value>(&line) else {
            continue;
        };
        let phase = v.get("phase").and_then(|x| x.as_str()).unwrap_or("");
        let msg = v.get("message").and_then(|x| x.as_str()).unwrap_or("");
        // 细粒度 0–100；worker 旧版可能不带，界面回退到 done/total。
        let pct = v
            .get("pct")
            .and_then(|x| x.as_u64().or_else(|| x.as_f64().map(|f| f as u64)));
        let step = v.get("step").and_then(|x| x.as_str());
        let current = v.get("current").and_then(|x| x.as_u64());
        let ok_n = v.get("ok").and_then(|x| x.as_u64());
        let skip_n = v.get("skip").and_then(|x| x.as_u64());
        let file = v.get("file").and_then(|x| x.as_str());
        match phase {
            "start" => {
                total = v.get("total").and_then(|x| x.as_u64()).unwrap_or(1).max(1);
                let fallback = crate::i18n::t("s.6b3e0028b8");
                emit_full(
                    app,
                    "start",
                    0,
                    total,
                    if msg.is_empty() { &fallback } else { msg },
                    pct.or(Some(0)),
                    step,
                    current.or(Some(0)),
                    ok_n.or(Some(0)),
                    skip_n.or(Some(0)),
                    file,
                );
            }
            "run" => {
                total = v.get("total").and_then(|x| x.as_u64()).unwrap_or(total).max(1);
                let done = v.get("done").and_then(|x| x.as_u64()).unwrap_or(0);
                let fallback = crate::i18n::t("s.090840132b");
                emit_full(
                    app,
                    "run",
                    done,
                    total,
                    if msg.is_empty() { &fallback } else { msg },
                    pct,
                    step,
                    current,
                    ok_n,
                    skip_n,
                    file,
                );
            }
            // 单个文件被跳过。照样往界面上推，用户当场就能看到是哪个坏了，
            // 不用等整批跑完再翻日志。
            "skip" => {
                total = v.get("total").and_then(|x| x.as_u64()).unwrap_or(total).max(1);
                let done = v.get("done").and_then(|x| x.as_u64()).unwrap_or(0);
                // 优先用 worker 的 reason 字段，避免列表里叠成「name — 跳过 name：…」。
                let reason = v
                    .get("reason")
                    .and_then(|x| x.as_str())
                    .filter(|s| !s.is_empty())
                    .unwrap_or(msg);
                if let Some(fname) = file {
                    skipped.push(json!({
                        "file": fname,
                        "name": fname,
                        "reason": reason,
                    }));
                }
                emit_full_ex(
                    app,
                    "skip",
                    done,
                    total,
                    msg,
                    pct,
                    step,
                    current,
                    ok_n,
                    skip_n,
                    file,
                    Some(reason),
                );
            }
            "done" => {
                if let Some(arr) = v.get("files").and_then(|x| x.as_array()) {
                    files = arr
                        .iter()
                        .filter_map(|x| x.as_str().map(str::to_string))
                        .collect();
                }
                if let Some(arr) = v.get("skipped").and_then(|x| x.as_array()) {
                    // 终态清单为准；过程中 skip 事件可能已塞过。
                    skipped = arr.clone();
                }
                // 推一条 100% 完成，避免界面停在最后一个文件的中间百分比。
                let done_msg = if msg.is_empty() {
                    crate::i18n::t("s.e43ef3d56a")
                } else {
                    msg.to_string()
                };
                emit_full(
                    app,
                    "done",
                    total,
                    total,
                    &done_msg,
                    Some(100),
                    Some("done"),
                    Some(total),
                    ok_n.or(Some(files.len() as u64)),
                    skip_n.or(Some(skipped.len() as u64)),
                    None,
                );
            }
            "error" => fail = Some(msg.to_string()),
            _ => {}
        }
    }

    let st = match child.wait() {
        Ok(s) => s,
        Err(e) => {
            crate::logging::note_run(log_path, &format!("wait failed: {e}"));
            return Err(crate::i18n::te("s.cdad0c927d", &(e)));
        }
    };
    if let Some(e) = fail {
        crate::logging::note_run(log_path, &format!("worker error: {e}"));
        return Err(e);
    }
    if !st.success() {
        crate::logging::note_run(
            log_path,
            &format!("process exit code {}", st.code().unwrap_or(-1)),
        );
        return Err(crate::i18n::te("s.0d8ec50de8", &st.code().unwrap_or(-1)));
    }
    if !sts_run_clean_success(&files, &skipped) {
        crate::logging::note_run(
            log_path,
            &format!(
                "finished with {} ok, {} skipped",
                files.len(),
                skipped.len()
            ),
        );
    }

    emit_full(
        app,
        "done",
        total,
        total,
        &crate::i18n::t("s.e43ef3d56a"),
        Some(100),
        Some("done"),
        Some(total),
        Some(files.len() as u64),
        Some(skipped.len() as u64),
        None,
    );
    let stats = crate::paths::clean_temps(root);
    crate::paths::log_clean_stats(&crate::i18n::t("s.e246e3bafa"), root, &stats);
    Ok(json!({
        "ok": true,
        "files": files,
        "skipped": skipped,
        "output": out.to_string_lossy(),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn tmp_root() -> PathBuf {
        let n = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let dir = std::env::temp_dir().join(format!("rvcf-sts-rec-{n}"));
        fs::create_dir_all(dir.join("User_Data")).unwrap();
        dir
    }

    #[test]
    fn audio_ext_accepts_common_and_rejects_other() {
        assert!(is_audio_path(Path::new("a.WAV")));
        assert!(is_audio_path(Path::new("b.opus")));
        assert!(!is_audio_path(Path::new("c.txt")));
        assert!(!is_audio_path(Path::new("noext")));
    }

    #[test]
    fn resolve_dir_file_parent_and_empty_default() {
        let root = tmp_root();
        let folder = root.join("clips");
        fs::create_dir_all(&folder).unwrap();
        let file = folder.join("v.wav");
        fs::write(&file, b"x").unwrap();

        assert_eq!(resolve_input_dir(&root, &folder.to_string_lossy()), folder);
        assert_eq!(resolve_input_dir(&root, &file.to_string_lossy()), folder);
        assert_eq!(resolve_input_dir(&root, ""), default_input_dir(&root));
        assert_eq!(
            resolve_input_dir(&root, r"Z:\no\such\sts_input"),
            default_input_dir(&root)
        );
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn list_skips_non_audio_and_sorts_new_first() {
        let root = tmp_root();
        let dir = root.join("in");
        fs::create_dir_all(dir.join("sub")).unwrap();
        fs::write(dir.join("skip.txt"), b"no").unwrap();
        fs::write(dir.join("a.wav"), b"1").unwrap();
        fs::write(dir.join("sub").join("b.mp3"), b"2").unwrap();

        let v = list_input(&root, &dir.to_string_lossy());
        let files = v.get("files").and_then(|x| x.as_array()).unwrap();
        assert_eq!(files.len(), 2);
        let rels: Vec<&str> = files
            .iter()
            .filter_map(|f| f.get("rel").and_then(|x| x.as_str()))
            .collect();
        assert!(rels.iter().any(|r| *r == "a.wav" || *r == "sub/b.mp3"));
        assert!(!rels.iter().any(|r| r.contains("skip")));
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn delete_rejects_outside_and_non_audio() {
        let root = tmp_root();
        let dir = root.join("in");
        fs::create_dir_all(&dir).unwrap();
        let wav = dir.join("ok.wav");
        fs::write(&wav, b"1").unwrap();
        let outside = root.join("secret.wav");
        fs::write(&outside, b"2").unwrap();
        let txt = dir.join("note.txt");
        fs::write(&txt, b"3").unwrap();

        assert!(delete_input_file(&root, &dir.to_string_lossy(), &outside.to_string_lossy()).is_err());
        assert!(delete_input_file(&root, &dir.to_string_lossy(), &txt.to_string_lossy()).is_err());
        assert!(delete_input_file(&root, &dir.to_string_lossy(), &wav.to_string_lossy()).is_ok());
        assert!(!wav.exists());
        assert!(outside.exists());
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn unique_rec_path_adds_suffix() {
        let root = tmp_root();
        let dir = root.join("in");
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("rec_20260813_120000.wav"), b"x").unwrap();
        let p = unique_rec_path(&dir, "20260813_120000");
        assert_eq!(
            p.file_name().unwrap().to_string_lossy(),
            "rec_20260813_120000_2.wav"
        );
        let _ = fs::remove_dir_all(&root);
    }
}
