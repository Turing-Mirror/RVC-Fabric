//! Self-update (OTA strategy A delivery side).
//!
//! `ui_assets` made the UI loadable from a swappable `frontend/` directory;
//! this module is what actually fetches a new one. Two package types, matching
//! `launcher/online/package_spec.py`:
//!
//! * **`gui_patch`** — a zip of the frontend. Downloaded, verified, staged, and
//!   swapped in atomically. Takes effect on restart. No new exe.
//! * **`full_package`** — never merged in-process. We only open the download
//!   page, because replacing the running exe is not something to attempt from
//!   inside it.
//!
//! Versions are plain `X.Y.Z`. `-hotfixN` / `-partN` are recognised only so
//! that clients still running an old build compare correctly; nothing new is
//! ever published in those forms.

use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;
use std::sync::Arc;

use serde_json::{json, Value};

use crate::{catalog, download, extract, paths, ui_assets};

/// Shipping version. Keep in step with tauri.conf.json and package.json.
pub const APP_VERSION: &str = "1.3.0";

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
    fn garbage_never_triggers_a_downgrade() {
        assert_eq!(compare_versions("1.3.0", "not-a-version"), 0);
        assert_eq!(compare_versions("", "1.3.0"), 0);
        assert_eq!(compare_versions("1.2.3.4", "1.3.0"), 0);
    }
}
