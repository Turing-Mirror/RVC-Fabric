//! File protocol under User_Data/runtime_control/ (same as Python shell).

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde_json::{json, Map, Value};

use crate::paths;

pub fn command_path(root: &Path) -> PathBuf {
    paths::control_dir(root).join("command.json")
}

pub fn status_path(root: &Path) -> PathBuf {
    paths::control_dir(root).join("status.json")
}

pub fn seq_path(root: &Path) -> PathBuf {
    paths::control_dir(root).join("command.seq")
}

pub fn pid_path(root: &Path) -> PathBuf {
    paths::control_dir(root).join("worker.pid")
}

pub fn ensure_control_dir(root: &Path) -> std::io::Result<()> {
    fs::create_dir_all(paths::control_dir(root))?;
    fs::create_dir_all(paths::logs_dir(root))?;
    Ok(())
}

fn now_ts() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

fn read_json(path: &Path) -> Value {
    if !path.is_file() {
        return json!({});
    }
    match fs::read_to_string(path) {
        Ok(s) => serde_json::from_str(&s).unwrap_or_else(|_| json!({})),
        Err(_) => json!({}),
    }
}

/// Atomic-ish write with unique temp + retries (Windows share/replace races).
fn write_json(path: &Path, data: &Value) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let text = serde_json::to_string_pretty(data)
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))?;
    let unique = format!(
        ".{}.{}.tmp",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    );
    let tmp = path.with_file_name(format!(
        "{}{}",
        path.file_name().and_then(|s| s.to_str()).unwrap_or("data"),
        unique
    ));
    {
        let mut f = fs::File::create(&tmp)?;
        f.write_all(text.as_bytes())?;
        f.sync_all().ok();
    }
    let mut last_err: Option<std::io::Error> = None;
    for attempt in 0..8 {
        match fs::rename(&tmp, path) {
            Ok(()) => return Ok(()),
            Err(e) => {
                last_err = Some(e);
                thread::sleep(Duration::from_millis(10 * (attempt + 1) as u64));
            }
        }
    }
    // Last resort: direct write
    match fs::write(path, text.as_bytes()) {
        Ok(()) => {
            let _ = fs::remove_file(&tmp);
            Ok(())
        }
        Err(e) => {
            let _ = fs::remove_file(&tmp);
            Err(last_err.unwrap_or(e))
        }
    }
}

pub fn read_status(root: &Path) -> Value {
    read_json(&status_path(root))
}

pub fn write_status_merge(root: &Path, fields: Map<String, Value>) -> std::io::Result<()> {
    let mut cur = read_status(root);
    if !cur.is_object() {
        cur = json!({});
    }
    if let Some(obj) = cur.as_object_mut() {
        for (k, v) in fields {
            obj.insert(k, v);
        }
        obj.insert("ts".into(), json!(now_ts()));
    }
    write_json(&status_path(root), &cur)
}

pub fn next_seq(root: &Path) -> std::io::Result<u64> {
    ensure_control_dir(root)?;
    let path = seq_path(root);
    let cur: u64 = fs::read_to_string(&path)
        .ok()
        .and_then(|s| s.trim().parse().ok())
        .unwrap_or(0);
    let next = cur.saturating_add(1);
    fs::write(&path, next.to_string())?;
    Ok(next)
}

pub fn write_command(root: &Path, cmd: &str, payload: Map<String, Value>) -> std::io::Result<u64> {
    ensure_control_dir(root)?;
    let seq = next_seq(root)?;
    let mut data = Map::new();
    data.insert("seq".into(), json!(seq));
    data.insert("cmd".into(), json!(cmd));
    data.insert("ts".into(), json!(now_ts()));
    for (k, v) in payload {
        data.insert(k, v);
    }
    write_json(&command_path(root), &Value::Object(data))?;
    Ok(seq)
}

pub fn write_worker_pid(root: &Path, pid: u32) -> std::io::Result<()> {
    ensure_control_dir(root)?;
    fs::write(pid_path(root), pid.to_string())
}

pub fn clear_worker_pid(root: &Path) {
    let _ = fs::remove_file(pid_path(root));
}

pub fn read_worker_pid_file(root: &Path) -> u32 {
    fs::read_to_string(pid_path(root))
        .ok()
        .and_then(|s| s.trim().parse().ok())
        .unwrap_or(0)
}

pub fn status_pid(root: &Path) -> u32 {
    read_status(root)
        .get("pid")
        .and_then(|v| v.as_u64().or_else(|| v.as_i64().map(|i| i as u64)))
        .unwrap_or(0) as u32
}
