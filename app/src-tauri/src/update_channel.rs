//! Release channel identity and the small, separate update transaction record.
//! User projects and Runtime trees never participate in rollback snapshots.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::{config, paths, update};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Channel {
    Stable,
    Beta,
}

impl Channel {
    pub fn name(self) -> &'static str {
        match self {
            Self::Stable => "stable",
            Self::Beta => "beta",
        }
    }

    pub fn parse(value: &str) -> Result<Self, String> {
        match value.trim() {
            "stable" => Ok(Self::Stable),
            "beta" => Ok(Self::Beta),
            _ => Err(crate::i18n::t("update.invalidChannel")),
        }
    }

    pub fn for_version(version: &str) -> Self {
        if semver::Version::parse(version)
            .ok()
            .is_some_and(|v| v.pre.as_str().starts_with("beta."))
        {
            Self::Beta
        } else {
            Self::Stable
        }
    }
}

#[derive(Deserialize)]
pub struct BetaSource {
    pub endpoint: String,
    pub pubkey: String,
}

#[derive(Deserialize)]
pub struct Settings {
    pub beta: BetaSource,
    pub data_schema: u32,
    pub minimum_stable_version: String,
}

pub fn settings() -> Result<Settings, String> {
    serde_json::from_str(include_str!("../update-channels.json"))
        .map_err(|_| crate::i18n::t("update.channelUnavailable"))
}

pub fn installed() -> Channel {
    static CHANNEL: std::sync::OnceLock<Channel> = std::sync::OnceLock::new();
    *CHANNEL.get_or_init(|| Channel::for_version(update::APP_VERSION))
}

pub fn selected(value: Option<&str>) -> Result<Channel, String> {
    value.map(Channel::parse).unwrap_or_else(|| Ok(installed()))
}

pub fn status() -> Value {
    let ready = settings()
        .is_ok_and(|s| s.beta.endpoint.starts_with("https://") && !s.beta.pubkey.trim().is_empty());
    json!({"channel": installed(), "version": update::APP_VERSION, "beta_available": ready})
}

fn state_dir(root: &Path) -> PathBuf {
    paths::user_data(root).join("update_channels")
}

fn state_path(root: &Path) -> PathBuf {
    state_dir(root).join("state.json")
}

fn schema_one() -> u32 {
    1
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct Pending {
    channel: Channel,
    version: String,
    data_schema: u32,
}

#[derive(Deserialize, Serialize)]
struct State {
    #[serde(default = "schema_one")]
    data_schema: u32,
    #[serde(default)]
    pending: Option<Pending>,
    #[serde(default)]
    confirmed_version: String,
}

impl Default for State {
    fn default() -> Self {
        Self {
            data_schema: 1,
            pending: None,
            confirmed_version: String::new(),
        }
    }
}

fn read_state(root: &Path) -> Result<State, String> {
    match std::fs::read(state_path(root)) {
        Ok(bytes) => {
            serde_json::from_slice(&bytes).map_err(|_| crate::i18n::t("update.dataIncompatible"))
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(State {
            data_schema: 1,
            ..State::default()
        }),
        Err(e) => Err(e.to_string()),
    }
}

fn save_state(root: &Path, state: &State) -> Result<(), String> {
    let text = serde_json::to_string_pretty(state).map_err(|e| e.to_string())?;
    config::write_atomic(&state_path(root), &text).map_err(|e| e.to_string())
}

/// Feed schema is an explicit compatibility promise. Legacy Stable feeds predate
/// it, and belong to schema 1; Beta feeds must carry it from their first release.
pub fn validate_target(
    root: &Path,
    channel: Channel,
    version: &str,
    feed: &Value,
) -> Result<(), String> {
    let cfg = settings()?;
    validate_version(channel, version)?;
    let local_schema = read_state(root)?.data_schema;
    let remote_schema = match feed.get("data_schema") {
        Some(v) => v.as_u64(),
        None if channel == Channel::Stable => Some(1),
        None => None,
    };
    if remote_schema != Some(u64::from(cfg.data_schema)) || local_schema != cfg.data_schema {
        return Err(crate::i18n::t("update.dataIncompatible"));
    }
    if let Some(value) = feed.get("channel") {
        if value.as_str() != Some(channel.name()) {
            return Err(crate::i18n::t("update.invalidChannel"));
        }
    } else if channel == Channel::Beta {
        return Err(crate::i18n::t("update.invalidChannel"));
    }
    if channel == Channel::Stable
        && update::compare_versions(version, &cfg.minimum_stable_version) < 0
    {
        return Err(crate::i18n::t("update.dataIncompatible"));
    }
    Ok(())
}

pub fn validate_version(channel: Channel, version: &str) -> Result<(), String> {
    let v = semver::Version::parse(version).map_err(|_| crate::i18n::t("update.invalidVersion"))?;
    let valid = match channel {
        Channel::Stable => v.pre.is_empty(),
        Channel::Beta => v
            .pre
            .as_str()
            .strip_prefix("beta.")
            .and_then(|n| n.parse::<u64>().ok())
            .is_some_and(|n| n > 0),
    };
    if !valid || !v.build.is_empty() {
        return Err(crate::i18n::t("update.invalidVersion"));
    }
    Ok(())
}

/// Save only the small compatibility files. Never restore an entire User_Data
/// snapshot: that would discard models and recordings made during Beta use.
pub fn prepare_install(root: &Path, channel: Channel, version: &str) -> Result<(), String> {
    let mut state = read_state(root)?;
    let cfg = settings()?;
    let backup = state_dir(root).join("backups").join(format!(
        "{}-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(|e| e.to_string())?
            .as_nanos(),
        std::process::id()
    ));
    std::fs::create_dir_all(&backup).map_err(|e| e.to_string())?;
    for name in [
        "app_config.json",
        "train_queue.json",
        "audio/library.json",
        "mobile/jobs.json",
    ] {
        let source = paths::user_data(root).join(name);
        match std::fs::metadata(&source) {
            Ok(meta) if meta.is_file() => {}
            Ok(_) => return Err(format!("更新备份需要普通文件: {name}")),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => continue,
            Err(e) => return Err(e.to_string()),
        }
        let target = backup.join(name);
        std::fs::create_dir_all(target.parent().unwrap()).map_err(|e| e.to_string())?;
        let bytes = std::fs::read(&source).map_err(|e| e.to_string())?;
        // A concurrently interrupted settings write is a reason to retry the
        // update, not to save a corrupt "recovery" snapshot.
        serde_json::from_slice::<Value>(&bytes).map_err(|e| e.to_string())?;
        std::fs::write(target, bytes).map_err(|e| e.to_string())?;
    }
    std::fs::write(
        backup.join("update.json"),
        serde_json::to_vec_pretty(&json!({
            "from_version": update::APP_VERSION,
            "to_version": version,
            "channel": channel,
            "data_schema": cfg.data_schema,
        }))
        .map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    state.pending = Some(Pending {
        channel,
        version: version.into(),
        data_schema: cfg.data_schema,
    });
    save_state(root, &state)
}

pub fn cancel_pending(root: &Path, version: &str) -> Result<(), String> {
    let mut state = read_state(root)?;
    if state.pending.as_ref().is_some_and(|p| p.version == version) {
        state.pending = None;
        save_state(root, &state)?;
    }
    Ok(())
}

/// Only a successfully mounted UI from the expected executable confirms an
/// installation. An older Stable without this code intentionally leaves pending.
pub fn confirm_startup(root: &Path) -> Result<(), String> {
    let mut state = read_state(root)?;
    let Some(pending) = state.pending.as_ref() else {
        return Ok(());
    };
    if pending.version != update::APP_VERSION || pending.channel != installed() {
        crate::logging::shell_log!("更新目标尚未确认，当前版本 {}", update::APP_VERSION);
        return Ok(());
    }
    if pending.data_schema != settings()?.data_schema {
        return Err(crate::i18n::t("update.dataIncompatible"));
    }
    state.data_schema = pending.data_schema;
    state.confirmed_version = update::APP_VERSION.into();
    state.pending = None;
    save_state(root, &state)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn channels_are_explicit_and_installed_version_determines_identity() {
        assert_eq!(Channel::for_version("1.9.0-beta.12"), Channel::Beta);
        assert_eq!(Channel::for_version("1.9.0"), Channel::Stable);
        assert!(Channel::parse("nightly").is_err());
        assert!(validate_version(Channel::Beta, "1.9.0-beta.12").is_ok());
        for bad in [
            "1.9.0-beta.0",
            "1.9.0-beta.01",
            "1.9.0-beta.gabc",
            "1.9.0-beta.1+gabc",
            "1.9.0",
        ] {
            assert!(validate_version(Channel::Beta, bad).is_err(), "{bad}");
        }
        assert!(validate_version(Channel::Stable, "1.9.0-beta.1").is_err());
    }

    #[test]
    fn legacy_stable_compatibility_and_beta_schema_are_checked() {
        let td = crate::testutil::scratch("update-compatibility");
        std::fs::create_dir_all(&td).unwrap();
        assert!(validate_target(&td, Channel::Stable, "1.8.0", &json!({})).is_ok());
        assert!(validate_target(&td, Channel::Stable, "1.7.2", &json!({})).is_err());
        assert!(validate_target(&td, Channel::Beta, "1.9.0-beta.1", &json!({})).is_err());
        let feed = json!({"channel":"beta", "data_schema":1});
        assert!(validate_target(&td, Channel::Beta, "1.9.0-beta.1", &feed).is_ok());
        assert!(validate_target(
            &td,
            Channel::Beta,
            "1.9.0-beta.1",
            &json!({"channel":"beta", "data_schema":2})
        )
        .is_err());
        save_state(
            &td,
            &State {
                data_schema: 2,
                ..State::default()
            },
        )
        .unwrap();
        assert!(validate_target(&td, Channel::Stable, "1.8.0", &json!({})).is_err());
        let _ = std::fs::remove_dir_all(td);
    }

    #[test]
    fn pending_backup_preserves_new_user_files_and_only_matching_startup_confirms() {
        let td = crate::testutil::scratch("update-pending");
        let ud = paths::user_data(&td);
        std::fs::create_dir_all(ud.join("models")).unwrap();
        std::fs::write(ud.join("app_config.json"), "{\"pitch\":3}").unwrap();
        std::fs::write(ud.join("models/new.pth"), b"user model").unwrap();
        prepare_install(&td, Channel::Beta, "99.0.0-beta.1").unwrap();
        confirm_startup(&td).unwrap();
        assert!(read_state(&td).unwrap().pending.is_some());
        cancel_pending(&td, "99.0.0-beta.1").unwrap();
        assert!(read_state(&td).unwrap().pending.is_none());
        prepare_install(&td, installed(), update::APP_VERSION).unwrap();
        confirm_startup(&td).unwrap();
        assert!(read_state(&td).unwrap().pending.is_none());
        assert_eq!(
            std::fs::read(ud.join("models/new.pth")).unwrap(),
            b"user model"
        );
        assert_eq!(
            std::fs::read_to_string(ud.join("app_config.json")).unwrap(),
            "{\"pitch\":3}"
        );
        assert!(
            std::fs::read_dir(state_dir(&td).join("backups"))
                .unwrap()
                .count()
                >= 2
        );
        let _ = std::fs::remove_dir_all(td);
    }
}
