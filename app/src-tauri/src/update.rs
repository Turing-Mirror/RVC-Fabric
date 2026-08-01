//! Self-update (OTA strategy A delivery side).
//!
//! `ui_assets` made the UI loadable from a swappable `frontend/` directory;
//! this module is what actually fetches a new one. Two package types, matching
//! `launcher/online/package_spec.py`:
//!
//! * **`gui_patch`** — a zip of the frontend. Downloaded, verified, staged, and
//!   swapped in atomically. Takes effect on restart. No new exe.
//! * **`full_package`** — the Rust side changed, so the exe must be replaced.
//!   Handled by the Tauri updater (strategy B), which verifies a detached
//!   signature against the public key baked into the build. We never merge an
//!   exe in-process.
//!
//! Versions are plain `X.Y.Z`. `-hotfixN` / `-partN` are recognised only so
//! that clients still running an old build compare correctly; nothing new is
//! ever published in those forms.

use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;
use std::sync::Arc;

use serde_json::{json, Value};

use crate::{catalog, download, extract, paths, ui_assets};

/// 本机版本号，编译期从 Cargo.toml 取。
///
/// 别改回手写字符串。1.3.1 就是这么翻的车：版本号 bump 改了 5 个地方，漏了
/// 这一个，于是发出去的 1.3.1 对外自称 1.3.0 —— 「其他」页显示错、遥测把
/// 一整批用户记成上一版、广场的版本定向全部落空。这几处都读 APP_VERSION：
/// shell_version / telemetry::tick / plaza 定向 / 更新检查 / min_app_version。
///
/// 现在它跟着 Cargo.toml 走，漏不掉。剩下四处手写的版本号（Cargo.toml、
/// tauri.conf.json、package.json、Inno 的 .iss）由 tests/test_version_sync.py
/// 盯着，对不上就测试挂，不用等发版之后才发现。
pub const APP_VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Debug, Clone, PartialEq, Eq)]
struct Ver {
    base: (u64, u64, u64),
    /// 0 = plain release, >0 = post-release hotfix, <0 = pre-release part.
    tag: i64,
}

fn parse_version(s: &str) -> Option<Ver> {
    let s = s.trim();
    let (core, tag) = match s.split_once('-') {
        None => (s, 0i64),
        Some((c, rest)) => {
            let r = rest.to_ascii_lowercase();
            let n = |p: &str| r.strip_prefix(p).and_then(|x| x.parse::<i64>().ok());
            if let Some(v) = n("hotfix") {
                (c, v.max(1))
            } else if let Some(v) = n("part") {
                (c, -v.max(1))
            } else {
                (c, 0)
            }
        }
    };
    let mut it = core.split('.');
    let a = it.next()?.trim().parse::<u64>().ok()?;
    let b = it.next().unwrap_or("0").trim().parse::<u64>().ok()?;
    let c = it.next().unwrap_or("0").trim().parse::<u64>().ok()?;
    if it.next().is_some() {
        return None;
    }
    Some(Ver { base: (a, b, c), tag })
}

/// <0 when `a` is older. Unparseable input compares as equal so a malformed
/// catalog entry can never trigger a downgrade.
pub fn compare_versions(a: &str, b: &str) -> i32 {
    let (Some(x), Some(y)) = (parse_version(a), parse_version(b)) else {
        return 0;
    };
    match x.base.cmp(&y.base) {
        std::cmp::Ordering::Less => -1,
        std::cmp::Ordering::Greater => 1,
        std::cmp::Ordering::Equal => match x.tag.cmp(&y.tag) {
            std::cmp::Ordering::Less => -1,
            std::cmp::Ordering::Greater => 1,
            std::cmp::Ordering::Equal => 0,
        },
    }
}

fn field<'a>(v: &'a Value, key: &str) -> &'a str {
    v.get(key).and_then(|x| x.as_str()).unwrap_or("")
}

/// Ask the catalog whether a newer build exists.
pub fn check(timeout_secs: u64) -> Result<Value, String> {
    let cat = catalog::fetch_remote_catalog(timeout_secs)?;
    let gui = cat.get("gui").cloned().unwrap_or(Value::Null);
    let remote = {
        let v = field(&gui, "version");
        if v.is_empty() {
            field(&cat, "app_version")
        } else {
            v
        }
    }
    .to_string();
    let url = field(&gui, "url").to_string();
    let sha = field(&gui, "sha256").to_string();
    let notes = field(&gui, "notes").to_string();
    let pkg = {
        let p = field(&gui, "package_type");
        if p.is_empty() { "gui_patch" } else { p }.to_string()
    };
    let min_app = field(&gui, "min_app_version").to_string();

    let newer = !remote.is_empty() && compare_versions(APP_VERSION, &remote) < 0;
    // A min_app_version above ours means we cannot jump straight there.
    let blocked = !min_app.is_empty() && compare_versions(APP_VERSION, &min_app) < 0;

    Ok(json!({
        "local": APP_VERSION,
        "remote": if remote.is_empty() { "—".into() } else { remote },
        "available": newer && !url.is_empty(),
        "blocked_by_min_version": blocked,
        "min_app_version": min_app,
        "package_type": pkg,
        "action": if pkg == "full_package" { "external" } else { "apply_patch" },
        "url": url,
        "sha256": sha,
        "notes": notes,
    }))
}

fn staging_dir(root: &Path) -> PathBuf {
    paths::update_cache(root).join("frontend_stage")
}

/// Download a `gui_patch` and swap it into the external `frontend/` directory.
///
/// Two-phase: extract fully into a staging dir first, and only touch the live
/// directory once the payload looks complete. A half-applied UI is a white
/// screen with no way back.
pub fn apply_gui_patch(
    root: &Path,
    url: &str,
    sha256: &str,
    cancel: Arc<AtomicBool>,
) -> Result<PathBuf, String> {
    if url.is_empty() {
        return Err("更新地址为空".into());
    }
    // download_file skips verification when the expected hash is empty, so an
    // absent sha256 in the catalog would mean "apply whatever this URL
    // returns" — for code that becomes the UI. Refuse instead of trusting the
    // feed to always be well-formed.
    if sha256.chars().filter(|c| c.is_ascii_hexdigit()).count() != 64 {
        return Err("更新包缺少有效的 sha256，已拒绝应用".into());
    }
    let target = ui_assets::external_dir()
        .ok_or("找不到可替换的 frontend 目录，本次安装无法热更界面")?;

    let cache = paths::update_cache(root);
    std::fs::create_dir_all(&cache).map_err(|e| e.to_string())?;
    let zip = cache.join("gui_patch.zip");
    download::download_file(&[url.to_string()], &zip, sha256, cancel, None)
        .map_err(|e| format!("下载更新失败：{e}"))?;

    let stage = staging_dir(root);
    let _ = std::fs::remove_dir_all(&stage);
    extract::extract_zip(&zip, &stage).map_err(|e| format!("解压更新失败：{e}"))?;

    // The zip may or may not have a single top-level folder.
    let payload = single_child_dir(&stage).unwrap_or_else(|| stage.clone());
    if !payload.join("index.html").is_file() {
        let _ = std::fs::remove_dir_all(&stage);
        return Err("更新包里没有 index.html，已放弃应用".into());
    }

    // Keep the previous UI next to the new one until the swap succeeds.
    let backup = target.with_extension("prev");
    let _ = std::fs::remove_dir_all(&backup);
    if target.exists() {
        std::fs::rename(&target, &backup).map_err(|e| format!("备份旧界面失败：{e}"))?;
    }
    if let Err(e) = std::fs::rename(&payload, &target) {
        // Put the old one back rather than leaving the app with no UI at all.
        let _ = std::fs::rename(&backup, &target);
        let _ = std::fs::remove_dir_all(&stage);
        return Err(format!("替换界面失败：{e}"));
    }
    let _ = std::fs::remove_dir_all(&backup);
    let _ = std::fs::remove_dir_all(&stage);
    let _ = std::fs::remove_file(&zip);
    Ok(target)
}

fn single_child_dir(dir: &Path) -> Option<PathBuf> {
    let mut it = std::fs::read_dir(dir).ok()?.filter_map(|e| e.ok());
    let first = it.next()?;
    if it.next().is_some() {
        return None;
    }
    let p = first.path();
    if p.is_dir() {
        Some(p)
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plain_versions_order() {
        assert!(compare_versions("1.2.4", "1.3.0") < 0);
        assert!(compare_versions("1.3.0", "1.3.0") == 0);
        assert!(compare_versions("1.10.0", "1.9.0") > 0);
    }

    #[test]
    fn hotfix_is_newer_than_its_base_part_is_older() {
        assert!(compare_versions("1.2.3", "1.2.3-hotfix1") < 0);
        assert!(compare_versions("1.2.3-hotfix3", "1.2.4") < 0);
        assert!(compare_versions("1.2.3-part1", "1.2.3") < 0);
        assert!(compare_versions("1.2.3-part1", "1.2.3-hotfix1") < 0);
    }

    #[test]
    fn old_clients_can_jump_straight_to_current() {
        // The whole point: no chaining through intermediate releases.
        assert!(compare_versions("1.2.3-hotfix3", APP_VERSION) < 0);
    }

    #[test]
    fn refuses_a_patch_without_a_valid_sha256() {
        // download_file skips verification on an empty hash, so this guard is
        // the only thing standing between a malformed catalog and arbitrary
        // code becoming the UI.
        let root = std::env::temp_dir();
        let cancel = Arc::new(AtomicBool::new(false));
        for bad in ["", "abc", "not-a-hash"] {
            let err = apply_gui_patch(&root, "https://x/y.zip", bad, cancel.clone())
                .unwrap_err();
            assert!(err.contains("sha256"), "expected sha256 refusal, got {err}");
        }
    }

    #[test]
    fn garbage_never_triggers_a_downgrade() {
        assert_eq!(compare_versions("1.3.0", "not-a-version"), 0);
        assert_eq!(compare_versions("", "1.3.0"), 0);
        assert_eq!(compare_versions("1.2.3.4", "1.3.0"), 0);
    }
}


// ---------------------------------------------------------------------------
// Strategy B — replace the executable via the Tauri updater
// ---------------------------------------------------------------------------

/// Check the signed updater feed and install if a newer build is published.
///
/// Signature verification is done by the plugin against the pubkey compiled
/// into the binary; an unsigned or wrongly-signed package is rejected before a
/// single byte is written. That is the difference from strategy A, where the
/// only integrity check is the sha256 carried in the catalog.
pub async fn run_app_updater(app: &tauri::AppHandle) -> Result<Value, String> {
    use tauri_plugin_updater::UpdaterExt;

    // Without a signing key pair there is nothing to verify against, and
    // shipping an unverified exe replacement is worse than not having the
    // feature. Say so plainly instead of failing with a plugin error.
    let updater = app
        .updater()
        .map_err(|_| "尚未配置更新签名密钥，请到发布页手动下载新版本".to_string())?;
    let Some(update) = updater.check().await.map_err(|e| e.to_string())? else {
        return Ok(json!({"available": false, "local": APP_VERSION}));
    };
    let version = update.version.clone();
    update
        .download_and_install(|_chunk, _total| {}, || {})
        .await
        .map_err(|e| format!("安装更新失败：{e}"))?;
    Ok(json!({
        "available": true,
        "installed": true,
        "version": version,
        "restart_required": true,
    }))
}
