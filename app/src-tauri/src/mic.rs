//! 设置页的麦克风测试。
//!
//! 「设备选好了，到底有没有声音进来」这件事，在这之前只有一条验证路径：
//! 挑个音色、把整个引擎起来、对着麦说话看底栏那根条动不动。引擎冷启动
//! 二三十秒，起不来的原因又有十几种 —— 用它来验一只麦是拿最重的锤子敲
//! 最小的钉子，而且敲不响的时候还分不清是麦的事还是引擎的事。
//!
//! 这里走 `tools/record_worker.py` 的 probe 模式：只开设备读电平，不写盘，
//! 不碰 GPU，不经过实时 worker。设备名和 hostapi 直接读 `app_config`，
//! 跟设置页那两个下拉框是同一个值 —— 测的必须是他选的那一个。

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

use serde_json::{json, Value};
use tauri::AppHandle;

use crate::paths;

static BUSY: Mutex<bool> = Mutex::new(false);
static CANCEL: OnceLock<Arc<AtomicBool>> = OnceLock::new();
static STOP_FILE: Mutex<Option<PathBuf>> = Mutex::new(None);

/// 测试最多跑这么久。用户忘了点停止也不该留一个开着麦的进程在后台。
const MAX_SEC: u64 = 30;

/// 峰值高过这个就算「听见了」。
///
/// -45 dBFS 大约是安静房间里正常说话的下限。再低一档会把电流底噪也算成
/// 说话，用户明明没出声却被告知「一切正常」，比不做还糟。
const HEARD_PEAK_DB: f64 = -45.0;

fn cancel_flag() -> Arc<AtomicBool> {
    CANCEL
        .get_or_init(|| Arc::new(AtomicBool::new(false)))
        .clone()
}

pub fn stop() {
    cancel_flag().store(true, Ordering::SeqCst);
    if let Ok(g) = STOP_FILE.lock() {
        if let Some(p) = g.as_ref() {
            let _ = std::fs::write(p, b"stop");
        }
    }
}

fn emit(app: &AppHandle, phase: &str, peak: Option<f64>, sec: Option<f64>, message: &str) {
    let mut body = json!({ "phase": phase, "message": message });
    if let Some(v) = peak {
        body["peak"] = json!(v);
    }
    if let Some(v) = sec {
        body["sec"] = json!(v);
    }
    let _ = crate::diagnostics::emit(&app, "mic-test", body);
}

/// worker 报的稳定标识 → 界面文案的键。诊断认不出原因时，这句话作为原因显示。
fn message_key(code: &str) -> Option<&'static str> {
    match code {
        "busy" => Some("s.micErrBusy"),
        "notfound" => Some("s.micErrNotFound"),
        "nolib" => Some("s.micErrNoLib"),
        // 一帧都没读到。多半是用户开完立刻点了停止，也可能是设备开着但完全
        // 不出数据 —— 两种情况对用户来说是同一句话：没听见。
        "silent" => Some("s.micTestSilent"),
        "enum" | "open" => Some("s.micErrOpen"),
        _ => None,
    }
}

/// 开麦读几秒电平。阻塞到用户点停止、超时，或者设备根本打不开。
pub fn test(app: &AppHandle, root: &Path) -> Result<Value, String> {
    {
        let mut g = BUSY.lock().unwrap_or_else(|e| e.into_inner());
        if *g {
            return Err(crate::i18n::t("s.micTestBusy"));
        }
        *g = true;
    }
    cancel_flag().store(false, Ordering::SeqCst);
    let log = crate::logging::begin_run(root, crate::logging::CH_STS, &json!({"operation":"mic_test"}));
    let slice = crate::diagnostics::LogSlice::start(&log);
    let out = test_inner(app, root, &log)
        .map_err(|error| slice.finish(fabric_diagnostics::Feature::Recording, error));
    *BUSY.lock().unwrap_or_else(|e| e.into_inner()) = false;
    *STOP_FILE.lock().unwrap_or_else(|e| e.into_inner()) = None;
    cancel_flag().store(false, Ordering::SeqCst);
    if let Err(ref e) = out {
        emit(app, "error", None, None, e);
    }
    out
}

fn test_inner(app: &AppHandle, root: &Path, log: &Path) -> Result<Value, String> {
    if !paths::runtime_ready(root) {
        return Err(crate::i18n::t("s.stsRecordNeedRuntime"));
    }
    let script = root.join("tools").join("record_worker.py");
    if !script.is_file() {
        return Err(crate::i18n::t("s.stsRecordNeedWorker"));
    }
    let py = paths::runtime_python(root).ok_or_else(|| crate::i18n::t("s.47e57cab60"))?;

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
    std::fs::create_dir_all(&cache).map_err(|e| crate::i18n::te("s.5ee0565f28", &e))?;
    let req = cache.join("mic_test_request.json");
    let stop = cache.join("mic_test_stop");
    let _ = std::fs::remove_file(&stop);
    *STOP_FILE.lock().unwrap_or_else(|e| e.into_inner()) = Some(stop.clone());
    let payload = json!({
        "probe": true,
        "device": device,
        "hostapi": hostapi,
        "stop_file": stop.to_string_lossy(),
        "max_sec": MAX_SEC,
    });
    std::fs::write(&req, payload.to_string()).map_err(|e| crate::i18n::te("s.5ee0565f28", &e))?;

    // stderr 落文件而不是 piped-不读：PortAudio 开设备时爱往 stderr 写警告，
    // 管道满了子进程就卡在 write 上，下面这个循环会永远等下去。
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
            return Err(crate::i18n::t("s.68759edc4b"));
        }
    };

    emit(app, "start", None, Some(0.0), &crate::i18n::t("s.micTestOpening"));

    let mut top = -90.0_f64;
    let mut secs = 0.0_f64;
    let mut label = String::new();
    let mut fail: Option<String> = None;

    for line in BufReader::new(stdout).lines().map_while(Result::ok) {
        if cancel_flag().load(Ordering::SeqCst) {
            let _ = std::fs::write(&stop, b"stop");
        }
        let Ok(v) = serde_json::from_str::<Value>(&line) else {
            continue;
        };
        let phase = v.get("phase").and_then(|x| x.as_str()).unwrap_or("");
        let peak = v.get("peak").and_then(|x| x.as_f64());
        let sec = v.get("sec").and_then(|x| x.as_f64());
        if let Some(s) = sec {
            secs = s;
        }
        if let Some(p) = peak {
            if p > top {
                top = p;
            }
        }
        match phase {
            "start" => {
                label = v
                    .get("device")
                    .and_then(|x| x.as_str())
                    .unwrap_or("")
                    .to_string();
                emit(
                    app,
                    "start",
                    None,
                    Some(0.0),
                    &crate::i18n::te("s.micTestListening", &label),
                );
            }
            // 电平原样转发。界面上那根条要跟得上说话，任何抽稀都会让它变呆。
            "level" => emit(app, "level", peak, sec, ""),
            "error" => {
                let mut v = v.clone();
                if let Some(key) = v.get("code").and_then(|x| x.as_str()).and_then(message_key) {
                    v["message_code"] = json!(key);
                }
                fail = Some(crate::diagnostics::worker_error(fabric_diagnostics::Feature::Recording, &v));
            }
            _ => {}
        }
    }

    let status = child.wait();
    let _ = std::fs::remove_file(&stop);

    if let Some(e) = fail {
        return Err(e);
    }
    // worker 崩在 JSON 之外（import 炸了、PortAudio 直接把进程带走）时一行
    // 都收不到。不看退出码的话，这里会拿着 top = -90 的初值报「没听到声音」，
    // 把一次崩溃说成一只坏麦，用户会去换麦克风。
    let status = status.map_err(|error| error.to_string())?;
    if !status.success() {
        return Err(crate::diagnostics::worker_error(fabric_diagnostics::Feature::Recording,
            &json!({"message":crate::i18n::t("s.micErrOpen"),"exit_code":status.code()})));
    }

    let heard = top >= HEARD_PEAK_DB;
    let message = if heard {
        crate::i18n::te("s.micTestHeard", &format!("{top:.0}"))
    } else {
        crate::i18n::t("s.micTestSilent")
    };
    emit(app, "done", Some(top), Some(secs), &message);
    Ok(json!({
        "ok": true,
        "heard": heard,
        "peak_db": top,
        "sec": secs,
        "device": label,
        "message": message,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 判定门限是这个功能的全部意义所在：调高了正常说话被判成「没声音」，
    /// 调低了底噪也算「听见了」。两边各钉一个样本。
    #[test]
    fn the_heard_threshold_separates_speech_from_room_noise() {
        // 安静房间的底噪 / 未插线的输入
        assert!(-60.0 < HEARD_PEAK_DB);
        assert!(-90.0 < HEARD_PEAK_DB);
        // 正常说话的峰值
        assert!(-20.0 > HEARD_PEAK_DB);
        assert!(-40.0 > HEARD_PEAK_DB);
    }

    /// 标识对不上时必须退回 worker 那句中文，不能变成空字符串 ——
    /// 界面上一个「测试失败」加一片空白，比一句中文还难查。
    #[test]
    fn an_unknown_code_falls_back_to_the_worker_message() {
        assert_eq!(message_key("busy"), Some("s.micErrBusy"));
        assert_eq!(message_key("weird"), None);
    }
}
