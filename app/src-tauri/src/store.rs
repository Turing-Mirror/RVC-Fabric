//! Community voice store: catalog fetch + zip/files install.
//! Mirrors launcher/online/catalog.py + voice_install.py (subset for stage 4).

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use serde_json::{json, Map, Value};
use tauri::{AppHandle, Emitter};

use crate::download::{self, DownloadKind, DownloadRequest};
use crate::paths;
use crate::voices::safe_model_dir_name;

const CNB_RAW_MAIN: &str = "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main";
const MIN_PTH_BYTES: u64 = 50_000;

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

fn bundled_catalog_path(root: &Path) -> PathBuf {
    root.join("configs").join("online_catalog.json")
}

fn cache_catalog_path(root: &Path) -> PathBuf {
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
    Some(json!({
        "id": id,
        "name": d.get("name").and_then(|v| v.as_str()).unwrap_or(&id),
        "tag": d.get("tag").and_then(|v| v.as_str()).unwrap_or("音色"),
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
        "series": d.get("series").or_else(|| d.get("series_name")).or_else(|| d.get("collection")).and_then(|v| v.as_str()).unwrap_or(""),
        "origin": d.get("origin").and_then(|v| v.as_str()).unwrap_or(""),
        "source_url": d.get("source_url").or_else(|| d.get("repo_url")).and_then(|v| v.as_str()).unwrap_or(""),
        "official": official,
    }))
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
    // cache
    let cache_p = cache_catalog_path(root);
    if cache_p.is_file() {
        if let Ok(s) = fs::read_to_string(&cache_p) {
            if let Ok(v) = serde_json::from_str::<Value>(&s) {
                if source == "empty" {
                    data = v;
                    source = "cache";
                }
            }
        }
    }

    if prefer_remote {
        // Cached: the dialog refetches on every open, and this is the same
        // index.json the runtime specs come from. Five minutes is short enough
        // that a newly published voice shows up promptly, and it means
        // reopening the store is instant instead of another 25s round trip.
        match crate::catalog::fetch_remote_catalog_cached(25) {
            Ok(remote) => {
                data = remote;
                source = "remote";
                if let Ok(text) = serde_json::to_string_pretty(&data) {
                    let _ = fs::write(&cache_p, text);
                }
            }
            Err(e) => {
                fetch_error = e;
                if source == "empty" {
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
                    let origin_label = if !official {
                        if origin.is_empty() {
                            "第三方".to_string()
                        } else {
                            format!("第三方 · {origin}")
                        }
                    } else if origin.is_empty() {
                        "图灵镜".to_string()
                    } else {
                        origin
                    };
                    obj.insert("origin_label".into(), json!(origin_label));
                    let size = obj.get("size_bytes").and_then(|x| x.as_u64()).unwrap_or(0);
                    obj.insert("size_label".into(), json!(format_size(size)));
                }
            }
        }
    }
    cat
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
    crate::extract::extract_zip(zip_path, dest).map_err(|e| format!("音色包{e}"))
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

/// Install a local voice_pack zip into User_Data/models/<id>/.
pub fn install_voice_pack_zip(
    root: &Path,
    zip_path: &Path,
    voice_id: &str,
    display_name: &str,
    tag: &str,
    official: bool,
) -> Result<Value, String> {
    if !zip_path.is_file() {
        return Err(format!("找不到音色包：{}", zip_path.display()));
    }
    let tmp = paths::update_cache(root).join(format!(
        "voice_extract_{}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&tmp);
    fs::create_dir_all(&tmp).map_err(|e| e.to_string())?;
    let result = (|| {
        safe_extract_zip(zip_path, &tmp)?;
        let content = find_content_root(&tmp);
        let pth = find_first(&content, "pth")
            .ok_or_else(|| "音色包内没有 .pth 文件".to_string())?;
        let size = pth.metadata().map(|m| m.len()).unwrap_or(0);
        if size < MIN_PTH_BYTES {
            return Err("音色包内 .pth 过小，可能损坏".into());
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
                .unwrap_or("音色")
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
        fs::copy(&pth, &dest_pth).map_err(|e| format!("复制 pth: {e}"))?;

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
        for k in ["author", "author_url", "date", "series", "cover"] {
            if let Some(v) = pack_cfg.get(k) {
                extra.insert(k.to_string(), v.clone());
            }
        }
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
        .unwrap_or("音色")
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
        return Err(format!("音色 {id} 缺少有效的 sha256，已拒绝安装"));
    }

    let emit = |phase: &str, done: u64, total: u64, message: &str| {
        let _ = app.emit(
            "store-progress",
            json!({
                "voice_id": id,
                "phase": phase,
                "done": done,
                "total": total,
                "percent": if total > 0 { (done as f64 / total as f64 * 100.0) as u32 } else { 0 },
                "message": message,
            }),
        );
    };

    emit("start", 0, size.max(1), &format!("开始下载 {name}…"));

    // 第三方一律先落暂存区，下完不装 —— .pth 是 pickle，加载即执行代码，
    // 而它来自社区站点不是我们的仓库。哈希只能证明「下到的就是清单里那个」，
    // 证明不了那个文件本身干净。让用户自己先看一眼。
    let stage_only = !official;

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
                json!({
                    "voice_id": id2,
                    "phase": "download",
                    "done": done,
                    "total": total,
                    "percent": if total > 0 { (done as f64 / total as f64 * 100.0) as u32 } else { 0 },
                    "message": msg,
                }),
            );
        });

        let res = download::download_request(
            DownloadRequest {
                urls: vec![pack_url],
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
            emit("staged", 1, 1, "已下载，待你确认后安装");
            return Ok(json!({
                "staged": true,
                "voice_id": id,
                "dir": cache.to_string_lossy(),
                "file": zpath.file_name().and_then(|s| s.to_str()).unwrap_or(""),
            }));
        }
        emit("extract", 0, 1, "正在解压安装…");
        let info = install_voice_pack_zip(&root, &zpath, &id, &name, &tag, official)?;
        emit("done", 1, 1, "安装完成");
        return Ok(info);
    }

    if pth_url.is_empty() {
        return Err("音色未配置下载地址".into());
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

    let cancel = Arc::new(AtomicBool::new(false));
    let app2 = app.clone();
    let id2 = id.clone();
    let progress: download::ProgressFn = Arc::new(move |done, total, msg| {
        let _ = app2.emit(
            "store-progress",
            json!({
                "voice_id": id2,
                "phase": "pth",
                "done": done,
                "total": total,
                "percent": if total > 0 { (done as f64 / total as f64 * 100.0) as u32 } else { 0 },
                "message": msg,
            }),
        );
    });
    download::download_request(
        DownloadRequest {
            urls: vec![pth_url],
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
    )?;
    if pth_tmp.metadata().map(|m| m.len()).unwrap_or(0) < MIN_PTH_BYTES {
        return Err("下载的模型文件过小，可能不是有效 .pth".into());
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
                        urls: vec![iu.to_string()],
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
        emit("staged", 1, 1, "已下载，待你确认后安装");
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
    fs::copy(&pth_tmp, &dest_pth).map_err(|e| e.to_string())?;

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
                    urls: vec![iu.to_string()],
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
    for k in ["author", "author_url", "date", "series"] {
        if let Some(v) = entry.get(k) {
            extra.insert(k.to_string(), v.clone());
        }
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
    emit("done", 1, 1, "安装完成");
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
        return Err("这个音色还没有下载好的文件".into());
    }
    crate::shell_extras::reveal(&dir.join("x"))
}

/// 丢掉暂存的文件（用户看完决定不装）。
pub fn discard_staged(root: &Path, voice_id: &str) -> Result<(), String> {
    let dir = staged_dir(root, voice_id)?;
    if dir.is_dir() {
        fs::remove_dir_all(&dir).map_err(|e| format!("删除失败：{e}"))?;
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
    let tag = entry.get("tag").and_then(|v| v.as_str()).unwrap_or("音色").to_string();
    let official = entry.get("official").and_then(|v| v.as_bool()).unwrap_or(false);

    let dir = staged_dir(&root, if id.is_empty() { &name } else { &id })?;
    let payload = staged_payload(&dir).ok_or("暂存目录里没有可安装的文件")?;

    let emit = |phase: &str, message: &str| {
        let _ = app.emit(
            "store-progress",
            json!({ "voice_id": id, "phase": phase, "done": 1, "total": 1,
                    "percent": 100, "message": message }),
        );
    };
    emit("extract", "正在安装…");

    let is_zip = payload
        .extension()
        .and_then(|s| s.to_str())
        .map(|s| s.eq_ignore_ascii_case("zip"))
        .unwrap_or(false);

    let info = if is_zip {
        install_voice_pack_zip(&root, &payload, &id, &name, &tag, official)?
    } else {
        install_staged_files(&root, &dir, &payload, &id, &name, &tag, official, &entry)?
    };
    // 装完就把暂存清掉，不然用户的 User_Data 会慢慢堆满几百 MB 的重复文件。
    let _ = fs::remove_dir_all(&dir);
    emit("done", "安装完成");
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
    fs::copy(pth, &dest_pth).map_err(|e| format!("复制模型失败：{e}"))?;

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
    for k in ["author", "author_url", "date", "series"] {
        if let Some(v) = entry.get(k) {
            extra.insert(k.to_string(), v.clone());
        }
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
        // voice_id 来自线上清单，会被拼进路径。safe_model_dir_name 是「洗干净」
        // 而不是「拒绝」，所以这里断言的是结果性质：必须还在 downloads 下面，
        // 且不含任何能往上跳的成分。
        let root = Path::new("C:\\App");
        for bad in ["../../evil", "a/b", "..\\..\\evil", "./x"] {
            let d = staged_dir(root, bad).expect("应当被清洗而不是报错");
            let s = d.to_string_lossy().to_string();
            assert!(s.contains("downloads"), "{bad:?} -> {s}");
            assert!(!s.contains(".."), "{bad:?} 逃出了 downloads: {s}");
            assert!(d.starts_with(root), "{bad:?} -> {s}");
        }
        // 洗完啥也不剩的必须报错，否则会建一个空名字的目录。
        for bad in ["", "..", "   ", "..."] {
            assert!(staged_dir(root, bad).is_err(), "{bad:?} 应当被拒绝");
        }
    }

    #[test]
    fn staged_payload_prefers_the_zip_and_ignores_junk() {
        let base = std::env::temp_dir().join("rvcf-staged-payload");
        let _ = std::fs::remove_dir_all(&base);
        std::fs::create_dir_all(&base).unwrap();
        assert!(staged_payload(&base).is_none(), "空目录没有可安装的东西");

        std::fs::write(base.join("readme.txt"), b"x").unwrap();
        std::fs::write(base.join("m.index"), b"x").unwrap();
        assert!(staged_payload(&base).is_none(), "只有 index 装不了");

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
        assert!(!o.contains_key("empty"), "空目录不该显示成「待安装」");
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
        assert!(discard_staged(&base, "v1").is_ok(), "再删一次也不该报错");
        let _ = std::fs::remove_dir_all(&base);
    }
}
