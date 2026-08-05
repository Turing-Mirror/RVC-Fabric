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

/// 广场顶部「置顶」那一排最多放几个。
///
/// 五个是排版定的，不是随手取的：置顶区和模型页用同一套卡片，默认窗口下一行
/// 正好五张。多出来的一张会换行，一排变两排，「置顶」就从一条横幅变成了一个
/// 列表 —— 那样它和下面的「投放」就没区别了，置顶也就不成其为置顶。
///
/// 清单里标了六个以上也不会报错：排序在前的五个进置顶区，其余的照常留在
/// 「投放」里。发布侧 `build_catalog.py` 会先警告一次。
pub const MAX_PINNED: usize = 5;

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
    /// 置顶卡片上单独写的标题；空则退回 `title`。
    ///
    /// 置顶卡是封面加一行字，宽度只有一张卡；投放条目的标题是按一整行排的，
    /// 常常十几二十个字，塞进卡片里要么截断要么挤成三行。给置顶留一个短标题
    /// 的口子，封面和跳转目标仍然共用同一条 —— 一条内容，两处展示。
    pub pin_title: String,
    pub dismissible: bool,
    pub placements: Vec<String>,
    pub start: String,
    pub end: String,
    pub min_app_version: String,
    pub max_app_version: String,
    pub sponsor: String,
    /// True when the UI must show an ad badge.
    pub is_ad: bool,
    /// True when the UI must show the 图灵镜推荐 badge. Independent of `is_ad`:
    /// an editorial pick that a sponsor also paid for carries **both**, which
    /// is one of the three shapes the feed is specified to support.
    pub recommended: bool,
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
        // Prefer localized title; fall back to Chinese primary for id check.
        let title = crate::i18n::pick_str(d, "title");
        let title_primary = s(d.get("title"));
        if id.is_empty() || (title.is_empty() && title_primary.is_empty()) {
            return None;
        }
        let title = if title.is_empty() {
            title_primary
        } else {
            title
        };
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
        // `ad` / `sponsor` are pure placements. Any other type is something we
        // chose to show, so it is a recommendation — and it is *also* an ad
        // whenever a sponsor is named.
        let paid_type = AD_TYPES.contains(&kind.as_str());
        let is_ad = paid_type || !sponsor.is_empty();
        let recommended = !paid_type;

        // Placement decides dismissibility. The plaza exists to carry ads and
        // they are not dismissible there; the models-page banner always is.
        let on_models = placements.iter().any(|p| p == PLACEMENT_MODELS);
        let dismissible = if on_models {
            true
        } else {
            d.get("dismissible").and_then(|v| v.as_bool()).unwrap_or(false)
        };

        let body = {
            let b = crate::i18n::pick_str(d, "body");
            if !b.is_empty() {
                b
            } else {
                first(d, &["text", "desc"])
            }
        };
        let action_label = {
            let a = crate::i18n::pick_str(d, "action_label");
            if !a.is_empty() {
                a
            } else {
                first(d, &["action"])
            }
        };
        let pin_title = {
            let p = crate::i18n::pick_str(d, "pin_title");
            if !p.is_empty() {
                p
            } else {
                first(d, &["pinned_title"])
            }
        };
        // Sponsor name is usually a brand — still allow i18n map.
        let sponsor = {
            let sp = crate::i18n::pick_str(d, "sponsor");
            if !sp.is_empty() {
                sp
            } else {
                first(d, &["advertiser"])
            }
        };

        Some(Self {
            id,
            kind,
            title,
            body,
            image_url: resolve_image_url(&first(d, &["image", "image_url", "cover"])),
            url: safe_link(&first(d, &["url", "link"])),
            action_label,
            date: normalize_yymmdd(&first(d, &["date", "released"])),
            priority,
            pinned: d.get("pinned").and_then(|v| v.as_bool()).unwrap_or(false),
            pin_title,
            dismissible,
            placements,
            start: normalize_yymmdd(&s(d.get("start"))),
            end: normalize_yymmdd(&s(d.get("end"))),
            min_app_version: s(d.get("min_app_version")),
            max_app_version: s(d.get("max_app_version")),
            sponsor,
            is_ad,
            recommended,
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
        // `release-*` 是清单侧自动派生的版本资讯，给没有更新日志区块的老客户端
        // 用的。现在广场自己就有「更新日志」，再在「投放」里挂一条
        // 「RVC Fabric v1.2.4 发布」既重复、又把一条不是投放的东西放进了投放位。
        // 清单那边也已经不再派生，这里挡一道是为了已经发布出去的 plaza.json。
        .filter(|it| !it.id.starts_with("release-"))
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
    // 排序已经把置顶的排在最前，所以「留前五个」= 留优先级最高的五个。
    //
    // 在这里削而不是留给界面自己数：置顶是**发布侧**的一条规则，界面只负责
    // 把 pinned 为真的画出来。真让界面 slice(0,5)，模型页横幅、以后可能有的
    // 别的展示位就各自要再数一遍，早晚数不一致。
    for (n, it) in out.iter_mut().filter(|it| it.pinned).enumerate() {
        if n >= MAX_PINNED {
            it.pinned = false;
        }
    }
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
                    // Prefer localized highlights/notes, then Chinese primary.
                    // `highlights` is what build_catalog writes; older feeds used notes/items.
                    let mut notes = crate::i18n::pick_str_list(d, "highlights");
                    if notes.is_empty() {
                        notes = crate::i18n::pick_str_list(d, "notes");
                    }
                    if notes.is_empty() {
                        notes = crate::i18n::pick_str_list(d, "items");
                    }
                    // 一条要点都没有就退回整段 body，总比一片空白强。
                    if notes.is_empty() {
                        let body = crate::i18n::pick_str(d, "body");
                        if !body.is_empty() {
                            notes.push(body);
                        }
                    }
                    let title = {
                        let t = crate::i18n::pick_str(d, "title");
                        if t.is_empty() {
                            s(d.get("title"))
                        } else {
                            t
                        }
                    };
                    Some(ChangelogEntry {
                        version,
                        date: normalize_yymmdd(&first(d, &["date", "released"])),
                        title,
                        notes,
                    })
                })
                .collect()
        })
        .unwrap_or_default();
    out.sort_by(|a, b| compare_versions(&b.version, &a.version).cmp(&0));
    out
}

// ---------------------------------------------------------------------------
// Fetch
// ---------------------------------------------------------------------------

/// Today as `YYMMDD`, the form the feed's `start` / `end` windows use.
pub fn today_yymmdd() -> String {
    chrono::Local::now().format("%y%m%d").to_string()
}

/// Pull `plaza.json` + `changelog.json` from the release repo.
///
/// One network round each, failures reported per-feed: a broken changelog must
/// not blank the ad placements, and vice versa — the plaza carries paid slots
/// and a partial outage should not read to a sponsor as "not shown at all".
pub fn fetch(timeout_secs: u64) -> (Vec<PlazaItem>, Vec<ChangelogEntry>, Vec<String>) {
    let mut errors = Vec::new();
    let items = match crate::catalog::http_get_json(
        &format!("{CNB_RAW_MAIN}/plaza.json"),
        timeout_secs,
    ) {
        Ok(v) => parse_feed(&v),
        Err(e) => {
            errors.push(crate::i18n::te("s.a005e42321", &(e)));
            Vec::new()
        }
    };
    let changelog = match crate::catalog::http_get_json(
        &format!("{CNB_RAW_MAIN}/changelog.json"),
        timeout_secs,
    ) {
        Ok(v) => parse_changelog(&v),
        Err(e) => {
            errors.push(crate::i18n::te("s.d2620f4b90", &(e)));
            Vec::new()
        }
    };
    (items, changelog, errors)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn the_three_badge_shapes() {
        let mk = |kind: &str, sponsor: &str| {
            PlazaItem::from_value(&serde_json::json!({
                "id": "x", "title": "t", "type": kind, "sponsor": sponsor
            }))
            .unwrap()
        };
        // 图灵镜推荐 only
        let a = mk("news", "");
        assert!(a.recommended && !a.is_ad);
        // 商业推广 only
        let b = mk("ad", "");
        assert!(!b.recommended && b.is_ad);
        // both — our pick, someone paid for the slot
        let c = mk("news", &crate::i18n::t("s.b4ce6178be"));
        assert!(c.recommended && c.is_ad);
    }

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
            {"id": "p", "title": &crate::i18n::t("s.800d82ff2e"), "type": "ad"},
            {"id": "m", "title": &crate::i18n::t("s.d06eb20450"), "type": "ad",
             "placements": ["models_page"]},
        ]});
        let items = parse_feed(&feed);
        let plaza = items.iter().find(|i| i.id == "p").unwrap();
        let models = items.iter().find(|i| i.id == "m").unwrap();
        assert!(plaza.is_ad && !plaza.dismissible);
        assert!(models.is_ad && models.dismissible);
    }

    #[test]
    fn schedule_window_and_version_gate() {
        let feed = json!({"items": [
            {"id": "past", "title": &crate::i18n::t("s.7cf7bfff3c"), "end": "260101"},
            {"id": "future", "title": &crate::i18n::t("s.062e5e670f"), "start": "991231"},
            {"id": "old", "title": &crate::i18n::t("s.a3af639cfd"), "max_app_version": "1.0.0"},
            {"id": "ok", "title": &crate::i18n::t("s.fcafc66aea")},
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
    fn only_five_rows_can_hold_a_pin_the_rest_stay_in_the_feed() {
        // 清单里标了七个置顶。置顶区一行放五张卡，第六张会换行，
        // 「置顶」就变成了第二个投放列表。多出来的照常出现在投放里。
        let rows: Vec<Value> = (0..7)
            .map(|i| json!({"id": format!("p{i}"), "title": "t", "pinned": true,
                            "priority": 100 - i}))
            .collect();
        let items = parse_feed(&json!({ "items": rows }));
        let vis = visible_items(&items, PLACEMENT_PLAZA, "1.3.0", "260801", &[]);
        assert_eq!(vis.len(), 7);
        let pinned: Vec<&str> = vis
            .iter()
            .filter(|i| i.pinned)
            .map(|i| i.id.as_str())
            .collect();
        assert_eq!(pinned, vec!["p0", "p1", "p2", "p3", "p4"]);
    }

    #[test]
    fn the_pin_can_carry_its_own_shorter_title() {
        // 封面和跳转目标共用一条内容，卡片上的字可以另写。
        let items = parse_feed(&json!({"items": [
            {"id": "a", "title": &crate::i18n::t("s.c7f1de0914"),
             "pinned": true, "pin_title": &crate::i18n::t("s.4f35061e6d")},
            {"id": "b", "title": &crate::i18n::t("s.15ada3dd1b"), "pinned": true},
        ]}));
        let a = items.iter().find(|i| i.id == "a").unwrap();
        let b = items.iter().find(|i| i.id == "b").unwrap();
        assert_eq!(a.pin_title, crate::i18n::t("s.4f35061e6d"));
        assert_eq!(b.pin_title, "");
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
    fn highlights_is_the_field_the_generator_actually_writes() {
        // 线上 changelog.json 写的是 highlights，解析器以前只认 notes/items，
        // 于是每条都解析成空列表：版本号和日期照常显示，正文一个字没有。
        let data = json!({"entries": [
            {"version": "1.2.4", "date": "260730",
             "highlights": [&crate::i18n::t("s.1937f75369"), &crate::i18n::t("s.754db380c0")],
             "body": &crate::i18n::t("s.5ba1f75537")},
        ]});
        let rows = parse_changelog(&data);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].notes.len(), 2);
        assert_eq!(rows[0].notes[0], crate::i18n::t("s.1937f75369"));
    }

    #[test]
    fn body_is_the_last_resort_so_the_entry_is_never_blank() {
        let data = json!({"entries": [{"version": "1.2.3", "body": &crate::i18n::t("s.39cb51599c")}]});
        let rows = parse_changelog(&data);
        assert_eq!(rows[0].notes, vec![crate::i18n::t("s.39cb51599c")]);
    }

    #[test]
    fn auto_derived_release_news_never_shows_in_placements() {
        // 「RVC Fabric v1.2.4 发布」是清单自动派生给老客户端的，不是投放内容。
        // 广场自己已经有更新日志区块，再挂一条就是同一件事说两遍。
        let feed = json!({"items": [
            {"id": "release-1.2.4", "type": "news", "title": &crate::i18n::t("s.772fad9699")},
            {"id": "ad-1", "type": "ad", "title": &crate::i18n::t("s.ca8050f45e")},
        ]});
        let items = parse_feed(&feed);
        let vis = visible_items(&items, PLACEMENT_PLAZA, "1.3.0", "260801", &[]);
        let ids: Vec<&str> = vis.iter().map(|i| i.id.as_str()).collect();
        assert_eq!(ids, vec!["ad-1"]);
    }

    #[test]
    fn yymmdd_normalisation() {
        assert_eq!(normalize_yymmdd("2026-07-30"), "260730");
        assert_eq!(normalize_yymmdd("260730"), "260730");
        assert_eq!(normalize_yymmdd("nope"), "");
    }
}
