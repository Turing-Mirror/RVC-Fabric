//! 下载源的解析顺序。
//!
//! 编译进 exe 的那份列表只是**兜底**。真正决定顺序的是三件事，优先级从高到低：
//!
//! 1. 用户在设置里填的 `hf_endpoint` —— 他自己指定的，永远第一。
//! 2. 上次真的下成功的那个源（`hf_endpoint_last_good`）。某些网络就是过不去
//!    sufy，不记住的话他每次、每个文件都要先白等一遍首字节超时。
//! 3. 在线清单下发的列表。
//!
//! 第 3 条是这个模块存在的理由：镜像写死在代码里的时候，某个源哪天挂了要发一
//! 个新版本才能救，而用户装的还是旧版。清单本来就在拉、在缓存，把列表放进去，
//! 改一行 JSON 几分钟内所有客户端换源。
//!
//! **清单是外部输入。** 它决定客户端去哪里下 .pth（一个 pickle），所以这里的
//! 校验不是形式主义：只收 https、只收裸主机名（HF 端点）或 https+路径（LFS
//! 基址），拒绝 userinfo、查询串、非 ASCII。写死的 sha256 校验仍然是最后一道
//! 闸，但别让一条被改过的清单先把流量引到任意地方去。

use std::path::Path;

use serde_json::Value;

use crate::config;

/// 一份清单最多认这么多个源。清单被改坏的时候，别让下载器去轮询几百个地址。
const MAX_ENDPOINTS: usize = 8;
/// 主机名 / 基址的长度上限。
const MAX_LEN: usize = 128;

/// 裸 HF 端点：`https://host`，没有路径、没有查询串。
///
/// 允许端口（`:8443`）是因为自建镜像常用非标端口；不允许用户名密码。
pub fn is_valid_endpoint(s: &str) -> bool {
    let s = s.trim();
    if s.is_empty() || s.len() > MAX_LEN || !s.is_ascii() {
        return false;
    }
    let Some(host) = s.strip_prefix("https://") else {
        // 明文 http 一律不收：这个值来自远端，降级到明文等于把「下什么」
        // 交给中间人。用户自己在设置里填的也一样 —— 他要真有内网 http 源，
        // 那是另一个需求，不该从这条路开口子。
        return false;
    };
    if host.is_empty() || host.len() > MAX_LEN {
        return false;
    }
    if host.contains('/') || host.contains('@') || host.contains('?') || host.contains('#') {
        return false;
    }
    valid_host_port(host)
}

/// LFS 基址：`https://host/path`，路径部分允许，但同样不许查询串和 userinfo。
pub fn is_valid_base(s: &str) -> bool {
    let s = s.trim().trim_end_matches('/');
    if s.is_empty() || s.len() > MAX_LEN || !s.is_ascii() {
        return false;
    }
    let Some(rest) = s.strip_prefix("https://") else {
        return false;
    };
    if rest.contains('@') || rest.contains('?') || rest.contains('#') {
        return false;
    }
    let (host, path) = match rest.split_once('/') {
        Some((h, p)) => (h, p),
        None => (rest, ""),
    };
    if !valid_host_port(host) {
        return false;
    }
    // 路径里不许有 `..`，免得一条清单把基址写成 `https://host/a/../..`
    // 再靠拼接跑到别的仓库去。
    !path.split('/').any(|seg| seg == "..")
}

fn valid_host_port(host: &str) -> bool {
    let (name, port) = match host.rsplit_once(':') {
        Some((n, p)) => (n, Some(p)),
        None => (host, None),
    };
    if let Some(p) = port {
        if p.is_empty() || p.len() > 5 || !p.bytes().all(|b| b.is_ascii_digit()) {
            return false;
        }
    }
    if name.is_empty() || name.starts_with('.') || name.ends_with('.') || !name.contains('.') {
        return false;
    }
    name.bytes()
        .all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'-')
        && !name.contains("..")
}

/// 清单里的 `download_mirrors`。读的是已经落地的那份（缓存优先，其次随包），
/// **不发网络请求** —— 这个函数在每次下载前都会调，不能自己先去下一个清单。
fn catalog_mirrors(root: &Path) -> Value {
    for p in [crate::store::cache_catalog_path(root), crate::store::bundled_catalog_path(root)] {
        if !p.is_file() {
            continue;
        }
        let Ok(text) = std::fs::read_to_string(&p) else {
            continue;
        };
        let Ok(v) = serde_json::from_str::<Value>(&text) else {
            continue;
        };
        if let Some(m) = v.get("download_mirrors").filter(|x| x.is_object()) {
            return m.clone();
        }
    }
    Value::Null
}

fn list_from(v: &Value, key: &str, valid: fn(&str) -> bool) -> Vec<String> {
    v.get(key)
        .and_then(|x| x.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|x| x.as_str())
                .map(|s| s.trim().trim_end_matches('/').to_string())
                .filter(|s| valid(s))
                .take(MAX_ENDPOINTS)
                .collect()
        })
        .unwrap_or_default()
}

fn push_unique(out: &mut Vec<String>, s: String) {
    if !s.is_empty() && !out.iter().any(|x| x == &s) {
        out.push(s);
    }
}

/// HF 端点的完整顺序：用户指定 → 上次成功 → 清单 → 编译进来的兜底 → 规范域。
pub fn hf_endpoints(root: &Path) -> Vec<String> {
    let cfg = config::read(root);
    let cat = catalog_mirrors(root);
    let mut out: Vec<String> = Vec::with_capacity(8);

    for key in ["hf_endpoint", "hf_endpoint_last_good"] {
        let v = cfg.get(key).and_then(|x| x.as_str()).unwrap_or("").trim();
        let v = v.trim_end_matches('/');
        if is_valid_endpoint(v) {
            push_unique(&mut out, v.to_string());
        }
    }
    for m in list_from(&cat, "hf", is_valid_endpoint) {
        push_unique(&mut out, m);
    }
    for m in crate::hf::DEFAULT_MIRRORS {
        push_unique(&mut out, (*m).to_string());
    }
    push_unique(&mut out, crate::hf::CANONICAL.to_string());
    out
}

/// CNB LFS 的基址列表。默认只有官方仓库一个 —— engine-core / VB-Cable 这些
/// 自家制品全走它，清单里加一条就能多一个备份源，不用发版。
pub fn lfs_bases(root: &Path) -> Vec<String> {
    let cat = catalog_mirrors(root);
    let mut out: Vec<String> = Vec::with_capacity(4);
    push_unique(&mut out, crate::engine_assets::CNB_REPO.to_string());
    for m in list_from(&cat, "lfs", is_valid_base) {
        push_unique(&mut out, m);
    }
    out
}

/// 从一条下载成功的 URL 里取出「源」，记进配置，下次排第二（仅次于用户自选）。
///
/// 只记 HF 那几个可互换的镜像：CNB 直链、LFS 基址不是「端点」，记了也没有
/// 换源的余地。写失败不管 —— 这只是个提速的记忆，不是正确性的一部分。
pub fn note_success(root: &Path, url: &str) {
    let Some(origin) = origin_of(url) else {
        return;
    };
    if !crate::hf::is_hf_url(url) {
        return;
    }
    let cfg = config::read(root);
    if cfg.get("hf_endpoint_last_good").and_then(|v| v.as_str()) == Some(origin.as_str()) {
        return; // 没变就别写盘：下载一个音色包会成功很多次
    }
    let mut patch = serde_json::Map::new();
    patch.insert("hf_endpoint_last_good".into(), Value::String(origin));
    let _ = config::update(root, patch);
}

/// `https://host/a/b` → `https://host`。给遥测和 last_good 用。
pub fn origin_of(url: &str) -> Option<String> {
    let rest = url.trim().strip_prefix("https://")?;
    let host = rest.split('/').next().unwrap_or("");
    if host.is_empty() {
        return None;
    }
    Some(format!("https://{host}"))
}

/// 只要主机名，给遥测用（不带 scheme，短一点）。
pub fn host_of(url: &str) -> String {
    let rest = url
        .trim()
        .strip_prefix("https://")
        .or_else(|| url.trim().strip_prefix("http://"))
        .unwrap_or(url.trim());
    rest.split('/').next().unwrap_or("").to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn scratch(name: &str) -> std::path::PathBuf {
        let p = std::env::temp_dir().join(format!("rvcf-mirrors-{name}"));
        let _ = std::fs::remove_dir_all(&p);
        std::fs::create_dir_all(p.join("configs")).unwrap();
        std::fs::create_dir_all(crate::paths::user_data(&p)).unwrap();
        p
    }

    fn write_catalog(root: &Path, v: Value) {
        std::fs::write(
            root.join("configs").join("online_catalog.json"),
            serde_json::to_string(&v).unwrap(),
        )
        .unwrap();
    }

    #[test]
    fn endpoint_validation_rejects_the_dangerous_shapes() {
        assert!(is_valid_endpoint("https://hf-mirror.com"));
        assert!(is_valid_endpoint("https://mirror.example.cn:8443"));
        // 明文、带路径、userinfo、查询串、非 ASCII、裸主机名
        assert!(!is_valid_endpoint("http://hf-mirror.com"));
        assert!(!is_valid_endpoint("https://evil.com/redirect?to=x"));
        assert!(!is_valid_endpoint("https://user:pw@evil.com"));
        assert!(!is_valid_endpoint("https://例子.cn"));
        assert!(!is_valid_endpoint("https://localhost"));
        assert!(!is_valid_endpoint("https://"));
        assert!(!is_valid_endpoint(&format!("https://{}.com", "a".repeat(200))));
    }

    #[test]
    fn base_validation_allows_a_path_but_not_traversal() {
        assert!(is_valid_base("https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases"));
        assert!(is_valid_base("https://cnb.cool/a/b/"));
        assert!(!is_valid_base("https://cnb.cool/a/../../b"));
        assert!(!is_valid_base("http://cnb.cool/a"));
        assert!(!is_valid_base("https://cnb.cool/a?x=1"));
    }

    #[test]
    fn catalog_mirrors_come_before_the_compiled_defaults() {
        let root = &scratch("order");
        write_catalog(
            root,
            json!({"download_mirrors": {"hf": ["https://fresh.mirror.cn"]}}),
        );
        let list = hf_endpoints(root);
        assert_eq!(list[0], "https://fresh.mirror.cn");
        // 兜底仍然在后面 —— 清单只是插队，不是替换
        assert!(list.iter().any(|u| u == "https://hf-mirror.com"));
        assert_eq!(list.last().unwrap(), crate::hf::CANONICAL);
    }

    #[test]
    fn a_tampered_catalog_cannot_redirect_downloads() {
        let root = &scratch("tampered");
        write_catalog(
            root,
            json!({"download_mirrors": {
                "hf": ["http://evil.cn", "https://evil.cn/steal?x=", "https://ok.mirror.cn"],
                "lfs": ["https://evil.cn/../../x"]
            }}),
        );
        let hf = hf_endpoints(root);
        assert!(!hf.iter().any(|u| u.contains("evil")), "{hf:?}");
        assert!(hf.iter().any(|u| u == "https://ok.mirror.cn"));
        let lfs = lfs_bases(root);
        assert_eq!(lfs, vec![crate::engine_assets::CNB_REPO.to_string()]);
    }

    #[test]
    fn user_endpoint_outranks_last_good() {
        let root = &scratch("userfirst");
        let mut patch = serde_json::Map::new();
        patch.insert("hf_endpoint".into(), json!("https://mine.mirror.cn"));
        patch.insert("hf_endpoint_last_good".into(), json!("https://last.mirror.cn"));
        config::update(root, patch).unwrap();
        let list = hf_endpoints(root);
        assert_eq!(list[0], "https://mine.mirror.cn");
        assert_eq!(list[1], "https://last.mirror.cn");
    }

    #[test]
    fn note_success_records_only_hf_origins() {
        let root = &scratch("note");
        note_success(root, "https://hf-mirror.com/org/repo/resolve/main/a.zip");
        assert_eq!(
            config::read(root).get("hf_endpoint_last_good").and_then(|v| v.as_str()),
            Some("https://hf-mirror.com")
        );
        // CNB 不是可互换的端点，不该覆盖掉刚记下的那个
        note_success(root, "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/lfs/abc");
        assert_eq!(
            config::read(root).get("hf_endpoint_last_good").and_then(|v| v.as_str()),
            Some("https://hf-mirror.com")
        );
    }

    #[test]
    fn origin_and_host() {
        assert_eq!(
            origin_of("https://a.b.cn/x/y").as_deref(),
            Some("https://a.b.cn")
        );
        assert_eq!(host_of("https://a.b.cn/x/y"), "a.b.cn");
        assert_eq!(origin_of("ftp://a.b.cn"), None);
    }
}
