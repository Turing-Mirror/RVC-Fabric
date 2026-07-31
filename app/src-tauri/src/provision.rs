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
            "未检测到显卡，请手动选择运行时版本".into(),
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
            format!("检测到 NVIDIA 50 系：{}，推荐 nvidia50 运行时", gpu_names[0]),
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
            format!("检测到 NVIDIA：{}，推荐 nvidia（CUDA）运行时", gpu_names[0]),
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
            format!(
                "检测到 AMD/Intel：{}，推荐 amd（DirectML）运行时",
                gpu_names[0]
            ),
        );
    }
    (
        "unknown".into(),
        format!("未能识别显卡类型：{}，请手动选择", gpu_names.join(", ")),
    )
}

/// Enumerated once per run. The video controller set does not change while the
/// app is open, and each enumeration is a PowerShell launch (300–800 ms) that
/// otherwise happened every time the provision gate opened or a diagnostics
/// bundle was built.
static GPUS: std::sync::OnceLock<Vec<String>> = std::sync::OnceLock::new();

pub fn list_gpus() -> Vec<String> {
    GPUS.get_or_init(enumerate_gpus).clone()
}

#[cfg(windows)]
fn enumerate_gpus() -> Vec<String> {
    // Kept inside the cfg(windows) body: at module scope it is an unused-import
    // warning on every other platform.
    use std::os::windows::process::CommandExt;
    use std::process::Command;
    let ps = r#"
Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
  Where-Object { $_.Name } |
  ForEach-Object { $_.Name }
"#;
    let out = Command::new("powershell")
        .args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps])
        .creation_flags(0x08000000)
        .output();
    match out {
        Ok(o) => String::from_utf8_lossy(&o.stdout)
            .lines()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect(),
        Err(_) => vec![],
    }
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
        "amd" => (
            "dml",
            true,
            "官方 A/I 卡路径：DirectML Runtime",
        ),
        "nvidia50" => (
            "cuda",
            false,
            "NVIDIA 50 系 CUDA Runtime",
        ),
        _ => ("cuda", false, "NVIDIA CUDA Runtime"),
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

    // Resolve recommended size for UI (best-effort, may use fallback)
    let mut size_hint = 0u64;
    let mut label = recommended.clone();
    if let Ok(spec) = catalog::resolve_runtime_spec(
        if recommended == "unknown" {
            "nvidia"
        } else {
            &recommended
        },
        true,
    ) {
        size_hint = spec.size_bytes.max(spec.part.size_bytes);
        label = spec.label;
    }

    json!({
        "runtime_ready": ready,
        "need_provision": need_provision,
        "runtime_python": pyw.map(|p| p.to_string_lossy().to_string()),
        "worker_script_ok": worker_script,
        "product_root": root.to_string_lossy(),
        "gpus": gpus,
        "recommended_variant": recommended,
        "recommend_reason": reason,
        "recommended_label": label,
        "recommended_size_bytes": size_hint,
        "recommended_size_label": format_size(size_hint),
        "installed_variant": installed,
        "download_supported": true,
        "busy": busy,
        "variants": [
            {"id": "nvidia", "label": "NVIDIA（推荐大多数 N 卡）"},
            {"id": "nvidia50", "label": "NVIDIA 50 系（RTX 50xx）"},
            {"id": "amd", "label": "AMD / Intel（DirectML）"},
        ],
        "message": if need_provision {
            "未检测到完整 Runtime（需含 torch）。可在本页下载补全。"
        } else if !worker_script {
            "Runtime 就绪，但缺少 tools/realtime_worker.py"
        } else {
            "Runtime 就绪"
        },
    })
}

fn emit_progress(app: &AppHandle, phase: &str, done: u64, total: u64, message: &str) {
    let pct = if total > 0 {
        ((done as f64 / total as f64) * 100.0).clamp(0.0, 100.0)
    } else {
        0.0
    };
    let _ = app.emit(
        "provision-progress",
        json!({
            "phase": phase,
            "done": done,
            "total": total,
            "percent": pct,
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
            return Err("已有补全任务在进行".into());
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
            emit_progress(&app, "done", 1, 1, "Runtime 已就绪，跳过下载");
            return Ok(json!({
                "ok": true,
                "message": "Runtime 已就绪，跳过下载。",
                "variant": var,
            }));
        }

        if force {
            let rt = root.join("Runtime");
            if rt.exists() {
                emit_progress(&app, "prepare", 0, 1, "移除旧 Runtime…");
                let _ = fs::remove_dir_all(&rt);
            }
        }

        emit_progress(&app, "catalog", 0, 1, "解析 CNB 运行时清单…");
        let spec = catalog::resolve_runtime_spec(&var, true)?;
        let part = &spec.part;
        if part.urls.is_empty() {
            return Err("清单中没有可用的 Runtime 下载地址。".to_string());
        }
        // The Runtime tar unpacks into python.exe and its libraries — running
        // it unverified is arbitrary code execution. download_request skips
        // verification on an empty hash, and the cache-reuse branch below would
        // also accept whatever is already on disk, so refuse up front.
        if part.sha256.chars().filter(|c| c.is_ascii_hexdigit()).count() != 64 {
            return Err("运行时清单缺少有效的 sha256，已拒绝下载。".to_string());
        }

        let size = spec.size_bytes.max(part.size_bytes);
        let conns_preview = download::auto_connections(size);
        emit_progress(
            &app,
            "download",
            0,
            size.max(1),
            &format!(
                "下载 {} Runtime v{}（约 {} · {} 连接）",
                spec.label,
                if spec.version.is_empty() {
                    "?"
                } else {
                    &spec.version
                },
                format_size(size),
                conns_preview
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
                    &format!(
                        "使用本地缓存：{}",
                        dest_file
                            .file_name()
                            .map(|s| s.to_string_lossy())
                            .unwrap_or_default()
                    ),
                );
            } else {
                let _ = fs::remove_file(&dest_file);
            }
        }

        if !dest_file.is_file() {
            let app_cb = app.clone();
            let conns = download::auto_connections(size);
            let progress: ProgressFn = Arc::new(move |done, total, phase| {
                let m = match phase {
                    "verify" => "校验 sha256…",
                    "retry" => "网络重试…",
                    other if other.starts_with("download:") => other,
                    _ => "多连接下载中…",
                };
                emit_progress(&app_cb, phase, done, total.max(1), m);
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
            return Err("已取消".to_string());
        }

        emit_progress(&app, "extract", 0, 1, "解压 Runtime…");
        extract::extract_runtime_tar(&dest_file, &root)?;
        emit_progress(&app, "extract", 1, 1, "解压完成");

        write_package_meta(&root, &var, &spec.label, &spec.version)?;

        if !paths::runtime_ready(&root) {
            return Err("解压完成但未检测到 torch，Runtime 可能不完整。".to_string());
        }

        emit_progress(&app, "done", 1, 1, "Runtime 补全完成");
        Ok(json!({
            "ok": true,
            "message": format!("{} Runtime 已安装", spec.label),
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
