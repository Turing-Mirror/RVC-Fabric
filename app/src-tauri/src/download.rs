//! Shared multi-connection downloader for Runtime / voice packs / gui updates.
//!
//! Core engine: **[ripget](https://github.com/sam0x17/ripget)** — open-source
//! multi-part HTTP range downloader (aria2c-style), with retries, idle reconnect,
//! and configurable parallelism. We only add product glue:
//! adaptive thread count, mirror URL fallback, sha256 verify, cancel,
//! reconnect on HTTP 500 (ripget treats it as fatal), and a blocking API
//! for Tauri commands.

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

use ripget::{DownloadOptions, ProgressReporter};
use sha2::{Digest, Sha256};

const UA: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RVCFabric/1.3";
const MIN_MULTIPART_BYTES: u64 = 16 * 1024 * 1024; // 16 MiB — same as launcher/online/multipart.py
const MAX_CONNECTIONS: usize = 32;
/// CNB Release CDN returns HTTP 500 under load. ripget treats 500 as fatal
/// (only 404/500 are non-retryable inside the crate), so a 6 GB Runtime
/// fetch used to die on the first blip. Wait ~3s and try again.
const RETRY_WAIT: Duration = Duration::from_secs(3);
const MAX_TRANSIENT_ATTEMPTS: u32 = 5;
/// ripget's `fetch_metadata` retries non-404/500 forever and the client has
/// no request timeout. A hanging mirror / CNB 502 then never returns, so the
/// store card stays at 0% and we never fail over to the next URL. Cap how
/// long we wait for the first real byte, then treat it as a transient error.
const FIRST_BYTE_TIMEOUT: Duration = Duration::from_secs(20);
const FIRST_BYTE_TIMEOUT_ERR: &str = "timed out waiting for first byte";
/// 选源阶段给每个候选的时间。这里只发一个 `Range: bytes=0-0`，回不回得来
/// 是秒级的事；等满 8 秒还没动静的源，让它排到后面去。
const PROBE_TIMEOUT: Duration = Duration::from_secs(8);
/// 续传流多久没有新字节算卡死。比 FIRST_BYTE_TIMEOUT 短：这时候连接已经建
/// 起来过了，再哑 15 秒就是真断了。
const RESUME_STALL: Duration = Duration::from_secs(15);

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

/// Progress phase token: `retry:N` (N = how many times we already failed).
pub fn retry_phase(attempt: u32) -> String {
    format!("retry:{attempt}")
}

/// Parse `retry:N`. Anything else is not a reconnect phase.
pub fn parse_retry_attempt(phase: &str) -> Option<u32> {
    phase.strip_prefix("retry:")?.parse().ok()
}

/// Percent for UI. Keep it a float so a 100 KB / 80 MB voice pack does not
/// sit on integer `0%` until a full percent has landed.
pub fn progress_percent(done: u64, total: u64) -> f64 {
    if total == 0 {
        0.0
    } else {
        (done as f64 / total as f64) * 100.0
    }
}

/// Network / origin blips we should reconnect on. Permanent catalog/auth/hash
/// errors must not spin.
pub fn is_transient_download_error(err: &str) -> bool {
    let e = err.to_ascii_lowercase();
    if e.contains("已取消") || e.contains("cancel") {
        return false;
    }
    if e.contains("status 404")
        || e.contains("status 403")
        || e.contains("status 401")
        || e.contains("status 410")
    {
        return false;
    }
    // Hash mismatch is the file we got, not the pipe. Next URL maybe; not a reconnect.
    if e.contains("sha256") {
        return false;
    }
    if e.contains("status 500")
        || e.contains("internal server error")
        || e.contains("status 502")
        || e.contains("status 503")
        || e.contains("status 504")
        || e.contains("status 429")
        || e.contains("bad gateway")
        || e.contains("service unavailable")
        || e.contains("gateway timeout")
        || e.contains("too many requests")
    {
        return true;
    }
    e.contains("timed out")
        || e.contains("timeout")
        || e.contains("connection")
        || e.contains("reset")
        || e.contains("broken pipe")
        || e.contains("unexpected end of stream")
        || e.contains("error sending request")
        || e.contains("dns")
        || e.contains("tls")
        || e.contains("handshake")
        || e.contains("unreachable")
        || e.contains("os error 10054")
        || e.contains("os error 10060")
        || e.contains("os error 10053")
        || e.contains("os error 10061")
        || e.contains("os error 11001")
        || (e.starts_with("ripget:") && !e.contains("status 40"))
}

fn wait_retry(cancel: &AtomicBool) -> Result<(), String> {
    let deadline = std::time::Instant::now() + RETRY_WAIT;
    while std::time::Instant::now() < deadline {
        if cancel.load(Ordering::SeqCst) {
            return Err(crate::i18n::t("s.a5ffdc95ee"));
        }
        let left = deadline.saturating_duration_since(std::time::Instant::now());
        std::thread::sleep(left.min(Duration::from_millis(200)));
    }
    if cancel.load(Ordering::SeqCst) {
        return Err(crate::i18n::t("s.a5ffdc95ee"));
    }
    Ok(())
}

fn with_retry_help(err: &str, attempts: u32) -> String {
    format!(
        "{}\n\n{}\n\n{}",
        err,
        crate::i18n::te("s.dlGaveUp", &attempts),
        crate::i18n::t("s.dlFailedHelp"),
    )
}

fn suffixed(base: &Path, suffix: &str) -> PathBuf {
    let mut p = base.as_os_str().to_os_string();
    p.push(suffix);
    PathBuf::from(p)
}

/// 手上这半截还能不能接着下：返回它属于哪个源，None = 作废重来。
///
/// 判据只有标记文件，因为 `.part` 本身分不出「续传攒下的前缀」和「ripget 预
/// 分配出来的完整长度空壳」—— 后者的大小就是完整大小。
fn resumable_from(recorded: &str, urls: &[String], part_len: u64) -> Option<String> {
    let r = recorded.trim();
    if r.is_empty() || part_len == 0 || !urls.iter().any(|u| u == r) {
        return None;
    }
    Some(r.to_string())
}

/// 第 n 次重试用多少连接。
///
/// 有些镜像不是「挂了」，是被 32 路并发打到限流才回 429/503。同样的并发重试
/// 五轮，五轮都会被同样地拒掉 —— 退一步反而下得来。
pub fn connections_for_attempt(base: usize, attempt: u32) -> usize {
    match attempt {
        0 | 1 => base,
        2 => (base / 4).max(4).min(base),
        _ => 1,
    }
}

/// 把候选源按「谁先回应」重排，第一个能用的排最前。
///
/// 以前是串行的：第一个源卡住就等满 20 秒，三个源全卡要等一分钟才轮到第一次
/// 重试。这里同时给每个源发一个 `Range: bytes=0-0`，谁先回 200/206 就用谁 ——
/// 一个字节的往返，是秒级的事。
///
/// 只重排、不淘汰：探测失败的源仍然留在后面。探测用的连接和真正下载的连接
/// 走的可能不是同一条路（CDN 节点、连接池），凭一次探测就把源判死太武断。
fn probe_order(urls: &[String], cancel: &Arc<AtomicBool>) -> Vec<String> {
    if urls.len() < 2 {
        return urls.to_vec();
    }
    let (tx, rx) = std::sync::mpsc::channel::<usize>();
    for (i, u) in urls.iter().enumerate().take(6) {
        let url = u.clone();
        let tx = tx.clone();
        // detach：探测线程最多活 PROBE_TIMEOUT，不 join，免得一个卡死的源
        // 把选源阶段拖成它自己的超时。
        std::thread::spawn(move || {
            let ok = reqwest::blocking::Client::builder()
                .timeout(PROBE_TIMEOUT)
                .user_agent(UA)
                .build()
                .ok()
                .and_then(|c| c.get(&url).header("Range", "bytes=0-0").send().ok())
                .map(|r| {
                    let s = r.status();
                    s.is_success() || s == reqwest::StatusCode::PARTIAL_CONTENT
                })
                .unwrap_or(false);
            if ok {
                let _ = tx.send(i);
            }
        });
    }
    drop(tx);

    let deadline = std::time::Instant::now() + PROBE_TIMEOUT;
    let winner = loop {
        if cancel.load(Ordering::SeqCst) {
            return urls.to_vec();
        }
        let left = deadline.saturating_duration_since(std::time::Instant::now());
        if left.is_zero() {
            break None;
        }
        match rx.recv_timeout(left.min(Duration::from_millis(250))) {
            Ok(i) => break Some(i),
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => continue,
            // 所有探测线程都结束了还没人成功
            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => break None,
        }
    };

    let Some(w) = winner else {
        return urls.to_vec();
    };
    let mut out = Vec::with_capacity(urls.len());
    out.push(urls[w].clone());
    for (i, u) in urls.iter().enumerate() {
        if i != w {
            out.push(u.clone());
        }
    }
    out
}

/// 单流续传：把 `part` 已有的字节数当起点，`Range: bytes=N-` 接着下。
///
/// **为什么不是全程都用它**：ripget 那条是多连接并行的，健康网络上快得多，
/// 但它会 `prepare_file` 把目标预分配成完整长度，再往各个 offset 写 —— 一个
/// 半截的 `.part` 大小就是完整大小，中间哪些块是真的没法知道，续不了。
///
/// 所以分工是：第一次走 ripget（快），重试走这条（能攒）。网络烂的时候重试
/// 才是常态，而那正是续传值钱的地方 —— 一个 500MB 的包不会每次都从零开始。
async fn resume_one_url(
    url: &str,
    part: &Path,
    kind: DownloadKind,
    size_hint: u64,
    cancel: Arc<AtomicBool>,
    progress: Option<ProgressFn>,
) -> Result<(), String> {
    use std::io::Write;

    let have = std::fs::metadata(part).map(|m| m.len()).unwrap_or(0);
    let client = reqwest::Client::builder()
        .user_agent(UA)
        .connect_timeout(Duration::from_secs(15))
        .read_timeout(RESUME_STALL)
        .build()
        .map_err(|e| format!("client: {e}"))?;

    let mut req = client.get(url);
    if have > 0 {
        req = req.header("Range", format!("bytes={have}-"));
    }
    let resp = req.send().await.map_err(|e| format!("resume: {e}"))?;
    let status = resp.status();
    if !status.is_success() {
        return Err(format!("resume: status {}", status.as_u16()));
    }

    // 服务器不认 Range（回 200 而不是 206）：它给的是整个文件，之前那截作废。
    let partial = status == reqwest::StatusCode::PARTIAL_CONTENT;
    let start = if partial && have > 0 { have } else { 0 };
    let total = resp
        .content_length()
        .map(|n| start + n)
        .unwrap_or(size_hint)
        .max(1);

    let mut f = if start > 0 {
        std::fs::OpenOptions::new()
            .append(true)
            .open(part)
            .map_err(|e| e.to_string())?
    } else {
        std::fs::File::create(part).map_err(|e| e.to_string())?
    };

    let mut done = start;
    let mut last_emit = std::time::Instant::now();
    if let Some(ref cb) = progress {
        cb(done, total, kind.as_str());
    }
    let mut resp = resp;
    loop {
        if cancel.load(Ordering::SeqCst) {
            let _ = f.flush();
            return Err(crate::i18n::t("s.a5ffdc95ee"));
        }
        let chunk = resp.chunk().await.map_err(|e| format!("resume: {e}"))?;
        let Some(bytes) = chunk else { break };
        f.write_all(&bytes).map_err(|e| e.to_string())?;
        done += bytes.len() as u64;
        if let Some(ref cb) = progress {
            if last_emit.elapsed() >= Duration::from_millis(150) {
                last_emit = std::time::Instant::now();
                cb(done, total.max(done), kind.as_str());
            }
        }
    }
    f.flush().map_err(|e| e.to_string())?;
    if let Some(ref cb) = progress {
        cb(done, total.max(done), kind.as_str());
    }
    Ok(())
}

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
    /// 产品根。有它才能记「上次成功的源」和攒下载成败计数；给 None 就是
    /// 纯下载，不碰配置（安装器早期、单元测试）。
    pub root: Option<PathBuf>,
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
            root: None,
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
    let part_path = suffixed(&req.dest, ".part");
    // 「这个 .part 是从哪个源续下来的合法前缀」。
    //
    // 光看文件本身分不出来：ripget 会把目标**预分配**成完整长度再往各个
    // offset 写，一个半截的 .part 大小就是完整大小。只有续传那条路会写这个
    // 标记，所以它在 = 可以接着下，它不在 = 无条件重来。
    //
    // 顺带解决跨调用续传：用户取消一个 700MB 的包，回头再点，接着下。
    let tag_path = suffixed(&req.dest, ".part.src");
    let recorded = std::fs::read_to_string(&tag_path).unwrap_or_default();
    let part_len = part_path.metadata().map(|m| m.len()).unwrap_or(0);
    let mut resume_url = resumable_from(&recorded, &req.urls, part_len).unwrap_or_default();
    if resume_url.is_empty() {
        // 没标记、标记指向一个这次不用的源、或者半截是空的 —— 全部作废。
        let _ = std::fs::remove_file(&part_path);
        let _ = std::fs::remove_file(&tag_path);
    } else {
        crate::logging::shell_log!(format!(
            "download resume {} bytes from {resume_url}",
            part_len
        ));
    }

    let rt = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .worker_threads(2.max(threads.min(8)))
        .thread_name("rvc-dl")
        .build()
        .map_err(|e| format!("tokio runtime: {e}"))?;

    // 选源：并发探一轮，谁先回应谁排第一。串行等超时的老做法在三个源都卡的
    // 时候要一分钟才轮到第一次重试。
    let urls = probe_order(&req.urls, &cancel);

    let mut last_err = String::new();
    let mut attempt = 0u32;
    loop {
        attempt += 1;
        let mut saw_transient = false;
        for url in &urls {
            if cancel.load(Ordering::SeqCst) {
                return Err(crate::i18n::t("s.a5ffdc95ee").into());
            }
            let conns = connections_for_attempt(threads, attempt);
            crate::logging::shell_log!(format!(
                "download {} try {} (attempt {attempt}, conns {conns})",
                req.kind.as_str(),
                url
            ));
            if let Some(ref cb) = progress {
                cb(
                    0,
                    req.size_hint.max(1),
                    &crate::i18n::te("s.9d7d0dbc49", &(req.kind.as_str())),
                );
            }
            // 第一次走 ripget（多连接，健康网络上快得多）；重试走单流续传 ——
            // 重试才是网络烂的时候的常态，而那正是续传值钱的地方。手上已经
            // 攒着这个源的半截时，第一次就直接接着下。
            let use_resume = attempt > 1 || resume_url == *url;
            if !use_resume {
                // 交给 ripget：它会预分配，接不上，半截作废。
                let _ = std::fs::remove_file(&part_path);
                let _ = std::fs::remove_file(&tag_path);
            } else if resume_url != *url {
                // 换源了：别在别人的字节后面接。
                let _ = std::fs::remove_file(&part_path);
            }
            let outcome = if use_resume {
                resume_url = url.clone();
                let _ = std::fs::write(&tag_path, url);
                rt.block_on(resume_one_url(
                    url,
                    &part_path,
                    req.kind,
                    req.size_hint,
                    cancel.clone(),
                    progress.clone(),
                ))
            } else {
                rt.block_on(download_one_url(
                    url,
                    &part_path,
                    conns,
                    req.kind,
                    req.size_hint,
                    cancel.clone(),
                    progress.clone(),
                ))
            };
            match outcome {
                Ok(()) => {
                    crate::logging::shell_log!(format!(
                        "download {} ok {}",
                        req.kind.as_str(),
                        url
                    ));
                    if let Some(ref root) = req.root {
                        crate::mirrors::note_success(root, url);
                        crate::telemetry::note_download(root, url, None);
                    }
                    if !req.expected_sha256.is_empty() {
                        if let Some(ref cb) = progress {
                            let len = part_path.metadata().map(|m| m.len()).unwrap_or(0);
                            cb(len, len.max(1), "verify");
                        }
                        if let Err(e) = verify_sha256(&part_path, &req.expected_sha256) {
                            // 拿到的东西不对，续传更没意义 —— 整个丢掉换下一个源。
                            let _ = std::fs::remove_file(&part_path);
                            let _ = std::fs::remove_file(&tag_path);
                            resume_url.clear();
                            if let Some(ref root) = req.root {
                                crate::telemetry::note_download(root, url, Some(&e));
                            }
                            last_err = e;
                            continue;
                        }
                    }
                    if req.dest.is_file() {
                        let _ = std::fs::remove_file(&req.dest);
                    }
                    let _ = std::fs::remove_file(&tag_path);
                    std::fs::rename(&part_path, &req.dest)
                        .map_err(|e| crate::i18n::te("s.fe9e98a65c", &(e)))?;
                    if let Some(ref cb) = progress {
                        let len = req.dest.metadata().map(|m| m.len()).unwrap_or(0);
                        cb(len, len.max(1), "download");
                    }
                    return Ok(());
                }
                Err(e) => {
                    crate::logging::shell_log!(format!(
                        "download {} fail {}: {e}",
                        req.kind.as_str(),
                        url
                    ));
                    if e == crate::i18n::t("s.a5ffdc95ee")
                        || e.to_ascii_lowercase().contains("cancel")
                    {
                        // 取消：把半截留着，下次点安装能接着下。
                        return Err(e);
                    }
                    if let Some(ref root) = req.root {
                        crate::telemetry::note_download(root, url, Some(&e));
                    }
                    // 续传路径下失败**不删** `.part` —— 那正是它存在的意义。
                    // ripget 那条留下的是预分配的稀疏文件，必须删。
                    if !use_resume {
                        let _ = std::fs::remove_file(&part_path);
                        let _ = std::fs::remove_file(&tag_path);
                    }
                    if is_transient_download_error(&e) {
                        saw_transient = true;
                    }
                    last_err = e;
                }
            }
        }
        if last_err.is_empty() {
            break;
        }
        if !saw_transient || attempt >= MAX_TRANSIENT_ATTEMPTS {
            break;
        }
        crate::logging::shell_log!(format!(
            "download retry {attempt}/{MAX_TRANSIENT_ATTEMPTS} after: {last_err}"
        ));
        if let Some(ref cb) = progress {
            cb(0, req.size_hint.max(1), &retry_phase(attempt));
        }
        wait_retry(&cancel)?;
    }
    Err(if last_err.is_empty() {
        crate::i18n::t("s.e0dab22b1a")
    } else if is_transient_download_error(&last_err) {
        with_retry_help(&last_err, attempt)
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
    let got_bytes = Arc::new(AtomicBool::new(false));
    // Always attach a reporter so first-byte timeout can see real traffic,
    // even when the caller did not pass a UI callback (index files, etc.).
    let track: ProgressFn = {
        let flag = got_bytes.clone();
        Arc::new(move |done, total, phase| {
            if done > 0 {
                flag.store(true, Ordering::SeqCst);
            }
            if let Some(ref cb) = progress {
                cb(done, total, phase);
            }
        })
    };
    let progress_handle: ripget::Progress = Arc::new(ProgressBridge {
        cb: track,
        total: AtomicU64::new(size_hint),
        done: AtomicU64::new(0),
        threads: AtomicU64::new(threads as u64),
        kind,
        cancel: cancel.clone(),
        size_hint,
        last_emit_ms: AtomicU64::new(0),
        started_ms: AtomicU64::new(0),
    });

    let options = DownloadOptions::new()
        .threads(threads)
        .user_agent(UA.to_string())
        .progress(progress_handle);

    // Cancel / first-byte timeout: poll and abort by dropping the future.
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

    let first_byte_wait = wait_first_byte_or_timeout(got_bytes, cancel.clone());
    tokio::pin!(first_byte_wait);

    tokio::select! {
        biased;
        _ = &mut cancel_wait => {
            Err(crate::i18n::t("s.a5ffdc95ee").into())
        }
        timed_out = &mut first_byte_wait => {
            timed_out
        }
        res = &mut download => {
            res.map(|_| ()).map_err(|e| format!("ripget: {e}"))
        }
    }
}

/// Completes only when the first byte never arrives in time. After bytes
/// start flowing this future parks so the download branch can finish.
async fn wait_first_byte_or_timeout(
    got_bytes: Arc<AtomicBool>,
    cancel: Arc<AtomicBool>,
) -> Result<(), String> {
    let deadline = tokio::time::Instant::now() + FIRST_BYTE_TIMEOUT;
    loop {
        if cancel.load(Ordering::SeqCst) {
            return Err(crate::i18n::t("s.a5ffdc95ee"));
        }
        if got_bytes.load(Ordering::SeqCst) {
            std::future::pending::<()>().await;
        }
        if tokio::time::Instant::now() >= deadline {
            return Err(FIRST_BYTE_TIMEOUT_ERR.to_string());
        }
        let left = deadline.saturating_duration_since(tokio::time::Instant::now());
        tokio::time::sleep(left.min(Duration::from_millis(200))).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn connections_back_off_across_retries() {
        // 有些镜像不是挂了，是被 32 路并发打到限流。同并发重试五轮全是白费。
        assert_eq!(connections_for_attempt(32, 1), 32);
        assert_eq!(connections_for_attempt(32, 2), 8);
        assert_eq!(connections_for_attempt(32, 3), 1);
        assert_eq!(connections_for_attempt(32, 5), 1);
        // 本来就只有一条连接的小文件，不该被「退让」抬上去
        assert_eq!(connections_for_attempt(1, 2), 1);
        assert_eq!(connections_for_attempt(4, 2), 4);
    }

    #[test]
    fn probe_leaves_a_single_url_alone() {
        // 只有一个源就没什么可探的 —— 别为它多付一个往返。
        let urls = vec!["https://example.invalid/a".to_string()];
        let cancel = Arc::new(AtomicBool::new(false));
        assert_eq!(probe_order(&urls, &cancel), urls);
    }

    #[test]
    fn probe_keeps_every_url_when_none_answers() {
        // 全都探不通时必须原样返回：探测只重排，不淘汰。真正的下载连接和探测
        // 连接走的可能不是同一条路，凭一次探测判死太武断。
        let urls = vec![
            "https://a.invalid/x".to_string(),
            "https://b.invalid/x".to_string(),
        ];
        let cancel = Arc::new(AtomicBool::new(true)); // 立刻取消，不真发请求
        assert_eq!(probe_order(&urls, &cancel), urls);
    }

    #[test]
    fn a_stale_partial_is_only_kept_with_a_matching_tag() {
        // `.part` 单看是分不出「续传攒下的前缀」和「ripget 预分配的空壳」的，
        // 所以只认标记文件。
        let urls = vec!["https://a.cn/p.zip".to_string(), "https://b.cn/p.zip".to_string()];
        assert_eq!(
            resumable_from("https://a.cn/p.zip", &urls, 1024),
            Some("https://a.cn/p.zip".to_string())
        );
        // 标记指向这次不用的源：接在别人的字节后面，最后 sha256 才发现，白下一遍
        assert_eq!(resumable_from("https://c.cn/p.zip", &urls, 1024), None);
        // 没标记 = ripget 留下的空壳，或者根本没下过
        assert_eq!(resumable_from("", &urls, 1024), None);
        // 空文件没什么可续的，还多一个 Range 往返
        assert_eq!(resumable_from("https://a.cn/p.zip", &urls, 0), None);
    }

    #[test]
    fn part_and_tag_sit_next_to_the_destination() {
        let dest = std::path::Path::new("/tmp/x/pack.zip");
        assert_eq!(suffixed(dest, ".part").file_name().unwrap(), "pack.zip.part");
        assert_eq!(
            suffixed(dest, ".part.src").file_name().unwrap(),
            "pack.zip.part.src"
        );
    }

    #[test]
    fn auto_connections_scales() {
        assert_eq!(auto_connections(1024), 1);
        assert_eq!(auto_connections(20 * 1024 * 1024), 8);
        assert!(auto_connections(2 * 1024 * 1024 * 1024) >= 12);
        assert!(auto_connections(8 * 1024 * 1024 * 1024) <= MAX_CONNECTIONS);
    }

    #[test]
    fn cnb_500_is_transient() {
        let e = "ripget: unexpected HTTP status 500 Internal Server Error for \
                 https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/releases/download/\
                 RVC-runtime/runtime-nvidia-2026.07.21.tar";
        assert!(is_transient_download_error(e));
        assert!(is_transient_download_error(
            "ripget: unexpected HTTP status 502 Bad Gateway for https://cnb.cool/x"
        ));
        assert!(is_transient_download_error("error sending request for url"));
        assert!(is_transient_download_error("os error 10054"));
        assert!(is_transient_download_error(FIRST_BYTE_TIMEOUT_ERR));
    }

    #[test]
    fn progress_percent_keeps_fractions() {
        // 100 KiB of an 80 MiB pack used to cast to integer 0%.
        let p = progress_percent(100 * 1024, 80 * 1024 * 1024);
        assert!(p > 0.1 && p < 0.2, "{p}");
        assert_eq!(progress_percent(0, 1), 0.0);
        assert_eq!(progress_percent(50, 0), 0.0);
        assert!((progress_percent(1, 1) - 100.0).abs() < f64::EPSILON);
    }

    #[test]
    fn permanent_errors_are_not_retried() {
        assert!(!is_transient_download_error(
            "ripget: unexpected HTTP status 404 Not Found for https://cnb.cool/x"
        ));
        assert!(!is_transient_download_error(
            "ripget: unexpected HTTP status 403 Forbidden for https://cnb.cool/x"
        ));
        assert!(!is_transient_download_error("已取消"));
        assert!(!is_transient_download_error("cancelled by user"));
        assert!(!is_transient_download_error(
            "sha256 mismatch: expected abc got def"
        ));
    }

    #[test]
    fn retry_phase_roundtrip() {
        assert_eq!(retry_phase(3), "retry:3");
        assert_eq!(parse_retry_attempt("retry:3"), Some(3));
        assert_eq!(parse_retry_attempt("retry"), None);
        assert_eq!(parse_retry_attempt("download"), None);
    }
}
