//! 已知问题表：这台机器有没有踩到我们已经知道的坑。
//!
//! 表跟着二进制走（`include_str!`），不是外部文件 —— 安装包少放一个文件就少一
//! 个「用户那份是空的」的可能。
//!
//! 文案不写在表里，只写 key，翻译仍然留在 app/i18n/locales 里那八份语言包。表
//! 里放两套文案等于第二条翻译流水线，而这张表本来就最容易腐烂。
//!
//! 腐烂的另一半靠 `fixed_in` 挡：修好的条目在已修版本上不再显示。改这张表的时
//! 候必须同时填 `fixed_in`，否则半年后它会对着已修版本的用户报旧问题。

use std::path::Path;

use serde::{Deserialize, Serialize};

const TABLE: &str = include_str!("../known_issues.json");

#[derive(Debug, Clone, Deserialize, Default)]
pub struct Affects {
    /// 含下界。空 = 不限。
    #[serde(default)]
    pub version_min: String,
    /// 含上界。空 = 不限。
    #[serde(default)]
    pub version_max: String,
    /// "windows" / "macos" / "linux"。空 = 不限。
    #[serde(default)]
    pub os: String,
    /// status.json 里的 compute_backend，如 "directml"。空 = 不限。
    #[serde(default)]
    pub backend: String,
    /// 显卡名里包含这一段（大小写不敏感）。空 = 不限。
    #[serde(default)]
    pub gpu_contains: String,
    /// 注册过的 ASIO 驱动名里包含这一段（大小写不敏感）。空 = 不限。
    #[serde(default)]
    pub asio_driver: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Entry {
    pub id: String,
    pub title_key: String,
    pub body_key: String,
    #[serde(default = "default_level")]
    pub level: String,
    #[serde(default)]
    pub affects: Affects,
    /// 哪一版修好的。当前版本 >= 它就不再显示。空 = 还没修。
    #[serde(default)]
    pub fixed_in: String,
    /// 只在本会话里 worker 被系统干掉过才报。Realtek ASIO 几乎每台 Windows
    /// 电脑都装着，26.8.24 那台 RTX 3050 引擎跑得好好的仍被这条 error 横幅
    /// 吓到；真正会崩的是少数旧版 rthdasio64.dll，崩过一次再提示才有用。
    #[serde(default)]
    pub requires_fatal: bool,
}

fn default_level() -> String {
    "warn".into()
}

/// 判据要用到的这台机器的事实。全部先取好再匹配，规则本身是纯函数，能测。
#[derive(Debug, Clone, Default)]
pub struct Machine {
    pub version: String,
    pub os: String,
    pub backend: String,
    pub gpus: Vec<String>,
    pub asio: Vec<String>,
    /// 本会话 worker 是否被系统终止过。配合 `requires_fatal`。
    pub saw_fatal: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct Hit {
    pub id: String,
    pub level: String,
    pub title: String,
    pub body: String,
    /// 哪一版修好的，空 = 还没修。界面拿它给「更新到 x.y.z」按钮写版本号。
    /// 能出现在 Hit 里的条目必然满足 当前版本 < fixed_in，所以有值就值得给按钮。
    pub fixed_in: String,
}

fn table() -> Vec<Entry> {
    serde_json::from_str::<Vec<Entry>>(TABLE).unwrap_or_default()
}

fn contains_ci(haystack: &[String], needle: &str) -> bool {
    let n = needle.to_ascii_lowercase();
    haystack.iter().any(|h| h.to_ascii_lowercase().contains(&n))
}

/// 这条已知问题适用于这台机器吗。
pub fn matches(e: &Entry, m: &Machine) -> bool {
    // 修好的不再显示。这条排最前面 —— 其余判据全中也不该报一个已经修掉的问题。
    if !e.fixed_in.is_empty()
        && !m.version.is_empty()
        && crate::update::compare_versions(&m.version, &e.fixed_in) >= 0
    {
        return false;
    }
    let a = &e.affects;
    if !a.version_min.is_empty()
        && crate::update::compare_versions(&m.version, &a.version_min) < 0
    {
        return false;
    }
    if !a.version_max.is_empty()
        && crate::update::compare_versions(&m.version, &a.version_max) > 0
    {
        return false;
    }
    if !a.os.is_empty() && !a.os.eq_ignore_ascii_case(&m.os) {
        return false;
    }
    if !a.backend.is_empty() && !a.backend.eq_ignore_ascii_case(&m.backend) {
        return false;
    }
    if !a.gpu_contains.is_empty() && !contains_ci(&m.gpus, &a.gpu_contains) {
        return false;
    }
    if !a.asio_driver.is_empty() && !contains_ci(&m.asio, &a.asio_driver) {
        return false;
    }
    if e.requires_fatal && !m.saw_fatal {
        return false;
    }
    true
}

pub fn machine(root: &Path) -> Machine {
    let status = crate::protocol::read_status(root);
    Machine {
        version: crate::update::APP_VERSION.to_string(),
        os: std::env::consts::OS.to_string(),
        backend: status
            .get("compute_backend")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        gpus: crate::provision::list_gpus(),
        asio: crate::crash::asio_drivers(),
        saw_fatal: crate::crash::saw_fatal_exit(),
    }
}

pub fn hits(root: &Path) -> Vec<Hit> {
    let m = machine(root);
    table()
        .into_iter()
        .filter(|e| matches(e, &m))
        .map(|e| Hit {
            id: e.id,
            level: e.level,
            title: crate::i18n::t(&e.title_key),
            body: crate::i18n::t(&e.body_key),
            fixed_in: e.fixed_in.clone(),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(json: &str) -> Entry {
        serde_json::from_str(json).unwrap()
    }

    #[test]
    fn the_shipped_table_parses_and_every_entry_has_its_strings() {
        let t = table();
        assert!(!t.is_empty(), "表是空的，include_str! 大概指错了");
        for e in &t {
            assert!(!e.id.is_empty());
            // key 必须在语言包里真的存在，否则界面上会显示 key 本身。
            assert_ne!(crate::i18n::t(&e.title_key), e.title_key, "{} 缺标题", e.id);
            assert_ne!(crate::i18n::t(&e.body_key), e.body_key, "{} 缺正文", e.id);
            assert!(matches!(e.level.as_str(), "error" | "warn" | "info"), "{}", e.id);
        }
    }

    #[test]
    fn a_fixed_entry_never_shows_on_a_fixed_build() {
        let e = entry(
            r#"{"id":"x","title_key":"a","body_key":"b","fixed_in":"1.5.5"}"#,
        );
        let mut m = Machine { version: "1.5.4".into(), ..Default::default() };
        assert!(matches(&e, &m), "还没修的版本要报");
        m.version = "1.5.5".into();
        assert!(!matches(&e, &m), "已修版本不能再报");
        m.version = "1.6.0".into();
        assert!(!matches(&e, &m));
    }

    #[test]
    fn version_bounds_are_inclusive() {
        let e = entry(
            r#"{"id":"x","title_key":"a","body_key":"b",
                "affects":{"version_min":"1.5.0","version_max":"1.5.4"}}"#,
        );
        for (v, want) in [("1.4.9", false), ("1.5.0", true), ("1.5.4", true), ("1.5.5", false)] {
            let m = Machine { version: v.into(), ..Default::default() };
            assert_eq!(matches(&e, &m), want, "{v}");
        }
    }

    #[test]
    fn the_asio_rule_matches_the_driver_name_case_insensitively() {
        let e = entry(
            r#"{"id":"x","title_key":"a","body_key":"b",
                "affects":{"os":"windows","asio_driver":"realtek"}}"#,
        );
        let m = |os: &str, asio: &[&str]| Machine {
            version: "1.5.4".into(),
            os: os.into(),
            asio: asio.iter().map(|s| s.to_string()).collect(),
            ..Default::default()
        };
        // 26.8.21 那位：注册表里就是这个名字。
        assert!(matches(&e, &m("windows", &["Realtek ASIO"])));
        assert!(matches(&e, &m("windows", &["ASIO4ALL v2", "REALTEK ASIO"])));
        // 没装这个驱动的不能报 —— 一条已知问题贴到无关机器上比不报还糟。
        assert!(!matches(&e, &m("windows", &["ASIO4ALL v2"])));
        assert!(!matches(&e, &m("windows", &[])));
        // 系统对不上也不报。
        assert!(!matches(&e, &m("macos", &["Realtek ASIO"])));
    }

    #[test]
    fn a_fatal_only_asio_entry_stays_quiet_until_a_crash() {
        let e = entry(
            r#"{"id":"x","title_key":"a","body_key":"b",
                "affects":{"os":"windows","asio_driver":"realtek"},
                "requires_fatal":true}"#,
        );
        let mut m = Machine {
            version: "1.5.5".into(),
            os: "windows".into(),
            asio: vec!["Realtek ASIO".into()],
            ..Default::default()
        };
        assert!(!matches(&e, &m), "光装着驱动不能报");
        m.saw_fatal = true;
        assert!(matches(&e, &m), "崩过才报");
    }

    #[test]
    fn the_shipped_realtek_entry_does_not_fire_just_because_the_driver_is_installed() {
        let t = table();
        let e = t
            .iter()
            .find(|e| e.id == "realtek-asio-enum-crash")
            .expect("shipped table");
        assert!(
            e.requires_fatal,
            "几乎每台 Windows 都有 Realtek ASIO，开机横幅必须要求先崩过"
        );
    }

    #[test]
    fn an_entry_with_no_conditions_matches_everything() {
        let e = entry(r#"{"id":"x","title_key":"a","body_key":"b"}"#);
        assert!(matches(&e, &Machine { version: "1.5.4".into(), ..Default::default() }));
    }

    /// Hit 要把 fixed_in 带出去 —— 界面上的「更新到 x.y.z」按钮靠它写版本号。
    #[test]
    fn a_hit_carries_the_fix_version_for_the_update_button() {
        let h = Hit {
            id: "x".into(),
            level: "warn".into(),
            title: "t".into(),
            body: "b".into(),
            fixed_in: "1.5.5".into(),
        };
        let v = serde_json::to_value(&h).unwrap();
        assert_eq!(v["fixed_in"], "1.5.5");
    }
}
