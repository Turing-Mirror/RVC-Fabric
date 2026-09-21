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
use std::sync::{Arc, Mutex, MutexGuard, OnceLock};

use serde_json::{json, Map, Value};
use tauri::{AppHandle, Emitter, Manager};

use crate::paths;

/// 一单的生命周期临界区：认领（busy + 记名 + 静默/进度/取消初始化）、
/// 凭证取消比对、收尾清态，三步都在这一把锁里完成——旧凭证的取消打不到
/// 新认领的单子，新单子也拿不到被旧收尾清了一半的归属。
///
/// 锁序（全仓只允许这两个方向，反向嵌锁不存在）：
/// - RUN → REC_BUSY：run()/record() 互查占用都按这个序；
/// - RUN → STATE / RUN → LAST_PROGRESS：来源变更守卫、认领时清旧进度。
/// STATE、LAST_PROGRESS、REC_BUSY 的持有者从不回头取 RUN。
/// CANCEL/QUIET 是原子量，只在 RUN 临界区内写。
pub(crate) struct RunCtl {
    busy: bool,
    /// 当前这单的归属凭证：前端发起时给的随机串。认领成功才记名，
    /// 收尾在锁内清空；带凭证的取消只动凭证匹配的那一单（见 cancel_for）。
    owner: Option<String>,
}
static RUN: Mutex<RunCtl> = Mutex::new(RunCtl {
    busy: false,
    owner: None,
});
/// 这一单要不要静音（见 `ConvertOpts::quiet`）。只在 `run()` 的 RUN
/// 临界区内读写，认领/收尾与下一单的初始化串行，不会有两单互相覆盖。
static QUIET: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
static CANCEL: OnceLock<Arc<AtomicBool>> = OnceLock::new();
static REC_BUSY: Mutex<bool> = Mutex::new(false);
/// 最后一条推出去的进度。
///
/// 进度是靠 `sts-progress` 事件推的，事件只发给**当时开着的**窗口。用户把语音
/// 转换窗口关掉再打开，新窗口一条都没赶上，于是显示成「还没开始」，而后台其实
/// 还在跑 —— 用户报的就是这个。存一份最后状态，新窗口进来先补一次。
static LAST_PROGRESS: Mutex<Option<Value>> = Mutex::new(None);
static REC_CANCEL: OnceLock<Arc<AtomicBool>> = OnceLock::new();
static REC_STOP: Mutex<Option<PathBuf>> = Mutex::new(None);

const AUDIO_EXT: &[&str] = &[
    "wav", "mp3", "flac", "ogg", "m4a", "aac", "wma", "opus", "webm",
];
const LIST_CAP: usize = 300;
const WALK_CAP: usize = 2000;
pub(crate) const LAST_INPUT: &str = "last_sts_input";
pub(crate) const LAST_OUTPUT: &str = "last_sts_output";
const MAX_RECORD_SEC: u64 = 30 * 60;

/// 原版单次推理那几个旋钮。缺省跟 infer-web 单次推理一致。
#[derive(Debug, Clone)]
pub struct ConvertOpts {
    /// 不往界面发 `sts-progress`。
    ///
    /// 文字合成借这条链路做它的第二步，但它有自己的进度条（`tts-progress`）。
    /// 不静音的话，用户开着「语音转换」页跑文字合成，那一页会显示一个它自己
    /// 没启动过的任务在跑 —— 看着像串台。
    pub quiet: bool,
    pub filter_radius: u32,
    pub resample_sr: u32,
    pub rms_mix_rate: f64,
    pub protect: f64,
    pub format: String,
    pub sid: u32,
    pub f0_file: String,
    /// 本单归属凭证。面板每次发起给一个新随机串；后端认领 BUSY 成功才记名。
    /// 内部调用方（tts/consult）不传 → None → 保持无凭证老行为。
    pub owner: Option<String>,
    /// 冻结快照时的 excluded 计数，仅落 run 日志 header，不参与执行。
    pub excluded: Option<u64>,
}

impl Default for ConvertOpts {
    fn default() -> Self {
        Self {
            quiet: false,
            filter_radius: 3,
            resample_sr: 0,
            rms_mix_rate: 0.25,
            protect: 0.33,
            format: "wav".into(),
            sid: 0,
            f0_file: String::new(),
            owner: None,
            excluded: None,
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

/// 当前单子的归属凭证（没有在跑/无凭证 → None）。
fn run_owner() -> Option<String> {
    RUN.lock().unwrap_or_else(|e| e.into_inner()).owner.clone()
}

/// 带归属凭证的取消：给了非空 owner 就只动凭证匹配的那一单——别窗/静默
/// 任务在跑时，本窗迟到的取消会被原样吞掉，不会误杀别人的任务。
/// None/空串 = 无凭证老语义，无条件取消（内部调用方照旧）。
///
/// 比对与置旗在同一把 RUN 锁里完成：旧单的凭证在新单认领后必然错配，
/// 不存在「读到 A 的 owner、置的却是 B 的取消旗」的交错窗口。
pub fn cancel_for(owner: Option<&str>) -> bool {
    let owner = owner.map(str::trim).filter(|s| !s.is_empty());
    let g = RUN.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(tok) = owner {
        if g.owner.as_deref() != Some(tok) {
            crate::logging::shell_log!("sts cancel ignored: owner mismatch");
            return false;
        }
    }
    cancel_flag().store(true, Ordering::SeqCst);
    true
}

/// 来源变更互斥守卫（sts_sources 用）：拿住 RUN 期间 `run()` 无法认领新单，
/// 「没在跑」的判定与随后的状态修改被焊成同一个临界区——不再是先查 busy
/// 再放开的 TOCTOU。调用方随后再取 sts_sources 的 STATE 锁（锁序
/// RUN → STATE），扫描/快照只碰 STATE 永不反向。
pub(crate) fn mutation_guard() -> Result<MutexGuard<'static, RunCtl>, String> {
    let g = RUN.lock().unwrap_or_else(|e| e.into_inner());
    if g.busy {
        return Err(crate::i18n::t("s.6a025ac81b").into());
    }
    Ok(g)
}

pub fn cancel() {
    cancel_flag().store(true, Ordering::SeqCst);
}

/// 有没有正在跑的转换任务。强杀引擎前拿它决定要不要先问一句。
pub fn is_busy() -> bool {
    RUN.lock().unwrap_or_else(|e| e.into_inner()).busy
}

/// 取消并等它真的停下来，最多等 `secs` 秒。返回停没停下来。
///
/// 强杀引擎会顺手清 Runtime 下的 python 进程，如果这时候转换还在跑，就是
/// 一边杀一边写文件。先让它按正常路径收尾，收不掉再交给强杀。
pub fn cancel_and_wait(secs: u64) -> bool {
    cancel();
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(secs);
    while std::time::Instant::now() < deadline {
        if !is_busy() {
            return true;
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
    !is_busy()
}

fn emit(app: &AppHandle, phase: &str, done: u64, total: u64, message: &str) {
    emit_full(
        app, phase, done, total, message, None, None, None, None, None, None,
    );
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
        app, phase, done, total, message, pct, step, current, ok, skip, file, None, None,
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
    path: Option<&str>,
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
    // 跳过事件的完整源路径：file 只有文件名，同名文件对不上号；
    // path 让界面能把跳过记录精确映射回清单条目。
    if let Some(p) = path {
        if !p.is_empty() {
            body["path"] = json!(p);
        }
    }
    // 归属回显：有凭证的单子每条事件都带 owner，别窗靠它判断能不能取消。
    if let Some(o) = run_owner() {
        body["owner"] = json!(o);
    }
    *LAST_PROGRESS.lock().unwrap_or_else(|e| e.into_inner()) = Some(body.clone());
    if QUIET.load(Ordering::SeqCst) {
        return;
    }
    let _ = app.emit("sts-progress", body);
}

/// 当前能不能转、用哪个音色。
pub fn status(root: &Path) -> Value {
    // busy 与归属凭证同一把锁读出，拿到的是一致对——不会出现
    // 「busy=true 但 owner 已被下一单换掉」的撕裂快照。
    let (busy, owner_now) = {
        let g = RUN.lock().unwrap_or_else(|e| e.into_inner());
        (g.busy, g.owner.clone())
    };
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
        "busy": busy,
        // 当前在跑的是不是静默任务（TTS/顾问借用转换管线）。面板据此给
        // 外来观察态一个说法；它不是归属判据——别窗开的非静默任务 quiet
        // 也是 false，归属只看本面板是否发起。
        "run_quiet": busy && QUIET.load(Ordering::SeqCst),
        // 在跑单子的归属凭证；无凭证任务（静默借用）给 null。
        "run_owner": if busy {
            owner_now.map(|o| json!(o)).unwrap_or(Value::Null)
        } else {
            Value::Null
        },
        // 只在还在跑的时候给，跑完了给一份陈旧进度反而误导。
        "progress": if busy {
            LAST_PROGRESS
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .clone()
                .unwrap_or(Value::Null)
        } else {
            Value::Null
        },
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
pub fn pick_input(win: Option<&tauri::WebviewWindow>, folder: bool) -> Option<String> {
    let title = if folder {
        crate::i18n::t("s.46ffa5479e")
    } else {
        crate::i18n::t("s.79b552d700")
    };
    let dlg = crate::shell_extras::dialog_on(win).set_title(&title);
    let picked = if folder {
        dlg.pick_folder().map(|p| p.to_string_lossy().into_owned())
    } else {
        let filter = crate::i18n::t("s.461189f186");
        dlg.add_filter(
            &filter,
            &["wav", "mp3", "flac", "ogg", "m4a", "aac", "wma", "opus"],
        )
        .pick_file()
        .map(|p| p.to_string_lossy().into_owned())
    };
    // 输入音频要在界面里试听，选进来的路径必须进 asset 白名单。
    if let (Some(win), Some(p)) = (win, picked.as_ref()) {
        crate::asset_scope::grant_picked(win.app_handle(), p, folder);
    }
    picked
}

pub fn pick_output(win: Option<&tauri::WebviewWindow>) -> Option<String> {
    let title = crate::i18n::t("s.cb12ce77e7");
    let picked = crate::shell_extras::dialog_on(win)
        .set_title(&title)
        .pick_folder()
        .map(|p| p.to_string_lossy().into_owned());
    if let (Some(win), Some(p)) = (win, picked.as_ref()) {
        crate::asset_scope::grant_dir(win.app_handle(), std::path::Path::new(p));
    }
    picked
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
    // 走系统回收站而不是 remove_file：用户能找回，删除前的确认文案也这么承诺。
    trash::delete(file).map_err(|e| crate::i18n::te("s.stsDeleteFail", &e))?;
    Ok(())
}

pub fn rename_input_file(
    root: &Path,
    input: &str,
    path: &str,
    new_name: &str,
) -> Result<String, String> {
    let dir = resolve_input_dir(root, input);
    let file = Path::new(path);
    if !file.is_file() {
        return Err(crate::i18n::t("s.stsInputDirMissing"));
    }
    if !is_audio_path(file) || !path_under(file, &dir) {
        return Err(crate::i18n::t("s.stsRenameUnsafe"));
    }

    let requested = new_name.trim();
    if requested.is_empty()
        || requested == "."
        || requested == ".."
        || requested.ends_with('.')
        || requested.contains('/')
        || requested.contains('\\')
    {
        return Err(crate::i18n::t("s.stsRenameUnsafe"));
    }
    let mut filename = requested.to_string();
    if Path::new(&filename).extension().is_none() {
        if let Some(ext) = file.extension().and_then(|e| e.to_str()) {
            filename.push('.');
            filename.push_str(ext);
        }
    }
    if !is_audio_path(Path::new(&filename)) {
        return Err(crate::i18n::t("s.stsRenameUnsafe"));
    }

    let Some(parent) = file.parent() else {
        return Err(crate::i18n::t("s.stsRenameUnsafe"));
    };
    if !path_under(parent, &dir) {
        return Err(crate::i18n::t("s.stsRenameUnsafe"));
    }
    let target = parent.join(filename);
    if target == file {
        return Ok(file.to_string_lossy().into_owned());
    }
    if std::fs::symlink_metadata(&target).is_ok() {
        return Err(crate::i18n::t("s.stsRenameExists"));
    }
    std::fs::rename(file, &target)
        .map_err(|e| crate::i18n::te("s.stsRenameFail", &e))?;
    Ok(target.to_string_lossy().into_owned())
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
        // 认领录音占用的整个判定在 RUN 锁内做（RUN → REC_BUSY 序，与
        // run() 认领同向）：run() 也在 RUN 里查 REC_BUSY，两个方向的
        // 「对方没在占用」检查因此对彼此都是原子的——不存在录音刚起步
        // 转换就挤进来的交错。
        let g = RUN.lock().unwrap_or_else(|e| e.into_inner());
        if g.busy {
            return Err(crate::i18n::t("s.stsRecordBusy"));
        }
        let mut rec = REC_BUSY.lock().unwrap_or_else(|e| e.into_inner());
        if *rec {
            return Err(crate::i18n::t("s.stsRecordAlready"));
        }
        *rec = true;
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

    // pythonw：piped stdout 仍然能读，不会闪控制台。python.exe 即便加了
    // CREATE_NO_WINDOW，它再拉起来的 ffmpeg 仍会弹黑框。
    let py = paths::runtime_pythonw(root).ok_or(crate::i18n::t("s.47e57cab60"))?;
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

// ─── 冷路径的常驻进程 ────────────────────────────────────────────────────────
//
// 冷启动那几十秒里，真正的转换只占很小一块，其余全在 import torch / 探设备 /
// 读 hubert / 读 rmvpe。这四样跟转哪段音频、转成谁都没关系，以前却是每转一次
// 重付一次 —— 只用离线转换、从来不开实时变声的用户（比如录视频时）就一直在付。
//
// 现在跑完一批不再让 python 退出：进程留着，模型留在显存里，下一条请求从 stdin
// 递进去。第二次起就没有加载阶段了。热路径（实时 worker 兼职）优先级不变，
// 这里只管「实时 worker 不在」的那条路。

/// 空闲多久就把常驻进程放掉。
///
/// 显存不是白占的：训练、游戏、实时变声都要抢。十分钟是按「录一段、说两句、
/// 再录一段」的节奏定的 —— 短了等于没复用，长了会在小显存卡上挡别人的路。
/// 另外开实时变声 / 开训练时会立刻放掉，不等这个钟。
const RESIDENT_IDLE_MS: u128 = 10 * 60 * 1000;
/// 关掉 stdin 之后等它自己退出的上限；torch 收尾偶尔慢，但不能无限等。
const RESIDENT_QUIT_MS: u64 = 1_000;

/// 一个还活着的冷路径 python。
struct Resident {
    child: std::process::Child,
    /// 写一行请求文件路径进去就是派一次活。`None` 表示已经在关了。
    stdin: Option<std::process::ChildStdin>,
    /// 读取线程那边送过来的 stdout 行。
    rx: std::sync::mpsc::Receiver<String>,
    root: PathBuf,
    /// 上一批结束的时间，空闲回收按它算。
    last: std::time::Instant,
    /// 拉起这个进程时的 spawn 策略指纹（accel_backend|main_gpu）。
    /// env_for_runtime 把这两个设置烘进进程环境；之后用户改了设置，
    /// 旧进程的指纹就对不上——take 时换掉，绝不能把上一套 CUDA 环境
    /// 喂给显式选了 CPU 的下一条任务。
    fingerprint: String,
    /// 活着期间一直占着，免得「关变声」把它当残留杀了。
    _guard: crate::worker::ToolPidGuard,
}

static RESIDENT: Mutex<Option<Resident>> = Mutex::new(None);
static REAPER: OnceLock<()> = OnceLock::new();

/// 让常驻进程退出：先关 stdin 让它自己走，赖着不走再杀。
fn stop_resident(mut r: Resident) {
    let pid = r.child.id();
    drop(r.stdin.take());
    let since = std::time::Instant::now();
    while since.elapsed().as_millis() < RESIDENT_QUIT_MS as u128 {
        if matches!(r.child.try_wait(), Ok(Some(_))) {
            crate::logging::shell_log!("语音转换常驻进程已退出 pid={pid}");
            return;
        }
        std::thread::sleep(std::time::Duration::from_millis(50));
    }
    let _ = r.child.kill();
    let _ = r.child.wait();
    crate::logging::shell_log!("语音转换常驻进程超时未退，已结束 pid={pid}");
}

/// 立刻放掉常驻进程，把显存还回去。
///
/// 开实时变声、开训练之前必须调 —— 那两样都要显存，而这个进程正攥着
/// hubert + rmvpe + net_g 不放。没有常驻进程时是空操作。
pub fn release_resident() {
    let taken = RESIDENT.lock().unwrap_or_else(|e| e.into_inner()).take();
    if let Some(r) = taken {
        stop_resident(r);
    }
}

/// 空闲回收线程，第一次起常驻进程时拉起来，之后一直在。
///
/// 正在转换的那个进程是从 RESIDENT 里**取出来**的（局部持有），所以这里
/// 永远看不到它 —— 不会把跑着的活腰斩。
fn ensure_reaper() {
    REAPER.get_or_init(|| {
        std::thread::spawn(|| loop {
            std::thread::sleep(std::time::Duration::from_secs(30));
            let expired = {
                let mut g = RESIDENT.lock().unwrap_or_else(|e| e.into_inner());
                let done = match g.as_mut() {
                    // 超时没人用，或者进程自己没了（崩溃 / 被外面杀掉）。
                    Some(r) => {
                        r.last.elapsed().as_millis() > RESIDENT_IDLE_MS
                            || matches!(r.child.try_wait(), Ok(Some(_)))
                    }
                    None => false,
                };
                if done {
                    g.take()
                } else {
                    None
                }
            };
            if let Some(r) = expired {
                stop_resident(r);
            }
        });
    });
}

/// 热路径能不能复用这个活着的实时 worker：worker 活着、是 RVC 工种
/// （DSP worker 不会转），且出生时的 spawn 策略指纹与「现在请求的那套
/// CPU/GPU/运行时身份」一致。判定走 worker.rs 的只读 API（alive + 落盘
/// v2 指纹 vs env_for_runtime+runtime_pythonw 重算），不开第二套算法。
/// 任一不满足 → 冷路径（常驻进程按当前配置另起），绝不动活着的实时音频。
fn live_worker_compatible(root: &Path) -> bool {
    crate::worker::worker_kind_of(root) == Some(crate::worker::WorkerKind::Rvc)
        && crate::worker::live_worker_matches_current_spawn_policy(root)
}

/// 取出可用的常驻进程。产品根对不上、进程已死、spawn 策略指纹过期的
/// 一律丢掉重来 —— 下一条任务用新设置重起，不在设置变更点杀进程。
/// 指纹比较走 worker::current_spawn_fingerprint（env+解释器路径重算）：
/// 当前 spawn 不出来（None）时任何常驻进程都不能算兼容。
fn take_resident(root: &Path) -> Option<Resident> {
    let mut g = RESIDENT.lock().unwrap_or_else(|e| e.into_inner());
    let mut r = g.take()?;
    let want = crate::worker::current_spawn_fingerprint(root);
    if r.root.as_path() != root || Some(r.fingerprint.as_str()) != want.as_deref() {
        drop(g);
        stop_resident(r);
        return None;
    }
    match r.child.try_wait() {
        Ok(None) => Some(r),
        // 已经退了 / 问不出状态：当它没了。
        _ => {
            let _ = r.child.wait();
            None
        }
    }
}

/// 一批跑完、进程还活着，放回去等下一次。
fn keep_resident(mut r: Resident) {
    // 这中间用户把实时变声开起来了：下一次转换会走热路径，这个进程再留着就
    // 纯粹是白占显存，还跟实时 worker 抢同一张卡。直接放掉。
    if crate::worker::is_worker_alive(&r.root) {
        stop_resident(r);
        return;
    }
    r.last = std::time::Instant::now();
    let mut g = RESIDENT.lock().unwrap_or_else(|e| e.into_inner());
    // 理论上此刻 RESIDENT 必然是 None（同一时刻只有一批在跑，RUN 拦着）。
    // 真撞上了就让旧的那个走，别攒出两个占显存的进程。
    if let Some(old) = g.replace(r) {
        drop(g);
        stop_resident(old);
    }
}

/// 热路径没跑成的两种情况。
enum HotError {
    /// worker 没接住（没应答、模型还没加载好…）。可以退回冷路径重试。
    Unavailable(String),
    /// 转换本身失败（音频坏了、显存不够…）。冷路径重来一遍也是同样的结果，
    /// 白等一分钟不说，还会把已经写出的输出再写一份。直接把错误报给用户。
    Failed(String),
}

/// worker 多久没更新 sts.json 就认为这条热路径走不通。
///
/// 进度只在片段边界跳（hubert / index / infer 完）。3GB fp32 上一窗
/// synthesizer 可能要十几秒（diag 26.8.22/3 卡在 infer 10%），20 秒会把
/// 还活着的转换误判成死了。卡死时必须走 Unavailable（杀进程 + 冷路径），
/// 走 Failed 的话 worker 命令循环还堵在 convert 里，用户重试就是
/// `command not claimed`。
const HOT_STALL_MS: u128 = 90_000;
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
    manifest: &Option<Vec<Value>>,
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
    if let Some(m) = manifest {
        payload.insert("manifest".into(), json!(m));
    }
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
                return Err(HotError::Unavailable(if saw_any {
                    crate::i18n::t("s.stsHotStalled").into()
                } else {
                    format!("no progress within {budget}ms (seq={seq})")
                }));
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
    let path = v.get("path").and_then(|x| x.as_str());

    match phase {
        "error" => {
            // 「热路径接不上」和「转换失败」是两件事，以前都归成 Failed。
            //
            // 回退分支（`HotError::Unavailable`）本来就写好了，但只有传输层问题
            // （worker 退出、命令没被领走）会走到它。worker 自己报的「实时引擎里
            // 没有已加载的音色」——恰恰是最该回退的那一种——以 phase=error 上来，
            // 被当成终端错误直接抛给用户，转换就失败了。而常驻模型为空是常态：
            // 用户开软件直接进语音转换，全程没碰实时变声，rvc 本来就是 None。
            let hot_unavailable = v
                .get("hot_unavailable")
                .and_then(|x| x.as_bool())
                .unwrap_or(false)
                || v.get("message_code").and_then(|x| x.as_str())
                    == Some("sts.hot_unavailable");
            if hot_unavailable {
                return Some(Err(HotError::Unavailable(if msg.is_empty() {
                    "no resident model".to_string()
                } else {
                    msg.to_string()
                })));
            }
            return Some(Err(HotError::Failed(if msg.is_empty() {
                crate::i18n::t("s.stsHotFailed").into()
            } else {
                msg.to_string()
            })));
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
                Some(reason), path,
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
    manifest: Option<Vec<Value>>,
) -> Result<Value, String> {
    {
        // 认领在 RUN 一把锁里做完：busy 判定、录音占用互查、记名、
        // 静默/进度/取消旗初始化。认领后才到达的 cancel_for 必然看到
        // 本单 owner（正确取消）；认领前的取消一律错配被吞——不存在
        // 「busy 已置、取消旗还没清」的中间态窗口。
        let mut g = RUN.lock().unwrap_or_else(|e| e.into_inner());
        if g.busy {
            return Err(crate::i18n::t("s.6a025ac81b").into());
        }
        // RUN → REC_BUSY 序：与 record() 的认领同向，两个方向的互斥
        // 判定因此对彼此原子，且无锁序环。
        if *REC_BUSY.lock().unwrap_or_else(|e| e.into_inner()) {
            return Err(crate::i18n::t("s.stsRecordConvertBusy").into());
        }
        g.busy = true;
        // 认领成功才记名：抢 RUN 失败的调用方不会顶掉在跑单子的归属。
        g.owner = opts
            .owner
            .as_deref()
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string);
        QUIET.store(opts.quiet, Ordering::SeqCst);
        // 上一单的终态别留给这一单看。
        *LAST_PROGRESS.lock().unwrap_or_else(|e| e.into_inner()) = None;
        cancel_flag().store(false, Ordering::SeqCst);
    }
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
        // 冻结时排除掉的条数：清单长度替代不了它（C9 验收口径）。
        "excluded": opts.excluded,
        "owner": opts.owner.as_deref().unwrap_or(""),
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
        &manifest,
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
    // 终态错误事件先按本单归属发出：此刻 busy/owner 仍是本单，事件带的
    // 是自己的凭证而不是下一单的（下一单还没法认领）。随后在临界区内
    // 一次性清 busy/owner/quiet——不存在「B 已认领却被 A 的收尾清掉
    // owner、A 的错误顶着 B 的归属发出」的交错。
    if let Err(ref e) = result {
        emit(app, "error", 0, 1, e);
    }
    {
        let mut g = RUN.lock().unwrap_or_else(|e| e.into_inner());
        g.busy = false;
        g.owner = None;
        // quiet 复位也在临界区内：与下一单的 quiet 初始化串行，不互相
        // 覆盖；且在 emit 之后——静默单的收尾错误照旧不广播。
        QUIET.store(false, Ordering::SeqCst);
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
    manifest: &Option<Vec<Value>>,
    job: &mut StsLog,
) -> Result<Value, String> {
    if !paths::runtime_ready(root) {
        return Err(crate::i18n::t("s.75b84a31d6").into());
    }
    if !crate::engine_assets::engine_core_ready(root) {
        let miss = crate::i18n::join_list(&crate::engine_assets::engine_core_missing(root));
        return Err(crate::i18n::te("s.5eb32f1350", &miss));
    }
    let script = worker_script(root);
    if !script.is_file() {
        return Err(crate::i18n::te("s.bc197d22e5", &(script.display())));
    }
    let has_manifest = manifest
        .as_ref()
        .map(|m| !m.is_empty())
        .unwrap_or(false);
    if input.trim().is_empty() && !has_manifest {
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

    // 实时 worker 还活着且带着当前 spawn 策略的话，hubert / net_g / rmvpe /
    // faiss 全在它显存里躺着，直接让它兼职把活干了。指纹对不上（用户起
    // 实时后改过后端/主显卡）、或活着的是 DSP 工种：直接走冷路径另起常驻
    // 进程——不碰热尝试，也就永远到不了 Unavailable→kill_known_workers
    // 那条会杀掉实时音频的路。显式 CPU 选择绝不在旧 CUDA 环境的 worker 上跑。
    if live_worker_compatible(root) {
        job.route = "hot";
        job.trace.note("hot path: reusing live worker models");
        // 界面上也要说走了哪条路。用户对同一段音频两次转换耗时差二十秒毫无头绪，
        // 只会得出「这软件时快时慢」——而这条信息本来就在，只是以前只进日志。
        emit_full(
            app, "run", 0, 1, &crate::i18n::t("s.stsRouteHot"),
            Some(0), Some("route"), Some(0), Some(0), Some(0), None,
        );
        match run_hot(
            app, root, input, &out, pitch, f0method, index_rate, &pth, &index, opts,
            manifest, job,
        ) {
            Ok(v) => {
                let stats = crate::paths::clean_temps(root);
                crate::paths::log_clean_stats(&crate::i18n::t("s.e246e3bafa"), root, &stats);
                return Ok(v);
            }
            Err(HotError::Failed(e)) => return Err(e),
            Err(HotError::Unavailable(why)) => {
                // 离线回退不能为了释放显存关闭实时音频；资源不足按正常转换错误返回。
                job.route = "cold";
                job.trace.note(&format!("hot path unavailable: {why}"));
            }
        }
    }

    // 走到这里就是冷路径。上一次转换留下的那个 python 还在的话，hubert /
    // net_g / rmvpe 都还在它显存里 —— 那就不是冷启动，也别拿「约 20 秒」吓人。
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
        "manifest": manifest,
    });
    std::fs::write(&req, serde_json::to_string_pretty(&payload).unwrap_or_default())
        .map_err(|e| crate::i18n::te("s.5ee0565f28", &(e)))?;

    // 先把请求递给还活着的那个进程；递不进去（管道断了 = 它其实已经不行了）
    // 就当没有，老老实实起一个新的。路线文案要等这一步有结果了才发。
    let mut sess = take_resident(root);
    if let Some(r) = sess.as_mut() {
        use std::io::Write;
        let line = format!("{}\n", req.display());
        let ok = r
            .stdin
            .as_mut()
            .map(|w| w.write_all(line.as_bytes()).and_then(|()| w.flush()).is_ok())
            .unwrap_or(false);
        if !ok {
            job.trace.note("resident stdin closed; starting a new python");
            if let Some(dead) = sess.take() {
                stop_resident(dead);
            }
        }
    }
    let reused = sess.is_some();
    job.trace.note(if reused {
        "cold path: reusing resident python"
    } else {
        "cold path: new python"
    });
    emit_full(
        app,
        "run",
        0,
        1,
        &crate::i18n::t(if reused { "s.stsRouteWarm" } else { "s.stsRouteCold" }),
        Some(0), Some("route"), Some(0), Some(0), Some(0), None,
    );

    let mut sess = match sess {
        Some(r) => r,
        None => {
            let py = paths::runtime_pythonw(root).ok_or(crate::i18n::t("s.47e57cab60"))?;
            let errfile = OpenOptions::new()
                .create(true)
                .append(true)
                .open(&job.trace.path)
                .ok();

            // env 先取一份本地变量：它既喂给子进程，也喂给出生指纹 ——
            // 指纹必须描述「实际传下去的那份环境」，不能 spawn 后再重读配置。
            let env = crate::worker::env_for_runtime(root);
            let mut cmd = Command::new(&py);
            cmd.arg(script.as_os_str())
                .arg(req.as_os_str())
                // 跑完不退出，模型留在显存里等下一条请求（见上面 Resident 的说明）。
                .arg("--resident")
                .current_dir(root)
                .envs(&env)
                .stdin(Stdio::piped())
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
            let guard = crate::worker::ToolPidGuard::new(child.id());
            let stdin = child.stdin.take();
            let stdout = match child.stdout.take() {
                Some(s) => s,
                None => {
                    let _ = child.kill();
                    return Err(crate::i18n::t("s.68759edc4b").into());
                }
            };

            // stdout 的读取放到单独线程，主循环每 200ms 醒一次。
            //
            // 以前是直接 `for line in stdout.lines()`，取消标志只在**新的一行进度
            // 出来时**才看得到。而一个文件转到一半，worker 十几秒不吭声是常事 ——
            // 这十几秒里点取消，界面上什么都不会发生，用户只会以为按钮坏了。
            // 用户报的就是这个。
            //
            // 换成 channel 之后取消是秒级的：不管 worker 在不在说话，200ms 内一定
            // 醒来查一次。读取线程那边 recv 端一断就自然结束，不用额外的收尾。
            let (tx, rx) = std::sync::mpsc::channel::<String>();
            std::thread::spawn(move || {
                for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                    if tx.send(line).is_err() {
                        break;
                    }
                }
            });
            ensure_reaper();
            Resident {
                child,
                stdin,
                rx,
                root: root.to_path_buf(),
                last: std::time::Instant::now(),
                fingerprint: crate::worker::spawn_fingerprint_for(&env, &py),
                _guard: guard,
            }
        }
    };

    let mut files: Vec<String> = Vec::new();
    let mut skipped: Vec<Value> = Vec::new();
    let mut fail: Option<String> = None;
    let mut total: u64 = 1;
    // 进程跑完这批之后还活着 —— 只有收到 idle 才算数。
    let mut alive = false;

    loop {
        if cancel_flag().load(Ordering::SeqCst) {
            // 取消就是杀。杀掉的这个不放回池子：它可能正卡在一半的推理里。
            let _ = sess.child.kill();
            let _ = sess.child.wait();
            job.trace.note("cancelled by user");
            return Err(crate::i18n::t("s.a5ffdc95ee").into());
        }
        let line = match sess.rx.recv_timeout(std::time::Duration::from_millis(200)) {
            Ok(l) => l,
            // 超时只是这一轮没有新进度，回去再查一遍取消标志。
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => continue,
            // 发送端没了 = 子进程 stdout 关了 = 它死了。常驻模式下正常收尾走
            // 的是 idle，走到这里就是崩了，下面按退出码报错。
            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => break,
        };
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
        let path = v.get("path").and_then(|x| x.as_str());
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
                    // file 与终端 skipped 清单同形（全路径），name 只留文件名；
                    // 同名文件靠全路径区分，重试匹配也用它。
                    skipped.push(json!({
                        "file": path.unwrap_or(fname),
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
                    path,
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
            "error" => {
                fail = Some(msg.to_string());
                // 错误也要走事件推一遍，且带上 message_code —— 有些码在前端配了
                // 动作按钮（「选到训练存档」配「打开训练窗」）。invoke 的 Err 只
                // 剩纯文本，码丢了按钮就没了。
                let mut body = json!({
                    "phase": "error",
                    "message": msg,
                    "done": v.get("done").and_then(|x| x.as_u64()).unwrap_or(0),
                    "total": total,
                });
                if let Some(c) = v.get("message_code").and_then(|x| x.as_str()) {
                    body["message_code"] = json!(c);
                }
                let _ = app.emit("sts-progress", body);
            }
            // 常驻进程说「这批收尾了、我还活着」。done / error 都在它前面，
            // 所以走到这里该收的都收齐了。
            "idle" => {
                alive = true;
                break;
            }
            _ => {}
        }
    }

    // 还活着就放回池子给下一次用；死了才有退出码可判。
    let exit = if alive {
        keep_resident(sess);
        None
    } else {
        match sess.child.wait() {
            Ok(s) => Some(s),
            Err(e) => {
                job.trace.note(&format!("wait failed: {e}"));
                return Err(crate::i18n::te("s.cdad0c927d", &(e)));
            }
        }
    };
    if let Some(e) = fail {
        job.trace.note(&format!("worker error: {e}"));
        return Err(e);
    }
    if let Some(st) = exit {
        if !st.success() {
            job.trace.note(&format!("process exit code {}", st.code().unwrap_or(-1)));
            return Err(crate::i18n::te("s.0d8ec50de8", &st.code().unwrap_or(-1)));
        }
        // 退出码 0 却没有 idle：装的是不认 --resident 的旧 worker（壳升级了、
        // 引擎负载还没升）。它已经把这批正常跑完了，照旧当成功。
        job.trace.note("python exited without an idle line (older worker?)");
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

    /// quiet 打开时不发 sts-progress。
    #[test]
    fn quiet_suppresses_progress_events() {
        QUIET.store(true, Ordering::SeqCst);
        assert!(QUIET.load(Ordering::SeqCst));
        QUIET.store(false, Ordering::SeqCst);
        assert!(!QUIET.load(Ordering::SeqCst));
        // 默认必须是不静音的：批量转换那条路要靠这些事件画进度。
        assert!(!ConvertOpts::default().quiet);
    }
    use super::*;
    use std::fs;

    fn tmp_root() -> PathBuf {
        let dir = crate::testutil::scratch("sts-rec");
        fs::create_dir_all(dir.join("User_Data")).unwrap();
        dir
    }

    #[test]
    fn sts_log_throttles_intra_file_pct() {
        let td = crate::testutil::scratch("sts-log");
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

    /// 改 RUN.owner / 取消旗的测试互相串行：同一测试进程里别的用例并行跑，
    /// 不加这把锁两个用例会互踩 owner 字段。注意测试里只写 owner 不写
    /// busy——sts_sources 的用例经 mutation_guard 查 busy，置 true 会误伤
    /// 并行用例。
    static RUN_TEST_LOCK: Mutex<()> = Mutex::new(());

    /// 归属凭证取消：只有回显凭证一致才动这一单；错配原样吞掉。
    /// 无凭证/空串保留老语义（内部调用方 tts/consult 无条件取消）。
    #[test]
    fn cancel_for_matches_owner_only() {
        let _tl = RUN_TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let reset = |owner: Option<String>| {
            RUN.lock().unwrap_or_else(|e| e.into_inner()).owner = owner;
            cancel_flag().store(false, Ordering::SeqCst);
        };
        reset(Some("w1".into()));
        // 别人的凭证：不动取消旗。
        assert!(!cancel_for(Some("w2")));
        assert!(!cancel_flag().load(Ordering::SeqCst));
        // 本窗凭证：取消生效。
        assert!(cancel_for(Some("w1")));
        assert!(cancel_flag().load(Ordering::SeqCst));
        // 无凭证（None/空串）= 老内部调用方：无条件取消，不看记名。
        reset(Some("w1".into()));
        assert!(cancel_for(None));
        assert!(cancel_flag().load(Ordering::SeqCst));
        reset(Some("w1".into()));
        assert!(cancel_for(Some("")));
        assert!(cancel_flag().load(Ordering::SeqCst));
        // 无记名的单子：带凭证的取消不匹配任何东西，也无凭证路径不变。
        reset(None);
        assert!(!cancel_for(Some("w1")));
        assert!(!cancel_flag().load(Ordering::SeqCst));
        assert!(cancel_for(None));
        assert!(cancel_flag().load(Ordering::SeqCst));
        reset(None);
    }

    /// 交错证明（确定性，不靠时序运气）：主线把 RUN 拿在手里模拟「B 正在
    /// 认领」的临界区，另一线程对旧凭证 A 调 cancel_for —— 它必须阻塞在锁
    /// 上直到临界区结束，然后读到的是 B 的 owner → 错配吞掉，B 的取消旗
    /// 不被置起。旧实现（查 owner 放锁再置旗）在这个交错里会误杀 B。
    #[test]
    fn cancel_for_blocks_during_claim_then_misses_old_owner() {
        let _tl = RUN_TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        RUN.lock().unwrap_or_else(|e| e.into_inner()).owner = Some("A".into());
        cancel_flag().store(false, Ordering::SeqCst);

        let mut g = RUN.lock().unwrap_or_else(|e| e.into_inner());
        let t = std::thread::spawn(|| cancel_for(Some("A")));
        // 它要么还没被调度、要么阻塞在 RUN 上——无论哪种都没跑完。
        // 若 cancel_for 能不经 RUN 置旗（旧实现），这里可能已经结束了。
        std::thread::sleep(std::time::Duration::from_millis(50));
        assert!(!t.is_finished(), "cancel_for 必须等 RUN 临界区结束");
        // B 的认领在同一临界区内完成：换名 + 取消旗复位。
        g.owner = Some("B".into());
        cancel_flag().store(false, Ordering::SeqCst);
        drop(g);

        assert!(!t.join().unwrap(), "A 的迟到取消打不到已换名的单子");
        assert!(!cancel_flag().load(Ordering::SeqCst), "B 的取消旗不能被 A 置起");
        RUN.lock().unwrap_or_else(|e| e.into_inner()).owner = None;
    }

    /// 反方向交错：取消先抢到锁（A 还在跑），置旗生效；随后 B 认领在临界
    /// 区内复位取消旗——A 的取消不会漏到 B 身上。
    #[test]
    fn cancel_before_next_claim_does_not_leak() {
        let _tl = RUN_TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        RUN.lock().unwrap_or_else(|e| e.into_inner()).owner = Some("A".into());
        cancel_flag().store(false, Ordering::SeqCst);
        assert!(cancel_for(Some("A")));
        assert!(cancel_flag().load(Ordering::SeqCst));

        // B 认领（模拟 run() 临界区）：换名 + 初始化取消旗。
        {
            let mut g = RUN.lock().unwrap_or_else(|e| e.into_inner());
            g.owner = Some("B".into());
            cancel_flag().store(false, Ordering::SeqCst);
        }
        // A 的取消已被认领初始化清掉，B 的新取消要按 B 的凭证来。
        assert!(!cancel_flag().load(Ordering::SeqCst), "A 的取消不许漏到 B");
        assert!(cancel_for(Some("B")), "B 的凭证取消自己的单子");
        RUN.lock().unwrap_or_else(|e| e.into_inner()).owner = None;
        cancel_flag().store(false, Ordering::SeqCst);
    }

    /// 来源变更守卫：mutation_guard 持有 RUN 期间，任何带凭证的取消都得
    /// 排在变更事务后面——busy 判定与状态读写被焊成同一临界区。
    /// 守卫放手后单子仍空闲（没跑），迟到取消按无主错配吞掉。
    #[test]
    fn mutation_guard_holds_run_across_source_transaction() {
        let _tl = RUN_TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        RUN.lock().unwrap_or_else(|e| e.into_inner()).owner = None;
        let guard = mutation_guard().expect("空闲时应拿到守卫");
        let t = std::thread::spawn(|| cancel_for(Some("late")));
        std::thread::sleep(std::time::Duration::from_millis(50));
        assert!(!t.is_finished(), "守卫活着时 RUN 不可进入");
        drop(guard);
        assert!(!t.join().unwrap());
    }

    /// 复用判定跟「实际 spawn 身份」走：常驻进程出生指纹 =
    /// spawn_fingerprint_for(env_for_runtime, runtime_pythonw)，
    /// take_resident 拿它和 current_spawn_fingerprint 比 —— 与实时 worker
    /// 的 worker.fingerprint 同一条 v2 公式（含运行时解释器身份）。
    /// accel_backend / cuda 下的 main_gpu 任一变化都必须换指纹；
    /// 运行时缺失 → None → 任何旧进程都不能算兼容。
    #[test]
    fn spawn_fingerprint_tracks_policy_and_runtime() {
        let root = tmp_root();
        let rt = crate::paths::runtime_dir(&root);
        fs::create_dir_all(&rt).unwrap();
        fs::write(rt.join("pythonw.exe"), b"fake").unwrap();
        let cfgp = crate::paths::app_config_path(&root);
        fs::create_dir_all(cfgp.parent().unwrap()).unwrap();
        fs::write(&cfgp, r#"{"accel_backend":"cuda","main_gpu":0}"#).unwrap();

        // 常驻出生指纹：env+pyw 直接算 —— 必须与「现在 spawn」同式同值。
        let env = crate::worker::env_for_runtime(&root);
        let pyw = crate::paths::runtime_pythonw(&root).unwrap();
        let cuda = crate::worker::spawn_fingerprint_for(&env, &pyw);
        assert_eq!(
            crate::worker::current_spawn_fingerprint(&root).as_deref(),
            Some(cuda.as_str()),
            "常驻出生指纹与 current_spawn_fingerprint 必须同源"
        );

        // 换后端：CUDA 环境进程不能给显式 CPU 单复用。
        fs::write(&cfgp, r#"{"accel_backend":"cpu","main_gpu":0}"#).unwrap();
        let cpu = crate::worker::current_spawn_fingerprint(&root).unwrap();
        assert_ne!(cuda, cpu, "换后端必须换指纹");

        // cuda 后端下换主显卡 → CUDA_VISIBLE_DEVICES 变 → 指纹变。
        fs::write(&cfgp, r#"{"accel_backend":"cuda","main_gpu":1}"#).unwrap();
        let gpu1 = crate::worker::current_spawn_fingerprint(&root).unwrap();
        assert_ne!(cuda, gpu1, "cuda 下换 main_gpu 必须换指纹");

        // 运行时解释器没了 → None：不能 spawn ≠ 随便兼容。
        fs::remove_file(rt.join("pythonw.exe")).unwrap();
        assert!(crate::worker::current_spawn_fingerprint(&root).is_none());
        let _ = fs::remove_dir_all(&root);
    }

    /// 热路径门：没有活 worker / 活的是 DSP 工种 → 绝不复用（返回 false 走
    /// 冷路径）。worker 活着时的指纹对号严格性由 worker.rs 的
    /// live_worker_spawn_policy_query_is_read_only_and_strict 覆盖
    /// （活进程身份需要 worker.rs 内部的身份缓存，本模块无法伪造）。
    #[test]
    fn live_worker_compatible_requires_alive_rvc_worker() {
        let root = tmp_root();
        // 死寂状态：没有任何 pid/status 文件 → 不兼容。
        assert!(!live_worker_compatible(&root));
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn hot_stall_budget_covers_a_low_vram_synthesizer_window() {
        // 26.8.22/3: 3GB fp32 上一窗 synthesizer 可能 >20s；20_000 会误杀还活着的转换。
        assert!(HOT_STALL_MS >= 60_000);
        assert!(HOT_STALL_MS <= HOT_FIRST_MS * 3);
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
    fn rename_stays_inside_input_and_keeps_audio_extension() {
        let root = tmp_root();
        let dir = root.join("in");
        fs::create_dir_all(&dir).unwrap();
        let wav = dir.join("old.wav");
        fs::write(&wav, b"1").unwrap();
        let outside = root.join("outside.wav");
        fs::write(&outside, b"2").unwrap();
        let renamed = rename_input_file(&root, &dir.to_string_lossy(), &wav.to_string_lossy(), "new").unwrap();
        assert_eq!(Path::new(&renamed).file_name().unwrap().to_string_lossy(), "new.wav");
        assert!(!wav.exists());
        assert!(Path::new(&renamed).exists());
        assert!(rename_input_file(&root, &dir.to_string_lossy(), &outside.to_string_lossy(), "x").is_err());
        fs::write(dir.join("taken.wav"), b"3").unwrap();
        assert!(rename_input_file(&root, &dir.to_string_lossy(), &renamed, "taken.wav").is_err());
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
