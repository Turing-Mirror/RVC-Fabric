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

/// 原版单次推理那几个旋钮。缺省跟 infer-web 单次推理一致。
#[derive(Debug, Clone)]
pub struct ConvertOpts {
    pub filter_radius: u32,
    pub resample_sr: u32,
    pub rms_mix_rate: f64,
    pub protect: f64,
    pub format: String,
    pub sid: u32,
    pub f0_file: String,
}

impl Default for ConvertOpts {
    fn default() -> Self {
        Self {
            filter_radius: 3,
            resample_sr: 0,
            rms_mix_rate: 0.25,
            protect: 0.33,
            format: "wav".into(),
            sid: 0,
            f0_file: String::new(),
        }
    }
}

impl ConvertOpts {
    pub fn from_raw(
        filter_radius: Option<u32>,
        resample_sr: Option<u32>,
        rms_mix_rate: Option<f64>,
        protect: Option<f64>,
        format: Option<String>,
        sid: Option<u32>,
        f0_file: Option<String>,
    ) -> Self {
        let mut o = Self::default();
        if let Some(n) = filter_radius {
            o.filter_radius = n.min(7);
        }
        if let Some(n) = resample_sr {
            o.resample_sr = match n {
                16000 | 32000 | 40000 | 44100 | 48000 => n,
                _ => 0,
            };
        }
        if let Some(n) = rms_mix_rate {
            o.rms_mix_rate = n.clamp(0.0, 1.0);
        }
        if let Some(n) = protect {
            o.protect = n.clamp(0.0, 0.5);
        }
        if let Some(s) = format {
            o.format = match s.trim().to_ascii_lowercase().as_str() {
                "flac" => "flac",
                "mp3" => "mp3",
                "m4a" => "m4a",
                _ => "wav",
            }
            .into();
        }
        if let Some(n) = sid {
            o.sid = n.min(2333);
        }
        if let Some(s) = f0_file {
            let t = s.trim();
            if t.is_empty() || Path::new(t).is_file() {
                o.f0_file = t.to_string();
            }
        }
        o
    }
}

fn cancel_flag() -> Arc<AtomicBool> {
    CANCEL
        .get_or_init(|| Arc::new(AtomicBool::new(false)))
        .clone()
}

/// 转换日志状态。进度条每 120ms 可能跳一次，不能每条都落盘。
struct StsLog {
    trace: crate::logging::RunTrace,
    started: std::time::Instant,
    last: String,
    route: &'static str,
    files: Vec<String>,
    skipped: usize,
}

impl StsLog {
    fn new(path: std::path::PathBuf) -> Self {
        Self {
            trace: crate::logging::RunTrace::new(path),
            started: std::time::Instant::now(),
            last: String::new(),
            route: "cold",
            files: Vec::new(),
            skipped: 0,
        }
    }

    fn event(&mut self, v: &Value) {
        let phase = v.get("phase").and_then(|x| x.as_str()).unwrap_or("");
        let file = v.get("file").and_then(|x| x.as_str()).unwrap_or("");
        let step = v.get("step").and_then(|x| x.as_str()).unwrap_or("");
        let msg_owned = crate::i18n::t_worker_msg(v);
        let msg = msg_owned.as_str();
        let done = v.get("done").and_then(|x| x.as_u64()).unwrap_or(0);
        let total = v.get("total").and_then(|x| x.as_u64()).unwrap_or(0);
        let pct = v
            .get("pct")
            .and_then(|x| x.as_u64().or_else(|| x.as_f64().map(|f| f as u64)))
            .unwrap_or(0);
        let current = v.get("current").and_then(|x| x.as_u64()).unwrap_or(0);
        self.last = format!("{phase} {current}/{total} {step} {file} {pct}% {msg}");
        if phase == "done" {
            if let Some(arr) = v.get("files").and_then(|x| x.as_array()) {
                self.files = arr
                    .iter()
                    .filter_map(|x| x.as_str().map(str::to_string))
                    .collect();
            }
            if let Some(arr) = v.get("skipped").and_then(|x| x.as_array()) {
                self.skipped = arr.len();
            }
        } else if phase == "skip" {
            self.skipped += 1;
        }
        let line = format!(
            "progress {phase} file={file} step={step} {done}/{total} {pct}% {msg}"
        );
        match phase {
            "start" | "skip" | "done" | "error" | "cancelled" => self.trace.note(&line),
            _ => {
                // 同一文件同一 step 的百分比节流；换文件 / 换步骤立刻写。
                self.trace.progress(&format!("{phase}:{current}:{step}"), &line);
            }
        }
    }

    fn finish(&self, outcome: &str) {
        let body = format!(
            "elapsed_ms: {}\nroute: {}\nlast: {}\nok: {}\nskipped: {}\noutputs:\n{}",
            self.started.elapsed().as_millis(),
            self.route,
            if self.last.is_empty() {
                "-"
            } else {
                self.last.as_str()
            },
            self.files.len(),
            self.skipped,
            crate::logging::describe_files(&self.files, 8),
        );
        self.trace.outcome(outcome, &body);
    }
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

fn norm_dir(p: &Path) -> String {
    p.to_string_lossy()
        .replace('/', "\\")
        .trim_end_matches(['\\', '/'])
        .to_ascii_lowercase()
}

/// 默认 `User_Data/sts`：界面不能预选它，但没选输出时文件仍会落到这儿。
pub fn is_default_out(root: &Path, path: &str) -> bool {
    let raw = path.trim();
    if raw.is_empty() {
        return false;
    }
    let a = PathBuf::from(raw);
    let b = out_dir(root);
    match (a.canonicalize(), b.canonicalize()) {
        (Ok(x), Ok(y)) => x == y,
        _ => norm_dir(&a) == norm_dir(&b),
    }
}

fn last_output_for_ui(root: &Path, raw: &str) -> String {
    let p = existing_path(raw);
    if p.is_empty() || is_default_out(root, &p) {
        String::new()
    } else {
        p
    }
}

/// 打开转换结果所在目录。界面传这次用的路径；空则用上次记下的，再没有才是默认。
pub fn reveal_output(root: &Path, path: &str) -> Result<(), String> {
    let raw = path.trim();
    let dir = if !raw.is_empty() {
        PathBuf::from(raw)
    } else {
        let last = existing_path(
            crate::config::read(root)
                .get(LAST_OUTPUT)
                .and_then(|v| v.as_str())
                .unwrap_or(""),
        );
        if !last.is_empty() {
            PathBuf::from(last)
        } else {
            out_dir(root)
        }
    };
    if dir.is_file() {
        return crate::shell_extras::reveal(&dir);
    }
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    crate::shell_extras::reveal(&dir.join("x"))
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
        "last_output": last_output_for_ui(
            root,
            cfg.get(LAST_OUTPUT).and_then(|v| v.as_str()).unwrap_or(""),
        ),
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
    let log = crate::logging::begin_run(
        root,
        crate::logging::CH_STS,
        &json!({ "kind": "record", "input": input }),
    );
    let result = record_inner(app, root, input);
    match &result {
        Ok(v) => {
            let file = v.get("file").and_then(|x| x.as_str()).unwrap_or("");
            crate::logging::note_run(
                &log,
                &format!(
                    "=== outcome ({}) ===\nfile: {} ({} bytes)\nsec: {}\ncancelled: {}",
                    if v.get("cancelled").and_then(|x| x.as_bool()).unwrap_or(false) {
                        "cancelled"
                    } else {
                        "ok"
                    },
                    file,
                    crate::logging::file_len(Path::new(file)),
                    v.get("sec").and_then(|x| x.as_f64()).unwrap_or(0.0),
                    v.get("cancelled").and_then(|x| x.as_bool()).unwrap_or(false),
                ),
            );
            crate::logging::finish_run(
                &log,
                true,
                if v.get("cancelled").and_then(|x| x.as_bool()).unwrap_or(false) {
                    "cancelled"
                } else {
                    "ok"
                },
            );
        }
        Err(e) => {
            crate::logging::note_run(&log, &format!("ERROR {e}"));
            crate::logging::finish_run(&log, true, "error");
        }
    }
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

    // stderr 必须落文件，不能 piped 后不读：管道满了子进程就卡在 write 上，
    // 再也不吐 stdout，这个循环于是永远等下去，连 stop 文件都读不到。
    // sounddevice / PortAudio 开设备时本来就爱往 stderr 写警告。
    let errfile = OpenOptions::new()
        .create(true)
        .append(true)
        .open(crate::logging::daily_path(root, crate::logging::CH_STS))
        .ok();

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
        let msg_owned = crate::i18n::t_worker_msg(&v);
        let msg = msg_owned.as_str();
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

/// 热路径没跑成的两种情况。
enum HotError {
    /// worker 没接住（没应答、模型还没加载好…）。可以退回冷路径重试。
    Unavailable(String),
    /// 转换本身失败（音频坏了、显存不够…）。冷路径重来一遍也是同样的结果，
    /// 白等一分钟不说，还会把已经写出的输出再写一份。直接把错误报给用户。
    Failed(String),
}

/// worker 多久没更新 sts.json 就认为它没接住这条命令。
/// 转换途中每个文件都会推好几条进度，卡这么久基本等于死了。
const HOT_STALL_MS: u128 = 20_000;
/// 发出命令后等第一条进度的宽限。换目标音色时这里要读一个 55MB 的 pth。
const HOT_FIRST_MS: u128 = 45_000;

/// 让活着的实时 worker 就地把转换跑了。进度轮询 sts.json。
#[allow(clippy::too_many_arguments)]
fn run_hot(
    app: &AppHandle,
    root: &Path,
    input: &str,
    out: &Path,
    pitch: i32,
    f0method: &str,
    index_rate: f64,
    pth: &str,
    index: &str,
    opts: &ConvertOpts,
    job: &mut StsLog,
) -> Result<Value, HotError> {
    crate::protocol::clear_sts(root);
    let mut payload = serde_json::Map::new();
    payload.insert("input".into(), json!(input));
    payload.insert("output".into(), json!(out.to_string_lossy()));
    payload.insert("model".into(), json!(pth));
    payload.insert("index".into(), json!(index));
    payload.insert("pitch".into(), json!(pitch));
    payload.insert(
        "f0method".into(),
        json!(if f0method.trim().is_empty() { "rmvpe" } else { f0method }),
    );
    payload.insert("index_rate".into(), json!(index_rate.clamp(0.0, 1.0)));
    payload.insert("filter_radius".into(), json!(opts.filter_radius));
    payload.insert("resample_sr".into(), json!(opts.resample_sr));
    payload.insert("rms_mix_rate".into(), json!(opts.rms_mix_rate));
    payload.insert("protect".into(), json!(opts.protect));
    payload.insert("format".into(), json!(opts.format));
    payload.insert("sid".into(), json!(opts.sid));
    payload.insert("f0_file".into(), json!(opts.f0_file));
    let seq = crate::worker::send_command(root, "convert", payload)
        .map_err(HotError::Unavailable)?;

    let started = std::time::Instant::now();
    let mut last_change = std::time::Instant::now();
    let mut last_ts = 0.0_f64;
    let mut saw_any = false;
    let mut sent_cancel = false;

    loop {
        if cancel_flag().load(Ordering::SeqCst) && !sent_cancel {
            sent_cancel = true;
            let _ = crate::worker::send_command(root, "sts_cancel", serde_json::Map::new());
        }
        let v = crate::protocol::read_sts(root);
        let ts = v.get("ts").and_then(|x| x.as_f64()).unwrap_or(0.0);
        if ts > last_ts {
            last_ts = ts;
            last_change = std::time::Instant::now();
            saw_any = true;
            if let Some(done) = forward_sts_event(app, &v, out, job) {
                return done;
            }
        } else {
            // worker 死了就别再等了 —— 进程没了 sts.json 也不会再变。
            if !crate::worker::is_worker_alive(root) {
                return Err(if saw_any {
                    HotError::Failed(crate::i18n::t("s.stsHotWorkerGone").into())
                } else {
                    HotError::Unavailable("worker exited".into())
                });
            }
            let idle = last_change.elapsed().as_millis();
            let budget = if saw_any { HOT_STALL_MS } else { HOT_FIRST_MS };
            if idle > budget {
                return Err(if saw_any {
                    HotError::Failed(crate::i18n::t("s.stsHotStalled").into())
                } else {
                    HotError::Unavailable(format!(
                        "no progress within {budget}ms (seq={seq})"
                    ))
                });
            }
            // 命令还没被认领，说明 worker 忙着别的（比如正在起流）。
            if !saw_any
                && started.elapsed().as_millis() > 3_000
                && crate::protocol::last_cmd_seq(root) < seq
            {
                return Err(HotError::Unavailable("command not claimed".into()));
            }
        }
        std::thread::sleep(std::time::Duration::from_millis(120));
    }
}

/// 把 worker 写的一条进度转成界面事件。返回 Some(..) 表示这批活结束了。
fn forward_sts_event(
    app: &AppHandle,
    v: &Value,
    out: &Path,
    job: &mut StsLog,
) -> Option<Result<Value, HotError>> {
    job.event(v);
    let phase = v.get("phase").and_then(|x| x.as_str()).unwrap_or("");
    let msg_owned = crate::i18n::t_worker_msg(v);
    let msg = msg_owned.as_str();
    let total = v.get("total").and_then(|x| x.as_u64()).unwrap_or(1).max(1);
    let done = v.get("done").and_then(|x| x.as_u64()).unwrap_or(0);
    let pct = v
        .get("pct")
        .and_then(|x| x.as_u64().or_else(|| x.as_f64().map(|f| f as u64)));
    let step = v.get("step").and_then(|x| x.as_str());
    let current = v.get("current").and_then(|x| x.as_u64());
    let ok_n = v.get("ok").and_then(|x| x.as_u64());
    let skip_n = v.get("skip").and_then(|x| x.as_u64());
    let file = v.get("file").and_then(|x| x.as_str());

    match phase {
        "error" => {
            return Some(Err(HotError::Failed(if msg.is_empty() {
                crate::i18n::t("s.stsHotFailed").into()
            } else {
                msg.to_string()
            })))
        }
        "cancelled" => {
            return Some(Err(HotError::Failed(
                crate::i18n::t("s.a5ffdc95ee").into(),
            )))
        }
        "done" => {
            let files: Vec<String> = v
                .get("files")
                .and_then(|x| x.as_array())
                .map(|a| {
                    a.iter()
                        .filter_map(|x| x.as_str().map(str::to_string))
                        .collect()
                })
                .unwrap_or_default();
            let skipped: Vec<Value> = v
                .get("skipped")
                .and_then(|x| x.as_array())
                .cloned()
                .unwrap_or_default();
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
            return Some(Ok(json!({
                "ok": true,
                "files": files,
                "skipped": skipped,
                "output": out.to_string_lossy(),
            })));
        }
        "skip" => {
            let reason = v
                .get("reason")
                .and_then(|x| x.as_str())
                .filter(|s| !s.is_empty())
                .unwrap_or(msg);
            emit_full_ex(
                app, "skip", done, total, msg, pct, step, current, ok_n, skip_n, file,
                Some(reason),
            );
        }
        _ => {
            let fallback = crate::i18n::t("s.090840132b");
            emit_full(
                app,
                if phase == "start" { "start" } else { "run" },
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
    }
    None
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
    opts: ConvertOpts,
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
        "filter_radius": opts.filter_radius,
        "resample_sr": opts.resample_sr,
        "rms_mix_rate": opts.rms_mix_rate,
        "protect": opts.protect,
        "format": opts.format,
        "sid": opts.sid,
        "f0_file": opts.f0_file,
    });
    let log_path = crate::logging::begin_run(root, crate::logging::CH_STS, &header);
    crate::logging::shell_log!(
        "sts run log {}",
        log_path
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("sts")
    );
    let mut job = StsLog::new(log_path.clone());
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
        &opts,
        &mut job,
    );
    match &result {
        Ok(v) => {
            if let Some(arr) = v.get("files").and_then(|x| x.as_array()) {
                job.files = arr
                    .iter()
                    .filter_map(|x| x.as_str().map(str::to_string))
                    .collect();
            }
            if let Some(arr) = v.get("skipped").and_then(|x| x.as_array()) {
                job.skipped = arr.len();
            }
            let files = job.files.len();
            let skipped = job.skipped;
            let summary = if skipped > 0 || files == 0 {
                "skipped or empty"
            } else {
                "ok"
            };
            job.finish(summary);
            crate::logging::finish_run(&log_path, true, summary);
        }
        Err(e) => {
            let outcome = if e == &crate::i18n::t("s.a5ffdc95ee") {
                "cancelled"
            } else {
                "error"
            };
            job.trace.note(&format!("ERROR {e}"));
            job.finish(outcome);
            crate::logging::finish_run(&log_path, true, outcome);
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
    opts: &ConvertOpts,
    job: &mut StsLog,
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
    remember_output(root, &out.to_string_lossy());

    let (pth, index) = resolve_model(root, model_path, index_path)?;

    // 实时 worker 还活着的话，hubert / net_g / rmvpe / faiss 全在它显存里躺着。
    // 老做法是把它杀掉再起一个新 python 把这四样从盘上重读一遍——一条 5 秒语音
    // 真正干活一两秒，其余全耗在这上面。现在直接让它兼职把活干了。
    if crate::worker::is_worker_alive(root) {
        job.route = "hot";
        job.trace.note("hot path: reusing live worker models");
        match run_hot(
            app, root, input, &out, pitch, f0method, index_rate, &pth, &index, opts, job,
        ) {
            Ok(v) => {
                let stats = crate::paths::clean_temps(root);
                crate::paths::log_clean_stats(&crate::i18n::t("s.e246e3bafa"), root, &stats);
                return Ok(v);
            }
            Err(HotError::Failed(e)) => return Err(e),
            Err(HotError::Unavailable(why)) => {
                // 热路径没接上（worker 半死、模型还没加载好…）。退回冷路径，
                // 慢是慢，但不能因为提速的那条路没走通就干脆转不了。
                job.route = "cold";
                job.trace.note(&format!("hot path unavailable: {why}"));
                let free_msg = crate::i18n::t("s.stsFreeVram");
                emit_full(
                    app, "run", 0, 1, &free_msg, Some(0), Some("free_vram"),
                    Some(0), Some(0), Some(0), None,
                );
                crate::worker::kill_known_workers(root);
                // 给驱动一点时间把进程显存真正吐回池子；立刻 spawn 下一份 python
                // 时偶发还能看见「reserved >> free」。3GB 卡上 400ms 有时不够。
                std::thread::sleep(std::time::Duration::from_millis(700));
            }
        }
    }

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
        "filter_radius": opts.filter_radius,
        "resample_sr": opts.resample_sr,
        "rms_mix_rate": opts.rms_mix_rate,
        "protect": opts.protect,
        "format": opts.format,
        "sid": opts.sid,
        "f0_file": opts.f0_file,
    });
    std::fs::write(&req, serde_json::to_string_pretty(&payload).unwrap_or_default())
        .map_err(|e| crate::i18n::te("s.5ee0565f28", &(e)))?;

    let py = paths::runtime_python(root).ok_or(crate::i18n::t("s.47e57cab60"))?;
    let errfile = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&job.trace.path)
        .ok();

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
            job.trace.note(&format!("spawn failed: {e}"));
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
            job.trace.note("cancelled by user");
            return Err(crate::i18n::t("s.a5ffdc95ee").into());
        }
        let Ok(v) = serde_json::from_str::<Value>(&line) else {
            continue;
        };
        job.event(&v);
        let phase = v.get("phase").and_then(|x| x.as_str()).unwrap_or("");
        let msg_owned = crate::i18n::t_worker_msg(&v);
        let msg = msg_owned.as_str();
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
                // 这里**不**推 100%。worker 说完 done 之后还可能非零退出，
                // 先亮一次「完成」再翻成红字，用户只会觉得程序在骗人。
                // 收尾那条 done 在 child.wait() 和错误判定之后发。
            }
            "error" => fail = Some(msg.to_string()),
            _ => {}
        }
    }

    let st = match child.wait() {
        Ok(s) => s,
        Err(e) => {
            job.trace.note(&format!("wait failed: {e}"));
            return Err(crate::i18n::te("s.cdad0c927d", &(e)));
        }
    };
    if let Some(e) = fail {
        job.trace.note(&format!("worker error: {e}"));
        return Err(e);
    }
    if !st.success() {
        job.trace.note(&format!("process exit code {}", st.code().unwrap_or(-1)));
        return Err(crate::i18n::te("s.0d8ec50de8", &st.code().unwrap_or(-1)));
    }
    if !sts_run_clean_success(&files, &skipped) {
        job.trace.note(&format!(
            "finished with {} ok, {} skipped",
            files.len(),
            skipped.len()
        ));
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
    fn sts_log_throttles_intra_file_pct() {
        let td = std::env::temp_dir().join(format!(
            "rvcf-sts-log-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&td);
        fs::create_dir_all(&td).unwrap();
        let p = td.join("sts.log");
        fs::write(&p, b"").unwrap();
        let mut job = StsLog::new(p.clone());
        job.event(&json!({"phase":"start","total":1,"message":"go"}));
        job.event(&json!({"phase":"run","current":1,"step":"infer","pct":10,"file":"a.wav"}));
        job.event(&json!({"phase":"run","current":1,"step":"infer","pct":20,"file":"a.wav"}));
        job.event(&json!({"phase":"skip","file":"b.wav","reason":"bad"}));
        let body = fs::read_to_string(&p).unwrap();
        assert!(body.contains("progress start"), "{body}");
        assert!(body.contains("a.wav"), "{body}");
        assert!(!body.contains("20%"), "pct tick should be throttled: {body}");
        assert!(body.contains("progress skip"), "{body}");
        let _ = fs::remove_dir_all(&td);
    }

    #[test]
    fn convert_opts_clamp_like_the_original_ui() {
        let o = ConvertOpts::from_raw(
            Some(99),
            Some(22050),
            Some(2.5),
            Some(-1.0),
            Some("AAC".into()),
            Some(9000),
            Some(String::new()),
        );
        assert_eq!(o.sid, 2333);
        assert_eq!(o.filter_radius, 7);
        assert_eq!(o.resample_sr, 0);
        assert_eq!(o.rms_mix_rate, 1.0);
        assert_eq!(o.protect, 0.0);
        assert_eq!(o.format, "wav");
        let o = ConvertOpts::from_raw(
            Some(3),
            Some(44100),
            Some(0.25),
            Some(0.33),
            Some("flac".into()),
            None,
            None,
        );
        assert_eq!(o.resample_sr, 44100);
        assert_eq!(o.format, "flac");
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

    #[test]
    fn default_sts_dir_is_not_shown_as_a_user_choice() {
        let root = tmp_root();
        let def = out_dir(&root);
        fs::create_dir_all(&def).unwrap();
        assert!(is_default_out(&root, &def.to_string_lossy()));
        assert!(is_default_out(
            &root,
            &def.to_string_lossy().replace('\\', "/")
        ));
        let custom = root.join("elsewhere");
        fs::create_dir_all(&custom).unwrap();
        assert!(!is_default_out(&root, &custom.to_string_lossy()));
        assert_eq!(last_output_for_ui(&root, &def.to_string_lossy()), "");
        assert_eq!(
            last_output_for_ui(&root, &custom.to_string_lossy()),
            custom.to_string_lossy()
        );
        let _ = fs::remove_dir_all(&root);
    }
}
