//! Hugging Face URL rewrite for domestic mirrors.
//!
//! Catalog entries always store canonical `https://huggingface.co/...` URLs.
//! At download time we expand them to a fallback list so Chinese users can pull
//! third-party voice packs without hitting the origin.
//!
//! Order (after de-dupe):
//! 1. User override `app_config.hf_endpoint` (if non-empty)
//! 2. `https://hf-mirror.com`
//! 3. `https://hf-cdn.sufy.com`
//! 4. Canonical `https://huggingface.co` (last resort)

/// Canonical host stored in catalog YAML / index.json.
pub const CANONICAL: &str = "https://huggingface.co";

/// Product defaults for third-party HF downloads (domestic first).
///
/// `hf-cdn.sufy.com` first: on some networks `hf-mirror.com` returns HTTP 308
/// for large LFS objects and older clients mishandle it; sufy serves 200.
pub const DEFAULT_MIRRORS: &[&str] = &["https://hf-cdn.sufy.com", "https://hf-mirror.com"];

/// True when `url` is an HF resolve/blob/api-style link we know how to rewrite.
pub fn is_hf_url(url: &str) -> bool {
    let u = url.trim();
    host_is_hf(u)
}

fn host_is_hf(url: &str) -> bool {
    let lower = url.to_ascii_lowercase();
    lower.starts_with("https://huggingface.co/")
        || lower.starts_with("http://huggingface.co/")
        || lower.starts_with("https://hf-mirror.com/")
        || lower.starts_with("http://hf-mirror.com/")
        || lower.starts_with("https://hf-cdn.sufy.com/")
        || lower.starts_with("http://hf-cdn.sufy.com/")
}

/// Strip a known HF host prefix; returns the remainder starting with `/`.
fn path_after_host(url: &str) -> Option<&str> {
    const HOSTS: &[&str] = &[
        "https://huggingface.co",
        "http://huggingface.co",
        "https://hf-mirror.com",
        "http://hf-mirror.com",
        "https://hf-cdn.sufy.com",
        "http://hf-cdn.sufy.com",
    ];
    for h in HOSTS {
        if let Some(rest) = url
            .strip_prefix(h)
            .or_else(|| {
                // case-insensitive host match for mixed-case typos in old caches
                let ul = url.to_ascii_lowercase();
                let hl = h.to_ascii_lowercase();
                if ul.starts_with(&hl) {
                    Some(&url[h.len()..])
                } else {
                    None
                }
            })
        {
            if rest.is_empty() || rest.starts_with('/') {
                return Some(if rest.is_empty() { "/" } else { rest });
            }
        }
    }
    None
}

/// Percent-encode path segments that still contain raw spaces / non-ASCII.
/// Already-encoded `%XX` sequences are left intact (decode then re-encode).
pub fn encode_path(url: &str) -> String {
    let url = url.trim();
    let Some(scheme_end) = url.find("://") else {
        return url.to_string();
    };
    let scheme = &url[..scheme_end];
    let after = &url[scheme_end + 3..];
    let slash = after.find('/').unwrap_or(after.len());
    let host = &after[..slash];
    let rest = if slash < after.len() {
        &after[slash..]
    } else {
        ""
    };
    let (path, query) = match rest.split_once('?') {
        Some((p, q)) => (p, Some(q)),
        None => (rest, None),
    };
    let encoded: String = path
        .split('/')
        .map(|seg| {
            if seg.is_empty() {
                return String::new();
            }
            let decoded = percent_decode(seg);
            percent_encode(&decoded)
        })
        .collect::<Vec<_>>()
        .join("/");
    match query {
        Some(q) => format!("{scheme}://{host}{encoded}?{q}"),
        None => format!("{scheme}://{host}{encoded}"),
    }
}

fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out: Vec<u8> = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let (Ok(hi), Ok(lo)) = (
                u8::from_str_radix(std::str::from_utf8(&bytes[i + 1..i + 2]).unwrap_or(""), 16),
                u8::from_str_radix(std::str::from_utf8(&bytes[i + 2..i + 3]).unwrap_or(""), 16),
            ) {
                out.push((hi << 4) | lo);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn percent_encode(s: &str) -> String {
    let mut out = String::with_capacity(s.len() * 3);
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(b as char);
            }
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

/// Rewrite an HF URL onto `endpoint` (scheme+host, no trailing slash required).
pub fn rewrite(url: &str, endpoint: &str) -> String {
    let url = encode_path(url.trim());
    let ep = endpoint.trim().trim_end_matches('/');
    if ep.is_empty() {
        return url;
    }
    match path_after_host(&url) {
        Some(path) => format!("{ep}{path}"),
        None => url,
    }
}

/// Ordered download URL list for one catalog link.
///
/// Non-HF URLs (CNB, etc.) are returned as a single-element list unchanged.
pub fn download_urls(url: &str, user_endpoint: &str) -> Vec<String> {
    let mut eps: Vec<String> = Vec::with_capacity(4);
    let user = user_endpoint.trim();
    if !user.is_empty() {
        eps.push(user.to_string());
    }
    eps.extend(DEFAULT_MIRRORS.iter().map(|m| (*m).to_string()));
    eps.push(CANONICAL.to_string());
    download_urls_with(url, &eps)
}

/// 同上，但端点顺序由调用方给 —— `mirrors::hf_endpoints` 解析出来的那份。
///
/// 这个模块保持无 IO、可纯测试：从哪儿读镜像列表是 `mirrors` 的事，怎么把一条
/// 规范链接改写到某个端点上是这里的事。
pub fn download_urls_with(url: &str, endpoints: &[String]) -> Vec<String> {
    let url = url.trim();
    if url.is_empty() {
        return Vec::new();
    }
    if !is_hf_url(url) {
        return vec![url.to_string()];
    }

    let url = encode_path(url);
    let mut out: Vec<String> = Vec::with_capacity(endpoints.len() + 1);
    for ep in endpoints {
        let u = rewrite(&url, ep);
        if !u.is_empty() && !out.iter().any(|x| x == &u) {
            out.push(u);
        }
    }
    // 兜底的兜底：调用方一个端点都没给（或全被过滤掉了）时，至少还有规范域。
    let canon = rewrite(&url, CANONICAL);
    if !out.iter().any(|x| x == &canon) {
        out.push(canon);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn non_hf_passthrough() {
        let u = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/lfs/abc";
        assert_eq!(download_urls(u, ""), vec![u.to_string()]);
        assert_eq!(download_urls(u, "https://hf-mirror.com"), vec![u.to_string()]);
    }

    #[test]
    fn default_order() {
        let u = "https://huggingface.co/org/repo/resolve/main/a.zip";
        let list = download_urls(u, "");
        assert_eq!(
            list,
            vec![
                "https://hf-cdn.sufy.com/org/repo/resolve/main/a.zip".to_string(),
                "https://hf-mirror.com/org/repo/resolve/main/a.zip".to_string(),
                "https://huggingface.co/org/repo/resolve/main/a.zip".to_string(),
            ]
        );
    }

    #[test]
    fn user_endpoint_first() {
        let u = "https://huggingface.co/org/repo/resolve/main/a.pth";
        let list = download_urls(u, "https://example.mirror");
        assert_eq!(list[0], "https://example.mirror/org/repo/resolve/main/a.pth");
        assert!(list.contains(&"https://hf-mirror.com/org/repo/resolve/main/a.pth".to_string()));
        assert!(list.contains(&"https://hf-cdn.sufy.com/org/repo/resolve/main/a.pth".to_string()));
        assert_eq!(list.last().unwrap(), u);
    }

    #[test]
    fn rewrite_from_mirror_source() {
        let u = "https://hf-mirror.com/org/repo/resolve/main/x.zip";
        assert_eq!(
            rewrite(u, "https://hf-cdn.sufy.com"),
            "https://hf-cdn.sufy.com/org/repo/resolve/main/x.zip"
        );
    }

    #[test]
    fn empty_and_dedupe() {
        assert!(download_urls("", "").is_empty());
        let u = "https://huggingface.co/a/b/resolve/main/f.zip";
        // user endpoint equals first default → no duplicate
        let list = download_urls(u, "https://hf-mirror.com");
        assert_eq!(list.len(), 3);
        assert_eq!(list[0], "https://hf-mirror.com/a/b/resolve/main/f.zip");
    }

    #[test]
    fn is_hf_detects() {
        assert!(is_hf_url("https://huggingface.co/x/y"));
        assert!(is_hf_url("https://hf-mirror.com/x/y"));
        assert!(!is_hf_url("https://cnb.cool/x"));
    }

    #[test]
    fn encodes_spaces_in_path() {
        let u = "https://huggingface.co/org/repo/resolve/main/prezipped/v2/ayaka-jp 101 epochs.zip";
        let list = download_urls(u, "");
        assert!(list[0].contains("ayaka-jp%20101%20epochs.zip"));
        assert!(!list[0].contains("ayaka-jp 101"));
    }
}
