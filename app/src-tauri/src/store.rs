//! Community voice store: catalog fetch + zip/files install.
//! Mirrors launcher/online/catalog.py + voice_install.py (subset for stage 4).

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;

use serde_json::{json, Map, Value};
use sha2::Digest;
use tauri::{AppHandle, Emitter};

use crate::download::{self, DownloadKind, DownloadRequest};
use crate::paths;
use crate::voices::safe_model_dir_name;

const CNB_RAW_MAIN: &str = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main";
const MIN_PTH_BYTES: u64 = 50_000;

fn progress_message(phase: &str) -> String {
    download::parse_retry_attempt(phase)
        .map(|n| crate::i18n::te("s.dlReconnect", &n))
        .unwrap_or_else(|| phase.to_string())
}

fn store_progress_payload(id: &str, phase: &str, done: u64, total: u64, message: &str) -> Value {
    let total = total.max(1);
    json!({
        "voice_id": id,
        "phase": phase,
        "done": done,
        "total": total,
        "percent": download::progress_percent(done, total),
        "message": message,
    })
}

/// Expand a catalog URL to the download list. HF links become the domestic
/// mirror chain. Official CNB packs also get a sha256 LFS fallback so a
/// hanging `/-/releases/download/` endpoint can fail over.
///
/// 镜像顺序由 `mirrors::hf_endpoints` 解出来（用户指定 → 上次成功 → 清单
/// 下发 → 编译进来的兜底），不再是写死在 `hf.rs` 里的那一串。
fn voice_download_urls(root: &Path, url: &str, sha: &str) -> Vec<String> {
    let mut urls = crate::hf::download_urls_with(url, &crate::mirrors::hf_endpoints(root));
    let sha: String = sha
        .chars()
        .filter(|c| c.is_ascii_hexdigit())
        .collect::<String>()
        .to_ascii_lowercase();
    if sha.len() == 64
        && (url.contains("cnb.cool") || url.contains("/-/releases/download/"))
    {
        for base in crate::mirrors::lfs_bases(root) {
            let lfs = format!("{base}/-/lfs/{sha}");
            if !urls.iter().any(|u| u == &lfs) {
                urls.push(lfs);
            }
        }
    }
    urls
}

/// .index 没有 sha（清单里常常缺），所以只做镜像展开。
fn index_urls(root: &Path, url: &str) -> Vec<String> {
    crate::hf::download_urls_with(url, &crate::mirrors::hf_endpoints(root))
}

/// Per-voice cancel flags. A single global flag meant that cancelling one
/// download killed every other in-flight one, and that starting a second
/// install reset the first one's cancel state — so concurrent installs were
/// unsafe and the UI had to serialise them.
static STORE_CANCELS: std::sync::Mutex<Option<HashMap<String, Arc<AtomicBool>>>> =
    std::sync::Mutex::new(None);

fn cancel_flag_for(id: &str) -> Arc<AtomicBool> {
    let mut g = STORE_CANCELS.lock().unwrap_or_else(|e| e.into_inner());
    let map = g.get_or_insert_with(HashMap::new);
    let flag = map
        .entry(id.to_string())
        .or_insert_with(|| Arc::new(AtomicBool::new(false)))
        .clone();
    flag.store(false, Ordering::SeqCst);
    flag
}

fn drop_cancel_flag(id: &str) {
    let mut g = STORE_CANCELS.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(map) = g.as_mut() {
        map.remove(id);
    }
}

pub(crate) fn bundled_catalog_path(root: &Path) -> PathBuf {
    root.join("configs").join("online_catalog.json")
}

pub(crate) fn cache_catalog_path(root: &Path) -> PathBuf {
    paths::user_data(root).join("catalog_cache.json")
}

fn parse_voice_entry(d: &Value, force_official: Option<bool>) -> Option<Value> {
    if !d.is_object() {
        return None;
    }
    let id = d
        .get("id")
        .or_else(|| d.get("name"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    if id.is_empty() {
        return None;
    }
    let mut cover = d
        .get("cover_url")
        .or_else(|| d.get("cover"))
        .or_else(|| d.get("banner"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    if !cover.is_empty()
        && !cover.to_ascii_lowercase().starts_with("http://")
        && !cover.to_ascii_lowercase().starts_with("https://")
    {
        cover = format!(
            "{CNB_RAW_MAIN}/{}",
            cover.replace('\\', "/").trim_start_matches('/')
        );
    }
    let pack_url = d
        .get("pack_url")
        .or_else(|| d.get("zip_url"))
        .or_else(|| d.get("pack"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let pth_url = d
        .get("pth_url")
        .or_else(|| d.get("pth"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    if pack_url.is_empty() && pth_url.is_empty() {
        return None;
    }
    let mut official = true;
    if let Some(f) = force_official {
        official = f;
    } else if let Some(v) = d.get("official").or_else(|| d.get("fabric_official")) {
        if let Some(b) = v.as_bool() {
            official = b;
        } else if let Some(s) = v.as_str() {
            official = !matches!(s.to_ascii_lowercase().as_str(), "0" | "false" | "no" | "n" | "");
        }
    }
    let author = d
        .get("author")
        .or_else(|| d.get("creator"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let size = d
        .get("size_bytes")
        .or_else(|| d.get("size"))
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    // Multilingual labels (optional). Frontend picks by ui_locale; English UI
    // shows "name_ja name_en" when both exist.
    let name_ja = d
        .get("name_ja")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let name_en = d
        .get("name_en")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let name_zh_hant = d
        .get("name_zh_Hant")
        .or_else(|| d.get("name_zh_hant"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let series = d
        .get("series")
        .or_else(|| d.get("series_name"))
        .or_else(|| d.get("collection"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let series_ja = d
        .get("series_ja")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let series_en = d
        .get("series_en")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let series_zh_hant = d
        .get("series_zh_Hant")
        .or_else(|| d.get("series_zh_hant"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let mut out = json!({
        "id": id,
        "name": d.get("name").and_then(|v| v.as_str()).unwrap_or(&id),
        "name_ja": name_ja,
        "name_en": name_en,
        "name_zh_Hant": name_zh_hant,
        "tag": d.get("tag").and_then(|v| v.as_str()).unwrap_or(&crate::i18n::t("s.c4301894a2")),
        "version": d.get("version").and_then(|v| v.as_str()).unwrap_or("1"),
        "package_type": d.get("package_type").or_else(|| d.get("type")).and_then(|v| v.as_str()).unwrap_or(""),
        "pack_url": pack_url,
        "pth_url": pth_url,
        "index_url": d.get("index_url").and_then(|v| v.as_str()).unwrap_or(""),
        "index_sha256": d.get("index_sha256").and_then(|v| v.as_str()).unwrap_or(""),
        "cover_url": cover,
        "size_bytes": size,
        "sha256": d.get("sha256").and_then(|v| v.as_str()).unwrap_or(""),
        "description": d.get("description").or_else(|| d.get("desc")).and_then(|v| v.as_str()).unwrap_or(""),
        "author": author,
        "author_url": d.get("author_url").or_else(|| d.get("author_link")).and_then(|v| v.as_str()).unwrap_or(""),
        "date": d.get("date").or_else(|| d.get("released")).and_then(|v| v.as_str()).unwrap_or(""),
        "series": series,
        "series_ja": series_ja,
        "series_en": series_en,
        "series_zh_Hant": series_zh_hant,
        "group": d.get("group").and_then(|v| v.as_str()).unwrap_or(""),
        "origin": d.get("origin").and_then(|v| v.as_str()).unwrap_or(""),
        "source_url": d.get("source_url").or_else(|| d.get("repo_url")).and_then(|v| v.as_str()).unwrap_or(""),
        "official": official,
    });
    // 上面那张表是**白名单**：没列的字段一律丢掉。清单里的 `name_i18n` /
    // `tag_i18n` / `description_i18n` 就是这么被吃掉的 —— 广场页拿不到译名，
    // 装到本地的 config.json 里更没有，于是英文界面下载 Chihaya Anon，
    // 模型页显示的还是「千早爱音」。
    //
    // ko / es / fr / ru 也一样：上面只单挑了 ja / en / zh_Hant 三个扁平别名，
    // 剩下四种语言压根没往下传。
    //
    // 这里把所有多语言字段整段搬过去，不再一个个列。
    if let Some(obj) = out.as_object_mut() {
        let mut extra = Map::new();
        copy_i18n_fields(d, &mut extra);
        for (k, v) in extra {
            obj.entry(k).or_insert(v);
        }
    }
    Some(out)
}

fn parse_voice_list(raw: &Value, force_official: Option<bool>) -> Vec<Value> {
    let Some(arr) = raw.as_array() else {
        return Vec::new();
    };
    arr.iter()
        .filter_map(|item| parse_voice_entry(item, force_official))
        .collect()
}

fn catalog_from_data(data: &Value, source: &str) -> Value {
    let voices = parse_voice_list(
        data.get("voices")
            .or_else(|| data.get("models"))
            .unwrap_or(&json!([])),
        None,
    );
    let thirdparty = parse_voice_list(
        data.get("thirdparty_voices")
            .or_else(|| data.get("third_party_voices"))
            .unwrap_or(&json!([])),
        Some(false),
    );
    json!({
        "source": source,
        "voices": voices,
        "thirdparty_voices": thirdparty,
        "fetch_error": "",
    })
}

fn is_voice_installed(root: &Path, voice_id: &str) -> bool {
    let Ok(name) = safe_model_dir_name(voice_id) else {
        return false;
    };
    let dir = paths::models_dir(root).join(name);
    if !dir.is_dir() {
        return false;
    }
    // has any .pth
    if let Ok(rd) = fs::read_dir(&dir) {
        for e in rd.flatten() {
            if e.path()
                .extension()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .eq_ignore_ascii_case("pth")
            {
                return true;
            }
        }
    }
    false
}

/// Fetch / merge online catalog; annotate installed flags.
pub fn fetch_store_catalog(root: &Path, prefer_remote: bool) -> Value {
    let _ = paths::ensure_user_dirs(root);
    let mut data = json!({});
    let mut source = "empty";
    let mut fetch_error = String::new();

    // bundled
    let bundled = bundled_catalog_path(root);
    if bundled.is_file() {
        if let Ok(s) = fs::read_to_string(&bundled) {
            if let Ok(v) = serde_json::from_str::<Value>(&s) {
                data = v;
                source = "bundled";
            }
        }
    }
    // Last successful remote snapshot. Prefer it over the catalog baked into
    // the exe: that one is frozen at build time, so a later store publish
    // would never show up after install (refresh(false) used to reload
    // bundled and wipe the just-fetched list).
    let cache_p = cache_catalog_path(root);
    let cached = if cache_p.is_file() {
        fs::read_to_string(&cache_p)
            .ok()
            .and_then(|s| serde_json::from_str::<Value>(&s).ok())
    } else {
        None
    };
    if let Some(v) = cached.clone() {
        data = v;
        source = "cache";
    }

    if prefer_remote {
        // 用户点了刷新：必须走不带 5 分钟内存缓存、并绕过 CDN 的那条。
        // 以前用 fetch_remote_catalog_cached，启动时 provision 先拉一次旧清单，
        // 五分钟内再点刷新还是那份，新上架的音色出不来。
        match crate::catalog::fetch_remote_catalog(25) {
            Ok(remote) => {
                data = remote;
                source = "remote";
                if let Ok(text) = serde_json::to_string_pretty(&data) {
                    let _ = fs::write(&cache_p, text);
                }
            }
            Err(e) => {
                fetch_error = e;
                if let Some(v) = cached {
                    data = v;
                    source = "cache";
                } else if source == "empty" {
                    source = "error";
                }
            }
        }
    }

    let mut cat = catalog_from_data(&data, source);
    if let Some(obj) = cat.as_object_mut() {
        obj.insert("fetch_error".into(), json!(fetch_error));
    }

    // annotate installed
    for key in ["voices", "thirdparty_voices"] {
        if let Some(arr) = cat.get_mut(key).and_then(|v| v.as_array_mut()) {
            for v in arr.iter_mut() {
                if let Some(obj) = v.as_object_mut() {
                    let id = obj
                        .get("id")
                        .and_then(|x| x.as_str())
                        .unwrap_or("")
                        .to_string();
                    obj.insert(
                        "installed".into(),
                        json!(is_voice_installed(root, &id)),
                    );
                    let origin = obj
                        .get("origin")
                        .and_then(|x| x.as_str())
                        .unwrap_or("")
                        .to_string();
                    let official = obj
                        .get("official")
                        .and_then(|x| x.as_bool())
                        .unwrap_or(true);
                    let origin_label = origin_label_for(&origin, official);
                    obj.insert("origin_label".into(), json!(origin_label));
                    let size = obj.get("size_bytes").and_then(|x| x.as_u64()).unwrap_or(0);
                    obj.insert("size_label".into(), json!(format_size(size)));
                    let cover_hint = obj
                        .get("cover_url")
                        .and_then(|x| x.as_str())
                        .or_else(|| obj.get("cover").and_then(|x| x.as_str()))
                        .unwrap_or("");
                    if let Some(local) = local_banner_for_hint(root, cover_hint) {
                        obj.insert("cover_local".into(), json!(local));
                    }
                }
            }
        }
    }
    cat
}

/// 清单 `origin` 是站点代号（huggingface），不能直接给人看。
/// `te()` 只替换 `{e}`/`{a0}`/`{}`，旧代码拿它填 `{origin}`，卡片上就印着
/// 「第三方 · {origin}」。
fn origin_display_name(origin: &str) -> String {
    let trimmed = origin.trim();
    match trimmed.to_ascii_lowercase().as_str() {
        "huggingface" | "hf" | "hugging-face" => "Hugging Face".into(),
        "cnb" => "CNB".into(),
        other if !other.is_empty() => trimmed.to_string(),
        _ => String::new(),
    }
}

fn origin_label_for(origin: &str, official: bool) -> String {
    if official {
        return if origin.trim().is_empty() {
            crate::i18n::t("s.7c134b6e64")
        } else {
            origin_display_name(origin)
        };
    }
    let shown = origin_display_name(origin);
    if shown.is_empty() {
        return crate::i18n::t("s.4500b5dfc7");
    }
    let mut vars = std::collections::HashMap::new();
    vars.insert("origin".into(), shown);
    crate::i18n::t_vars("s.d03c6cb553", &vars)
}

/// 封面本地化缓存：批量把远程封面 URL 下载到 `User_Data/cover_cache/`，
/// 键 = URL 的 sha256 前缀。一次成功永久可用 —— WebView 不再每次打开商店
/// 全量重拉远程封面，国内访问 CNB 间歇失败导致的随机缺图在这里根治。
/// 返回 url → 本地缓存路径；下载失败的条目是空串，前端回退远程直连。
pub fn resolve_covers(root: &Path, urls: &[String]) -> Map<String, Value> {
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Mutex;
    let out: Mutex<Map<String, Value>> = Mutex::new(Map::new());
    let next = AtomicUsize::new(0);
    let lanes = urls.len().clamp(1, 8); // 封面是小图，8 路并行加快批次返回，少拖后腿
    std::thread::scope(|s| {
        for _ in 0..lanes {
            s.spawn(|| loop {
                let i = next.fetch_add(1, Ordering::Relaxed);
                if i >= urls.len() {
                    break;
                }
                let r = resolve_cover_url(root, &urls[i]);
                out.lock()
                    .unwrap_or_else(|e| e.into_inner())
                    .insert(urls[i].clone(), json!(r.unwrap_or_default()));
            });
        }
    });
    out.into_inner().unwrap_or_default()
}

fn resolve_cover_url(root: &Path, url: &str) -> Result<String, String> {
    if !url.starts_with("http://") && !url.starts_with("https://") {
        return Ok(url.to_string()); // 非 http（如 asset://）原样返回
    }
    // 本机有图就先用：远程 404 / 国内访问 CNB 挂掉时，优香这类条目不再空白。
    if let Some(local) = local_banner_for_hint(root, url) {
        return Ok(local);
    }
    let dir = paths::user_data(root).join("cover_cache");
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let key = hex::encode(sha2::Sha256::digest(url.as_bytes()));
    let dest = dir.join(format!("{}.jpg", &key[..24]));
    if dest.is_file() && dest.metadata().map(|m| m.len()).unwrap_or(0) > 100 {
        return Ok(dest.to_string_lossy().into_owned());
    }
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(8)) // 封面几十 KB，8 秒足够；挂了快速失败交给前端重试
        .build()
        .map_err(|e| e.to_string())?;
    let mut last_err = String::new();
    for cand in cover_download_candidates(url) {
        match fetch_cover_bytes(&client, &cand) {
            Ok(bytes) => {
                let tmp = dir.join(format!("{}.tmp", &key[..24]));
                fs::write(&tmp, &bytes).map_err(|e| e.to_string())?;
                fs::rename(&tmp, &dest).map_err(|e| e.to_string())?;
                return Ok(dest.to_string_lossy().into_owned());
            }
            Err(e) => last_err = e,
        }
    }
    local_banner_for_hint(root, url).ok_or(last_err)
}

fn fetch_cover_bytes(
    client: &reqwest::blocking::Client,
    url: &str,
) -> Result<Vec<u8>, String> {
    let resp = client.get(url).send().map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("HTTP {}", resp.status()));
    }
    let bytes = resp.bytes().map_err(|e| e.to_string())?;
    // 封面是几十 KB 的 jpg；小于 100B 不像图，大于 8MB 不像封面。
    if bytes.len() < 100 || bytes.len() > 8 * 1024 * 1024 {
        return Err(format!("unexpected size {}", bytes.len()));
    }
    Ok(bytes.to_vec())
}

/// 发布附件 404 时再试 git-raw（ch-banner 进仓、covers 标签可能漏传）。
fn cover_download_candidates(url: &str) -> Vec<String> {
    let mut out = vec![url.to_string()];
    if let Some(name) = banner_file_name(url) {
        let raw = format!("{CNB_RAW_MAIN}/ch-banner/{name}");
        if raw != url {
            out.push(raw);
        }
    }
    out
}

fn banner_file_name(hint: &str) -> Option<String> {
    let name = hint
        .rsplit(['/', '\\'])
        .next()?
        .split('?')
        .next()?
        .trim();
    if name.is_empty() || name.contains("..") {
        return None;
    }
    Some(name.to_string())
}

/// 远程封面挂了时，用文件名去本机 ch-banner 里找（开发仓 / 已缓存的封面）。
fn local_banner_for_url(root: &Path, url: &str) -> Option<String> {
    local_banner_for_hint(root, url)
}

fn local_banner_for_hint(root: &Path, hint: &str) -> Option<String> {
    let name = banner_file_name(hint)?;
    let dirs = [
        paths::ch_banner_dir(root),
        root.join("ch-banner"),
        root.join("CNB-GIT-RELEASE").join("ch-banner"),
    ];
    for base in dirs {
        let p = base.join(&name);
        if p.is_file() && p.metadata().map(|m| m.len()).unwrap_or(0) > 100 {
            return Some(p.to_string_lossy().into_owned());
        }
    }
    None
}

fn format_size(n: u64) -> String {
    if n == 0 {
        return String::new();
    }
    if n >= 1024 * 1024 * 1024 {
        return format!("{:.1} GB", n as f64 / (1024.0 * 1024.0 * 1024.0));
    }
    if n >= 1024 * 1024 {
        return format!("{:.0} MB", n as f64 / (1024.0 * 1024.0));
    }
    if n >= 1024 {
        return format!("{:.0} KB", n as f64 / 1024.0);
    }
    format!("{n} B")
}

// ---------------------------------------------------------------------------
// safe zip extract
// ---------------------------------------------------------------------------

/// Voice packs go through the same extractor as every other archive.
///
/// This used to be a second, near-identical implementation. Two copies of a
/// path-safety check is one copy too many — the one in `extract` is the one
/// with tests.
fn safe_extract_zip(zip_path: &Path, dest: &Path) -> Result<(), String> {
    crate::extract::extract_zip(zip_path, dest).map_err(|e| crate::i18n::te("s.007e8f085e", &(e)))
}

fn find_content_root(tmp: &Path) -> PathBuf {
    // If single top-level dir containing .pth, use it
    let Ok(rd) = fs::read_dir(tmp) else {
        return tmp.to_path_buf();
    };
    let entries: Vec<_> = rd.flatten().map(|e| e.path()).collect();
    if entries.len() == 1 && entries[0].is_dir() {
        return entries[0].clone();
    }
    // find dir that has pth
    if find_first(tmp, "pth").is_some() {
        return tmp.to_path_buf();
    }
    for e in &entries {
        if e.is_dir() && find_first(e, "pth").is_some() {
            return e.clone();
        }
    }
    tmp.to_path_buf()
}

fn find_first(dir: &Path, ext: &str) -> Option<PathBuf> {
    fn walk(d: &Path, ext: &str, depth: u32) -> Option<PathBuf> {
        if depth > 4 {
            return None;
        }
        let rd = fs::read_dir(d).ok()?;
        let mut files = Vec::new();
        let mut dirs = Vec::new();
        for e in rd.flatten() {
            let p = e.path();
            if p.is_file() {
                if p.extension()
                    .and_then(|s| s.to_str())
                    .unwrap_or("")
                    .eq_ignore_ascii_case(ext)
                {
                    files.push(p);
                }
            } else if p.is_dir() {
                dirs.push(p);
            }
        }
        files.sort();
        if let Some(f) = files.into_iter().next() {
            return Some(f);
        }
        for d in dirs {
            if let Some(f) = walk(&d, ext, depth + 1) {
                return Some(f);
            }
        }
        None
    }
    walk(dir, ext, 0)
}

/// 清单条目里所有多语言字段，原样搬进本地音色的 `config.json`。
///
/// 清单里 `name` 是中文主名（千早爱音），`name_i18n` 才是各语言的写法。装的时候
/// 只留下 `name`，模型页就只能显示中文 —— 用户在英文环境下下载 Chihaya Anon，
/// 装完看到的是「千早爱音」。
///
/// 存整张表而不是「按下载时的语言挑一个存下来」：用户之后换语言，模型页要跟着
/// 变。挑一个存等于把当时的语言焊死在磁盘上。
///
/// `pick_str` 除了 `x_i18n` 这种表，还认 `name_en` / `name_zh_Hant` 这类扁平写法
/// （第三方源手写 YAML 常用），所以这里两种都搬。
/// 清单封面（`cover_url` / `cover`）—— 第三方包自己不带封面文件，封面
/// URL 只在清单里。装进 sidecar 的 `cover` 字段后，`voices` 列表的
/// `resolve_cover` 对 http(s) 直通，模型页/首页直接 `<img src>` 拉远程。
fn entry_cover(entry: &Value) -> Option<Value> {
    let v = entry.get("cover_url").or_else(|| entry.get("cover"))?;
    let s = v.as_str().unwrap_or("").trim();
    if s.is_empty() {
        return None;
    }
    Some(v.clone())
}

fn copy_i18n_fields(entry: &Value, extra: &mut Map<String, Value>) {
    let Some(obj) = entry.as_object() else { return };
    const FIELDS: [&str; 6] = ["name", "tag", "series", "author", "description", "group"];
    for (k, v) in obj {
        let Some((field, rest)) = k.split_once('_') else {
            continue;
        };
        if rest.is_empty() || !FIELDS.contains(&field) {
            continue;
        }
        // `author_url` 是地址不是译名，上面那个循环已经单独搬过了。
        if k == "author_url" {
            continue;
        }
        extra.entry(k.clone()).or_insert_with(|| v.clone());
    }
}

fn write_voice_config(
    dest_dir: &Path,
    dest_pth: &Path,
    name: &str,
    tag: &str,
    online_id: &str,
    index_path: &str,
    source: &str,
    official: bool,
    extra: &Map<String, Value>,
) -> Value {
    let mut side = Map::new();
    side.insert("name".into(), json!(name));
    side.insert("tag".into(), json!(tag));
    side.insert(
        "file".into(),
        json!(dest_pth.file_name().and_then(|s| s.to_str()).unwrap_or("")),
    );
    side.insert("source".into(), json!(source));
    side.insert("online_id".into(), json!(online_id));
    side.insert("fabric_official".into(), json!(official));
    if !index_path.is_empty() {
        side.insert("index".into(), json!(index_path));
        side.insert("index_files".into(), json!([index_path]));
    }
    for (k, v) in extra {
        if !side.contains_key(k) {
            side.insert(k.clone(), v.clone());
        }
    }
    let path = dest_dir.join("config.json");
    if let Ok(text) = serde_json::to_string_pretty(&Value::Object(side.clone())) {
        let _ = fs::write(path, text);
    }
    json!({
        "name": name,
        "path": dest_pth.to_string_lossy(),
        "file": dest_pth.file_name().and_then(|s| s.to_str()).unwrap_or(""),
        "dir": dest_dir.to_string_lossy(),
        "index": index_path,
        "tag": tag,
        "source": "user_data",
        "online_id": online_id,
    })
}

/// 每次安装一份独立的解压目录，并发装两个音色才不会互相踩。
fn unique_voice_extract_dir(root: &Path, voice_id: &str) -> PathBuf {
    static SEQ: AtomicU64 = AtomicU64::new(1);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let safe: String = voice_id
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '-' || c == '_' {
                c
            } else {
                '_'
            }
        })
        .take(48)
        .collect();
    let safe = if safe.is_empty() {
        "voice".to_string()
    } else {
        safe
    };
    paths::update_cache(root).join(format!(
        "voice_extract_{safe}_{}_{seq}",
        std::process::id()
    ))
}

/// Install a local voice_pack zip into User_Data/models/<id>/.
/// `entry` 是清单里那条（广场下载时有，本地导入 zip 时没有）。它带着
/// `name_i18n` 之类的多语言字段，装进本地 `config.json` 才能让模型页按当前
/// 语言显示名字。
#[allow(clippy::too_many_arguments)]
pub fn install_voice_pack_zip(
    root: &Path,
    zip_path: &Path,
    voice_id: &str,
    display_name: &str,
    tag: &str,
    official: bool,
    entry: Option<&Value>,
) -> Result<Value, String> {
    if !zip_path.is_file() {
        return Err(crate::i18n::te("s.760364197e", &(zip_path.display())));
    }
    // 以前按壳进程 pid 共用一个解压目录。广场允许同时下多个音色（26.8.24
    // 一秒内点了 Serika-JP 和 Serika-ZH），两个 zip 解到同一处、一个装完
    // remove_dir_all 另一个还在写，Windows 就报目录被占用。
    let tmp = unique_voice_extract_dir(root, voice_id);
    let _ = fs::remove_dir_all(&tmp);
    fs::create_dir_all(&tmp).map_err(|e| e.to_string())?;
    let result = (|| {
        safe_extract_zip(zip_path, &tmp)?;
        let content = find_content_root(&tmp);
        let pth = find_first(&content, "pth")
            .ok_or_else(|| crate::i18n::t("s.41e7454584"))?;
        let size = pth.metadata().map(|m| m.len()).unwrap_or(0);
        if size < MIN_PTH_BYTES {
            return Err(crate::i18n::t("s.713173a2d7").into());
        }
        // optional pack config
        let pack_cfg = {
            let cfg = content.join("config.json");
            if cfg.is_file() {
                fs::read_to_string(cfg)
                    .ok()
                    .and_then(|s| serde_json::from_str::<Value>(&s).ok())
                    .and_then(|v| v.as_object().cloned())
                    .unwrap_or_default()
            } else {
                Map::new()
            }
        };
        let vid = safe_model_dir_name(
            if !voice_id.is_empty() {
                voice_id
            } else if let Some(s) = pack_cfg
                .get("voice_id")
                .or_else(|| pack_cfg.get("id"))
                .and_then(|v| v.as_str())
            {
                s
            } else if !display_name.is_empty() {
                display_name
            } else {
                zip_path
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or("voice")
            },
        )?;
        let name = if !display_name.is_empty() {
            display_name.to_string()
        } else {
            pack_cfg
                .get("name")
                .and_then(|v| v.as_str())
                .unwrap_or(&vid)
                .to_string()
        };
        let tag = if tag.is_empty() {
            pack_cfg
                .get("tag")
                .and_then(|v| v.as_str())
                .unwrap_or(&crate::i18n::t("s.c4301894a2"))
                .to_string()
        } else {
            tag.to_string()
        };
        let dest_dir = paths::models_dir(root).join(&vid);
        if dest_dir.is_dir() {
            // clear previous
            for e in fs::read_dir(&dest_dir).map_err(|e| e.to_string())? {
                let p = e.map_err(|e| e.to_string())?.path();
                if p.is_file() {
                    let _ = fs::remove_file(&p);
                } else if p.is_dir() {
                    let _ = fs::remove_dir_all(&p);
                }
            }
        }
        fs::create_dir_all(&dest_dir).map_err(|e| e.to_string())?;
        let dest_pth = dest_dir.join(pth.file_name().unwrap_or_default());
        fs::copy(&pth, &dest_pth).map_err(|e| crate::i18n::te("s.8c8dade1e1", &(e)))?;

        let mut index_path = String::new();
        if let Some(idx) = find_first(&content, "index") {
            if idx.metadata().map(|m| m.len()).unwrap_or(0) > 1000 {
                let dest_idx = dest_dir.join(idx.file_name().unwrap_or_default());
                fs::copy(&idx, &dest_idx).map_err(|e| e.to_string())?;
                index_path = dest_idx
                    .canonicalize()
                    .unwrap_or(dest_idx)
                    .to_string_lossy()
                    .into_owned();
            }
        }
        // cover
        for name in ["cover.png", "cover.jpg", "cover.jpeg", "cover.webp"] {
            let c = content.join(name);
            if c.is_file() {
                let _ = fs::copy(&c, dest_dir.join(name));
                break;
            }
        }
        // copy profiles if present
        let prof_src = content.join("profiles");
        if prof_src.is_dir() {
            let prof_dst = dest_dir.join("profiles");
            let _ = fs::create_dir_all(&prof_dst);
            if let Ok(rd) = fs::read_dir(&prof_src) {
                for e in rd.flatten() {
                    let p = e.path();
                    if p.is_file() {
                        let _ = fs::copy(&p, prof_dst.join(p.file_name().unwrap_or_default()));
                    }
                }
            }
        }

        let mut extra = Map::new();
        for k in [
            "author",
            "author_url",
            "source_url",
            "date",
            "series",
            "group",
            "cover",
        ] {
            if let Some(v) = pack_cfg.get(k) {
                extra.insert(k.to_string(), v.clone());
            }
        }
        // 作者主页 / 来源仓库多半只写在清单里 —— 第三方的 zip 是别人打的包，
        // 里面那份 config.json 通常只有名字和标签。不从 entry 兜底，装完的
        // 音色就再也查不到它是从哪来的、是谁做的。
        if let Some(e) = entry {
            for k in ["author_url", "source_url"] {
                if extra.contains_key(k) {
                    continue;
                }
                if let Some(v) = e.get(k).filter(|v| !v.as_str().unwrap_or("").is_empty()) {
                    extra.insert(k.to_string(), v.clone());
                }
            }
        }
        // 第三方 zip 里没有 cover，封面 URL 只在清单 —— 不补上，安装后的
        // 模型页/首页就永远没有封面（官方包自带 cover 已优先，不受影响）。
        if !extra.contains_key("cover") {
            if let Some(v) = entry.and_then(entry_cover) {
                extra.insert("cover".into(), v);
            }
        }
        // 多语言字段：清单里那条优先（广场下载走这条），包里自带的兜底
        // （第三方 zip 自己写的 config.json）。
        if let Some(e) = entry {
            copy_i18n_fields(e, &mut extra);
        }
        copy_i18n_fields(&Value::Object(pack_cfg.clone()), &mut extra);
        let source = if official {
            "online_pack"
        } else {
            "thirdparty_pack"
        };
        Ok(write_voice_config(
            &dest_dir,
            &dest_pth,
            &name,
            &tag,
            &vid,
            &index_path,
            source,
            official,
            &extra,
        ))
    })();
    let _ = fs::remove_dir_all(&tmp);
    result
}

/// Download + install one catalog voice entry.
pub fn install_voice_entry(
    app: AppHandle,
    root: PathBuf,
    entry: Value,
) -> Result<Value, String> {
    let id = entry
        .get("id")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let name = entry
        .get("name")
        .and_then(|v| v.as_str())
        .unwrap_or(&id)
        .to_string();
    let tag = entry
        .get("tag")
        .and_then(|v| v.as_str())
        .unwrap_or(&crate::i18n::t("s.c4301894a2"))
        .to_string();
    let official = entry
        .get("official")
        .and_then(|v| v.as_bool())
        .unwrap_or(true);
    let pack_url = entry
        .get("pack_url")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let pth_url = entry
        .get("pth_url")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let sha = entry
        .get("sha256")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let size = entry
        .get("size_bytes")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);

    // download_request skips verification when the expected hash is empty.
    // A .pth is an untrusted pickle — it must never be installed unverified,
    // whatever the catalog happens to contain.
    if sha.chars().filter(|c| c.is_ascii_hexdigit()).count() != 64 {
        crate::logging::shell_log!(format!("store install reject id={id}: missing sha256"));
        return Err(crate::i18n::te("s.40dc667415", &(id)));
    }

    crate::logging::shell_log!(format!(
        "store install start id={id} official={official} form={} size={size}",
        if !pack_url.is_empty() { "pack" } else { "files" }
    ));

    let emit = |phase: &str, done: u64, total: u64, message: &str| {
        let _ = app.emit(
            "store-progress",
            store_progress_payload(&id, phase, done, total, message),
        );
    };

    emit("start", 0, size.max(1), &crate::i18n::te("s.1cf582864a", &(name)));

    // 第三方一律先落暂存区，下完不装 —— .pth 是 pickle，加载即执行代码，
    // 而它来自社区站点不是我们的仓库。哈希只能证明「下到的就是清单里那个」，
    // 证明不了那个文件本身干净。让用户自己先看一眼。
    let stage_only = !official;

    // HF 清单写规范域；下载时扩成镜像列表 —— 见 `voice_download_urls`。
    if !pack_url.is_empty() {
        let vid = safe_model_dir_name(if id.is_empty() { &name } else { &id })?;
        let cache = if stage_only {
            staged_dir(&root, if id.is_empty() { &name } else { &id })?
        } else {
            paths::update_cache(&root).join("voice_packs")
        };
        fs::create_dir_all(&cache).map_err(|e| e.to_string())?;
        let zpath = cache.join(format!("{vid}.zip"));
        // This download's own flag — cancelling another voice must not touch it.
        let cancel = cancel_flag_for(&id);
        let cancel_flag = cancel.clone();

        let app2 = app.clone();
        let id2 = id.clone();
        let progress: download::ProgressFn = Arc::new(move |done, total, msg| {
            let _ = app2.emit(
                "store-progress",
                store_progress_payload(&id2, "download", done, total, &progress_message(msg)),
            );
        });

        let urls = voice_download_urls(&root, &pack_url, &sha);
        let res = download::download_request(
            DownloadRequest {
                urls,
                root: Some(root.clone()),
                dest: zpath.clone(),
                expected_sha256: sha,
                size_hint: size,
                connections: None,
                kind: DownloadKind::VoicePack,
            },
            cancel_flag,
            Some(progress),
        );
        drop_cancel_flag(&id);
        res?;
        if stage_only {
            emit("staged", 1, 1, &crate::i18n::t("s.1245a7db42"));
            return Ok(json!({
                "staged": true,
                "voice_id": id,
                "dir": cache.to_string_lossy(),
                "file": zpath.file_name().and_then(|s| s.to_str()).unwrap_or(""),
            }));
        }
        emit("extract", 0, 1, &crate::i18n::t("s.6b42cff431"));
        let info = install_voice_pack_zip(&root, &zpath, &id, &name, &tag, official, Some(&entry))?;
        emit("done", 1, 1, &crate::i18n::t("s.f423573349"));
        return Ok(info);
    }

    if pth_url.is_empty() {
        return Err(crate::i18n::t("s.5ca65185f2").into());
    }
    // multi-file install
    let vid = safe_model_dir_name(if id.is_empty() { &name } else { &id })?;
    let cache = if stage_only {
        staged_dir(&root, if id.is_empty() { &name } else { &id })?
    } else {
        paths::update_cache(&root).join("voices").join(&vid)
    };
    fs::create_dir_all(&cache).map_err(|e| e.to_string())?;
    let pth_tmp = cache.join(format!("{vid}.pth"));
    // 暂存模式下先不建音色目录 —— 用户可能看完就删，不该留一个空目录在
    // 音色库里让人以为装过。
    let dest_dir = paths::models_dir(&root).join(&vid);
    if !stage_only {
        fs::create_dir_all(&dest_dir).map_err(|e| e.to_string())?;
    }

    let cancel = cancel_flag_for(&id);
    let app2 = app.clone();
    let id2 = id.clone();
    let progress: download::ProgressFn = Arc::new(move |done, total, msg| {
        let _ = app2.emit(
            "store-progress",
            store_progress_payload(&id2, "pth", done, total, &progress_message(msg)),
        );
    });
    if let Err(e) = download::download_request(
        DownloadRequest {
            urls: voice_download_urls(&root, &pth_url, &sha),
            root: Some(root.clone()),
            dest: pth_tmp.clone(),
            expected_sha256: sha,
            // 0 而不是 size：voice_files 的 size_bytes 是 pth + index 的合计
            // （商店要显示用户实际下载的总量），拿它当单个 pth 的进度分母，
            // 进度会一直卡在一成左右然后突然跳完。Content-Length 有，够用。
            size_hint: 0,
            connections: None,
            kind: DownloadKind::VoicePack,
        },
        cancel.clone(),
        Some(progress),
    ) {
        drop_cancel_flag(&id);
        return Err(e);
    }
    if pth_tmp.metadata().map(|m| m.len()).unwrap_or(0) < MIN_PTH_BYTES {
        drop_cancel_flag(&id);
        return Err(crate::i18n::t("s.281cb87781").into());
    }

    if stage_only {
        // index 也一并拉到暂存区，用户要看就一次看全，装的时候也不用再联网。
        if let Some(iu) = entry.get("index_url").and_then(|v| v.as_str()) {
            if !iu.is_empty() {
                let idx_sha = entry
                    .get("index_sha256")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
                let _ = download::download_request(
                    DownloadRequest {
                        urls: index_urls(&root, iu),
                        root: Some(root.clone()),
                        dest: cache.join(format!("{vid}.index")),
                        expected_sha256: idx_sha,
                        size_hint: 0,
                        connections: Some(1),
                        kind: DownloadKind::Generic,
                    },
                    cancel.clone(),
                    None,
                );
            }
        }
        emit("staged", 1, 1, &crate::i18n::t("s.1245a7db42"));
        drop_cancel_flag(&id);
        return Ok(json!({
            "staged": true,
            "voice_id": id,
            "dir": cache.to_string_lossy(),
            "file": pth_tmp.file_name().and_then(|s| s.to_str()).unwrap_or(""),
        }));
    }

    // clear old pths
    if let Ok(rd) = fs::read_dir(&dest_dir) {
        for e in rd.flatten() {
            let p = e.path();
            if p.extension()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .eq_ignore_ascii_case("pth")
            {
                let _ = fs::remove_file(p);
            }
        }
    }
    let dest_pth = dest_dir.join(format!("{vid}.pth"));
    if let Err(e) = fs::copy(&pth_tmp, &dest_pth) {
        drop_cancel_flag(&id);
        return Err(e.to_string());
    }

    let mut index_path = String::new();
    if let Some(iu) = entry.get("index_url").and_then(|v| v.as_str()) {
        if !iu.is_empty() {
            let idx_tmp = cache.join(format!("{vid}.index"));
            // 清单带了 index 的哈希就校验。index 不是 pickle，风险比 pth 低，
            // 所以缺哈希时不像 pth 那样硬拒；但既然发布前验证过、值也记下来了，
            // 就没有理由不比对。
            let idx_sha = entry
                .get("index_sha256")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let _ = download::download_request(
                DownloadRequest {
                    urls: index_urls(&root, iu),
                    root: Some(root.clone()),
                    dest: idx_tmp.clone(),
                    expected_sha256: idx_sha,
                    size_hint: 0,
                    connections: Some(1),
                    kind: DownloadKind::Generic,
                },
                cancel.clone(),
                None,
            );
            if idx_tmp.is_file() && idx_tmp.metadata().map(|m| m.len()).unwrap_or(0) > 1000 {
                let dest_idx = dest_dir.join(format!("{vid}.index"));
                let _ = fs::copy(&idx_tmp, &dest_idx);
                index_path = dest_idx.to_string_lossy().into_owned();
            }
        }
    }

    let mut extra = Map::new();
    for k in ["author", "author_url", "source_url", "date", "series", "group"] {
        if let Some(v) = entry.get(k) {
            extra.insert(k.to_string(), v.clone());
        }
    }
    // 清单封面（voice_files 形态的第三方也没有包内 cover，全靠这一行）。
    if let Some(v) = entry_cover(&entry) {
        extra.insert("cover".into(), v);
    }
    let source = if official {
        "online_files"
    } else {
        "thirdparty_files"
    };
    let info = write_voice_config(
        &dest_dir,
        &dest_pth,
        &name,
        &tag,
        &vid,
        &index_path,
        source,
        official,
        &extra,
    );
    emit("done", 1, 1, &crate::i18n::t("s.f423573349"));
    drop_cancel_flag(&id);
    Ok(info)
}

// ---------------------------------------------------------------------------
// 第三方音色：下载完不自动装
// ---------------------------------------------------------------------------
//
// 第三方 .pth 是 pickle，加载即执行代码。哈希校验只能保证「你下到的就是清单
// 里那个文件」，不能保证那个文件本身安全 —— 清单里的地址指向社区站点，不是
// 我们的仓库。所以第三方一律先落到暂存区，用户自己看过再决定装不装。
//
// 官方源不走这条路：那些包是我们自己传的、自己签的哈希，没有中间环节。

/// 暂存区：`User_Data/downloads/<voice_id>/`。
///
/// 放在 User_Data 而不是缓存目录，因为用户要能用资源管理器找到它、能自己删。
/// 缓存目录是我们随时会清的地方，把用户要审查的东西放那儿是不负责任的。
pub fn staged_dir(root: &Path, voice_id: &str) -> Result<PathBuf, String> {
    let vid = safe_model_dir_name(voice_id)?;
    Ok(paths::user_data(root).join("downloads").join(vid))
}

/// 暂存区里有没有可安装的东西。zip 或 pth 有一个就算。
fn staged_payload(dir: &Path) -> Option<PathBuf> {
    let rd = fs::read_dir(dir).ok()?;
    let mut zip = None;
    let mut pth = None;
    for e in rd.flatten() {
        let p = e.path();
        match p.extension().and_then(|s| s.to_str()).map(str::to_ascii_lowercase) {
            Some(ref x) if x == "zip" => zip = Some(p),
            Some(ref x) if x == "pth" => pth = Some(p),
            _ => {}
        }
    }
    zip.or(pth)
}

/// 每个音色的暂存状态，给商店界面决定按钮显示什么。
pub fn staged_status(root: &Path) -> Value {
    let base = paths::user_data(root).join("downloads");
    let mut out = Map::new();
    if let Ok(rd) = fs::read_dir(&base) {
        for e in rd.flatten() {
            let p = e.path();
            if !p.is_dir() {
                continue;
            }
            let Some(id) = p.file_name().and_then(|s| s.to_str()) else {
                continue;
            };
            if let Some(f) = staged_payload(&p) {
                let size = f.metadata().map(|m| m.len()).unwrap_or(0);
                out.insert(
                    id.to_string(),
                    json!({
                        "dir": p.to_string_lossy(),
                        "file": f.file_name().and_then(|s| s.to_str()).unwrap_or(""),
                        "size_bytes": size,
                    }),
                );
            }
        }
    }
    Value::Object(out)
}

/// 在资源管理器里打开某个音色的暂存目录。
pub fn reveal_staged(root: &Path, voice_id: &str) -> Result<(), String> {
    let dir = staged_dir(root, voice_id)?;
    if !dir.is_dir() {
        return Err(crate::i18n::t("s.0c6c58c683").into());
    }
    crate::shell_extras::reveal(&dir.join("x"))
}

/// 丢掉暂存的文件（用户看完决定不装）。
pub fn discard_staged(root: &Path, voice_id: &str) -> Result<(), String> {
    let dir = staged_dir(root, voice_id)?;
    if dir.is_dir() {
        fs::remove_dir_all(&dir).map_err(|e| crate::i18n::te("s.80b25fdbcd", &(e)))?;
    }
    Ok(())
}

/// 把暂存的文件真正装进音色库。
///
/// `entry` 还是清单里那一条 —— 名字、标签、index 地址都在里面，装的时候要用。
pub fn install_staged(
    app: AppHandle,
    root: PathBuf,
    entry: Value,
) -> Result<Value, String> {
    let id = entry.get("id").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let name = entry.get("name").and_then(|v| v.as_str()).unwrap_or(&id).to_string();
    let tag = entry.get("tag").and_then(|v| v.as_str()).unwrap_or(&crate::i18n::t("s.c4301894a2")).to_string();
    let official = entry.get("official").and_then(|v| v.as_bool()).unwrap_or(false);

    let dir = staged_dir(&root, if id.is_empty() { &name } else { &id })?;
    let payload = staged_payload(&dir).ok_or(crate::i18n::t("s.361cb27e7b"))?;

    let emit = |phase: &str, message: &str| {
        let _ = app.emit(
            "store-progress",
            json!({ "voice_id": id, "phase": phase, "done": 1, "total": 1,
                    "percent": 100, "message": message }),
        );
    };
    emit("extract", &crate::i18n::t("s.e0ce99ef5b"));

    let is_zip = payload
        .extension()
        .and_then(|s| s.to_str())
        .map(|s| s.eq_ignore_ascii_case("zip"))
        .unwrap_or(false);

    let info = if is_zip {
        install_voice_pack_zip(&root, &payload, &id, &name, &tag, official, Some(&entry))?
    } else {
        install_staged_files(&root, &dir, &payload, &id, &name, &tag, official, &entry)?
    };
    // 装完就把暂存清掉，不然用户的 User_Data 会慢慢堆满几百 MB 的重复文件。
    let _ = fs::remove_dir_all(&dir);
    emit("done", &crate::i18n::t("s.f423573349"));
    Ok(info)
}

/// 多文件形态（pth + 可选 index）的暂存安装。
#[allow(clippy::too_many_arguments)]
fn install_staged_files(
    root: &Path,
    dir: &Path,
    pth: &Path,
    id: &str,
    name: &str,
    tag: &str,
    official: bool,
    entry: &Value,
) -> Result<Value, String> {
    let vid = safe_model_dir_name(if id.is_empty() { name } else { id })?;
    let dest_dir = paths::models_dir(root).join(&vid);
    fs::create_dir_all(&dest_dir).map_err(|e| e.to_string())?;

    // 换音色前先清掉旧的 pth，否则目录里会同时躺着两个模型。
    if let Ok(rd) = fs::read_dir(&dest_dir) {
        for e in rd.flatten() {
            let p = e.path();
            if p.extension().and_then(|s| s.to_str()).unwrap_or("").eq_ignore_ascii_case("pth") {
                let _ = fs::remove_file(p);
            }
        }
    }
    let dest_pth = dest_dir.join(format!("{vid}.pth"));
    fs::copy(pth, &dest_pth).map_err(|e| crate::i18n::te("s.afcf23635f", &(e)))?;

    let mut index_path = String::new();
    if let Ok(rd) = fs::read_dir(dir) {
        for e in rd.flatten() {
            let p = e.path();
            if p.extension().and_then(|s| s.to_str()).unwrap_or("").eq_ignore_ascii_case("index") {
                let dest_idx = dest_dir.join(format!("{vid}.index"));
                if fs::copy(&p, &dest_idx).is_ok() {
                    index_path = dest_idx.to_string_lossy().into_owned();
                }
                break;
            }
        }
    }

    let mut extra = Map::new();
    for k in ["author", "author_url", "source_url", "date", "series", "group"] {
        if let Some(v) = entry.get(k) {
            extra.insert(k.to_string(), v.clone());
        }
    }
    copy_i18n_fields(entry, &mut extra);
    // 暂存安装走的也是清单 entry —— 封面同样要补，否则装完没封面。
    if let Some(v) = entry_cover(entry) {
        extra.insert("cover".into(), v);
    }
    let source = if official { "online_files" } else { "thirdparty_files" };
    Ok(write_voice_config(
        &dest_dir, &dest_pth, name, tag, &vid, &index_path, source, official, &extra,
    ))
}

/// Cancel one voice's download, or every in-flight one when `id` is empty.
pub fn cancel_store_download(id: &str) {
    let g = STORE_CANCELS.lock().unwrap_or_else(|e| e.into_inner());
    let Some(map) = g.as_ref() else { return };
    if id.is_empty() {
        for f in map.values() {
            f.store(true, Ordering::SeqCst);
        }
    } else if let Some(f) = map.get(id) {
        f.store(true, Ordering::SeqCst);
    }
}




#[cfg(test)]
mod tests {
    use super::*;

    /// 清单条目里的多语言字段必须一路走到本地 `config.json`。
    ///
    /// 英文环境下载 Chihaya Anon，模型页显示「千早爱音」就是因为这里断了。
    #[test]
    fn install_keeps_every_translated_name() {
        let entry = json!({
            "id": "Anon",
            "name": "千早爱音",
            "name_i18n": { "en-US": "Chihaya Anon", "ko-KR": "치하야 아논" },
            "name_en": "Chihaya Anon",
            "tag_i18n": { "en-US": "Young Girl Voice" },
            "author": "望月星逸",
            "author_url": "https://example.invalid/u",
            "sha256": "deadbeef",
        });
        let mut extra = Map::new();
        copy_i18n_fields(&entry, &mut extra);

        assert!(extra.contains_key("name_i18n"), "少了 name_i18n：{extra:?}");
        assert!(extra.contains_key("name_en"));
        assert!(extra.contains_key("tag_i18n"));
        // 地址不是译名，`author_url` 不该被当成 author 的一个语言变体带走。
        assert!(!extra.contains_key("author_url"));
        // 白名单外的字段一个都不许混进来。
        assert!(!extra.contains_key("sha256"));
    }

    /// 作者主页和来源仓库都要从清单原样传下来。
    ///
    /// 第三方音色是别人的东西：装完之后「这是谁做的、从哪来的」必须还查得到，
    /// 否则用户想去提个 issue、想看看作者别的作品，一条路都没有。清单解析那张
    /// json! 表是白名单，少列一个字段这两条链接就永远到不了界面上。
    #[test]
    fn a_thirdparty_entry_keeps_both_of_its_links() {
        let v = parse_voice_entry(
            &json!({
                "id": "tp-x",
                "name": "某某",
                "pth_url": "https://example.invalid/a.pth",
                "author_url": "https://example.invalid/u/someone",
                "repo_url": "https://example.invalid/someone/voices",
            }),
            Some(false),
        )
        .expect("entry should parse");
        assert_eq!(
            v.get("author_url").and_then(|x| x.as_str()),
            Some("https://example.invalid/u/someone"),
        );
        // `repo_url` 是第三方手写 YAML 里的常见叫法，得认成 source_url。
        assert_eq!(
            v.get("source_url").and_then(|x| x.as_str()),
            Some("https://example.invalid/someone/voices"),
        );
    }

    /// 第三方条目的封面 URL 必须落进 sidecar 的 `cover` —— 漏掉这条，
    /// 装完的模型页/首页永远没有封面（第三方 zip 里没有 cover 文件，
    /// 官方包自带 cover 走的是另一条路）。曾整条漏写（1.4.6 起修的回归）。
    #[test]
    fn install_writes_catalog_cover() {
        let entry = json!({
            "id": "tp-miku",
            "name": "初音未来",
            "cover_url": "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/releases/download/covers/tp-miku.jpg",
        });
        let mut extra = Map::new();
        if let Some(v) = entry_cover(&entry) {
            extra.insert("cover".into(), v);
        }
        assert_eq!(
            extra.get("cover").and_then(|v| v.as_str()).unwrap_or(""),
            "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/releases/download/covers/tp-miku.jpg"
        );

        // 清单没有封面字段时不得产出空 cover。
        let mut none = Map::new();
        if let Some(v) = entry_cover(&json!({"id": "tp-x"})) {
            none.insert("cover".into(), v);
        }
        assert!(!none.contains_key("cover"), "空封面不该写进 sidecar");
    }

    /// 26.8.24 同时点 Serika-JP / Serika-ZH：解压目录必须按音色分开，不能
    /// 大家都写 `voice_extract_<pid>`。
    #[test]
    fn concurrent_installs_get_distinct_extract_dirs() {
        let root = Path::new(r"C:\App");
        let a = unique_voice_extract_dir(root, "Serika-JP");
        let b = unique_voice_extract_dir(root, "Serika-ZH");
        let c = unique_voice_extract_dir(root, "Serika-JP");
        assert_ne!(a, b);
        assert_ne!(a, c);
        let name = a.file_name().unwrap().to_string_lossy();
        assert!(name.contains("Serika-JP"), "{name}");
        assert!(name.starts_with("voice_extract_"));
    }

    /// 清单解析那张 json! 表是白名单，多语言字段以前全被它吃掉。
    #[test]
    fn catalog_entry_carries_all_locales_through() {
        let raw = json!({
            "id": "Anon",
            "name": "千早爱音",
            "pth_url": "https://example.invalid/a.pth",
            "group": "研讨会",
            "group_i18n": { "en-US": "Seminar" },
            "name_i18n": { "en-US": "Chihaya Anon", "ru-RU": "Тихая Анон" },
            "description_i18n": { "en-US": "From the official download" },
        });
        let out = parse_voice_entry(&raw, None).expect("条目应该解析得出来");
        assert_eq!(out.get("group").and_then(|v| v.as_str()), Some("研讨会"));
        assert_eq!(
            crate::i18n::pick_str_locale(&out, "group", "en-US"),
            "Seminar"
        );

        assert_eq!(
            crate::i18n::pick_str_locale(&out, "name", "en-US"),
            "Chihaya Anon"
        );
        // ru / ko / es / fr 以前根本没往下传 —— 只挑了 ja / en / zh_Hant 三个。
        assert_eq!(
            crate::i18n::pick_str_locale(&out, "name", "ru-RU"),
            "Тихая Анон"
        );
        // 没有译文的语言落回中文主名，不是空字符串。
        assert_eq!(crate::i18n::pick_str_locale(&out, "name", "zh-CN"), "千早爱音");
        assert_eq!(
            crate::i18n::pick_str_locale(&out, "description", "en-US"),
            "From the official download"
        );
    }

    #[test]
    fn official_cnb_pack_gets_lfs_fallback() {
        let sha = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        let url = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/releases/download/voices/Anon-v1.zip";
        let root = std::env::temp_dir().join("rvcf-store-lfs");
        let _ = std::fs::remove_dir_all(&root);
        let list = voice_download_urls(&root, url, sha);
        assert_eq!(list[0], url);
        assert_eq!(
            list[1],
            format!("https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/lfs/{sha}")
        );
    }

    #[test]
    fn hf_pack_does_not_get_cnb_lfs() {
        let sha = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        let url = "https://huggingface.co/org/repo/resolve/main/a.zip";
        let root = std::env::temp_dir().join("rvcf-store-hf");
        let _ = std::fs::remove_dir_all(&root);
        let list = voice_download_urls(&root, url, sha);
        assert!(list.iter().all(|u| !u.contains("/-/lfs/")), "{list:?}");
        assert!(list[0].contains("hf-cdn.sufy.com"));
    }

    #[test]
    fn store_progress_percent_is_float() {
        let p = store_progress_payload("tp-alice", "download", 100 * 1024, 80 * 1024 * 1024, "x");
        let pct = p.get("percent").and_then(|v| v.as_f64()).unwrap();
        assert!(pct > 0.1 && pct < 0.2, "{pct}");
    }

    #[test]
    fn cancelling_one_voice_leaves_the_others_running() {
        // A single global flag used to mean one cancel killed every in-flight
        // download, and that starting a second install reset the first one's
        // cancel state. Per-voice flags are what make 2-at-a-time safe.
        let a = cancel_flag_for("anon");
        let b = cancel_flag_for("soyo");
        assert!(!a.load(Ordering::SeqCst) && !b.load(Ordering::SeqCst));

        cancel_store_download("anon");
        assert!(a.load(Ordering::SeqCst), "target cancelled");
        assert!(!b.load(Ordering::SeqCst), "bystander untouched");

        cancel_store_download("");
        assert!(b.load(Ordering::SeqCst), "empty id cancels all");

        drop_cancel_flag("anon");
        drop_cancel_flag("soyo");
    }

    #[test]
    fn starting_a_second_install_does_not_reset_the_first() {
        let a = cancel_flag_for("v1");
        cancel_store_download("v1");
        assert!(a.load(Ordering::SeqCst));
        let _b = cancel_flag_for("v2"); // second install starts
        assert!(a.load(Ordering::SeqCst), "v1 stays cancelled");
        drop_cancel_flag("v1");
        drop_cancel_flag("v2");
    }

    #[test]
    fn staged_dir_lives_under_user_data_not_the_cache() {
        // 用户要能用资源管理器找到它、自己删。缓存目录是我们随时会清的地方，
        // 把等待用户审查的东西放那儿是不负责任的。
        let d = staged_dir(Path::new("C:\\App"), "abc").unwrap();
        let s = d.to_string_lossy().to_string();
        assert!(s.contains("User_Data"), "{s}");
        assert!(s.contains("downloads"), "{s}");
        assert!(s.ends_with("abc"), "{s}");
    }

    #[test]
    fn a_hostile_voice_id_cannot_escape_the_downloads_dir() {
        // 语言是进程级全局状态，cargo 默认多线程跑测试。不钉住的话，
        // 断言里两次取文案可能落在不同语言上（实测到过法语 vs 韩语）。
        let _g = crate::i18n::testing::pin("zh-CN");
        // voice_id 来自线上清单，会被拼进路径。safe_model_dir_name 是「洗干净」
        // 而不是「拒绝」，所以这里断言的是结果性质：必须还在 downloads 下面，
        // 且不含任何能往上跳的成分。
        let root = Path::new("C:\\App");
        for bad in ["../../evil", "a/b", "..\\..\\evil", "./x"] {
            let d = staged_dir(root, bad).expect(&crate::i18n::t("s.ab16acefd8"));
            let s = d.to_string_lossy().to_string();
            assert!(s.contains("downloads"), "{bad:?} -> {s}");
            assert!(!s.contains(".."));
            assert!(d.starts_with(root), "{bad:?} -> {s}");
        }
        // 洗完啥也不剩的必须报错，否则会建一个空名字的目录。
        for bad in ["", "..", "   ", "..."] {
            assert!(staged_dir(root, bad).is_err());
        }
    }

    #[test]
    fn staged_payload_prefers_the_zip_and_ignores_junk() {
        let base = std::env::temp_dir().join("rvcf-staged-payload");
        let _ = std::fs::remove_dir_all(&base);
        std::fs::create_dir_all(&base).unwrap();
        assert!(staged_payload(&base).is_none());

        std::fs::write(base.join("readme.txt"), b"x").unwrap();
        std::fs::write(base.join("m.index"), b"x").unwrap();
        assert!(staged_payload(&base).is_none());

        std::fs::write(base.join("m.pth"), b"x").unwrap();
        assert!(staged_payload(&base).unwrap().ends_with("m.pth"));

        // zip 和 pth 同时在时用 zip：整包里还带封面和 config。
        std::fs::write(base.join("m.zip"), b"x").unwrap();
        assert!(staged_payload(&base).unwrap().ends_with("m.zip"));
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn staged_status_only_lists_dirs_that_have_something_installable() {
        let base = std::env::temp_dir().join("rvcf-staged-status");
        let _ = std::fs::remove_dir_all(&base);
        let dl = base.join("User_Data").join("downloads");
        std::fs::create_dir_all(dl.join("ready")).unwrap();
        std::fs::create_dir_all(dl.join("empty")).unwrap();
        std::fs::write(dl.join("ready").join("a.pth"), b"1234").unwrap();

        let st = staged_status(&base);
        let o = st.as_object().unwrap();
        assert!(o.contains_key("ready"));
        assert!(!o.contains_key("empty"));
        assert_eq!(st["ready"]["file"], json!("a.pth"));
        assert_eq!(st["ready"]["size_bytes"], json!(4));
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn discarding_staged_files_is_idempotent() {
        // 用户连点两下「删除」不该报错。
        let base = std::env::temp_dir().join("rvcf-staged-discard");
        let _ = std::fs::remove_dir_all(&base);
        let d = staged_dir(&base, "v1").unwrap();
        std::fs::create_dir_all(&d).unwrap();
        std::fs::write(d.join("a.pth"), b"x").unwrap();
        assert!(discard_staged(&base, "v1").is_ok());
        assert!(!d.exists());
        assert!(discard_staged(&base, "v1").is_ok());
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn origin_label_fills_origin_not_the_placeholder() {
        // 语言是进程级全局状态，cargo 默认多线程跑测试。不钉住的话，
        // 断言里两次取文案可能落在不同语言上（实测到过法语 vs 韩语）。
        let _g = crate::i18n::testing::pin("zh-CN");
        let s = origin_label_for("huggingface", false);
        assert!(!s.contains("{origin}"), "{s}");
        assert!(s.contains("Hugging Face"), "{s}");
        assert_eq!(origin_label_for("", false), crate::i18n::t("s.4500b5dfc7"));
        assert_eq!(origin_label_for("", true), crate::i18n::t("s.7c134b6e64"));
        assert!(origin_label_for("GitHub", false).contains("GitHub"));
        assert!(!origin_label_for("GitHub", false).contains("github"));
    }

    #[test]
    fn cover_url_falls_back_to_local_banner_file() {
        let root = std::env::temp_dir().join(format!("rvcf-cover-fb-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let dir = root.join("CNB-GIT-RELEASE").join("ch-banner");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("tp-yuuka.jpg"), vec![0u8; 200]).unwrap();
        let url = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/releases/download/covers/tp-yuuka.jpg";
        let got = local_banner_for_url(&root, url).expect("should find local yuuka");
        assert!(got.ends_with("tp-yuuka.jpg"), "{got}");
        assert!(local_banner_for_url(&root, "https://x/covers/..").is_none());
        // 相对路径 cover 字段也能对上本机文件。
        let rel = local_banner_for_hint(&root, "ch-banner/tp-yuuka.jpg");
        assert!(rel.unwrap().ends_with("tp-yuuka.jpg"));
        // 本机有图时不再去网上撞 404。
        let resolved = resolve_cover_url(&root, url).expect("local first");
        assert!(resolved.ends_with("tp-yuuka.jpg"), "{resolved}");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn cover_download_adds_git_raw_fallback() {
        let url = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/releases/download/covers/tp-yuuka.jpg";
        let c = cover_download_candidates(url);
        assert_eq!(c[0], url);
        assert!(c.iter().any(|u| u.ends_with("/ch-banner/tp-yuuka.jpg")), "{c:?}");
    }
}
