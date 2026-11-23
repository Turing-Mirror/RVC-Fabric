//! Read-only live catalog parsing and Range acceptance.
use app_lib::catalog;
use serde_json::{json, Value};
use std::io::Read;
use std::time::Duration;

#[test]
#[ignore = "Live CNB requests; explicit acceptance only"]
fn live_runtime_ranges() {
    let source = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main/index.json";
    let client = reqwest::blocking::Client::builder()
        .user_agent("RVCFabric-Shell/1.3")
        .timeout(Duration::from_secs(60))
        .build()
        .unwrap();
    let response = client
        .get(source)
        .header("Cache-Control", "no-cache")
        .send()
        .unwrap();
    assert!(
        response.status().is_success(),
        "Catalog HTTP {}",
        response.status()
    );
    let data: Value = serde_json::from_str(&response.text().unwrap()).unwrap();
    println!("CATALOG {source} version={}", data["app"]["version"]);
    let mut failures = Vec::new();
    for variant in ["nvidia", "nvidia50", "amd"] {
        let spec = catalog::parse_spec(variant, &data);
        assert!(!spec.part.urls.is_empty() && spec.part.sha256.len() == 64);
        println!(
            "PARSED {variant} name={} size={} sha256={}",
            spec.part.name, spec.part.size_bytes, spec.part.sha256
        );
        for url in &spec.part.urls {
            let result = (|| -> Result<Value, String> {
                let response = client
                    .get(url)
                    .header("Range", "bytes=0-1023")
                    .header("Accept-Encoding", "identity")
                    .send()
                    .map_err(|e| e.to_string())?;
                let status = response.status().as_u16();
                let final_url = response.url().to_string();
                let range = response
                    .headers()
                    .get("content-range")
                    .and_then(|h| h.to_str().ok())
                    .unwrap_or("")
                    .to_owned();
                let mut bytes = Vec::new();
                response
                    .take(1025)
                    .read_to_end(&mut bytes)
                    .map_err(|e| e.to_string())?;
                let expected = format!("bytes 0-1023/{}", spec.part.size_bytes);
                if status != 206 || range != expected || bytes.len() != 1024 {
                    return Err(format!(
                        "HTTP {status}, content-range={range}, bytes={}, final={final_url}",
                        bytes.len()
                    ));
                }
                Ok(
                    json!({"variant":variant,"pass":true,"url":url,"final_url":final_url,"status":status,"range":range,"bytes":bytes.len()}),
                )
            })();
            match result {
                Ok(row) => println!("RESULT {row}"),
                Err(error) => {
                    println!("FAIL {variant} {url}: {error}");
                    failures.push(error);
                }
            }
        }
    }
    assert!(failures.is_empty(), "Live Range failures: {failures:?}");
}
