//! App settings — `User_Data/app_config.json`, mirrored into
//! `configs/inuse/config.json` for the worker.
//!
//! Ports `launcher/config_store.py` + `launcher/inuse_config.py`. Two rules from
//! the Python shell carry over and must not be dropped:
//!
//! * **`configs/inuse/config.json` must never contain dev-machine absolute
//!   paths.** Shipped builds once leaked `L:\…` and the worker died on user
//!   machines. Anything that looks like an absolute path on another drive is
//!   stripped on write.
//! * **HOT vs COLD.** Hot keys apply to a running stream; cold keys need a
//!   stop + start. The UI has to say which it is instead of silently doing
//!   nothing.

use std::collections::BTreeMap;
use std::path::Path;

use serde_json::{json, Map, Value};

use crate::paths;

/// Applies live while converting (mirrors `realtime_protocol.HOT_KEYS`).
pub const HOT_KEYS: &[&str] = &[
    "pitch",
    "formant",
    "index_rate",
    "rms_mix_rate",
    "threhold",
    "in_gain_db",
    "f0method",
    "I_noise_reduce",
    "O_noise_reduce",
    "use_pv",
    "function",
];

/// Needs stop + start (mirrors `realtime_protocol.COLD_KEYS`).
pub const COLD_KEYS: &[&str] = &[
    "pth_path",
    "index_path",
    "sg_hostapi",
    "sg_wasapi_exclusive",
    "sg_input_device",
    "sg_output_device",
    "sr_type",
    "block_time",
    "crossfade_length",
    "extra_time",
    "n_cpu",
];

/// Keys the worker consumes — only these are mirrored into `inuse`.
fn engine_keys() -> Vec<&'static str> {
    let mut v: Vec<&'static str> = HOT_KEYS.to_vec();
    v.extend_from_slice(COLD_KEYS);
    v
}

pub fn is_hot(key: &str) -> bool {
    HOT_KEYS.contains(&key)
}

pub fn is_cold(key: &str) -> bool {
    COLD_KEYS.contains(&key)
}

/// Product defaults. Values match the Python shell so a user switching over
/// does not silently get different audio.
pub fn defaults() -> Map<String, Value> {
    let mut m = Map::new();
    // voice params (hot)
    m.insert("pitch".into(), json!(0));
    m.insert("formant".into(), json!(0.0));
    m.insert("index_rate".into(), json!(0.75));
    m.insert("rms_mix_rate".into(), json!(0.25));
    m.insert("threhold".into(), json!(-60));
    m.insert("in_gain_db".into(), json!(0.0));
    m.insert("f0method".into(), json!("rmvpe"));
    m.insert("I_noise_reduce".into(), json!(true));
    m.insert("O_noise_reduce".into(), json!(false));
    m.insert("use_pv".into(), json!(false));
    m.insert("function".into(), json!("vc"));
    // model binding (cold) — written by voice selection, not by the settings
    // page, but the worker expects the keys to exist.
    m.insert("pth_path".into(), json!(""));
    m.insert("index_path".into(), json!(""));
    // devices / performance (cold)
    m.insert("sg_hostapi".into(), json!(""));
    m.insert("sg_wasapi_exclusive".into(), json!(false));
    m.insert("sg_input_device".into(), json!(""));
    m.insert("sg_output_device".into(), json!(""));
    m.insert("sr_type".into(), json!("sr_device"));
    m.insert("block_time".into(), json!(0.25));
    m.insert("crossfade_length".into(), json!(0.08));
    m.insert("extra_time".into(), json!(2.5));
    m.insert("n_cpu".into(), json!(4));
    // shell-only
    m.insert("monitor_self".into(), json!(false));
    m.insert("monitor_device".into(), json!(""));
    m.insert("close_action".into(), json!("ask"));
    m.insert("theme_mode".into(), json!("system"));
    m.insert("wallpaper_path".into(), json!(""));
    m.insert("wallpaper_blur".into(), json!(40));
    m.insert("wallpaper_opacity".into(), json!(70));
    m.insert("hotkeys_enabled".into(), json!(false));
    m.insert("telemetry_opt_in".into(), json!(Value::Null));
    m
}

fn read_json(path: &Path) -> Map<String, Value> {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .and_then(|v| v.as_object().cloned())
        .unwrap_or_default()
}

/// Full effective config: defaults overlaid with what the user has saved.
pub fn read(root: &Path) -> Map<String, Value> {
    let mut cfg = defaults();
    for (k, v) in read_json(&paths::app_config_path(root)) {
        cfg.insert(k, v);
    }
    cfg
}

fn write_atomic(path: &Path, text: &str) -> std::io::Result<()> {
    if let Some(p) = path.parent() {
        std::fs::create_dir_all(p)?;
    }
    // Unique temp name: the shell and the worker can both be writing under
    // User_Data, and a fixed `.tmp` was a real source of WinError 5.
    let tmp = path.with_extension(format!(
        "tmp{}",
        std::process::id() as u64
            ^ std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos() as u64)
                .unwrap_or(0)
    ));
    std::fs::write(&tmp, text)?;
    match std::fs::rename(&tmp, path) {
        Ok(()) => Ok(()),
        Err(e) => {
            // Windows can hold the target open; fall back to a direct write
            // rather than losing the user's setting.
            let _ = std::fs::remove_file(&tmp);
            std::fs::write(path, text).map_err(|_| e)
        }
    }
}

/// True when a string looks like an absolute path (drive letter or UNC).
fn looks_absolute(s: &str) -> bool {
    let b = s.as_bytes();
    (b.len() >= 3 && b[1] == b':' && (b[2] == b'\\' || b[2] == b'/'))
        || s.starts_with("\\\\")
        || s.starts_with('/')
}

/// Strip anything that would pin the worker to this machine's layout.
fn sanitize_inuse(root: &Path, m: &mut Map<String, Value>) {
    let root_s = root.to_string_lossy().to_string();
    for key in ["pth_path", "index_path"] {
        let Some(Value::String(p)) = m.get(key).cloned() else {
            continue;
        };
        if !looks_absolute(&p) {
            continue;
        }
        // Keep it only if it is inside this install, and store it relative.
        if let Some(rel) = p.strip_prefix(&root_s) {
            let rel = rel.trim_start_matches(['\\', '/']).to_string();
            m.insert(key.into(), json!(rel));
        } else {
            m.insert(key.into(), json!(""));
        }
    }
}

/// Mirror the engine-relevant subset into `configs/inuse/config.json`.
pub fn sync_inuse(root: &Path, cfg: &Map<String, Value>) -> Result<(), String> {
    let path = paths::inuse_config_path(root);
    let mut out = read_json(&path);
    for k in engine_keys() {
        let Some(v) = cfg.get(k) else { continue };
        // Never let an empty model path overwrite one that is already set:
        // losing pth_path means the worker starts with no model at all.
        if matches!(k, "pth_path" | "index_path")
            && v.as_str().map(str::is_empty).unwrap_or(false)
            && out.get(k).and_then(|x| x.as_str()).map(|s| !s.is_empty()) == Some(true)
        {
            continue;
        }
        out.insert(k.to_string(), v.clone());
    }
    sanitize_inuse(root, &mut out);
    let text = serde_json::to_string_pretty(&Value::Object(out)).map_err(|e| e.to_string())?;
    write_atomic(&path, &text).map_err(|e| format!("写入 inuse 配置失败：{e}"))
}

/// Merge `patch` into the saved config; returns the new effective config plus
/// which keys need a restart of the stream to take effect.
pub fn update(root: &Path, patch: Map<String, Value>) -> Result<Value, String> {
    let mut saved = read_json(&paths::app_config_path(root));
    let mut hot = Map::new();
    let mut needs_restart: Vec<String> = Vec::new();
    let mut touched_engine = false;

    for (k, v) in patch {
        if is_hot(&k) {
            hot.insert(k.clone(), v.clone());
            touched_engine = true;
        } else if is_cold(&k) {
            needs_restart.push(k.clone());
            touched_engine = true;
        }
        saved.insert(k, v);
    }

    let text = serde_json::to_string_pretty(&Value::Object(saved)).map_err(|e| e.to_string())?;
    write_atomic(&paths::app_config_path(root), &text)
        .map_err(|e| format!("保存设置失败：{e}"))?;

    let cfg = read(root);
    // Only touch the engine's config file when an engine key actually changed.
    // The worker may be reading it, and theme / wallpaper / telemetry writes
    // have no business rewriting it.
    if touched_engine {
        sync_inuse(root, &cfg)?;
    }

    Ok(json!({
        "config": Value::Object(cfg),
        "hot": Value::Object(hot),
        "needs_restart": needs_restart,
    }))
}

/// Key holding dismissed models-page banner ids. Not a settings key: it never
/// appears in the settings UI and must not reach the engine's config.
const DISMISSED_ADS: &str = "dismissed_ads";
/// Cap so a long-lived install cannot grow this list without bound.
const DISMISSED_MAX: usize = 200;

pub fn dismissed_ads(root: &Path) -> Vec<String> {
    read_json(&paths::app_config_path(root))
        .get(DISMISSED_ADS)
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|x| x.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default()
}

pub fn dismiss_ad(root: &Path, id: &str) -> Result<(), String> {
    if id.is_empty() {
        return Ok(());
    }
    let mut saved = read_json(&paths::app_config_path(root));
    let mut list = dismissed_ads(root);
    if list.iter().any(|x| x == id) {
        return Ok(());
    }
    list.push(id.to_string());
    // Oldest out first: a banner from two years ago will not come back.
    if list.len() > DISMISSED_MAX {
        let drop = list.len() - DISMISSED_MAX;
        list.drain(..drop);
    }
    saved.insert(DISMISSED_ADS.into(), json!(list));
    let text = serde_json::to_string_pretty(&Value::Object(saved)).map_err(|e| e.to_string())?;
    // Deliberately no sync_inuse: this is not an engine key.
    write_atomic(&paths::app_config_path(root), &text)
        .map_err(|e| format!("保存失败：{e}"))
}

/// Grouped view used by the settings page, so the UI does not hard-code which
/// keys belong to which tab.
pub fn describe() -> Value {
    let mut groups: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    groups.insert(
        "devices",
        vec![
            "sg_hostapi",
            "sg_input_device",
            "in_gain_db",
            "sg_output_device",
            "monitor_self",
            "monitor_device",
            "sg_wasapi_exclusive",
            "sr_type",
        ],
    );
    groups.insert(
        "voice",
        vec![
            "threhold",
            "pitch",
            "formant",
            "index_rate",
            "rms_mix_rate",
            "f0method",
        ],
    );
    groups.insert(
        "perf",
        vec!["block_time", "crossfade_length", "extra_time", "n_cpu"],
    );
    groups.insert("fx", vec!["I_noise_reduce", "O_noise_reduce", "use_pv"]);
    groups.insert(
        "appearance",
        vec!["theme_mode", "wallpaper_path", "wallpaper_blur", "wallpaper_opacity"],
    );
    groups.insert("general", vec!["close_action", "telemetry_opt_in"]);
    json!({
        "groups": groups,
        "hot": HOT_KEYS,
        "cold": COLD_KEYS,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hot_and_cold_do_not_overlap() {
        for k in HOT_KEYS {
            assert!(!COLD_KEYS.contains(k), "{k} in both sets");
        }
    }

    #[test]
    fn absolute_paths_are_detected() {
        assert!(looks_absolute("L:\\My Project\\a.pth"));
        assert!(looks_absolute("C:/x/y.index"));
        assert!(looks_absolute("\\\\server\\share\\a"));
        assert!(!looks_absolute("User_Data/models/anon/a.pth"));
        assert!(!looks_absolute(""));
    }

    #[test]
    fn inuse_strips_foreign_absolute_paths() {
        let root = Path::new("C:\\App");
        let mut m = Map::new();
        m.insert("pth_path".into(), json!("L:\\dev\\anon.pth"));
        m.insert("index_path".into(), json!("C:\\App\\User_Data\\a.index"));
        sanitize_inuse(root, &mut m);
        assert_eq!(m["pth_path"], json!(""));
        assert_eq!(m["index_path"], json!("User_Data\\a.index"));
    }

    #[test]
    fn empty_model_path_never_clobbers_a_real_one() {
        // The shell rewrites inuse from app_config at startup. If app_config
        // has not caught up yet, an empty pth_path must not wipe the model the
        // worker is actually using.
        let root = std::env::temp_dir().join("rvcf-inuse-guard");
        let inuse = root.join("configs").join("inuse");
        std::fs::create_dir_all(&inuse).unwrap();
        std::fs::write(
            inuse.join("config.json"),
            r#"{"pth_path":"User_Data/models/anon/anon.pth","index_path":"a.index"}"#,
        )
        .unwrap();

        let mut cfg = defaults(); // pth_path / index_path default to ""
        cfg.insert("pitch".into(), json!(5));
        sync_inuse(&root, &cfg).unwrap();

        let after = read_json(&paths::inuse_config_path(&root));
        assert_eq!(
            after["pth_path"], json!("User_Data/models/anon/anon.pth"),
            "empty default must not clear the selected model"
        );
        assert_eq!(after["pitch"], json!(5), "other keys still sync");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn defaults_cover_every_engine_key() {
        let d = defaults();
        for k in engine_keys() {
            assert!(d.contains_key(k), "default missing for {k}");
        }
    }
}
