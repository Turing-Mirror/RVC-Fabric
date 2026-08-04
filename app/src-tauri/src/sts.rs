//! 离线语音转换（Speech-to-Speech）：音频文件 → 目标音色。
//!
//! 对应官方 RVC WebUI「推理 / 批量推理」。与 `tts.rs`（文字 → SAPI → RVC）
//! 是两条线：STS 输入必须是声音，TTS 输入是文字。界面上同属「语音转换」
//! 工具窗，用分段控件切换。

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

fn cancel_flag() -> Arc<AtomicBool> {
    CANCEL
        .get_or_init(|| Arc::new(AtomicBool::new(false)))
        .clone()
}

fn worker_script(root: &Path) -> PathBuf {
    root.join("tools").join("sts_worker.py")
}

pub fn out_dir(root: &Path) -> PathBuf {
    paths::user_data(root).join("sts")
}

pub fn cancel() {
    cancel_flag().store(true, Ordering::SeqCst);
}

fn emit(app: &AppHandle, phase: &str, done: u64, total: u64, message: &str) {
    let _ = app.emit(
        "sts-progress",
        json!({
            "phase": phase,
            "done": done,
            "total": total.max(1),
            "message": message,
        }),
    );
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
        "busy": *BUSY.lock().unwrap_or_else(|e| e.into_inner()),
    })
}

/// 选输入：`folder=false` 选单个音频，`true` 选文件夹（批量）。
pub fn pick_input(folder: bool) -> Option<String> {
    let dlg = rfd::FileDialog::new().set_title(if folder {
        "选择待转换音频所在文件夹"
    } else {
        "选择待转换的音频"
    });
    if folder {
        dlg.pick_folder().map(|p| p.to_string_lossy().into_owned())
    } else {
        dlg.add_filter(
            "音频",
            &["wav", "mp3", "flac", "ogg", "m4a", "aac", "wma", "opus"],
        )
        .pick_file()
        .map(|p| p.to_string_lossy().into_owned())
    }
}

pub fn pick_output() -> Option<String> {
    rfd::FileDialog::new()
        .set_title("选择输出目录")
        .pick_folder()
        .map(|p| p.to_string_lossy().into_owned())
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
) -> Result<Value, String> {
    {
        let mut g = BUSY.lock().unwrap_or_else(|e| e.into_inner());
        if *g {
            return Err("已经有一个转换任务在跑了".into());
        }
        *g = true;
    }
    cancel_flag().store(false, Ordering::SeqCst);
    let result = run_inner(app, root, input, output, pitch, f0method, index_rate);
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
) -> Result<Value, String> {
    if !paths::runtime_ready(root) {
        return Err("Runtime 未就绪，请先补全运行时".into());
    }
    if !crate::engine_assets::engine_core_ready(root) {
        let miss = crate::engine_assets::engine_core_missing(root).join("、");
        return Err(format!(
            "引擎资源不完整（缺 {miss}）。请先在主界面完成「引擎资源」下载（hubert / rmvpe / ffmpeg）。"
        ));
    }
    let script = worker_script(root);
    if !script.is_file() {
        return Err(format!("找不到转换脚本：{}", script.display()));
    }
    if input.trim().is_empty() {
        return Err("请先选好输入文件或文件夹".into());
    }
    let out = if output.trim().is_empty() {
        out_dir(root)
    } else {
        PathBuf::from(output.trim())
    };
    std::fs::create_dir_all(&out).map_err(|e| format!("建不了输出目录：{e}"))?;

    let cfg = crate::config::read(root);
    let pth = cfg
        .get("pth_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    if pth.is_empty() || !Path::new(&pth).is_file() {
        return Err("还没有选中的音色。先在「首页」或「模型」页选一个。".into());
    }
    let index = cfg
        .get("index_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

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
        .map_err(|e| format!("写请求文件失败：{e}"))?;

    let py = paths::runtime_python(root).ok_or("找不到 Runtime\\python.exe")?;
    let log = paths::logs_dir(root).join("sts.log");
    let _ = std::fs::create_dir_all(paths::logs_dir(root));
    let errfile = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log)
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

    let mut child = cmd.spawn().map_err(|e| format!("起不来转换进程：{e}"))?;
    let stdout = child.stdout.take().ok_or("拿不到转换进程的输出")?;
    let mut files: Vec<String> = Vec::new();
    let mut fail: Option<String> = None;
    let mut total: u64 = 1;

    for line in BufReader::new(stdout).lines().map_while(Result::ok) {
        if cancel_flag().load(Ordering::SeqCst) {
            let _ = child.kill();
            return Err("已取消".into());
        }
        let Ok(v) = serde_json::from_str::<Value>(&line) else {
            continue;
        };
        let phase = v.get("phase").and_then(|x| x.as_str()).unwrap_or("");
        let msg = v.get("message").and_then(|x| x.as_str()).unwrap_or("");
        match phase {
            "start" => {
                total = v.get("total").and_then(|x| x.as_u64()).unwrap_or(1).max(1);
                emit(app, "start", 0, total, if msg.is_empty() { "正在加载音色…" } else { msg });
            }
            "run" => {
                total = v.get("total").and_then(|x| x.as_u64()).unwrap_or(total).max(1);
                let done = v.get("done").and_then(|x| x.as_u64()).unwrap_or(0);
                emit(
                    app,
                    "run",
                    done,
                    total,
                    if msg.is_empty() { "转换中…" } else { msg },
                );
            }
            "done" => {
                if let Some(arr) = v.get("files").and_then(|x| x.as_array()) {
                    files = arr
                        .iter()
                        .filter_map(|x| x.as_str().map(str::to_string))
                        .collect();
                }
            }
            "error" => fail = Some(msg.to_string()),
            _ => {}
        }
    }

    let st = child.wait().map_err(|e| format!("等转换进程失败：{e}"))?;
    if let Some(e) = fail {
        return Err(e);
    }
    if !st.success() {
        return Err(format!(
            "转换进程异常退出（{}）。详情见 User_Data/logs/sts.log",
            st.code().unwrap_or(-1)
        ));
    }
    emit(app, "done", total, total, "转换完成");
    let stats = crate::paths::clean_temps(root);
    crate::paths::log_clean_stats("语音转换后", root, &stats);
    Ok(json!({
        "ok": true,
        "files": files,
        "output": out.to_string_lossy(),
    }))
}
