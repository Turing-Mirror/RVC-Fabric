//! Runtime presence + GPU variant recommendation (stage 3 foundation).
//!
//! Download/extract of multi-GB Runtime comes next; this module reports what
//! is missing and which variant to fetch, without torch (works before Runtime).

use std::path::Path;
use std::process::Command;

use serde_json::{json, Value};

use crate::paths;

/// nvidia | nvidia50 | amd | unknown
pub fn recommend_variant(gpu_names: &[String]) -> (String, String) {
    let joined = gpu_names.join(" | ").to_ascii_lowercase();
    if joined.is_empty() {
        return (
            "unknown".into(),
            "未检测到显卡，请手动选择运行时版本".into(),
        );
    }
    // 50-series needs sm_120-capable pack
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

/// Enumerate display adapters via WMI (no torch, no Runtime required).
#[cfg(windows)]
pub fn list_gpus() -> Vec<String> {
    use std::os::windows::process::CommandExt;
    let ps = r#"
Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
  Where-Object { $_.Name } |
  ForEach-Object { $_.Name }
"#;
    let out = Command::new("powershell")
        .args([
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps,
        ])
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
pub fn list_gpus() -> Vec<String> {
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
        .map(|s| s.to_string())
}

/// Full provision snapshot for UI / first-run gate.
pub fn provision_status(root: &Path) -> Value {
    let ready = paths::runtime_ready(root);
    let pyw = paths::runtime_pythonw(root);
    let gpus = list_gpus();
    let (recommended, reason) = recommend_variant(&gpus);
    let installed = read_package_meta_variant(root);
    let worker_script = paths::worker_script(root).is_file();
    let need_provision = !ready;

    json!({
        "runtime_ready": ready,
        "need_provision": need_provision,
        "runtime_python": pyw.map(|p| p.to_string_lossy().to_string()),
        "worker_script_ok": worker_script,
        "product_root": root.to_string_lossy(),
        "gpus": gpus,
        "recommended_variant": recommended,
        "recommend_reason": reason,
        "installed_variant": installed,
        // Download not implemented yet — UI can show plan only
        "download_supported": false,
        "message": if need_provision {
            "未检测到完整 Runtime（需含 torch）。首次使用请用启动器补全，或等待壳内下载上线。"
        } else if !worker_script {
            "Runtime 就绪，但缺少 tools/realtime_worker.py"
        } else {
            "Runtime 就绪"
        },
    })
}
