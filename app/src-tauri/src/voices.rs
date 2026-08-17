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

/// 档案自己管的键。切模型时整组换成该模型的，不沿用上一个。
const PROFILE_VOICE_KEYS: &[&str] = &[
    "pitch",
    "formant",
    "index_rate",
    "rms_mix_rate",
    "threhold",
    "f0method",
];
const PROFILE_FX_KEYS: &[&str] = &[
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
];
const PROFILE_PERF_KEYS: &[&str] = &["block_time", "crossfade_length", "extra_time"];

/// 从内置清单（bundled，离线可用）按 id 找封面 URL。
/// 只在 sidecar 与包内都没有封面时查 —— 覆盖旧版本装的第三方音色
/// （安装时漏写 cover），一次文件读的代价可接受，不加跨 root 的缓存。
fn catalog_cover(root: &Path, id: &str) -> String {
    let cat = crate::store::fetch_store_catalog(root, false);
    for key in ["voices", "thirdparty_voices"] {
        let Some(arr) = cat.get(key).and_then(|v| v.as_array()) else {
            continue;
        };
        if let Some(item) = arr
            .iter()
            .find(|x| x.get("id").and_then(|i| i.as_str()) == Some(id))
        {
            return item
                .get("cover_url")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
        }
    }
    String::new()
}

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

fn guess_tag(name: &str) -> String {
    let n = name.to_lowercase();
    let k_girl = crate::i18n::t("s.26bc84961c");
    let k_loli = crate::i18n::t("s.2eb8caf80a");
    let k_shao = crate::i18n::t("s.22d9b9afb9");
    if [k_girl.as_str(), "girl", "loli", k_loli.as_str(), k_shao.as_str()]
        .iter()
        .any(|k| n.contains(k) || name.contains(k))
    {
        return crate::i18n::t("s.bacc87084d");
    }
    let k_boy = crate::i18n::t("s.51625d909c");
    let k_nan = crate::i18n::t("s.3c689400b4");
    let k_shu = crate::i18n::t("s.a0c5fa2d9f");
    if [k_boy.as_str(), "boy", k_nan.as_str(), k_shu.as_str()]
        .iter()
        .any(|k| n.contains(k) || name.contains(k))
    {
        return crate::i18n::t("s.3c689400b4");
    }
    let k_other = crate::i18n::t("s.b0684a167c");
    if name.contains(&k_other) {
        return crate::i18n::t("s.1bf4a01d78");
    }
    crate::i18n::t("s.c4301894a2")
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
    scan_models_dir(root, &paths::models_dir(root))
}

/// 扫一个音色目录。以前这里写死 `User_Data/models`；训练可以把音色放到别的盘
/// 之后，同一段逻辑要能对着任意目录跑。
fn scan_models_dir(root: &Path, models_root: &Path) -> Vec<Value> {
    let mut out = Vec::new();
    let Ok(rd) = fs::read_dir(models_root) else {
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
        // 名字/标签/作者按当前界面语言取：`config.json` 里存着下载时一并带下来
        // 的整张多语言表（store::copy_i18n_fields），`pick_str` 取不到译名才落回
        // 中文主名。所以换语言不用重新下载，模型页跟着变。
        let name = Some(crate::i18n::pick_str_obj(&side, "name"))
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| vid.clone());
        let tag = Some(crate::i18n::pick_str_obj(&side, "tag"))
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| guess_tag(&name).to_string());
        let author = crate::i18n::pick_str_obj(&side, "author");
        let author_url = side
            .get("author_url")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        // 来源仓库。第三方音色的清单里两个地址常常只有一个，模型页那个
        // 「⋯」菜单两条都挂，有哪条给哪条。
        let source_url = side
            .get("source_url")
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
        if cover.is_empty() {
            // 旧版本装的第三方音色，sidecar 里没有 cover（安装时漏写）。
            // 按 online_id 从内置清单回补封面 URL —— 用户不用重下也有封面。
            let oid = side
                .get("online_id")
                .and_then(|v| v.as_str())
                .unwrap_or(&vid)
                .to_string();
            cover = catalog_cover(root, &oid);
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
                "source_url": source_url,
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
            "source_url": source_url,
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
            "source_url": "",
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
        // 三个键都没对上就是没选中。以前退回第一条，选用 DSP 清掉音色之后
        // 列表又把第一条当成「使用中」，检索库跟着露出来。
        .map(|i| i as i64)
        .unwrap_or(-1)
}

pub fn list_voices(root: &Path) -> Value {
    let _ = paths::ensure_user_dirs(root);
    let mut primary = list_user_data(root);
    // 训练可以把音色放到别的盘（`train_output_dir`）。不扫这里的话，用户训完
    // 几小时，模型页上什么都没有 —— 文件明明在，只是没人去看那个目录。
    let extra = crate::config::train_output_dir(root);
    if !extra.trim().is_empty() {
        let extra = PathBuf::from(extra.trim());
        let default_root = paths::models_dir(root);
        // 指回默认目录时别扫第二遍。canonicalize 是为了认出 `..`、短名、
        // 大小写不同的同一个目录；取不到（目录还没建）就退回原样比较。
        let same = extra
            .canonicalize()
            .ok()
            .zip(default_root.canonicalize().ok())
            .map(|(a, b)| a == b)
            .unwrap_or(extra == default_root);
        if !same {
            primary.extend(scan_models_dir(root, &extra));
        }
    }
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

    let dsp_on = cfg
        .get("dsp_enabled")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    // DSP 开着时界面不能把 last_model 当成「当前音色」，否则首页中间那张
    // 卡还亮着，用户以为选了音色、一点开启却走 DSP 或被拒。
    let selected_idx = if dsp_on {
        -1
    } else {
        resolve_selected(
            &primary,
            &selected_path,
            &selected_file,
            &selected_name,
        )
    };

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
    let m = found.ok_or_else(|| crate::i18n::t("s.8cfc8f198c"))?;
    if m.get("missing").and_then(|v| v.as_bool()).unwrap_or(false) {
        return Err(crate::i18n::t("s.01eba6e7b6").into());
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

    // 档案参数按「这个音色」来，不沿用上一个模型留在 app_config 里的值。
    if let Some(md) = m.get("dir").and_then(|v| v.as_str()) {
        if m.get("source").and_then(|v| v.as_str()) == Some("user_data") {
            apply_profile_to_cfg(md, &mut cfg);
        } else {
            reset_profile_keys(&mut cfg);
            overlay_keys_from_value(&m, PROFILE_VOICE_KEYS, &mut cfg);
        }
    } else {
        reset_profile_keys(&mut cfg);
        overlay_keys_from_value(&m, PROFILE_VOICE_KEYS, &mut cfg);
    }

    // RVC / DSP 二选一：选了音色就把 DSP 关掉。预设参数也要清，
    // 不然 start 看见残留 dsp_params 还会当成纯 DSP。
    cfg.insert("dsp_enabled".into(), json!(false));
    cfg.insert("dsp_preset".into(), json!(""));
    cfg.insert("dsp_params".into(), json!({}));
    cfg.insert("function".into(), json!("vc"));

    save_app_config(root, &cfg)?;

    // Sync engine inuse config if present
    let _ = sync_inuse_model(
        root,
        m.get("path").and_then(|v| v.as_str()).unwrap_or(""),
        m.get("index").and_then(|v| v.as_str()).unwrap_or(""),
    );
    let _ = crate::config::sync_inuse(root, &cfg);

    Ok(json!({
        "ok": true,
        "model": m,
        "pitch": cfg.get("pitch").cloned().unwrap_or(json!(0)),
        "formant": cfg.get("formant").cloned().unwrap_or(json!(0.0)),
        "active_profile": cfg.get("_active_profile_name").cloned().unwrap_or(json!("")),
        "profile_summary": profile_summary_from_cfg(&cfg),
    }))
}

/// 丢掉当前选中的 RVC 音色，好让 DSP 走纯 fx。
///
/// `sync_inuse` 不会把空 pth 写进 inuse，所以必须走 force_clear。
pub fn clear_voice(root: &Path) -> Result<Value, String> {
    crate::config::force_clear_model_paths(root)?;
    // 正在变声的话，还得让引擎当场把 RVC 放掉 —— 光清配置只改了下次开启。
    // 没在跑就是 Err，那时候本来也没什么要热更新的。
    let dropped = crate::worker::drop_model(root).is_ok();
    Ok(json!({ "ok": true, "dropped": dropped }))
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
        crate::i18n::t("s.8923a00d0b")
    } else {
        name.to_string()
    };
    if pitch == 0 && (formant - 0.0).abs() < 0.001 {
        label
    } else {
        // Template s.6aaa2fc9a9: "{label} · 音高 {sign}{pitch} 共鸣 {formant:.2}"
        // Pass preformatted keys so locale packs keep format specs.
        let sign = if pitch >= 0 { "+" } else { "" };
        let mut vars = std::collections::HashMap::new();
        vars.insert("label".into(), label);
        vars.insert("sign".into(), sign.to_string());
        vars.insert("pitch".into(), pitch.to_string());
        vars.insert("formant:.2".into(), format!("{formant:.2}"));
        crate::i18n::t_vars("s.6aaa2fc9a9", &vars)
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
        "label": &crate::i18n::t("s.76bf90ae3e"),
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
            crate::i18n::t("s.a7018f695e")
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
        return Err(crate::i18n::t("s.3c07b16355").into());
    };
    let Ok(root_c) = models.canonicalize() else {
        return Err(crate::i18n::t("s.3ba595eced").into());
    };
    if !md_c.starts_with(&root_c) {
        return Err(crate::i18n::t("s.899c21edd3").into());
    }
    // starts_with is also true when the paths are equal, so without this a
    // delete_voice(models_dir) would recursively wipe the whole library. The UI
    // never passes it today, but this is the most destructive operation in the
    // app and it should not be one bad argument away.
    if md_c == root_c {
        return Err(crate::i18n::t("s.b43921940c").into());
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
    crate::shell_extras::dialog()
        .add_filter(&crate::i18n::t("s.dc66c55a2e"), &["index"])
        .add_filter(&crate::i18n::t("s.778fc8f994"), &["*"])
        .set_title(&crate::i18n::t("s.6832505652"))
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
        return Err(crate::i18n::te("s.e178207ec7", &(profile_id)));
    }
    Ok(profiles_dir(model_dir).join(format!("{profile_id}{PROFILE_EXT}")))
}

fn profile_voice_desc(src: &Map<String, Value>) -> String {
    let mut cfg = Map::new();
    reset_profile_keys(&mut cfg);
    overlay_keys(src, PROFILE_VOICE_KEYS, &mut cfg);
    let pitch = cfg
        .get("pitch")
        .and_then(|v| v.as_i64().or_else(|| v.as_f64().map(|f| f as i64)))
        .unwrap_or(0);
    let formant = cfg
        .get("formant")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0);
    crate::i18n::t2(
        "s.8ece88dffe",
        &format!("{:+}", pitch),
        &format!("{:.2}", formant),
    )
}

fn source_label(src: &str) -> String {
    match src {
        "default" => crate::i18n::t("s.a55afe4b5f"),
        "self" => crate::i18n::t("s.b5f0bfe1d8"),
        "import" => crate::i18n::t("s.60e2bcad85"),
        "official" => crate::i18n::t("s.291eab062c"),
        other => other.to_string(),
    }
}

fn reset_profile_keys(cfg: &mut Map<String, Value>) {
    let d = crate::config::defaults();
    for k in PROFILE_VOICE_KEYS
        .iter()
        .chain(PROFILE_FX_KEYS)
        .chain(PROFILE_PERF_KEYS)
    {
        if let Some(v) = d.get(*k) {
            cfg.insert((*k).to_string(), v.clone());
        }
    }
}

fn overlay_keys(src: &Map<String, Value>, keys: &[&str], dest: &mut Map<String, Value>) {
    for k in keys {
        match src.get(*k) {
            Some(v) if !v.is_null() && v != "" => {
                dest.insert((*k).to_string(), v.clone());
            }
            _ => {}
        }
    }
}

fn overlay_keys_from_value(src: &Value, keys: &[&str], dest: &mut Map<String, Value>) {
    let Some(obj) = src.as_object() else {
        return;
    };
    overlay_keys(obj, keys, dest);
}

fn overlay_profile_groups(prof: &Value, dest: &mut Map<String, Value>) {
    for (group, keys) in [
        ("voice", PROFILE_VOICE_KEYS),
        ("fx", PROFILE_FX_KEYS),
        ("perf", PROFILE_PERF_KEYS),
    ] {
        if let Some(g) = prof.get(group).and_then(|v| v.as_object()) {
            overlay_keys(g, keys, dest);
        }
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
    // 先摊成产品默认，再盖这个音色自己的 sidecar / 具名档案。
    // 缺键不能留着上一个模型的音高。
    reset_profile_keys(cfg);
    overlay_keys(&side, PROFILE_VOICE_KEYS, cfg);
    overlay_keys(&side, PROFILE_FX_KEYS, cfg);
    overlay_keys(&side, PROFILE_PERF_KEYS, cfg);
    if pid.is_empty() {
        cfg.insert("_active_profile_name".into(), json!(""));
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
        .unwrap_or(&crate::i18n::t("s.3ca928cd40"))
        .to_string();
    cfg.insert("_active_profile_name".into(), json!(name));
    overlay_profile_groups(&prof, cfg);
}

fn patch_has_profile_keys(patch: &Map<String, Value>) -> bool {
    PROFILE_VOICE_KEYS
        .iter()
        .chain(PROFILE_FX_KEYS)
        .chain(PROFILE_PERF_KEYS)
        .any(|k| patch.contains_key(*k))
}

fn merge_patch_into_group(dest: &mut Map<String, Value>, patch: &Map<String, Value>, keys: &[&str]) {
    for k in keys {
        if let Some(v) = patch.get(*k) {
            dest.insert((*k).to_string(), v.clone());
        }
    }
}

/// 设置页 / 底栏改了档案键：写回当前音色的默认 sidecar 或具名 .tmvp。
pub fn persist_profile_patch(root: &Path, patch: &Map<String, Value>) -> Result<(), String> {
    if !patch_has_profile_keys(patch) {
        return Ok(());
    }
    let cfg = load_app_config(root);
    let pth = cfg
        .get("last_model_path")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    if pth.is_empty() {
        return Ok(());
    }
    let pth_path = PathBuf::from(pth);
    let Some(md) = pth_path.parent() else {
        return Ok(());
    };
    if guard_model_dir(root, md).is_err() {
        return Ok(());
    }
    let mut side = read_sidecar(md);
    let pid = side
        .get("active_profile")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let named = !pid.is_empty() && profile_path(md, &pid).map(|p| p.is_file()).unwrap_or(false);
    if named {
        let path = profile_path(md, &pid)?;
        let mut prof = read_json(&path);
        let obj = prof.as_object_mut().ok_or_else(|| crate::i18n::t("s.dab1a19c29"))?;
        for (group, keys) in [
            ("voice", PROFILE_VOICE_KEYS),
            ("fx", PROFILE_FX_KEYS),
            ("perf", PROFILE_PERF_KEYS),
        ] {
            let mut g = obj
                .get(group)
                .and_then(|v| v.as_object())
                .cloned()
                .unwrap_or_default();
            merge_patch_into_group(&mut g, patch, keys);
            obj.insert(group.into(), Value::Object(g));
        }
        write_json_atomic(&path, &prof)?;
    } else {
        merge_patch_into_group(&mut side, patch, PROFILE_VOICE_KEYS);
        merge_patch_into_group(&mut side, patch, PROFILE_FX_KEYS);
        merge_patch_into_group(&mut side, patch, PROFILE_PERF_KEYS);
        write_sidecar(md, &side)?;
    }
    Ok(())
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

    let def_desc = profile_voice_desc(&side);
    let mut items = vec![json!({
        "id": "",
        "name": &crate::i18n::t("s.8923a00d0b"),
        "source": "default",
        "source_label": &crate::i18n::t("s.a55afe4b5f"),
        "score": null,
        "active": active.is_empty(),
        "desc": def_desc,
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
            let mut desc = crate::i18n::t2("s.8ece88dffe", &format!("{:+}", pitch), &format!("{:.2}", formant));
            if let Some(s) = score.as_f64() {
                desc = crate::i18n::t2("s.c67426f74d", &desc, &format!("{:.2}", s));
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
    overlay_keys(&cfg, PROFILE_VOICE_KEYS, &mut voice);
    let mut fx = Map::new();
    overlay_keys(&cfg, PROFILE_FX_KEYS, &mut fx);
    let mut perf = Map::new();
    overlay_keys(&cfg, PROFILE_PERF_KEYS, &mut perf);
    let display = if name.trim().is_empty() {
        &crate::i18n::t("s.6cdd7fc584")
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
        return Err(crate::i18n::t("s.5584cc4752").into());
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
    let path = crate::shell_extras::dialog()
        .add_filter(&crate::i18n::t("s.5ec6f626c3"), &["tmvp", "json"])
        .set_title(&crate::i18n::t("s.a49f8d4a05"))
        .pick_file()
        .ok_or_else(|| crate::i18n::t("s.a5ffdc95ee"))?;
    let raw = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let mut data: Value = serde_json::from_str(&raw).map_err(|e| crate::i18n::te("s.a5a2f91ea1", &(e)))?;
    if !data.is_object() {
        return Err(crate::i18n::t("s.dab1a19c29").into());
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
        return Err(crate::i18n::t("s.fffda47f1e").into());
    }
    let src = profile_path(&md, &pid)?;
    if !src.is_file() {
        return Err(crate::i18n::t("s.8af26d69aa").into());
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
    let dest = crate::shell_extras::dialog()
        .set_file_name(format!("{safe}.tmvp"))
        .add_filter(&crate::i18n::t("s.5ec6f626c3"), &["tmvp"])
        .set_title(&crate::i18n::t("s.217b12a5cb"))
        .save_file()
        .ok_or_else(|| crate::i18n::t("s.a5ffdc95ee"))?;
    fs::copy(&src, &dest).map_err(|e| e.to_string())?;
    Ok(json!({ "ok": true, "path": dest.to_string_lossy() }))
}

// ---------------------------------------------------------------------------
// import / delete / open / promote
// ---------------------------------------------------------------------------

pub fn pick_import_files() -> Vec<String> {
    crate::shell_extras::dialog()
        .add_filter(&crate::i18n::t("s.c4301894a2"), &["pth", "index", "zip"])
        .add_filter(&crate::i18n::t("s.778fc8f994"), &["*"])
        .set_title(&crate::i18n::t("s.54b3625b92"))
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
            errors.push(json!({"path": p, "error": &crate::i18n::t("s.ffcf0a1eb0")}));
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
                &crate::i18n::t("s.c4301894a2"),
                false, // local user import — never mark as 图灵镜 official
                None,  // 本地导入没有清单条目，多语言信息只能靠包里自带的
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
                    .ok_or_else(|| crate::i18n::t("s.acaebc442f"));
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
        fs::copy(src, &dest_pth).map_err(|e| crate::i18n::te("s.1090b966ea", &(e)))?;
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
        return Err(crate::i18n::t("s.ca898456b2").into());
    }
    let mut side = read_sidecar(&md);
    side.insert("name".into(), json!(name));
    write_sidecar(&md, &side)?;
    Ok(json!({"ok": true, "name": name}))
}

pub fn promote_legacy(root: &Path, pth_path: &str) -> Result<Value, String> {
    let src = PathBuf::from(pth_path);
    if !src.is_file() {
        return Err(crate::i18n::t("s.6f0a06a10f").into());
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
        // 语言是进程级全局状态，cargo 默认多线程跑测试。不钉住的话，
        // 断言里两次取文案可能落在不同语言上（实测到过法语 vs 韩语）。
        let _g = crate::i18n::testing::pin("zh-CN");
        // 社区音色包里 `model.pth` 这种文件名重名是常态。以前三个键或在一起、
        // 第一个撞上的赢，于是排在前面的同名模型把真正选中的那条顶掉了：
        // 界面「使用中」是别人，重开变声也用错模型 —— 而随手切一次别的再切
        // 回来就好了，因为那一下会把三个键一起改写。
        let models = vec![
            model(&crate::i18n::t("s.3d9fe9e5d0"), "model.pth", "C:\\rvc\\models\\other\\model.pth"),
            model(&crate::i18n::t("s.8fd94350c5"), "model.pth", "C:\\rvc\\models\\mine\\model.pth"),
        ];
        let idx = resolve_selected(
            &models,
            "C:\\rvc\\models\\mine\\model.pth", // 全路径，唯一，必须赢
            "model.pth",                        // 文件名，两条都对得上
            &crate::i18n::t("s.8fd94350c5"),
        );
        assert_eq!(idx, 1);
    }

    #[test]
    fn falls_back_through_file_then_name() {
        // 语言是进程级全局状态，cargo 默认多线程跑测试。不钉住的话，
        // 断言里两次取文案可能落在不同语言上（实测到过法语 vs 韩语）。
        let _g = crate::i18n::testing::pin("zh-CN");
        let models = vec![
            model(&crate::i18n::t("s.1b85dd8d61"), "a.pth", "/lib/a/a.pth"),
            model(&crate::i18n::t("s.3458316756"), "b.pth", "/lib/b/b.pth"),
        ];
        // 路径变了（换了安装目录），文件名还在
        assert_eq!(resolve_selected(&models, "/old/b.pth", "b.pth", ""), 1);
        // 文件也重命名了，只剩显示名
        assert_eq!(
            resolve_selected(
                &models,
                "/old/x.pth",
                "x.pth",
                &crate::i18n::t("s.3458316756")
            ),
            1
        );
        // 三个都对不上：就是没选中。退回第一条会让 DSP 清音色后检索库又露出来。
        assert_eq!(
            resolve_selected(&models, "/x", "x.pth", &crate::i18n::t("s.c72e61fc70")),
            -1
        );
        // 一条音色都没有
        assert_eq!(
            resolve_selected(&[], "/x", "x.pth", &crate::i18n::t("s.c72e61fc70")),
            -1
        );
    }

    #[test]
    fn guard_rejects_the_library_root_itself() {
        // 语言是进程级全局状态，别的测试改了会让这里的 t() 前后取到两种语言。
        let _g = crate::i18n::testing::pin("zh-CN");
        let root = std::env::temp_dir().join("rvcf-guard-test");
        let models = paths::models_dir(&root);
        let one = models.join("anon");
        std::fs::create_dir_all(&one).unwrap();

        // A real voice directory is fine.
        assert!(guard_model_dir(&root, &one).is_ok());
        // The library root is not — starts_with() alone would have allowed it
        // and delete_voice would have wiped every installed voice.
        let err = guard_model_dir(&root, &models).unwrap_err();
        assert!(err.contains(&crate::i18n::t("s.18755acbbb")), "got {err}");
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

    fn scratch(tag: &str) -> PathBuf {
        let p = std::env::temp_dir().join(format!(
            "rvcf-prof-{}-{}",
            tag,
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&p);
        p
    }

    #[test]
    fn default_profile_does_not_keep_previous_model_pitch() {
        let md = scratch("def-reset");
        std::fs::create_dir_all(&md).unwrap();
        write_sidecar(&md, &Map::new()).unwrap();
        let mut cfg = Map::new();
        cfg.insert("pitch".into(), json!(12));
        cfg.insert("formant".into(), json!(1.5));
        apply_profile_to_cfg(&md.to_string_lossy(), &mut cfg);
        assert_eq!(cfg["pitch"], json!(0));
        assert_eq!(cfg["formant"], json!(0.0));
        let _ = std::fs::remove_dir_all(&md);
    }

    #[test]
    fn default_profile_uses_this_model_sidecar() {
        let md = scratch("def-side");
        std::fs::create_dir_all(&md).unwrap();
        let mut side = Map::new();
        side.insert("pitch".into(), json!(7));
        side.insert("formant".into(), json!(0.4));
        write_sidecar(&md, &side).unwrap();
        let mut cfg = Map::new();
        cfg.insert("pitch".into(), json!(12));
        apply_profile_to_cfg(&md.to_string_lossy(), &mut cfg);
        assert_eq!(cfg["pitch"], json!(7));
        assert_eq!(cfg["formant"], json!(0.4));
        let _ = std::fs::remove_dir_all(&md);
    }

    #[test]
    fn persist_default_writes_sidecar_not_app_config_only() {
        let root = scratch("persist-def");
        let md = paths::models_dir(&root).join("voice-a");
        std::fs::create_dir_all(&md).unwrap();
        let pth = md.join("a.pth");
        std::fs::write(&pth, vec![0u8; 8]).unwrap();
        write_sidecar(&md, &Map::new()).unwrap();
        let mut cfg = Map::new();
        cfg.insert(
            "last_model_path".into(),
            json!(pth.to_string_lossy().to_string()),
        );
        save_app_config(&root, &cfg).unwrap();
        let mut patch = Map::new();
        patch.insert("pitch".into(), json!(8));
        persist_profile_patch(&root, &patch).unwrap();
        let side = read_sidecar(&md);
        assert_eq!(side["pitch"], json!(8));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn persist_named_updates_tmvp() {
        let root = scratch("persist-named");
        let md = paths::models_dir(&root).join("voice-b");
        std::fs::create_dir_all(md.join(PROFILES_DIR)).unwrap();
        let pth = md.join("b.pth");
        std::fs::write(&pth, vec![0u8; 8]).unwrap();
        let mut side = Map::new();
        side.insert("active_profile".into(), json!("p1"));
        write_sidecar(&md, &side).unwrap();
        let dest = profile_path(&md, "p1").unwrap();
        write_json_atomic(
            &dest,
            &json!({
                "id": "p1",
                "name": "test",
                "voice": { "pitch": 1, "formant": 0.1 },
                "fx": {},
                "perf": {}
            }),
        )
        .unwrap();
        let mut cfg = Map::new();
        cfg.insert(
            "last_model_path".into(),
            json!(pth.to_string_lossy().to_string()),
        );
        save_app_config(&root, &cfg).unwrap();
        let mut patch = Map::new();
        patch.insert("pitch".into(), json!(9));
        persist_profile_patch(&root, &patch).unwrap();
        let prof = read_json(&dest);
        assert_eq!(prof["voice"]["pitch"], json!(9));
        assert_eq!(prof["voice"]["formant"], json!(0.1));
        let _ = std::fs::remove_dir_all(&root);
    }
}
