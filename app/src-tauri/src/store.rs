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

fn safe_extract_zip(zip_path: &Path, dest: &Path) -> Result<(), String> {
    fs::create_dir_all(dest).map_err(|e| e.to_string())?;
    let file = fs::File::open(zip_path).map_err(|e| format!("打开 zip: {e}"))?;
    let mut archive = zip::ZipArchive::new(file).map_err(|e| format!("无效 zip: {e}"))?;
    for i in 0..archive.len() {
        let mut entry = archive
            .by_index(i)
            .map_err(|e| format!("zip 条目: {e}"))?;
        let name = entry.name().replace('\\', "/");
        if name.is_empty()
            || name.starts_with('/')
            || name.starts_with("../")
            || name.contains("/../")
        {
            return Err(format!("音色包路径不安全：{name}"));
        }
        if name.split('/').any(|p| p == "..") {
            return Err(format!("音色包路径不安全：{name}"));
        }
        // skip absolute / drive
        if name.len() > 1 && name.as_bytes().get(1) == Some(&b':') {
            return Err(format!("音色包含盘符路径：{name}"));
        }
        let out_path = dest.join(&name);
        if entry.is_dir() || name.ends_with('/') {
            fs::create_dir_all(&out_path).map_err(|e| e.to_string())?;
            continue;
        }
        if let Some(parent) = out_path.parent() {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        let mut outfile = fs::File::create(&out_path).map_err(|e| e.to_string())?;
        std::io::copy(&mut entry, &mut outfile).map_err(|e| e.to_string())?;
    }
    Ok(())
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

    if !pack_url.is_empty() {
        let cache = paths::update_cache(&root).join("voice_packs");
        fs::create_dir_all(&cache).map_err(|e| e.to_string())?;
        let vid = safe_model_dir_name(if id.is_empty() { &name } else { &id })?;
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
    let dest_dir = paths::models_dir(&root).join(&vid);
    fs::create_dir_all(&dest_dir).map_err(|e| e.to_string())?;
    let cache = paths::update_cache(&root).join("voices").join(&vid);
    fs::create_dir_all(&cache).map_err(|e| e.to_string())?;
    let pth_tmp = cache.join(format!("{vid}.pth"));

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
            size_hint: size,
            connections: None,
            kind: DownloadKind::VoicePack,
        },
        cancel.clone(),
        Some(progress),
    )?;
    if pth_tmp.metadata().map(|m| m.len()).unwrap_or(0) < MIN_PTH_BYTES {
        return Err("下载的模型文件过小，可能不是有效 .pth".into());
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
            let _ = download::download_request(
                DownloadRequest {
                    urls: vec![iu.to_string()],
                    dest: idx_tmp.clone(),
                    expected_sha256: String::new(),
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
}
