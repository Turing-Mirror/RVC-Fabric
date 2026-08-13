//! Resolve Runtime download specs from CNB index / embedded fallback.
//! Mirrors launcher/cnb_sources.py (URLs + channels).

use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde_json::Value;

const CNB_HOST: &str = "https://cnb.cool";
const CNB_ORG_REPO: &str = "Turing-Mirror/RVC-Fabric-Releases";
const CNB_RAW_MAIN: &str = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main";
const CNB_LFS_BASE: &str = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/lfs";
const DEFAULT_RELEASE_TAG: &str = "RVC-runtime";

/// 清单来源，按顺序试，第一个能解析成对象的就用。
///
/// 第三条以前是 `manifest.json` —— LFS 时代的老清单。**它不是兜底，是个陷阱：**
/// 里面的 runtime 条目根本没有 url，只有 `runtime\amd\...` 这种本地路径，客户端
/// 只好按 lfs 通道拿 sha256 拼出 `/-/lfs/<sha>`；而那批 LFS 对象在 173a573
/// 清仓时就删干净了，实测那个地址返回 404。也就是说前两条一旦抖一下，用户拿到
/// 的不是「旧一点的清单」，而是一个下不动的地址。它也没有 app 段，更新检查
/// 落到它头上只会永远回答「已是最新」。
///
/// 已经从发布仓删掉了。少一条 404 的退路，比多一条假的强。
const MANIFEST_URLS: &[&str] = &[
    "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main/index.json",
    "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main/catalog/online_catalog.snippet.json",
];

const UA: &str = "RVCFabric-Shell/1.3";

#[derive(Debug, Clone)]
#[allow(dead_code)]
pub struct RuntimePart {
    pub name: String,
    pub sha256: String,
    pub size_bytes: u64,
    pub urls: Vec<String>,
    pub channel: String,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
pub struct RuntimeSpec {
    pub variant: String,
    pub label: String,
    pub version: String,
    pub size_bytes: u64,
    pub part: RuntimePart,
    pub channel: String,
}

fn normalize_hex_sha(s: &str) -> String {
    s.chars()
        .filter(|c| c.is_ascii_hexdigit())
        .collect::<String>()
        .to_ascii_lowercase()
}

fn default_channel(variant: &str) -> &'static str {
    if variant == "amd" {
        "lfs"
    } else {
        "release"
    }
}

fn lfs_url(sha: &str) -> String {
    format!("{CNB_LFS_BASE}/{sha}")
}

fn release_url(tag: &str, name: &str) -> String {
    format!("{CNB_HOST}/{CNB_ORG_REPO}/-/releases/download/{tag}/{name}")
}

/// Embedded fallback when CNB is unreachable (keep in sync with cnb_sources._FALLBACK_RUNTIMES).
fn fallback_blob(variant: &str) -> Value {
    let (label, version, size, sha, name, channel) = match variant {
        "amd" => (
            "AMD/Intel DirectML".to_string(),
            "2026.07.21",
            1801268224u64,
            "5d5e4437c70ac1cf368232829381170d5a88f457eed20d14d35b1ef155dd0274",
            "runtime-amd-2026.07.21.tar",
            "lfs",
        ),
        "nvidia50" => (
            crate::i18n::t("s.bf312fa098"),
            "2026.07.21",
            6698774016u64,
            "a828e13e23589447f25b16b9314b6d730a1a7701e973613bc97d80a026102489",
            "runtime-nvidia50-2026.07.21.tar",
            "release",
        ),
        _ => (
            "NVIDIA CUDA".to_string(),
            "2026.07.21",
            6077133824u64,
            "d76ac4e8140490bda1abac8df2718bfec95f8a696c8a5ba730a5e7e901421d9b",
            "runtime-nvidia-2026.07.21.tar",
            "release",
        ),
    };
    let urls = if channel == "lfs" {
        vec![lfs_url(sha)]
    } else {
        vec![release_url(DEFAULT_RELEASE_TAG, name)]
    };
    serde_json::json!({
        "variant": variant,
        "label": label,
        "version": version,
        "format": "tar",
        "size_bytes": size,
        "channel": channel,
        "release_tag": DEFAULT_RELEASE_TAG,
        "parts": [{
            "name": name,
            "size_bytes": size,
            "sha256": sha,
            "urls": urls,
        }]
    })
}

pub(crate) fn http_get_json(url: &str, timeout_secs: u64) -> Result<Value, String> {
    http_get_json_ex(url, timeout_secs, false)
}

fn http_get_json_ex(url: &str, timeout_secs: u64, no_cache: bool) -> Result<Value, String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(timeout_secs))
        .user_agent(UA)
        .build()
        .map_err(|e| e.to_string())?;
    let mut req = client
        .get(url)
        .header("Accept", "application/json,text/plain,*/*");
    if no_cache {
        // CNB git-raw 前面有 CDN。用户点「刷新」时必须绕过，否则新上架的音色
        // 要等缓存过期才看得见。
        req = req
            .header("Cache-Control", "no-cache")
            .header("Pragma", "no-cache");
    }
    let resp = req.send().map_err(|e| format!("{url}: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("{url}: HTTP {}", resp.status()));
    }
    let text = resp.text().map_err(|e| e.to_string())?;
    serde_json::from_str(&text).map_err(|e| format!("JSON {url}: {e}"))
}

/// 给 URL 加时间戳，避免 CDN 把 `index.json` 钉死在旧版本。
fn with_cache_bust(url: &str) -> String {
    let sep = if url.contains('?') { '&' } else { '?' };
    let ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    format!("{url}{sep}_={ms}")
}

/// Short-lived memo of the remote catalog.
///
/// `provision_status` resolves a runtime spec, which fetches this. That command
/// runs on app start and again every time the provision gate opens, so without
/// a memo an offline or slow CNB meant repeating a 20-second request. Explicit
/// user actions ("检查更新") deliberately bypass it — see `fetch_remote_catalog`.
static CATALOG_MEMO: Mutex<Option<(Instant, Value)>> = Mutex::new(None);
const CATALOG_TTL: Duration = Duration::from_secs(300);

/// Cached variant for background/status callers.
pub fn fetch_remote_catalog_cached(timeout_secs: u64) -> Result<Value, String> {
    if let Some((at, v)) = CATALOG_MEMO
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .clone()
    {
        if at.elapsed() < CATALOG_TTL {
            return Ok(v);
        }
    }
    let fresh = fetch_remote_catalog(timeout_secs)?;
    *CATALOG_MEMO.lock().unwrap_or_else(|e| e.into_inner()) =
        Some((Instant::now(), fresh.clone()));
    Ok(fresh)
}

/// Always hits the network. Use for actions the user explicitly asked for
/// (商店刷新、「检查更新」)。顺带绕过 CDN 缓存。
pub fn fetch_remote_catalog(timeout_secs: u64) -> Result<Value, String> {
    let mut errors = Vec::new();
    for url in MANIFEST_URLS {
        let u = with_cache_bust(url);
        match http_get_json_ex(&u, timeout_secs, true) {
            Ok(v) if v.is_object() => {
                *CATALOG_MEMO.lock().unwrap_or_else(|e| e.into_inner()) =
                    Some((Instant::now(), v.clone()));
                return Ok(v);
            }
            Ok(_) => errors.push(format!("{url}: not an object")),
            Err(e) => errors.push(e),
        }
    }
    Err(crate::i18n::te("s.af72a27185", &errors.into_iter().take(3).collect::<Vec<_>>().join(" | ")))
}

fn normalize_part(
    part: &Value,
    variant: &str,
    channel: &str,
    release_tag: &str,
) -> Option<RuntimePart> {
    let name = part
        .get("name")
        .or_else(|| part.get("file"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    let sha = normalize_hex_sha(part.get("sha256").and_then(|v| v.as_str()).unwrap_or(""));
    let size = part
        .get("size_bytes")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let mut ch = part
        .get("channel")
        .and_then(|v| v.as_str())
        .unwrap_or(channel)
        .trim()
        .to_ascii_lowercase();
    if ch != "lfs" && ch != "release" {
        ch = default_channel(variant).into();
    }

    let mut urls: Vec<String> = Vec::new();
    match part.get("urls").or_else(|| part.get("url")) {
        Some(Value::String(s)) if !s.trim().is_empty() => urls.push(s.trim().to_string()),
        Some(Value::Array(arr)) => {
            for u in arr {
                if let Some(s) = u.as_str() {
                    if !s.trim().is_empty() {
                        urls.push(s.trim().to_string());
                    }
                }
            }
        }
        _ => {}
    }

    if urls.is_empty() {
        if ch == "lfs" && sha.len() == 64 {
            urls.push(lfs_url(&sha));
        } else if !name.is_empty() {
            urls.push(release_url(release_tag, &name));
        }
    } else if ch == "lfs" {
        urls.retain(|u| u.contains("/-/lfs/") || u.contains("/-/git/raw/"));
        if sha.len() == 64 {
            let lfs = lfs_url(&sha);
            if !urls.iter().any(|u| u == &lfs) {
                urls.insert(0, lfs);
            }
        }
    } else {
        let mut release: Vec<String> = urls
            .into_iter()
            .filter(|u| u.contains("/-/releases/download/") || u.contains("/releases/download/"))
            .collect();
        if release.is_empty() && !name.is_empty() {
            release.push(release_url(release_tag, &name));
        }
        urls = release;
    }

    if urls.is_empty() {
        return None;
    }
    Some(RuntimePart {
        name: if name.is_empty() {
            format!("runtime-{}.tar", &sha[..12.min(sha.len())])
        } else {
            name
        },
        sha256: sha,
        size_bytes: size,
        urls,
        channel: ch,
    })
}

pub fn parse_spec(variant: &str, data: &Value) -> RuntimeSpec {
    let mut var = variant.trim().to_ascii_lowercase();
    if var != "nvidia" && var != "amd" && var != "nvidia50" {
        var = "nvidia".into();
    }
    let runtimes = data.get("runtimes").and_then(|v| v.as_object());
    let mut blob = runtimes
        .and_then(|m| m.get(&var).cloned())
        .unwrap_or_else(|| fallback_blob(&var));

    // Ensure fallback fields if remote blob is sparse
    if blob.get("parts").is_none() && blob.get("sha256").is_none() {
        blob = fallback_blob(&var);
    }

    let channel = blob
        .get("channel")
        .and_then(|v| v.as_str())
        .unwrap_or_else(|| default_channel(&var))
        .to_ascii_lowercase();
    let release_tag = blob
        .get("release_tag")
        .and_then(|v| v.as_str())
        .or_else(|| data.get("runtime_release_tag").and_then(|v| v.as_str()))
        .unwrap_or(DEFAULT_RELEASE_TAG)
        .to_string();

    let mut part = None;
    if let Some(arr) = blob.get("parts").and_then(|v| v.as_array()) {
        for p in arr {
            if let Some(rp) = normalize_part(p, &var, &channel, &release_tag) {
                part = Some(rp);
                break;
            }
        }
    }
    if part.is_none() {
        if let Some(sha) = blob.get("sha256") {
            let p = serde_json::json!({
                "name": blob.get("name").and_then(|v| v.as_str()).unwrap_or(&format!("runtime-{var}.tar")),
                "sha256": sha,
                "size_bytes": blob.get("size_bytes").cloned().unwrap_or(Value::Null),
            });
            part = normalize_part(&p, &var, &channel, &release_tag);
        }
    }
    if part.is_none() {
        let fb = fallback_blob(&var);
        part = fb
            .get("parts")
            .and_then(|v| v.as_array())
            .and_then(|a| a.first())
            .and_then(|p| normalize_part(p, &var, &channel, &release_tag));
        blob = fb;
    }
    let part = match part {
        Some(p) => p,
        None => {
            // Last-resort: synthesize from hardcoded nvidia fallback
            let fb = fallback_blob("nvidia");
            normalize_part(
                fb.get("parts")
                    .and_then(|v| v.as_array())
                    .and_then(|a| a.first())
                    .unwrap_or(&fb),
                "nvidia",
                "release",
                DEFAULT_RELEASE_TAG,
            )
            .expect("embedded nvidia fallback is valid")
        }
    };
    let size = blob
        .get("size_bytes")
        .and_then(|v| v.as_u64())
        .unwrap_or(part.size_bytes);

    RuntimeSpec {
        variant: var.clone(),
        label: blob
            .get("label")
            .and_then(|v| v.as_str())
            .unwrap_or(&var)
            .to_string(),
        version: blob
            .get("version")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        size_bytes: size,
        channel: blob
            .get("channel")
            .and_then(|v| v.as_str())
            .unwrap_or(&channel)
            .to_string(),
        part,
    }
}

/// Remote catalog wins; embedded fallback if offline.
pub fn resolve_runtime_spec(variant: &str, prefer_remote: bool) -> Result<RuntimeSpec, String> {
    let mut data = serde_json::json!({
        "runtimes": {
            "nvidia": fallback_blob("nvidia"),
            "amd": fallback_blob("amd"),
            "nvidia50": fallback_blob("nvidia50"),
        }
    });
    if prefer_remote {
        if let Ok(remote) = fetch_remote_catalog_cached(20) {
            if let Some(rem_rt) = remote.get("runtimes").and_then(|v| v.as_object()) {
                let mut merged = data
                    .get("runtimes")
                    .cloned()
                    .unwrap_or_else(|| serde_json::json!({}));
                if let Some(m) = merged.as_object_mut() {
                    for (k, rem_blob) in rem_rt {
                        if !rem_blob.is_object() {
                            continue;
                        }
                        let base = m.get(k).cloned().unwrap_or_else(|| fallback_blob(k));
                        let mut out = base;
                        if let (Some(bo), Some(ro)) = (out.as_object_mut(), rem_blob.as_object()) {
                            for (rk, rv) in ro {
                                if rv.is_null() {
                                    continue;
                                }
                                if rk == "parts" {
                                    if rv.as_array().map(|a| !a.is_empty()).unwrap_or(false) {
                                        bo.insert(rk.clone(), rv.clone());
                                    }
                                } else if !(rv.is_string() && rv.as_str() == Some("")) {
                                    bo.insert(rk.clone(), rv.clone());
                                }
                            }
                        }
                        m.insert(k.clone(), out);
                    }
                }
                data["runtimes"] = merged;
            }
            if let Some(tag) = remote.get("runtime_release_tag") {
                data["runtime_release_tag"] = tag.clone();
            }
        }
    }
    Ok(parse_spec(variant, &data))
}

/// Silence unused import warning for CNB_RAW_MAIN if needed later.
#[allow(dead_code)]
fn _raw_main() -> &'static str {
    CNB_RAW_MAIN
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cache_bust_adds_a_timestamp_query() {
        let u = with_cache_bust("https://example.invalid/index.json");
        assert!(u.starts_with("https://example.invalid/index.json?_="));
        assert!(u.len() > "https://example.invalid/index.json?_=".len());
    }

    #[test]
    fn cache_bust_appends_when_the_url_already_has_a_query() {
        let u = with_cache_bust("https://example.invalid/index.json?x=1");
        assert!(u.contains("&_="));
        assert!(u.starts_with("https://example.invalid/index.json?x=1&_="));
    }
}
