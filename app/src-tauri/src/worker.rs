//! Spawn / track Runtime pythonw realtime_worker (file protocol).
//!
//! Behaviour mirrors launcher/realtime_client.py where it matters:
//! one worker, cleaned env, pythonw preferred, soft stop then force.

use std::collections::HashMap;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use serde_json::{json, Map, Value};

use crate::paths;
use crate::protocol;

static START_LOCK: Mutex<()> = Mutex::new(());

fn append_log(root: &Path, line: &str) {
    let path = paths::logs_dir(root).join("realtime_worker.log");
    let _ = std::fs::create_dir_all(path.parent().unwrap_or(root));
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(&path) {
        let _ = writeln!(f, "{line}");
    }
}

/// Local `YYYY-MM-DD HH:MM:SS` — these lines end up in the diagnostics bundle
/// and get correlated against user reports, so epoch seconds are useless.
fn stamp() -> String {
    chrono::Local::now().format("%Y-%m-%d %H:%M:%S").to_string()
}

/// True if *pid* is still running (exact PID, no substring false positives).
#[cfg(windows)]
fn pid_alive(pid: u32) -> bool {
    if pid == 0 {
        return false;
    }
    use std::os::windows::process::CommandExt;
    // CSV: "Image Name","PID",...
    let out = Command::new("tasklist")
        .args(["/FI", &format!("PID eq {pid}"), "/FO", "CSV", "/NH"])
        .creation_flags(0x08000000)
        .output();
    match out {
        Ok(o) => {
            let s = String::from_utf8_lossy(&o.stdout);
            for line in s.lines() {
                // "pythonw.exe","1234",...
                let cols: Vec<&str> = line.split(',').collect();
                if cols.len() >= 2 {
                    let p = cols[1].trim().trim_matches('"');
                    if p == pid.to_string() {
                        return true;
                    }
                }
            }
            false
        }
        Err(_) => false,
    }
}

#[cfg(not(windows))]
fn pid_alive(pid: u32) -> bool {
    pid != 0 && Path::new(&format!("/proc/{pid}")).exists()
}

/// Full image path for *pid*, or empty.
#[cfg(windows)]
fn pid_image_path(pid: u32) -> String {
    if pid == 0 {
        return String::new();
    }
    use std::os::windows::process::CommandExt;
    let ps = format!(
        "$p=Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\" -ErrorAction SilentlyContinue; if($p){{$p.ExecutablePath}}"
    );
    let out = Command::new("powershell")
        .args([
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            &ps,
        ])
        .creation_flags(0x08000000)
        .output();
    match out {
        Ok(o) => String::from_utf8_lossy(&o.stdout).trim().to_string(),
        Err(_) => String::new(),
    }
}

#[cfg(not(windows))]
fn pid_image_path(_pid: u32) -> String {
    String::new()
}

/// Only treat as our worker if image is Runtime/product python (avoids recycled-PID kill).
fn pid_is_our_worker(root: &Path, pid: u32) -> bool {
    if pid == 0 || !pid_alive(pid) {
        return false;
    }
    let img = pid_image_path(pid).replace('/', "\\").to_ascii_lowercase();
    if img.is_empty() {
        // No path (rare): trust only if status.pid matches and process is python*
        return false;
    }
    let base = Path::new(&img)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if base != "python.exe" && base != "pythonw.exe" {
        return false;
    }
    let root_n = root.to_string_lossy().replace('/', "\\").to_ascii_lowercase();
    let rt = paths::runtime_dir(root)
        .to_string_lossy()
        .replace('/', "\\")
        .to_ascii_lowercase();
    if !rt.is_empty() && img.contains(&rt) {
        return true;
    }
    if !root_n.is_empty() && img.contains(&root_n) {
        return true;
    }
    false
}

#[cfg(windows)]
fn kill_tree(pid: u32) {
    if pid == 0 {
        return;
    }
    use std::os::windows::process::CommandExt;
    let _ = Command::new("taskkill")
        .args(["/F", "/T", "/PID", &pid.to_string()])
        .creation_flags(0x08000000)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

#[cfg(not(windows))]
fn kill_tree(pid: u32) {
    if pid == 0 {
        return;
    }
    let _ = Command::new("kill").args(["-9", &pid.to_string()]).status();
}

/// Build env for Runtime python: strip host Python pollution (see win_util._env_for_runtime_python).
pub(crate) fn env_for_runtime(root: &Path) -> HashMap<String, String> {
    let drop_exact = [
        "_MEIPASS",
        "_PYI_APPLICATION_HOME_DIR",
        "_PYI_ARCHIVE_FILE",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONEXECUTABLE",
        "PYTHONUSERBASE",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        "CONDA_PYTHON_EXE",
        "TCL_LIBRARY",
        "TK_LIBRARY",
        "TIX_LIBRARY",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
    ];
    let mut env: HashMap<String, String> = std::env::vars().collect();
    env.retain(|k, _| {
        let ku = k.to_ascii_uppercase();
        if drop_exact.iter().any(|d| ku == *d) {
            return false;
        }
        if ku.starts_with("PYTHON")
            || ku.starts_with("CONDA_")
            || ku.starts_with("VIRTUAL_ENV")
            || ku.starts_with("PIP_")
            || ku.starts_with("UV_")
            || ku.starts_with("POETRY_")
            || ku.starts_with("MAMBA_")
            || ku.starts_with("PYENV_")
        {
            return false;
        }
        true
    });

    let root_s = root.to_string_lossy().to_string();
    let rt = paths::runtime_dir(root);
    let rt_s = rt.to_string_lossy().to_string();

    let path_key = env
        .keys()
        .find(|k| k.eq_ignore_ascii_case("PATH"))
        .cloned()
        .unwrap_or_else(|| "PATH".into());
    let old_path = env.get(&path_key).cloned().unwrap_or_default();
    let mut parts: Vec<String> = vec![rt_s, root_s.clone()];
    for p in old_path.split(';') {
        if p.is_empty() {
            continue;
        }
        let pl = p.replace('/', "\\").to_ascii_lowercase();
        if pl.contains("_mei") || pl.contains("pyinstaller") {
            continue;
        }
        parts.push(p.to_string());
    }
    env.insert(path_key, parts.join(";"));
    env.insert("TM_VOICE_ROOT".into(), root_s);
    env.insert("TM_REALTIME_WORKER".into(), "1".into());
    env.insert("PYTHONUNBUFFERED".into(), "1".into());
    env.insert("PYTHONNOUSERSITE".into(), "1".into());
    env.insert("no_proxy".into(), "localhost,127.0.0.1,::1".into());
    env.insert("NO_PROXY".into(), "localhost,127.0.0.1,::1".into());
    for k in ["TM_ACCEL", "TM_ACCEL_RESOLVED", "TM_USE_DML"] {
        if let Ok(v) = std::env::var(k) {
            env.insert(k.into(), v);
        }
    }
    if !env.contains_key("TM_ACCEL") {
        env.insert("TM_ACCEL".into(), "auto".into());
    }
    env
}

fn status_looks_ready(st: &Value) -> bool {
    let state = st.get("state").and_then(|v| v.as_str()).unwrap_or("");
    if state == "error" {
        return true;
    }
    let pid = st.get("pid").and_then(|v| v.as_u64()).unwrap_or(0);
    if pid == 0 {
        return false;
    }
    // Prefer idle/running; hostapis alone can appear mid-load
    state == "idle" || state == "running"
}

pub fn get_live_pid(root: &Path) -> u32 {
    for pid in [
        protocol::read_worker_pid_file(root),
        protocol::status_pid(root),
    ] {
        if pid_is_our_worker(root, pid) {
            return pid;
        }
        // Stale dead entry
        if pid > 0 && !pid_alive(pid) {
            protocol::clear_worker_pid(root);
        }
    }
    0
}

pub fn is_worker_alive(root: &Path) -> bool {
    get_live_pid(root) > 0
}

/// Kill only PIDs that still look like this product's worker.
pub fn kill_known_workers(root: &Path) {
    for pid in [
        protocol::read_worker_pid_file(root),
        protocol::status_pid(root),
    ] {
        if pid == 0 {
            continue;
        }
        if pid_is_our_worker(root, pid) {
            append_log(root, &format!("kill_tree our worker pid={pid}"));
            kill_tree(pid);
        } else if !pid_alive(pid) {
            // stale
        } else {
            append_log(
                root,
                &format!("skip kill pid={pid} (not our worker image)"),
            );
        }
    }
    protocol::clear_worker_pid(root);
    let mut fields = Map::new();
    fields.insert("state".into(), json!("idle"));
    fields.insert("pid".into(), json!(0));
    fields.insert("message".into(), json!("workers cleared"));
    fields.insert("error".into(), json!(""));
    fields.insert("delay_ms".into(), json!(0));
    fields.insert("infer_ms".into(), json!(0));
    let _ = protocol::write_status_merge(root, fields);
}

pub fn start_worker(root: &Path) -> Result<(), String> {
    // Recover from poisoning instead of failing forever: one panic while
    // starting would otherwise make the engine unstartable for the rest of the
    // session, with a restart as the only way out. The lock guards a re-check
    // that is idempotent, so a poisoned state is safe to continue from.
    let _guard = START_LOCK.lock().unwrap_or_else(|e| e.into_inner());

    if is_worker_alive(root) {
        return Ok(());
    }

    // Clear dead bookkeeping; only kill confirmed ours
    kill_known_workers(root);
    thread::sleep(Duration::from_millis(200));
    if is_worker_alive(root) {
        return Ok(());
    }

    let script = paths::worker_script(root);
    if !script.is_file() {
        return Err(format!("找不到实时 worker: {}", script.display()));
    }
    let pyw = paths::runtime_pythonw(root).ok_or_else(|| {
        format!(
            "找不到 Runtime\\pythonw.exe（根目录 {}）。请先补全 Runtime。",
            root.display()
        )
    })?;

    protocol::ensure_control_dir(root).map_err(|e| e.to_string())?;
    let mut fields = Map::new();
    fields.insert("state".into(), json!("starting"));
    fields.insert("message".into(), json!("launching worker…"));
    fields.insert("error".into(), json!(""));
    fields.insert("pid".into(), json!(0));
    let _ = protocol::write_status_merge(root, fields);

    append_log(
        root,
        &format!(
            "\n===== launch ts={} (tauri shell) =====\nROOT={}\nvia: {} {}",
            stamp(),
            root.display(),
            pyw.display(),
            script.display()
        ),
    );

    let env = env_for_runtime(root);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let log_path = paths::logs_dir(root).join("realtime_worker.log");
        let log_file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
            .ok();
        // Prefer pythonw (no console). CREATE_NO_WINDOW if fallback to python.exe.
        let is_pythonw = pyw
            .file_name()
            .and_then(|s| s.to_str())
            .map(|s| s.eq_ignore_ascii_case("pythonw.exe"))
            .unwrap_or(false);
        let mut flags = 0x00000200u32; // CREATE_NEW_PROCESS_GROUP
        if !is_pythonw {
            flags |= 0x08000000; // CREATE_NO_WINDOW
        }
        let mut cmd = Command::new(&pyw);
        cmd.arg(script.as_os_str())
            .current_dir(root)
            .envs(&env)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(match log_file {
                Some(f) => Stdio::from(f),
                None => Stdio::null(),
            })
            .creation_flags(flags);
        let child = cmd
            .spawn()
            .map_err(|e| format!("无法启动 worker: {e}"))?;
        append_log(root, &format!("spawned shell-side pid={}", child.id()));
        // Do not wait; worker re-parents as Runtime process and writes its own pid
        std::mem::forget(child);
    }
    #[cfg(not(windows))]
    {
        let child = Command::new(&pyw)
            .arg(script.as_os_str())
            .current_dir(root)
            .envs(&env)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("无法启动 worker: {e}"))?;
        std::mem::forget(child);
    }

    Ok(())
}

pub fn wait_worker_ready(root: &Path, timeout_ms: u64) -> Value {
    let deadline = Instant::now() + Duration::from_millis(timeout_ms);
    let mut last = protocol::read_status(root);
    let mut saw_live = false;
    while Instant::now() < deadline {
        last = protocol::read_status(root);
        let state = last.get("state").and_then(|v| v.as_str()).unwrap_or("");
        if state == "error" {
            return last;
        }
        let pid = last.get("pid").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
        if pid > 0 && pid_is_our_worker(root, pid) {
            saw_live = true;
            if status_looks_ready(&last) {
                let _ = protocol::write_worker_pid(root, pid);
                return last;
            }
        } else if pid > 0 && !pid_alive(pid) && (saw_live || state == "starting") {
            protocol::clear_worker_pid(root);
            return json!({
                "state": "error",
                "error": last.get("error").and_then(|v| v.as_str()).unwrap_or("worker died during load"),
                "message": "worker pid not alive",
                "pid": 0
            });
        }
        thread::sleep(Duration::from_millis(250));
    }
    if last.as_object().map(|o| o.is_empty()).unwrap_or(true) {
        json!({"state": "error", "error": "worker ready timeout", "pid": 0})
    } else if !is_worker_alive(root) {
        json!({
            "state": "error",
            "error": last.get("error").and_then(|v| v.as_str()).unwrap_or("worker ready timeout"),
            "message": "timeout",
            "pid": 0
        })
    } else {
        last
    }
}

pub fn send_command(root: &Path, cmd: &str, payload: Map<String, Value>) -> Result<u64, String> {
    protocol::write_command(root, cmd, payload).map_err(|e| e.to_string())
}

/// Ensure worker is up; refresh device list if empty. Does not hold UI locks.
pub fn ensure_worker_and_devices(root: &Path, timeout_ms: u64) -> Value {
    if !is_worker_alive(root) {
        if let Err(e) = start_worker(root) {
            return json!({"state": "error", "error": e, "pid": 0});
        }
    }
    let st = wait_worker_ready(root, timeout_ms);
    if st.get("state").and_then(|v| v.as_str()) == Some("error") {
        return st;
    }
    if st.get("state").and_then(|v| v.as_str()) == Some("running") {
        return st;
    }
    // Already have devices?
    let has_dev = st
        .get("input_devices")
        .and_then(|v| v.as_array())
        .map(|a| !a.is_empty())
        .unwrap_or(false)
        && st.get("hostapis").and_then(|v| v.as_array()).is_some();
    if has_dev {
        return st;
    }
    let _ = send_command(root, "list_devices", Map::new());
    let deadline = Instant::now() + Duration::from_secs(30);
    while Instant::now() < deadline {
        let st = protocol::read_status(root);
        let ok = st
            .get("input_devices")
            .and_then(|v| v.as_array())
            .map(|a| !a.is_empty())
            .unwrap_or(false)
            && st.get("hostapis").and_then(|v| v.as_array()).is_some();
        if ok {
            return st;
        }
        if !is_worker_alive(root) {
            return json!({"state": "error", "error": "worker died during list_devices", "pid": 0});
        }
        thread::sleep(Duration::from_millis(200));
    }
    protocol::read_status(root)
}

/// Soft-stop then start (same order as Tk shell before start_vc_remote).
pub fn start_vc(root: &Path) -> Result<u64, String> {
    if !is_worker_alive(root) {
        start_worker(root)?;
        let st = wait_worker_ready(root, 100_000);
        if st.get("state").and_then(|v| v.as_str()) == Some("error") {
            return Err(st
                .get("error")
                .and_then(|v| v.as_str())
                .unwrap_or("worker error")
                .to_string());
        }
    } else {
        // Soft stop any leftover stream so start is clean
        let st = protocol::read_status(root);
        if st.get("state").and_then(|v| v.as_str()) == Some("running") {
            let _ = send_command(root, "stop", Map::new());
            let deadline = Instant::now() + Duration::from_secs(4);
            while Instant::now() < deadline {
                let s = protocol::read_status(root);
                if s.get("state").and_then(|v| v.as_str()) != Some("running") {
                    break;
                }
                thread::sleep(Duration::from_millis(150));
            }
            thread::sleep(Duration::from_millis(250));
        }
    }
    send_command(root, "start", Map::new())
}

pub fn wait_vc_running(root: &Path, timeout_ms: u64) -> Value {
    let deadline = Instant::now() + Duration::from_millis(timeout_ms);
    let mut last = protocol::read_status(root);
    let mut saw_starting = false;
    while Instant::now() < deadline {
        last = protocol::read_status(root);
        let state = last.get("state").and_then(|v| v.as_str()).unwrap_or("");
        if state == "running" || state == "error" {
            return last;
        }
        if state == "starting" {
            saw_starting = true;
        }
        if saw_starting && !is_worker_alive(root) {
            kill_known_workers(root);
            return json!({
                "state": "error",
                "error": "变声引擎进程意外退出（常见：显存不足、声卡被占用）。已清理残留，请再试。",
                "message": "worker died during start",
                "pid": 0
            });
        }
        thread::sleep(Duration::from_millis(300));
    }
    if !is_worker_alive(root) {
        kill_known_workers(root);
        return json!({
            "state": "error",
            "error": "启动超时且引擎已退出，请查看 User_Data/logs/realtime_worker.log",
            "pid": 0
        });
    }
    last
}

pub fn stop_vc(root: &Path, force: bool) -> Result<(), String> {
    let pid = get_live_pid(root);
    if pid == 0 {
        if force {
            kill_known_workers(root);
        }
        return Ok(());
    }
    let _ = send_command(root, "stop", Map::new());
    let deadline = Instant::now() + Duration::from_secs(12);
    while Instant::now() < deadline {
        if !pid_alive(pid) {
            // Parent gone — clear bookkeeping (orphans may remain; force kills tree)
            if force {
                kill_tree(pid);
            }
            protocol::clear_worker_pid(root);
            return Ok(());
        }
        let st = protocol::read_status(root);
        if st.get("state").and_then(|v| v.as_str()) != Some("running") {
            // Soft stop leaves worker alive in idle — correct
            return Ok(());
        }
        thread::sleep(Duration::from_millis(200));
    }
    if force {
        if pid_is_our_worker(root, pid) {
            kill_tree(pid);
        }
        kill_known_workers(root);
    }
    Ok(())
}

pub fn set_hot(root: &Path, payload: Map<String, Value>) -> Result<u64, String> {
    if !is_worker_alive(root) {
        return Err("worker 未运行".into());
    }
    send_command(root, "set", payload)
}

/// Snapshot for the UI (status + derived meter 0..1).
pub fn status_for_ui(root: &Path) -> Value {
    let mut st = protocol::read_status(root);
    let alive = is_worker_alive(root);
    if let Some(obj) = st.as_object_mut() {
        obj.insert("worker_alive".into(), json!(alive));
        obj.insert("product_root".into(), json!(root.to_string_lossy()));
        // last_input_db ~ -90..0 → meter 0..1 (floor -60 matches common dock range)
        // gui_v1 writes the status field as `input_db`; `last_input_db` is its
        // own internal attribute name and never appears in status.json, so the
        // old lookup always fell back to -90 and pinned the meter at 0.
        let db = obj
            .get("input_db")
            .or_else(|| obj.get("last_input_db"))
            .and_then(|v| v.as_f64())
            .unwrap_or(-90.0);
        let meter = ((db + 60.0) / 60.0).clamp(0.0, 1.0);
        obj.insert("meter_level".into(), json!(meter));
        let th = obj
            .get("threhold")
            .or_else(|| obj.get("threshold"))
            .and_then(|v| v.as_f64())
            .unwrap_or(-45.0);
        let th_meter = ((th + 60.0) / 60.0).clamp(0.0, 1.0);
        obj.insert("threshold_meter".into(), json!(th_meter));
        // If status claims a pid that is not ours / dead, surface it
        if !alive {
            if let Some(p) = obj.get("pid").and_then(|v| v.as_u64()) {
                if p > 0 {
                    obj.insert("pid".into(), json!(0));
                }
            }
        }
    }
    st
}
