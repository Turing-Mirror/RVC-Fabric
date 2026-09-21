//! Runtime presence, GPU recommendation, download + extract (stage 3).

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

use crate::catalog;
use crate::config;
use crate::download::{self, ProgressFn};
use crate::extract;
use crate::paths;
use crate::worker;

static PROVISION_BUSY: Mutex<bool> = Mutex::new(false);

/// RAII guard for the one-runtime-operation-at-a-time rule. Downloads and the
/// one-time migration both move trees under `Runtimes/`; overlapping them
/// means two movers on the same directory.
pub struct ProvisionGuard {
    _private: (),
}

impl Drop for ProvisionGuard {
    fn drop(&mut self) {
        let mut g = PROVISION_BUSY.lock().unwrap_or_else(|e| e.into_inner());
        *g = false;
    }
}

pub fn try_begin() -> Result<ProvisionGuard, String> {
    let mut g = PROVISION_BUSY.lock().unwrap_or_else(|e| e.into_inner());
    if *g {
        return Err(crate::i18n::t("s.eca157a71e"));
    }
    *g = true;
    Ok(ProvisionGuard { _private: () })
}
/// Shared with download layer (async-fetcher shutdown).
static CANCEL: std::sync::OnceLock<Arc<AtomicBool>> = std::sync::OnceLock::new();

fn cancel_flag() -> Arc<AtomicBool> {
    CANCEL
        .get_or_init(|| Arc::new(AtomicBool::new(false)))
        .clone()
}

/// nvidia | nvidia50 | amd | unknown
pub fn recommend_variant(gpu_names: &[String]) -> (String, String) {
    let joined = gpu_names.join(" | ").to_ascii_lowercase();
    if joined.is_empty() {
        return ("unknown".into(), crate::i18n::t("s.47c37d6efa"));
    }
    if joined.contains("rtx 50")
        || joined.contains("rtx50")
        || joined.contains("5060")
        || joined.contains("5070")
        || joined.contains("5080")
        || joined.contains("5090")
    {
        return (
            "nvidia50".into(),
            crate::i18n::t("s.8289d5d0bc").replacen("{}", &gpu_names[0], 1),
        );
    }
    if joined.contains("nvidia")
        || joined.contains("geforce")
        || joined.contains("rtx")
        || joined.contains("gtx")
        || joined.contains("quadro")
    {
        return (
            "nvidia".into(),
            crate::i18n::t("s.3967a4b124").replacen("{}", &gpu_names[0], 1),
        );
    }
    if joined.contains("amd")
        || joined.contains("radeon")
        || joined.contains("intel")
        || joined.contains("arc")
        || joined.contains("uhd")
        || joined.contains("iris")
    {
        return (
            "amd".into(),
            crate::i18n::t("s.c0b4d5c2f4").replacen("{}", &gpu_names[0], 1),
        );
    }
    (
        "unknown".into(),
        crate::i18n::t("s.e12d8322af").replacen("{}", &gpu_names.join(", "), 1),
    )
}

/// 名字看起来是不是一块 N 卡。
///
/// 只用来筛「主显卡」那个下拉里能选的项：CUDA 只看得见 N 卡，把核显和 A 卡也
/// 列进去，用户选了之后序号还会往后错一位，等于给自己挖坑。
pub(crate) fn looks_like_nvidia(name: &str) -> bool {
    let n = name.to_ascii_lowercase();
    ["nvidia", "geforce", "rtx", "gtx", "quadro", "tesla"]
        .iter()
        .any(|k| n.contains(k))
}

/// 能选作「主显卡」的 N 卡，顺序即 `CUDA_VISIBLE_DEVICES` 的序号。
///
/// 序号必须和 CUDA 自己数出来的一致，所以优先问 `nvidia-smi`：它按 PCI bus 排，
/// 而 `worker::apply_main_gpu` 会一并设 `CUDA_DEVICE_ORDER=PCI_BUS_ID`，两边天然
/// 对齐。
///
/// 注册表那份列表只在 `nvidia-smi` 不在时兜底，因为它数的是显示适配器而不是
/// 计算设备：已禁用的卡、拔掉之后残留的驱动键都还在里面，虚拟显示器（串流、
/// VR、远程桌面）也照样占位。于是「第 N 个名字带 NVIDIA 的注册表项」和「第 N
/// 块 CUDA 设备」可以完全对不上号 —— 用户选了列表里的第二块卡，环境变量却指向
/// 一个不存在的设备，CUDA 直接报 0 设备、`is_available()` 变 false，整个引擎静默
/// 掉进 DirectML。这不是「选错卡慢一点」，是显卡整块消失。
pub fn list_nvidia_gpus() -> Vec<String> {
    static NV: std::sync::OnceLock<Vec<String>> = std::sync::OnceLock::new();
    NV.get_or_init(|| {
        if let Some(v) = nvidia_smi_gpus() {
            crate::logging::shell_log!("nvidia gpus (nvidia-smi): {:?}", v);
            return v;
        }
        let v: Vec<String> = list_gpus()
            .into_iter()
            .filter(|g| looks_like_nvidia(g))
            .collect();
        crate::logging::shell_log!("nvidia gpus (registry fallback): {:?}", v);
        v
    })
    .clone()
}

/// `nvidia-smi --query-gpu=index,name`，读到什么就是 CUDA 数得到什么。
///
/// 超时是必须的：`Command::output()` 没有超时，而这个进程在驱动出问题的机器上
/// 是会挂住的 —— 结果被 `OnceLock` 记住，一次卡死就把后面每一个调用者一起拖住，
/// 表现是应用打开之后再也画不完。所以放线程里跑，到点就当没有。
///
/// 返回 `None` 表示「问不到」，不是「没有 N 卡」：两者要分开，前者该退回注册表，
/// 后者不该。
fn nvidia_smi_gpus() -> Option<Vec<String>> {
    use std::sync::mpsc;
    use std::time::Duration;

    let (tx, rx) = mpsc::channel::<Option<String>>();
    std::thread::spawn(move || {
        let mut cmd = std::process::Command::new("nvidia-smi");
        cmd.args(["--query-gpu=index,name", "--format=csv,noheader"]);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
        }
        let out = cmd
            .output()
            .ok()
            .filter(|o| o.status.success())
            .map(|o| String::from_utf8_lossy(&o.stdout).into_owned());
        let _ = tx.send(out);
    });

    match rx.recv_timeout(Duration::from_secs(5)) {
        Ok(Some(t)) => parse_nvidia_smi(&t),
        // 超时的线程仍在跑，但它只持有自己的 sender，发不出去就结束，不泄漏。
        Ok(None) | Err(_) => None,
    }
}

/// 每行 `0, NVIDIA GeForce RTX 3060`。按 index 排一遍再取名字，不依赖输出顺序。
fn parse_nvidia_smi(text: &str) -> Option<Vec<String>> {
    let mut rows: Vec<(u32, String)> = Vec::new();
    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let Some((idx, name)) = line.split_once(',') else {
            continue;
        };
        let Ok(idx) = idx.trim().parse::<u32>() else {
            continue;
        };
        let name = name.trim();
        if name.is_empty() {
            continue;
        }
        rows.push((idx, name.to_string()));
    }
    if rows.is_empty() {
        return None;
    }
    rows.sort_by_key(|(i, _)| *i);
    Some(rows.into_iter().map(|(_, n)| n).collect())
}

/// Enumerated once per run. The video controller set does not change while the
/// app is open, and this used to be a PowerShell launch that ran every time the
/// provision gate opened or a diagnostics bundle was built.
static GPUS: std::sync::OnceLock<Vec<String>> = std::sync::OnceLock::new();

pub fn list_gpus() -> Vec<String> {
    GPUS.get_or_init(|| {
        let t = std::time::Instant::now();
        let g = enumerate_gpus();
        crate::logging::shell_log!("gpu enumeration: {:?} in {} ms", g, t.elapsed().as_millis());
        g
    })
    .clone()
}

/// Display adapters, read straight out of the class key Device Manager lists.
///
/// This was `Get-CimInstance Win32_VideoController` through PowerShell. Two
/// problems with that on a user's machine: a PowerShell cold start is 300–800
/// ms, and on a box with a damaged WMI repository the query does not return at
/// all. `Command::output()` has no timeout, and the result is memoised behind a
/// `OnceLock` — so one wedged WMI call blocked the initialiser forever and
/// every later caller with it, which is a first-run app that opens and then
/// never finishes drawing the provision gate. A registry read cannot hang and
/// needs no child process.
#[cfg(windows)]
fn enumerate_gpus() -> Vec<String> {
    use std::ffi::{OsStr, OsString};
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    use windows_sys::Win32::Foundation::ERROR_SUCCESS;
    use windows_sys::Win32::System::Registry::{
        RegCloseKey, RegEnumKeyExW, RegOpenKeyExW, RegQueryValueExW, HKEY, HKEY_LOCAL_MACHINE,
        KEY_READ,
    };

    fn wide(s: &str) -> Vec<u16> {
        OsStr::new(s)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect()
    }

    // GUID_DEVCLASS_DISPLAY.
    const CLASS: &str =
        r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}";

    let mut out: Vec<String> = Vec::new();
    unsafe {
        let mut class_key: HKEY = std::ptr::null_mut();
        if RegOpenKeyExW(
            HKEY_LOCAL_MACHINE,
            wide(CLASS).as_ptr(),
            0,
            KEY_READ,
            &mut class_key,
        ) != ERROR_SUCCESS
        {
            return out;
        }
        let mut i: u32 = 0;
        loop {
            let mut name = [0u16; 256];
            let mut len: u32 = name.len() as u32;
            if RegEnumKeyExW(
                class_key,
                i,
                name.as_mut_ptr(),
                &mut len,
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
            ) != ERROR_SUCCESS
            {
                break;
            }
            i += 1;
            // Adapters are the numbered subkeys (0000, 0001, …); siblings like
            // "Properties" are not devices.
            let sub = OsString::from_wide(&name[..len as usize])
                .to_string_lossy()
                .to_string();
            if sub.is_empty() || !sub.chars().all(|c| c.is_ascii_digit()) {
                continue;
            }
            let mut dev: HKEY = std::ptr::null_mut();
            if RegOpenKeyExW(class_key, wide(&sub).as_ptr(), 0, KEY_READ, &mut dev) != ERROR_SUCCESS
            {
                continue;
            }
            let mut buf = [0u16; 512];
            let mut cb: u32 = std::mem::size_of_val(&buf) as u32;
            let rc = RegQueryValueExW(
                dev,
                wide("DriverDesc").as_ptr(),
                std::ptr::null(),
                std::ptr::null_mut(),
                buf.as_mut_ptr() as *mut u8,
                &mut cb,
            );
            RegCloseKey(dev);
            if rc != ERROR_SUCCESS {
                continue;
            }
            // cb is bytes and includes the terminating NUL.
            let chars = (cb as usize / 2).min(buf.len());
            let s = OsString::from_wide(&buf[..chars])
                .to_string_lossy()
                .trim_end_matches('\0')
                .trim()
                .to_string();
            if !s.is_empty() && !out.contains(&s) {
                out.push(s);
            }
        }
        RegCloseKey(class_key);
    }
    out
}

#[cfg(not(windows))]
fn enumerate_gpus() -> Vec<String> {
    vec![]
}

/// CPU 名称：注册表 `CentralProcessor\0` 的 ProcessorNameString。
/// 与 enumerate_gpus 同一套读法——不起 PowerShell、不会挂起（C-05）。
#[cfg(windows)]
pub fn cpu_name() -> String {
    use std::ffi::{OsStr, OsString};
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    use windows_sys::Win32::Foundation::ERROR_SUCCESS;
    use windows_sys::Win32::System::Registry::{
        RegCloseKey, RegOpenKeyExW, RegQueryValueExW, HKEY, HKEY_LOCAL_MACHINE, KEY_READ,
    };

    fn wide(s: &str) -> Vec<u16> {
        OsStr::new(s)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect()
    }
    unsafe {
        let mut key: HKEY = std::ptr::null_mut();
        if RegOpenKeyExW(
            HKEY_LOCAL_MACHINE,
            wide(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0").as_ptr(),
            0,
            KEY_READ,
            &mut key,
        ) != ERROR_SUCCESS
        {
            return String::new();
        }
        let mut buf = [0u16; 512];
        let mut cb: u32 = std::mem::size_of_val(&buf) as u32;
        let rc = RegQueryValueExW(
            key,
            wide("ProcessorNameString").as_ptr(),
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            buf.as_mut_ptr() as *mut u8,
            &mut cb,
        );
        RegCloseKey(key);
        if rc != ERROR_SUCCESS {
            return String::new();
        }
        let chars = (cb as usize / 2).min(buf.len());
        OsString::from_wide(&buf[..chars])
            .to_string_lossy()
            .trim_end_matches('\0')
            .trim()
            .to_string()
    }
}

#[cfg(not(windows))]
pub fn cpu_name() -> String {
    String::new()
}

/// 物理内存总量（GB，一位小数）。读不出来就给 0，界面把它当「未知」。
#[cfg(windows)]
pub fn memory_gb() -> f64 {
    use windows_sys::Win32::System::SystemInformation::{
        GlobalMemoryStatusEx, MEMORYSTATUSEX,
    };
    unsafe {
        let mut st: MEMORYSTATUSEX = std::mem::zeroed();
        st.dwLength = std::mem::size_of::<MEMORYSTATUSEX>() as u32;
        if GlobalMemoryStatusEx(&mut st) == 0 {
            return 0.0;
        }
        (st.ullTotalPhys as f64 / 1024.0 / 1024.0 / 1024.0 * 10.0).round() / 10.0
    }
}

#[cfg(not(windows))]
pub fn memory_gb() -> f64 {
    0.0
}

pub fn read_package_meta_variant(root: &Path) -> Option<String> {
    let p = paths::package_meta_path(root);
    if !p.is_file() {
        return None;
    }
    let text = std::fs::read_to_string(p).ok()?;
    let v: Value = serde_json::from_str(&text).ok()?;
    v.get("variant")
        .or_else(|| v.get("runtime_variant"))
        .and_then(|x| x.as_str())
        .and_then(paths::normalize_runtime_variant)
        .map(str::to_string)
        // The universal Setup writes an empty variant on purpose: the app picks
        // it after detecting the GPU. Empty must read as "not chosen", not as a
        // variant named "".
        .filter(|s| !s.is_empty())
}

pub fn read_runtime_meta(root: &Path, variant: &str) -> Option<Value> {
    let path = paths::runtime_meta_path(root, variant);
    fs::read_to_string(path)
        .ok()
        .and_then(|text| serde_json::from_str(&text).ok())
}

fn runtime_meta_value(variant: &str, label: &str, version: &str) -> Value {
    let (accel, use_dml, summary) = match variant {
        "amd" => ("dml", true, crate::i18n::t("s.ab31cc9ebb")),
        "nvidia50" => ("cuda", false, crate::i18n::t("s.083e3aad12")),
        _ => ("cuda", false, "NVIDIA CUDA Runtime".to_string()),
    };
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    json!({
        "variant": variant,
        "label": label,
        "accel_default": accel,
        "use_dml": use_dml,
        "summary": summary,
        "runtime_version": version,
        "runtime_source": "cnb_release",
        "provisioned_at_unix": now,
        "tagged": true,
    })
}

pub fn write_runtime_meta_at(
    runtime_dir: &Path,
    variant: &str,
    label: &str,
    version: &str,
) -> Result<(), String> {
    let data = runtime_meta_value(variant, label, version);
    let path = runtime_dir.join("runtime.json");
    fs::write(
        &path,
        serde_json::to_string_pretty(&data).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())
}

pub fn write_package_meta(
    root: &Path,
    variant: &str,
    label: &str,
    version: &str,
) -> Result<(), String> {
    let data = runtime_meta_value(variant, label, version);
    let path = paths::package_meta_path(root);
    fs::write(
        &path,
        serde_json::to_string_pretty(&data).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    let managed = paths::runtime_variant_dir(root, variant);
    if managed.is_dir() {
        write_runtime_meta_at(&managed, variant, label, version)?;
    }
    Ok(())
}

fn runtime_meta_field(root: &Path, variant: &str, key: &str) -> String {
    read_runtime_meta(root, variant)
        .and_then(|meta| meta.get(key).and_then(|v| v.as_str()).map(str::to_string))
        .or_else(|| {
            let root_meta = fs::read_to_string(paths::package_meta_path(root))
                .ok()
                .and_then(|text| serde_json::from_str::<Value>(&text).ok())?;
            root_meta
                .get(key)
                .and_then(|v| v.as_str())
                .map(str::to_string)
        })
        .unwrap_or_default()
}

pub fn activate_runtime(root: &Path, variant: &str) -> Result<(), String> {
    let id = paths::normalize_runtime_variant(variant)
        .ok_or_else(|| format!("unsupported runtime variant: {variant}"))?;
    if !paths::runtime_variant_ready(root, id) {
        return Err(crate::i18n::t("runtimeMigration.runtimeNotReady"));
    }
    let label = runtime_meta_field(root, id, "label");
    let label = if label.is_empty() {
        id.to_string()
    } else {
        label
    };
    let version = runtime_meta_field(root, id, "runtime_version");
    config::set_runtime_variant(root, id)?;
    write_package_meta(root, id, &label, &version)
}

fn cache_dir(root: &Path) -> PathBuf {
    let d = paths::user_data(root).join("update_cache").join("runtime");
    let _ = fs::create_dir_all(&d);
    d
}

fn format_size(n: u64) -> String {
    if n >= 1_000_000_000 {
        format!("{:.2} GB", n as f64 / 1e9)
    } else if n >= 1_000_000 {
        format!("{:.1} MB", n as f64 / 1e6)
    } else {
        format!("{n} B")
    }
}

pub fn provision_status(root: &Path) -> Value {
    let migration_required = paths::runtime_migration_required(root);
    let ready = paths::runtime_ready(root);
    let pyw = paths::runtime_pythonw(root);
    let gpus = list_gpus();
    let (recommended, reason) = recommend_variant(&gpus);
    let active = paths::active_runtime_variant(root);
    let legacy_variant = read_package_meta_variant(root);
    let legacy_ready = paths::legacy_runtime_dir(root)
        .map(|dir| paths::runtime_tree_ready(&dir))
        .unwrap_or(false);
    let installed = active.clone().or(legacy_variant.clone());
    let worker_script = paths::worker_script(root).is_file();
    let need_provision = !ready;
    let busy = *PROVISION_BUSY.lock().unwrap_or_else(|e| e.into_inner());

    // Per-variant sizes so the UI can follow the user's selection, not only
    // the recommended package. One catalog fetch is cached for ~5 minutes.
    let variant_defs = [
        ("nvidia", crate::i18n::t("s.4c65a5e25e")),
        ("nvidia50", crate::i18n::t("s.e7a64d4aaf")),
        ("amd", crate::i18n::t("s.variantAmd")),
    ];
    let mut variants = Vec::with_capacity(3);
    let mut size_hint = 0u64;
    let mut label = recommended.clone();
    let rec_key = if recommended == "unknown" {
        "nvidia"
    } else {
        recommended.as_str()
    };
    for (id, fallback_label) in &variant_defs {
        let id = *id;
        let (sz, lab, latest_version) = match catalog::resolve_runtime_spec(id, true) {
            Ok(spec) => {
                let s = spec.size_bytes.max(spec.part.size_bytes);
                let l = if spec.label.is_empty() {
                    fallback_label.clone()
                } else {
                    spec.label
                };
                (s, l, spec.version)
            }
            Err(_) => (0u64, fallback_label.clone(), String::new()),
        };
        if id == rec_key {
            size_hint = sz;
            label = lab.clone();
        }
        let is_managed = paths::runtime_variant_ready(root, id);
        let is_legacy = legacy_ready && legacy_variant.as_deref() == Some(id);
        let installed_for_variant = is_managed || is_legacy;
        let active_for_variant =
            active.as_deref() == Some(id) || (active.is_none() && is_legacy && !migration_required);
        let installed_version = if installed_for_variant {
            runtime_meta_field(root, id, "runtime_version")
        } else {
            String::new()
        };
        let update_available = !installed_version.is_empty()
            && !latest_version.is_empty()
            && crate::update::compare_versions(&installed_version, &latest_version) < 0;
        variants.push(json!({
            "id": id,
            "label": fallback_label,
            "size_bytes": sz,
            "size_label": format_size(sz),
            "installed": installed_for_variant,
            "active": active_for_variant,
            "installed_version": if installed_version.is_empty() { Value::Null } else { json!(installed_version) },
            "latest_version": if latest_version.is_empty() { Value::Null } else { json!(latest_version) },
            "update_available": update_available,
        }));
    }

    let active_latest_version = active
        .as_deref()
        .or_else(|| {
            if migration_required {
                legacy_variant.as_deref()
            } else {
                None
            }
        })
        .and_then(|id| catalog::resolve_runtime_spec(id, true).ok())
        .map(|spec| spec.version)
        .filter(|version| !version.is_empty());
    let installed_version = installed
        .as_deref()
        .map(|id| runtime_meta_field(root, id, "runtime_version"))
        .filter(|version| !version.is_empty());

    json!({
        "runtime_ready": ready,
        "need_provision": need_provision,
        "runtime_migration_required": migration_required,
        "runtime_python": pyw.map(|p| p.to_string_lossy().to_string()),
        "worker_script_ok": worker_script,
        "product_root": root.to_string_lossy(),
        "gpus": gpus,
        // C-05 安装前能力说明的原料：CPU 型号与内存总量（读不到留空/0，
        // 界面按「未知」处理，不编数字）。
        "cpu_name": cpu_name(),
        "memory_gb": memory_gb(),
        // 「主显卡」下拉的候选项。下标即 CUDA 序号。
        "nvidia_gpus": list_nvidia_gpus(),
        "recommended_variant": recommended,
        "recommend_reason": reason,
        "recommended_label": label,
        "recommended_size_bytes": size_hint,
        "recommended_size_label": format_size(size_hint),
        "installed_variant": installed,
        "installed_version": installed_version,
        "latest_runtime_version": active_latest_version,
        "worker_alive": crate::worker::is_worker_alive(root),
        "download_supported": true,
        "busy": busy,
        "variants": variants,
        "message": if migration_required {
            crate::i18n::t("runtimeMigration.description")
        } else if need_provision {
            crate::i18n::t("s.2ae4c43ac6")
        } else if !worker_script {
            crate::i18n::t("s.ee7e83d91d")
        } else {
            crate::i18n::t("s.f2e88c071e")
        },
    })
}

fn format_speed(bps: u64) -> String {
    if bps == 0 {
        return "—".into();
    }
    if bps >= 1_000_000_000 {
        format!("{:.2} GB/s", bps as f64 / 1e9)
    } else if bps >= 1_000_000 {
        format!("{:.1} MB/s", bps as f64 / 1e6)
    } else if bps >= 1_000 {
        format!("{:.0} KB/s", bps as f64 / 1e3)
    } else {
        format!("{bps} B/s")
    }
}

/// 解压这一步失败时说清楚「不是网的问题」。
///
/// 走到解压说明 tar 的 sha256 已经对上了 —— 包本身是好的。用户看到一句
/// 「解压失败 Lib/site-packages/…: 拒绝访问」只会以为又得重下，实际上重下
/// 一遍还是同样的错，真正要动的是杀软白名单或者磁盘空间。
fn extract_error_text(raw: &str) -> String {
    let why = crate::download::explain_error(raw)
        .map(crate::i18n::t)
        .unwrap_or_else(|| crate::i18n::t("s.rtExtractFailed"));
    format!(
        "{}\n\n{}\n\n{}",
        why,
        crate::i18n::t("s.rtExtractHelp"),
        crate::i18n::te("s.dlDetail", &raw),
    )
}

fn emit_progress(app: &AppHandle, phase: &str, done: u64, total: u64, message: &str) {
    emit_progress_speed(app, phase, done, total, 0, message);
}

fn emit_progress_speed(
    app: &AppHandle,
    phase: &str,
    done: u64,
    total: u64,
    speed_bps: u64,
    message: &str,
) {
    let total = total.max(1);
    // Keep a fractional percent so multi-GB downloads do not sit at "0%" until
    // hundreds of MB have landed (round(0.4) == 0).
    let pct = ((done as f64 / total as f64) * 100.0).clamp(0.0, 100.0);
    let _ = app.emit(
        "provision-progress",
        json!({
            "phase": phase,
            "done": done,
            "total": total,
            "percent": pct,
            "speed_bps": speed_bps,
            "speed_label": format_speed(speed_bps),
            "message": message,
        }),
    );
}

pub fn cancel_provision() {
    cancel_flag().store(true, Ordering::SeqCst);
}

fn replace_managed_runtime(root: &Path, variant: &str, staged: &Path) -> Result<(), String> {
    let target = paths::runtime_variant_dir(root, variant);
    let backup = paths::update_cache(root)
        .join("runtime_backup")
        .join(variant);
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    if let Some(parent) = backup.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }

    // A previous process may have stopped between the two renames. Restore
    // that old tree before starting a new replacement attempt.
    if !target.exists() && backup.exists() {
        let _ = fs::rename(&backup, &target);
    }
    if target.exists() {
        if !target.is_dir() {
            return Err(crate::i18n::te(
                "runtimeMigration.targetExists",
                &(target.display()),
            ));
        }
        if backup.exists() {
            fs::remove_dir_all(&backup).map_err(|e| e.to_string())?;
        }
        fs::rename(&target, &backup).map_err(|e| crate::i18n::te("s.90e6bba99d", &(e)))?;
    }

    if let Err(error) = fs::rename(staged, &target) {
        if backup.exists() && !target.exists() {
            let _ = fs::rename(&backup, &target);
        }
        return Err(crate::i18n::te("s.90e6bba99d", &(error)));
    }
    let _ = fs::remove_dir_all(&backup);
    Ok(())
}

fn ensure_worker_background(root: PathBuf) {
    std::thread::spawn(move || {
        let r = crate::worker::ensure_worker_and_devices(&root, 90_000);
        let n = r
            .get("input_devices")
            .and_then(|v| v.as_array())
            .map(|a| a.len())
            .unwrap_or(0);
        let mut vars = std::collections::HashMap::new();
        vars.insert("n".to_string(), n.to_string());
        crate::logging::shell_log!("{}", crate::i18n::t_vars("s.5c5f9ed8e4", &vars));
    });
}

/// Download + extract Runtime for *variant*. Emits `provision-progress` events.
pub fn run_provision(
    app: AppHandle,
    root: PathBuf,
    variant: String,
    force: bool,
) -> Result<Value, String> {
    // Held until the end of the function; Drop releases the flag even on
    // panic, so a wedged run can't report 「已有补全任务在进行」 forever.
    let _op_guard = try_begin()?;
    cancel_flag().store(false, Ordering::SeqCst);

    let result: Result<Value, String> = (|| {
        let var = paths::normalize_runtime_variant(&variant)
            .unwrap_or("nvidia")
            .to_string();
        if paths::runtime_migration_required(&root) {
            return Err(crate::i18n::t("runtimeMigration.required"));
        }

        let active = paths::active_runtime_variant(&root);
        if paths::runtime_variant_ready(&root, &var) && !force {
            if worker::is_worker_alive(&root) && active.as_deref() != Some(var.as_str()) {
                return Err(crate::i18n::t("runtimeMigration.stopEngine"));
            }
            activate_runtime(&root, &var)?;
            if !worker::is_worker_alive(&root) {
                ensure_worker_background(root.clone());
            }
            emit_progress(&app, "done", 1, 1, &crate::i18n::t("runtimeMigration.done"));
            return Ok(json!({
                "ok": true,
                "message": crate::i18n::t("runtimeActions.switchDone"),
                "variant": var,
                "action": "switch",
                "version": runtime_meta_field(&root, &var, "runtime_version"),
            }));
        }

        // Replacing or activating a Runtime while its Python worker is using
        // the files is unsafe. The old tree is kept until the user stops it.
        if worker::is_worker_alive(&root) {
            return Err(crate::i18n::t("runtimeMigration.stopEngine"));
        }
        // WebUI / 实时面板 / 常驻转换都不在 worker 台账里，但它们的 pythonw
        // 就住在要被换掉的目录下 —— 不先拦住，6GB 下完 rename 才「拒绝访问」。
        let busy = worker::pythons_under(&paths::runtime_variant_dir(&root, &var));
        if !busy.is_empty() {
            return Err(crate::i18n::te(
                "runtimeMigration.runtimeBusy",
                &(busy.len()),
            ));
        }

        emit_progress(&app, "catalog", 0, 1, &crate::i18n::t("s.bd45f9d523"));
        let spec = catalog::resolve_runtime_spec(&var, true)?;
        let part = &spec.part;
        if part.urls.is_empty() {
            return Err(crate::i18n::t("s.33d04e20c0"));
        }
        // The Runtime tar unpacks into python.exe and its libraries — running
        // it unverified is arbitrary code execution. download_request skips
        // verification on an empty hash, and the cache-reuse branch below would
        // also accept whatever is already on disk, so refuse up front.
        if part
            .sha256
            .chars()
            .filter(|c| c.is_ascii_hexdigit())
            .count()
            != 64
        {
            return Err(crate::i18n::t("s.09dfaea8c0"));
        }

        let size = spec.size_bytes.max(part.size_bytes);
        let conns_preview = download::auto_connections(size);
        emit_progress(
            &app,
            "download",
            0,
            size.max(1),
            &crate::i18n::tn(
                "s.c5f9b6cc72",
                &[
                    &spec.label,
                    if spec.version.is_empty() {
                        "?"
                    } else {
                        &spec.version
                    },
                    &format_size(size),
                    &conns_preview.to_string(),
                ],
            ),
        );

        let cache = cache_dir(&root);
        let dest_file = cache.join(if part.name.is_empty() {
            format!("runtime-{var}.tar")
        } else {
            part.name.clone()
        });

        // A deliberate update / re-download must not silently reuse the old
        // archive. A failed download still leaves the installed tree intact.
        if force && dest_file.is_file() {
            let _ = fs::remove_file(&dest_file);
        }

        // Reuse the cache only after verifying it. A stale or truncated file
        // must be dropped, never trusted because it happens to exist.
        if dest_file.is_file() {
            if download::verify_sha256(&dest_file, &part.sha256).is_ok() {
                emit_progress(
                    &app,
                    "download",
                    size.max(1),
                    size.max(1),
                    &crate::i18n::te(
                        "s.31eac83efc",
                        &dest_file
                            .file_name()
                            .map(|s| s.to_string_lossy())
                            .unwrap_or_default(),
                    ),
                );
            } else {
                let _ = fs::remove_file(&dest_file);
            }
        }

        if !dest_file.is_file() {
            let app_cb = app.clone();
            let size_hint = size.max(1);
            let conns = download::auto_connections(size);
            // Wall-clock + last sample for average / near-instant speed.
            let t0 = std::sync::Mutex::new(std::time::Instant::now());
            let last = std::sync::Mutex::new((std::time::Instant::now(), 0u64));
            let progress: ProgressFn = Arc::new(move |done, total, phase| {
                let total = total.max(size_hint).max(1);
                let now = std::time::Instant::now();
                let started = *t0.lock().unwrap_or_else(|e| e.into_inner());
                let mut guard = last.lock().unwrap_or_else(|e| e.into_inner());
                let (t_prev, d_prev) = *guard;
                let dt = now.duration_since(t_prev).as_secs_f64();
                // Prefer short-window speed once we have a real interval; else overall.
                let speed = if dt >= 0.12 && done >= d_prev {
                    ((done - d_prev) as f64 / dt) as u64
                } else {
                    let elapsed = now.duration_since(started).as_secs_f64().max(0.001);
                    (done as f64 / elapsed) as u64
                };
                if dt >= 0.12 || done < d_prev {
                    *guard = (now, done);
                }
                drop(guard);

                let pct = ((done as f64 / total as f64) * 100.0).clamp(0.0, 100.0);
                let m = match phase {
                    "verify" => crate::i18n::te("s.af05b41a37", &format_size(done.max(total))),
                    "retry" => crate::i18n::t("s.a24d69a01d"),
                    other if other.starts_with("retry:") => {
                        let n = download::parse_retry_attempt(other).unwrap_or(1);
                        crate::i18n::te("s.dlReconnect", &n)
                    }
                    other if other.starts_with("connecting:") => {
                        crate::i18n::te("s.d28fcd74d0", &(format_size(total)))
                    }
                    other if other.starts_with("download:") => crate::i18n::tn(
                        "s.3de4870b5b",
                        &[
                            &format_size(done),
                            &format_size(total),
                            &format_speed(speed),
                        ],
                    ),
                    _ if done == 0 => crate::i18n::te("s.11a39009ac", &(format_size(total))),
                    _ => crate::i18n::tn(
                        "s.c77af9b599",
                        &[
                            &format_size(done),
                            &format_size(total),
                            &format!("{:.1}", pct),
                            &format_speed(speed),
                        ],
                    ),
                };
                emit_progress_speed(&app_cb, phase, done, total, speed, &m);
            });
            // Shared pipeline (async-fetcher): same path for voice_pack / gui_patch later.
            download::download_request(
                download::DownloadRequest {
                    urls: part.urls.clone(),
                    root: Some(root.clone()),
                    dest: dest_file.clone(),
                    expected_sha256: part.sha256.clone(),
                    size_hint: size,
                    connections: Some(conns),
                    kind: download::DownloadKind::Runtime,
                },
                cancel_flag(),
                Some(progress),
            )?;
        }

        if cancel_flag().load(Ordering::SeqCst) {
            return Err(crate::i18n::t("s.a5ffdc95ee"));
        }

        // Several GB of tar takes minutes. A single static line with a bar that
        // never moves is indistinguishable from a hang, so report bytes read.
        emit_progress(&app, "extract", 0, 1, &crate::i18n::t("s.e5d3918de2"));
        let staged = paths::update_cache(&root)
            .join("runtime_install")
            .join(&var);
        let staging = paths::update_cache(&root)
            .join("runtime_extract")
            .join(&var);
        if staged.exists() {
            let _ = fs::remove_dir_all(&staged);
        }
        {
            let app_x = app.clone();
            extract::extract_runtime_tar_into(&dest_file, &staged, &staging, &|done, total| {
                emit_progress(
                    &app_x,
                    "extract",
                    done,
                    total.max(1),
                    &crate::i18n::t2("s.6aa1e213af", &format_size(done), &format_size(total)),
                );
            })
            .map_err(|e| extract_error_text(&e))?;
        }
        emit_progress(&app, "extract", 1, 1, &crate::i18n::t("s.58a0882f6f"));

        if !paths::runtime_tree_ready(&staged) {
            // 校验过的包解出来却少东西，几乎只有一个原因：杀软在解压过程中
            // 把 torch 那几个 dll 挑走了。不写出来，用户只会一遍遍重下。
            let _ = fs::remove_dir_all(&staged);
            return Err(format!(
                "{}\n\n{}",
                crate::i18n::t("s.74aef4af02"),
                crate::i18n::t("s.rtExtractHelp"),
            ));
        }
        write_runtime_meta_at(&staged, &var, &spec.label, &spec.version)?;
        // 下载要十几分钟，期间用户可能又开了 WebUI / 面板 —— 换目录前再扫一遍。
        let busy = worker::pythons_under(&paths::runtime_variant_dir(&root, &var));
        if !busy.is_empty() {
            return Err(crate::i18n::te(
                "runtimeMigration.runtimeBusy",
                &(busy.len()),
            ));
        }
        replace_managed_runtime(&root, &var, &staged)?;
        activate_runtime(&root, &var)?;

        if !paths::runtime_ready(&root) {
            return Err(format!(
                "{}\n\n{}",
                crate::i18n::t("s.74aef4af02"),
                crate::i18n::t("s.rtExtractHelp"),
            ));
        }

        // 起 worker 并把设备列表读出来。以前这一步只在应用启动时做过一次，
        // 而首装的用户那时候 Runtime 还没有，于是补全完什么也不会发生：设备
        // 下拉是空的、变声起不来，必须重启软件。补全刚结束正是该做这件事的
        // 时候。放后台线程，别把补全流程的收尾卡在 90 秒的等待上。
        ensure_worker_background(root.clone());

        emit_progress(&app, "done", 1, 1, &crate::i18n::t("s.a64a986f63"));
        Ok(json!({
            "ok": true,
            "message": crate::i18n::te("s.3c5bbe47d1", &(spec.label)),
            "variant": var,
            "version": spec.version,
            "action": if force { "replace" } else { "install" },
        }))
    })();

    cancel_flag().store(false, Ordering::SeqCst);

    if let Err(ref e) = result {
        emit_progress(&app, "error", 0, 1, e);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 「主显卡」的序号最后是给 `CUDA_VISIBLE_DEVICES` 用的，而 CUDA 只看得见
    /// N 卡。核显或 A 卡混进候选列表，用户选「1」拿到的就不是他看到的那块。
    #[test]
    fn only_nvidia_adapters_can_be_picked_as_the_main_gpu() {
        for good in [
            "NVIDIA GeForce RTX 5090",
            "NVIDIA GeForce RTX 5060 Ti",
            "GeForce GTX 1660 SUPER",
            "Quadro P2000",
            "Tesla T4",
        ] {
            assert!(looks_like_nvidia(good));
        }
        for bad in [
            "Intel(R) UHD Graphics 770",
            "AMD Radeon RX 7900 XTX",
            "Intel(R) Arc(TM) A770",
            "Microsoft Basic Display Adapter",
            "Parsec Virtual Display Adapter",
        ] {
            assert!(!looks_like_nvidia(bad));
        }
    }

    /// 序号得按 `index` 列排，不能按行序。CUDA 的下标就是这个 index，两边错开
    /// 一位就等于把用户选的卡换成另一块。
    #[test]
    fn nvidia_smi_rows_are_ordered_by_index_not_by_line() {
        let out = "1, NVIDIA GeForce RTX 3060\n0, NVIDIA GeForce GTX 1050 Ti\n";
        assert_eq!(
            parse_nvidia_smi(out),
            Some(vec![
                "NVIDIA GeForce GTX 1050 Ti".to_string(),
                "NVIDIA GeForce RTX 3060".to_string(),
            ])
        );
    }

    /// 「问不到」和「一块 N 卡都没有」必须分开：前者要退回注册表那份列表，后者
    /// 不能退 —— 退了就又把注册表里的虚拟适配器和残留驱动键当成可选项。
    #[test]
    fn unusable_nvidia_smi_output_is_none_not_empty() {
        for junk in ["", "   \n\n", "NVIDIA-SMI has failed because...", "x, y"] {
            assert_eq!(parse_nvidia_smi(junk), None, "{junk:?}");
        }
    }

    /// 显卡名里本来就有逗号的话（`NVIDIA RTX A4000, Laptop GPU` 这类），只在第一个
    /// 逗号处切，剩下的都算名字。
    #[test]
    fn only_the_first_comma_separates_index_from_name() {
        assert_eq!(
            parse_nvidia_smi("0, NVIDIA RTX A4000, Laptop GPU\n"),
            Some(vec!["NVIDIA RTX A4000, Laptop GPU".to_string()])
        );
    }
}
