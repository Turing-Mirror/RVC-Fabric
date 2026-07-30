//! Anonymous daily usage ping (opt-in).
//!
//! Design constraints, decided 2026-07-30:
//!
//! * The download path stays **direct to CNB** — putting Cloudflare in front of
//!   a domestic origin makes things slower for the users we actually have. Only
//!   this tiny ping goes to CF.
//! * Fire and forget: background thread, short timeout, **never retried inline**
//!   and never surfaced as an error. It must not affect any feature.
//! * **Backfill.** CF from the mainland fails sometimes; dropping those days
//!   would under-count DAU systematically. We report *which days this install
//!   launched*, so catching up later is accurate rather than a guess.
//! * No behaviour events, no IP stored client-side, endpoint hard-coded (never
//!   read from plaza.json or any other editable feed).

use std::path::Path;

use serde_json::{json, Map, Value};

use crate::config;

/// Hard-coded on purpose. A feed-supplied endpoint would mean handing the
/// telemetry destination to whoever can edit the catalog.
const ENDPOINT: &str = "https://cdn.turingmirror.com/p";

/// Days kept when the endpoint is unreachable. Beyond this the oldest are
/// dropped — an install offline for two weeks is not worth unbounded state.
const MAX_QUEUE: usize = 14;

fn today() -> String {
    // UTC day bucket without pulling in a date crate.
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let days = secs / 86_400;
    let (y, m, d) = civil_from_days(days as i64);
    format!("{y:04}{m:02}{d:02}")
}

/// days since 1970-01-01 -> (y, m, d). Howard Hinnant's civil_from_days.
fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = (z - era * 146_097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    (if m <= 2 { y + 1 } else { y }, m, d)
}

fn random_id() -> String {
    let a = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0);
    let b = std::process::id() as u64;
    let mut x = a ^ (b << 32) ^ 0x9E37_79B9_7F4A_7C15;
    // splitmix64 — no rand dependency needed for one identifier.
    x = (x ^ (x >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    x = (x ^ (x >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    x ^= x >> 31;
    format!("{x:016x}")
}

/// Queue today, then try to flush everything queued. Returns what was sent.
pub fn tick(root: &Path, app_version: &str, accel: &str) -> Value {
    let cfg = config::read(root);
    if cfg.get("telemetry_opt_in").and_then(|v| v.as_bool()) != Some(true) {
        return json!({"sent": false, "reason": "opt-out"});
    }

    let id = match cfg.get("telemetry_id").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => {
            let fresh = random_id();
            let mut p = Map::new();
            p.insert("telemetry_id".into(), json!(fresh));
            let _ = config::update(root, p);
            fresh
        }
    };

    let mut days: Vec<String> = cfg
        .get("telemetry_pending_days")
        .and_then(|v| v.as_array())
        .map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect())
        .unwrap_or_default();
    let t = today();
    if !days.contains(&t) {
        days.push(t);
    }
    days.sort();
    days.dedup();
    if days.len() > MAX_QUEUE {
        let cut = days.len() - MAX_QUEUE;
        days.drain(0..cut);
    }

    let body = json!({ "id": id, "days": days, "ver": app_version, "accel": accel });
    let ok = post(&body);

    let mut patch = Map::new();
    patch.insert(
        "telemetry_pending_days".into(),
        if ok { json!([]) } else { json!(days) },
    );
    let _ = config::update(root, patch);

    json!({"sent": ok, "days": body["days"].clone()})
}

fn post(body: &Value) -> bool {
    let Ok(client) = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(3))
        .build()
    else {
        return false;
    };
    let Ok(text) = serde_json::to_string(body) else {
        return false;
    };
    client
        .post(ENDPOINT)
        .header("Content-Type", "application/json")
        .body(text)
        .send()
        .map(|r: reqwest::blocking::Response| r.status().is_success())
        .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn day_bucket_is_yyyymmdd() {
        let t = today();
        assert_eq!(t.len(), 8);
        assert!(t.chars().all(|c| c.is_ascii_digit()));
    }

    #[test]
    fn civil_conversion_matches_known_dates() {
        assert_eq!(civil_from_days(0), (1970, 1, 1));
        assert_eq!(civil_from_days(19_723), (2024, 1, 1));
    }

    #[test]
    fn ids_are_not_all_the_same() {
        let a = random_id();
        std::thread::sleep(std::time::Duration::from_millis(2));
        let b = random_id();
        assert_ne!(a, b);
        assert_eq!(a.len(), 16);
    }

    #[test]
    fn endpoint_is_hard_coded_https() {
        assert!(ENDPOINT.starts_with("https://"));
    }
}
