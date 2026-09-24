//! Shared action catalogue; the frontend imports the same JSON at build time.
use serde::{Deserialize, Serialize};
use std::{collections::HashSet, path::Path, sync::{Mutex, OnceLock}};
use tauri_plugin_global_shortcut::Shortcut;

/// Serializes full-list edits with source deletion so a stale editor cannot
/// restore a binding to an entry that was just removed.
pub static WRITE_LOCK: Mutex<()> = Mutex::new(());

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct LegacyHotkey {
    pub key: String,
    pub action: String,
    pub fallback: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct AudioAction {
    pub action: String,
    pub requires_entry: bool,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct HotkeyCatalog {
    pub legacy: Vec<LegacyHotkey>,
    pub audio_actions: Vec<AudioAction>,
}

pub fn catalog() -> &'static HotkeyCatalog {
    static CATALOG: OnceLock<HotkeyCatalog> = OnceLock::new();
    CATALOG.get_or_init(|| {
        serde_json::from_str(include_str!("../../shared/hotkeys.json"))
            .expect("bundled hotkey catalogue is valid")
    })
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum HotkeyScope {
    Global,
    Window,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct AudioBinding {
    pub binding_id: String,
    pub action: String,
    pub target_entry_id: Option<String>,
    pub combo: String,
    pub scope: HotkeyScope,
    pub enabled: bool,
    pub mode: Option<String>,
}

pub fn validate_bindings(bindings: &[AudioBinding]) -> Result<(), String> {
    let mut ids = HashSet::new();
    let mut combos = HashSet::new();
    for binding in bindings {
        if binding.binding_id.trim().is_empty() || !ids.insert(binding.binding_id.as_str()) {
            return Err("audio_hotkey_id_invalid".into());
        }
        let action = catalog()
            .audio_actions
            .iter()
            .find(|spec| spec.action == binding.action)
            .ok_or("audio_hotkey_action_invalid")?;
        if action.requires_entry
            && binding
                .target_entry_id
                .as_ref()
                .is_none_or(|id| id.trim().is_empty())
        {
            return Err("audio_hotkey_entry_missing".into());
        }
        if !matches!(
            binding.mode.as_deref().unwrap_or("replace"),
            "replace" | "overlay"
        ) {
            return Err("audio_hotkey_mode_invalid".into());
        }
        if !binding.combo.trim().is_empty() {
            let combo = binding.combo.parse::<Shortcut>()
                .map_err(|_| "audio_hotkey_combo_invalid")?;
            if binding.enabled && !combos.insert(combo.id()) {
                return Err("audio_hotkey_conflict".into());
            }
        }
    }
    Ok(())
}

pub fn read_bindings(root: &Path) -> Result<Vec<AudioBinding>, String> {
    let value = crate::config::read(root)
        .get("audio_hotkeys")
        .cloned()
        .unwrap_or_else(|| serde_json::json!([]));
    let bindings: Vec<AudioBinding> =
        serde_json::from_value(value).map_err(|_| "audio_hotkey_config_invalid")?;
    validate_bindings(&bindings)?;
    Ok(bindings)
}

pub fn validate_entry_targets<'a>(
    bindings: &[AudioBinding],
    entry_ids: impl IntoIterator<Item = &'a str>,
) -> Result<(), String> {
    let known: HashSet<_> = entry_ids.into_iter().collect();
    if bindings.iter().any(|binding| {
        binding.action == "play-entry"
            && binding.target_entry_id.as_deref().is_none_or(|id| !known.contains(id))
    }) {
        return Err("audio_hotkey_entry_missing".into());
    }
    Ok(())
}

pub fn without_deleted_entries<'a>(
    bindings: Vec<AudioBinding>,
    entry_ids: impl IntoIterator<Item = &'a str>,
) -> Vec<AudioBinding> {
    let known: HashSet<_> = entry_ids.into_iter().collect();
    bindings.into_iter().filter(|binding| {
        binding.action != "play-entry"
            || binding.target_entry_id.as_deref().is_some_and(|id| known.contains(id))
    }).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn catalogue_has_unique_actions_and_preserves_legacy_defaults() {
        let catalog = catalog();
        let first: Vec<_> = catalog
            .legacy
            .iter()
            .take(4)
            .map(|h| h.fallback.as_str())
            .collect();
        assert_eq!(
            first,
            [
                "CmdOrCtrl+F2",
                "CmdOrCtrl+F3",
                "CmdOrCtrl+F5",
                "CmdOrCtrl+F6"
            ]
        );
        let mut actions: Vec<_> = catalog
            .legacy
            .iter()
            .map(|h| h.action.as_str())
            .chain(catalog.audio_actions.iter().map(|h| h.action.as_str()))
            .collect();
        let count = actions.len();
        actions.sort_unstable();
        actions.dedup();
        assert_eq!(actions.len(), count);
    }

    #[test]
    fn audio_bindings_are_dynamic_and_allow_explicitly_unbound_rows() {
        let one = AudioBinding {
            binding_id: "one".into(),
            action: "play-entry".into(),
            target_entry_id: Some("entry-1".into()),
            combo: String::new(),
            scope: HotkeyScope::Window,
            enabled: true,
            mode: Some("overlay".into()),
        };
        assert!(validate_bindings(&[one.clone()]).is_ok());
        assert!(validate_bindings(&[one.clone(), one.clone()]).is_err());
        assert!(validate_bindings(&[
            AudioBinding { combo: "Numpad7".into(), ..one.clone() },
            AudioBinding { binding_id: "two".into(), combo: "Num7".into(), ..one.clone() },
        ]).is_err());
        assert!(validate_bindings(&[AudioBinding { combo: "Ctrl++A".into(), ..one.clone() }]).is_err());
        for combo in ["Numpad7", "ArrowLeft", "PageDown", "F24", "MediaPlayPause"] {
            assert!(validate_bindings(&[AudioBinding { combo: combo.into(), ..one.clone() }]).is_ok(), "{combo}");
        }
        assert!(validate_bindings(&[AudioBinding {
            target_entry_id: None,
            ..one
        }])
        .is_err());
    }

    #[test]
    fn deleted_entry_pruning_keeps_other_actions_and_surviving_targets() {
        let make = |id: &str, action: &str, target: Option<&str>| AudioBinding {
            binding_id: id.into(), action: action.into(),
            target_entry_id: target.map(str::to_owned), combo: String::new(),
            scope: HotkeyScope::Window, enabled: true, mode: None,
        };
        let bindings = vec![
            make("gone", "play-entry", Some("entry-1")),
            make("kept", "play-entry", Some("entry-2")),
            make("stop", "stop-preview", None),
        ];
        assert!(validate_entry_targets(&bindings, ["entry-2"]).is_err());
        let kept = without_deleted_entries(bindings, ["entry-2"]);
        assert_eq!(kept.iter().map(|binding| binding.binding_id.as_str()).collect::<Vec<_>>(),
            ["kept", "stop"]);
        assert!(validate_entry_targets(&kept, ["entry-2"]).is_ok());
    }
}
