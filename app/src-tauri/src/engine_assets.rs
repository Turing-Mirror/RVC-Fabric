//! engine-core and VB-Cable provisioning.
//!
//! Ports `launcher/engine_core.py` and `launcher/vbcable.py`. Both are required
//! for a usable install and neither ships inside Setup:
//!
//! * **engine-core** — hubert + rmvpe + ffmpeg/ffprobe, shared by every GPU
//!   variant. Without it the worker cannot start at all.
//! * **VB-Cable** — the virtual cable. Without it nothing the user says reaches
//!   the game, which is the whole point of the product.
//!
//! Specs mirror `launcher/cnb_sources.py` fallbacks; CNB LFS objects are
//! sha256-addressed so the URL doubles as the integrity check.

use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;
use std::sync::Arc;

use serde_json::{json, Value};

use crate::{download, extract, paths};

const CNB_REPO: &str = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases";

// ---------------------------------------------------------------------------
// engine-core
// ---------------------------------------------------------------------------

const ENGINE_CORE_SHA: &str =
    "ecb3231c7d26ad553e902ac24d40daf3d3fbe5786a7d8e78af8038fc389cab47";
const ENGINE_CORE_NAME: &str = "engine-core-260722.zip";

/// (relative path, minimum plausible size) — a truncated download must not
/// count as ready, which is why sizes are checked and not just existence.
fn engine_core_files() -> Vec<(&'static str, u64)> {
    vec![
        ("assets/hubert/hubert_base.pt", 1_000_000),
        ("assets/rmvpe/rmvpe.pt", 1_000_000),
        ("assets/rmvpe/rmvpe.onnx", 100_000),
        ("ffmpeg.exe", 1_000_000),
        ("ffprobe.exe", 1_000_000),
    ]
}

pub fn engine_core_missing(root: &Path) -> Vec<String> {
    engine_core_files()
        .into_iter()
        .filter(|(rel, min)| {
            let p = root.join(rel);
            match std::fs::metadata(&p) {
                Ok(m) => !m.is_file() || m.len() < *min,
                Err(_) => true,
            }
        })
        .map(|(rel, _)| rel.to_string())
        .collect()
}

pub fn engine_core_ready(root: &Path) -> bool {
    engine_core_missing(root).is_empty()
}

// ---------------------------------------------------------------------------
// VB-Cable
// ---------------------------------------------------------------------------

const VBCABLE_SHA: &str =
    "0518435a76264856e4e2733ac22143ff16595c763cbf58106ed04d6895c6ddf5";
const VBCABLE_NAME: &str = "vbcable-setup.zip";

pub fn vbcable_dir(root: &Path) -> PathBuf {
    root.join("VBCABLE")
}

/// The unpacked pack must have both an installer and the driver files next to
/// it — the installer refuses to work from a directory without the INF/SYS.
pub fn vbcable_pack_ready(root: &Path) -> bool {
    let dir = vbcable_dir(root);
    find_vbcable_setup(&dir).is_some() && has_driver_files(&dir)
}

fn find_vbcable_setup(dir: &Path) -> Option<PathBuf> {
    for name in [
        "VBCABLE_Setup_x64.exe",
        "VBCABLE_Setup.exe",
        "VBCable_Setup_x64.exe",
    ] {
        let p = dir.join(name);
        if p.is_file() {
            return Some(p);
        }
    }
    let mut found: Vec<PathBuf> = std::fs::read_dir(dir)
        .ok()?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| {
            p.extension().and_then(|e| e.to_str()).map(|e| e.eq_ignore_ascii_case("exe"))
                == Some(true)
                && p.file_name()
                    .and_then(|n| n.to_str())
                    .map(|n| n.to_ascii_lowercase().contains("setup"))
                    == Some(true)
                && p.metadata().map(|m| m.len() > 50_000).unwrap_or(false)
        })
        .collect();
    found.sort();
    found.into_iter().next()
}

fn has_driver_files(dir: &Path) -> bool {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return false;
    };
    rd.filter_map(|e| e.ok())
        .any(|e| {
            e.path()
                .extension()
                .and_then(|x| x.to_str())
                .map(|x| x.eq_ignore_ascii_case("inf") || x.eq_ignore_ascii_case("sys"))
                == Some(true)
        })
}

// ---------------------------------------------------------------------------
// Shared download + extract
// ---------------------------------------------------------------------------

fn lfs_urls(sha: &str) -> Vec<String> {
    vec![format!("{CNB_REPO}/-/lfs/{sha}")]
}

fn fetch_and_extract(
    cache_name: &str,
    sha: &str,
    dest_root: &Path,
    root: &Path,
    cancel: Arc<AtomicBool>,
) -> Result<(), String> {
    let cache = paths::update_cache(root);
    std::fs::create_dir_all(&cache).map_err(|e| e.to_string())?;
    let archive = cache.join(cache_name);

    // Reuse a previously completed download, but only after verifying it.
    let cached_ok = archive.is_file() && download::verify_sha256(&archive, sha).is_ok();
    if !cached_ok {
        download::download_file(&lfs_urls(sha), &archive, sha, cancel, None)
            .map_err(|e| format!("下载失败：{e}"))?;
    }

    extract::extract_zip(&archive, dest_root).map_err(|e| format!("解压失败：{e}"))?;
    let _ = std::fs::remove_file(&archive);
    Ok(())
}

/// Download + extract engine-core into the install root.
pub fn ensure_engine_core(root: &Path, cancel: Arc<AtomicBool>) -> Result<(), String> {
    if engine_core_ready(root) {
        return Ok(());
    }
    fetch_and_extract(ENGINE_CORE_NAME, ENGINE_CORE_SHA, root, root, cancel)?;
    let missing = engine_core_missing(root);
    if missing.is_empty() {
        Ok(())
    } else {
        Err(format!("引擎资源仍缺少：{}", missing.join("、")))
    }
}

/// Download + extract the VB-Cable pack into `VBCABLE/`. Does **not** run the
/// installer — that needs UAC and is a separate, user-initiated step.
pub fn ensure_vbcable_pack(root: &Path, cancel: Arc<AtomicBool>) -> Result<(), String> {
    if vbcable_pack_ready(root) {
        return Ok(());
    }
    fetch_and_extract(VBCABLE_NAME, VBCABLE_SHA, &vbcable_dir(root), root, cancel)?;
    if vbcable_pack_ready(root) {
        Ok(())
    } else {
        Err("VB-Cable 安装包解压后不完整".into())
    }
}

/// Launch the VB-Cable installer elevated, with cwd = VBCABLE (the INF/SYS must
/// be resolvable from the working directory or the driver install fails).
#[cfg(target_os = "windows")]
pub fn install_vbcable(root: &Path) -> Result<(), String> {
    let dir = vbcable_dir(root);
    let setup = find_vbcable_setup(&dir).ok_or("没有找到 VB-Cable 安装程序")?;
    let ps = format!(
        "Start-Process -FilePath '{}' -WorkingDirectory '{}' -Verb RunAs",
        setup.to_string_lossy().replace('\'', "''"),
        dir.to_string_lossy().replace('\'', "''"),
    );
    std::process::Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &ps])
        .spawn()
        .map_err(|e| format!("启动安装程序失败：{e}"))?;
    Ok(())
}

#[cfg(not(target_os = "windows"))]
pub fn install_vbcable(_root: &Path) -> Result<(), String> {
    Err("VB-Cable 只在 Windows 上安装".into())
}

/// Status for the first-run gate and the 「其他」page.
pub fn assets_status(root: &Path) -> Value {
    let missing = engine_core_missing(root);
    json!({
        "engine_core_ready": missing.is_empty(),
        "engine_core_missing": missing,
        "vbcable_pack_ready": vbcable_pack_ready(root),
        "vbcable_dir": vbcable_dir(root).to_string_lossy(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_when_root_is_empty() {
        let tmp = std::env::temp_dir().join("rvcf-engine-core-test");
        let _ = std::fs::create_dir_all(&tmp);
        assert_eq!(engine_core_missing(&tmp).len(), 5);
        assert!(!engine_core_ready(&tmp));
    }

    #[test]
    fn truncated_file_does_not_count_as_ready() {
        let tmp = std::env::temp_dir().join("rvcf-engine-core-trunc");
        let f = tmp.join("assets/hubert");
        let _ = std::fs::create_dir_all(&f);
        let _ = std::fs::write(f.join("hubert_base.pt"), b"too small");
        assert!(engine_core_missing(&tmp)
            .iter()
            .any(|m| m.contains("hubert_base.pt")));
    }

    #[test]
    fn lfs_url_is_sha_addressed() {
        let u = lfs_urls(ENGINE_CORE_SHA);
        assert_eq!(u.len(), 1);
        assert!(u[0].ends_with(ENGINE_CORE_SHA));
        assert!(u[0].contains("/-/lfs/"));
    }
}
