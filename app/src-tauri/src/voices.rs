//! Local voice catalog: list / select / import / index / profiles / delete.
//! Mirrors launcher/catalog.py + profiles.py behaviour (disk layout only).

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use regex::Regex;
use serde_json::{json, Map, Value};

use crate::paths;

const MIN_MODEL_BYTES: u64 = 200 * 1024;
const PROFILE_EXT: &str = ".tmvp";
const PROFILES_DIR: &str = "profiles";

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

fn read_json(path: &Path) -> Value {
    if !path.is_file() {
        return json!({});
    }
    match fs::read_to_string(path) {
        Ok(s) => serde_json::from_str(&s).unwrap_or_else(|_| json!({})),
        Err(_) => json!({}),
    }
}

fn write_json_atomic(path: &Path, data: &Value) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let text = serde_json::to_string_pretty(data).map_err(|e| e.to_string())?;
    let tmp = path.with_extension(format!(
        "tmp.{}",
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    ));
    {
        let mut f = fs::File::create(&tmp).map_err(|e| e.to_string())?;
        f.write_all(text.as_bytes()).map_err(|e| e.to_string())?;
        f.sync_all().ok();
    }
    fs::rename(&tmp, path).map_err(|e| {
        let _ = fs::remove_file(&tmp);
        e.to_string()
    })?;
    Ok(())
}

fn load_app_config(root: &Path) -> Map<String, Value> {
    let v = read_json(&paths::app_config_path(root));
    v.as_object().cloned().unwrap_or_default()
}

fn save_app_config(root: &Path, cfg: &Map<String, Value>) -> Result<(), String> {
    write_json_atomic(&paths::app_config_path(root), &Value::Object(cfg.clone()))
}

pub fn safe_model_dir_name(name: &str) -> Result<String, String> {
    let re = Regex::new(r"[^\w\u4e00-\u9fff\-]+").unwrap();
    let n = re.replace_all(name.trim(), "_");
    let n = n.trim_matches(|c| c == '.' || c == '_');
    if n.is_empty() || n == "." || n == ".." {
        return Err(format!("invalid model name: {name:?}"));
    }
    Ok(n.chars().take(80).collect())
}

fn guess_tag(name: &str) -> &'static str {
    let n = name.to_lowercase();
    if ["女", "girl", "loli", "萝莉", "少女"]
        .iter()
        .any(|k| n.contains(k) || name.contains(k))
    {
        return "少女音";
    }
    if ["男", "boy", "男声", "青年"]
        .iter()
        .any(|k| n.contains(k) || name.contains(k))
    {
        return "男声";
    }
    if name.contains("御姐") {
        return "御姐音";
    }
    "音色"
}

fn find_pth(folder: &Path) -> Option<PathBuf> {
    let mut pths: Vec<PathBuf> = fs::read_dir(folder)
        .ok()?
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|s| s.to_str()).unwrap_or("") == "pth")
        .collect();
    pths.sort();
    pths.into_iter().next()
}

fn find_cover(folder: &Path) -> Option<String> {
    for ext in [".png", ".jpg", ".jpeg", ".webp"] {
        if let Ok(rd) = fs::read_dir(folder) {
            for e in rd.flatten() {
                let p = e.path();
                let name = p.file_name().and_then(|s| s.to_str()).unwrap_or("");
                if name.eq_ignore_ascii_case(&format!("cover{ext}"))
                    || name.to_ascii_lowercase().ends_with(ext)
                {
                    if p.is_file() {
                        return Some(p.to_string_lossy().into_owned());
                    }
                }
            }
        }
        let c = folder.join(format!("cover{ext}"));
        if c.is_file() {
            return Some(c.to_string_lossy().into_owned());
        }
    }
    None
}

fn resolve_cover(cover: &str, model_dir: Option<&Path>, voice_id: &str, root: &Path) -> String {
    let cover = cover.trim().replace('\\', "/");
    if cover.is_empty() {
        return String::new();
    }
    if cover.to_ascii_lowercase().starts_with("http://")
        || cover.to_ascii_lowercase().starts_with("https://")
    {
        return cover;
    }
    let cp = PathBuf::from(&cover);
    if cp.is_file() {
        return cp.to_string_lossy().into_owned();
    }
    let mut rel = cover.clone();
    if rel.to_ascii_lowercase().starts_with("ch-banner/") {
        rel = rel["ch-banner/".len()..].to_string();
    }
    for base in [paths::ch_banner_dir(root), root.join("ch-banner")] {
        let cand = base.join(&rel);
        if cand.is_file() {
            return cand.to_string_lossy().into_owned();
        }
        let stem = Path::new(&rel)
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or(voice_id);
        if !stem.is_empty() {
            for ext in [".jpg", ".jpeg", ".png", ".webp"] {
                let c2 = base.join(format!("{stem}{ext}"));
                if c2.is_file() {
                    return c2.to_string_lossy().into_owned();
                }
            }
        }
    }
    if let Some(md) = model_dir {
        let cand = md.join(&cover);
        if cand.is_file() {
            return cand.to_string_lossy().into_owned();
        }
        if let Some(f) = find_cover(md) {
            return f;
        }
    }
    String::new()
}

fn model_is_broken(pth: Option<&Path>) -> bool {
    match pth {
        None => true,
        Some(p) if !p.is_file() => true,
        Some(p) => p.metadata().map(|m| m.len() < MIN_MODEL_BYTES).unwrap_or(true),
    }
}

fn looks_like_voice_folder(folder: &Path) -> bool {
    (folder.join("config.json")).is_file() || find_cover(folder).is_some()
}

fn read_sidecar(folder: &Path) -> Map<String, Value> {
    let v = read_json(&folder.join("config.json"));
    v.as_object().cloned().unwrap_or_default()
}

fn write_sidecar(folder: &Path, side: &Map<String, Value>) -> Result<(), String> {
    write_json_atomic(&folder.join("config.json"), &Value::Object(side.clone()))
}

fn path_inside_dir(path: &Path, folder: &Path) -> bool {
    let Ok(p) = path.canonicalize() else {
        return false;
    };
    let Ok(f) = folder.canonicalize() else {
        return false;
    };
    p.starts_with(&f)
}

fn ensure_index_in_model_dir(model_dir: &Path, index_src: &Path) -> Result<String, String> {
    if !index_src.is_file()
        || index_src
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_ascii_lowercase()
            != "index"
    {
        return Err(format!("not a .index file: {}", index_src.display()));
    }
    fs::create_dir_all(model_dir).map_err(|e| e.to_string())?;
    if path_inside_dir(index_src, model_dir) {
        return Ok(index_src
            .canonicalize()
            .unwrap_or_else(|_| index_src.to_path_buf())
            .to_string_lossy()
            .into_owned());
    }
    let dest = model_dir.join(
        index_src
            .file_name()
            .ok_or_else(|| "index name".to_string())?,
    );
    if !dest.is_file()
        || dest.canonicalize().ok() != index_src.canonicalize().ok()
    {
        fs::copy(index_src, &dest).map_err(|e| format!("copy index: {e}"))?;
    }
    Ok(dest
        .canonicalize()
        .unwrap_or(dest)
        .to_string_lossy()
        .into_owned())
}

// ---------------------------------------------------------------------------
// list
// ---------------------------------------------------------------------------

fn resolve_active_index(model_dir: &Path, side: &Map<String, Value>) -> String {
    // Prefer config index if file exists
    if let Some(idx) = side.get("index").and_then(|v| v.as_str()) {
        let p = PathBuf::from(idx.trim());
        if p.is_file() {
            // Prefer same-name local twin
            let local = model_dir.join(p.file_name().unwrap_or_default());
            if local.is_file() {
                return local
                    .canonicalize()
                    .unwrap_or(local)
                    .to_string_lossy()
                    .into_owned();
            }
            return p
                .canonicalize()
                .unwrap_or(p)
                .to_string_lossy()
                .into_owned();
        }
    }
    // Any local *.index
    if let Ok(rd) = fs::read_dir(model_dir) {
        let mut idxs: Vec<PathBuf> = rd
            .flatten()
            .map(|e| e.path())
            .filter(|p| {
                p.extension()
                    .and_then(|s| s.to_str())
                    .unwrap_or("")
                    .eq_ignore_ascii_case("index")
            })
            .collect();
        idxs.sort();
        if let Some(p) = idxs.into_iter().next() {
            return p
                .canonicalize()
                .unwrap_or(p)
                .to_string_lossy()
                .into_owned();
        }
    }
    String::new()
}

fn list_user_data(root: &Path) -> Vec<Value> {
    let models_root = paths::models_dir(root);
    let mut out = Vec::new();
    let Ok(rd) = fs::read_dir(&models_root) else {
        return out;
    };
    let mut folders: Vec<PathBuf> = rd
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.is_dir())
        .filter(|p| {
            !p.file_name()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .starts_with('.')
        })
        .collect();
    folders.sort();
    for folder in folders {
        let pth = find_pth(&folder);
        let side = read_sidecar(&folder);
        let vid = folder
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_string();
        let name = side
            .get("name")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty())
            .unwrap_or(&vid)
            .to_string();
        let tag = side
            .get("tag")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty())
            .map(|s| s.to_string())
            .unwrap_or_else(|| guess_tag(&name).to_string());
        let author = side
            .get("author")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let author_url = side
            .get("author_url")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let mut cover = side
            .get("cover")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        cover = resolve_cover(&cover, Some(&folder), &vid, root);
        if cover.is_empty() {
            cover = find_cover(&folder).unwrap_or_default();
        }

        if pth.is_none() {
            if !looks_like_voice_folder(&folder) {
                continue;
            }
            out.push(json!({
                "name": name,
                "path": "",
                "file": "",
                "dir": folder.to_string_lossy(),
                "cover": cover,
                "index": "",
                "has_index": false,
                "tag": tag,
                "author": author,
                "author_url": author_url,
                "source": "user_data",
                "missing": true,
            }));
            continue;
        }
        let pth = pth.unwrap();
        let broken = model_is_broken(Some(&pth));
        let index = resolve_active_index(&folder, &side);
        let mut entry = json!({
            "name": name,
            "path": pth.to_string_lossy(),
            "file": pth.file_name().and_then(|s| s.to_str()).unwrap_or(""),
            "dir": folder.to_string_lossy(),
            "cover": cover,
            "index": index,
            "has_index": !index.is_empty(),
            "tag": tag,
            "author": author,
            "author_url": author_url,
            "source": "user_data",
            "missing": broken,
        });
        // voice params if present
        if let Some(obj) = entry.as_object_mut() {
            for k in [
                "pitch",
                "formant",
                "index_rate",
                "rms_mix_rate",
                "threhold",
                "f0method",
            ] {
                if let Some(v) = side.get(k) {
                    if !v.is_null() && v != "" {
                        obj.insert(k.to_string(), v.clone());
                    }
                }
            }
            if let Some(ap) = side.get("active_profile") {
                obj.insert("active_profile".into(), ap.clone());
            }
        }
        out.push(entry);
    }
    out
}

fn list_legacy(root: &Path) -> Vec<Value> {
    let weights = paths::engine_weights(root);
    let mut out = Vec::new();
    let Ok(rd) = fs::read_dir(&weights) else {
        return out;
    };
    let mut pths: Vec<PathBuf> = rd
        .flatten()
        .map(|e| e.path())
        .filter(|p| {
            p.extension()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .eq_ignore_ascii_case("pth")
        })
        .collect();
    pths.sort();
    for p in pths {
        let name = p
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("voice")
            .to_string();
        let mut cover = String::new();
        for ext in [".png", ".jpg", ".jpeg", ".webp"] {
            let c = p.with_extension(&ext[1..]);
            if c.is_file() {
                cover = c.to_string_lossy().into_owned();
                break;
            }
        }
        out.push(json!({
            "name": name,
            "path": p.to_string_lossy(),
            "file": p.file_name().and_then(|s| s.to_str()).unwrap_or(""),
            "dir": weights.to_string_lossy(),
            "cover": cover,
            "index": "",
            "has_index": false,
            "tag": guess_tag(&name),
            "author": "",
            "author_url": "",
            "source": "legacy_weights",
            "missing": model_is_broken(Some(&p)),
        }));
    }
    out
}

/// Full local catalog (User_Data first, then legacy weights not already present).
/// 在音色列表里定位「当前选中的那一条」，返回下标；一条都没有时返回 -1。
///
/// 三个键**按可靠性依次匹配**，不是「或」在一起谁先撞上算谁：
///
/// * `path` —— 全路径，唯一，最可信
/// * `file` —— 只是文件名（`model.pth`、`added.pth` 这种），社区音色包里重名是常态
/// * `name` —— 显示名，也可能重复
///
/// 以前是一趟循环里把三个或起来，第一个命中的模型就赢。于是排在前面的某个
/// **同名文件**会把真正选中的那条顶掉：界面显示的「使用中」是别人，重开变声
/// 也跟着用错。而随手切一次别的模型会把三个键一起改写，看上去就成了
/// 「切到另一个再切回来就好了」。
///
/// 一档一档地问，问到为止 —— 最弱的键不该有机会抢在最强的前面。
fn resolve_selected(models: &[Value], path: &str, file: &str, name: &str) -> i64 {
    let find = |key: &str, want: &str| -> Option<usize> {
        if want.is_empty() {
            return None;
        }
        models
            .iter()
            .position(|m| m.get(key).and_then(|v| v.as_str()).unwrap_or("") == want)
    };
    find("path", path)
        .or_else(|| find("file", file))
        .or_else(|| find("name", name))
        // 三个键都没对上（配置是新的、或者选中的音色被删了）：退回第一条，
        // 总比「一条都没选中」强 —— 那会让底栏显示「未选择模型」。
        .or(if models.is_empty() { None } else { Some(0) })
        .map(|i| i as i64)
        .unwrap_or(-1)
}

pub fn list_voices(root: &Path) -> Value {
    let _ = paths::ensure_user_dirs(root);
    let mut primary = list_user_data(root);
    let mut seen_paths: std::collections::HashSet<String> = primary
        .iter()
        .filter_map(|m| m.get("path").and_then(|v| v.as_str()))
        .filter(|s| !s.is_empty())
        .map(|s| {
            PathBuf::from(s)
                .canonicalize()
                .map(|p| p.to_string_lossy().into_owned())
                .unwrap_or_else(|_| s.to_string())
        })
        .collect();
    let mut seen_stems: std::collections::HashSet<String> = primary
        .iter()
        .filter_map(|m| m.get("file").and_then(|v| v.as_str()))
        .map(|s| s.to_ascii_lowercase())
        .collect();

    for m in list_legacy(root) {
        let path = m.get("path").and_then(|v| v.as_str()).unwrap_or("");
        let file = m.get("file").and_then(|v| v.as_str()).unwrap_or("");
        let rp = PathBuf::from(path)
            .canonicalize()
            .map(|p| p.to_string_lossy().into_owned())
            .unwrap_or_else(|_| path.to_string());
        let stem = file.to_ascii_lowercase();
        if seen_paths.contains(&rp) || seen_stems.contains(&stem) {
            continue;
        }
        seen_paths.insert(rp);
        seen_stems.insert(stem);
        primary.push(m);
    }

    let cfg = load_app_config(root);
    let selected_path = cfg
        .get("last_model_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let selected_name = cfg
        .get("last_model_name")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let selected_file = cfg
        .get("last_model")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    let selected_idx = resolve_selected(
        &primary,
        &selected_path,
        &selected_file,
        &selected_name,
    );

    let recents = cfg
        .get("recent_models")
        .cloned()
        .unwrap_or_else(|| json!([]));

    json!({
        "models": primary,
        "selected_idx": selected_idx,
        "models_dir": paths::models_dir(root).to_string_lossy(),
        "recent_keys": recents,
    })
}

// ---------------------------------------------------------------------------
// select
// ---------------------------------------------------------------------------

fn model_key(m: &Value) -> String {
    let path = m.get("path").and_then(|v| v.as_str()).unwrap_or("");
    if !path.is_empty() {
        return path.to_string();
    }
    let dir = m.get("dir").and_then(|v| v.as_str()).unwrap_or("");
    let name = m.get("name").and_then(|v| v.as_str()).unwrap_or("");
    format!("{dir}|{name}")
}

pub fn select_voice(root: &Path, path: &str, dir: &str, name: &str) -> Result<Value, String> {
    let cat = list_voices(root);
    let models = cat
        .get("models")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    let mut found: Option<Value> = None;
    for m in &models {
        let mp = m.get("path").and_then(|v| v.as_str()).unwrap_or("");
        let md = m.get("dir").and_then(|v| v.as_str()).unwrap_or("");
        let mn = m.get("name").and_then(|v| v.as_str()).unwrap_or("");
        if (!path.is_empty() && mp == path)
            || (!dir.is_empty() && !name.is_empty() && md == dir && mn == name)
            || (!name.is_empty() && mn == name && path.is_empty() && dir.is_empty())
        {
            found = Some(m.clone());
            break;
        }
    }
    let m = found.ok_or_else(|| "未找到该音色".to_string())?;
    if m.get("missing").and_then(|v| v.as_bool()).unwrap_or(false) {
        return Err("音色文件缺失或不完整".into());
    }
    let mut cfg = load_app_config(root);
    cfg.insert(
        "last_model".into(),
        json!(m.get("file").and_then(|v| v.as_str()).unwrap_or("")),
    );
    cfg.insert(
        "last_model_name".into(),
        json!(m.get("name").and_then(|v| v.as_str()).unwrap_or("")),
    );
    cfg.insert(
        "last_model_path".into(),
        json!(m.get("path").and_then(|v| v.as_str()).unwrap_or("")),
    );
    let key = model_key(&m);
    let mut recents: Vec<String> = cfg
        .get("recent_models")
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|x| x.as_str().map(|s| s.to_string()))
                .filter(|s| s != &key)
                .collect()
        })
        .unwrap_or_default();
    recents.insert(0, key);
    recents.truncate(12);
    cfg.insert("recent_models".into(), json!(recents));

    // Apply profile / voice params into app config for dock
    if let Some(md) = m.get("dir").and_then(|v| v.as_str()) {
        if m.get("source").and_then(|v| v.as_str()) == Some("user_data") {
            apply_profile_to_cfg(md, &mut cfg);
        }
    }
    // Fallback voice params from model entry
    for k in ["pitch", "formant", "index_rate", "rms_mix_rate", "threhold", "f0method"] {
        if let Some(v) = m.get(k) {
            if !v.is_null() && cfg.get(k).is_none() {
                cfg.insert(k.to_string(), v.clone());
            }
        }
    }

    save_app_config(root, &cfg)?;

    // Sync engine inuse config if present
    let _ = sync_inuse_model(
        root,
        m.get("path").and_then(|v| v.as_str()).unwrap_or(""),
        m.get("index").and_then(|v| v.as_str()).unwrap_or(""),
    );

    Ok(json!({
        "ok": true,
        "model": m,
        "pitch": cfg.get("pitch").cloned().unwrap_or(json!(0)),
        "formant": cfg.get("formant").cloned().unwrap_or(json!(0.0)),
        "active_profile": cfg.get("_active_profile_name").cloned().unwrap_or(json!("")),
        "profile_summary": profile_summary_from_cfg(&cfg),
    }))
}

/// Persist the selected model.
///
/// **app_config is the source of truth**, not inuse: the shell rewrites inuse
/// from app_config at startup, so a selection that only landed in inuse would
/// be wiped on the next launch. Write both.
/// 把「当前选中的音色」原样重写进引擎配置。
///
/// 不改选择，只是把界面认定的那一条重新落到 `configs/inuse` 里 —— 相当于
/// 替用户做了一次「切到别的再切回来」。强制结束引擎之后调用：那时候引擎配置
/// 可能是被打断的写入留下的半截状态，而下一次开启变声只读那份文件。
///
/// 找不到选中项（音色库是空的、或者选中的那个被删了）就什么都不做：这时候
/// 没有「正确答案」可写，凭空写一条只会让状态更乱。
pub fn resync_selected_model(root: &Path) -> Result<(), String> {
    let cat = list_voices(root);
    let idx = cat.get("selected_idx").and_then(|v| v.as_i64()).unwrap_or(-1);
    if idx < 0 {
        return Ok(());
    }
    let Some(m) = cat
        .get("models")
        .and_then(|v| v.as_array())
        .and_then(|a| a.get(idx as usize))
    else {
        return Ok(());
    };
    if m.get("missing").and_then(|v| v.as_bool()).unwrap_or(false) {
        return Ok(());
    }
    sync_inuse_model(
        root,
        m.get("path").and_then(|v| v.as_str()).unwrap_or(""),
        m.get("index").and_then(|v| v.as_str()).unwrap_or(""),
    )
}

fn sync_inuse_model(root: &Path, pth: &str, index: &str) -> Result<(), String> {
    if pth.is_empty() {
        return Ok(());
    }
    let mut patch = serde_json::Map::new();
    patch.insert("pth_path".into(), json!(pth));
    patch.insert("index_path".into(), json!(index));
    // This also mirrors into inuse (both keys are COLD engine keys).
    crate::config::update(root, patch).map(|_| ())
}

fn profile_summary_from_cfg(cfg: &Map<String, Value>) -> String {
    let name = cfg
        .get("_active_profile_name")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let pitch = cfg
        .get("pitch")
        .and_then(|v| v.as_i64())
        .or_else(|| cfg.get("pitch").and_then(|v| v.as_f64()).map(|f| f as i64))
        .unwrap_or(0);
    let formant = cfg.get("formant").and_then(|v| v.as_f64()).unwrap_or(0.0);
    let label = if name.is_empty() {
        "默认（原始参数）".to_string()
    } else {
        name.to_string()
    };
    if pitch == 0 && (formant - 0.0).abs() < 0.001 {
        label
    } else {
        let sign = if pitch >= 0 { "+" } else { "" };
        format!("{label} · 音高 {sign}{pitch} 共鸣 {formant:.2}")
    }
}

// ---------------------------------------------------------------------------
// index bindings
// ---------------------------------------------------------------------------

pub fn list_index_bindings(root: &Path, model_dir: &str) -> Result<Value, String> {
    let md = PathBuf::from(model_dir);
    guard_model_dir(root, &md)?;
    let mut side = read_sidecar(&md);
    let mut files: Vec<String> = Vec::new();
    // local *.index
    if let Ok(rd) = fs::read_dir(&md) {
        for e in rd.flatten() {
            let p = e.path();
            if p.extension()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .eq_ignore_ascii_case("index")
            {
                files.push(
                    p.canonicalize()
                        .unwrap_or(p)
                        .to_string_lossy()
                        .into_owned(),
                );
            }
        }
    }
    if let Some(arr) = side.get("index_files").and_then(|v| v.as_array()) {
        for v in arr {
            if let Some(s) = v.as_str() {
                let p = PathBuf::from(s);
                if p.is_file() {
                    let rp = p
                        .canonicalize()
                        .unwrap_or(p)
                        .to_string_lossy()
                        .into_owned();
                    if !files.iter().any(|x| x == &rp) {
                        files.push(rp);
                    }
                }
            }
        }
    }
    files.sort();
    let active = resolve_active_index(&md, &side);
    side.insert("index_files".into(), json!(files));
    side.insert("index".into(), json!(active));
    let _ = write_sidecar(&md, &side);

    let items: Vec<Value> = std::iter::once(json!({
        "path": "",
        "label": "不用检索库（仅 .pth）",
        "badge": "",
        "active": active.is_empty(),
    }))
    .chain(files.iter().map(|p| {
        let pb = PathBuf::from(p);
        let label = pb
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or(p)
            .to_string();
        let badge = if path_inside_dir(&pb, &md) {
            "当前音色目录".to_string()
        } else {
            pb.parent()
                .map(|x| x.to_string_lossy().into_owned())
                .unwrap_or_default()
        };
        let is_active = !active.is_empty()
            && (active == *p
                || PathBuf::from(&active).canonicalize().ok()
                    == pb.canonicalize().ok());
        json!({
            "path": p,
            "label": label,
            "badge": badge,
            "active": is_active,
        })
    }))
    .collect();

    Ok(json!({ "items": items, "active": active, "model_dir": model_dir }))
}

fn guard_model_dir(root: &Path, md: &Path) -> Result<(), String> {
    let models = paths::models_dir(root);
    let Ok(md_c) = md.canonicalize() else {
        return Err("音色目录不存在".into());
    };
    let Ok(root_c) = models.canonicalize() else {
        return Err("models 目录不存在".into());
    };
    if !md_c.starts_with(&root_c) {
        return Err("路径不在音色库内".into());
    }
    // starts_with is also true when the paths are equal, so without this a
    // delete_voice(models_dir) would recursively wipe the whole library. The UI
    // never passes it today, but this is the most destructive operation in the
    // app and it should not be one bad argument away.
    if md_c == root_c {
        return Err("不能操作音色库根目录".into());
    }
    Ok(())
}

pub fn set_active_index(root: &Path, model_dir: &str, index_path: &str) -> Result<Value, String> {
    let md = PathBuf::from(model_dir);
    guard_model_dir(root, &md)?;
    let mut side = read_sidecar(&md);
    if index_path.trim().is_empty() {
        side.insert("index".into(), json!(""));
        write_sidecar(&md, &side)?;
        return list_index_bindings(root, model_dir);
    }
    let local = ensure_index_in_model_dir(&md, Path::new(index_path))?;
    let mut files: Vec<String> = side
        .get("index_files")
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|x| x.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();
    if !files.iter().any(|f| f == &local) {
        files.push(local.clone());
    }
    side.insert("index_files".into(), json!(files));
    side.insert("index".into(), json!(local));
    write_sidecar(&md, &side)?;
    // Keep app selection in sync if this is current model
    let cfg = load_app_config(root);
    if cfg.get("last_model_path").and_then(|v| v.as_str()).unwrap_or("")
        == find_pth(&md)
            .map(|p| p.to_string_lossy().into_owned())
            .unwrap_or_default()
    {
        let _ = sync_inuse_model(
            root,
            cfg.get("last_model_path")
                .and_then(|v| v.as_str())
                .unwrap_or(""),
            &local,
        );
    }
    list_index_bindings(root, model_dir)
}

pub fn bind_index_file(root: &Path, model_dir: &str, index_src: &str) -> Result<Value, String> {
    let md = PathBuf::from(model_dir);
    guard_model_dir(root, &md)?;
    let local = ensure_index_in_model_dir(&md, Path::new(index_src))?;
    let mut side = read_sidecar(&md);
    let mut files: Vec<String> = side
        .get("index_files")
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|x| x.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();
    if !files.iter().any(|f| f == &local) {
        files.push(local.clone());
    }
    side.insert("index_files".into(), json!(files));
    side.insert("index".into(), json!(local));
    write_sidecar(&md, &side)?;
    list_index_bindings(root, model_dir)
}

pub fn unbind_index(root: &Path, model_dir: &str, index_path: &str) -> Result<Value, String> {
    let md = PathBuf::from(model_dir);
    guard_model_dir(root, &md)?;
    let mut side = read_sidecar(&md);
    let target = PathBuf::from(index_path)
        .canonicalize()
        .map(|p| p.to_string_lossy().into_owned())
        .unwrap_or_else(|_| index_path.to_string());
    let files: Vec<String> = side
        .get("index_files")
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|x| x.as_str().map(|s| s.to_string()))
                .filter(|s| {
                    let rp = PathBuf::from(s)
                        .canonicalize()
                        .map(|p| p.to_string_lossy().into_owned())
                        .unwrap_or_else(|_| s.clone());
                    rp != target
                })
                .collect()
        })
        .unwrap_or_default();
    side.insert("index_files".into(), json!(files));
    let active = side
        .get("index")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let active_r = PathBuf::from(&active)
        .canonicalize()
        .map(|p| p.to_string_lossy().into_owned())
        .unwrap_or(active);
    if active_r == target {
        side.insert("index".into(), json!(""));
    }
    write_sidecar(&md, &side)?;
    list_index_bindings(root, model_dir)
}

pub fn pick_index_file() -> Option<String> {
    rfd::FileDialog::new()
        .add_filter("特征索引", &["index"])
        .add_filter("全部", &["*"])
        .set_title("选择特征索引文件 (.index)")
        .pick_file()
        .map(|p| p.to_string_lossy().into_owned())
}

// ---------------------------------------------------------------------------
// profiles
// ---------------------------------------------------------------------------

fn profiles_dir(model_dir: &Path) -> PathBuf {
    model_dir.join(PROFILES_DIR)
}

/// Resolve `<model>/profiles/<id>.tmvp`, refusing anything that is not a plain
/// file name.
///
/// Every profile path is built by pasting a caller-supplied id into a filename.
/// `join("../../x")` walks straight out of the model directory, and
/// `delete_profile` then calls `remove_file` on the result. Ids only ever come
/// from a directory listing today, but that is a property of the current UI,
/// not of this function.
fn profile_path(model_dir: &Path, profile_id: &str) -> Result<PathBuf, String> {
    let bad = profile_id.is_empty()
        || profile_id.contains('/')
        || profile_id.contains('\\')
        || profile_id.contains(':')
        || profile_id.contains("..");
    if bad {
        return Err(format!("档案名不合法：{profile_id:?}"));
    }
    Ok(profiles_dir(model_dir).join(format!("{profile_id}{PROFILE_EXT}")))
}

fn source_label(src: &str) -> String {
    match src {
        "default" => "原始".into(),
        "self" => "自建".into(),
        "import" => "导入".into(),
        "official" => "官方优化".into(),
        other => other.to_string(),
    }
}

fn apply_profile_to_cfg(model_dir: &str, cfg: &mut Map<String, Value>) {
    let md = PathBuf::from(model_dir);
    let side = read_sidecar(&md);
    let pid = side
        .get("active_profile")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    cfg.insert("_active_profile_id".into(), json!(pid));
    if pid.is_empty() {
        cfg.insert("_active_profile_name".into(), json!(""));
        // model inline params
        for k in ["pitch", "formant", "index_rate", "rms_mix_rate", "threhold", "f0method"] {
            if let Some(v) = side.get(k) {
                if !v.is_null() {
                    cfg.insert(k.to_string(), v.clone());
                }
            }
        }
        return;
    }
    let Ok(path) = profile_path(&md, &pid) else {
        cfg.insert("_active_profile_name".into(), json!(""));
        return;
    };
    let prof = read_json(&path);
    if !prof.is_object() {
        cfg.insert("_active_profile_name".into(), json!(""));
        return;
    }
    let name = prof
        .get("name")
        .and_then(|v| v.as_str())
        .unwrap_or("档案")
        .to_string();
    cfg.insert("_active_profile_name".into(), json!(name));
    for group in ["voice", "fx", "perf"] {
        if let Some(g) = prof.get(group).and_then(|v| v.as_object()) {
            for (k, v) in g {
                cfg.insert(k.clone(), v.clone());
            }
        }
    }
}

pub fn list_profiles(root: &Path, model_dir: &str) -> Result<Value, String> {
    let md = PathBuf::from(model_dir);
    guard_model_dir(root, &md)?;
    let side = read_sidecar(&md);
    let active = side
        .get("active_profile")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    let mut items = vec![json!({
        "id": "",
        "name": "默认（原始参数）",
        "source": "default",
        "source_label": "原始",
        "score": null,
        "active": active.is_empty(),
        "desc": "",
    })];

    let dir = profiles_dir(&md);
    if let Ok(rd) = fs::read_dir(&dir) {
        let mut files: Vec<PathBuf> = rd
            .flatten()
            .map(|e| e.path())
            .filter(|p| {
                p.extension()
                    .and_then(|s| s.to_str())
                    .unwrap_or("")
                    .eq_ignore_ascii_case("tmvp")
                    || p.file_name()
                        .and_then(|s| s.to_str())
                        .unwrap_or("")
                        .ends_with(PROFILE_EXT)
            })
            .collect();
        files.sort();
        for f in files {
            let stem = f
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .to_string();
            let prof = read_json(&f);
            let name = prof
                .get("name")
                .and_then(|v| v.as_str())
                .unwrap_or(&stem)
                .to_string();
            let src = prof
                .get("meta")
                .and_then(|v| v.get("source"))
                .and_then(|v| v.as_str())
                .unwrap_or("self")
                .to_string();
            let score = prof
                .get("meta")
                .and_then(|v| v.get("score"))
                .cloned()
                .unwrap_or(Value::Null);
            let voice = prof.get("voice").and_then(|v| v.as_object());
            let pitch = voice
                .and_then(|v| v.get("pitch"))
                .and_then(|v| v.as_i64().or_else(|| v.as_f64().map(|f| f as i64)))
                .unwrap_or(0);
            let formant = voice
                .and_then(|v| v.get("formant"))
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0);
            let mut desc = format!("音高 {pitch:+} · 共鸣 {formant:.2}");
            if let Some(s) = score.as_f64() {
                desc = format!("{desc} · 相似度 {s:.2}");
            }
            items.push(json!({
                "id": stem,
                "name": name,
                "source": src,
                "source_label": source_label(&src),
                "score": score,
                "active": active == stem,
                "desc": desc,
            }));
        }
    }

    Ok(json!({
        "items": items,
        "active_id": active,
        "model_dir": model_dir,
    }))
}

pub fn set_active_profile(
    root: &Path,
    model_dir: &str,
    profile_id: &str,
) -> Result<Value, String> {
    let md = PathBuf::from(model_dir);
    guard_model_dir(root, &md)?;
    let mut side = read_sidecar(&md);
    side.insert("active_profile".into(), json!(profile_id));
    write_sidecar(&md, &side)?;

    let mut cfg = load_app_config(root);
    apply_profile_to_cfg(model_dir, &mut cfg);
    save_app_config(root, &cfg)?;

    // Push hot params if possible (best-effort; UI also does this)
    Ok(json!({
        "ok": true,
        "profiles": list_profiles(root, model_dir)?,
        "pitch": cfg.get("pitch").cloned().unwrap_or(json!(0)),
        "formant": cfg.get("formant").cloned().unwrap_or(json!(0.0)),
        "profile_summary": profile_summary_from_cfg(&cfg),
        "hot": {
            "pitch": cfg.get("pitch"),
            "formant": cfg.get("formant"),
            "index_rate": cfg.get("index_rate"),
            "rms_mix_rate": cfg.get("rms_mix_rate"),
            "threhold": cfg.get("threhold"),
        }
    }))
}

pub fn save_current_as_profile(
    root: &Path,
    model_dir: &str,
    name: &str,
) -> Result<Value, String> {
    let md = PathBuf::from(model_dir);
    guard_model_dir(root, &md)?;
    let cfg = load_app_config(root);
    let id = format!(
        "{:x}",
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
            % 0xffff_ffff_ffff
    );
    let id = &id[..id.len().min(12)];
    let mut voice = Map::new();
    for k in ["pitch", "formant", "index_rate", "rms_mix_rate", "threhold", "f0method"] {
        if let Some(v) = cfg.get(k) {
            if !v.is_null() {
                voice.insert(k.to_string(), v.clone());
            }
        }
    }
    let mut fx = Map::new();
    for k in [
        "fx_enabled",
        "fx_gate_enabled",
        "fx_gate_threshold_db",
        "fx_gate_release_ms",
        "fx_gate_hold_ms",
        "fx_gate_range_db",
        "fx_comp_enabled",
        "fx_comp_threshold_db",
        "fx_comp_ratio",
        "fx_comp_attack_ms",
        "fx_comp_release_ms",
        "fx_comp_makeup_db",
        "fx_eq_enabled",
        "fx_eq_gains",
        "fx_eq_preset",
        "fx_out_gain_db",
    ] {
        if let Some(v) = cfg.get(k) {
            if !v.is_null() {
                fx.insert(k.to_string(), v.clone());
            }
        }
    }
    let mut perf = Map::new();
    for k in ["block_time", "crossfade_length", "extra_time"] {
        if let Some(v) = cfg.get(k) {
            if !v.is_null() {
                perf.insert(k.to_string(), v.clone());
            }
        }
    }
    let display = if name.trim().is_empty() {
        "未命名档案"
    } else {
        name.trim()
    };
    let for_model = md
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_string();
    let now = chrono_lite_now();
    let prof = json!({
        "schema_version": 1,
        "id": id,
        "name": display.chars().take(60).collect::<String>(),
        "voice": voice,
        "fx": fx,
        "perf": perf,
        "meta": {
            "source": "self",
            "score": null,
            "for_model": for_model,
            "created": now,
        }
    });
    let dest = profile_path(&md, id)?;
    fs::create_dir_all(profiles_dir(&md)).map_err(|e| e.to_string())?;
    write_json_atomic(&dest, &prof)?;
    set_active_profile(root, model_dir, id)
}

fn chrono_lite_now() -> String {
    // Local-ish YYYY-MM-DD HH:MM:SS without chrono dep
    use std::time::SystemTime;
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    // UTC approximation is fine for created stamp
    let days = secs / 86400;
    let rem = secs % 86400;
    let h = rem / 3600;
    let m = (rem % 3600) / 60;
    let s = rem % 60;
    // rough civil date from days since epoch
    let (y, mo, d) = days_to_ymd(days as i64);
    format!("{y:04}-{mo:02}-{d:02} {h:02}:{m:02}:{s:02}")
}

fn days_to_ymd(mut days: i64) -> (i32, u32, u32) {
    // Algorithm from civil_from_days (Howard Hinnant)
    days += 719468;
    let era = if days >= 0 { days } else { days - 146096 } / 146097;
    let doe = (days - era * 146097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = (yoe as i64) + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    (y as i32, m as u32, d as u32)
}

pub fn delete_profile(root: &Path, model_dir: &str, profile_id: &str) -> Result<Value, String> {
    let md = PathBuf::from(model_dir);
    guard_model_dir(root, &md)?;
    if profile_id.is_empty() {
        return Err("不能删除默认档案".into());
    }
    let path = profile_path(&md, profile_id)?;
    let _ = fs::remove_file(&path);
    let side = read_sidecar(&md);
    if side
        .get("active_profile")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        == profile_id
    {
        return set_active_profile(root, model_dir, "");
    }
    list_profiles(root, model_dir)
}

pub fn import_profile(root: &Path, model_dir: &str) -> Result<Value, String> {
    let path = rfd::FileDialog::new()
        .add_filter("配置档案", &["tmvp", "json"])
        .set_title("导入配置档案")
        .pick_file()
        .ok_or_else(|| "已取消".to_string())?;
    let raw = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let mut data: Value = serde_json::from_str(&raw).map_err(|e| format!("无效档案: {e}"))?;
    if !data.is_object() {
        return Err("档案格式无效".into());
    }
    let fresh_id = || {
        format!(
            "{:x}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0)
                % 0xffff_ffff
        )
    };
    // The id is read out of the imported file, and .tmvp files are made to be
    // passed around — a shared profile carrying `"id": "../../../evil"` would
    // otherwise have us write outside the model directory entirely. Anything
    // that is not a plain name gets replaced rather than rejected: the profile
    // itself is still perfectly usable under a new id.
    let id = data
        .get("id")
        .and_then(|v| v.as_str())
        .map(str::to_string)
        .filter(|s| profile_path(Path::new("x"), s).is_ok())
        .unwrap_or_else(fresh_id);
    if let Some(obj) = data.as_object_mut() {
        obj.insert("id".into(), json!(id));
        if let Some(meta) = obj.get_mut("meta").and_then(|v| v.as_object_mut()) {
            meta.insert("source".into(), json!("import"));
        } else {
            obj.insert(
                "meta".into(),
                json!({"source": "import", "score": null, "for_model": "", "created": chrono_lite_now()}),
            );
        }
    }
    let md = PathBuf::from(model_dir);
    guard_model_dir(root, &md)?;
    let dest = profile_path(&md, &id)?;
    fs::create_dir_all(profiles_dir(&md)).map_err(|e| e.to_string())?;
    write_json_atomic(&dest, &data)?;
    set_active_profile(root, model_dir, &id)
}

pub fn export_active_profile(root: &Path, model_dir: &str) -> Result<Value, String> {
    let md = PathBuf::from(model_dir);
    guard_model_dir(root, &md)?;
    let side = read_sidecar(&md);
    let pid = side
        .get("active_profile")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    if pid.is_empty() {
        return Err("当前是默认参数，没有可导出的档案。请先「另存当前为档案」。".into());
    }
    let src = profile_path(&md, &pid)?;
    if !src.is_file() {
        return Err("活动档案文件不存在".into());
    }
    let name = read_json(&src)
        .get("name")
        .and_then(|v| v.as_str())
        .unwrap_or(&pid)
        .to_string();
    let safe: String = name
        .chars()
        .map(|c| {
            if r#"\/:*?"<>|"#.contains(c) {
                '_'
            } else {
                c
            }
        })
        .take(80)
        .collect();
    let dest = rfd::FileDialog::new()
        .set_file_name(format!("{safe}.tmvp"))
        .add_filter("配置档案", &["tmvp"])
        .set_title("导出当前档案（可分享）")
        .save_file()
        .ok_or_else(|| "已取消".to_string())?;
    fs::copy(&src, &dest).map_err(|e| e.to_string())?;
    Ok(json!({ "ok": true, "path": dest.to_string_lossy() }))
}

// ---------------------------------------------------------------------------
// import / delete / open / promote
// ---------------------------------------------------------------------------

pub fn pick_import_files() -> Vec<String> {
    rfd::FileDialog::new()
        .add_filter("音色", &["pth", "index", "zip"])
        .add_filter("全部", &["*"])
        .set_title("导入音色…")
        .pick_files()
        .unwrap_or_default()
        .into_iter()
        .map(|p| p.to_string_lossy().into_owned())
        .collect()
}

pub fn import_files(
    root: &Path,
    paths: &[String],
    current_model_dir: Option<&str>,
) -> Result<Value, String> {
    let _ = paths::ensure_user_dirs(root);
    let models_root = paths::models_dir(root);
    let mut models = Vec::new();
    let mut indices = Vec::new();
    let mut errors = Vec::new();
    let mut skipped = Vec::new();

    for p in paths {
        let path = PathBuf::from(p);
        if !path.is_file() {
            errors.push(json!({"path": p, "error": "文件不存在"}));
            continue;
        }
        let ext = path
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        match ext.as_str() {
            "zip" => match crate::store::install_voice_pack_zip(
                root,
                &path,
                "",
                "",
                "音色",
                false, // local user import — never mark as 图灵镜 official
            ) {
                Ok(info) => models.push(info),
                Err(e) => errors.push(json!({"path": p, "error": e})),
            },
            "pth" => match import_pth(root, &path) {
                Ok(info) => models.push(info),
                Err(e) => errors.push(json!({"path": p, "error": e})),
            },
            "index" => {
                let md = current_model_dir
                    .filter(|s| !s.is_empty())
                    .map(PathBuf::from)
                    .ok_or_else(|| "导入 .index 需要先选中一个可管理音色".to_string());
                match md {
                    Ok(md) => match guard_model_dir(root, &md)
                        .and_then(|_| ensure_index_in_model_dir(&md, &path))
                    {
                        Ok(local) => {
                            let mut side = read_sidecar(&md);
                            side.insert("index".into(), json!(local));
                            let mut files: Vec<String> = side
                                .get("index_files")
                                .and_then(|v| v.as_array())
                                .map(|a| {
                                    a.iter()
                                        .filter_map(|x| x.as_str().map(|s| s.to_string()))
                                        .collect()
                                })
                                .unwrap_or_default();
                            if !files.iter().any(|f| f == &local) {
                                files.push(local.clone());
                            }
                            side.insert("index_files".into(), json!(files));
                            let _ = write_sidecar(&md, &side);
                            indices.push(json!({"path": local, "model_dir": md.to_string_lossy()}));
                        }
                        Err(e) => errors.push(json!({"path": p, "error": e})),
                    },
                    Err(e) => errors.push(json!({"path": p, "error": e})),
                }
            }
            _ => skipped.push(p.clone()),
        }
    }
    let _ = models_root;
    Ok(json!({
        "models": models,
        "indices": indices,
        "errors": errors,
        "skipped_other": skipped,
    }))
}

fn import_pth(root: &Path, src: &Path) -> Result<Value, String> {
    let name = safe_model_dir_name(
        src.file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("voice"),
    )?;
    let dest_dir = paths::models_dir(root).join(&name);
    fs::create_dir_all(&dest_dir).map_err(|e| e.to_string())?;
    let dest_pth = dest_dir.join(src.file_name().unwrap_or_default());
    if dest_pth.canonicalize().ok() != src.canonicalize().ok() {
        fs::copy(src, &dest_pth).map_err(|e| format!("复制 .pth 失败: {e}"))?;
    }
    // sibling index
    let mut index_path = String::new();
    let sib = src.with_extension("index");
    if sib.is_file() {
        index_path = ensure_index_in_model_dir(&dest_dir, &sib)?;
    } else if let Some(parent) = src.parent() {
        if let Ok(rd) = fs::read_dir(parent) {
            for e in rd.flatten() {
                let p = e.path();
                if p.extension()
                    .and_then(|s| s.to_str())
                    .unwrap_or("")
                    .eq_ignore_ascii_case("index")
                {
                    let stem = src.file_stem().and_then(|s| s.to_str()).unwrap_or("");
                    let pname = p.file_stem().and_then(|s| s.to_str()).unwrap_or("");
                    if pname.contains(stem) || pname.contains(&name) {
                        index_path = ensure_index_in_model_dir(&dest_dir, &p)?;
                        break;
                    }
                }
            }
        }
    }
    let mut side = Map::new();
    side.insert("name".into(), json!(name));
    side.insert("tag".into(), json!(guess_tag(&name)));
    side.insert(
        "file".into(),
        json!(dest_pth.file_name().and_then(|s| s.to_str()).unwrap_or("")),
    );
    side.insert("source".into(), json!("import"));
    if !index_path.is_empty() {
        side.insert("index".into(), json!(index_path));
        side.insert("index_files".into(), json!([index_path]));
    }
    write_sidecar(&dest_dir, &side)?;
    Ok(json!({
        "name": name,
        "path": dest_pth.to_string_lossy(),
        "file": dest_pth.file_name().and_then(|s| s.to_str()).unwrap_or(""),
        "dir": dest_dir.to_string_lossy(),
        "index": index_path,
        "tag": guess_tag(&name),
        "source": "user_data",
    }))
}

pub fn delete_voice(root: &Path, model_dir: &str) -> Result<Value, String> {
    let md = PathBuf::from(model_dir);
    guard_model_dir(root, &md)?;
    fn clear_ro(p: &Path) {
        if let Ok(meta) = fs::metadata(p) {
            let mut perms = meta.permissions();
            perms.set_readonly(false);
            let _ = fs::set_permissions(p, perms);
        }
    }
    fn rm(p: &Path) -> Result<(), String> {
        if p.is_file() {
            clear_ro(p);
            return fs::remove_file(p).map_err(|e| e.to_string());
        }
        if p.is_dir() {
            for e in fs::read_dir(p).map_err(|e| e.to_string())? {
                rm(&e.map_err(|e| e.to_string())?.path())?;
            }
            clear_ro(p);
            return fs::remove_dir(p).map_err(|e| e.to_string());
        }
        Ok(())
    }
    rm(&md)?;
    Ok(json!({"ok": true}))
}

pub fn rename_voice(root: &Path, model_dir: &str, new_name: &str) -> Result<Value, String> {
    let md = PathBuf::from(model_dir);
    guard_model_dir(root, &md)?;
    let name = new_name.trim();
    if name.is_empty() {
        return Err("名称不能为空".into());
    }
    let mut side = read_sidecar(&md);
    side.insert("name".into(), json!(name));
    write_sidecar(&md, &side)?;
    Ok(json!({"ok": true, "name": name}))
}

pub fn promote_legacy(root: &Path, pth_path: &str) -> Result<Value, String> {
    let src = PathBuf::from(pth_path);
    if !src.is_file() {
        return Err("源 .pth 不存在".into());
    }
    import_pth(root, &src)
}

pub fn open_models_dir(root: &Path) -> Result<(), String> {
    let d = paths::models_dir(root);
    fs::create_dir_all(&d).map_err(|e| e.to_string())?;
    #[cfg(windows)]
    {
        std::process::Command::new("explorer")
            .arg(d.as_os_str())
            .spawn()
            .map_err(|e| e.to_string())?;
        return Ok(());
    }
    #[cfg(not(windows))]
    {
        std::process::Command::new("xdg-open")
            .arg(d.as_os_str())
            .spawn()
            .map_err(|e| e.to_string())?;
        Ok(())
    }
}

pub fn current_selection_summary(root: &Path) -> Value {
    let cat = list_voices(root);
    let idx = cat.get("selected_idx").and_then(|v| v.as_i64()).unwrap_or(-1);
    let models = cat.get("models").and_then(|v| v.as_array());
    let model = if idx >= 0 {
        models.and_then(|a| a.get(idx as usize).cloned())
    } else {
        None
    };
    let cfg = load_app_config(root);
    let mut profile_name = String::new();
    if let Some(ref m) = model {
        if let Some(dir) = m.get("dir").and_then(|v| v.as_str()) {
            if m.get("source").and_then(|v| v.as_str()) == Some("user_data") {
                let side = read_sidecar(Path::new(dir));
                let pid = side
                    .get("active_profile")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");
                if let Ok(pp) = profile_path(Path::new(dir), pid) {
                    let prof = read_json(&pp);
                    profile_name = prof
                        .get("name")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string();
                }
            }
        }
    }
    let mut cfg2 = cfg.clone();
    cfg2.insert("_active_profile_name".into(), json!(profile_name));
    // Position in the library, for the dock's "少女音 · 2/7" line. The UI had
    // no source for this and shipped a hardcoded "1/3" to every user.
    let total = models.map(|a| a.len()).unwrap_or(0);
    json!({
        "model": model,
        "pitch": cfg.get("pitch").cloned().unwrap_or(json!(0)),
        "formant": cfg.get("formant").cloned().unwrap_or(json!(0.0)),
        "profile_summary": profile_summary_from_cfg(&cfg2),
        "index": if idx >= 0 { idx + 1 } else { 0 },
        "total": total,
        "catalog": cat,
    })
}


#[cfg(test)]
mod tests {
    use super::*;

    fn model(name: &str, file: &str, path: &str) -> Value {
        json!({"name": name, "file": file, "path": path})
    }

    #[test]
    fn a_shared_pth_filename_cannot_hijack_the_selection() {
        // 社区音色包里 `model.pth` 这种文件名重名是常态。以前三个键或在一起、
        // 第一个撞上的赢，于是排在前面的同名模型把真正选中的那条顶掉了：
        // 界面「使用中」是别人，重开变声也用错模型 —— 而随手切一次别的再切
        // 回来就好了，因为那一下会把三个键一起改写。
        let models = vec![
            model("别人家的音色", "model.pth", "C:\\rvc\\models\\other\\model.pth"),
            model("我选的音色", "model.pth", "C:\\rvc\\models\\mine\\model.pth"),
        ];
        let idx = resolve_selected(
            &models,
            "C:\\rvc\\models\\mine\\model.pth", // 全路径，唯一，必须赢
            "model.pth",                        // 文件名，两条都对得上
            "我选的音色",
        );
        assert_eq!(idx, 1, "全路径对得上时不能被同名文件抢走");
    }

    #[test]
    fn falls_back_through_file_then_name() {
        let models = vec![
            model("甲", "a.pth", "/lib/a/a.pth"),
            model("乙", "b.pth", "/lib/b/b.pth"),
        ];
        // 路径变了（换了安装目录），文件名还在
        assert_eq!(resolve_selected(&models, "/old/b.pth", "b.pth", ""), 1);
        // 文件也重命名了，只剩显示名
        assert_eq!(resolve_selected(&models, "/old/x.pth", "x.pth", "乙"), 1);
        // 三个都对不上：退回第一条，而不是「未选择模型」
        assert_eq!(resolve_selected(&models, "/x", "x.pth", "丙"), 0);
        // 一条音色都没有
        assert_eq!(resolve_selected(&[], "/x", "x.pth", "丙"), -1);
    }

    #[test]
    fn guard_rejects_the_library_root_itself() {
        let root = std::env::temp_dir().join("rvcf-guard-test");
        let models = paths::models_dir(&root);
        let one = models.join("anon");
        std::fs::create_dir_all(&one).unwrap();

        // A real voice directory is fine.
        assert!(guard_model_dir(&root, &one).is_ok());
        // The library root is not — starts_with() alone would have allowed it
        // and delete_voice would have wiped every installed voice.
        let err = guard_model_dir(&root, &models).unwrap_err();
        assert!(err.contains("根目录"), "got {err}");
        // Anything outside stays rejected.
        assert!(guard_model_dir(&root, &root).is_err());

        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn profile_ids_cannot_escape_the_profiles_dir() {
        let md = Path::new("/tmp/model");
        for bad in [
            "",
            "..",
            "../x",
            "../../../../evil",
            "a/b",
            "a\\b",
            "C:evil",
            "sub/../../out",
        ] {
            assert!(
                profile_path(md, bad).is_err(),
                "should have rejected {bad:?}"
            );
        }
        let ok = profile_path(md, "1a2b3c").unwrap();
        assert_eq!(ok, md.join(PROFILES_DIR).join(format!("1a2b3c{PROFILE_EXT}")));
    }

    #[test]
    fn an_imported_profile_cannot_choose_a_traversing_id() {
        // .tmvp files are shared between users; the id inside one is untrusted.
        let hostile = "../../../../evil";
        assert!(profile_path(Path::new("x"), hostile).is_err());
    }
}
