//! Spawn / track Runtime pythonw realtime_worker (file protocol).
//!
//! Behaviour mirrors launcher/realtime_client.py where it matters:
//! one worker, cleaned env, pythonw preferred, soft stop then force.

use std::collections::HashMap;
#[cfg(windows)]
use std::fs::OpenOptions;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{LazyLock, Mutex, TryLockError};
use std::thread;
use std::time::{Duration, Instant};

use serde_json::{json, Map, Value};

use crate::paths;
use crate::protocol;

static START_LOCK: Mutex<()> = Mutex::new(());

pub(crate) fn append_log(root: &Path, line: &str) {
    crate::logging::append_daily(root, crate::logging::CH_WORKER, line);
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

/// Remembers each probed pid's verdict so the expensive identity lookup runs
/// once per process rather than once per poll. Keyed by pid — probing one
/// process must not evict another's verified identity.
///
/// A pid's image cannot change while the process lives, so the only way the
/// answer goes stale is the process dying and the number being recycled — and
/// that is exactly what the liveness check catches before the cache is read.
static IDENTITY_CACHE: LazyLock<Mutex<HashMap<u32, bool>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

fn cached_identity(pid: u32) -> Option<bool> {
    IDENTITY_CACHE
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .get(&pid)
        .copied()
}

fn remember_identity(pid: u32, ours: bool) {
    IDENTITY_CACHE
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .insert(pid, ours);
}

/// Drop one pid's memo. Called when that pid is found dead, so a recycled
/// number is never trusted on the strength of the previous occupant's
/// identity — and so a dead pid's eviction can't touch a live worker's entry.
fn forget_identity(pid: u32) {
    IDENTITY_CACHE
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .remove(&pid);
}

/// Drop all memos. Called when we stop or kill workers wholesale.
pub fn forget_identity_cache() {
    IDENTITY_CACHE
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .clear();
}

/// Only treat as our worker if image is Runtime/product python (avoids recycled-PID kill).
fn pid_is_our_worker(root: &Path, pid: u32) -> bool {
    // Liveness first, every time: cheap, and it is what makes the memo below
    // safe against pid recycling.
    if pid == 0 || !pid_alive(pid) {
        if pid != 0 {
            forget_identity(pid);
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
    // 管道里的 worker stdout 走 UTF-8，避免中文进度/报错 OSError 22。
    env.insert("PYTHONIOENCODING".into(), "utf-8".into());
    env.insert("PYTHONUTF8".into(), "1".into());
    env.insert("no_proxy".into(), "localhost,127.0.0.1,::1".into());
    env.insert("NO_PROXY".into(), "localhost,127.0.0.1,::1".into());
    // 官方 RVC 靠产品根 .env；安装包历史上未带该文件。路径相对 cwd=产品根。
    // 已有值（用户/壳层显式设置）不覆盖。
    for (k, v) in [
        ("weight_root", "assets/weights"),
        ("weight_uvr5_root", "assets/uvr5_weights"),
        ("index_root", "logs"),
        ("outside_index_root", "assets/indices"),
        ("rmvpe_root", "assets/rmvpe"),
    ] {
        env.entry(k.into()).or_insert_with(|| v.into());
    }
    // 与官方 WebUI 一致：把 TEMP/TMP/TMPDIR 指到安装目录下的 TEMP，
    // 中间文件统一落这里，启动/退出/任务结束时清理。
    let temp = paths::temp_dir(root);
    let _ = std::fs::create_dir_all(&temp);
    let temp_s = temp.to_string_lossy().to_string();
    env.insert("TEMP".into(), temp_s.clone());
    env.insert("TMP".into(), temp_s.clone());
    env.insert("TMPDIR".into(), temp_s);
    let cfg = crate::config::read(root);
    for k in ["TM_ACCEL", "TM_ACCEL_RESOLVED", "TM_USE_DML"] {
        if let Ok(v) = std::env::var(k) {
            env.insert(k.into(), v);
        }
    }
    // E-03 唯一后端选择：用户保存的选择 > 旧环境变量 > auto。
    // 显式选择时清掉 TM_USE_DML——不然用户在界面选 CPU，OS 环境里
    // 遗留的 TM_USE_DML=1 会把它顶回 DirectML。
    match cfg.get("accel_backend").and_then(|v| v.as_str()) {
        Some(v @ ("auto" | "cuda" | "dml" | "cpu")) => {
            env.insert("TM_ACCEL".into(), v.into());
            env.remove("TM_USE_DML");
        }
        _ => {}
    }
    if !env.contains_key("TM_ACCEL") {
        env.insert("TM_ACCEL".into(), "auto".into());
    }
    // 注册表 / nvidia-smi 看到的 N 卡名。worker 里 torch.cuda 起不来时，靠这个
    // 判断「卡在、驱动不在」，不要自动改走核显 DirectML。
    let nv = crate::provision::list_nvidia_gpus();
    if !nv.is_empty() {
        env.insert("TM_NVIDIA_GPUS".into(), nv.join("|"));
    }
    apply_main_gpu(root, &mut env);
    env.remove("TM_PORTAUDIO_DLL");
    if cfg.get("audio_compatibility").and_then(|v| v.as_bool()) == Some(true) {
        env.insert("TM_PORTAUDIO_DLL".into(), crate::audio_recovery::dll_path(root).to_string_lossy().into_owned());
    }
    let ignored = if cfg.get("audio_ignore_enabled").and_then(|v| v.as_bool()) == Some(true) {
        cfg.get("ignored_audio_devices").cloned().unwrap_or_else(|| serde_json::json!([]))
    } else { serde_json::json!([]) };
    env.insert("TM_AUDIO_IGNORED".into(), ignored.to_string());
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
    // 越界的序号比不设还糟：`CUDA_VISIBLE_DEVICES` 指向不存在的设备时，CUDA 报的
    // 是 0 个设备，`is_available()` 直接变 false，引擎会静默退到 DirectML 甚至 CPU。
    // 用户看到的是「显存不足」，跟他动过的那个下拉框看不出任何关系。
    //
    // 这种脏序号是真会存在的：早先的列表来自注册表的显示适配器枚举，里面混着已
    // 禁用的卡和残留的驱动键，存下来的下标换到 CUDA 那边可能根本没有对应设备；
    // 用户换掉一块卡之后，旧配置里的下标同样会悬空。宁可当「自动」。
    let avail = crate::provision::list_nvidia_gpus().len() as i64;
    if avail == 0 || idx >= avail {
        crate::logging::shell_log!(
            "main_gpu={idx} 超出可用 N 卡数量（{avail}），按自动处理，不设 CUDA_VISIBLE_DEVICES"
        );
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

/// 当前该起哪一种 worker。纯 DSP 绝不能去拉 torch。
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WorkerKind {
    Rvc,
    Dsp,
}

impl WorkerKind {
    fn as_str(self) -> &'static str {
        match self {
            WorkerKind::Rvc => "rvc",
            WorkerKind::Dsp => "dsp",
        }
    }
}

pub fn dsp_requested(root: &Path) -> bool {
    crate::config::wants_dsp(&crate::config::read(root))
}

pub fn worker_kind_of(root: &Path) -> Option<WorkerKind> {
    if !is_worker_alive(root) {
        return None;
    }
    let st = protocol::read_status(root);
    match st.get("worker_kind").and_then(|v| v.as_str()) {
        Some("dsp") => Some(WorkerKind::Dsp),
        Some("rvc") => Some(WorkerKind::Rvc),
        _ => Some(WorkerKind::Rvc),
    }
}

fn worker_ready_for_commands(root: &Path) -> bool {
    if !is_worker_alive(root) {
        return false;
    }
    status_looks_ready(&protocol::read_status(root))
}

fn worker_script_for(root: &Path, kind: WorkerKind) -> std::path::PathBuf {
    match kind {
        WorkerKind::Dsp => paths::dsp_worker_script(root),
        WorkerKind::Rvc => paths::worker_script(root),
    }
}

pub fn get_live_pid(root: &Path) -> u32 {
    // 台账里的 pid 必须参与判定。只看 worker.pid / status.pid 时：
    // adopt 之后若文件被清掉、或 python 还没回写，is_worker_alive 会变 false，
    // 另一路 start_worker 就会再开一个 —— 这就是「假启动 / 双 worker」的残留口子。
    for pid in known_worker_pids(root) {
        if pid == 0 {
            continue;
        }
        if pid_is_our_worker(root, pid) {
            // 进程还活着但 pid 文件丢了：补回，免得下一秒又被当成没 worker。
            if protocol::read_worker_pid_file(root) != pid {
                let _ = protocol::write_worker_pid(root, pid);
            }
            return pid;
        }
        // Stale dead entry in the primary pid file
        if !pid_alive(pid) && protocol::read_worker_pid_file(root) == pid {
            protocol::clear_worker_pid(root);
            forget_identity(pid);
        }
    }
    0
}

pub fn is_worker_alive(root: &Path) -> bool {
    get_live_pid(root) > 0
}

/// 所有可能是我们 worker 的 pid：当前 pid 文件、status 里的、以及我们自己
/// spawn 过的那本台账。去重后返回。
fn known_worker_pids(root: &Path) -> Vec<u32> {
    let mut out = vec![
        protocol::read_worker_pid_file(root),
        protocol::status_pid(root),
    ];
    out.extend(protocol::read_spawned_pids(root));
    out.retain(|p| *p != 0);
    out.sort_unstable();
    out.dedup();
    out
}

/// True when *img* sits under *dir* (Windows path, case-insensitive).
fn path_is_under(dir: &Path, img: &str) -> bool {
    let d = dir
        .to_string_lossy()
        .replace('/', "\\")
        .trim_end_matches('\\')
        .to_ascii_lowercase();
    let i = img.replace('/', "\\").to_ascii_lowercase();
    !d.is_empty() && (i == d || i.starts_with(&(d.clone() + "\\")))
}

/// (pid, parent_pid, image_path) for every live python.exe / pythonw.exe.
#[cfg(windows)]
fn iter_python_procs() -> Vec<(u32, u32, String)> {
    use std::ffi::OsString;
    use std::os::windows::ffi::OsStringExt;
    use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W,
        TH32CS_SNAPPROCESS,
    };
    let snap = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) };
    if snap.is_null() || snap == INVALID_HANDLE_VALUE {
        return Vec::new();
    }
    let mut pe: PROCESSENTRY32W = unsafe { std::mem::zeroed() };
    pe.dwSize = std::mem::size_of::<PROCESSENTRY32W>() as u32;
    let mut out = Vec::new();
    unsafe {
        if Process32FirstW(snap, &mut pe) != 0 {
            loop {
                let end = pe
                    .szExeFile
                    .iter()
                    .position(|&c| c == 0)
                    .unwrap_or(pe.szExeFile.len());
                let name = OsString::from_wide(&pe.szExeFile[..end])
                    .to_string_lossy()
                    .to_ascii_lowercase();
                if name == "python.exe" || name == "pythonw.exe" {
                    let pid = pe.th32ProcessID;
                    let parent = pe.th32ParentProcessID;
                    let img = pid_image_path(pid);
                    if !img.is_empty() {
                        out.push((pid, parent, img));
                    }
                }
                if Process32NextW(snap, &mut pe) == 0 {
                    break;
                }
            }
        }
        CloseHandle(snap);
    }
    out
}

#[cfg(not(windows))]
fn iter_python_procs() -> Vec<(u32, u32, String)> {
    Vec::new()
}

/// 壳自己拉起来的一次性任务（STS / 训练 / 分离 / TTS）。关变声时不能杀它们。
static TOOL_PIDS: Mutex<Vec<u32>> = Mutex::new(Vec::new());

/// 记住一个工具子进程，函数返回时自动忘掉。
pub struct ToolPidGuard {
    pid: u32,
}

impl ToolPidGuard {
    pub fn new(pid: u32) -> Self {
        if pid != 0 {
            let mut g = TOOL_PIDS.lock().unwrap_or_else(|e| e.into_inner());
            if !g.contains(&pid) {
                g.push(pid);
            }
        }
        Self { pid }
    }
}

impl Drop for ToolPidGuard {
    fn drop(&mut self) {
        if self.pid == 0 {
            return;
        }
        let mut g = TOOL_PIDS.lock().unwrap_or_else(|e| e.into_inner());
        g.retain(|p| *p != self.pid);
    }
}

fn protected_tool_pids() -> Vec<u32> {
    TOOL_PIDS
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .clone()
}

/// Live python.exe / pythonw.exe whose image path sits under `dir`.
///
/// 补全/切换运行时用：is_worker_alive 只认实时 worker 台账，原版 WebUI
/// 和实时面板是 spawn_detached 出去的、不在台账里；它们还开着的时候
/// rename 运行时目录就是「拒绝访问 (os error 5)」。先扫出来让用户关，
/// 别下到一半才撞在锁上。
pub fn pythons_under(dir: &Path) -> Vec<u32> {
    iter_python_procs()
        .into_iter()
        .filter(|(_, _, img)| path_is_under(dir, img))
        .map(|(pid, _, _)| pid)
        .collect()
}

/// Kill Runtime python processes.
///
/// * `orphans_only` — leftovers after **强制结束** / 关应用. Parent-dead
///   **or** reparented onto this shell. 普通「停止变声」走软停，不调这里。
///   STS / train / separate / TTS pids the shell itself spawned are skipped.
/// * otherwise — every python whose image lives under Runtime. Used on
///   关闭应用 so nothing is left behind.
///
/// Returns how many were killed — 启动时的那次调用要拿它写日志。
pub fn kill_runtime_pythons(root: &Path, orphans_only: bool) -> usize {
    let rt = paths::runtime_dir(root);
    let shell = std::process::id();
    let tools = protected_tool_pids();
    let mut killed = 0usize;
    for (pid, parent, img) in iter_python_procs() {
        if !path_is_under(&rt, &img) {
            continue;
        }
        if orphans_only {
            if tools.contains(&pid) {
                continue;
            }
            // 父进程还活着，且不是本壳：别人的 python，别动。
            // 父进程已死，或已被 Windows 过继到本壳：worker 留下的 AudioIo。
            if pid_alive(parent) && parent != shell {
                continue;
            }
        }
        append_log(
            root,
            &format!(
                "kill_tree runtime python pid={pid} parent={parent} orphans_only={orphans_only}"
            ),
        );
        kill_tree(pid);
        killed += 1;
    }
    killed
}

/// 上一次是被强杀 / 崩掉的：训练、分离、STS、TTS 的 python 都是我们 spawn
/// 出来的独立进程，壳一死它们不死，还攥着显存继续跑。
///
/// 26.8.18 的用户就栽在这里：窗口黑了他去任务管理器结束进程，训练进程活
/// 得好好的继续跑了五分钟；重开之后界面显示「空闲」，他再点一次开始训练，
/// 两个进程抢同一张 8G 卡 —— 那时候才是真卡死。
///
/// `reap_orphan_workers` 只认实时 worker 的 pid 台账，工具进程不在里面，
/// 所以这里单独扫一遍。判据和 `orphans_only` 一致：父进程已死，或者已被
/// Windows 过继到本壳。别人那份还活着的 App 不受影响（它的 python 父进程
/// 活着且不是本壳）。
pub fn reap_orphan_tool_pythons(root: &Path) {
    let n = kill_runtime_pythons(root, true);
    if n > 0 {
        crate::logging::shell_log!("收掉 {n} 个上次留下的 Runtime python（训练/分离/合成的残留）");
    }
}

/// Kill only PIDs that still look like this product's worker.
pub fn kill_known_workers(root: &Path) {
    for pid in known_worker_pids(root) {
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
    protocol::clear_spawned_pids(root);
    forget_identity_cache();
    let mut fields = Map::new();
    fields.insert("state".into(), json!("idle"));
    fields.insert("pid".into(), json!(0));
    // 同上：底栏读的就是这一条，写死英文等于八种语言都显示 "workers cleared"。
    fields.insert("message_code".into(), json!("engine.stopped"));
    fields.insert("message".into(), json!("workers cleared"));
    fields.insert("error".into(), json!(""));
    // 种类也要清。status.json 是合并写的，杀掉 DSP worker 之后这里还留着
    // worker_kind="dsp"，`worker_kind_of` 就会对着一个已经不存在的进程回答
    // 「现在跑的是 DSP」—— 换回 RVC 的判断从第一步就错了。
    fields.insert("worker_kind".into(), json!(""));
    fields.insert("dsp_only".into(), json!(false));
    fields.insert("delay_ms".into(), json!(0));
    fields.insert("infer_ms".into(), json!(0));
    let _ = protocol::write_status_merge(root, fields);
}

/// 启动时收掉上几次留下的孤儿 worker，保留当前这个。
///
/// 关到托盘故意不杀 worker：还要接着变声，下次打开也省掉冷启动。
/// 真正退出（Exit / 关闭应用）会走 `kill_known_workers` + Runtime python 清扫。
/// 这里只碰台账里记过的 pid（都是我们自己 spawn 的），不做全系统进程枚举。
pub fn reap_orphan_workers(root: &Path) {
    let keep = protocol::read_worker_pid_file(root);
    let mut reaped = 0usize;
    for pid in known_worker_pids(root) {
        if pid == keep || !pid_is_our_worker(root, pid) {
            continue;
        }
        append_log(root, &format!("kill_tree 孤儿 worker pid={pid}（上次启动留下的）"));
        kill_tree(pid);
        reaped += 1;
    }
    // 台账重置成「只有当前这个」。留着死 pid 除了让下次启动白检查一遍，
    // 还会在 pid 被系统复用之后指向别人的进程。
    protocol::clear_spawned_pids(root);
    if keep != 0 {
        let _ = protocol::remember_spawned_pid(root, keep);
    }
    if reaped > 0 {
        forget_identity_cache();
        crate::logging::shell_log!("清掉 {reaped} 个孤儿 worker（保留 pid={keep}）");
    }
}

pub fn start_worker(root: &Path) -> Result<(), String> {
    let kind = if dsp_requested(root) {
        WorkerKind::Dsp
    } else {
        WorkerKind::Rvc
    };
    start_worker_kind(root, kind)
}

/// spawn 指纹的组成：进程真正吃到的策略环境变量（TM_ACCEL /
/// CUDA_VISIBLE_DEVICES / TM_USE_DML）+ 运行时解释器身份（解析出的
/// pyw 路径）。一律从 spawn 时实际传给子进程的 env 和路径算，不从
/// config 重读 ——「生的时候是旧配置、记指纹时读到新配置」会把带旧
/// 环境的进程错记成新策略。
///
/// `v2|` 前缀：旧版两字段 `accel|gpu` 指纹永远不等于 v2 —— 缺运行时
/// 身份的旧记录一律按不兼容处理。
/// `pub(crate)`：sts.rs 常驻进程用同一个公式给自己的 env/解释器打指纹，
/// 别开第二套算法。
pub(crate) fn spawn_fingerprint_for(env: &HashMap<String, String>, pyw: &Path) -> String {
    let pick = |k: &str| env.get(k).map(|v| v.trim().to_string()).unwrap_or_default();
    // Windows 路径统一小写+反斜杠再比，同一运行时只因写法不同不算换。
    let rt = pyw.to_string_lossy().replace('/', "\\").to_ascii_lowercase();
    format!(
        "v2|{}|{}|{}|{rt}",
        pick("TM_ACCEL"),
        pick("CUDA_VISIBLE_DEVICES"),
        pick("TM_USE_DML"),
    )
}

/// 「现在立刻 spawn 会得到什么身份」：和 spawn 走同一条数据通路
/// （env_for_runtime + runtime_pythonw）。运行时缺失返回 None ——
/// 「现在没法 spawn」不等于「随便谁都兼容」。
pub(crate) fn current_spawn_fingerprint(root: &Path) -> Option<String> {
    let pyw = paths::runtime_pythonw(root)?;
    let env = env_for_runtime(root);
    Some(spawn_fingerprint_for(&env, &pyw))
}

fn fingerprint_path(root: &Path) -> PathBuf {
    paths::control_dir(root).join("worker.fingerprint")
}

fn read_spawn_fingerprint(root: &Path) -> String {
    std::fs::read_to_string(fingerprint_path(root))
        .map(|s| s.trim().to_string())
        .unwrap_or_default()
}

/// 落盘出生指纹 vs 现在 spawn 会用的指纹。纯文件读 + 策略重算，
/// 不查活、不碰进程。指纹缺失（老版本起的进程）或旧格式一律不兼容。
fn saved_spawn_policy_matches_current(root: &Path) -> bool {
    let saved = read_spawn_fingerprint(root);
    !saved.is_empty() && current_spawn_fingerprint(root).as_deref() == Some(saved.as_str())
}

/// Agent I 的只读查询：活着的实时 worker 是不是带着「现在请求的那套
/// CPU/GPU/运行时策略」出生的。不杀进程、不改状态、不写文件 ——
/// false 只代表「不能证明兼容」（死了 / 没指纹 / 旧格式 / 策略变了），
/// 离线侧要不要换路由由调用方决定，这里不做任何处置。
/// 发布给 sts.rs round4 复用实时进程前判定（run_hot 已接）。
pub(crate) fn live_worker_matches_current_spawn_policy(root: &Path) -> bool {
    is_worker_alive(root) && saved_spawn_policy_matches_current(root)
}

/// 把这个进程出生时的策略指纹落盘。env/pyw 必须是刚传给子进程的那一份，
/// 不许在里面重读 config。
fn write_spawn_fingerprint(root: &Path, env: &HashMap<String, String>, pyw: &Path) {
    let _ = std::fs::write(fingerprint_path(root), spawn_fingerprint_for(env, pyw));
}

/// 起指定种类的 worker。种类不对就先杀掉再开 —— 纯 DSP 不能卡在
/// 「正在导入推理库」上等 torch。
pub fn start_worker_kind(root: &Path, kind: WorkerKind) -> Result<(), String> {
    // Recover from poisoning instead of failing forever: one panic while
    // starting would otherwise make the engine unstartable for the rest of the
    // session, with a restart as the only way out. The lock guards a re-check
    // that is idempotent, so a poisoned state is safe to continue from.
    let _guard = START_LOCK.lock().unwrap_or_else(|e| e.into_inner());

    // 离线语音转换的常驻 python 攥着 hubert + rmvpe + net_g 不放。实时变声要
    // 的是同一张卡的同一块显存，小显存机器上两边一起在就是开不起来。先放掉。
    crate::sts::release_resident();

    if is_worker_alive(root) {
        if worker_kind_of(root) == Some(kind) {
            return Ok(());
        }
        crate::logging::shell_log!(
            "worker kind {:?} → {:?}, replacing",
            worker_kind_of(root),
            kind
        );
        let _ = send_command(root, "stop", Map::new());
        thread::sleep(Duration::from_millis(200));
        kill_known_workers(root);
        thread::sleep(Duration::from_millis(200));
    }

    // Clear dead bookkeeping; only kill confirmed ours
    kill_known_workers(root);
    thread::sleep(Duration::from_millis(200));
    if is_worker_alive(root) && worker_kind_of(root) == Some(kind) {
        return Ok(());
    }
    if is_worker_alive(root) {
        kill_known_workers(root);
        thread::sleep(Duration::from_millis(200));
    }

    let script = worker_script_for(root, kind);
    if !script.is_file() {
        return Err(crate::i18n::te("s.fd40e2e936", &script.display()));
    }
    let pyw = paths::runtime_pythonw(root).ok_or_else(|| {
        crate::i18n::te("s.e8edbd3cce", &root.display())
    })?;

    protocol::ensure_control_dir(root).map_err(|e| e.to_string())?;

    // 音频设备枚举会不会把进程带走？值得一探，但不值得每次都探。
    //
    // 探一次要起一个 Python 进程，一两秒起步；正常机器上这钱白花。所以只在
    // 本次会话已经有 worker 被系统终止过的时候才去踩：第一次崩照崩（拦不住，
    // 那时还没有任何迹象），第二次点开启之前就能把祸首指出来，而不是让用户
    // 像 26.8.21 那位一样点满九次。
    if crate::crash::saw_fatal_exit() {
        if let Some(reason) = crate::audio_probe::blocking_reason(root) {
            let mut fields = Map::new();
            fields.insert("state".into(), json!("error"));
            fields.insert("error".into(), json!(reason.clone()));
            fields.insert("message".into(), json!(""));
            fields.insert("message_code".into(), json!(""));
            fields.insert("pid".into(), json!(0));
            fields.insert("progress".into(), json!(0));
            let _ = protocol::write_status_merge(root, fields);
            append_log(root, &format!("拒绝启动 worker：{reason}"));
            return Err(reason);
        }
    }

    let mut fields = Map::new();
    fields.insert("state".into(), json!("starting"));
    // 带上 code，别只写一句英文：这条会直接显示在底栏状态行上，而 status.json
    // 里的 message 只有在下一次写入时才会变 —— 用 code 的话，用户中途换语言，
    // `localize_status` 每次读都会重新解析成当前语言。
    fields.insert("message_code".into(), json!("engine.launching"));
    fields.insert("message".into(), json!("launching worker…"));
    fields.insert("error".into(), json!(""));
    fields.insert("pid".into(), json!(0));
    fields.insert("worker_kind".into(), json!(kind.as_str()));
    if kind == WorkerKind::Dsp {
        fields.insert("dsp_only".into(), json!(true));
        fields.insert("function".into(), json!("fx"));
        fields.insert("message_code".into(), json!("engine.dsp_starting"));
        fields.insert("message".into(), json!("正在启动 DSP 变声…"));
    }
    let _ = protocol::write_status_merge(root, fields);

    append_log(
        root,
        &format!(
            "\n===== launch ts={} kind={} (tauri shell) =====\nROOT={}\nvia: {} {}",
            stamp(),
            kind.as_str(),
            root.display(),
            pyw.display(),
            script.display()
        ),
    );

    let mut env = env_for_runtime(root);
    env.insert("TM_WORKER_KIND".into(), kind.as_str().into());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let log_path = crate::logging::daily_path(root, crate::logging::CH_WORKER);
        let log_file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
            .ok();
        // CREATE_NO_WINDOW 对 pythonw 无害，对 python.exe 回退是必须的。
        // 子进程（AudioIoProcess）走 multiprocessing CreateProcess，不吃这个
        // 标志 —— 那边在 worker_protocol.hide_multiprocessing_windows 补。
        let mut flags = 0x00000200u32; // CREATE_NEW_PROCESS_GROUP
        flags |= 0x08000000; // CREATE_NO_WINDOW
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
            .map_err(|e| crate::i18n::te("s.7611f15dff", &e))?;
        crate::win_realtime::boost_child(&child);
        append_log(root, &format!("spawned shell-side pid={}", child.id()));
        adopt_spawned(root, child.id());
        watch_exit(root, child);
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
            .map_err(|e| crate::i18n::te("s.7611f15dff", &e))?;
        adopt_spawned(root, child.id());
        watch_exit(root, child);
    }

    // 记下这个进程出生时的策略指纹：后端/显卡/运行时之后被改过的话，
    // 下次用户点开始就能把还活着但带旧环境的 worker 换掉。指纹从刚传给
    // 子进程的 env 和 pyw 算 —— 这里不许再读 config。
    write_spawn_fingerprint(root, &env, &pyw);
    Ok(())
}

/// spawn 完立刻认领这个 pid，别等 python 自己写 `worker.pid`。
///
/// worker 冷启动要几十秒（torch/faiss/CUDA），这段时间里 `worker.pid` 还是空的、
/// status 里的 pid 还是 0，`is_worker_alive` 于是一路返回 false。而启动预热
/// （lib.rs 的后台线程）和界面拉设备列表（list_devices_blocking）是两条并行的
/// 路，各自都会调 `start_worker` —— START_LOCK 只保证它们不同时进函数，
/// 保证不了后进来的那个看见前一个的成果。结果就是**一次启动开出两个 worker**：
/// 两个进程抢同一个声卡、抢着往同一份 status.json 里写，界面显示「引擎就绪」
/// 但变声根本出不了声。
///
/// 更糟的是退出时只按 `worker.pid` 杀，那里只记得住后写的那个，另一个就此变成
/// 孤儿 —— 它会活过软件的每一次重启，直到用户重启电脑或者装新版本。用户报的
/// 「除非彻底重启电脑否则不会自己好」就是这个。
fn adopt_spawned(root: &Path, pid: u32) {
    if pid == 0 {
        return;
    }
    // pid 会被系统复用：上一个用这个号的进程怎么死的，跟眼前这个没关系。
    crate::crash::forget_exit(pid);
    let _ = protocol::write_worker_pid(root, pid);
    let _ = protocol::remember_spawned_pid(root, pid);
    // 直接记成「是我们的」，别让它去走镜像路径比对。
    //
    // 那条比对是防 pid 复用的，对刚 spawn 出来的进程既没必要也不安全：进程刚
    // 建好的头几毫秒 `QueryFullProcessImageNameW` 可能还问不出路径，而结论会被
    // 缓存住 —— 一次「不是我们的」就会粘住这个 pid 的一辈子，于是我们自己刚开
    // 的 worker 从此认不出来，退出时也杀不掉。
    //
    // 我们是拿产品 Runtime 里的 pythonw 启的它，这件事不需要再问操作系统。
    remember_identity(pid, true);
    let mut fields = Map::new();
    fields.insert("pid".into(), json!(pid));
    let _ = protocol::write_status_merge(root, fields);
}

/// 收 worker 的退出码。
///
/// 以前这里是 `std::mem::forget(child)`，理由写的是「worker 会 re-parent，自己
/// 写 pid」。前半句对 pythonw 这条路不成立：`spawned shell-side pid=` 和 worker
/// 日志里的 pid 是同一个，句柄就是它本人。代价是进程被系统终止时退出码没人收，
/// 日志里连一行都没有 —— 26.8.21 那位连点九次开启变声，九次都是 PortAudio 探
/// ASIO 驱动时被 0xC0000094 带走，诊断包里翻不出任何痕迹。
///
/// 等在后台线程里，不挡任何人。`wait()` 也顺手把句柄还给系统。
fn watch_exit(root: &Path, mut child: std::process::Child) {
    let pid = child.id();
    let root = root.to_path_buf();
    let _ = thread::Builder::new()
        .name(format!("worker-exit-{pid}"))
        .spawn(move || {
            let code = match child.wait() {
                Ok(st) => st.code(),
                Err(_) => return,
            };
            let Some(code) = code else { return };
            crate::crash::record_exit(pid, code);
            if crate::crash::is_fatal_status(code) {
                let desc = crate::crash::describe(code);
                append_log(&root, &format!("worker pid={pid} 被系统终止，退出码 {desc}"));
                crate::logging::shell_log!("worker pid={} 被系统终止，退出码 {}", pid, desc);
            } else if code != 0 {
                append_log(&root, &format!("worker pid={pid} 退出，退出码 {code}"));
            }
        });
}

/// 「引擎进程为什么没了」——能说出退出码就说，说不出就退回旧那句。
///
/// 退出码由 `watch_exit` 的线程回填，进程刚没的那一瞬间可能还没到，所以这里给
/// 它半秒。等不到也不硬等：没有退出码一样要把话说完整。
fn death_reason(pid: u32) -> String {
    let deadline = Instant::now() + Duration::from_millis(500);
    loop {
        if let Some(code) = crate::crash::exit_code_of(pid) {
            if crate::crash::is_fatal_status(code) {
                return crate::i18n::te("s.wkKilledBySystem", &crate::crash::describe(code));
            }
            return crate::i18n::te("s.wkExitedWithCode", &code);
        }
        if Instant::now() >= deadline {
            return crate::i18n::t("s.wkDiedDuringLoad");
        }
        thread::sleep(Duration::from_millis(50));
    }
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
            // 这几条是现算现返给界面的，不落 status.json，所以直接按当前语言
            // 取文案就行 —— 不像上面那些写盘的，需要留 code 等下次解析。
            let died = death_reason(pid);
            return json!({
                "state": "error",
                "error": last.get("error").and_then(|v| v.as_str()).filter(|s| !s.is_empty()).unwrap_or(&died),
                "message": &crate::i18n::t("s.wkPidNotAlive"),
                "pid": 0
            });
        }
        thread::sleep(Duration::from_millis(250));
    }
    let timeout = crate::i18n::t("s.wkReadyTimeout");
    if last.as_object().map(|o| o.is_empty()).unwrap_or(true) {
        json!({"state": "error", "error": &timeout, "pid": 0})
    } else if !is_worker_alive(root) {
        json!({
            "state": "error",
            "error": last.get("error").and_then(|v| v.as_str()).filter(|s| !s.is_empty()).unwrap_or(&timeout),
            "message": &crate::i18n::t("s.wkStartTimeout"),
            "pid": 0
        })
    } else {
        last
    }
}

/// command.seq 是读改写计数器、command.json 是单槽邮箱，两者都只能在这一把
/// 锁里动：要发命令的线程先拿派发权，再等上一条被认领、再领号、再落邮箱。
/// 不串行的话，两个线程会领到同一个 seq —— 后落邮箱的把先落的顶掉，被顶的
/// 那条命令永远没人执行（R05）。
///
/// 派发权按 root 分：邮箱本来就是每个产品目录一份，不同 root 之间串行只是
/// 互相拖时间（测试并发跑各自的临时目录时尤其明显）。
static COMMAND_DISPATCH: LazyLock<Mutex<HashMap<PathBuf, std::sync::Arc<Mutex<()>>>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

fn dispatch_permit(root: &Path) -> std::sync::Arc<Mutex<()>> {
    let mut map = COMMAND_DISPATCH
        .lock()
        .unwrap_or_else(|e| e.into_inner());
    map.entry(root.to_path_buf())
        .or_insert_with(|| std::sync::Arc::new(Mutex::new(())))
        .clone()
}

/// Worker 命令循环约 80ms 一轮；3s 盖住繁忙 GC / 磁盘抖动。超过仍不认领就让
/// **本次**派发有界失败：邮箱里那条 pending 原样保留 —— 它的调用方拿到的是
/// Ok(seq)（已入队），worker 之后认领了照样执行，不能替它宣布失败。覆盖它则
/// 是把已接受的命令悄悄丢掉（start/stop/换模型丢一条，界面就说谎一次）。
const CMD_ACK_TIMEOUT_MS: u64 = 3_000;

/// Pending 是否已被当前这轮 worker 判死：worker 启动时按 ts 丢弃上一轮残留
/// （gui_v1 / dsp_worker 的 boot 丢弃：`cmd_ts < worker_boot_ts - 1.0` 的命令
/// 永不执行）。壳这边用同一份证据：pending 比当前 worker 的启动还早，它就是
/// 死信，覆盖不算丢。没有启动证据（状态里没有 worker_boot_ts）就当作活的。
fn pending_is_pre_boot(pending: &Value, status: &Value) -> bool {
    let boot_ts = status
        .get("worker_boot_ts")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0);
    if boot_ts <= 0.0 {
        return false;
    }
    let cmd_ts = pending.get("ts").and_then(|v| v.as_f64()).unwrap_or(0.0);
    cmd_ts > 0.0 && cmd_ts < boot_ts - 1.0
}

pub fn send_command(root: &Path, cmd: &str, payload: Map<String, Value>) -> Result<u64, String> {
    send_command_wait(root, cmd, payload, CMD_ACK_TIMEOUT_MS)
}

fn send_command_wait(
    root: &Path,
    cmd: &str,
    payload: Map<String, Value>,
    ack_timeout_ms: u64,
) -> Result<u64, String> {
    // command.json is a single-slot mailbox. The worker polls ~every 80 ms and
    // only keeps the latest file contents. If the shell writes set → start → set
    // faster than that poll, `start` is overwritten and never runs — the dock
    // freezes on「引擎就绪 / 参数已应用」(diag 26.8.6/bug/1: many set/stop,
    // zero start after relaunch). Wait for the previous command to be claimed
    // (status.last_cmd_seq) before replacing the mailbox.
    //
    // 预算从入口算：拿派发权和等认领共用同一个 deadline。不限制拿锁的话，
    // N 个并发派发各自再等 ack 3s，队尾的 stop 能排出 N*3s——「有界」就名不
    // 副实。锁拿不到就失败本次派发，邮箱里的 pending 原样保留。
    let deadline = Instant::now() + Duration::from_millis(ack_timeout_ms);
    let permit = dispatch_permit(root);
    let _dispatch = loop {
        match permit.try_lock() {
            Ok(g) => break g,
            Err(TryLockError::WouldBlock) => {
                if Instant::now() >= deadline {
                    return Err(format!("{}: dispatch", engine_busy_msg()));
                }
                thread::sleep(Duration::from_millis(15));
            }
            Err(TryLockError::Poisoned(_)) => {
                return Err("command dispatch lock poisoned".to_string());
            }
        }
    };
    let pending = protocol::read_command(root);
    let pending_seq = pending
        .get("seq")
        .and_then(|v| v.as_u64().or_else(|| v.as_i64().map(|i| i as u64)))
        .unwrap_or(0);
    let status = protocol::read_status(root);
    let last_ack = status
        .get("last_cmd_seq")
        .and_then(|v| v.as_u64().or_else(|| v.as_i64().map(|i| i as u64)))
        .unwrap_or(0);
    if pending_seq > last_ack && !pending_is_pre_boot(&pending, &status) {
        let remain = deadline
            .saturating_duration_since(Instant::now())
            .as_millis() as u64;
        if remain == 0 || !protocol::wait_cmd_acked(root, pending_seq, remain) {
            // 有界失败：不覆盖、不作废 pending。它的调用方早已拿到 Ok(seq)，
            // worker 认领后仍会执行 —— 这里替它失败才会真丢命令。
            append_log(
                root,
                &format!(
                    "send_command: previous seq={pending_seq} not acked within {ack_timeout_ms}ms; {cmd} not dispatched (last_ack={last_ack})"
                ),
            );
            return Err(format!(
                "{}: seq={pending_seq}",
                engine_busy_msg(),
            ));
        }
    }
    protocol::write_command(root, cmd, payload).map_err(|e| e.to_string())
}

/// 「引擎正忙，上一条命令还没被接收」。locales 归 Agent I；key 落地前
/// t() 会原样返回 key 名，兜底复用现有的「等引擎就绪超时」文案（8 个
/// locale 都有），不落生英语。
fn engine_busy_msg() -> String {
    // 字面 key：静态检查器扫 t() 的字符串参数，常量会漏检。
    let s = crate::i18n::t("s.engineCmdBusy");
    if s == "s.engineCmdBusy" {
        crate::i18n::t("s.wkReadyTimeout")
    } else {
        s
    }
}

/// 「引擎没有确认音色已应用」。同上：正式 key 由 Agent I 落地，兜底先用
/// wkReadyTimeout，保证界面看到的是人话而不是 `s.xxx`。
fn model_apply_unconfirmed_msg() -> String {
    let s = crate::i18n::t("s.modelApplyUnconfirmed");
    if s == "s.modelApplyUnconfirmed" {
        crate::i18n::t("s.wkReadyTimeout")
    } else {
        s
    }
}

/// 换模型 committed 等待上限：冷权重（hubert + net_g）冷读可能几十秒。
const MODEL_APPLY_TIMEOUT_MS: u64 = 90_000;
/// 启动已到 running 之后等应用记录落盘的上限（同一循环内写完，正常 <1s）。
pub const MODEL_APPLY_CONFIRM_MS: u64 = 20_000;

/// 路径比较统一大小写和分隔符 —— shell/worker 之间的路径串可能只差这些。
fn norm_path(p: &str) -> String {
    p.trim().replace('/', "\\").to_lowercase()
}

/// 等一条跟请求对得上的模型应用记录。
///
/// `phase=="committed"` 只在音频线程把 RVC 指针换上去之后由 worker 发布，
/// 且 seq、pth_path、index_path 三个都要跟这条请求相等 —— 「认领了」
/// （last_cmd_seq）、「还在跑」（state=running）、「model_active 恰好是
/// 这个身份」都不算应用完成：active 只是上一个已应用身份的快照，证明不了
/// **这条**请求被提交过。同模型请求是合法 no-op 时，由 worker 核实推理链
/// 之后为这条 seq 新发一条 committed，壳不猜。
///
/// 早退条件：`model_apply.seq > seq`（应用槽位被新请求接管，这条 seq 的
/// 记录已被覆盖、永远不会出现）；worker 死了（status.json 是残影）；超时
/// —— 超时同时覆盖「worker 没有上报能力」的情形，一律 Err，绝不报假成功。
pub fn wait_model_applied(
    root: &Path,
    seq: u64,
    pth: &str,
    index: &str,
    timeout_ms: u64,
) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_millis(timeout_ms);
    let want_pth = norm_path(pth);
    let want_idx = norm_path(index);
    loop {
        // 先查活：死 worker 留下的 status.json 是上一世的残影，任何字段
        // （包括一条对得上的 committed）都不能当成当前进程的应用证据。
        if !is_worker_alive(root) {
            return Err(crate::i18n::t("s.7764d6bdd2"));
        }
        let st = protocol::read_status(root);
        if let Some(ma) = st.get("model_apply").and_then(|v| v.as_object()) {
            let mseq = ma
                .get("seq")
                .and_then(|v| v.as_u64().or_else(|| v.as_i64().map(|i| i as u64)))
                .unwrap_or(0);
            let mphase = ma.get("phase").and_then(|v| v.as_str()).unwrap_or("");
            let mpth = norm_path(
                ma.get("pth_path").and_then(|v| v.as_str()).unwrap_or(""),
            );
            let midx = norm_path(
                ma.get("index_path").and_then(|v| v.as_str()).unwrap_or(""),
            );
            if seq > 0 && mseq == seq && mpth == want_pth && midx == want_idx {
                match mphase {
                    "committed" => return Ok(()),
                    "failed" => {
                        let detail = ma
                            .get("error")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string();
                        return Err(if detail.is_empty() {
                            model_apply_unconfirmed_msg()
                        } else {
                            detail
                        });
                    }
                    _ => {} // loading/selected 等中间态：继续等
                }
            } else if mseq > seq {
                // 更新的请求接管了应用槽位：这条 seq 的记录已被覆盖，
                // 永远不会再出现，立即失败而不是傻等。
                return Err(model_apply_unconfirmed_msg());
            }
            // mseq < seq：更早请求留下的旧记录，不是这条的结论 —— 继续等。
        }
        if Instant::now() >= deadline {
            return Err(model_apply_unconfirmed_msg());
        }
        thread::sleep(Duration::from_millis(150));
    }
}

/// Ensure worker is up; refresh device list if empty. Does not hold UI locks.
pub fn ensure_worker_and_devices(root: &Path, timeout_ms: u64) -> Value {
    let kind = if dsp_requested(root) {
        WorkerKind::Dsp
    } else {
        WorkerKind::Rvc
    };
    if worker_kind_of(root) != Some(kind) || !is_worker_alive(root) {
        if let Err(e) = start_worker_kind(root, kind) {
            return json!({"state": "error", "error": e, "pid": 0});
        }
    }
    let wait_ms = if kind == WorkerKind::Dsp {
        timeout_ms.min(20_000)
    } else {
        timeout_ms
    };
    let st = wait_worker_ready(root, wait_ms);
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
    // 派发失败不能拿盘上旧列表冒充本次刷新 —— 如实报 error。
    let seq = match send_command(root, "list_devices", Map::new()) {
        Ok(s) => s,
        Err(e) => return json!({"state": "error", "error": e, "pid": 0}),
    };
    let deadline = Instant::now() + Duration::from_millis(timeout_ms.min(30_000));
    while Instant::now() < deadline {
        let st = protocol::read_status(root);
        // 只认 devices_seq 对号：worker 在枚举收尾时才写它，非空设备列表
        // 可能只是上一次刷新留下的旧数据。
        let done = st
            .get("devices_seq")
            .and_then(|v| v.as_u64().or_else(|| v.as_i64().map(|i| i as u64)))
            .unwrap_or(0)
            >= seq;
        if done {
            return st;
        }
        if !is_worker_alive(root) {
            return json!({"state": "error", "error": &crate::i18n::t("s.wkDiedListDevices"), "pid": 0});
        }
        thread::sleep(Duration::from_millis(200));
    }
    json!({"state": "error", "error": crate::i18n::t("s.wkReadyTimeout"), "pid": 0})
}

/// `start` / `set` 命令里那几个 DSP 字段，按**唯一**的判定 `config::wants_dsp` 生成。
///
/// 抽出来是为了能测：这几个键以前在 `start_vc` 和 `push_running_hot` 里各写了
/// 一遍，判定条件还和 `wants_dsp` 不一样（不看 pth_path、不看 function，比它
/// 松）。后果是壳按 wants_dsp 选了 RVC worker，转头又在命令里告诉它
/// 「dsp_enabled=true, function=fx」——「DSP 之后换不回 RVC」就是这么来的。
///
/// 非 DSP 时**明确写 false**，不是省略：worker 的 gui_config 是常驻的，
/// 跑过一次纯 DSP 之后那几个字段还在内存里，不覆盖等于沿用上一次。
pub fn dsp_command_fields(cfg: &Map<String, Value>) -> Map<String, Value> {
    let mut out = Map::new();
    if crate::config::wants_dsp(cfg) {
        out.insert("dsp_enabled".into(), json!(true));
        out.insert("function".into(), json!("fx"));
        let preset = cfg
            .get("dsp_preset")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim()
            .to_string();
        if !preset.is_empty() {
            out.insert("dsp_preset".into(), json!(preset));
        }
        if let Some(v) = cfg.get("dsp_params").cloned() {
            if v.as_object().map(|m| !m.is_empty()).unwrap_or(false) {
                out.insert("dsp_params".into(), v);
            }
        }
    } else {
        out.insert("dsp_enabled".into(), json!(false));
        out.insert("dsp_preset".into(), json!(""));
        out.insert("dsp_params".into(), json!({}));
        out.insert(
            "function".into(),
            match cfg.get("function").and_then(|v| v.as_str()) {
                // 残留的 fx 不能带回去：那是上一次纯 DSP 留下的。
                Some(f) if f != "fx" => json!(f),
                _ => json!("vc"),
            },
        );
    }
    out
}

/// `start_vc` 的返回：seq + 派发那一刻冻结的模型身份 + 是否纯 DSP。
/// 身份从同一份配置里读出、随命令本体下发给 worker —— 事后验收也按它
/// 验，不许再读一遍配置去猜当时请求的是谁：启动期间的另一次音色选择
/// 会把配置改走，拿新配置验收旧命令就是假失败。
pub struct StartOutcome {
    pub seq: u64,
    pub pth: String,
    pub index: String,
    pub dsp: bool,
}

/// Soft-stop then start (same order as Tk shell before start_vc_remote).
pub fn start_vc_with_bridge(
    root: &Path,
    bridge: Option<&crate::audio_bus::BridgeDescriptor>,
) -> Result<StartOutcome, String> {
    // 锁里再读一次：补上预设参数，避免用过期的空 DSP 把 inuse 盖掉。
    // 必须在选 worker 之前：dsp_enabled 决定走哪条进程。
    let cfg = crate::config::prepare_vc_start(root).unwrap_or_else(|_| crate::config::read(root));
    let dsp_on = crate::config::wants_dsp(&cfg);
    let want = if dsp_on {
        WorkerKind::Dsp
    } else {
        WorkerKind::Rvc
    };
    // 纯 DSP：RVC worker 还在 import torch 时立刻换掉，不要让用户等。
    // RVC worker 已经 idle/running 则复用（里面也有 numpy DSP 路径）。
    let keep_rvc_for_dsp = dsp_on
        && worker_kind_of(root) == Some(WorkerKind::Rvc)
        && worker_ready_for_commands(root);
    let kind = if keep_rvc_for_dsp {
        WorkerKind::Rvc
    } else {
        want
    };
    // 后端/主显卡的改动只在进程 spawn 时进环境变量。活着的 worker 指纹
    // 对不上 = 它带着上一套环境 —— 用户现在点了「开始」，新选择必须生效。
    // 这一步只发生在用户主动 start 的路径上；改设置那一刻绝不动在跑的流。
    // 指纹文件缺失（旧版 worker 起的进程）按对不上处理。
    if is_worker_alive(root) && !saved_spawn_policy_matches_current(root) {
        crate::logging::shell_log!("worker spawn policy fingerprint changed; restarting worker");
        kill_known_workers(root);
        thread::sleep(Duration::from_millis(200));
    }
    if worker_kind_of(root) != Some(kind) || !is_worker_alive(root) {
        start_worker_kind(root, kind)?;
    }
    // 导入推理库时 worker 已经活着，但命令环还没起来。这时候写下的 start
    // 会被 gui_v1 当成上一轮残留丢掉。先等到 idle/running 再发命令。
    // 纯 DSP worker 几秒就就绪，不必按 torch 的 100 秒等。
    let ready_ms = if kind == WorkerKind::Dsp {
        20_000
    } else {
        100_000
    };
    let st = wait_worker_ready(root, ready_ms);
    if st.get("state").and_then(|v| v.as_str()) == Some("error") {
        return Err(st
            .get("error")
            .and_then(|v| v.as_str())
            .unwrap_or("worker error")
            .to_string());
    }
    {
        // Soft stop any leftover stream so start is clean. 派发失败和超时都
        // 要透出：在还转着的流上再发 start，命令循环依序执行会变成「start
        // 排在 stop 后面」或干脆把 stop 的等待拖进下一次派发——用户点的是
        // 「开启」，收到「忙碌」比收到一次假启动诚实。
        let st = protocol::read_status(root);
        if st.get("state").and_then(|v| v.as_str()) == Some("running") {
            // 和 stop_vc 同一套证据：只认这条 stop 自己的 stop_seq，
            // state 恰好不是 running 不算数。
            let seq = send_command(root, "stop", Map::new())?;
            wait_own_stop(root, seq, get_live_pid(root), 4_000)?;
            thread::sleep(Duration::from_millis(250));
        }
    }
    // 纯 DSP 必须把开关/预设/参数塞进 start 本体。
    // 以前 start 载荷是空的，worker 只读 inuse；inuse 若没同步到 dsp_enabled，
    // set_values 会当成没选音色，直接报「请选择pth文件」——纯 DSP 永远开不了。
    //
    // 用的必须是上面那个 `dsp_on`（`config::wants_dsp`），不能在这里另算一套。
    // 这里以前是「dsp_enabled 或 有预设 或 有参数」，不看 pth_path、不看
    // function —— 比 wants_dsp 松。于是换回 RVC 时会出现：壳按 wants_dsp 选了
    // RVC worker，转头又在 start 载荷里告诉它「dsp_enabled=true, function=fx」。
    // worker 听载荷的，于是走纯 DSP，RVC 永远加载不上 —— 这就是「DSP 之后换不
    // 回 RVC，要反复切模型甚至重启」。
    let mut payload = dsp_command_fields(&cfg);
    if let Some(bridge) = bridge {
        payload.insert("pcm_bridge_name".into(), json!(bridge.name));
        payload.insert("pcm_bridge_epoch".into(), json!(bridge.epoch));
    }
    // 模型身份冻结进命令本体：worker 处理 start 时用载荷里的 pth/index，
    // 不再以认领那一刻的 inuse 为准 —— 启动中途用户又点了别的音色，
    // 这条 start 的结论仍然可判定。
    let mut pth = String::new();
    let mut index = String::new();
    if !dsp_on {
        pth = cfg
            .get("pth_path")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim()
            .to_string();
        index = cfg
            .get("index_path")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        payload.insert("pth_path".into(), json!(pth));
        payload.insert("index_path".into(), json!(index));
        if let Some(v) = cfg.get("index_rate").cloned() {
            payload.insert("index_rate".into(), v);
        }
    }
    let seq = send_command(root, "start", payload)?;
    // Claim start before any follow-up set. Worker acks last_cmd_seq as soon as
    // it dequeues start (before model load), so this is usually <100 ms.
    if !protocol::wait_cmd_acked(root, seq, 5_000) {
        append_log(
            root,
            &format!("start_vc: start seq={seq} not acked within 5s"),
        );
    }
    // 音高/DSP 热推挪到 wait_vc_running 之后：start 失败（没音色、没预设）
    // 时再推一条 set，会把 error 盖成「参数已应用」，底栏看起来像没点过
    // （diag 26.8.16）。
    Ok(StartOutcome {
        seq,
        pth,
        index,
        dsp: dsp_on,
    })
}

/// 起流成功后再补一次音高/共鸣/DSP。失败的 start 不要走这里。
pub fn push_running_hot(root: &Path, cfg: &Map<String, Value>) -> Result<u64, String> {
    let mut hot = Map::new();
    if let Some(v) = cfg.get("pitch") {
        hot.insert("pitch".into(), v.clone());
    }
    if let Some(v) = cfg.get("formant") {
        hot.insert("formant".into(), v.clone());
    }
    // 和 start 载荷共用同一个生成器 —— 也就是同一个判定。以前这里是另一套松
    // 规则，后果比 start 更重：start 已经按 RVC 起好了流，这一条热推又把
    // function 改回 fx、dsp_enabled 改回 true，等于当场把刚起来的 RVC 掐掉。
    for (k, v) in dsp_command_fields(cfg) {
        hot.insert(k, v);
    }
    if hot.is_empty() {
        return Ok(0);
    }
    set_hot(root, hot)
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
                "error": &crate::i18n::t("s.496951c554"),
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
            "error": &crate::i18n::t("s.7da520ca1f"),
            "pid": 0
        });
    }
    // Worker still alive but never reached running — do not leave the dock on
    // a silent idle「参数已应用」after a full wait.
    let mut out = last;
    if let Some(obj) = out.as_object_mut() {
        let state = obj
            .get("state")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        if state != "running" && state != "error" {
            obj.insert("state".into(), json!("error"));
            obj.insert(
                "error".into(),
                json!(crate::i18n::t("msg.vc.start_timeout")),
            );
            obj.insert(
                "message".into(),
                json!(crate::i18n::t("msg.vc.start_timeout")),
            );
            obj.insert("message_code".into(), json!(""));
        }
    }
    out
}

/// 等「这条」stop 自己完结的证据。
///
/// worker 在 `_worker_stop` 收尾时把 `stop_seq` 写成这条命令的 seq —— 只有
/// 它对上号才说明我们的 stop 被处理完：state 从 running 变成任何别的样子
/// （starting/stopping/error）都证明不了是这条 stop 干的，可能只是上一个
/// 生命周期留下的状态。进程死了也算停 —— 死进程不在输出。
fn wait_own_stop(root: &Path, seq: u64, pid: u32, timeout_ms: u64) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_millis(timeout_ms);
    while Instant::now() < deadline {
        if pid != 0 && !pid_alive(pid) {
            return Ok(());
        }
        let st = protocol::read_status(root);
        let done = st
            .get("stop_seq")
            .and_then(|v| v.as_u64().or_else(|| v.as_i64().map(|i| i as u64)))
            .unwrap_or(0)
            >= seq;
        if done {
            // 同一条记录里 state=="error" 是 worker 自报 stop 失败，把它的
            // 错误透出去；否则（idle / 又被新 start 拉起的 running）这条
            // stop 本身已经处理完。
            if st.get("state").and_then(|v| v.as_str()) == Some("error") {
                let detail = st
                    .get("error")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
                return Err(if detail.is_empty() {
                    crate::i18n::t("s.0ec38407bc")
                } else {
                    detail
                });
            }
            return Ok(());
        }
        thread::sleep(Duration::from_millis(150));
    }
    Err(crate::i18n::t("s.0ec38407bc"))
}

pub fn stop_vc(root: &Path, force: bool) -> Result<(), String> {
    let pid = get_live_pid(root);
    if pid == 0 {
        if force {
            kill_known_workers(root);
            kill_runtime_pythons(root, true);
        }
        let _ = crate::audio_voice::on_engine_stopped();
        return Ok(());
    }
    // 软停没有兜底：stop 派发不出去 / worker 没有给出完结证据都必须如实
    // 报错，不能记一行日志再报成功 —— 否则界面显示已停，引擎还在输出。
    // force 有显式兜底（超时杀树），任何失败都可以继续往下走。
    match send_command(root, "stop", Map::new()) {
        Ok(seq) => {
            // force：给 stop_stream / AudioIoProcess.join 几秒，再杀树。
            // 软停：等 worker 自己写完 stop_seq，进程留下给下次开启用。
            if let Err(e) = wait_own_stop(root, seq, pid, if force { 3_000 } else { 12_000 }) {
                if !force {
                    return Err(e);
                }
                append_log(root, &format!("stop_vc: soft stop unconfirmed: {e}"));
            }
        }
        Err(e) => {
            if !force {
                return Err(e);
            }
            append_log(root, &format!("stop_vc: stop dispatch failed: {e}"));
        }
    }
    if force {
        if pid_alive(pid) && (pid_is_our_worker(root, pid) || pid_looks_like_python(pid)) {
            kill_tree(pid);
        }
        kill_known_workers(root);
        // AudioIoProcess 是 multiprocessing 子进程；父进程死后若没跟上，
        // 这里按「Runtime 下、父进程已死」收掉，不动正在跑的 STS/训练。
        kill_runtime_pythons(root, true);
    }
    if let Err(error) = crate::audio_voice::on_engine_stopped() {
        append_log(root, &format!("microphone bridge detach: {error}"));
    }
    Ok(())
}

pub fn set_hot(root: &Path, payload: Map<String, Value>) -> Result<u64, String> {
    if !is_worker_alive(root) {
        return Err(crate::i18n::t("s.7764d6bdd2").into());
    }
    send_command(root, "set", payload)
}

/// 把「当前选中的音色」热推给引擎，不重开流。
///
/// 路径从配置里读，不从界面传进来 —— `voices_select` 刚刚才把它写进去，而且
/// 那条路径是经过音色库校验的。让界面直接递一个路径给引擎，等于把「让引擎去
/// torch.load 任意文件」这件事开放给了前端。
///
/// worker 没在跑的时候直接报错走人：那时候配置已经是新的，下次开启自然就对，
/// 没有任何要热更新的东西。
pub fn swap_model(root: &Path) -> Result<u64, String> {
    let cfg = crate::config::read(root);
    let pth = cfg
        .get("pth_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    if pth.is_empty() {
        return Err(crate::i18n::t("s.b3b2c06973").into());
    }
    let index = cfg
        .get("index_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let mut payload = Map::new();
    payload.insert("pth_path".into(), json!(pth));
    payload.insert("index_path".into(), json!(index));
    if let Some(r) = cfg.get("index_rate") {
        payload.insert("index_rate".into(), r.clone());
    }
    let seq = set_hot(root, payload)?;
    // 没在跑：没有推理链可提交，Ok(seq) 只代表「已派发 + 配置已落盘」，
    // 界面靠 model_selected / 下次启动兑现。在跑：必须等到 worker 的
    // committed 记录——「认领了 set」不等于「音色换上了」。
    let st = protocol::read_status(root);
    if st.get("state").and_then(|v| v.as_str()) == Some("running") {
        wait_model_applied(root, seq, &pth, &index, MODEL_APPLY_TIMEOUT_MS)?;
    }
    Ok(seq)
}

/// 「丢掉当前音色」热推给引擎，不重开流。`swap_model` 的反向操作。
///
/// 只清配置是不够的：转着的 worker 手里还攥着 RVC 实例，界面上音色没了、
/// 耳朵里还是那个音色。worker 没在跑时 `set_hot` 自己会报错，调用方吞掉即可 ——
/// 配置已经清干净，下次开启就是纯 DSP。
pub fn drop_model(root: &Path) -> Result<u64, String> {
    let mut payload = Map::new();
    payload.insert("drop_model".into(), json!(true));
    set_hot(root, payload)
}

/// Snapshot for the UI (status + derived meter 0..1).
pub fn status_for_ui(root: &Path) -> Value {
    let mut st = protocol::read_status(root);
    // Prefer localized message when worker sent a stable message_code.
    crate::i18n::localize_status(&mut st);
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

        let state = obj
            .get("state")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        // 假启动：status 仍写 starting，但已经没有活着的 worker。
        // 底栏会一直「启动中…」，用户点开启也像没反应。
        //
        // 但不能一律摊成 idle。26.8.21 那位九次点开启，九次 worker 被系统终止，
        // 每次都在这里被抹成「空闲、无消息」，只剩一根停在 22% 的进度条 ——
        // 界面上没有任何东西告诉他刚才崩了。收得到退出码就照实说；收不到（多半
        // 是上一次会话遗留的陈旧 status）才按空闲处理。
        if state == "starting" && !alive {
            let dead_pid = obj.get("pid").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
            let fatal = crate::crash::exit_code_of(dead_pid)
                .filter(|c| crate::crash::is_fatal_status(*c));
            obj.insert("pid".into(), json!(0));
            obj.insert("progress".into(), json!(0));
            match fatal {
                Some(code) => {
                    obj.insert("state".into(), json!("error"));
                    // message 留空：statusSub 会优先显示 message，短提示反而会
                    // 把真正那句「被系统终止，退出码 …」顶掉。
                    obj.insert("message_code".into(), json!(""));
                    obj.insert("message".into(), json!(""));
                    obj.insert(
                        "error".into(),
                        json!(crate::i18n::te(
                            "s.wkKilledBySystem",
                            &crate::crash::describe(code)
                        )),
                    );
                }
                None => {
                    obj.insert("state".into(), json!("idle"));
                    obj.insert("message".into(), json!(""));
                    obj.insert("message_code".into(), json!(""));
                }
            }
        } else if !alive {
            // If status claims a pid that is not ours / dead, surface it
            if let Some(p) = obj.get("pid").and_then(|v| v.as_u64()) {
                if p > 0 {
                    obj.insert("pid".into(), json!(0));
                }
            }
        } else if state == "starting" {
            // worker 已活着：把台账 pid 回填，避免界面 pid=0 的「半就绪」
            let live = get_live_pid(root);
            if live > 0 {
                let cur = obj.get("pid").and_then(|v| v.as_u64()).unwrap_or(0);
                if cur == 0 {
                    obj.insert("pid".into(), json!(live));
                }
            }
        }
    }
    st
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 仓库里没有 tempfile 依赖，其他模块的测试都是这么开临时目录的。
    fn tmp_root(name: &str) -> std::path::PathBuf {
        let d = crate::testutil::scratch(name);
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        protocol::ensure_control_dir(&d).unwrap();
        d
    }

    /// 系统上不会存在的 pid，`pid_alive` 必须判它死。
    const DEAD_PID: u32 = 4_000_000;

    fn write_starting(root: &Path, pid: u32) {
        let mut f = Map::new();
        f.insert("state".into(), json!("starting"));
        f.insert("pid".into(), json!(pid));
        f.insert("progress".into(), json!(22));
        f.insert("message_code".into(), json!("engine.importing"));
        f.insert("message".into(), json!("正在导入推理库（可能需要十几秒）…"));
        protocol::write_status_merge(root, f).unwrap();
    }

    /// 26.8.21 的用户：worker 被系统终止（ASIO 驱动 0xC0000094），status 还停在
    /// starting/22。以前这里一律摊成 idle 且清空 message，界面上只剩一根停住的
    /// 进度条，什么都不说 —— 他因此点了九次。
    #[test]
    fn a_worker_killed_by_the_system_is_reported_not_blanked() {
        let root = tmp_root("crash-reported");
        write_starting(&root, DEAD_PID);
        crate::crash::record_exit(DEAD_PID, 0xC000_0094u32 as i32);

        let st = status_for_ui(&root);
        assert_eq!(st.get("state").unwrap(), "error");
        let err = st.get("error").and_then(|v| v.as_str()).unwrap_or("");
        assert!(err.contains("0xC0000094"), "退出码要写在报错里：{err}");
        // 进度条必须归零，否则界面上留着一根 22% 的条子。
        assert_eq!(st.get("progress").and_then(|v| v.as_u64()), Some(0));
        assert_eq!(st.get("pid").and_then(|v| v.as_u64()), Some(0));

        crate::crash::forget_exit(DEAD_PID);
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 另一半：收不到退出码就说明多半是上次会话遗留的陈旧 status，那还是按
    /// 空闲处理 —— 不能凭「进程不在」就报崩溃。
    ///
    /// PID 不能复用 DEAD_PID：crash 注册表是全局的，两个测试并行时那边
    /// `record_exit` 与这边 `forget_exit` 的先后不定，赶巧了就把这条挤成
    /// error。各用各的 PID，互不踩脚。
    #[test]
    fn a_stale_starting_status_without_an_exit_code_still_falls_back_to_idle() {
        const STALE_PID: u32 = 4_000_001;
        let root = tmp_root("stale-starting");
        write_starting(&root, STALE_PID);
        crate::crash::forget_exit(STALE_PID);

        let st = status_for_ui(&root);
        assert_eq!(st.get("state").unwrap(), "idle");
        assert_eq!(st.get("message").and_then(|v| v.as_str()), Some(""));

        let _ = std::fs::remove_dir_all(&root);
    }

    fn cfg_of(pairs: &[(&str, Value)]) -> Map<String, Value> {
        let mut m = crate::config::defaults();
        for (k, v) in pairs {
            m.insert((*k).to_string(), v.clone());
        }
        m
    }

    /// 这条是「DSP 之后换不回 RVC」的回归测试。
    ///
    /// 命令载荷的判定必须**等于** `config::wants_dsp`。以前它是另一套更松的
    /// 规则（只看 dsp_enabled / 有没有预设 / 有没有参数），于是「选了音色但
    /// 配置里还留着旧预设」这种状态下，壳按 wants_dsp 选了 RVC worker，却在
    /// start 载荷里告诉它 function=fx —— worker 听载荷的，RVC 永远起不来。
    #[test]
    fn the_command_payload_never_disagrees_with_wants_dsp() {
        let cases = vec![
            // 选了音色，但上一次纯 DSP 的预设和参数还留在配置里 ← 就是那个 bug
            cfg_of(&[
                ("pth_path", json!("C:\\voices\\a.pth")),
                ("function", json!("vc")),
                ("dsp_enabled", json!(false)),
                ("dsp_preset", json!("robot")),
                ("dsp_params", json!({"pitch": 3})),
            ]),
            // 纯 DSP
            cfg_of(&[
                ("pth_path", json!("")),
                ("function", json!("fx")),
                ("dsp_enabled", json!(true)),
                ("dsp_preset", json!("robot")),
            ]),
            // 什么都没选
            cfg_of(&[("pth_path", json!("")), ("function", json!("vc"))]),
            // 残留 fx + 有音色：算 RVC
            cfg_of(&[
                ("pth_path", json!("C:\\voices\\a.pth")),
                ("function", json!("fx")),
                ("dsp_enabled", json!(false)),
            ]),
        ];
        for cfg in cases {
            let want = crate::config::wants_dsp(&cfg);
            let fields = dsp_command_fields(&cfg);
            let sent = fields
                .get("dsp_enabled")
                .and_then(|v| v.as_bool())
                .expect("dsp_enabled 必须明确给出");
            assert_eq!(
                sent, want,
                "载荷和 wants_dsp 不一致，cfg={cfg:?} fields={fields:?}"
            );
            let fname = fields.get("function").and_then(|v| v.as_str()).unwrap();
            assert_eq!(fname == "fx", want, "function 和判定不一致：{fields:?}");
        }
    }

    /// 非 DSP 时必须**明确**把三个键写成关闭态，不能只是不提。
    ///
    /// worker 的 gui_config 是常驻的：跑过一次纯 DSP 之后 dsp_enabled / preset /
    /// params 都还在内存里。载荷不覆盖就等于沿用上一次，用户看到的还是换不回。
    #[test]
    fn switching_back_to_rvc_states_the_negative_explicitly() {
        let cfg = cfg_of(&[
            ("pth_path", json!("C:\\voices\\a.pth")),
            ("function", json!("vc")),
            ("dsp_enabled", json!(false)),
            ("dsp_preset", json!("robot")),
            ("dsp_params", json!({"pitch": 3})),
        ]);
        let f = dsp_command_fields(&cfg);
        assert_eq!(f.get("dsp_enabled"), Some(&json!(false)));
        assert_eq!(f.get("dsp_preset"), Some(&json!("")));
        assert_eq!(f.get("dsp_params"), Some(&json!({})));
        assert_eq!(f.get("function"), Some(&json!("vc")));
    }

    /// 残留的 `function="fx"` 不能被原样带回给 worker。
    #[test]
    fn a_leftover_fx_function_is_not_echoed_back() {
        let cfg = cfg_of(&[
            ("pth_path", json!("C:\\voices\\a.pth")),
            ("function", json!("fx")),
            ("dsp_enabled", json!(false)),
        ]);
        assert!(!crate::config::wants_dsp(&cfg));
        let f = dsp_command_fields(&cfg);
        assert_eq!(f.get("function"), Some(&json!("vc")));
    }

    /// 纯 DSP 该带上预设和参数，否则 worker 只能干声直通。
    #[test]
    fn a_dsp_start_carries_the_preset_and_params() {
        let cfg = cfg_of(&[
            ("pth_path", json!("")),
            ("dsp_enabled", json!(true)),
            ("dsp_preset", json!("robot")),
            ("dsp_params", json!({"pitch": 5})),
        ]);
        let f = dsp_command_fields(&cfg);
        assert_eq!(f.get("dsp_enabled"), Some(&json!(true)));
        assert_eq!(f.get("function"), Some(&json!("fx")));
        assert_eq!(f.get("dsp_preset"), Some(&json!("robot")));
        assert_eq!(f.get("dsp_params"), Some(&json!({"pitch": 5})));
    }

    #[test]
    fn identity_memo_is_keyed_to_one_pid() {
        forget_identity(1234);
        forget_identity(5678);
        assert_eq!(cached_identity(1234), None);
        remember_identity(1234, true);
        assert_eq!(cached_identity(1234), Some(true));
        // A different pid must never be answered from another pid's entry —
        // and probing/remembering it must not evict the first entry either.
        assert_eq!(cached_identity(5678), None);
        remember_identity(5678, false);
        assert_eq!(cached_identity(5678), Some(false));
        assert_eq!(cached_identity(1234), Some(true));
        // Dead-pid eviction is per-pid: dropping 1234 leaves 5678's verdict.
        forget_identity(1234);
        assert_eq!(cached_identity(1234), None);
        assert_eq!(cached_identity(5678), Some(false));
        forget_identity(5678);
    }

    #[test]
    fn pid_zero_is_never_alive() {
        assert!(!pid_alive(0));
    }

    /// R05：command.seq 是读改写计数器，command.json 是单槽邮箱。并发派发必须
    /// 由 COMMAND_DISPATCH 串行 —— 否则两个线程领到同一个 seq，后写邮箱的把
    /// 先写的顶掉，被顶的命令永远没人执行。
    ///
    /// 这里模拟一个真在认领的 worker：它每认走一条就推 last_cmd_seq。不变量
    /// 是「写进邮箱的每一条都被认领过」——派发方要等上一条被认走才写新
    /// 的，所以认领记录必须严格覆盖 1..=N，少一条就是有人被悄悄顶掉。
    #[test]
    fn concurrent_dispatches_get_unique_seqs_and_nothing_is_lost_silently() {
        use std::sync::atomic::{AtomicBool, Ordering};
        use std::sync::Arc;

        let root = tmp_root("dispatch-serial");
        const N: u64 = 8;
        let stop = Arc::new(AtomicBool::new(false));
        let seen = Arc::new(Mutex::new(Vec::<u64>::new()));
        let claimer = {
            let r = root.clone();
            let stop = stop.clone();
            let seen = seen.clone();
            thread::spawn(move || {
                let mut last = 0u64;
                while !stop.load(Ordering::SeqCst) {
                    let seq = protocol::read_command(&r)
                        .get("seq")
                        .and_then(|v| v.as_u64())
                        .unwrap_or(0);
                    if seq > last {
                        last = seq;
                        seen.lock().unwrap_or_else(|e| e.into_inner()).push(seq);
                        let mut f = Map::new();
                        f.insert("last_cmd_seq".into(), json!(seq));
                        let _ = protocol::write_status_merge(&r, f);
                    }
                    thread::sleep(Duration::from_millis(2));
                }
            })
        };
        let mut handles = Vec::new();
        for i in 0..N {
            let r = root.clone();
            handles.push(thread::spawn(move || {
                let mut p = Map::new();
                p.insert("tag".into(), json!(i));
                send_command_wait(&r, "set", p, 10_000)
            }));
        }
        let mut seqs: Vec<u64> = handles
            .into_iter()
            .map(|h| h.join().unwrap().expect("有 worker 认领时派发必须成功"))
            .collect();
        // 派发只等**上一条**被认领，自己写完就返回 —— 最后一条还给认领线程
        // 一个短暂的观察窗口再断言。
        let deadline = Instant::now() + Duration::from_secs(2);
        while Instant::now() < deadline {
            let n = seen.lock().unwrap_or_else(|e| e.into_inner()).len();
            if n >= N as usize {
                break;
            }
            thread::sleep(Duration::from_millis(5));
        }
        stop.store(true, Ordering::SeqCst);
        claimer.join().unwrap();
        seqs.sort_unstable();
        seqs.dedup();
        assert_eq!(seqs.len(), N as usize, "每个派发都要领到唯一 seq：{seqs:?}");
        // 认领记录必须是一条不缺：mailbox 里被顶掉却没被认走的命令 = 静默丢失。
        let claimed = seen.lock().unwrap_or_else(|e| e.into_inner()).clone();
        assert_eq!(
            claimed,
            (1..=N).collect::<Vec<u64>>(),
            "每条写进邮箱的命令都必须被 worker 认走：claimed={claimed:?}"
        );
        let last = protocol::read_command(&root);
        assert_eq!(
            last.get("seq").and_then(|v| v.as_u64()),
            Some(*seqs.last().unwrap())
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    /// A 已被接受（调用方拿到 Ok(seqA)），worker 迟迟不认领（慢/卡在长任务）：
    /// B 必须**有界失败**，且 A 原样留在邮箱里 —— A 的调用方从没收到失败，
    /// worker 缓过来之后照样要认到它、执行它。B 失败不能替 A 宣布失败。
    #[test]
    fn a_rejected_dispatch_leaves_the_pending_command_untouched() {
        let root = tmp_root("dispatch-timeout");
        let seq_a = send_command_wait(&root, "start", Map::new(), 10).unwrap();
        let t0 = Instant::now();
        let err = send_command_wait(&root, "set", Map::new(), 10).unwrap_err();
        assert!(
            t0.elapsed() >= Duration::from_millis(10),
            "超时应至少等到 ack_timeout"
        );
        assert!(
            err.contains(&seq_a.to_string()),
            "失败必须指到具体哪条命令没被认领：{err}"
        );
        // A 还在邮箱、未被覆盖未被作废：worker 之后认领它照样执行。
        let cmd = protocol::read_command(&root);
        assert_eq!(cmd.get("seq").and_then(|v| v.as_u64()), Some(seq_a));
        assert_eq!(cmd.get("cmd").and_then(|v| v.as_str()), Some("start"));
        // 不许出现任何作废标记文件：A 的调用方拿到的是 Ok(seqA)，谁也没有
        // 权力替它宣布失败。
        assert!(
            !root
                .join("User_Data/runtime_control/command.cancel")
                .exists(),
            "B 超时绝不能给 A 留下作废标记"
        );
        // worker 缓过来之后认走 A：A 照常执行，之后的派发也能过。
        let mut f = Map::new();
        f.insert("last_cmd_seq".into(), json!(seq_a));
        protocol::write_status_merge(&root, f).unwrap();
        let seq_b = send_command_wait(&root, "set", Map::new(), 2_000).unwrap();
        assert!(seq_b > seq_a, "A 被认走后 B 的重发必须成功拿到新 seq");
        let _ = std::fs::remove_dir_all(&root);
    }

    /// A 还没被认走时 C 也不能跳过它：pending 活着就必须等，等不到就失败，
    /// 不能绕过去把 A 顶掉。
    #[test]
    fn a_later_dispatch_cannot_skip_an_unclaimed_pending() {
        let root = tmp_root("dispatch-noskip");
        let seq_a = send_command_wait(&root, "start", Map::new(), 10).unwrap();
        // A 未认领期间，再派一条仍然只能等有界失败。
        let err = send_command_wait(&root, "stop", Map::new(), 10).unwrap_err();
        assert!(err.contains(&seq_a.to_string()));
        let cmd = protocol::read_command(&root);
        assert_eq!(cmd.get("seq").and_then(|v| v.as_u64()), Some(seq_a));
        // worker 后来认走了 A：last_cmd_seq 推上去之后，C 照常派发成功。
        let mut f = Map::new();
        f.insert("last_cmd_seq".into(), json!(seq_a));
        protocol::write_status_merge(&root, f).unwrap();
        let t0 = Instant::now();
        let seq_c = send_command_wait(&root, "stop", Map::new(), 5_000).unwrap();
        assert!(seq_c > seq_a);
        assert!(t0.elapsed() < Duration::from_secs(1), "已认领的 pending 不该再挡路");
        let cmd = protocol::read_command(&root);
        assert_eq!(cmd.get("seq").and_then(|v| v.as_u64()), Some(seq_c));
        assert_eq!(cmd.get("cmd").and_then(|v| v.as_str()), Some("stop"));
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 「有界」包的是从入口算的总预算，不只是拿到派发权之后的 ack 等待。
    /// 锁拿不到也该在预算内失败 —— 否则 N 个并发派发者各自再等 3s，队尾
    /// 的 stop 实际排出 N*3s。
    #[test]
    fn dispatch_budget_covers_the_dispatch_lock_itself() {
        use std::sync::atomic::{AtomicU64, Ordering as AOrd};
        use std::sync::Arc;

        let root = tmp_root("dispatch-budget");
        let seq_a = send_command_wait(&root, "start", Map::new(), 10).unwrap();
        // A 永远不被认领。4 个并发派发者预算各 600ms：最坏排队情形也必须
        // 在各自预算内失败，不能串成 4*600ms。
        let worst = Arc::new(AtomicU64::new(0));
        let mut handles = Vec::new();
        for _ in 0..4 {
            let root = root.clone();
            let worst = Arc::clone(&worst);
            handles.push(thread::spawn(move || {
                let t0 = Instant::now();
                let r = send_command_wait(&root, "stop", Map::new(), 600);
                let ms = t0.elapsed().as_millis() as u64;
                worst.fetch_max(ms, AOrd::Relaxed);
                r
            }));
        }
        for h in handles {
            let r = h.join().unwrap();
            assert!(r.is_err(), "pending 没被认领，每个派发者都该有界失败");
        }
        let worst_ms = worst.load(AOrd::Relaxed);
        assert!(
            worst_ms < 1_800,
            "排队+等认领要算在同一个预算里，最坏 {worst_ms}ms 超了"
        );
        // A 原样在邮箱里，谁也没覆盖它。
        let cmd = protocol::read_command(&root);
        assert_eq!(cmd.get("seq").and_then(|v| v.as_u64()), Some(seq_a));
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 上一轮 worker 留下的 pending：cmd.ts 早于本轮 worker_boot_ts，worker
    /// boot 路径已经按同样证据把它判死（永不执行），壳直接覆盖不算丢。
    /// 没有 boot 证据时一律当作活 pending —— 宁可失败也不能猜。
    #[test]
    fn a_pre_boot_pending_is_dead_mail_and_may_be_replaced() {
        let root = tmp_root("dispatch-stale");
        let seq_a = send_command_wait(&root, "start", Map::new(), 10).unwrap();
        // 模拟 worker 重启后写入的 boot_ts：比 pending 晚很多 → A 是死信。
        let cmd_ts = protocol::read_command(&root)
            .get("ts")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0);
        let mut f = Map::new();
        f.insert("worker_boot_ts".into(), json!(cmd_ts + 60.0));
        protocol::write_status_merge(&root, f).unwrap();
        let t0 = Instant::now();
        let seq_b = send_command_wait(&root, "set", Map::new(), 5_000).unwrap();
        assert!(seq_b > seq_a);
        assert!(
            t0.elapsed() < Duration::from_secs(1),
            "已被 boot 判死的 pending 不该让派发等超时"
        );
        let cmd = protocol::read_command(&root);
        assert_eq!(cmd.get("seq").and_then(|v| v.as_u64()), Some(seq_b));

        // 反向：有 boot_ts 但 pending 是本轮的（ts 不早于 boot-1s）→ 活的。
        let _ = std::fs::remove_dir_all(&root);
        let root = tmp_root("dispatch-live");
        let mut f = Map::new();
        f.insert("worker_boot_ts".into(), json!(now_epoch() - 60.0));
        protocol::write_status_merge(&root, f).unwrap();
        let seq_a = send_command_wait(&root, "start", Map::new(), 10).unwrap();
        // pending.ts ≈ now > boot_ts-60s → 本轮命令，不许覆盖。
        let err = send_command_wait(&root, "set", Map::new(), 10).unwrap_err();
        assert!(err.contains(&seq_a.to_string()));
        let cmd = protocol::read_command(&root);
        assert_eq!(cmd.get("seq").and_then(|v| v.as_u64()), Some(seq_a));
        let _ = std::fs::remove_dir_all(&root);
    }

    fn now_epoch() -> f64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0)
    }

    #[test]
    fn tool_pid_guard_tracks_and_drops() {
        let pid = 4_242_424;
        assert!(!protected_tool_pids().contains(&pid));
        {
            let _g = ToolPidGuard::new(pid);
            assert!(protected_tool_pids().contains(&pid));
        }
        assert!(!protected_tool_pids().contains(&pid));
    }

    #[test]
    fn path_is_under_matches_runtime_children_only() {
        let rt = Path::new(r"C:\App\Runtime");
        assert!(path_is_under(rt, r"C:\App\Runtime\pythonw.exe"));
        assert!(path_is_under(rt, r"c:\app\runtime\python.exe"));
        assert!(path_is_under(rt, r"C:/App/Runtime/Scripts/python.exe"));
        assert!(!path_is_under(rt, r"C:\App\RuntimeX\python.exe"));
        assert!(!path_is_under(rt, r"C:\Python39\python.exe"));
        assert!(!path_is_under(Path::new(""), r"C:\App\Runtime\python.exe"));
    }

    /// 不存在的目录下不可能有镜像路径 —— 扫描必须安静返回空，而不是报错。
    /// 补全运行时用这份结果决定要不要拦用户，空目录绝不能误报「有进程占用」。
    #[test]
    fn pythons_under_a_missing_dir_is_empty() {
        let dir = crate::testutil::scratch("pythons-under-missing");
        let _ = std::fs::remove_dir_all(&dir);
        assert!(pythons_under(&dir).is_empty());
    }

    /// 一次启动开出两个 worker 的时候，多出来那个必须留下痕迹。
    ///
    /// `worker.pid` 只有一行，后写的盖掉先写的 —— 于是先起来那个再也没人认识，
    /// 退出时杀不掉，它会一直占着声卡活到用户重启电脑。台账就是补这条记忆。
    #[test]
    fn every_spawned_pid_stays_on_the_ledger() {
        let dir = crate::testutil::scratch("pids");
        let _ = std::fs::remove_dir_all(&dir);
        let root = dir.as_path();

        protocol::remember_spawned_pid(root, 111).unwrap();
        protocol::remember_spawned_pid(root, 222).unwrap();
        // 同一个 pid 记两次不该变成两行。
        protocol::remember_spawned_pid(root, 111).unwrap();
        assert_eq!(protocol::read_spawned_pids(root), vec![111, 222]);

        // 后写的 worker.pid 盖掉了 111，但台账里还留着它。
        protocol::write_worker_pid(root, 222).unwrap();
        let known = known_worker_pids(root);
        assert!(known.contains(&111), "孤儿 pid 丢了：{known:?}");
        assert!(known.contains(&222));

        protocol::clear_spawned_pids(root);
        assert!(protocol::read_spawned_pids(root).is_empty());
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// pid 0 是「没有 worker」的意思，不能进台账、不能进待杀名单。
    #[test]
    fn pid_zero_never_enters_the_ledger() {
        let dir = crate::testutil::scratch("pid0");
        let _ = std::fs::remove_dir_all(&dir);
        let root = dir.as_path();
        protocol::remember_spawned_pid(root, 0).unwrap();
        assert!(protocol::read_spawned_pids(root).is_empty());
        assert!(!known_worker_pids(root).contains(&0));
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// 台账里的 pid 必须进入 known 列表（get_live_pid 靠它防双开）。
    #[test]
    fn ledger_pids_are_known_even_without_pid_file() {
        let dir = crate::testutil::scratch("live");
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(paths::control_dir(dir.as_path())).unwrap();
        let root = dir.as_path();
        protocol::clear_worker_pid(root);
        protocol::remember_spawned_pid(root, 424242).unwrap();
        assert!(
            known_worker_pids(root).contains(&424242),
            "台账 pid 必须被 known_worker_pids 看见"
        );
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// E-03：保存的后端选择胜过进程环境里的 TM_ACCEL / TM_USE_DML。
    ///
    /// 旧环境变量是 OS 级的，测试里没法安全地伪造（set_var 是进程全局、
    /// 测试并行会互踩）；这里钉「显式 cpu → TM_ACCEL=cpu 且 TM_USE_DML 被清」，
    /// 对机器上恰好设了 TM_USE_DML 的情况同样成立——显式选择必须抹掉它。
    #[test]
    fn saved_accel_beats_legacy_env() {
        let root = tmp_root("accel-env");
        let cfgp = paths::app_config_path(&root);
        std::fs::create_dir_all(cfgp.parent().unwrap()).unwrap();
        std::fs::write(&cfgp, r#"{"accel_backend":"cpu"}"#).unwrap();
        let env = env_for_runtime(&root);
        assert_eq!(env.get("TM_ACCEL").map(|s| s.as_str()), Some("cpu"));
        assert!(
            !env.contains_key("TM_USE_DML"),
            "显式 CPU 选择必须清掉遗留的 TM_USE_DML：{env:?}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 没保存选择时维持旧行为：TM_ACCEL 缺席补 auto，旧变量照常继承。
    #[test]
    fn unset_accel_defaults_to_auto() {
        let root = tmp_root("accel-none");
        let env = env_for_runtime(&root);
        assert_eq!(env.get("TM_ACCEL").map(|s| s.as_str()), Some("auto"));
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 身份缓存是进程级共享：fake_live_worker 写入的「这是我们的 worker」
    /// 会被别的并行测试里的清缓存路径（kill_known_workers / 死亡分支）
    /// 抹掉，也会反之。凡是依赖 is_worker_alive 或会触发清缓存的测试，
    /// 都在这把锁上串行；只碰邮箱/协议的测试不需要。
    fn identity_test_lock() -> std::sync::MutexGuard<'static, ()> {
        static L: Mutex<()> = Mutex::new(());
        L.lock().unwrap_or_else(|e| e.into_inner())
    }

    /// 测试里「活着的 worker」= 本测试进程自己的 pid：真活，且把身份判断
    /// 直接写进 identity 缓存（pid_is_our_worker 先查缓存，不走镜像比对）。
    /// 仅限不会走到 kill 分支的断言用 —— 会走到杀树的路径（force）必须
    /// 用死 pid，见下方 stop 测试。
    fn fake_live_worker(root: &Path) -> u32 {
        let pid = std::process::id();
        remember_identity(pid, true);
        protocol::write_worker_pid(root, pid).unwrap();
        pid
    }

    fn write_apply(root: &Path, seq: u64, pth: &str, idx: &str, phase: &str, err: &str) {
        let mut f = Map::new();
        f.insert(
            "model_apply".into(),
            json!({
                "seq": seq,
                "pth_path": pth,
                "index_path": idx,
                "phase": phase,
                "error": err,
            }),
        );
        protocol::write_status_merge(root, f).unwrap();
    }

    /// committed 记录必须 seq + pth + index 三个全对上才算这条请求应用完成。
    #[test]
    fn model_apply_committed_resolves_only_on_full_correlation() {
        let _identity_guard = identity_test_lock();
        let root = tmp_root("apply-committed");
        fake_live_worker(&root);
        write_apply(&root, 7, r"C:\voices\b.pth", r"C:\voices\b.index", "committed", "");
        assert!(
            wait_model_applied(&root, 7, r"C:\voices\b.pth", r"C:\voices\b.index", 2_000)
                .is_ok(),
            "seq+路径全对上的 committed 必须算应用成功"
        );
        // 同一条 seq 但路径不对 = 另一条请求的记录，不能拿来充数。
        let root2 = tmp_root("apply-wrongpath");
        fake_live_worker(&root2);
        write_apply(&root2, 7, r"C:\voices\other.pth", "", "committed", "");
        let err = wait_model_applied(
            &root2,
            7,
            r"C:\voices\b.pth",
            r"C:\voices\b.index",
            600,
        )
        .unwrap_err();
        assert!(!err.is_empty());
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&root2);
    }

    /// failed 要把 worker 的报错原样透给调用方，不许换成「成功」。
    #[test]
    fn model_apply_failed_surfaces_the_worker_error() {
        let _identity_guard = identity_test_lock();
        let root = tmp_root("apply-failed");
        fake_live_worker(&root);
        write_apply(
            &root,
            9,
            r"C:\voices\b.pth",
            "",
            "failed",
            "换模型失败，仍在用上一个音色",
        );
        let err = wait_model_applied(&root, 9, r"C:\voices\b.pth", "", 2_000).unwrap_err();
        assert!(
            err.contains("仍在用上一个音色"),
            "worker 的失败原因要透出去：{err}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 槽位被更新的请求接管（seq 更大）且推理链上跑的不是我们要的：
    /// 这条 seq 永远不会提交，必须立刻失败而不是傻等。
    #[test]
    fn model_apply_superseded_by_a_newer_request_fails_fast() {
        let _identity_guard = identity_test_lock();
        let root = tmp_root("apply-superseded");
        fake_live_worker(&root);
        write_apply(&root, 11, r"C:\voices\c.pth", "", "loading", "");
        let t0 = Instant::now();
        let err = wait_model_applied(&root, 9, r"C:\voices\b.pth", "", 5_000).unwrap_err();
        assert!(t0.elapsed() < Duration::from_secs(2), "被顶掉的请求要快速失败");
        assert!(!err.is_empty());
        let _ = std::fs::remove_dir_all(&root);
    }

    /// model_active 只是上一个已应用身份的快照，证明不了**这条**请求被
    /// 提交过。同模型 no-op 必须由 worker 为这条 seq 新发 committed，壳
    /// 不许拿 active 猜 —— 这里有界超时必须是 Err。
    #[test]
    fn model_active_identity_alone_is_not_evidence() {
        let _identity_guard = identity_test_lock();
        let root = tmp_root("apply-active");
        fake_live_worker(&root);
        let mut f = Map::new();
        f.insert(
            "model_active".into(),
            json!({"pth_path": r"C:\voices\b.pth", "index_path": ""}),
        );
        protocol::write_status_merge(&root, f).unwrap();
        let t0 = Instant::now();
        let err = wait_model_applied(&root, 9, r"C:\voices\b.pth", "", 800).unwrap_err();
        assert!(t0.elapsed() < Duration::from_secs(3));
        assert!(!err.is_empty(), "active 对上但无对号记录时必须报错");
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 同 pth 但 index 不同 = 链上跑的还是旧索引：active 对上 pth、记录
    /// 属于别的 seq，都不能算成功。
    #[test]
    fn model_apply_wrong_index_is_not_success() {
        let _identity_guard = identity_test_lock();
        let root = tmp_root("apply-wrongidx");
        fake_live_worker(&root);
        let mut f = Map::new();
        f.insert(
            "model_active".into(),
            json!({"pth_path": r"C:\voices\b.pth", "index_path": r"C:\voices\old.index"}),
        );
        f.insert(
            "model_apply".into(),
            json!({"seq": 9, "pth_path": r"C:\voices\b.pth",
                   "index_path": r"C:\voices\old.index",
                   "phase": "committed", "error": ""}),
        );
        protocol::write_status_merge(&root, f).unwrap();
        let err =
            wait_model_applied(&root, 9, r"C:\voices\b.pth", r"C:\voices\new.index", 800)
                .unwrap_err();
        assert!(!err.is_empty());
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 别的 seq 留下的 committed 不是这条请求的结论：mseq < seq 要忽略，
    /// 等不到自己的记录就有界报错。
    #[test]
    fn model_apply_stale_committed_for_older_seq_is_ignored() {
        let _identity_guard = identity_test_lock();
        let root = tmp_root("apply-staleseq");
        fake_live_worker(&root);
        write_apply(&root, 3, r"C:\voices\b.pth", r"C:\voices\b.index", "committed", "");
        let err = wait_model_applied(
            &root,
            9,
            r"C:\voices\b.pth",
            r"C:\voices\b.index",
            800,
        )
        .unwrap_err();
        assert!(!err.is_empty());
        let _ = std::fs::remove_dir_all(&root);
    }

    /// worker 死了之后 status.json 里哪怕留着对得上的 model_active /
    /// committed 记录也是残影：必须先查活，立刻 Err。
    #[test]
    fn model_apply_dead_worker_overrides_stale_evidence() {
        let root = tmp_root("apply-deadactive");
        // 不写 worker.pid：worker 不在。status 里伪造一条完全对号的
        // committed + active —— 全是死进程留下的残影，不能算数。
        let mut f = Map::new();
        f.insert(
            "model_active".into(),
            json!({"pth_path": r"C:\voices\b.pth", "index_path": ""}),
        );
        f.insert(
            "model_apply".into(),
            json!({"seq": 9, "pth_path": r"C:\voices\b.pth", "index_path": "",
                   "phase": "committed", "error": ""}),
        );
        protocol::write_status_merge(&root, f).unwrap();
        let t0 = Instant::now();
        let err = wait_model_applied(&root, 9, r"C:\voices\b.pth", "", 30_000).unwrap_err();
        assert!(t0.elapsed() < Duration::from_secs(2), "死 worker 要立刻失败");
        let _ = std::fs::remove_dir_all(&root);
    }

    /// worker 活着但永远不报应用记录（旧版 worker / 没有这条能力）：
    /// 有界超时 Err —— 不许拿「还在 running」冒充「已应用」。
    #[test]
    fn missing_apply_capability_is_a_bounded_error_not_false_success() {
        let _identity_guard = identity_test_lock();
        let root = tmp_root("apply-nocap");
        fake_live_worker(&root);
        let mut f = Map::new();
        f.insert("state".into(), json!("running"));
        f.insert("last_cmd_seq".into(), json!(9));
        protocol::write_status_merge(&root, f).unwrap();
        let t0 = Instant::now();
        let err = wait_model_applied(&root, 9, r"C:\voices\b.pth", "", 600).unwrap_err();
        assert!(t0.elapsed() < Duration::from_secs(2));
        assert!(!err.is_empty(), "能力缺失必须报错，不能报假成功");
        let _ = std::fs::remove_dir_all(&root);
    }

    /// worker 死了：等待立刻结束并报「未运行」，不拖到超时。
    #[test]
    fn model_apply_dead_worker_fails_immediately() {
        let root = tmp_root("apply-dead");
        // 不写 worker.pid：没有活 worker。
        let t0 = Instant::now();
        let err = wait_model_applied(&root, 9, r"C:\voices\b.pth", "", 30_000).unwrap_err();
        assert!(t0.elapsed() < Duration::from_secs(2), "死 worker 要立刻失败");
        assert!(!err.is_empty());
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 软停派发失败必须如实报错 —— 不能记一行日志再报成功，让界面显示
    /// 已停而引擎还在输出。
    ///
    /// force 的「派发失败 → 超时杀树」兜底无法在单测里安全复现：伪造存活
    /// 要靠 identity 缓存，而缓存一旦认下这个 pid，杀树分支就真会朝本测试
    /// 进程开火。所以这里只钉软停的语义；force 的另一半见下面的死进程用例。
    #[test]
    fn soft_stop_propagates_dispatch_failure() {
        let _identity_guard = identity_test_lock();
        let root = tmp_root("stop-dispatch");
        fake_live_worker(&root);
        // 邮箱里压一条永远没人认领的 pending：stop 的派发必有界失败。
        let _pending = send_command_wait(&root, "start", Map::new(), 10).unwrap();
        let soft = stop_vc(&root, false);
        assert!(soft.is_err(), "软停派发失败必须报错，不能报成功");
        let _ = std::fs::remove_dir_all(&root);
        forget_identity(std::process::id());
    }

    /// force 的另一半语义：没有活 worker 时是干净 no-op（Ok），兜底的
    /// kill 扫不到任何目标。DEAD_PID 保证 kill 分支拿不到活进程。
    #[test]
    fn force_stop_on_a_dead_worker_is_a_noop_ok() {
        let _identity_guard = identity_test_lock();
        let root = tmp_root("stop-dead-force");
        protocol::write_worker_pid(&root, DEAD_PID).unwrap();
        let t0 = Instant::now();
        assert!(stop_vc(&root, true).is_ok());
        assert!(t0.elapsed() < Duration::from_secs(2), "死 worker 的 force 不该等");
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 软停等满期限 worker 还在 running：必须报错而不是「就当停了」。
    /// 这里用本进程 pid 充当活着的 worker：状态写死 running，等满 12s。
    #[test]
    fn soft_stop_still_running_at_deadline_is_an_error() {
        let _identity_guard = identity_test_lock();
        let root = tmp_root("stop-still-running");
        fake_live_worker(&root);
        let mut f = Map::new();
        f.insert("state".into(), json!("running"));
        protocol::write_status_merge(&root, f).unwrap();
        let err = stop_vc(&root, false).unwrap_err();
        assert!(!err.is_empty(), "等满仍 running 必须报错");
        let _ = std::fs::remove_dir_all(&root);
    }

    /// F5/round4：指纹的每一项都来自 spawn 时实际下发的 env 和运行时
    /// 路径 —— 后端、显卡、DML 覆盖、解释器路径，任一不同都必须换指纹。
    /// 纯函数侧用合成 env，不依赖本机显卡数。
    #[test]
    fn spawn_fingerprint_for_tracks_env_and_runtime_identity() {
        let rt = Path::new("F:\\x\\Runtime");
        let pyw = rt.join("pythonw.exe");
        let mut env = HashMap::new();
        env.insert("TM_ACCEL".to_string(), "cpu".to_string());
        let fp = spawn_fingerprint_for(&env, &pyw);
        assert!(fp.starts_with("v2|cpu||"), "TM_ACCEL 要进指纹: {fp}");
        assert!(
            fp.ends_with("runtime\\pythonw.exe"),
            "解释器路径要进指纹: {fp}"
        );

        let mut e = env.clone();
        e.insert("CUDA_VISIBLE_DEVICES".to_string(), "1".to_string());
        assert_ne!(spawn_fingerprint_for(&e, &pyw), fp, "显卡选择要进指纹");
        let mut e = env.clone();
        e.insert("TM_USE_DML".to_string(), "1".to_string());
        assert_ne!(spawn_fingerprint_for(&e, &pyw), fp, "DML 覆盖要进指纹");
        assert_ne!(
            spawn_fingerprint_for(&env, &rt.join("python.exe")),
            fp,
            "换运行时解释器必须换指纹"
        );
        // 大小写/分隔符写法不同的同一路径不算换。
        let alt = Path::new("f:/x/runtime/pythonw.exe").to_path_buf();
        assert_eq!(spawn_fingerprint_for(&env, &alt), fp);
    }

    /// 落盘指纹描述的是「spawn 那一刻实际传给子进程的东西」：
    /// spawn 后改配置不重算落盘值 —— 兼容性判断只认「还活着的进程
    /// 出生时的 env」对「现在会用的 env」。缺的、旧两字段格式的指纹
    /// 一律不兼容；运行时没了也判不兼容（没法 spawn ≠ 谁都兼容）。
    #[test]
    fn spawn_policy_match_uses_spawned_env_not_reread_config() {
        let root = tmp_root("fingerprint-env");
        let rt = paths::runtime_dir(&root);
        std::fs::create_dir_all(&rt).unwrap();
        let pyw = rt.join("pythonw.exe");
        std::fs::write(&pyw, b"fake").unwrap();
        let cfgp = paths::app_config_path(&root);
        std::fs::create_dir_all(cfgp.parent().unwrap()).unwrap();
        std::fs::write(&cfgp, r#"{"accel_backend":"cpu"}"#).unwrap();

        // 用 spawn 同一条通路拿到的 env 落盘 → 与当前策略一致。
        let env = env_for_runtime(&root);
        write_spawn_fingerprint(&root, &env, &pyw);
        assert_eq!(
            read_spawn_fingerprint(&root),
            spawn_fingerprint_for(&env, &pyw)
        );
        assert!(
            saved_spawn_policy_matches_current(&root),
            "同一份 env/运行时必须兼容"
        );

        // spawn 之后改配置：活进程带的是旧 env —— 不兼容，不许错记成新策略。
        std::fs::write(&cfgp, r#"{"accel_backend":"auto"}"#).unwrap();
        assert!(
            !saved_spawn_policy_matches_current(&root),
            "spawn 后改配置必须判不兼容"
        );
        // 改回来 → 又兼容（现在的策略恰好等于出生时的）。
        std::fs::write(&cfgp, r#"{"accel_backend":"cpu"}"#).unwrap();
        assert!(saved_spawn_policy_matches_current(&root));

        // 指纹文件缺失 / 旧版两字段格式：只能当不兼容。
        let _ = std::fs::remove_file(fingerprint_path(&root));
        assert!(!saved_spawn_policy_matches_current(&root));
        std::fs::write(fingerprint_path(&root), "cpu|-1").unwrap();
        assert!(
            !saved_spawn_policy_matches_current(&root),
            "旧格式证明不了运行时身份，不许兼容"
        );

        // 运行时整体没了 → current_spawn_fingerprint 为 None → 不兼容。
        let _ = std::fs::remove_dir_all(&rt);
        assert!(current_spawn_fingerprint(&root).is_none());
        assert!(!saved_spawn_policy_matches_current(&root));
        let _ = std::fs::remove_dir_all(&root);
    }

    /// Agent I 的只读查询：活着 + 指纹对号才 true。死进程、缺指纹、
    /// 策略漂移都返回 false，且全程不杀进程不动文件。
    #[test]
    fn live_worker_spawn_policy_query_is_read_only_and_strict() {
        let _identity_guard = identity_test_lock();
        let root = tmp_root("fingerprint-live");
        let rt = paths::runtime_dir(&root);
        std::fs::create_dir_all(&rt).unwrap();
        let pyw = rt.join("pythonw.exe");
        std::fs::write(&pyw, b"fake").unwrap();
        let cfgp = paths::app_config_path(&root);
        std::fs::create_dir_all(cfgp.parent().unwrap()).unwrap();
        std::fs::write(&cfgp, r#"{"accel_backend":"cpu"}"#).unwrap();

        // 没有活 worker → false（即使指纹对得上）。
        let env = env_for_runtime(&root);
        write_spawn_fingerprint(&root, &env, &pyw);
        assert!(
            !live_worker_matches_current_spawn_policy(&root),
            "没有活进程不能报兼容"
        );

        // 活 worker + 对号指纹 → true。
        let pid = fake_live_worker(&root);
        assert!(live_worker_matches_current_spawn_policy(&root));
        assert!(pid_alive(pid), "查询不许动这个进程");

        // 策略漂移 → false；进程仍活着。
        std::fs::write(&cfgp, r#"{"accel_backend":"cuda"}"#).unwrap();
        assert!(!live_worker_matches_current_spawn_policy(&root));
        assert!(pid_alive(pid));
        let _ = std::fs::remove_dir_all(&root);
        forget_identity(std::process::id());
    }

    /// 停的证据是「这条 seq 的 stop_seq」：state 恰好不是 running
    /// （这里是 idle）但 stop_seq 不是我们的 —— 那条记录属于更早的
    /// stop，不能当成本次完结，必须有界报错。
    #[test]
    fn wait_own_stop_requires_matching_seq_not_any_idle() {
        let root = tmp_root("stop-seq-mismatch");
        let mut f = Map::new();
        f.insert("state".into(), json!("idle"));
        f.insert("stop_seq".into(), json!(3));
        protocol::write_status_merge(&root, f).unwrap();
        let t0 = Instant::now();
        let err = wait_own_stop(&root, 9, std::process::id(), 700).unwrap_err();
        assert!(t0.elapsed() >= Duration::from_millis(600), "不许秒收旧记录");
        assert!(!err.is_empty());
        let _ = std::fs::remove_dir_all(&root);
    }

    /// starting/stopping/error 都不是完结证据；stop_seq 对号且 idle 才是。
    #[test]
    fn wait_own_stop_accepts_only_its_own_terminal_record() {
        let root = tmp_root("stop-seq-own");
        let mut f = Map::new();
        f.insert("state".into(), json!("idle"));
        f.insert("stop_seq".into(), json!(9));
        protocol::write_status_merge(&root, f).unwrap();
        let t0 = Instant::now();
        assert!(wait_own_stop(&root, 9, std::process::id(), 2_000).is_ok());
        assert!(t0.elapsed() < Duration::from_secs(2));
        let _ = std::fs::remove_dir_all(&root);
    }

    /// worker 自报 stop 失败（stop_seq 对号 + state=error）要把错误透出去，
    /// 不能吞成「已停止」。
    #[test]
    fn wait_own_stop_surfaces_the_workers_stop_error() {
        let root = tmp_root("stop-seq-err");
        let mut f = Map::new();
        f.insert("state".into(), json!("error"));
        f.insert("error".into(), json!("stop: boom"));
        f.insert("stop_seq".into(), json!(9));
        protocol::write_status_merge(&root, f).unwrap();
        let err = wait_own_stop(&root, 9, std::process::id(), 2_000).unwrap_err();
        assert!(err.contains("boom"), "worker 的 stop 报错要透出：{err}");
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 软停全链路：派发 stop 之后必须等到「这条 seq」的完结记录才算停。
    /// 认领线程模仿 worker：先写 last_cmd_seq（认领），再写 stop_seq+idle
    /// （_worker_stop 收尾）。stop_vc 晚于第二条写返回才算对。
    #[test]
    fn soft_stop_waits_for_the_workers_own_completion() {
        let _identity_guard = identity_test_lock();
        let root = tmp_root("stop-fullpath");
        fake_live_worker(&root);
        let root_t = root.clone();
        let claimer = thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(10);
            while Instant::now() < deadline {
                let seq = protocol::read_command(&root_t)
                    .get("seq")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0);
                if seq > 0 {
                    let mut f = Map::new();
                    f.insert("last_cmd_seq".into(), json!(seq));
                    f.insert("state".into(), json!("running"));
                    protocol::write_status_merge(&root_t, f).unwrap();
                    // 模拟 _worker_stop 的处理耗时：认领不等于停完。
                    thread::sleep(Duration::from_millis(120));
                    let mut f = Map::new();
                    f.insert("stop_seq".into(), json!(seq));
                    f.insert("state".into(), json!("idle"));
                    protocol::write_status_merge(&root_t, f).unwrap();
                    return;
                }
                thread::sleep(Duration::from_millis(20));
            }
        });
        let t0 = Instant::now();
        assert!(stop_vc(&root, false).is_ok(), "自己的 stop 完结后必须 Ok");
        assert!(
            t0.elapsed() >= Duration::from_millis(100),
            "没等 worker 的完结记录就返回 = 假停止"
        );
        claimer.join().unwrap();
        let _ = std::fs::remove_dir_all(&root);
        forget_identity(std::process::id());
    }

    /// 设备列表同理：claimed（last_cmd_seq）不等于枚举完。worker 心跳
    /// 里带的旧设备列表不是本次刷新的结果 —— 只认 devices_seq 对号。
    #[test]
    fn list_devices_returns_only_this_enumerations_result() {
        let _identity_guard = identity_test_lock();
        let root = tmp_root("dev-stale");
        fake_live_worker(&root);
        let mut f = Map::new();
        f.insert("state".into(), json!("idle"));
        f.insert("pid".into(), json!(std::process::id()));
        protocol::write_status_merge(&root, f).unwrap();
        let root_t = root.clone();
        // 认领线程：认领后先写一条带旧设备的心跳（不碰 devices_seq），
        // 再把本次枚举的结果连同 devices_seq 落盘。
        let claimer = thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(10);
            while Instant::now() < deadline {
                let seq = protocol::read_command(&root_t)
                    .get("seq")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0);
                if seq > 0 {
                    let mut f = Map::new();
                    f.insert("last_cmd_seq".into(), json!(seq));
                    f.insert("input_devices".into(), json!(["stale-mic"]));
                    f.insert("output_devices".into(), json!(["stale-spk"]));
                    f.insert("hostapis".into(), json!(["stale-api"]));
                    protocol::write_status_merge(&root_t, f).unwrap();
                    thread::sleep(Duration::from_millis(120));
                    let mut f = Map::new();
                    f.insert("devices_seq".into(), json!(seq));
                    f.insert("input_devices".into(), json!(["fresh-mic"]));
                    f.insert("output_devices".into(), json!(["fresh-spk"]));
                    f.insert("hostapis".into(), json!(["fresh-api"]));
                    protocol::write_status_merge(&root_t, f).unwrap();
                    return;
                }
                thread::sleep(Duration::from_millis(20));
            }
        });
        let st = ensure_worker_and_devices(&root, 5_000);
        claimer.join().unwrap();
        assert_eq!(
            st.get("input_devices").and_then(|v| v.as_array()).map(|a| a[0].as_str().unwrap_or("")),
            Some("fresh-mic"),
            "返回的必须是本次枚举的列表，不是认领时的旧数据"
        );
        let _ = std::fs::remove_dir_all(&root);
        forget_identity(std::process::id());
    }

    /// 对偶：worker 认领了却永远不写 devices_seq（旧版 worker / 卡死），
    /// 有界超时必须是 error，不能交回陈旧列表。
    #[test]
    fn list_devices_without_completion_marker_is_an_error() {
        let _identity_guard = identity_test_lock();
        let root = tmp_root("dev-nomarker");
        fake_live_worker(&root);
        let mut f = Map::new();
        f.insert("state".into(), json!("idle"));
        f.insert("pid".into(), json!(std::process::id()));
        protocol::write_status_merge(&root, f).unwrap();
        let root_t = root.clone();
        let claimer = thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(5);
            while Instant::now() < deadline {
                let seq = protocol::read_command(&root_t)
                    .get("seq")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0);
                if seq > 0 {
                    let mut f = Map::new();
                    f.insert("last_cmd_seq".into(), json!(seq));
                    f.insert("input_devices".into(), json!(["stale-mic"]));
                    f.insert("hostapis".into(), json!(["stale-api"]));
                    protocol::write_status_merge(&root_t, f).unwrap();
                    return;
                }
                thread::sleep(Duration::from_millis(20));
            }
        });
        let st = ensure_worker_and_devices(&root, 700);
        claimer.join().unwrap();
        assert_eq!(
            st.get("state").and_then(|v| v.as_str()),
            Some("error"),
            "没有 devices_seq 对号就必须报错，不许交回陈旧数据"
        );
        let _ = std::fs::remove_dir_all(&root);
        forget_identity(std::process::id());
    }
}
