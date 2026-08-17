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

pub(crate) const CNB_REPO: &str = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases";

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

/// engine-core / VB-Cable 的下载地址。
///
/// 以前只有官方仓库一条 —— CNB 一挂，谁都装不上，而这是首次运行的必经之路。
/// 现在基址列表从清单来（`mirrors::lfs_bases`），官方仓库永远排第一，要加备份
/// 源改一行 JSON 就行，不用发新版本。
fn lfs_urls(root: &Path, sha: &str) -> Vec<String> {
    crate::mirrors::lfs_bases(root)
        .into_iter()
        .map(|base| format!("{base}/-/lfs/{sha}"))
        .collect()
}

/// 给别的资源包复用同一条路：下载 → 校验 → 解压。
///
/// VC++ 运行库走的是跟 VB-Cable 一模一样的流程，没必要各写一份 —— 两份就会
/// 有一份先长出自己的重试逻辑和缓存规则，然后行为对不上。
pub fn fetch_pack(
    cache_name: &str,
    sha: &str,
    dest_root: &Path,
    root: &Path,
    cancel: Arc<AtomicBool>,
    progress: Option<download::ProgressFn>,
) -> Result<(), String> {
    fetch_and_extract(cache_name, sha, dest_root, root, cancel, progress)
}

fn fetch_and_extract(
    cache_name: &str,
    sha: &str,
    dest_root: &Path,
    root: &Path,
    cancel: Arc<AtomicBool>,
    progress: Option<download::ProgressFn>,
) -> Result<(), String> {
    let cache = paths::update_cache(root);
    std::fs::create_dir_all(&cache).map_err(|e| e.to_string())?;
    let archive = cache.join(cache_name);

    // Reuse a previously completed download, but only after verifying it.
    let cached_ok = archive.is_file() && download::verify_sha256(&archive, sha).is_ok();
    if !cached_ok {
        // Passing progress through is what keeps the first-run gate honest:
        // without it the bar sits still while the NIC is busy for minutes.
        download::download_request(
            download::DownloadRequest {
                urls: lfs_urls(root, sha),
                root: Some(root.to_path_buf()),
                dest: archive.clone(),
                expected_sha256: sha.to_string(),
                size_hint: 0,
                connections: None,
                kind: download::DownloadKind::Generic,
            },
            cancel,
            progress,
        )
        .map_err(|e| crate::i18n::te("s.04c4e3b2b3", &(e)))?;
    }

    extract::extract_zip(&archive, dest_root).map_err(|e| crate::i18n::te("s.0707e8af4e", &(e)))?;
    let _ = std::fs::remove_file(&archive);
    Ok(())
}

/// Hoist `<dir>/<name>/*` up into `<dir>` when the zip carried a single
/// top-level folder of that name.
///
/// The VB-Cable pack ships this way about half the time; without the hoist the
/// installer lands at `VBCABLE/VBCABLE/VBCABLE_Setup_x64.exe`, nothing finds
/// it, and the user simply cannot install the virtual cable. The Python shell
/// had this same guard.
fn hoist_nested(dir: &Path, name: &str) {
    let nested = dir.join(name);
    if !nested.is_dir() {
        return;
    }
    let Ok(entries) = std::fs::read_dir(&nested) else {
        return;
    };
    for e in entries.filter_map(|e| e.ok()) {
        let from = e.path();
        let to = dir.join(e.file_name());
        if to.exists() {
            let _ = if to.is_dir() {
                std::fs::remove_dir_all(&to)
            } else {
                std::fs::remove_file(&to)
            };
        }
        let _ = std::fs::rename(&from, &to);
    }
    let _ = std::fs::remove_dir(&nested);
}

/// Download + extract engine-core into the install root.
///
/// `progress` mirrors the shared downloader's (done, total, phase) so the
/// caller can forward it to the UI. Before it existed, the first-run gate
/// showed a frozen bar during this step — several hundred MB of hubert / rmvpe
/// / ffmpeg with no event at all, which reads exactly like a hang.
pub fn ensure_engine_core(
    root: &Path,
    cancel: Arc<AtomicBool>,
    progress: Option<download::ProgressFn>,
) -> Result<(), String> {
    if engine_core_ready(root) {
        return Ok(());
    }
    fetch_and_extract(ENGINE_CORE_NAME, ENGINE_CORE_SHA, root, root, cancel, progress)?;
    if !engine_core_ready(root) {
        // Same guard: a single top-level folder in the zip would put
        // assets/ and ffmpeg.exe one level too deep.
        for name in ["engine-core", "engine_core"] {
            hoist_nested(root, name);
        }
    }
    let missing = engine_core_missing(root);
    if missing.is_empty() {
        Ok(())
    } else {
        Err(crate::i18n::te("s.f36aff2870", &(missing.join("、"))))
    }
}

/// Download + extract the VB-Cable pack into `VBCABLE/`. Does **not** run the
/// installer — that needs UAC and is a separate, user-initiated step.
pub fn ensure_vbcable_pack(
    root: &Path,
    cancel: Arc<AtomicBool>,
    progress: Option<download::ProgressFn>,
) -> Result<(), String> {
    if vbcable_pack_ready(root) {
        return Ok(());
    }
    let dir = vbcable_dir(root);
    fetch_and_extract(VBCABLE_NAME, VBCABLE_SHA, &dir, root, cancel, progress)?;
    if !vbcable_pack_ready(root) {
        // Some builds of the pack have a single top-level VBCABLE/ folder.
        hoist_nested(&dir, "VBCABLE");
    }
    if vbcable_pack_ready(root) {
        Ok(())
    } else {
        Err(crate::i18n::t("s.vbcablePackBroken").into())
    }
}

/// Official install location after a successful setup. Windows "Apps &
/// features" points here. Uninstall must run this copy when it exists;
/// the downloaded pack is only a fallback (user may have installed Cable
/// themselves, or the pack has not been fetched yet).
fn system_vbcable_dirs() -> Vec<PathBuf> {
    let mut out = Vec::new();
    for key in ["ProgramFiles", "ProgramFiles(x86)"] {
        if let Ok(pf) = std::env::var(key) {
            let dir = PathBuf::from(pf).join("VB").join("CABLE");
            if !out.iter().any(|p| p == &dir) {
                out.push(dir);
            }
        }
    }
    out
}

pub fn vbcable_system_dir() -> Option<PathBuf> {
    system_vbcable_dirs()
        .into_iter()
        .find(|d| find_vbcable_setup(d).is_some())
}

/// Driver is on the machine (setup lives under Program Files), not just
/// that we have a downloaded pack. Device names only appear after reboot,
/// so the Help page cannot rely on the worker list alone.
pub fn vbcable_installed() -> bool {
    vbcable_system_dir().is_some()
}

fn pick_setup_dir(root: &Path, prefer_system: bool) -> Result<(PathBuf, PathBuf), String> {
    if prefer_system {
        if let Some(dir) = vbcable_system_dir() {
            if let Some(setup) = find_vbcable_setup(&dir) {
                return Ok((dir, setup));
            }
        }
    }
    let dir = vbcable_dir(root);
    let setup = find_vbcable_setup(&dir).ok_or(crate::i18n::t("s.vbcableNoSetup"))?;
    Ok((dir, setup))
}

/// `-i -h` / `-u -h` 是 VB-Audio 官方静默参数（i=install，u=uninstall，h=不显示界面）。
/// 提权躲不掉 —— 动的是驱动，系统那道 UAC 必须由用户点确认。
///
/// cwd 必须是安装程序所在目录：它要从工作目录里找 INF/SYS，找不到就装不上。
///
/// `-Wait -PassThru` 之后把安装程序的退出码原样带回来。以前是 spawn 完就
/// 返回，界面只能说「已启动安装程序」，装成没装成谁都不知道。
#[cfg(target_os = "windows")]
fn run_vbcable_setup(setup: &Path, dir: &Path, uninstall: bool) -> Result<(), String> {
    use std::os::windows::process::CommandExt;

    let args = if uninstall {
        "'-u','-h'"
    } else {
        "'-i','-h'"
    };
    let fail_key = if uninstall {
        "s.vbcableUninstallFailedCode"
    } else {
        "s.vbcableFailedCode"
    };
    let cancel_key = if uninstall {
        "s.vbcableUninstallCancelled"
    } else {
        "s.vbcableCancelled"
    };
    // UAC 被用户点「否」时 Start-Process 抛异常，单靠退出码分不出「拒绝提权」
    // 和「装失败」。这里把它归一成 1223（ERROR_CANCELLED）。
    let ps = format!(
        "try {{ $p = Start-Process -FilePath '{}' -ArgumentList {args} \
         -WorkingDirectory '{}' -Verb RunAs -Wait -PassThru }} catch {{ exit 1223 }}; \
         exit $p.ExitCode",
        setup.to_string_lossy().replace('\'', "''"),
        dir.to_string_lossy().replace('\'', "''"),
    );
    let status = std::process::Command::new("powershell")
        .args([
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-Command",
            &ps,
        ])
        .creation_flags(0x08000000) // CREATE_NO_WINDOW：别闪一下黑框
        .status()
        .map_err(|e| crate::i18n::te("s.23220ab448", &(e)))?;
    match status.code() {
        // 3010 = 做完了，等重启生效。对用户来说是成功。
        Some(0) | Some(3010) => Ok(()),
        Some(1223) => Err(crate::i18n::t(cancel_key)),
        Some(c) => Err(crate::i18n::te(fail_key, &c)),
        None => Err(crate::i18n::te(fail_key, &"?")),
    }
}

#[cfg(target_os = "windows")]
pub fn install_vbcable(root: &Path) -> Result<(), String> {
    let (dir, setup) = pick_setup_dir(root, false)?;
    run_vbcable_setup(&setup, &dir, false)
}

#[cfg(target_os = "windows")]
pub fn uninstall_vbcable(root: &Path) -> Result<(), String> {
    let (dir, setup) = pick_setup_dir(root, true)?;
    run_vbcable_setup(&setup, &dir, true)
}

#[cfg(not(target_os = "windows"))]
pub fn install_vbcable(_root: &Path) -> Result<(), String> {
    Err(crate::i18n::t("s.vbcableWindowsOnly").into())
}

#[cfg(not(target_os = "windows"))]
pub fn uninstall_vbcable(_root: &Path) -> Result<(), String> {
    Err(crate::i18n::t("s.vbcableWindowsOnly").into())
}

/// Status for the first-run gate and the Help page.
pub fn assets_status(root: &Path) -> Value {
    let missing = engine_core_missing(root);
    json!({
        "engine_core_ready": missing.is_empty(),
        "engine_core_missing": missing,
        "vbcable_pack_ready": vbcable_pack_ready(root),
        "vbcable_installed": vbcable_installed(),
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
    fn hoists_a_single_nested_folder() {
        // The VB-Cable pack sometimes ships with a top-level VBCABLE/ folder.
        // Without the hoist the installer ends up one level too deep and the
        // user simply cannot install the virtual cable.
        let base = std::env::temp_dir().join("rvcf-hoist-test");
        let _ = std::fs::remove_dir_all(&base);
        let nested = base.join("VBCABLE");
        std::fs::create_dir_all(&nested).unwrap();
        std::fs::write(nested.join("VBCABLE_Setup_x64.exe"), b"x".repeat(60_000)).unwrap();
        std::fs::write(nested.join("vbcable.inf"), b"inf").unwrap();

        assert!(find_vbcable_setup(&base).is_none(), "before hoist: nothing at top");
        hoist_nested(&base, "VBCABLE");
        assert!(find_vbcable_setup(&base).is_some(), "after hoist: setup found");
        assert!(has_driver_files(&base), "after hoist: inf found");
        assert!(!nested.exists(), "nested dir removed");
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn lfs_url_is_sha_addressed() {
        let root = std::env::temp_dir().join("rvcf-lfs-url");
        let _ = std::fs::remove_dir_all(&root);
        let u = lfs_urls(&root, ENGINE_CORE_SHA);
        // 没有清单时就只有官方仓库那一条
        assert_eq!(u.len(), 1);
        assert!(u[0].starts_with(CNB_REPO));
        assert!(u[0].ends_with(ENGINE_CORE_SHA));
        assert!(u[0].contains("/-/lfs/"));
    }

    #[test]
    fn system_vbcable_dirs_are_under_program_files() {
        let dirs = system_vbcable_dirs();
        for d in &dirs {
            assert!(
                d.ends_with(Path::new("VB").join("CABLE")),
                "unexpected system cable dir: {}",
                d.display()
            );
        }
    }

    #[test]
    fn lfs_urls_pick_up_catalog_mirrors() {
        // engine-core 是首次运行的必经之路，以前只有一个源，CNB 一挂谁都装不上。
        let root = std::env::temp_dir().join("rvcf-lfs-mirror");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("configs")).unwrap();
        std::fs::write(
            root.join("configs").join("online_catalog.json"),
            r#"{"download_mirrors":{"lfs":["https://backup.example.cn/Turing-Mirror/Rel"]}}"#,
        )
        .unwrap();
        let u = lfs_urls(&root, ENGINE_CORE_SHA);
        assert_eq!(u.len(), 2, "{u:?}");
        assert!(u[0].starts_with(CNB_REPO), "官方仓库必须还是第一个");
        assert!(u[1].starts_with("https://backup.example.cn/"));
        let _ = std::fs::remove_dir_all(&root);
    }
}
