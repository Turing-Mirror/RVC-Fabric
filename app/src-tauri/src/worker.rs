//! Spawn / track Runtime pythonw realtime_worker (file protocol).

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

#[cfg(windows)]
fn pid_alive(pid: u32) -> bool {
    if pid == 0 {
        return false;
    }
    use std::os::windows::process::CommandExt;
    // Use tasklist (available without admin); STILL_ACTIVE via OpenProcess is better but needs winapi.
    let out = Command::new("tasklist")
        .args(["/FI", &format!("PID eq {pid}"), "/NH"])
        .creation_flags(0x08000000)
        .output();
    match out {
        Ok(o) => {
            let s = String::from_utf8_lossy(&o.stdout);
            s.contains(&pid.to_string())
        }
        Err(_) => false,
    }
}

#[cfg(not(windows))]
fn pid_alive(pid: u32) -> bool {
    if pid == 0 {
        return false;
    }
    std::path::Path::new(&format!("/proc/{pid}")).exists()
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

/// Build env for Runtime python: strip host Python pollution.
fn env_for_runtime(root: &Path) -> HashMap<String, String> {
    let drop_exact = [
        "_MEIPASS",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONEXECUTABLE",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        "CONDA_PYTHON_EXE",
        "TCL_LIBRARY",
        "TK_LIBRARY",
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
        {
            return false;
        }
        true
    });

    let root_s = root.to_string_lossy().to_string();
    let rt = if root.join("Runtime").is_dir() {
        root.join("Runtime")
    } else {
        root.join("runtime")
    };
    let rt_s = rt.to_string_lossy().to_string();

    // Prepend Runtime + root to PATH; drop _MEI and host python shadows loosely
    let path_key = env
        .keys()
        .find(|k| k.eq_ignore_ascii_case("PATH"))
        .cloned()
        .unwrap_or_else(|| "PATH".into());
    let old_path = env.get(&path_key).cloned().unwrap_or_default();
    let mut parts: Vec<String> = vec![rt_s.clone(), root_s.clone()];
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
    env.insert("no_proxy".into(), "localhost,127.0.0.1,::1".into());
    env.insert("NO_PROXY".into(), "localhost,127.0.0.1,::1".into());
    // Prefer parent GPU resolution when already set
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
        return true; // terminal
    }
    let pid = st
        .get("pid")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    if pid == 0 {
        return false;
    }
    state == "idle" || state == "running" || st.get("hostapis").is_some()
}

pub fn get_live_pid(root: &Path) -> u32 {
    for pid in [
        protocol::read_worker_pid_file(root),
        protocol::status_pid(root),
    ] {
        if pid > 0 && pid_alive(pid) {
            return pid;
        }
    }
    0
}

pub fn is_worker_alive(root: &Path) -> bool {
    get_live_pid(root) > 0
}

/// Kill known worker PIDs from control files (best-effort).
pub fn kill_known_workers(root: &Path) {
    for pid in [
        protocol::read_worker_pid_file(root),
        protocol::status_pid(root),
    ] {
        if pid > 0 && pid_alive(pid) {
            append_log(root, &format!("kill_tree pid={pid}"));
            kill_tree(pid);
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
    let _guard = START_LOCK
        .lock()
        .map_err(|_| "start lock poisoned".to_string())?;

    if is_worker_alive(root) {
        return Ok(());
    }

    // Clear dead PIDs
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

    let stamp = chrono_lite_stamp();
    append_log(
        root,
        &format!(
            "\n===== launch {stamp} (tauri shell) =====\nROOT={}\nvia: {} {}",
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
        let mut cmd = Command::new(&pyw);
        cmd.arg(&script)
            .current_dir(root)
            .envs(&env)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(match log_file {
                Some(f) => Stdio::from(f),
                None => Stdio::null(),
            })
            // CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
            .creation_flags(0x00000200 | 0x08000000);
        let child = cmd
            .spawn()
            .map_err(|e| format!("无法启动 worker: {e}"))?;
        append_log(root, &format!("spawned launcher pid={}", child.id()));
        // Detach: child is Runtime pythonw; don't wait
        std::mem::forget(child);
    }
    #[cfg(not(windows))]
    {
        let child = Command::new(&pyw)
            .arg(&script)
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

fn chrono_lite_stamp() -> String {
    use std::time::SystemTime;
    match SystemTime::now().duration_since(std::time::UNIX_EPOCH) {
        Ok(d) => format!("unix_ts={}", d.as_secs()),
        Err(_) => "unix_ts=?".into(),
    }
}

pub fn wait_worker_ready(root: &Path, timeout_ms: u64) -> Value {
    let deadline = Instant::now() + Duration::from_millis(timeout_ms);
    let mut last = protocol::read_status(root);
    while Instant::now() < deadline {
        last = protocol::read_status(root);
        let state = last.get("state").and_then(|v| v.as_str()).unwrap_or("");
        if state == "error" {
            return last;
        }
        let pid = last
            .get("pid")
            .and_then(|v| v.as_u64())
            .unwrap_or(0) as u32;
        if pid > 0 && pid_alive(pid) && status_looks_ready(&last) {
            let _ = protocol::write_worker_pid(root, pid);
            return last;
        }
        thread::sleep(Duration::from_millis(250));
    }
    if last.as_object().map(|o| o.is_empty()).unwrap_or(true) {
        json!({"state": "error", "error": "worker ready timeout", "pid": 0})
    } else {
        last
    }
}

pub fn send_command(root: &Path, cmd: &str, payload: Map<String, Value>) -> Result<u64, String> {
    protocol::write_command(root, cmd, payload).map_err(|e| e.to_string())
}

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
    let _ = send_command(root, "list_devices", Map::new());
    let deadline = Instant::now() + Duration::from_secs(30);
    while Instant::now() < deadline {
        let st = protocol::read_status(root);
        if st.get("input_devices").is_some() && st.get("hostapis").is_some() {
            return st;
        }
        if !is_worker_alive(root) {
            return json!({"state": "error", "error": "worker died during list_devices", "pid": 0});
        }
        thread::sleep(Duration::from_millis(200));
    }
    protocol::read_status(root)
}

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
    }
    send_command(root, "start", Map::new())
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
            kill_known_workers(root);
            return Ok(());
        }
        let st = protocol::read_status(root);
        if st.get("state").and_then(|v| v.as_str()) != Some("running") {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(200));
    }
    if force {
        kill_tree(pid);
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
        // last_input_db ~ -90..0 → meter 0..1
        let db = obj
            .get("last_input_db")
            .and_then(|v| v.as_f64())
            .unwrap_or(-90.0);
        let meter = ((db + 60.0) / 60.0).clamp(0.0, 1.0);
        obj.insert("meter_level".into(), json!(meter));
        let th = obj
            .get("threhold")
            .or_else(|| obj.get("threshold"))
            .and_then(|v| v.as_f64())
            .unwrap_or(-45.0);
        // threshold mark on same scale as meter
        let th_meter = ((th + 60.0) / 60.0).clamp(0.0, 1.0);
        obj.insert("threshold_meter".into(), json!(th_meter));
    }
    st
}
