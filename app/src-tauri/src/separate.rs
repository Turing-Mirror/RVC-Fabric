//! 人声分离（PyMSS）。
//!
//! 和实时 worker 是两码事：这里没有常驻进程、没有音频设备、没有状态机。一次
//! 分离就是「起一个 python，读它 stdout 的进度行，等它退出」。所以不复用
//! `worker.rs` 那套 pid 文件 + status.json 的协议 —— 那套是为「一直活着的
//! 进程」设计的，套在一次性任务上只会多出一堆要清理的残留。
//!
//! 模型权重不进安装包：一个 bs_roformer 就三四百 MB，而大多数用户根本不会用
//! 到分离。和 Runtime 一样按需下载，走同一个下载器和 sha256 校验。

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

use crate::paths;

/// 一次只跑一个：分离很吃显存，两个一起跑基本必爆。
static BUSY: Mutex<bool> = Mutex::new(false);
static CANCEL: OnceLock<Arc<AtomicBool>> = OnceLock::new();

fn cancel_flag() -> Arc<AtomicBool> {
    CANCEL
        .get_or_init(|| Arc::new(AtomicBool::new(false)))
        .clone()
}

/// 权重放安装目录，不放用户主目录 —— PyMSS 默认写 ~/.cache/pymss，
/// 卸载软件不会带走，用户也找不到。
pub fn model_dir(root: &Path) -> PathBuf {
    root.join("assets").join("pymss")
}

fn worker_script(root: &Path) -> PathBuf {
    root.join("tools").join("separate_worker.py")
}

/// PyMSS 拆成 tools/pymss + tools/pymss_core 两半，`pymss` 顶层 import
/// `pymss_core`，缺任意一半都是同样的崩溃。这里只查后半 —— 前半缺了
/// 会在 import 时报错，但报的是另一条链路；后半缺失时给用户能读懂的提示。
fn core_present(root: &Path) -> bool {
    root.join("tools").join("pymss_core").join("__init__.py").is_file()
}

/// 分离能不能用：要 Runtime、要 worker 脚本、要至少一个权重文件。
/// 权重按 PyMSS catalog 的 relpath 摆在子目录里，所以要递归扫；界面下拉框
/// 里列文件名（模型名/别名），PyMSS 解析器自己按名字找到子目录里的那份。
pub fn status(root: &Path) -> Value {
    let dir = model_dir(root);
    let mut models: Vec<String> = Vec::new();
    collect_models(&dir, &mut models);
    models.sort();
    models.dedup();
    json!({
        "runtime_ready": paths::runtime_ready(root),
        "worker_present": worker_script(root).is_file(),
        "core_present": core_present(root),
        "model_dir": dir.to_string_lossy(),
        "models": models,
        "busy": *BUSY.lock().unwrap_or_else(|e| e.into_inner()),
    })
}

fn collect_models(dir: &Path, out: &mut Vec<String>) {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return;
    };
    for e in rd.flatten() {
        let p = e.path();
        if p.is_dir() {
            collect_models(&p, out);
            continue;
        }
        let ok = p
            .extension()
            .and_then(|s| s.to_str())
            .map(|s| s.eq_ignore_ascii_case("ckpt") || s.eq_ignore_ascii_case("pth"))
            .unwrap_or(false);
        if ok {
            if let Some(n) = p.file_name().and_then(|s| s.to_str()) {
                out.push(n.to_string());
            }
        }
    }
}

/// 目录里（含子目录）有没有至少一个权重。防的是「一个都没下」，不是校验
/// 用户选的这一个 —— 具体哪个名字能用由 PyMSS 解析器说了算，它会给出
/// 更准确的错误。
fn any_model_present(dir: &Path) -> bool {
    let mut models: Vec<String> = Vec::new();
    collect_models(dir, &mut models);
    !models.is_empty()
}

pub fn cancel() {
    cancel_flag().store(true, Ordering::SeqCst);
}

fn emit(app: &AppHandle, phase: &str, done: u64, total: u64, message: &str) {
    let _ = app.emit(
        "separate-progress",
        json!({
            "phase": phase,
            "done": done,
            "total": total.max(1),
            "message": message,
        }),
    );
}

/// 跑一次分离。阻塞，调用方负责挪到后台线程。
pub fn run(app: &AppHandle, root: &Path, input: &str, output: &str, model: &str) -> Result<Value, String> {
    {
        let mut g = BUSY.lock().unwrap_or_else(|e| e.into_inner());
        if *g {
            return Err(crate::i18n::t("s.38d4c44c83").into());
        }
        *g = true;
    }
    cancel_flag().store(false, Ordering::SeqCst);
    let log = crate::logging::begin_run(
        root,
        crate::logging::CH_SEPARATE,
        &json!({
            "input": input,
            "output": output,
            "model": model,
        }),
    );
    crate::logging::shell_log!(
        "separate run log {}",
        log.file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("separate")
    );
    let result = run_inner(app, root, input, output, model, &log);
    match &result {
        Ok(_) => crate::logging::finish_run(&log, true, "ok"),
        Err(e) => {
            crate::logging::note_run(&log, &format!("ERROR {e}"));
            crate::logging::finish_run(&log, true, "error");
        }
    }
    {
        let mut g = BUSY.lock().unwrap_or_else(|e| e.into_inner());
        *g = false;
    }
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
    model: &str,
    log: &Path,
) -> Result<Value, String> {
    if !paths::runtime_ready(root) {
        return Err(crate::i18n::t("s.75b84a31d6").into());
    }
    let script = worker_script(root);
    if !script.is_file() {
        return Err(crate::i18n::te("s.271fa82d5c", &(script.display())));
    }
    if !core_present(root) {
        return Err(crate::i18n::t("s.6ff3d83b8f"));
    }
    if input.trim().is_empty() || output.trim().is_empty() {
        return Err(crate::i18n::t("s.494f3ed5a0").into());
    }
    let mdir = model_dir(root);
    if !any_model_present(&mdir) {
        return Err(crate::i18n::t("s.e38da2e4e6"));
    }
    std::fs::create_dir_all(output).map_err(|e| crate::i18n::te("s.e9ddef6eab", &(e)))?;

    // 参数走临时文件而不是命令行：输入路径里有中文、空格、引号都很常见，
    // 拼进命令行就是一串转义地雷。
    let req = paths::update_cache(root).join("separate_request.json");
    if let Some(p) = req.parent() {
        let _ = std::fs::create_dir_all(p);
    }
    let payload = json!({
        "model": model,
        "model_dir": mdir.to_string_lossy(),
        "input": input,
        "output": output,
        "device": "auto",
        "format": "wav",
    });
    std::fs::write(&req, serde_json::to_string_pretty(&payload).unwrap_or_default())
        .map_err(|e| crate::i18n::te("s.5ee0565f28", &(e)))?;

    // python.exe 而不是 pythonw：我们要读它的 stdout。窗口用 CREATE_NO_WINDOW
    // 压掉，不然每次分离都会闪一个黑框。
    let py = paths::runtime_python(root).ok_or(crate::i18n::t("s.47e57cab60"))?;
    let errfile = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(log)
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
        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }

    let mut child = cmd.spawn().map_err(|e| crate::i18n::te("s.c727da1f5b", &(e)))?;
    let _keep = crate::worker::ToolPidGuard::new(child.id());
    let stdout = child.stdout.take().ok_or(crate::i18n::t("s.1a66c860cd"))?;
    let mut files: Vec<String> = Vec::new();
    let mut fail: Option<String> = None;

    for line in BufReader::new(stdout).lines().map_while(Result::ok) {
        if cancel_flag().load(Ordering::SeqCst) {
            let _ = child.kill();
            return Err(crate::i18n::t("s.a5ffdc95ee").into());
        }
        let Ok(v) = serde_json::from_str::<Value>(&line) else {
            continue; // 不是我们的协议行，忽略
        };
        let phase = v.get("phase").and_then(|x| x.as_str()).unwrap_or("");
        let msg = v.get("message").and_then(|x| x.as_str()).unwrap_or("");
        match phase {
            "start" => {
                let m = crate::i18n::t("s.07bbf0331b");
                emit(app, "start", 0, 1, &m);
            }
            "run" => {
                let fallback = crate::i18n::t("s.2282c91c77");
                emit(
                    app,
                    "run",
                    v.get("done").and_then(|x| x.as_u64()).unwrap_or(0),
                    v.get("total").and_then(|x| x.as_u64()).unwrap_or(1),
                    if msg.is_empty() {
                        &fallback
                    } else {
                        msg
                    },
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

    let st = child.wait().map_err(|e| crate::i18n::te("s.a4abecd0fe", &(e)))?;
    if let Some(e) = fail {
        return Err(e);
    }
    if !st.success() {
        return Err(crate::i18n::te("s.6b7047af91", &st.code().unwrap_or(-1)));
    }
    emit(app, "done", 1, 1, &crate::i18n::t("s.104ec2bbf7"));
    // 分离会在 TEMP 里落 reformatted.wav 等中间文件，用完就清。
    let stats = crate::paths::clean_temps(root);
    crate::paths::log_clean_stats(&crate::i18n::t("s.b0cf745781"), root, &stats);
    Ok(json!({ "ok": true, "files": files, "output": output }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn model_dir_lives_in_the_install_not_the_home_dir() {
        // PyMSS 默认写 ~/.cache/pymss：卸载带不走，用户也找不到。
        let d = model_dir(Path::new("C:\\App"));
        assert!(d.ends_with("pymss"));
        assert!(d.to_string_lossy().starts_with("C:\\App"));
    }

    #[test]
    fn status_reports_not_ready_without_a_runtime() {
        let st = status(Path::new("C:\\definitely-not-here"));
        assert_eq!(st["runtime_ready"], json!(false));
        assert_eq!(st["models"], json!([]));
    }

    #[test]
    fn core_present_detects_missing_pymss_core() {
        // 部署树缺 tools/pymss_core 时分离会崩在 import 上，预检要认得出来。
        let base = std::env::temp_dir().join("rvcf-separate-core");
        let _ = std::fs::remove_dir_all(&base);
        std::fs::create_dir_all(base.join("tools").join("pymss")).unwrap();
        assert!(!core_present(&base));
        std::fs::create_dir_all(base.join("tools").join("pymss_core")).unwrap();
        std::fs::write(
            base.join("tools").join("pymss_core").join("__init__.py"),
            b"",
        )
        .unwrap();
        assert!(core_present(&base));
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn models_in_nested_catalog_dirs_are_found() {
        // PyMSS 按 relpath 摆子目录（legacy_vr/vr_hp2/…），平铺扫描会扫不到。
        let base = std::env::temp_dir().join("rvcf-separate-nested");
        let _ = std::fs::remove_dir_all(&base);
        let nested = base.join("legacy_vr").join("vr_hp2");
        std::fs::create_dir_all(&nested).unwrap();
        std::fs::write(nested.join("7_HP2-UVR.pth"), b"x").unwrap();
        let mut models = Vec::new();
        collect_models(&base, &mut models);
        assert_eq!(models, vec!["7_HP2-UVR.pth"]);
        assert!(any_model_present(&base));
        let _ = std::fs::remove_dir_all(&base);
    }
}
