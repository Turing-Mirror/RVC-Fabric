//! Shell-side i18n — same JSON packs as the React UI (`app/i18n/locales`).
//!
//! Load order: product_root/i18n/locales/{code}.json → embedded zh-CN fallback.
//! Keys use dotted paths: `tray.show`, `msg.engine.starting`.

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use serde_json::Value;

use crate::paths;

const EMBEDDED_ZH_CN: &str = include_str!("../../i18n/locales/zh-CN.json");
const EMBEDDED_EN_US: &str = include_str!("../../i18n/locales/en-US.json");
const EMBEDDED_ES_ES: &str = include_str!("../../i18n/locales/es-ES.json");
const EMBEDDED_FR_FR: &str = include_str!("../../i18n/locales/fr-FR.json");
const EMBEDDED_JA_JP: &str = include_str!("../../i18n/locales/ja-JP.json");
const EMBEDDED_KO_KR: &str = include_str!("../../i18n/locales/ko-KR.json");
const EMBEDDED_RU_RU: &str = include_str!("../../i18n/locales/ru-RU.json");
const EMBEDDED_ZH_TW: &str = include_str!("../../i18n/locales/zh-TW.json");

struct I18nState {
    locale: String,
    cache: Option<(String, Value)>,
}

static STATE: Mutex<I18nState> = Mutex::new(I18nState {
    locale: String::new(),
    cache: None,
});

fn default_locale() -> String {
    "zh-CN".into()
}

pub fn supported(code: &str) -> bool {
    matches!(
        code,
        "zh-CN" | "en-US" | "es-ES" | "fr-FR" | "ja-JP" | "ko-KR" | "ru-RU" | "zh-TW"
    )
}

/// Current locale (from config or last set). Empty until init.
pub fn current() -> String {
    let g = STATE.lock().unwrap_or_else(|e| e.into_inner());
    if g.locale.is_empty() {
        default_locale()
    } else {
        g.locale.clone()
    }
}

/// Load locale from app config (call early in run()).
pub fn init_from_config(root: &Path) {
    let cfg = crate::config::read(root);
    let code = cfg
        .get("ui_locale")
        .and_then(|v| v.as_str())
        .unwrap_or("zh-CN");
    set_locale(if supported(code) {
        code
    } else {
        "zh-CN"
    });
}

pub fn set_locale(code: &str) {
    let code = if supported(code) {
        code.to_string()
    } else {
        default_locale()
    };
    let mut g = STATE.lock().unwrap_or_else(|e| e.into_inner());
    g.locale = code;
    g.cache = None;
}

fn locales_dir(root: &Path) -> PathBuf {
    // Must not use product `i18n/` — that path is the upstream Gradio locale tree
    // shipped in engine-payload. Shell packs live under shell-i18n/ (install) or
    // app/i18n/locales (dev tree).
    for cand in [
        root.join("shell-i18n").join("locales"),
        root.join("app").join("i18n").join("locales"),
        // tauri dev: cwd may be app/
        root.join("i18n").join("locales"),
    ] {
        if cand.is_dir() {
            return cand;
        }
    }
    root.join("shell-i18n").join("locales")
}

fn embedded(code: &str) -> Value {
    let raw = match code {
        "en-US" => EMBEDDED_EN_US,
        "es-ES" => EMBEDDED_ES_ES,
        "fr-FR" => EMBEDDED_FR_FR,
        "ja-JP" => EMBEDDED_JA_JP,
        "ko-KR" => EMBEDDED_KO_KR,
        "ru-RU" => EMBEDDED_RU_RU,
        "zh-TW" => EMBEDDED_ZH_TW,
        _ => EMBEDDED_ZH_CN,
    };
    serde_json::from_str(raw).unwrap_or_else(|_| Value::Object(Default::default()))
}

fn load_file(root: &Path, code: &str) -> Option<Value> {
    let path = locales_dir(root).join(format!("{code}.json"));
    let text = fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}

fn pack() -> Value {
    let mut g = STATE.lock().unwrap_or_else(|e| e.into_inner());
    let code = if g.locale.is_empty() {
        default_locale()
    } else {
        g.locale.clone()
    };
    if let Some((c, v)) = g.cache.as_ref() {
        if c == &code {
            return v.clone();
        }
    }
    // Prefer embedded packs in tests / missing install layout so locale is
    // deterministic. Disk override only when a shell-i18n tree exists.
    let root = paths::product_root();
    let v = load_file(&root, &code).unwrap_or_else(|| embedded(&code));
    g.cache = Some((code, v.clone()));
    v
}

fn lookup(v: &Value, key: &str) -> Option<String> {
    // Prefer dotted path segments (msg.engine.starting → obj.msg.engine.starting,
    // s.ab12cd → obj.s.ab12cd). Also try the remainder as a single key.
    let parts: Vec<&str> = key.split('.').filter(|p| !p.is_empty()).collect();
    if parts.is_empty() {
        return None;
    }
    let mut cur = v;
    for (i, part) in parts.iter().enumerate() {
        if let Some(next) = cur.get(*part) {
            cur = next;
            continue;
        }
        let rest = parts[i..].join(".");
        cur = cur.get(&rest)?;
        break;
    }
    cur.as_str().map(|s| s.to_string())
}

fn interpolate(template: &str, vars: &HashMap<String, String>) -> String {
    let mut out = template.to_string();
    for (k, val) in vars {
        out = out.replace(&format!("{{{k}}}"), val);
        out = out.replace(&format!("${{{k}}}"), val);
    }
    out
}

/// Translate a dotted key. Falls back to embedded zh-CN, then the key itself.
pub fn t(key: &str) -> String {
    t_vars(key, &HashMap::new())
}

pub fn t_vars(key: &str, vars: &HashMap<String, String>) -> String {
    let primary = pack();
    if let Some(s) = lookup(&primary, key) {
        return interpolate(&s, vars);
    }
    let zh = embedded("zh-CN");
    if let Some(s) = lookup(&zh, key) {
        return interpolate(&s, vars);
    }
    key.to_string()
}

/// Single display arg: replaces {e}, {a0}, and first {}.
pub fn te(key: &str, e: &impl std::fmt::Display) -> String {
    let v = e.to_string();
    t(key)
        .replace("{e}", &v)
        .replace("{a0}", &v)
        .replacen("{}", &v, 1)
}

/// Two display args: {a0}/{a1} or first two {}.
pub fn t2(key: &str, a0: &impl std::fmt::Display, a1: &impl std::fmt::Display) -> String {
    let v0 = a0.to_string();
    let v1 = a1.to_string();
    let mut s = t(key).replace("{a0}", &v0).replace("{a1}", &v1);
    s = s.replacen("{}", &v0, 1);
    s = s.replacen("{}", &v1, 1);
    s
}

/// N display args: replace `{a0}`… then remaining `{}` left-to-right.
pub fn tn(key: &str, args: &[&str]) -> String {
    let mut s = t(key);
    for (i, a) in args.iter().enumerate() {
        s = s.replace(&format!("{{a{i}}}"), a);
    }
    for a in args {
        s = s.replacen("{}", a, 1);
    }
    s
}

/// Resolve `message_code` from status.json (e.g. `engine.starting` → msg.engine.starting).
#[allow(dead_code)] // used by status localization & future command errors
pub fn t_msg(code: &str) -> String {
    if code.is_empty() {
        return String::new();
    }
    let key = if code.starts_with("msg.") {
        code.to_string()
    } else {
        format!("msg.{code}")
    };
    t(&key)
}

/// If status has message_code, replace message with localized string.
pub fn localize_status(status: &mut Value) {
    let code = status
        .get("message_code")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    if code.is_empty() {
        return;
    }
    let mut vars = HashMap::new();
    if let Some(obj) = status.get("message_params").and_then(|v| v.as_object()) {
        for (k, v) in obj {
            let s = match v {
                Value::String(s) => s.clone(),
                Value::Number(n) => n.to_string(),
                Value::Bool(b) => b.to_string(),
                _ => continue,
            };
            vars.insert(k.clone(), s);
        }
    }
    let key = if code.starts_with("msg.") {
        code.clone()
    } else {
        format!("msg.{code}")
    };
    let text = t_vars(&key, &vars);
    if text != key {
        if let Some(obj) = status.as_object_mut() {
            obj.insert("message".into(), Value::String(text));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    // Global STATE is process-wide; serialize these tests.
    static TEST_LOCK: Mutex<()> = Mutex::new(());

    #[test]
    fn tray_and_msg_locales() {
        let _g = TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());

        set_locale("zh-CN");
        assert_eq!(t("tray.show"), "打开主界面");
        assert_eq!(t("tray.quit"), "退出");
        assert!(
            t_msg("engine.starting").contains("加载"),
            "got {:?}",
            t_msg("engine.starting")
        );

        set_locale("en-US");
        assert_eq!(t("tray.show"), "Open main window");
        assert!(
            t_msg("engine.starting").to_ascii_lowercase().contains("load"),
            "got {:?}",
            t_msg("engine.starting")
        );

        // Non-English packs must resolve (embedded), not fall back to the key.
        for code in ["ja-JP", "zh-TW", "es-ES", "fr-FR", "ko-KR", "ru-RU"] {
            set_locale(code);
            let s = t("tray.show");
            assert!(!s.is_empty() && s != "tray.show", "{code}: {s}");
            assert!(supported(code), "{code} should be supported");
        }
    }
}
