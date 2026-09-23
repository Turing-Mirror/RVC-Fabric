//! Shared action catalogue; the frontend imports the same JSON at build time.
use serde::{Deserialize, Serialize};
use std::sync::OnceLock;

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
}
