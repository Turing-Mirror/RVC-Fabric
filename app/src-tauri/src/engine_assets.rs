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
use std::sync::{Arc, Mutex};

use serde_json::{json, Value};

use crate::{download, extract, paths};

pub(crate) const CNB_REPO: &str = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases";

/// 同一时刻只允许一个引擎资源包在下载。
///
/// 触发入口有好几个：首跑补全、点「开启变声」、工具窗、更多页。以前每个
/// 入口各起一条下载线程，全往同一个 `.part` 里写：一个在续传追加，另一个
/// 走 ripget 把文件预分配成完整长度盖上去，最后 sha256 对不上，整包作废
/// 从零再来 —— 用户看到的就是「下完一遍又重新下一遍」（diag 26.8.22/1：
/// 两条重试循环交错了一上午，754MB 一次都没落地）。串行化之后后来的等先来
/// 的做完，轮到它时一看就绪了，直接返回。
static PACK_LOCK: Mutex<()> = Mutex::new(());

fn pack_lock() -> std::sync::MutexGuard<'static, ()> {
    PACK_LOCK.lock().unwrap_or_else(|e| e.into_inner())
}

/// 内置清单里登记的包大小（字节）。拿不到就 0 —— 下载器按无提示处理，
/// 行为和从前一样。
///
/// 这个数喂给 `auto_connections` 和进度条分母：以前恒传 0，754MB 的
/// engine-core 只开一条连接慢慢爬（Runtime 有 6GB 大小可查所以有 16 条），
/// 慢网络下雪上加霜。
fn catalog_size_for(root: &Path, cache_name: &str) -> u64 {
    let data: Value = std::fs::read_to_string(root.join("configs").join("online_catalog.json"))
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_else(|| json!({}));
    for section in ["engine_core", "vbcable", "extras"] {
        let Some(v) = data.get(section) else { continue };
        // 段本身就是条目（engine_core / vbcable 在清单里是单对象）。
        if v.get("name").and_then(|x| x.as_str()) == Some(cache_name) {
            return v.get("size_bytes").and_then(|x| x.as_u64()).unwrap_or(0);
        }
        // 或者是「名字 → 条目」的映射（extras 预留这种形状）。
        if let Value::Object(m) = v {
            for e in m.values() {
                if e.get("name").and_then(|x| x.as_str()) == Some(cache_name) {
                    return e.get("size_bytes").and_then(|x| x.as_u64()).unwrap_or(0);
                }
            }
        }
    }
    0
}

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
///
/// **这条路只对老制品有效。** 实测 engine-core 和 vbcable 按 sha 能取到
/// （206），而 setup 和新传的 vcredist 都是 404 —— 前两个是仓库当年还在用
/// git-lfs 时留下的对象，后来 LFS 清掉了，但对象永远留在历史里。之后用
/// Release 附件传上去的东西，**不会**进这个命名空间。
///
/// 所以每个包都必须另外挂一条按标签直连的地址（`release_urls`）。只写这一条
/// 的话，新加的包会在用户机器上报「下载失败」，而我们本地什么都测不出来。
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

/// 按 Release 标签直连的下载地址，作为 `/-/lfs/<sha>` 的备用源。
///
/// 按 sha 寻址那条路要等 CNB 侧建索引，刚传上去的制品会 404 一段时间（实测
/// 新传的包直连 206、按 sha 404）。只挂一条源等于把「能不能装」押在一个我们
/// 控制不了的后台任务上。
///
/// 两条路指向同一个文件，而下载完照样按 sha 校验，多一条源不会放松任何检查。
pub fn release_urls(root: &Path, tag: &str, file: &str) -> Vec<String> {
    crate::mirrors::lfs_bases(root)
        .into_iter()
        .map(|base| format!("{base}/-/releases/download/{tag}/{file}"))
        .collect()
}

/// 同 `fetch_pack`，但在按 sha 寻址之后再挂几条备用地址。
pub fn fetch_pack_with_fallback(
    cache_name: &str,
    sha: &str,
    extra: Vec<String>,
    dest_root: &Path,
    root: &Path,
    cancel: Arc<AtomicBool>,
    progress: Option<download::ProgressFn>,
) -> Result<(), String> {
    let cache = paths::update_cache(root);
    std::fs::create_dir_all(&cache).map_err(|e| e.to_string())?;
    let archive = cache.join(cache_name);
    let cached_ok = archive.is_file() && download::verify_sha256(&archive, sha).is_ok();
    if !cached_ok {
        let mut urls = lfs_urls(root, sha);
        urls.extend(extra);
        download::download_request(
            download::DownloadRequest {
                urls,
                root: Some(root.to_path_buf()),
                dest: archive.clone(),
                expected_sha256: sha.to_string(),
                size_hint: catalog_size_for(root, cache_name),
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

/// 制品的 Release 标签。按 sha 寻址那条路只对**老制品**有效（见 `lfs_urls`
/// 上面那段），所以每个包都要能按标签直连兜底。
fn release_ref(cache_name: &str) -> Option<(&'static str, &'static str)> {
    match cache_name {
        ENGINE_CORE_NAME => Some(("engine-core", ENGINE_CORE_NAME)),
        VBCABLE_NAME => Some(("vbcable", VBCABLE_NAME)),
        _ => None,
    }
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
        let mut urls = lfs_urls(root, sha);
        if let Some((tag, file)) = release_ref(cache_name) {
            urls.extend(release_urls(root, tag, file));
        }
        download::download_request(
            download::DownloadRequest {
                urls,
                root: Some(root.to_path_buf()),
                dest: archive.clone(),
                expected_sha256: sha.to_string(),
                size_hint: catalog_size_for(root, cache_name),
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
    // 先拿锁再看就绪：并发触发的第二个调用等第一个下完，回头一看文件都在
    // 了，直接返回 —— 而不是再起一条下载线程去打同一个 .part。
    let _flight = pack_lock();
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
    // 与 engine-core 共用一把锁：两个包都走 update_cache 里的同一条下载管线，
    // 弱网下同时抢带宽只会两个都下不动，串行反而各自更快落地。
    let _flight = pack_lock();
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
    fn catalog_size_feeds_the_engine_core_download() {
        // 754MB 的包以前 size_hint 恒为 0，auto_connections 只给一条连接慢慢
        // 爬，进度条连分母都没有。大小得从内置清单里查出来。
        let root = crate::testutil::scratch("catalog-size");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("configs")).unwrap();
        std::fs::write(
            root.join("configs").join("online_catalog.json"),
            r#"{"engine_core":{"name":"engine-core-260722.zip","size_bytes":753796337}}"#,
        )
        .unwrap();
        assert_eq!(catalog_size_for(&root, "engine-core-260722.zip"), 753_796_337);
        assert_eq!(catalog_size_for(&root, "not-in-catalog.zip"), 0);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn missing_when_root_is_empty() {
        let tmp = crate::testutil::scratch("engine-core-test");
        let _ = std::fs::create_dir_all(&tmp);
        assert_eq!(engine_core_missing(&tmp).len(), 5);
        assert!(!engine_core_ready(&tmp));
    }

    #[test]
    fn truncated_file_does_not_count_as_ready() {
        let tmp = crate::testutil::scratch("engine-core-trunc");
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
        let base = crate::testutil::scratch("hoist-test");
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
        let root = crate::testutil::scratch("lfs-url");
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
    fn a_release_tag_url_is_built_for_every_mirror() {
        // 按 sha 寻址要等 CNB 建索引，新传的包会 404 一阵子。备用源必须跟着
        // 镜像一起铺开，只有官方仓一条的话 CNB 一挂就全断。
        let root = crate::testutil::scratch("rel-url");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("configs")).unwrap();
        std::fs::write(
            root.join("configs").join("online_catalog.json"),
            r#"{"download_mirrors":{"lfs":["https://backup.example.cn/Turing-Mirror/Rel"]}}"#,
        )
        .unwrap();
        let u = release_urls(&root, "vcredist", "vcredist-x64.zip");
        assert_eq!(u.len(), 2, "{u:?}");
        assert!(u[0].starts_with(CNB_REPO), "官方仓库必须还是第一个");
        assert!(u[0].ends_with("/-/releases/download/vcredist/vcredist-x64.zip"), "{}", u[0]);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn lfs_urls_pick_up_catalog_mirrors() {
        // engine-core 是首次运行的必经之路，以前只有一个源，CNB 一挂谁都装不上。
        let root = crate::testutil::scratch("lfs-mirror");
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
