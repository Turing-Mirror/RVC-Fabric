//! Spawn / track Runtime pythonw realtime_worker (file protocol).
//!
//! Behaviour mirrors launcher/realtime_client.py where it matters:
//! one worker, cleaned env, pythonw preferred, soft stop then force.

use std::collections::HashMap;
use std::fs::OpenOptions;
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
            forget_identity_cache();
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

pub fn send_command(root: &Path, cmd: &str, payload: Map<String, Value>) -> Result<u64, String> {
    // command.json is a single-slot mailbox. The worker polls ~every 80 ms and
    // only keeps the latest file contents. If the shell writes set → start → set
    // faster than that poll, `start` is overwritten and never runs — the dock
    // freezes on「引擎就绪 / 参数已应用」(diag 26.8.6/bug/1: many set/stop,
    // zero start after relaunch). Wait for the previous command to be claimed
    // (status.last_cmd_seq) before replacing the mailbox.
    let pending = protocol::read_command(root);
    let pending_seq = pending
        .get("seq")
        .and_then(|v| v.as_u64().or_else(|| v.as_i64().map(|i| i as u64)))
        .unwrap_or(0);
    let last_ack = protocol::last_cmd_seq(root);
    if pending_seq > last_ack {
        // Worker loop is 80 ms; 3 s covers a busy GC / disk hiccup. Past that
        // we still write so the UI cannot deadlock on a dead worker.
        let acked = protocol::wait_cmd_acked(root, pending_seq, 3_000);
        if !acked {
            append_log(
                root,
                &format!(
                    "send_command: previous seq={pending_seq} not acked before writing {cmd} (last_ack={last_ack})"
                ),
            );
        }
    }
    protocol::write_command(root, cmd, payload).map_err(|e| e.to_string())
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
            return json!({"state": "error", "error": &crate::i18n::t("s.wkDiedListDevices"), "pid": 0});
        }
        thread::sleep(Duration::from_millis(200));
    }
    protocol::read_status(root)
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

/// Soft-stop then start (same order as Tk shell before start_vc_remote).
pub fn start_vc(root: &Path) -> Result<u64, String> {
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
    let payload = dsp_command_fields(&cfg);
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
    Ok(seq)
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

pub fn stop_vc(root: &Path, force: bool) -> Result<(), String> {
    let pid = get_live_pid(root);
    if pid == 0 {
        if force {
            kill_known_workers(root);
            kill_runtime_pythons(root, true);
        }
        return Ok(());
    }
    let _ = send_command(root, "stop", Map::new());
    // force：给 stop_stream / AudioIoProcess.join 几秒，再杀树。
    // 软停：等 worker 自己落到 idle，进程留下给下次开启用。
    let deadline = Instant::now() + Duration::from_secs(if force { 3 } else { 12 });
    while Instant::now() < deadline {
        if !pid_alive(pid) {
            break;
        }
        let st = protocol::read_status(root);
        if st.get("state").and_then(|v| v.as_str()) != Some("running") {
            if !force {
                return Ok(());
            }
            break;
        }
        thread::sleep(Duration::from_millis(200));
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
    let mut payload = Map::new();
    payload.insert("pth_path".into(), json!(pth));
    payload.insert(
        "index_path".into(),
        json!(cfg.get("index_path").and_then(|v| v.as_str()).unwrap_or("")),
    );
    if let Some(r) = cfg.get("index_rate") {
        payload.insert("index_rate".into(), r.clone());
    }
    set_hot(root, payload)
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
        let d = std::env::temp_dir().join(format!("rvcf-worker-{name}"));
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

    /// 一次启动开出两个 worker 的时候，多出来那个必须留下痕迹。
    ///
    /// `worker.pid` 只有一行，后写的盖掉先写的 —— 于是先起来那个再也没人认识，
    /// 退出时杀不掉，它会一直占着声卡活到用户重启电脑。台账就是补这条记忆。
    #[test]
    fn every_spawned_pid_stays_on_the_ledger() {
        let dir = std::env::temp_dir().join(format!("rvcf_pids_{}", std::process::id()));
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
        let dir = std::env::temp_dir().join(format!("rvcf_pid0_{}", std::process::id()));
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
        let dir = std::env::temp_dir().join(format!("rvcf_live_{}", std::process::id()));
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
}
