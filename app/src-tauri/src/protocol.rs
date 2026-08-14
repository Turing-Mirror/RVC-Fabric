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

/// 我们 spawn 过的每一个 worker pid，一行一个。
///
/// `worker.pid` 只有一行，谁后写就是谁 —— 一旦同时活着两个 worker，先写的那个
/// 就再也没人记得，退出时也就杀不掉它。它会一直占着声卡活到用户重启电脑。
/// 这个台账是补上那条记忆：只记我们自己 spawn 出来的 pid，不做进程枚举，
/// 所以永远不会误伤别人的进程。
pub fn pids_path(root: &Path) -> PathBuf {
    paths::control_dir(root).join("worker.pids")
}

/// 记一个 spawn 出来的 pid。文件不存在就建，重复的不再写第二遍。
pub fn remember_spawned_pid(root: &Path, pid: u32) -> std::io::Result<()> {
    if pid == 0 {
        return Ok(());
    }
    ensure_control_dir(root)?;
    let mut pids = read_spawned_pids(root);
    if pids.contains(&pid) {
        return Ok(());
    }
    pids.push(pid);
    // 只留最近 32 个：这是台账不是历史，早就死透的 pid 留着只会让每次启动
    // 多做几十次无用的存活检查，还会因为 pid 复用而误判。
    let start = pids.len().saturating_sub(32);
    let text = pids[start..]
        .iter()
        .map(|p| p.to_string())
        .collect::<Vec<_>>()
        .join("\n");
    fs::write(pids_path(root), text)
}

pub fn read_spawned_pids(root: &Path) -> Vec<u32> {
    fs::read_to_string(pids_path(root))
        .ok()
        .map(|s| s.lines().filter_map(|l| l.trim().parse().ok()).collect())
        .unwrap_or_default()
}

pub fn clear_spawned_pids(root: &Path) {
    let _ = fs::remove_file(pids_path(root));
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

/// 离线转换进度（`tools/worker_protocol.write_sts` 的另一头）。
///
/// 单独一个文件而不是塞进 status.json：进度一秒好几条，每条都顺带重写一遍
/// 引擎状态不值当，还要跟上面那条 message_code 规矩打架。
pub fn sts_path(root: &Path) -> PathBuf {
    paths::control_dir(root).join("sts.json")
}

pub fn read_sts(root: &Path) -> Value {
    read_json(&sts_path(root))
}

/// 开转前清干净。不清的话热路径第一次轮询会读到上一轮的 done，界面直接跳完成。
pub fn clear_sts(root: &Path) {
    let _ = fs::remove_file(sts_path(root));
}

pub fn write_status_merge(root: &Path, fields: Map<String, Value>) -> std::io::Result<()> {
    let mut cur = read_status(root);
    if !cur.is_object() {
        cur = json!({});
    }
    if let Some(obj) = cur.as_object_mut() {
        // 和 tools/worker_protocol.write_status 同一条规矩：谁改了 message/state
        // 又没给新的 message_code，就把旧 code 清掉。status.json 是合并写的，
        // 开机那句 `engine.starting` 不清就会一直粘着 —— 界面按 code 翻译，
        // 于是引擎早就 idle 了，副标题还写着「正在加载…」。
        let touches_text = fields.contains_key("message") || fields.contains_key("state");
        if touches_text && !fields.contains_key("message_code") {
            obj.insert("message_code".into(), json!(""));
        }
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

pub fn read_command(root: &Path) -> Value {
    read_json(&command_path(root))
}

/// Worker writes this after accepting a command (before long work finishes).
pub fn last_cmd_seq(root: &Path) -> u64 {
    read_status(root)
        .get("last_cmd_seq")
        .and_then(|v| v.as_u64().or_else(|| v.as_i64().map(|i| i as u64)))
        .unwrap_or(0)
}

/// Wait until `status.last_cmd_seq >= seq` (worker has claimed that command).
pub fn wait_cmd_acked(root: &Path, seq: u64, timeout_ms: u64) -> bool {
    if seq == 0 {
        return true;
    }
    let deadline = SystemTime::now() + Duration::from_millis(timeout_ms);
    while SystemTime::now() < deadline {
        if last_cmd_seq(root) >= seq {
            return true;
        }
        thread::sleep(Duration::from_millis(20));
    }
    last_cmd_seq(root) >= seq
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
