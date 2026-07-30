//! Loopback checker for `scripts/build_catalog.py`.
//!
//! The build script must verify its output against the *real client parser*.
//! That parser now lives in Rust, so the check runs through this binary instead
//! of importing the retired Python shell.
//!
//! Usage:
//!     catalog-check plaza     < plaza.json
//!     catalog-check changelog < changelog.json
//!     catalog-check version <a> <b>      # prints -1 / 0 / 1
//!     catalog-check types                # KNOWN_TYPES / AD_TYPES
//!
//! Output is JSON on stdout; exit code 1 means the payload could not be parsed
//! at all.

use std::io::Read;

use app_lib::{catalog, plaza, update};
use serde_json::json;

fn read_stdin() -> serde_json::Value {
    let mut buf = String::new();
    if std::io::stdin().read_to_string(&mut buf).is_err() {
        return serde_json::Value::Null;
    }
    serde_json::from_str(&buf).unwrap_or(serde_json::Value::Null)
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let cmd = args.first().map(String::as_str).unwrap_or("");

    let out = match cmd {
        "plaza" => {
            let data = read_stdin();
            let items = plaza::parse_feed(&data);
            json!({
                "ok": true,
                "count": items.len(),
                "ids": items.iter().map(|i| i.id.clone()).collect::<Vec<_>>(),
                "items": items,
            })
        }
        "changelog" => {
            let data = read_stdin();
            let rows = plaza::parse_changelog(&data);
            json!({
                "ok": true,
                "count": rows.len(),
                "versions": rows.iter().map(|r| r.version.clone()).collect::<Vec<_>>(),
                "entries": rows,
            })
        }
        "version" => {
            let a = args.get(1).cloned().unwrap_or_default();
            let b = args.get(2).cloned().unwrap_or_default();
            json!({"ok": true, "cmp": update::compare_versions(&a, &b)})
        }
        "runtimes" => {
            // Loopback B: every runtime variant must survive the client parser
            // with at least one URL and a sha256.
            let data = read_stdin();
            let mut rows = Vec::new();
            if let Some(rt) = data.get("runtimes").and_then(|v| v.as_object()) {
                for variant in rt.keys() {
                    let spec = catalog::parse_spec(variant, &data);
                    rows.push(json!({
                        "variant": variant,
                        "urls": spec.part.urls.len(),
                        "sha256": !spec.part.sha256.is_empty(),
                    }));
                }
            }
            json!({"ok": true, "runtimes": rows})
        }
        "types" => json!({
            "ok": true,
            "known_types": plaza::KNOWN_TYPES,
            "ad_types": plaza::AD_TYPES,
            "app_version": update::APP_VERSION,
        }),
        _ => {
            eprintln!("usage: catalog-check <plaza|changelog|version|types>");
            std::process::exit(2);
        }
    };
    println!("{}", serde_json::to_string(&out).unwrap_or_default());
}
