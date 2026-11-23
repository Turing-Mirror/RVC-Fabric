//! Opt-in, read-only acceptance through the client's catalog and Runtime downloader.
use crate::catalog::{self, RuntimeSpec};
use crate::download::{self, DownloadKind, DownloadRequest, ProgressFn};
use serde_json::{json, Value};
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

const CATALOG: &str =
    "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main/index.json";
const MODELSCOPE: &str = "https://modelscope.cn/models/Kara251/kara-rvc-model/resolve/";
const CNB: &str = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/";
const CANCEL_AFTER: u64 = 4 * 1024 * 1024;

fn shell_log() -> Result<String, String> {
    fs::read_to_string(crate::logging::path().ok_or("Test logger is not initialized")?)
        .map_err(|e| e.to_string())
}

fn specs_from_live_catalog(dir: &Path) -> Result<Vec<RuntimeSpec>, String> {
    let data = catalog::fetch_remote_catalog(60)?;
    fs::write(
        dir.join("catalog.json"),
        serde_json::to_vec_pretty(&data).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    if !shell_log()?
        .lines()
        .any(|line| line.ends_with(&format!("catalog source {CATALOG}")))
    {
        return Err("The client did not use the requested index.json source".into());
    }
    let mut specs = Vec::new();
    for variant in ["amd", "nvidia", "nvidia50"] {
        let spec = catalog::parse_spec(variant, &data);
        let raw = &data["runtimes"][variant]["parts"][0];
        let first = raw["urls"][0].as_str().unwrap_or_default();
        let second = raw["urls"][1].as_str().unwrap_or_default();
        if !first.starts_with(MODELSCOPE)
            || !second.starts_with(CNB)
            || spec.part.urls.first().map(String::as_str) != Some(first)
            || spec.part.urls.get(1).map(String::as_str) != Some(second)
            || spec.part.name != raw["name"].as_str().unwrap_or_default()
            || spec.part.sha256.len() != 64
            || spec.part.sha256 != raw["sha256"].as_str().unwrap_or_default()
            || spec.part.size_bytes == 0
            || Some(spec.part.size_bytes) != raw["size_bytes"].as_u64()
        {
            return Err(format!("Invalid raw/parsed {variant} part: {raw}"));
        }
        println!(
            "PARSED {variant} name={} size={} sha256={} urls={:?}",
            spec.part.name, spec.part.size_bytes, spec.part.sha256, spec.part.urls
        );
        specs.push(spec);
    }
    Ok(specs)
}

fn request(spec: &RuntimeSpec, dest: &Path, urls: Vec<String>) -> DownloadRequest {
    DownloadRequest {
        urls,
        // Pure download: no telemetry, mirror preferences or user configuration writes.
        root: None,
        dest: dest.to_path_buf(),
        expected_sha256: spec.part.sha256.clone(),
        size_hint: spec.part.size_bytes,
        connections: None,
        kind: DownloadKind::Runtime,
    }
}

fn suffix(dest: &Path, suffix: &str) -> PathBuf {
    let mut name = dest.as_os_str().to_os_string();
    name.push(suffix);
    name.into()
}

fn full_download(spec: &RuntimeSpec, dir: &Path) -> Result<Value, String> {
    let dest = dir.join(&spec.part.name);
    let source = Arc::new(Mutex::new(String::new()));
    let source_cb = source.clone();
    let marker = suffix(&dest, ".part.src");
    let last_progress = Mutex::new(Instant::now());
    let progress: ProgressFn = Arc::new(move |done, total, phase| {
        if phase == "verify" {
            *source_cb.lock().unwrap() = fs::read_to_string(&marker).unwrap_or_default();
        }
        let mut last = last_progress.lock().unwrap();
        if last.elapsed() >= Duration::from_secs(10) || phase == "verify" {
            println!("PROGRESS amd {done}/{total} phase={phase}");
            *last = Instant::now();
        }
    });
    let started = Instant::now();
    download::download_request(
        request(spec, &dest, spec.part.urls.clone()),
        Arc::new(AtomicBool::new(false)),
        Some(progress),
    )?;
    let bytes = dest.metadata().map_err(|e| e.to_string())?.len();
    let sha256 = download::file_sha256(&dest)?;
    let source = source.lock().unwrap().clone();
    if bytes != spec.part.size_bytes || sha256 != spec.part.sha256 || source != spec.part.urls[0] {
        return Err(format!(
            "AMD verification mismatch: bytes={bytes}, sha256={sha256}, source={source}"
        ));
    }
    Ok(json!({
        "variant":spec.variant,"name":spec.part.name,"bytes":bytes,"sha256":sha256,
        "expected_sha256":spec.part.sha256,"source":source,"path":dest,
        "elapsed_seconds":started.elapsed().as_secs_f64()
    }))
}

fn fallback_download(spec: &RuntimeSpec, dir: &Path) -> Result<Value, String> {
    let broken = format!("{CNB}-/releases/download/RVC-runtime/not-exist.tar");
    let model_url = &spec.part.urls[0];
    let dest = dir.join(format!("fallback-{}", spec.part.name));
    let cancel = Arc::new(AtomicBool::new(false));
    let cancel_cb = cancel.clone();
    let progress: ProgressFn = Arc::new(move |done, _, _| {
        if done >= CANCEL_AFTER {
            cancel_cb.store(true, Ordering::SeqCst);
        }
    });
    let result = download::download_request(
        request(spec, &dest, vec![broken.clone(), model_url.clone()]),
        cancel.clone(),
        Some(progress),
    );
    let error = result
        .err()
        .ok_or("Fallback unexpectedly completed the whole archive")?;
    let bytes = suffix(&dest, ".part")
        .metadata()
        .map_err(|e| e.to_string())?
        .len();
    let source = fs::read_to_string(suffix(&dest, ".part.src")).map_err(|e| e.to_string())?;
    let log = shell_log()?;
    let failed = format!("download runtime fail {broken}:");
    let tried = format!("download runtime try {model_url}");
    let failed_at = log
        .find(&failed)
        .ok_or("Missing first-address failure log")?;
    let tried_at = log
        .find(&tried)
        .ok_or("Missing second-address attempt log")?;
    if failed_at >= tried_at
        || !cancel.load(Ordering::SeqCst)
        || error != crate::i18n::t("s.a5ffdc95ee")
        || source != *model_url
        || bytes < CANCEL_AFTER
        || bytes >= spec.part.size_bytes
        || dest.exists()
    {
        return Err(format!(
            "Fallback/cancel mismatch: error={error}, bytes={bytes}, source={source}"
        ));
    }
    Ok(json!({
        "variant":spec.variant,"first_url":broken,"source":source,
        "first_failure":log.lines().find(|line| line.contains(&failed)),
        "bytes":bytes,"cancel_threshold":CANCEL_AFTER,"cancelled":true,"error":error,
        "full_archive_verified":false
    }))
}

fn range_request(spec: &RuntimeSpec) -> Result<Value, String> {
    let url = &spec.part.urls[0];
    let client = reqwest::blocking::Client::builder()
        .user_agent(concat!(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RVCFabric/",
            env!("CARGO_PKG_VERSION")
        ))
        .no_gzip()
        .timeout(Duration::from_secs(60))
        .build()
        .map_err(|e| e.to_string())?;
    let response = client
        .get(url)
        .header("Range", "bytes=0-1023")
        .header("Accept-Encoding", "identity")
        .send()
        .map_err(|e| e.to_string())?;
    let status = response.status().as_u16();
    // Redirect query strings may contain temporary signed credentials.
    let mut final_url = response.url().clone();
    final_url.set_query(None);
    final_url.set_fragment(None);
    let range = response
        .headers()
        .get("content-range")
        .and_then(|v| v.to_str().ok())
        .unwrap_or_default()
        .to_owned();
    let mut bytes = Vec::new();
    response
        .take(1025)
        .read_to_end(&mut bytes)
        .map_err(|e| e.to_string())?;
    if status != 206
        || range != format!("bytes 0-1023/{}", spec.part.size_bytes)
        || bytes.len() != 1024
    {
        return Err(format!(
            "Range mismatch: HTTP {status}, content-range={range}, bytes={}",
            bytes.len()
        ));
    }
    Ok(
        json!({"variant":spec.variant,"url":url,"status":status,"range":range,
        "bytes":bytes.len(),"final_url_without_query":final_url.as_str()}),
    )
}

fn record(rows: &mut Vec<Value>, check: &str, result: Result<Value, String>) {
    let row = match result {
        Ok(evidence) => json!({"check":check,"pass":true,"evidence":evidence}),
        Err(error) => json!({"check":check,"pass":false,"error":error}),
    };
    println!("RESULT {row}");
    rows.push(row);
}

fn cleanup(dir: &Path) -> Result<Value, String> {
    let mut removed = Vec::new();
    let mut errors = Vec::new();
    // This run owns the newly created directory. Keep only its small evidence files.
    for entry in fs::read_dir(dir).map_err(|e| e.to_string())? {
        let path = entry.map_err(|e| e.to_string())?.path();
        if !matches!(
            path.extension().and_then(|v| v.to_str()),
            Some("tar" | "part" | "src")
        ) {
            continue;
        }
        let bytes = path.metadata().map_err(|e| e.to_string())?.len();
        match fs::remove_file(&path) {
            Ok(()) => removed.push(json!({"path":path,"bytes":bytes})),
            Err(e) => errors.push(format!("{}: {e}", path.display())),
        }
    }
    if !errors.is_empty() {
        return Err(errors.join("; "));
    }
    Ok(json!({"removed":removed,"remaining_archive_files":0}))
}

#[test]
#[ignore = "Live read-only acceptance; downloads about 1.8 GB and then removes archives"]
fn live_modelscope_runtime_downloads() {
    let product = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap();
    let parent = product.join("User_Data/e2e");
    fs::create_dir_all(&parent).unwrap();
    let started_at = chrono::Utc::now();
    let dir = parent.join(format!(
        "modelscope-{}-{}",
        started_at.format("%Y%m%dT%H%M%SZ"),
        std::process::id()
    ));
    fs::create_dir(&dir).unwrap();
    crate::logging::init(&dir);
    println!("EVIDENCE_DIR {}", dir.display());
    let mut rows = Vec::new();
    match specs_from_live_catalog(&dir) {
        Ok(specs) => {
            record(
                &mut rows,
                "catalog",
                Ok(json!({"source":CATALOG,"runtimes":specs.iter().map(|s|
                json!({"variant":s.variant,"name":s.part.name,"urls":s.part.urls,
                    "size_bytes":s.part.size_bytes,"sha256":s.part.sha256})).collect::<Vec<_>>()})),
            );
            record(&mut rows, "range_nvidia", range_request(&specs[1]));
            record(&mut rows, "range_nvidia50", range_request(&specs[2]));
            record(&mut rows, "fallback", fallback_download(&specs[1], &dir));
            record(&mut rows, "amd_download", full_download(&specs[0], &dir));
        }
        Err(error) => {
            record(&mut rows, "catalog", Err(error));
            for check in ["range_nvidia", "range_nvidia50", "fallback", "amd_download"] {
                record(
                    &mut rows,
                    check,
                    Err("Not run: live catalog validation failed".into()),
                );
            }
        }
    }
    record(&mut rows, "cleanup", cleanup(&dir));
    let result_path = dir.join("results.json");
    fs::write(
        &result_path,
        serde_json::to_vec_pretty(&json!({
            "started_at":started_at.to_rfc3339(),"completed_at":chrono::Utc::now().to_rfc3339(),
            "product_version":env!("CARGO_PKG_VERSION"),"results":rows
        }))
        .unwrap(),
    )
    .unwrap();
    println!("EVIDENCE {}", result_path.display());
    assert!(
        rows.iter().all(|row| row["pass"] == true),
        "Acceptance failures: {rows:?}"
    );
}
