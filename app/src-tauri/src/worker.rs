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

pub(crate) fn append_log(root: &Path, line: &str) {
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

/// True if *pid* is still running.
///
/// Win32 directly, no child process. This is on the status-poll path, which
/// runs every 400 ms while converting — the previous `tasklist.exe` spawn cost
/// far more CPU than the check was worth, and it competed with the realtime
/// audio thread on exactly the machines that can least afford it.
#[cfg(windows)]
fn pid_alive(pid: u32) -> bool {
    use windows_sys::Win32::Foundation::{CloseHandle, STILL_ACTIVE};
    use windows_sys::Win32::System::Threading::{
        GetExitCodeProcess, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION,
    };
    if pid == 0 {
        return false;
    }
    unsafe {
        let h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if h.is_null() {
            // Access denied also lands here. A process we cannot open is not
            // one we could have spawned, so treating it as gone is correct for
            // our purposes and never kills someone else's process.
            return false;
        }
        let mut code: u32 = 0;
        let ok = GetExitCodeProcess(h, &mut code);
        CloseHandle(h);
        ok != 0 && code == STILL_ACTIVE as u32
    }
}

#[cfg(not(windows))]
fn pid_alive(pid: u32) -> bool {
    pid != 0 && Path::new(&format!("/proc/{pid}")).exists()
}

/// Full image path for *pid*, or empty.
///
/// Was a `Get-CimInstance Win32_Process` call through PowerShell — a cold start
/// per lookup, and no return at all on a machine whose WMI repository is
/// damaged. `Command::output()` has no timeout, so that stalled the caller
/// indefinitely. The Win32 call cannot hang and spawns nothing.
#[cfg(windows)]
fn pid_image_path(pid: u32) -> String {
    use std::ffi::OsString;
    use std::os::windows::ffi::OsStringExt;
    use windows_sys::Win32::Foundation::CloseHandle;
    use windows_sys::Win32::System::Threading::{
        OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_WIN32,
        PROCESS_QUERY_LIMITED_INFORMATION,
    };
    if pid == 0 {
        return String::new();
    }
    unsafe {
        let h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if h.is_null() {
            return String::new();
        }
        // MAX_PATH is not enough: a long-path-enabled system can exceed it, and
        // the call fails rather than truncating.
        let mut buf = [0u16; 32768];
        let mut len: u32 = buf.len() as u32;
        let ok = QueryFullProcessImageNameW(h, PROCESS_NAME_WIN32, buf.as_mut_ptr(), &mut len);
        CloseHandle(h);
        if ok == 0 {
            return String::new();
        }
        OsString::from_wide(&buf[..len as usize])
            .to_string_lossy()
            .trim()
            .to_string()
    }
}

#[cfg(not(windows))]
fn pid_image_path(_pid: u32) -> String {
    String::new()
}

/// Remembers the verdict for one pid so the expensive identity lookup runs once
/// per process rather than once per poll.
///
/// A pid's image cannot change while the process lives, so the only way the
/// answer goes stale is the process dying and the number being recycled — and
/// that is exactly what the liveness check catches before the cache is read.
static IDENTITY_CACHE: Mutex<Option<(u32, bool)>> = Mutex::new(None);

fn cached_identity(pid: u32) -> Option<bool> {
    IDENTITY_CACHE
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .and_then(|(p, ours)| if p == pid { Some(ours) } else { None })
}

fn remember_identity(pid: u32, ours: bool) {
    *IDENTITY_CACHE.lock().unwrap_or_else(|e| e.into_inner()) = Some((pid, ours));
}

/// Drop the memo. Called when we stop or kill a worker, so a recycled pid is
/// never trusted on the strength of the previous occupant's identity.
pub fn forget_identity_cache() {
    *IDENTITY_CACHE.lock().unwrap_or_else(|e| e.into_inner()) = None;
}

/// Only treat as our worker if image is Runtime/product python (avoids recycled-PID kill).
fn pid_is_our_worker(root: &Path, pid: u32) -> bool {
    // Liveness first, every time: cheap, and it is what makes the memo below
    // safe against pid recycling.
    if pid == 0 || !pid_alive(pid) {
        if pid != 0 {
            forget_identity_cache();
        }
        return false;
    }
    if let Some(ours) = cached_identity(pid) {
        return ours;
    }
    let ours = verify_identity(root, pid);
    remember_identity(pid, ours);
    ours
}

/// 只问「这是不是一个 python 进程」，不管它在哪个目录。
///
/// 用于我们自己记录过的 pid：路径可能因为 8.3 短名、盘符大小写、符号链接而对不
/// 上，但只要它是 python 就该按我们的 worker 处理，而不是既不认也不杀。
fn pid_looks_like_python(pid: u32) -> bool {
    let img = pid_image_path(pid).replace('/', "\\").to_ascii_lowercase();
    let base = Path::new(&img)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("");
    base == "python.exe" || base == "pythonw.exe"
}

/// The expensive half: ask the OS what image a pid is running.
fn verify_identity(root: &Path, pid: u32) -> bool {
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
    apply_main_gpu(root, &mut env);
    env
}

/// 把「主显卡」选择变成 worker 进程的环境变量。
///
/// 引擎全线写死 `cuda:0`（configs/config.py 的 `Config.device`，还有 rtrvc /
/// rmvpe / train_worker 里的一堆 0）。双卡机器上这就是「谁排第一用谁」——
/// 一块 5060 一块 5090，很可能整场都在用 5060 算。
///
/// 不去改引擎那一堆 0，而是在这里遮住其他卡：`CUDA_VISIBLE_DEVICES=n` 之后，
/// torch 眼里就只剩一块卡，`cuda:0` 自然落到用户选的那块上。训练、分离走的是
/// 同一个 `env_for_runtime`，所以三边行为一致。
///
/// `CUDA_DEVICE_ORDER=PCI_BUS_ID` 是为了让序号稳定：CUDA 默认按
/// FASTEST_FIRST 排，换一次驱动、插一块新卡都可能让同一个序号指向另一块卡，
/// 那样用户选过的设置会莫名其妙失效。
///
/// DirectML（A 卡 / 核显）不认这两个变量，那条路径上这个设置不生效 ——
/// 界面上写清楚了。
fn apply_main_gpu(root: &Path, env: &mut HashMap<String, String>) {
    let cfg = crate::config::read(root);
    let idx = cfg.get("main_gpu").and_then(|v| v.as_i64()).unwrap_or(-1);
    if idx < 0 {
        // 「自动」。用户机器上本来就设了这个变量的话别动它 —— 那是他自己的
        // 环境，不是我们该覆盖的东西。
        return;
    }
    env.insert("CUDA_VISIBLE_DEVICES".into(), idx.to_string());
    env.insert("CUDA_DEVICE_ORDER".into(), "PCI_BUS_ID".into());
    crate::logging::shell_log!("main_gpu={idx} → CUDA_VISIBLE_DEVICES");
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
            forget_identity_cache();
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
        } else if pid_looks_like_python(pid) {
            // 活着、是个 python 进程，但镜像路径没匹配上我们的目录。
            //
            // 这个 pid 是我们自己 spawn 的时候写进 pid 文件的，所以它就是我们的
            // —— 镜像路径比对只是防 pid 复用的第二道保险，不该反过来让我们认不出
            // 自己的进程。以前这里只记一行日志就放过：进程还活着占着声卡，
            // is_worker_alive 又因为同一个判断返回 false，于是 start_worker 再开
            // 一个。开几次就有几个 worker 同时往同一个输出设备写 —— 用户听到的
            // 就是「好几个模型的声音一起响」。
            append_log(
                root,
                &format!("kill_tree pid={pid} (我们记录的 pid，镜像路径没匹配上)"),
            );
            kill_tree(pid);
        } else {
            append_log(
                root,
                &format!("skip kill pid={pid} (不是 python 进程，可能是复用的 pid)"),
            );
        }
    }
    protocol::clear_worker_pid(root);
    forget_identity_cache();
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
            forget_identity_cache();
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
            forget_identity_cache();
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identity_memo_is_keyed_to_one_pid() {
        forget_identity_cache();
        assert_eq!(cached_identity(1234), None);
        remember_identity(1234, true);
        assert_eq!(cached_identity(1234), Some(true));
        // A different pid must never be answered from another pid's entry.
        assert_eq!(cached_identity(5678), None);
        remember_identity(5678, false);
        assert_eq!(cached_identity(5678), Some(false));
        assert_eq!(cached_identity(1234), None);
        forget_identity_cache();
        assert_eq!(cached_identity(5678), None);
    }

    #[test]
    fn pid_zero_is_never_alive() {
        assert!(!pid_alive(0));
    }
}
