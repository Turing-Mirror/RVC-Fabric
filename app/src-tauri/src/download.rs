//! HTTP download with optional Range resume + sha256 verify.

use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::Path;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

// AtomicU64 used for progress

use sha2::{Digest, Sha256};

const UA: &str = "Mozilla/5.0 RVCFabric/1.3";
const CHUNK: usize = 64 * 1024;

pub type ProgressFn = Arc<dyn Fn(u64, u64, &str) + Send + Sync>;

pub fn verify_sha256(path: &Path, expected: &str) -> Result<(), String> {
    let exp = expected
        .chars()
        .filter(|c| c.is_ascii_hexdigit())
        .collect::<String>()
        .to_ascii_lowercase();
    if exp.len() != 64 {
        return Err("sha256 格式无效".into());
    }
    let mut f = File::open(path).map_err(|e| format!("打开文件失败: {e}"))?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; CHUNK];
    loop {
        let n = f.read(&mut buf).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    let got = hex::encode(hasher.finalize());
    if got != exp {
        return Err(format!("sha256 不匹配\n期望 {exp}\n实际 {got}"));
    }
    Ok(())
}

fn client(timeout_secs: u64) -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(timeout_secs))
        .connect_timeout(Duration::from_secs(30))
        .user_agent(UA)
        .redirect(reqwest::redirect::Policy::limited(10))
        .build()
        .map_err(|e| e.to_string())
}

/// Probe total size; 0 if unknown.
fn probe_size(client: &reqwest::blocking::Client, url: &str) -> u64 {
    if let Ok(r) = client.head(url).send() {
        if r.status().is_success() {
            if let Some(len) = r.content_length() {
                return len;
            }
            if let Some(h) = r.headers().get(reqwest::header::CONTENT_LENGTH) {
                if let Ok(s) = h.to_str() {
                    if let Ok(n) = s.parse::<u64>() {
                        return n;
                    }
                }
            }
        }
    }
    // Some hosts reject HEAD — try Range 0-0
    if let Ok(r) = client
        .get(url)
        .header(reqwest::header::RANGE, "bytes=0-0")
        .send()
    {
        if let Some(cr) = r.headers().get(reqwest::header::CONTENT_RANGE) {
            if let Ok(s) = cr.to_str() {
                // bytes 0-0/12345
                if let Some(total) = s.split('/').nth(1) {
                    if let Ok(n) = total.trim().parse::<u64>() {
                        return n;
                    }
                }
            }
        }
    }
    0
}

/// Download *url* to *dest*, resuming via existing .part size when possible.
pub fn download_file(
    urls: &[String],
    dest: &Path,
    expected_sha256: &str,
    cancel: &AtomicBool,
    progress: Option<ProgressFn>,
) -> Result<(), String> {
    if urls.is_empty() {
        return Err("没有下载地址".into());
    }
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }

    // Already complete + verified
    if dest.is_file() && !expected_sha256.is_empty() {
        if verify_sha256(dest, expected_sha256).is_ok() {
            if let Some(ref cb) = progress {
                let len = dest.metadata().map(|m| m.len()).unwrap_or(0);
                cb(len, len, "download");
            }
            return Ok(());
        }
        let _ = fs::remove_file(dest);
    }

    let part = dest.with_extension(format!(
        "{}part",
        dest.extension()
            .and_then(|e| e.to_str())
            .map(|e| format!("{e}."))
            .unwrap_or_default()
    ));
    // Prefer dest.part next to dest
    let part_path = {
        let mut p = dest.as_os_str().to_os_string();
        p.push(".part");
        std::path::PathBuf::from(p)
    };
    let _ = part; // silence

    let client = client(7200)?;
    let mut last_err = String::new();

    for url in urls {
        if cancel.load(Ordering::SeqCst) {
            return Err("已取消".into());
        }
        match download_one(
            &client,
            url,
            dest,
            &part_path,
            expected_sha256,
            cancel,
            progress.clone(),
        ) {
            Ok(()) => return Ok(()),
            Err(e) => {
                last_err = e;
                // keep .part for resume across mirrors
            }
        }
    }
    Err(last_err)
}

fn download_one(
    client: &reqwest::blocking::Client,
    url: &str,
    dest: &Path,
    part_path: &Path,
    expected_sha256: &str,
    cancel: &AtomicBool,
    progress: Option<ProgressFn>,
) -> Result<(), String> {
    let total_hint = probe_size(client, url);
    let mut existing = if part_path.is_file() {
        part_path.metadata().map(|m| m.len()).unwrap_or(0)
    } else {
        0
    };
    // If complete size known and part already full, just rename + verify
    if total_hint > 0 && existing >= total_hint {
        fs::rename(part_path, dest).map_err(|e| e.to_string())?;
        if !expected_sha256.is_empty() {
            verify_sha256(dest, expected_sha256)?;
        }
        return Ok(());
    }

    let mut req = client.get(url);
    if existing > 0 {
        req = req.header(reqwest::header::RANGE, format!("bytes={existing}-"));
    }
    let mut resp = req.send().map_err(|e| format!("请求失败: {e}"))?;
    let status = resp.status();
    if status.as_u16() == 416 {
        // Range not satisfiable — file complete on server side
        if part_path.is_file() {
            fs::rename(part_path, dest).map_err(|e| e.to_string())?;
            if !expected_sha256.is_empty() {
                verify_sha256(dest, expected_sha256)?;
            }
            return Ok(());
        }
        return Err("HTTP 416".into());
    }
    if status.as_u16() == 200 && existing > 0 {
        // Server ignored Range — restart
        existing = 0;
        let _ = fs::remove_file(part_path);
    } else if !status.is_success() && status.as_u16() != 206 {
        return Err(format!("HTTP {status}：{}", &url[..url.len().min(120)]));
    }

    let total = if status.as_u16() == 206 {
        // Content-Range: bytes start-end/total
        resp.headers()
            .get(reqwest::header::CONTENT_RANGE)
            .and_then(|h| h.to_str().ok())
            .and_then(|s| s.split('/').nth(1))
            .and_then(|t| t.trim().parse().ok())
            .unwrap_or(total_hint)
    } else {
        resp.content_length()
            .map(|l| l + existing)
            .unwrap_or(total_hint)
    };

    let mut file = OpenOptions::new()
        .create(true)
        .write(true)
        .read(true)
        .open(part_path)
        .map_err(|e| format!("无法创建临时文件: {e}"))?;
    if existing > 0 {
        file.seek(SeekFrom::Start(existing))
            .map_err(|e| e.to_string())?;
    } else {
        file.set_len(0).ok();
    }

    let done = Arc::new(AtomicU64::new(existing));
    let mut buf = [0u8; CHUNK];
    let mut last_emit = std::time::Instant::now();
    loop {
        if cancel.load(Ordering::SeqCst) {
            return Err("已取消".into());
        }
        let n = resp.read(&mut buf).map_err(|e| format!("读取失败: {e}"))?;
        if n == 0 {
            break;
        }
        file.write_all(&buf[..n])
            .map_err(|e| format!("写入失败: {e}"))?;
        let d = done.fetch_add(n as u64, Ordering::SeqCst) + n as u64;
        if let Some(ref cb) = progress {
            if last_emit.elapsed() >= Duration::from_millis(200) {
                cb(d, total, "download");
                last_emit = std::time::Instant::now();
            }
        }
    }
    file.flush().ok();
    drop(file);

    if let Some(ref cb) = progress {
        let d = done.load(Ordering::SeqCst);
        cb(d, if total > 0 { total } else { d }, "download");
    }

    fs::rename(part_path, dest).map_err(|e| format!("完成重命名失败: {e}"))?;
    if !expected_sha256.is_empty() {
        if let Some(ref cb) = progress {
            cb(total, total, "verify");
        }
        verify_sha256(dest, expected_sha256).map_err(|e| {
            let _ = fs::remove_file(dest);
            e
        })?;
    }
    Ok(())
}
