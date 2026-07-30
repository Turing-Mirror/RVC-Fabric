//! Plaza feed and changelog — the client-side parser.
//!
//! Ported from `launcher/online/plaza.py` + `changelog.py`. This is now the
//! authoritative parser, and `scripts/build_catalog.py` validates its output
//! against it (the "loopback" check) by invoking the `catalog-check` binary.
//!
//! Two product rules are enforced here rather than left to the feed:
//!
//! * **Ads are identifiable.** `ad` / `sponsor`, or any entry with a sponsor
//!   name, is flagged so the UI must badge it.
//! * **Images come from CNB only.** Foreign image hosts are dropped — the
//!   supply chain stays ours.
//!
//! Dismissibility is decided by *placement*, not by type: the plaza itself
//! exists to carry ads and they are not dismissible there; the models page may
//! carry one unobtrusive banner and that one is.

use serde::Serialize;
use serde_json::Value;

use crate::update::compare_versions;

pub const KNOWN_TYPES: &[&str] = &["news", "notice", "banner", "ad", "sponsor"];
pub const AD_TYPES: &[&str] = &["ad", "sponsor"];

pub const PLACEMENT_PLAZA: &str = "plaza";
pub const PLACEMENT_MODELS: &str = "models_page";

const CNB_RAW_MAIN: &str =
    "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main";

#[derive(Debug, Clone, Serialize, Default)]
pub struct PlazaItem {
    pub id: String,
    #[serde(rename = "type")]
    pub kind: String,
    pub title: String,
    pub body: String,
    pub image_url: String,
    pub url: String,
    pub action_label: String,
    pub date: String,
    pub priority: i64,
    pub pinned: bool,
    pub dismissible: bool,
    pub placements: Vec<String>,
    pub start: String,
    pub end: String,
    pub min_app_version: String,
    pub max_app_version: String,
    pub sponsor: String,
    /// True when the UI must show an ad badge.
    pub is_ad: bool,
}

fn s(v: Option<&Value>) -> String {
    v.and_then(|x| x.as_str()).unwrap_or("").trim().to_string()
}

fn first(d: &Value, keys: &[&str]) -> String {
    for k in keys {
        let got = s(d.get(*k));
        if !got.is_empty() {
            return got;
        }
    }
    String::new()
}

/// `YYMMDD`, tolerant of `YYYY-MM-DD` / `YYYYMMDD` / `YY-MM-DD`.
pub fn normalize_yymmdd(raw: &str) -> String {
    let digits: String = raw.chars().filter(|c| c.is_ascii_digit()).collect();
    match digits.len() {
        6 => digits,
        8 => digits[2..].to_string(),
        _ => String::new(),
    }
}

/// Click-through URLs are http/https only.
fn safe_link(url: &str) -> String {
    let u = url.trim();
    let lower = u.to_ascii_lowercase();
    if lower.starts_with("http://") || lower.starts_with("https://") {
        u.to_string()
    } else {
        String::new()
    }
}

/// CNB-only image policy: relative path → raw URL; foreign hosts dropped.
fn resolve_image_url(image: &str) -> String {
    let s = image.trim();
    if s.is_empty() {
        return String::new();
    }
    let lower = s.to_ascii_lowercase();
    if lower.starts_with("http://") || lower.starts_with("https://") {
        let host = lower
            .split("//")
            .nth(1)
            .and_then(|rest| rest.split(['/', '?', '#']).next())
            .map(|h| h.split('@').next_back().unwrap_or(h))
            .map(|h| h.split(':').next().unwrap_or(h))
            .unwrap_or("")
            .to_string();
        if host == "cnb.cool" || host.ends_with(".cnb.cool") {
            return s.to_string();
        }
        return String::new();
    }
    let rel = s.replace('\\', "/");
    format!("{CNB_RAW_MAIN}/{}", rel.trim_start_matches('/'))
}

impl PlazaItem {
    /// Tolerant parse; `None` when the entry is unusable (no id or no title).
    pub fn from_value(d: &Value) -> Option<Self> {
        if !d.is_object() {
            return None;
        }
        let id = s(d.get("id"));
        let title = s(d.get("title"));
        if id.is_empty() || title.is_empty() {
            return None;
        }
        let kind = {
            let k = first(d, &["type", "kind"]).to_ascii_lowercase();
            if k.is_empty() { "news".to_string() } else { k }
        };

        let mut placements: Vec<String> = match d.get("placements").or_else(|| d.get("placement")) {
            Some(Value::String(x)) => vec![x.trim().to_string()],
            Some(Value::Array(a)) => a
                .iter()
                .filter_map(|v| v.as_str().map(|x| x.trim().to_string()))
                .filter(|x| !x.is_empty())
                .collect(),
            _ => vec![],
        };
        if placements.is_empty() {
            placements.push(PLACEMENT_PLAZA.to_string());
        }

        let priority = d
            .get("priority")
            .or_else(|| d.get("weight"))
            .and_then(|v| v.as_i64().or_else(|| v.as_str().and_then(|s| s.parse().ok())))
            .unwrap_or(0);

        let sponsor = first(d, &["sponsor", "advertiser"]);
        let is_ad = AD_TYPES.contains(&kind.as_str()) || !sponsor.is_empty();

        // Placement decides dismissibility. The plaza exists to carry ads and
        // they are not dismissible there; the models-page banner always is.
        let on_models = placements.iter().any(|p| p == PLACEMENT_MODELS);
        let dismissible = if on_models {
            true
        } else {
            d.get("dismissible").and_then(|v| v.as_bool()).unwrap_or(false)
        };

        Some(Self {
            id,
            kind,
            title,
            body: first(d, &["body", "text", "desc"]),
            image_url: resolve_image_url(&first(d, &["image", "image_url", "cover"])),
            url: safe_link(&first(d, &["url", "link"])),
            action_label: first(d, &["action_label", "action"]),
            date: normalize_yymmdd(&first(d, &["date", "released"])),
            priority,
            pinned: d.get("pinned").and_then(|v| v.as_bool()).unwrap_or(false),
            dismissible,
            placements,
            start: normalize_yymmdd(&s(d.get("start"))),
            end: normalize_yymmdd(&s(d.get("end"))),
            min_app_version: s(d.get("min_app_version")),
            max_app_version: s(d.get("max_app_version")),
            sponsor,
            is_ad,
        })
    }
}

/// Parse a feed payload: `{items: [...]}` or a bare list.
pub fn parse_feed(data: &Value) -> Vec<PlazaItem> {
    let rows = match data {
        Value::Object(_) => data.get("items").cloned().unwrap_or(Value::Array(vec![])),
        Value::Array(_) => data.clone(),
        _ => Value::Array(vec![]),
    };
    rows.as_array()
        .map(|a| a.iter().filter_map(PlazaItem::from_value).collect())
        .unwrap_or_default()
}

/// Sort helper: map digits 0↔9 so an ascending sort puts newer dates first.
fn date_desc(date: &str) -> String {
    if date.is_empty() {
        return "999999".into(); // undated sinks below any real date
    }
    date.chars()
        .map(|c| char::from(b'9' - (c as u8 - b'0')))
        .collect()
}

/// Items visible at `placement` for this app version, on this day.
pub fn visible_items(
    items: &[PlazaItem],
    placement: &str,
    app_version: &str,
    today: &str,
    dismissed: &[String],
) -> Vec<PlazaItem> {
    let mut out: Vec<PlazaItem> = items
        .iter()
        .filter(|it| KNOWN_TYPES.contains(&it.kind.as_str()))
        .filter(|it| it.placements.iter().any(|p| p == placement))
        .filter(|it| it.start.is_empty() || today >= it.start.as_str())
        .filter(|it| it.end.is_empty() || today <= it.end.as_str())
        .filter(|it| {
            it.min_app_version.is_empty()
                || compare_versions(app_version, &it.min_app_version) >= 0
        })
        .filter(|it| {
            it.max_app_version.is_empty()
                || compare_versions(app_version, &it.max_app_version) <= 0
        })
        .filter(|it| !(it.dismissible && dismissed.iter().any(|d| d == &it.id)))
        .cloned()
        .collect();

    out.sort_by(|a, b| {
        (!a.pinned, -a.priority, date_desc(&a.date), a.id.clone()).cmp(&(
            !b.pinned,
            -b.priority,
            date_desc(&b.date),
            b.id.clone(),
        ))
    });
    out
}

/// Models-page banner: at most one, and it must be dismissible.
pub fn pick_models_banner(
    items: &[PlazaItem],
    app_version: &str,
    today: &str,
    dismissed: &[String],
) -> Option<PlazaItem> {
    visible_items(items, PLACEMENT_MODELS, app_version, today, dismissed)
        .into_iter()
        .find(|it| it.dismissible)
}

// ---------------------------------------------------------------------------
// Changelog
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Default)]
pub struct ChangelogEntry {
    pub version: String,
    pub date: String,
    pub title: String,
    pub notes: Vec<String>,
}

/// Parse `changelog.json`; newest first, unusable rows dropped.
pub fn parse_changelog(data: &Value) -> Vec<ChangelogEntry> {
    let rows = data
        .get("entries")
        .or_else(|| data.get("items"))
        .cloned()
        .unwrap_or(Value::Array(vec![]));
    let mut out: Vec<ChangelogEntry> = rows
        .as_array()
        .map(|a| {
            a.iter()
                .filter_map(|d| {
                    let version = s(d.get("version"));
                    if version.is_empty() {
                        return None;
                    }
                    let notes = d
                        .get("notes")
                        .or_else(|| d.get("items"))
                        .and_then(|v| v.as_array())
                        .map(|a| {
                            a.iter()
                                .filter_map(|x| x.as_str().map(|s| s.trim().to_string()))
                                .filter(|s| !s.is_empty())
                                .collect()
                        })
                        .unwrap_or_default();
                    Some(ChangelogEntry {
                        version,
                        date: normalize_yymmdd(&first(d, &["date", "released"])),
                        title: s(d.get("title")),
                        notes,
                    })
                })
                .collect()
        })
        .unwrap_or_default();
    out.sort_by(|a, b| compare_versions(&b.version, &a.version).cmp(&0));
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn drops_entries_without_id_or_title() {
        let feed = json!({"items": [
            {"id": "a", "title": "A"},
            {"id": "", "title": "B"},
            {"id": "c"},
        ]});
        let items = parse_feed(&feed);
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].id, "a");
    }

    #[test]
    fn foreign_image_hosts_are_dropped() {
        assert_eq!(resolve_image_url("https://evil.example/x.jpg"), "");
        assert_eq!(
            resolve_image_url("https://cnb.cool/a/b.jpg"),
            "https://cnb.cool/a/b.jpg"
        );
        assert!(resolve_image_url("plaza/a.jpg").starts_with(CNB_RAW_MAIN));
    }

    #[test]
    fn non_http_links_are_dropped() {
        assert_eq!(safe_link("javascript:alert(1)"), "");
        assert_eq!(safe_link("file:///etc/passwd"), "");
        assert_eq!(safe_link("https://x.example"), "https://x.example");
    }

    #[test]
    fn plaza_ads_are_not_dismissible_models_banner_is() {
        let feed = json!({"items": [
            {"id": "p", "title": "广场广告", "type": "ad"},
            {"id": "m", "title": "模型页横幅", "type": "ad",
             "placements": ["models_page"]},
        ]});
        let items = parse_feed(&feed);
        let plaza = items.iter().find(|i| i.id == "p").unwrap();
        let models = items.iter().find(|i| i.id == "m").unwrap();
        assert!(plaza.is_ad && !plaza.dismissible, "广场广告不可关闭");
        assert!(models.is_ad && models.dismissible, "模型页横幅必须可关闭");
    }

    #[test]
    fn schedule_window_and_version_gate() {
        let feed = json!({"items": [
            {"id": "past", "title": "过期", "end": "260101"},
            {"id": "future", "title": "未开始", "start": "991231"},
            {"id": "old", "title": "旧客户端", "max_app_version": "1.0.0"},
            {"id": "ok", "title": "可见"},
        ]});
        let items = parse_feed(&feed);
        let vis = visible_items(&items, PLACEMENT_PLAZA, "1.3.0", "260730", &[]);
        let ids: Vec<&str> = vis.iter().map(|i| i.id.as_str()).collect();
        assert_eq!(ids, vec!["ok"]);
    }

    #[test]
    fn pinned_then_priority_then_newest() {
        let feed = json!({"items": [
            {"id": "c", "title": "c", "date": "260101"},
            {"id": "b", "title": "b", "priority": 5},
            {"id": "a", "title": "a", "pinned": true},
            {"id": "d", "title": "d", "date": "260730"},
        ]});
        let items = parse_feed(&feed);
        let vis = visible_items(&items, PLACEMENT_PLAZA, "1.3.0", "260730", &[]);
        let ids: Vec<&str> = vis.iter().map(|i| i.id.as_str()).collect();
        assert_eq!(ids, vec!["a", "b", "d", "c"]);
    }

    #[test]
    fn changelog_is_newest_first() {
        let data = json!({"entries": [
            {"version": "1.2.4", "notes": ["x"]},
            {"version": "1.3.0", "notes": ["y"]},
            {"version": "", "notes": ["dropped"]},
        ]});
        let rows = parse_changelog(&data);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].version, "1.3.0");
    }

    #[test]
    fn yymmdd_normalisation() {
        assert_eq!(normalize_yymmdd("2026-07-30"), "260730");
        assert_eq!(normalize_yymmdd("260730"), "260730");
        assert_eq!(normalize_yymmdd("nope"), "");
    }
}
