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

/// 已经打上的界面补丁版本，读不到就是空串。
///
/// 补丁只换 `frontend/`，换不了 exe，所以打完补丁 APP_VERSION 还是旧的。
/// 光看 APP_VERSION 的话，同一个补丁会被无限次提示「有新版本」—— 装了、
/// 重启了、再问一次还是有。补丁里带了 `tm_package.json`，版本号跟着界面
/// 走，读它才知道界面到底到哪一版了。
fn applied_ui_version() -> String {
    let Some(dir) = ui_assets::external_dir() else {
        return String::new();
    };
    let Ok(text) = std::fs::read_to_string(dir.join("tm_package.json")) else {
        return String::new();
    };
    let Ok(v) = serde_json::from_str::<Value>(&text) else {
        return String::new();
    };
    field(&v, "version").to_string()
}

/// 本机的「有效版本」：exe 和界面里更新的那一个。
///
/// 装了整包就是 exe 的版本；之后又打了界面补丁，就是补丁的版本。反过来，
/// 整包更新之后 exe 比界面新，这时要以 exe 为准 —— 整包里自带的 frontend
/// 会把旧补丁覆盖掉，但如果没覆盖干净，也不能让旧的 tm_package.json 把
/// 版本号拉回去。
fn effective_version() -> String {
    let ui = applied_ui_version();
    if !ui.is_empty() && compare_versions(APP_VERSION, &ui) < 0 {
        ui
    } else {
        APP_VERSION.to_string()
    }
}

/// 从清单里挑出「该装哪个包」的那一段。
///
/// 清单实际长这样（build_catalog.py 生成的 index.json）：
///
/// ```json
/// { "app": { "version": "1.3.3", "gui": { "package_type": …, "url": … } } }
/// ```
///
/// 以前这里读的是**顶层**的 `gui` 和 `app_version` —— 那两个键在清单里根本
/// 不存在。于是版本号取到空串，`newer` 恒为 false，「检查更新」永远回答
/// 「已是最新」，不管远端发了什么。整条更新链路就是这么断的，而且断得很安静：
/// 没有报错，只有一句听起来很正常的「已是最新」。
///
/// 顶层的 `gui` / `app_version` 仍然兜底读一次，万一以后清单换形状。
fn gui_entry(cat: &Value) -> Value {
    cat.get("app")
        .and_then(|a| a.get("gui"))
        .or_else(|| cat.get("gui"))
        .cloned()
        .unwrap_or(Value::Null)
}

/// 远端版本号：先看 gui 段自己的，再看 `app.version`，最后兜底顶层。
fn remote_version(cat: &Value, gui: &Value) -> String {
    for v in [
        field(gui, "version"),
        cat.get("app")
            .map(|a| field(a, "version"))
            .unwrap_or_default(),
        field(cat, "app_version"),
    ] {
        if !v.is_empty() {
            return v.to_string();
        }
    }
    String::new()
}

/// 纯函数版的 check：给定清单和本机版本，算出该回什么。
///
/// 抽出来是为了能测 —— 上面那个「读错键」的 bug 活了整整一个大版本，就是因为
/// check() 全程要联网，没人能给它写用例。tests 里拿真实形状的清单钉住了。
fn decide(cat: &Value, local: &str, exe_version: &str) -> Value {
    let gui = gui_entry(cat);
    let remote = remote_version(cat, &gui);
    let url = field(&gui, "url").to_string();
    let sha = field(&gui, "sha256").to_string();
    let notes = field(&gui, "notes").to_string();
    let pkg = {
        let p = field(&gui, "package_type");
        if p.is_empty() { "gui_patch" } else { p }.to_string()
    };
    let min_app = field(&gui, "min_app_version").to_string();

    // 拿有效版本比，不是 exe 版本 —— 否则打过的界面补丁会一直重复提示。
    let newer = !remote.is_empty() && compare_versions(local, &remote) < 0;
    // min_app_version 卡的是 Rust 侧的能力（有没有那些命令），所以用 exe 的
    // 版本比：换了界面并不会让老 exe 多出命令来。
    let blocked = !min_app.is_empty() && compare_versions(exe_version, &min_app) < 0;

    json!({
        "local": local,
        "remote": if remote.is_empty() { "—".into() } else { remote },
        "available": newer && !url.is_empty() && !blocked,
        "blocked_by_min_version": blocked,
        "min_app_version": min_app,
        "package_type": pkg,
        "action": if pkg == "full_package" { "external" } else { "apply_patch" },
        "url": url,
        "sha256": sha,
        "notes": notes,
    })
}

/// Ask the catalog whether a newer build exists.
pub fn check(timeout_secs: u64) -> Result<Value, String> {
    let cat = catalog::fetch_remote_catalog(timeout_secs)?;
    Ok(decide(&cat, &effective_version(), APP_VERSION))
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
        return Err(crate::i18n::t("s.099b3eb863").into());
    }
    // download_file skips verification when the expected hash is empty, so an
    // absent sha256 in the catalog would mean "apply whatever this URL
    // returns" — for code that becomes the UI. Refuse instead of trusting the
    // feed to always be well-formed.
    if sha256.chars().filter(|c| c.is_ascii_hexdigit()).count() != 64 {
        return Err(crate::i18n::t("s.a6af760282").into());
    }
    let target = ui_assets::external_dir()
        .ok_or(crate::i18n::t("s.6462f5c407"))?;

    let cache = paths::update_cache(root);
    std::fs::create_dir_all(&cache).map_err(|e| e.to_string())?;
    let zip = cache.join("gui_patch.zip");
    download::download_file(&[url.to_string()], &zip, sha256, cancel, None)
        .map_err(|e| crate::i18n::te("s.acc7dfe816", &(e)))?;

    let stage = staging_dir(root);
    let _ = std::fs::remove_dir_all(&stage);
    extract::extract_zip(&zip, &stage).map_err(|e| crate::i18n::te("s.0350fdf3a0", &(e)))?;

    // The zip may or may not have a single top-level folder.
    let payload = single_child_dir(&stage).unwrap_or_else(|| stage.clone());
    if !payload.join("index.html").is_file() {
        let _ = std::fs::remove_dir_all(&stage);
        return Err(crate::i18n::t("s.f0098a67e2").into());
    }

    // Keep the previous UI next to the new one until the swap succeeds.
    let backup = target.with_extension("prev");
    let _ = std::fs::remove_dir_all(&backup);
    if target.exists() {
        std::fs::rename(&target, &backup).map_err(|e| crate::i18n::te("s.a9fa441818", &(e)))?;
    }
    if let Err(e) = std::fs::rename(&payload, &target) {
        // Put the old one back rather than leaving the app with no UI at all.
        let _ = std::fs::rename(&backup, &target);
        let _ = std::fs::remove_dir_all(&stage);
        return Err(crate::i18n::te("s.7935e3dd3e", &(e)));
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

    /// index.json 的真实形状（build_catalog.py 生成的那种）。
    fn real_catalog(version: &str, pkg: &str, url: &str) -> Value {
        json!({
            "schema": 1,
            "packages": { "setup": [], "gui_patch": [] },
            "app": {
                "version": version,
                "channel": "stable",
                "gui": {
                    "package_type": pkg,
                    "version": version,
                    "url": url,
                    "sha256": "a".repeat(64),
                    "min_app_version": "1.3.0",
                    "notes": "x"
                }
            }
        })
    }

    /// 这条用例钉的就是「检查更新永远说已是最新」那个 bug：清单里的 gui 在
    /// app 底下，以前读的是顶层，取不到版本号就永远不更新。
    #[test]
    fn reads_gui_from_app_section() {
        let cat = real_catalog("1.3.3", "full_package", "https://x/setup.exe");
        let r = decide(&cat, "1.3.1", "1.3.1");
        assert_eq!(r["remote"], "1.3.3");
        assert_eq!(r["available"], true);
        assert_eq!(r["action"], "external");
    }

    #[test]
    fn top_level_gui_still_works() {
        let cat = json!({
            "gui": { "package_type": "gui_patch", "version": "9.9.9",
                     "url": "https://x/p.zip", "sha256": "b".repeat(64) }
        });
        let r = decide(&cat, "1.3.3", "1.3.3");
        assert_eq!(r["remote"], "9.9.9");
        assert_eq!(r["available"], true);
        assert_eq!(r["action"], "apply_patch");
    }

    #[test]
    fn same_version_is_not_an_update() {
        let cat = real_catalog("1.3.3", "full_package", "https://x/setup.exe");
        let r = decide(&cat, "1.3.3", "1.3.3");
        assert_eq!(r["available"], false);
    }

    /// 打完界面补丁之后，exe 还是旧的，但界面已经是新的 —— 不能再提示一次。
    #[test]
    fn applied_ui_patch_stops_the_nag() {
        let cat = real_catalog("1.3.4", "gui_patch", "https://x/p.zip");
        // 界面已经打到 1.3.4，exe 仍是 1.3.3
        let r = decide(&cat, "1.3.4", "1.3.3");
        assert_eq!(r["available"], false, &crate::i18n::t("s.8cdca7ff61"));
    }

    /// exe 太老、装不了目标版本时，不该让用户去下一个装不上的包。
    #[test]
    fn blocked_by_min_version_is_not_offered() {
        let mut cat = real_catalog("1.4.0", "full_package", "https://x/setup.exe");
        cat["app"]["gui"]["min_app_version"] = json!("1.3.5");
        let r = decide(&cat, "1.3.1", "1.3.1");
        assert_eq!(r["blocked_by_min_version"], true);
        assert_eq!(r["available"], false);
    }

    /// 清单缺字段 / 拿到个空对象时，绝不能凭空说有更新。
    #[test]
    fn empty_catalog_offers_nothing() {
        let r = decide(&json!({}), "1.3.3", "1.3.3");
        assert_eq!(r["available"], false);
        assert_eq!(r["remote"], "—");
    }

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
        .map_err(|_| crate::i18n::t("s.6a3b354477"))?;
    let Some(update) = updater.check().await.map_err(|e| e.to_string())? else {
        return Ok(json!({"available": false, "local": APP_VERSION}));
    };
    let version = update.version.clone();
    update
        .download_and_install(|_chunk, _total| {}, || {})
        .await
        .map_err(|e| crate::i18n::te("s.90d174c86a", &(e)))?;
    Ok(json!({
        "available": true,
        "installed": true,
        "version": version,
        "restart_required": true,
    }))
}
