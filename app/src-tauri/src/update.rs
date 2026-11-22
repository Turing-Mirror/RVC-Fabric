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
//! Stable uses `X.Y.Z`; Beta uses `X.Y.Z-beta.N`. Historical `hotfix` / `part`
//! builds retain their old ordering for clients migrating from the Python shell.

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use serde_json::{json, Value};

use crate::{
    download, extract, paths, ui_assets,
    update_channel::{self, Channel},
};

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
    version: semver::Version,
    /// Old hotfix builds intentionally sorted after their plain release.
    hotfix: Option<u64>,
}

fn parse_version(s: &str) -> Option<Ver> {
    let mut version = semver::Version::parse(s.trim()).ok()?;
    let suffix = version.pre.as_str().to_ascii_lowercase();
    let hotfix = suffix
        .strip_prefix("hotfix")
        .and_then(|n| n.parse::<u64>().ok());
    if hotfix.is_some() {
        version.pre = semver::Prerelease::EMPTY;
    } else if let Some(n) = suffix
        .strip_prefix("part")
        .and_then(|n| n.parse::<u64>().ok())
    {
        // Numeric historical part order, including part10 > part2.
        version.pre = semver::Prerelease::new(&format!("part.{}", n.max(1))).ok()?;
    }
    Some(Ver {
        version,
        hotfix: hotfix.map(|n| n.max(1)),
    })
}

/// <0 when `a` is older. Unparseable input compares as equal so a malformed
/// catalog entry can never trigger a downgrade.
pub fn compare_versions(a: &str, b: &str) -> i32 {
    let (Some(x), Some(y)) = (parse_version(a), parse_version(b)) else {
        return 0;
    };
    let base = |v: &semver::Version| (v.major, v.minor, v.patch);
    match base(&x.version).cmp(&base(&y.version)) {
        std::cmp::Ordering::Less => -1,
        std::cmp::Ordering::Greater => 1,
        std::cmp::Ordering::Equal => match x
            .hotfix
            .cmp(&y.hotfix)
            .then_with(|| x.version.cmp_precedence(&y.version))
        {
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
    if !ui.is_empty()
        && Channel::for_version(&ui) == update_channel::installed()
        && compare_versions(APP_VERSION, &ui) < 0
    {
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
    // Prefer notes_i18n[locale] from catalog; fall back to Chinese notes.
    let notes = {
        let n = crate::i18n::pick_str(&gui, "notes");
        if n.is_empty() {
            field(&gui, "notes").to_string()
        } else {
            n
        }
    };
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
        "remote": if remote.is_empty() { crate::i18n::t("s.valueUnknown") } else { remote },
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

/// Check the release website for a newer build.
pub fn check(timeout_secs: u64) -> Result<Value, String> {
    let cat = crate::plaza::fetch_release_feed("app.json", timeout_secs)?;
    let mut result = decide(&cat, &effective_version(), APP_VERSION);
    result["channel"] = json!("stable");
    result["installed_channel"] = json!(update_channel::installed());
    result["switching_channel"] = json!(false);
    result["downgrade"] = json!(false);
    result["legacy_target"] = json!(matches!(result["remote"].as_str(), Some("1.8.0" | "1.8.1")));
    Ok(result)
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
    if sha256.len() != 64 || !sha256.bytes().all(|c| c.is_ascii_hexdigit()) {
        return Err(crate::i18n::t("s.a6af760282").into());
    }
    let target = ui_assets::external_dir().ok_or(crate::i18n::t("s.6462f5c407"))?;

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

    // A channel change always requires a complete signed installer. A frontend
    // patch cannot turn a Stable executable into Beta or revert its native code.
    let manifest = std::fs::read(payload.join("tm_package.json"))
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok());
    if let Some(version) = manifest
        .as_ref()
        .and_then(|m| m.get("version"))
        .and_then(Value::as_str)
    {
        if Channel::for_version(version) != update_channel::installed() {
            let _ = std::fs::remove_dir_all(&stage);
            return Err(crate::i18n::t("update.invalidChannel"));
        }
    } else if update_channel::installed() == Channel::Beta {
        let _ = std::fs::remove_dir_all(&stage);
        return Err(crate::i18n::t("update.invalidVersion"));
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
        assert_eq!(r["available"], false);
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
        assert_eq!(r["remote"], crate::i18n::t("s.valueUnknown"));
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
            let err = apply_gui_patch(&root, "https://x/y.zip", bad, cancel.clone()).unwrap_err();
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

fn channel_updater(
    app: &tauri::AppHandle,
    channel: Channel,
) -> Result<tauri_plugin_updater::Updater, String> {
    use tauri_plugin_updater::UpdaterExt;
    let mut builder = app
        .updater_builder()
        // Inspect a target even when it is older. The separate offer predicate
        // below permits downgrades only for an explicitly selected channel.
        .version_comparator(|_, _| true)
        .timeout(std::time::Duration::from_secs(180));
    if channel == Channel::Beta {
        let source = update_channel::settings()?.beta;
        let endpoint = source
            .endpoint
            .parse()
            .map_err(|_| crate::i18n::t("update.channelUnavailable"))?;
        builder = builder
            .endpoints(vec![endpoint])
            .map_err(|e| e.to_string())?
            .pubkey(source.pubkey);
    }
    let app_exit = app.clone();
    builder = builder.on_before_exit(move || {
        crate::shutdown_for_update(&app_exit);
        app_exit.cleanup_before_exit();
    });
    builder.build().map_err(|e| e.to_string())
}

fn can_offer(
    local: &str,
    remote: &str,
    installed: Channel,
    target: Channel,
    explicit: bool,
) -> bool {
    if explicit && installed != target {
        return true;
    }
    compare_versions(local, remote) < 0
}

fn empty_signed_offer(channel: Channel) -> Value {
    json!({
        "local": effective_version(), "remote": APP_VERSION, "available": false,
        "blocked_by_min_version": false, "min_app_version": "",
        "package_type": "full_package", "action": "external", "url": "", "sha256": "", "notes": "",
        "channel": channel, "installed_channel": update_channel::installed(),
        "switching_channel": channel != update_channel::installed(), "downgrade": false,
        "legacy_target": false,
    })
}

/// The ordinary Stable check keeps its existing catalog behavior. Explicit
/// channel selections and Beta checks use the channel's signed-installer feed.
pub async fn check_channel(
    app: &tauri::AppHandle,
    root: &Path,
    requested: Option<&str>,
) -> Result<Value, String> {
    let channel = update_channel::selected(requested)?;
    if requested.is_none() && channel == Channel::Stable {
        return tauri::async_runtime::spawn_blocking(|| check(12))
            .await
            .map_err(|e| e.to_string())?;
    }
    let updater = channel_updater(app, channel)?;
    let Some(update) = updater.check().await.map_err(|e| e.to_string())? else {
        return Ok(empty_signed_offer(channel));
    };
    update_channel::validate_target(root, channel, &update.version, &update.raw_json)?;
    let local = effective_version();
    Ok(json!({
        "local": local,
        "remote": update.version,
        "available": can_offer(&local, &update.version, update_channel::installed(), channel, requested.is_some()),
        "blocked_by_min_version": false,
        "min_app_version": "",
        "package_type": "full_package",
        "action": "external",
        "url": update.download_url.as_str(),
        "sha256": update.raw_json.get("sha256").and_then(Value::as_str).unwrap_or(""),
        "notes": update.body.as_deref().unwrap_or(""),
        "channel": channel,
        "installed_channel": update_channel::installed(),
        "switching_channel": channel != update_channel::installed(),
        "downgrade": compare_versions(APP_VERSION, &update.version) > 0,
        "legacy_target": channel == Channel::Stable && matches!(update.version.as_str(), "1.8.0" | "1.8.1"),
    }))
}

static INSTALL_BUSY: AtomicBool = AtomicBool::new(false);
static INSTALL_PREPARING: AtomicBool = AtomicBool::new(false);
static TASK_START_GATE: std::sync::Mutex<()> = std::sync::Mutex::new(());

/// Hold this only while admitting a new task and setting that task's busy flag.
/// It closes the race between the final idle check and a tool starting work.
pub(crate) fn task_start_guard() -> Result<std::sync::MutexGuard<'static, ()>, String> {
    let guard = TASK_START_GATE.lock().unwrap_or_else(|e| e.into_inner());
    if INSTALL_PREPARING.load(Ordering::Acquire) {
        return Err(crate::i18n::t("update.tasksBusy"));
    }
    Ok(guard)
}

struct PreparationGuard;
impl PreparationGuard {
    fn acquire() -> Self {
        let _admission = TASK_START_GATE.lock().unwrap_or_else(|e| e.into_inner());
        INSTALL_PREPARING.store(true, Ordering::Release);
        Self
    }
}
impl Drop for PreparationGuard {
    fn drop(&mut self) {
        INSTALL_PREPARING.store(false, Ordering::Release);
    }
}

struct InstallGuard;
impl InstallGuard {
    fn acquire() -> Result<Self, String> {
        INSTALL_BUSY
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .map_err(|_| crate::i18n::t("update.tasksBusy"))?;
        Ok(Self)
    }
}
impl Drop for InstallGuard {
    fn drop(&mut self) {
        INSTALL_BUSY.store(false, Ordering::Release);
    }
}

/// Long-running jobs are not interrupted by an update. The check is repeated
/// after downloading because the user can start a tool while bytes are arriving.
fn ensure_idle(root: &Path) -> Result<(), String> {
    let queue = crate::train_queue::list(root)?;
    let queue_active = queue["jobs"].as_array().is_some_and(|jobs| {
        jobs.iter().any(|j| {
            matches!(
                j["state"].as_str(),
                Some("queued" | "running" | "cancelling")
            )
        })
    });
    if crate::train::busy()
        || crate::sts::is_busy()
        || crate::sts::is_recording()
        || crate::tts::is_busy()
        || crate::separate::busy()
        || crate::provision::is_busy()
        || queue_active
    {
        return Err(crate::i18n::t("update.tasksBusy"));
    }
    Ok(())
}

#[cfg(any(windows, test))]
fn materialize_installer(root: &Path, version: &str, bytes: &[u8]) -> Result<PathBuf, String> {
    use std::io::Write;

    update_channel::validate_version(Channel::for_version(version), version)?;
    let dir = paths::user_data(root).join("update_channels/installers");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let destination = dir.join(format!("RVC-Fabric-Setup-{version}.exe"));
    let temp = dir.join(format!(
        ".setup-{}-{}.tmp",
        std::process::id(),
        rand::random::<u64>()
    ));
    let result = (|| {
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)
            .map_err(|e| e.to_string())?;
        file.write_all(bytes)
            .and_then(|_| file.sync_all())
            .map_err(|e| e.to_string())?;
        drop(file);
        std::fs::rename(&temp, &destination).map_err(|e| e.to_string())?;
        Ok(destination)
    })();
    if result.is_err() {
        let _ = std::fs::remove_file(&temp);
    }
    result
}

/// Keep the installer argument vector explicit; never invoke a shell. NSIS
/// requires /D to be the last, unquoted remainder of the Windows command line.
#[cfg(windows)]
fn windows_installer_command(
    root: &Path,
    installer: &Path,
) -> Result<std::process::Command, String> {
    use std::os::windows::process::CommandExt;

    let canonical = root.canonicalize().map_err(|e| e.to_string())?;
    let text = canonical
        .to_str()
        .ok_or_else(|| crate::i18n::t("update.backupFailed"))?;
    let directory = if let Some(unc) = text.strip_prefix(r"\\?\UNC\") {
        format!(r"\\{unc}")
    } else {
        text.strip_prefix(r"\\?\").unwrap_or(text).to_owned()
    };
    if directory.contains(['"', '\0', '\r', '\n']) || !canonical.is_absolute() {
        return Err(crate::i18n::t("update.backupFailed"));
    }
    let mut command = std::process::Command::new(installer);
    command
        .args(["/P", "/R", "/UPDATE"])
        .current_dir(&canonical)
        .raw_arg(format!("/D={directory}"));
    Ok(command)
}

fn recover_preparation(root: &Path, version: &str, mut error: String) -> String {
    if let Err(restore) = crate::update_install::rollback_preparation(root) {
        error.push_str(&format!(
            "; {}: {restore}",
            crate::i18n::t("update.backupFailed")
        ));
    }
    if let Err(cancel) = update_channel::cancel_pending(root, version) {
        error.push_str(&format!(
            "; {}: {cancel}",
            crate::i18n::t("update.backupFailed")
        ));
    }
    error
}

#[cfg(windows)]
fn launch_windows_installer(
    root: &Path,
    installer: &Path,
    version: &str,
) -> Result<std::process::Child, String> {
    let result = windows_installer_command(root, installer)
        .and_then(|mut command| command.spawn().map_err(|e| e.to_string()));
    result.map_err(|e| recover_preparation(root, version, e))
}

/// Install precisely the version that was confirmed. Feed changes require a
/// new check; simply changing channels never edits the running channel state.
pub async fn run_app_updater(
    app: &tauri::AppHandle,
    root: &Path,
    requested: Option<&str>,
    expected_version: Option<&str>,
) -> Result<Value, String> {
    let _install_guard = InstallGuard::acquire()?;
    let channel = update_channel::selected(requested)?;
    if requested.is_some() && expected_version.is_none() {
        return Err(crate::i18n::t("update.targetChanged"));
    }
    ensure_idle(root)?;
    let updater = channel_updater(app, channel)?;
    let Some(update) = updater.check().await.map_err(|e| e.to_string())? else {
        return Ok(json!({"available": false, "local": APP_VERSION}));
    };
    update_channel::validate_target(root, channel, &update.version, &update.raw_json)?;
    if expected_version.is_some_and(|v| v != update.version) {
        return Err(crate::i18n::t("update.targetChanged"));
    }
    if !can_offer(
        &effective_version(),
        &update.version,
        update_channel::installed(),
        channel,
        requested.is_some(),
    ) {
        return Ok(json!({"available": false, "local": APP_VERSION}));
    }
    let version = update.version.clone();
    let bytes = update
        .download(|_chunk, _total| {}, || {})
        .await
        .map_err(|e| crate::i18n::te("s.90d174c86a", &(e)))?;
    let _preparation = PreparationGuard::acquire();
    ensure_idle(root)?;
    update_channel::validate_target(root, channel, &version, &update.raw_json)?;
    // Finish all disk writes before moving live resources. These are precisely
    // the bytes already verified by Update::download against the channel key.
    #[cfg(windows)]
    let installer = materialize_installer(root, &version, &bytes)
        .map_err(|e| crate::i18n::te("s.90d174c86a", &e))?;
    update_channel::prepare_install(root, channel, &version)
        .map_err(|e| format!("{}: {e}", crate::i18n::t("update.backupFailed")))?;
    if let Err(e) = crate::update_install::prepare_install(root) {
        // prepare_install restores its own partial moves. Its previous backup
        // record may describe an older version and must not be replayed here.
        let _ = update_channel::cancel_pending(root, &version);
        return Err(format!("{}: {e}", crate::i18n::t("update.backupFailed")));
    }
    #[cfg(windows)]
    {
        // The plugin ignores ShellExecute failure and exits regardless. Launch
        // directly so an OS refusal restores resources while this UI is alive.
        let _installer = launch_windows_installer(root, &installer, &version)
            .map_err(|e| crate::i18n::te("s.90d174c86a", &e))?;
        crate::shutdown_for_update(app);
        app.cleanup_before_exit();
        std::process::exit(0);
    }
    #[cfg(not(windows))]
    {
        if let Err(e) = update.install(bytes) {
            let detail = recover_preparation(root, &version, e.to_string());
            return Err(crate::i18n::te("s.90d174c86a", &detail));
        }
        Ok(json!({
            "available": true, "installed": true,
            "version": version, "restart_required": true,
        }))
    }
}

#[cfg(test)]
mod channel_tests {
    use super::*;

    #[test]
    fn beta_ordering_is_numeric_and_build_metadata_does_not_order() {
        assert!(compare_versions("1.8.0", "1.9.0-beta.1") < 0);
        assert!(compare_versions("1.9.0-beta.2", "1.9.0-beta.10") < 0);
        assert!(compare_versions("1.9.0-beta.10", "1.9.0") < 0);
        assert_eq!(compare_versions("1.9.0-beta.2+abc", "1.9.0-beta.2+def"), 0);
        assert!(compare_versions("1.3.0-part2", "1.3.0-part10") < 0);
        assert!(compare_versions("1.3.0", "1.3.0-hotfix1") < 0);
        assert_eq!(compare_versions("1.9.0-beta.01", "1.9.0"), 0);
    }

    #[test]
    fn only_explicit_cross_channel_selection_can_offer_older_versions() {
        assert!(can_offer(
            "1.9.0-beta.3",
            "1.8.0",
            Channel::Beta,
            Channel::Stable,
            true
        ));
        assert!(!can_offer(
            "1.9.0-beta.3",
            "1.8.0",
            Channel::Beta,
            Channel::Stable,
            false
        ));
        assert!(!can_offer(
            "1.9.0-beta.3",
            "1.9.0-beta.2",
            Channel::Beta,
            Channel::Beta,
            true
        ));
        assert!(!can_offer(
            "1.9.0-beta.3",
            "1.9.0-beta.3",
            Channel::Beta,
            Channel::Beta,
            false
        ));
        assert!(can_offer(
            "1.9.0-beta.3",
            "1.9.0-beta.4",
            Channel::Beta,
            Channel::Beta,
            false
        ));
    }

    #[test]
    fn concurrent_installs_are_serialized_and_failure_releases_the_slot() {
        let first = InstallGuard::acquire().unwrap();
        assert!(InstallGuard::acquire().is_err());
        drop(first);
        assert!(InstallGuard::acquire().is_ok());
    }

    #[test]
    fn installer_materialization_uses_verified_bytes_and_refuses_unsafe_versions() {
        let root = crate::testutil::scratch("update-installer-write");
        std::fs::create_dir_all(&root).unwrap();
        let path =
            materialize_installer(&root, "1.8.2-beta.3", b"verified installer bytes").unwrap();
        assert_eq!(
            path.file_name().unwrap(),
            "RVC-Fabric-Setup-1.8.2-beta.3.exe"
        );
        assert_eq!(std::fs::read(&path).unwrap(), b"verified installer bytes");
        assert!(materialize_installer(&root, "../../escape", b"bad").is_err());
        assert!(materialize_installer(&root, "1.8.2-beta.3+hash", b"bad").is_err());
        let _ = std::fs::remove_dir_all(root);
    }

    #[cfg(windows)]
    #[test]
    fn windows_installer_command_keeps_target_directory_last_without_a_shell() {
        let root = crate::testutil::scratch("update-command").join("安装 空格");
        std::fs::create_dir_all(&root).unwrap();
        let installer = root.join("Setup.exe");
        let command = windows_installer_command(&root, &installer).unwrap();
        assert_eq!(command.get_program(), installer.as_os_str());
        let args: Vec<_> = command
            .get_args()
            .map(|v| v.to_string_lossy().into_owned())
            .collect();
        assert_eq!(&args[..3], ["/P", "/R", "/UPDATE"]);
        let target = args.last().unwrap();
        assert!(target.starts_with("/D="));
        assert!(target.ends_with("安装 空格"));
        assert!(!target.contains('"'));
        let _ = std::fs::remove_dir_all(root.parent().unwrap());
    }

    #[cfg(windows)]
    #[test]
    fn windows_spawn_refusal_restores_resources_and_cancels_pending() {
        let root = crate::testutil::scratch("update-launch-failure");
        std::fs::create_dir_all(root.join("frontend")).unwrap();
        std::fs::create_dir_all(root.join("User_Data/models")).unwrap();
        std::fs::write(root.join("rvc-fabric.exe"), b"current exe").unwrap();
        std::fs::write(root.join("frontend/index.html"), b"current frontend").unwrap();
        std::fs::write(root.join("User_Data/models/new.pth"), b"user model").unwrap();
        std::fs::write(
            root.join("setup_package.json"),
            serde_json::to_vec(&json!({
                "product":"RVC Fabric",
                "program_files":["frontend/index.html", "setup_package.json"],
            }))
            .unwrap(),
        )
        .unwrap();
        update_channel::prepare_install(&root, Channel::Beta, "1.8.2-beta.3").unwrap();
        crate::update_install::prepare_install(&root).unwrap();
        assert!(!root.join("frontend/index.html").exists());
        assert!(
            launch_windows_installer(&root, &root.join("does-not-exist.exe"), "1.8.2-beta.3")
                .is_err()
        );
        assert_eq!(
            std::fs::read(root.join("frontend/index.html")).unwrap(),
            b"current frontend"
        );
        assert!(root.join("setup_package.json").is_file());
        assert_eq!(
            std::fs::read(root.join("User_Data/models/new.pth")).unwrap(),
            b"user model"
        );
        let state: Value = serde_json::from_slice(
            &std::fs::read(root.join("User_Data/update_channels/state.json")).unwrap(),
        )
        .unwrap();
        assert!(state["pending"].is_null());
        let _ = std::fs::remove_dir_all(root);
    }
}
