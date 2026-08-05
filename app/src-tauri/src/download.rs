//! Shared multi-connection downloader for Runtime / voice packs / gui updates.
//!
//! Core engine: **[ripget](https://github.com/sam0x17/ripget)** — open-source
//! multi-part HTTP range downloader (aria2c-style), with retries, idle reconnect,
//! and configurable parallelism. We only add product glue:
//! adaptive thread count, mirror URL fallback, sha256 verify, cancel, and a
//! blocking API for Tauri commands.

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;

use ripget::{DownloadOptions, ProgressReporter};
use sha2::{Digest, Sha256};

const UA: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RVCFabric/1.3";
const MIN_MULTIPART_BYTES: u64 = 16 * 1024 * 1024; // 16 MiB — same as launcher/online/multipart.py
const MAX_CONNECTIONS: usize = 32;

/// What is being downloaded — same pipeline for all product artifacts.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(dead_code)] // VoicePack / GuiPatch used when store & update land
pub enum DownloadKind {
    Runtime,
    VoicePack,
    GuiPatch,
    Generic,
}

impl DownloadKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Runtime => "runtime",
            Self::VoicePack => "voice_pack",
            Self::GuiPatch => "gui_patch",
            Self::Generic => "file",
        }
    }
}

pub type ProgressFn = Arc<dyn Fn(u64, u64, &str) + Send + Sync>;

/// Adaptive connection count (mirrors `launcher/online/multipart.auto_connections`).
pub fn auto_connections(size: u64) -> usize {
    if size == 0 {
        return 1;
    }
    if size < MIN_MULTIPART_BYTES {
        return 1;
    }
    if size < 64 * 1024 * 1024 {
        return 8;
    }
    // Multi-GB Runtime: 16 connections; never exceed 32
    let preferred = if size >= 1024 * 1024 * 1024 { 16 } else { 12 };
    // Also keep ~1 MiB minimum per thread for very large sizes
    let by_mb = (size / (1024 * 1024)).clamp(1, MAX_CONNECTIONS as u64) as usize;
    preferred.min(by_mb).clamp(1, MAX_CONNECTIONS)
}

pub fn verify_sha256(path: &Path, expected: &str) -> Result<(), String> {
    let exp = expected
        .chars()
        .filter(|c| c.is_ascii_hexdigit())
        .collect::<String>()
        .to_ascii_lowercase();
    if exp.len() != 64 {
        return Err(crate::i18n::t("s.5ca337dd03").into());
    }
    let mut f = std::fs::File::open(path).map_err(|e| crate::i18n::te("s.21ce93c732", &(e)))?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 1024 * 1024];
    use std::io::Read;
    loop {
        let n = f.read(&mut buf).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    let got = hex::encode(hasher.finalize());
    if got != exp {
        return Err(crate::i18n::t2("s.73a397a7fd", &exp, &got));
    }
    Ok(())
}

/// Options for a single product download (Runtime / voice / patch).
#[derive(Clone)]
pub struct DownloadRequest {
    pub urls: Vec<String>,
    pub dest: PathBuf,
    pub expected_sha256: String,
    /// Known size from catalog (feeds auto_connections when HEAD is slow).
    pub size_hint: u64,
    /// None = auto_connections(size)
    pub connections: Option<usize>,
    pub kind: DownloadKind,
}

/// Bridge product progress callbacks into ripget's ProgressReporter.
///
/// Emits are throttled (~150 ms) so the UI keeps up, but the first non-zero
/// byte and completion always fire immediately — otherwise multi-GB Runtime
/// downloads can show 0% for a long time even while the network is busy
/// (percent rounds down until done/total ≥ 0.5%).
struct ProgressBridge {
    cb: ProgressFn,
    total: AtomicU64,
    done: AtomicU64,
    threads: AtomicU64,
    kind: DownloadKind,
    cancel: Arc<AtomicBool>,
    /// size_hint from catalog when Content-Length is late / missing
    size_hint: u64,
    last_emit_ms: AtomicU64,
    started_ms: AtomicU64,
}

impl ProgressBridge {
    fn now_ms() -> u64 {
        use std::time::{SystemTime, UNIX_EPOCH};
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0)
    }

    fn effective_total(&self) -> u64 {
        self.total
            .load(Ordering::SeqCst)
            .max(self.size_hint)
            .max(1)
    }

    fn emit(&self, done: u64, phase: &str, force: bool) {
        let now = Self::now_ms();
        let last = self.last_emit_ms.load(Ordering::SeqCst);
        if !force && last != 0 && now.saturating_sub(last) < 150 {
            return;
        }
        self.last_emit_ms.store(now, Ordering::SeqCst);
        if self.started_ms.load(Ordering::SeqCst) == 0 {
            self.started_ms.store(now, Ordering::SeqCst);
        }
        let total = self.effective_total();
        (self.cb)(done, total, phase);
    }
}

impl ProgressReporter for ProgressBridge {
    fn init(&self, total: u64) {
        // Prefer the larger of HEAD length and catalog hint so the bar has a
        // real denominator from the first paint.
        let t = total.max(self.size_hint).max(1);
        self.total.store(t, Ordering::SeqCst);
        self.done.store(0, Ordering::SeqCst);
        let threads = self.threads.load(Ordering::SeqCst).max(1);
        self.emit(
            0,
            &crate::i18n::t2("s.364fa9e6bf", &self.kind.as_str(), &threads),
            true,
        );
    }

    fn set_threads(&self, threads: usize) {
        self.threads.store(threads as u64, Ordering::SeqCst);
    }

    fn add(&self, delta: u64) {
        if self.cancel.load(Ordering::SeqCst) {
            return;
        }
        let prev = self.done.fetch_add(delta, Ordering::SeqCst);
        let d = prev + delta;
        // First bytes always notify; then throttle.
        let force = prev == 0 || d >= self.effective_total();
        self.emit(d, "download", force);
    }
}

/// Blocking entry used by provision / future voice & update modules.
#[allow(dead_code)]
pub fn download_file(
    urls: &[String],
    dest: &Path,
    expected_sha256: &str,
    cancel: Arc<AtomicBool>,
    progress: Option<ProgressFn>,
) -> Result<(), String> {
    download_request(
        DownloadRequest {
            urls: urls.to_vec(),
            dest: dest.to_path_buf(),
            expected_sha256: expected_sha256.to_string(),
            size_hint: 0,
            connections: None,
            kind: DownloadKind::Generic,
        },
        cancel,
        progress,
    )
}

pub fn download_request(
    req: DownloadRequest,
    cancel: Arc<AtomicBool>,
    progress: Option<ProgressFn>,
) -> Result<(), String> {
    if req.urls.is_empty() {
        return Err(crate::i18n::t("s.d08e45e275").into());
    }
    if let Some(parent) = req.dest.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }

    // Already complete + verified
    if req.dest.is_file() && !req.expected_sha256.is_empty() {
        if verify_sha256(&req.dest, &req.expected_sha256).is_ok() {
            if let Some(ref cb) = progress {
                let len = req.dest.metadata().map(|m| m.len()).unwrap_or(0);
                cb(len, len, "download");
            }
            return Ok(());
        }
        let _ = std::fs::remove_file(&req.dest);
    }

    if cancel.load(Ordering::SeqCst) {
        return Err(crate::i18n::t("s.a5ffdc95ee").into());
    }

    let threads = req
        .connections
        .unwrap_or_else(|| auto_connections(req.size_hint))
        .clamp(1, MAX_CONNECTIONS);

    // Tell the UI we are past "idle" before HEAD/TLS/handshake so the bar is
    // not stuck at 0% while the NIC is already moving packets.
    if let Some(ref cb) = progress {
        let total = req.size_hint.max(1);
        cb(
            0,
            total,
            &crate::i18n::t2("s.a32e5d5c37", &req.kind.as_str(), &threads),
        );
    }

    // Download to .part then rename after verify
    let part_path = {
        let mut p = req.dest.as_os_str().to_os_string();
        p.push(".part");
        PathBuf::from(p)
    };
    if part_path.is_file() {
        // ripget overwrites destination; drop stale partial
        let _ = std::fs::remove_file(&part_path);
    }

    let rt = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .worker_threads(2.max(threads.min(8)))
        .thread_name("rvc-dl")
        .build()
        .map_err(|e| format!("tokio runtime: {e}"))?;

    let mut last_err = String::new();
    for url in &req.urls {
        if cancel.load(Ordering::SeqCst) {
            return Err(crate::i18n::t("s.a5ffdc95ee").into());
        }
        if let Some(ref cb) = progress {
            cb(
                0,
                req.size_hint.max(1),
                &crate::i18n::te("s.9d7d0dbc49", &(req.kind.as_str())),
            );
        }
        match rt.block_on(download_one_url(
            url,
            &part_path,
            threads,
            req.kind,
            req.size_hint,
            cancel.clone(),
            progress.clone(),
        )) {
            Ok(()) => {
                if !req.expected_sha256.is_empty() {
                    if let Some(ref cb) = progress {
                        let len = part_path.metadata().map(|m| m.len()).unwrap_or(0);
                        cb(len, len.max(1), "verify");
                    }
                    if let Err(e) = verify_sha256(&part_path, &req.expected_sha256) {
                        let _ = std::fs::remove_file(&part_path);
                        last_err = e;
                        continue;
                    }
                }
                if req.dest.is_file() {
                    let _ = std::fs::remove_file(&req.dest);
                }
                std::fs::rename(&part_path, &req.dest)
                    .map_err(|e| crate::i18n::te("s.fe9e98a65c", &(e)))?;
                if let Some(ref cb) = progress {
                    let len = req.dest.metadata().map(|m| m.len()).unwrap_or(0);
                    cb(len, len.max(1), "download");
                }
                return Ok(());
            }
            Err(e) => {
                last_err = e;
                let _ = std::fs::remove_file(&part_path);
            }
        }
    }
    Err(if last_err.is_empty() {
        crate::i18n::t("s.e0dab22b1a")
    } else {
        last_err
    })
}

async fn download_one_url(
    url: &str,
    dest: &Path,
    threads: usize,
    kind: DownloadKind,
    size_hint: u64,
    cancel: Arc<AtomicBool>,
    progress: Option<ProgressFn>,
) -> Result<(), String> {
    let progress_handle: Option<ripget::Progress> = progress.map(|cb| {
        Arc::new(ProgressBridge {
            cb,
            total: AtomicU64::new(size_hint),
            done: AtomicU64::new(0),
            threads: AtomicU64::new(threads as u64),
            kind,
            cancel: cancel.clone(),
            size_hint,
            last_emit_ms: AtomicU64::new(0),
            started_ms: AtomicU64::new(0),
        }) as ripget::Progress
    });

    let mut options = DownloadOptions::new()
        .threads(threads)
        .user_agent(UA.to_string());
    if let Some(p) = progress_handle {
        options = options.progress(p);
    }

    // Cancel: poll and abort by dropping the future via select
    let download = ripget::download_url_with_options(url, dest, options);
    tokio::pin!(download);

    let cancel_wait = async {
        loop {
            if cancel.load(Ordering::SeqCst) {
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(200)).await;
        }
    };
    tokio::pin!(cancel_wait);

    tokio::select! {
        biased;
        _ = &mut cancel_wait => {
            Err(crate::i18n::t("s.a5ffdc95ee").into())
        }
        res = &mut download => {
            res.map(|_| ()).map_err(|e| format!("ripget: {e}"))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn auto_connections_scales() {
        assert_eq!(auto_connections(1024), 1);
        assert_eq!(auto_connections(20 * 1024 * 1024), 8);
        assert!(auto_connections(2 * 1024 * 1024 * 1024) >= 12);
        assert!(auto_connections(8 * 1024 * 1024 * 1024) <= MAX_CONNECTIONS);
    }
}
