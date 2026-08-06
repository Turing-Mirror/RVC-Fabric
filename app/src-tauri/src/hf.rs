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

/// Rewrite an HF URL onto `endpoint` (scheme+host, no trailing slash required).
pub fn rewrite(url: &str, endpoint: &str) -> String {
    let ep = endpoint.trim().trim_end_matches('/');
    if ep.is_empty() {
        return url.to_string();
    }
    match path_after_host(url.trim()) {
        Some(path) => format!("{ep}{path}"),
        None => url.to_string(),
    }
}

/// Ordered download URL list for one catalog link.
///
/// Non-HF URLs (CNB, etc.) are returned as a single-element list unchanged.
pub fn download_urls(url: &str, user_endpoint: &str) -> Vec<String> {
    let url = url.trim();
    if url.is_empty() {
        return Vec::new();
    }
    if !is_hf_url(url) {
        return vec![url.to_string()];
    }

    let mut out: Vec<String> = Vec::with_capacity(4);
    let mut push = |u: String| {
        if u.is_empty() {
            return;
        }
        if !out.iter().any(|x| x == &u) {
            out.push(u);
        }
    };

    let user = user_endpoint.trim();
    if !user.is_empty() {
        push(rewrite(url, user));
    }
    for m in DEFAULT_MIRRORS {
        push(rewrite(url, m));
    }
    // Canonical last — overseas / when both mirrors fail.
    push(rewrite(url, CANONICAL));
    // If the catalog somehow already pointed at a mirror, keep the original
    // order's first rewrite but also try the raw catalog URL near the front
    // when it is not already covered.
    if !out.iter().any(|x| x == url) {
        // Insert after user endpoint (if any), before defaults would have… actually
        // original mirror URL is already rewritten into defaults. Skip.
    }

    if out.is_empty() {
        out.push(url.to_string());
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
}
