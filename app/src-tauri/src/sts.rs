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
        // 实时变声是否还占着显存。面板拿它决定要不要先问一句再开转。
        "worker_alive": crate::worker::is_worker_alive(root),
        "busy": *BUSY.lock().unwrap_or_else(|e| e.into_inner()),
    })
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
            let keep = skipped > 0 || files == 0;
            crate::logging::finish_run(
                &log_path,
                keep,
                if keep {
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
