//! Runtime presence, GPU recommendation, download + extract (stage 3).

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

use crate::catalog;
use crate::download::{self, ProgressFn};
use crate::extract;
use crate::paths;

static PROVISION_BUSY: Mutex<bool> = Mutex::new(false);
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
        return (
            "unknown".into(),
            crate::i18n::t("s.47c37d6efa"),
        );
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

/// 系统里枚举到的 N 卡，保持枚举顺序。
///
/// 下标就是给 `CUDA_VISIBLE_DEVICES` 用的序号。注册表枚举顺序和 CUDA 的排序
/// 不保证一一对应 —— 所以界面上写明了「选完不对就换一个」，而不是假装这里
/// 算出来的一定准。
pub fn list_nvidia_gpus() -> Vec<String> {
    list_gpus()
        .into_iter()
        .filter(|g| looks_like_nvidia(g))
        .collect()
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
        OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
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
            if RegOpenKeyExW(class_key, wide(&sub).as_ptr(), 0, KEY_READ, &mut dev)
                != ERROR_SUCCESS
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
        .map(|s| s.trim().to_string())
        // The universal Setup writes an empty variant on purpose: the app picks
        // it after detecting the GPU. Empty must read as "not chosen", not as a
        // variant named "".
        .filter(|s| !s.is_empty())
}

fn write_package_meta(root: &Path, variant: &str, label: &str, version: &str) -> Result<(), String> {
    let (accel, use_dml, summary) = match variant {
        "amd" => ("dml", true, crate::i18n::t("s.ab31cc9ebb")),
        "nvidia50" => ("cuda", false, crate::i18n::t("s.083e3aad12")),
        _ => ("cuda", false, "NVIDIA CUDA Runtime".to_string()),
    };
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let data = json!({
        "variant": variant,
        "label": label,
        "accel_default": accel,
        "use_dml": use_dml,
        "summary": summary,
        "runtime_version": version,
        "runtime_source": "cnb_release",
        "provisioned_at_unix": now,
        "tagged": true,
    });
    let path = paths::package_meta_path(root);
    fs::write(
        &path,
        serde_json::to_string_pretty(&data).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    Ok(())
}

fn cache_dir(root: &Path) -> PathBuf {
    let d = paths::user_data(root)
        .join("update_cache")
        .join("runtime");
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
    let ready = paths::runtime_ready(root);
    let pyw = paths::runtime_pythonw(root);
    let gpus = list_gpus();
    let (recommended, reason) = recommend_variant(&gpus);
    let installed = read_package_meta_variant(root);
    let worker_script = paths::worker_script(root).is_file();
    let need_provision = !ready;
    let busy = *PROVISION_BUSY.lock().unwrap_or_else(|e| e.into_inner());

    // Per-variant sizes so the UI can follow the user's selection, not only
    // the recommended package. One catalog fetch is cached for ~5 minutes.
    let variant_defs = [
        ("nvidia", crate::i18n::t("s.4c65a5e25e")),
        ("nvidia50", crate::i18n::t("s.e7a64d4aaf")),
        ("amd", "AMD / Intel（DirectML）".to_string()),
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
        let (sz, lab) = match catalog::resolve_runtime_spec(id, true) {
            Ok(spec) => {
                let s = spec.size_bytes.max(spec.part.size_bytes);
                let l = if spec.label.is_empty() {
                    fallback_label.clone()
                } else {
                    spec.label
                };
                (s, l)
            }
            Err(_) => (0u64, fallback_label.clone()),
        };
        if *id == rec_key {
            size_hint = sz;
            label = lab.clone();
        }
        variants.push(json!({
            "id": id,
            "label": fallback_label,
            "size_bytes": sz,
            "size_label": format_size(sz),
        }));
    }

    json!({
        "runtime_ready": ready,
        "need_provision": need_provision,
        "runtime_python": pyw.map(|p| p.to_string_lossy().to_string()),
        "worker_script_ok": worker_script,
        "product_root": root.to_string_lossy(),
        "gpus": gpus,
        // 「主显卡」下拉的候选项。下标即 CUDA 序号。
        "nvidia_gpus": list_nvidia_gpus(),
        "recommended_variant": recommended,
        "recommend_reason": reason,
        "recommended_label": label,
        "recommended_size_bytes": size_hint,
        "recommended_size_label": format_size(size_hint),
        "installed_variant": installed,
        "download_supported": true,
        "busy": busy,
        "variants": variants,
        "message": if need_provision {
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

/// Download + extract Runtime for *variant*. Emits `provision-progress` events.
pub fn run_provision(
    app: AppHandle,
    root: PathBuf,
    variant: String,
    force: bool,
) -> Result<Value, String> {
    {
        // Poison recovery: a panic here would otherwise leave the flag stuck
        // and every later provision would report 「已有补全任务在进行」.
        let mut g = PROVISION_BUSY.lock().unwrap_or_else(|e| e.into_inner());
        if *g {
            return Err(crate::i18n::t("s.eca157a71e").into());
        }
        *g = true;
    }
    cancel_flag().store(false, Ordering::SeqCst);

    let result: Result<Value, String> = (|| {
        let mut var = variant.trim().to_ascii_lowercase();
        if var != "nvidia" && var != "amd" && var != "nvidia50" {
            var = "nvidia".to_string();
        }

        if paths::runtime_ready(&root) && !force {
            write_package_meta(&root, &var, &var, "").ok();
            emit_progress(&app, "done", 1, 1, &crate::i18n::t("s.e1b39abf92"));
            return Ok(json!({
                "ok": true,
                "message": crate::i18n::t("s.227d108a35"),
                "variant": var,
            }));
        }

        if force {
            let rt = root.join("Runtime");
            if rt.exists() {
                emit_progress(&app, "prepare", 0, 1, &crate::i18n::t("s.7a048346cb"));
                let _ = fs::remove_dir_all(&rt);
            }
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
        if part.sha256.chars().filter(|c| c.is_ascii_hexdigit()).count() != 64 {
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
                    if spec.version.is_empty() { "?" } else { &spec.version },
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
                    other if other.starts_with("connecting:") => {
                        crate::i18n::te("s.d28fcd74d0", &(format_size(total)))
                    }
                    other if other.starts_with("download:") => crate::i18n::tn(
                        "s.3de4870b5b",
                        &[&format_size(done), &format_size(total), &format_speed(speed)],
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
        {
            let app_x = app.clone();
            extract::extract_runtime_tar_with_progress(&dest_file, &root, &|done, total| {
                emit_progress(
                    &app_x,
                    "extract",
                    done,
                    total.max(1),
                    &crate::i18n::t2("s.6aa1e213af", &format_size(done), &format_size(total)),
                );
            })?;
        }
        emit_progress(&app, "extract", 1, 1, &crate::i18n::t("s.58a0882f6f"));

        write_package_meta(&root, &var, &spec.label, &spec.version)?;

        if !paths::runtime_ready(&root) {
            return Err(crate::i18n::t("s.74aef4af02"));
        }

        // 起 worker 并把设备列表读出来。以前这一步只在应用启动时做过一次，
        // 而首装的用户那时候 Runtime 还没有，于是补全完什么也不会发生：设备
        // 下拉是空的、变声起不来，必须重启软件。补全刚结束正是该做这件事的
        // 时候。放后台线程，别把补全流程的收尾卡在 90 秒的等待上。
        {
            let root_bg = root.clone();
            std::thread::spawn(move || {
                let r = crate::worker::ensure_worker_and_devices(&root_bg, 90_000);
                let n = r
                    .get("input_devices")
                    .and_then(|v| v.as_array())
                    .map(|a| a.len())
                    .unwrap_or(0);
                crate::logging::shell_log!(crate::i18n::t("s.5c5f9ed8e4"));
            });
        }

        emit_progress(&app, "done", 1, 1, &crate::i18n::t("s.a64a986f63"));
        Ok(json!({
            "ok": true,
            "message": crate::i18n::te("s.3c5bbe47d1", &(spec.label)),
            "variant": var,
            "version": spec.version,
        }))
    })();

    {
        let mut g = PROVISION_BUSY.lock().unwrap_or_else(|e| e.into_inner());
        *g = false;
    }
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
}
