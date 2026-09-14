//! 多目录清单服务（C-08/C-10）：来源、排除规则、扫描结果、任务快照分开。
//!
//! 持久化在 `User_Data/sts_sources.json`：sources（文件/目录，目录记
//! recursive 开关）+ excludes（规范化路径列表，按路径边界匹配子树）。
//! 「排除优先」——排除了就一直在 excludes 里，重扫或重叠来源不会悄悄
//! 恢复；恢复单文件时若仍落在某个被排除目录下，如实上报 `blocked_by`。
//!
//! 快照给 worker 的是 [(源文件绝对路径, 输出相对路径)]：输出相对路径里
//! 已带来源短名前缀，不同来源的同名文件不会互相覆盖；worker 端不再自己
//! 扫目录，排除项不可能在执行阶段回流。

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashSet;
use std::path::{Path, PathBuf};

use crate::paths;

#[derive(Clone, Serialize, Deserialize)]
pub struct Source {
    pub id: String,
    /// "file" | "dir"
    pub kind: String,
    /// 规范化后的绝对路径（展示用原样，比较用 norm_key）。
    pub path: String,
    /// 仅目录有意义：包含子目录（默认 true，用户可关）。
    #[serde(default = "default_true")]
    pub recursive: bool,
}

fn default_true() -> bool {
    true
}

#[derive(Default, Serialize, Deserialize)]
pub struct SourcesFile {
    #[serde(default)]
    pub sources: Vec<Source>,
    /// 规范化（norm_key 形态）的排除路径；目录条目覆盖整个子树。
    #[serde(default)]
    pub excludes: Vec<String>,
}

fn store_path(root: &Path) -> PathBuf {
    paths::user_data(root).join("sts_sources.json")
}

pub fn load(root: &Path) -> SourcesFile {
    let p = store_path(root);
    if !p.is_file() {
        return SourcesFile::default();
    }
    let text = std::fs::read_to_string(&p).unwrap_or_default();
    serde_json::from_str(&text).unwrap_or_default()
}

fn save(root: &Path, st: &SourcesFile) -> Result<(), String> {
    let p = store_path(root);
    if let Some(d) = p.parent() {
        let _ = std::fs::create_dir_all(d);
    }
    let text = serde_json::to_string_pretty(st).map_err(|e| e.to_string())?;
    crate::config::write_atomic(&p, &text).map_err(|e| e.to_string())
}

/// 路径身份：canonicalize 解析别名/链接写法，去 `\\?\` 前缀，统一分隔符，
/// Windows 文件系统大小写不敏感所以整体小写。比较、去重、排除全用它；
/// 展示永远用 display 路径，不拿小写键当界面文本。
pub fn norm_key(path: &Path) -> String {
    let abs = path.canonicalize().unwrap_or_else(|_| {
        if path.is_absolute() {
            path.to_path_buf()
        } else {
            std::env::current_dir()
                .map(|c| c.join(path))
                .unwrap_or_else(|_| path.to_path_buf())
        }
    });
    let s = abs.to_string_lossy().replace('/', "\\");
    let s = s.strip_prefix("\\\\?\\").map(str::to_string).unwrap_or(s);
    s.trim_end_matches('\\').to_lowercase()
}

/// 展示路径：canonicalize 成功用规范形（同样的文件不同写法只显一份），
/// 失败（文件已消失）原样返回，调用方标 missing。
fn display_path(path: &Path) -> String {
    let canon = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
    let s = canon.to_string_lossy().replace('/', "\\");
    s.strip_prefix("\\\\?\\").map(str::to_string).unwrap_or(s)
}

/// 路径边界匹配：e 是目录前缀时必须带分隔符，`take1` 不会吃掉 `take10`。
fn excluded_by(norm: &str, excludes: &[String]) -> Option<String> {
    excludes
        .iter()
        .find(|e| norm == e.as_str() || norm.starts_with(&format!("{e}\\")))
        .cloned()
}

fn is_excluded_dir(norm: &str, excludes: &[String]) -> bool {
    excludes
        .iter()
        .any(|e| norm == e.as_str() || norm.starts_with(&format!("{e}\\")))
}

/// 来源短名：目录取目录名，文件取文件名去扩展。重名加序号，输出目录用它
/// 组织「来源短名/相对路径」，同名文件跨来源不覆盖。
fn short_name(s: &Source, taken: &mut HashSet<String>) -> String {
    let p = Path::new(&s.path);
    let base = if s.kind == "dir" {
        p.file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_else(|| "source".into())
    } else {
        p.file_stem()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_else(|| "source".into())
    };
    let base = if base.trim().is_empty() {
        "source".to_string()
    } else {
        base
    };
    if taken.insert(base.clone()) {
        return base;
    }
    let mut i = 2;
    loop {
        let cand = format!("{base}_{i}");
        if taken.insert(cand.clone()) {
            return cand;
        }
        i += 1;
    }
}

/// 旧版单路径输入迁移成一个目录来源；不搬文件、不改原配置值。
pub fn migrate_if_empty(root: &Path) {
    let p = store_path(root);
    if p.is_file() {
        return;
    }
    let last = crate::config::read(root)
        .get(crate::sts::LAST_INPUT)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    if last.is_empty() {
        return;
    }
    let src = Source {
        id: new_id(),
        kind: if Path::new(&last).is_file() {
            "file".into()
        } else {
            "dir".into()
        },
        path: last,
        recursive: true,
    };
    let st = SourcesFile {
        sources: vec![src],
        excludes: vec![],
    };
    let _ = save(root, &st);
}

fn new_id() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    format!("s{nanos:x}")
}

/// 添加来源（文件或目录）。同一路径规范化后已存在则返回已有 id。
pub fn add(root: &Path, raw: &str) -> Result<Value, String> {
    let path = Path::new(raw.trim());
    if raw.trim().is_empty() {
        return Err(crate::i18n::t("s.e9c01e81cb").into());
    }
    let kind = if path.is_file() {
        "file"
    } else if path.is_dir() {
        "dir"
    } else {
        return Err(crate::i18n::t("s.stsInputDirMissing").into());
    };
    let mut st = load(root);
    let key = norm_key(path);
    if let Some(s) = st.sources.iter().find(|s| norm_key(Path::new(&s.path)) == key) {
        return Ok(json!({ "id": s.id, "dup": true }));
    }
    let src = Source {
        id: new_id(),
        kind: kind.into(),
        path: display_path(path),
        recursive: true,
    };
    let id = src.id.clone();
    st.sources.push(src);
    save(root, &st)?;
    Ok(json!({ "id": id, "dup": false }))
}

/// 移除来源：其专属排除里「只覆盖该来源子树」的条目一并清掉——排除
/// 记录按规范化路径存，来源都没了还留着只会变成幽灵规则。
pub fn remove(root: &Path, id: &str) -> Result<Value, String> {
    let mut st = load(root);
    let before = st.sources.len();
    let removed: Vec<Source> = st
        .sources
        .iter()
        .filter(|s| s.id == id)
        .cloned()
        .collect();
    st.sources.retain(|s| s.id != id);
    if st.sources.len() == before {
        return Err("来源不存在".into());
    }
    if let Some(src) = removed.first() {
        let base = norm_key(Path::new(&src.path));
        let still = st
            .sources
            .iter()
            .any(|s| norm_key(Path::new(&s.path)) == base);
        if !still {
            st.excludes
                .retain(|e| !(e == &base || e.starts_with(&format!("{base}\\"))));
        }
    }
    save(root, &st)
        .map(|_| json!({ "removed": before - st.sources.len() }))
}

pub fn set_recursive(root: &Path, id: &str, recursive: bool) -> Result<(), String> {
    let mut st = load(root);
    match st.sources.iter_mut().find(|s| s.id == id) {
        Some(s) => {
            s.recursive = recursive;
            save(root, &st)
        }
        None => Err("来源不存在".into()),
    }
}

/// 排除一条路径（文件或目录，目录即整棵子树）。
pub fn exclude(root: &Path, raw: &str) -> Result<(), String> {
    let mut st = load(root);
    let key = norm_key(Path::new(raw.trim()));
    if !key.is_empty() && !st.excludes.iter().any(|e| e == &key) {
        st.excludes.push(key);
        save(root, &st)?;
    }
    Ok(())
}

/// 恢复一条路径。若它仍落在某个被排除的目录下，解除目录排除才算真恢复：
/// 返回 blocked_by 让界面提示，不暗中建反向规则。
pub fn restore(root: &Path, raw: &str) -> Result<Value, String> {
    let mut st = load(root);
    let key = norm_key(Path::new(raw.trim()));
    st.excludes.retain(|e| e != &key);
    let blocked = excluded_by(&key, &st.excludes);
    save(root, &st)?;
    Ok(json!({ "blocked_by": blocked }))
}

pub fn clear(root: &Path) -> Result<(), String> {
    save(root, &SourcesFile::default())
}

/// 文件是否落在某个来源内：file 源必须是自己，dir 源在子树内。
/// 删除/改名只允许动清单内的文件——不能拿面板当通用文件管理器删任意路径。
fn path_in_sources(root: &Path, path: &str) -> bool {
    let st = load(root);
    let key = norm_key(Path::new(path));
    st.sources.iter().any(|s| {
        let sk = norm_key(Path::new(&s.path));
        if s.kind == "file" {
            sk == key
        } else {
            key.starts_with(&format!("{sk}\\"))
        }
    })
}

/// 删除清单里的源文件：优先回收站，确认文案在前端已写明「删除源文件」。
/// file 源被删后来源本身也移除；指向它的排除一并清掉。
pub fn delete_file(root: &Path, path: &str) -> Result<(), String> {
    let file = Path::new(path);
    if !file.is_file() {
        return Err(crate::i18n::t("s.stsInputDirMissing"));
    }
    if !crate::sts::is_audio_path(file) || !path_in_sources(root, path) {
        return Err(crate::i18n::t("s.stsDeleteUnsafe"));
    }
    trash::delete(file).map_err(|e| crate::i18n::te("s.stsDeleteFail", &e))?;
    let mut st = load(root);
    let key = norm_key(file);
    let had_source = st.sources.iter().any(|s| {
        s.kind == "file" && norm_key(Path::new(&s.path)) == key
    });
    if had_source {
        st.sources.retain(|s| !(s.kind == "file" && norm_key(Path::new(&s.path)) == key));
    }
    st.excludes.retain(|e| e != &key);
    save(root, &st)
}

/// 重命名清单内文件。规则与旧单目录版一致；改名后排除记录跟随新路径，
/// file 源路径同步更新，不然再开工具清单里是个幽灵路径。
pub fn rename_file(root: &Path, path: &str, new_name: &str) -> Result<String, String> {
    let file = Path::new(path);
    if !file.is_file() {
        return Err(crate::i18n::t("s.stsInputDirMissing"));
    }
    if !crate::sts::is_audio_path(file) || !path_in_sources(root, path) {
        return Err(crate::i18n::t("s.stsRenameUnsafe"));
    }
    let requested = new_name.trim();
    if requested.is_empty()
        || requested == "."
        || requested == ".."
        || requested.ends_with('.')
        || requested.contains('/')
        || requested.contains('\\')
    {
        return Err(crate::i18n::t("s.stsRenameUnsafe"));
    }
    let mut filename = requested.to_string();
    if Path::new(&filename).extension().is_none() {
        if let Some(ext) = file.extension().and_then(|e| e.to_str()) {
            filename.push('.');
            filename.push_str(ext);
        }
    }
    if !crate::sts::is_audio_path(Path::new(&filename)) {
        return Err(crate::i18n::t("s.stsRenameUnsafe"));
    }
    let Some(parent) = file.parent() else {
        return Err(crate::i18n::t("s.stsRenameUnsafe"));
    };
    let target = parent.join(filename);
    if target == file {
        return Ok(file.to_string_lossy().into_owned());
    }
    if std::fs::symlink_metadata(&target).is_ok() {
        return Err(crate::i18n::t("s.stsRenameExists"));
    }
    std::fs::rename(file, &target).map_err(|e| crate::i18n::te("s.stsRenameFail", &e))?;
    let old_key = norm_key(file);
    let new_key = norm_key(&target);
    let mut st = load(root);
    for e in st.excludes.iter_mut() {
        if *e == old_key {
            *e = new_key.clone();
        }
    }
    for s in st.sources.iter_mut() {
        if s.kind == "file" && norm_key(Path::new(&s.path)) == old_key {
            s.path = display_path(&target);
        }
    }
    save(root, &st)?;
    Ok(target.to_string_lossy().into_owned())
}

struct Item {
    path: PathBuf,
    rel: String,
    source_idx: usize,
    name: String,
    size: u64,
    mtime: u64,
    excluded: bool,
    excluded_by_dir: bool,
}

/// 全量扫描：来源→条目。过期结果不回流由调用方保证（快照只认本次扫描）。
/// 输出目录落在某来源内部时把该子树整体当排除处理并置 output_in_source。
pub fn scan(root: &Path, output: &str) -> Value {
    migrate_if_empty(root);
    let st = load(root);
    let out_key = {
        let t = output.trim();
        if t.is_empty() {
            norm_key(&crate::sts::out_dir(root))
        } else {
            norm_key(Path::new(t))
        }
    };
    let mut items: Vec<Item> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();
    let mut missing: Vec<Value> = Vec::new();
    let mut output_in_source = false;

    for (idx, src) in st.sources.iter().enumerate() {
        let spath = Path::new(&src.path);
        if src.kind == "file" {
            if !spath.is_file() {
                missing.push(json!({"id": src.id, "path": src.path}));
                continue;
            }
            push_file(&st, &out_key, &mut items, &mut seen, idx, spath, spath);
            continue;
        }
        if !spath.is_dir() {
            missing.push(json!({"id": src.id, "path": src.path}));
            continue;
        }
        // 迭代遍历 + 排除剪枝；不跟随链接循环（file_type 的 symlink 不展开）。
        let mut stack = vec![spath.to_path_buf()];
        while let Some(dir) = stack.pop() {
            // 排除的目录不剪枝：里面的文件要逐条列出（标 excluded_by_dir），
            // 「已排除」过滤和恢复入口才看得见它们。只有输出子树真跳过。
            let dkey = norm_key(&dir);
            if dkey != norm_key(spath) && dkey == out_key {
                continue;
            }
            let rd = match std::fs::read_dir(&dir) {
                Ok(r) => r,
                Err(_) => {
                    missing.push(json!({"id": src.id, "path": display_path(&dir)}));
                    continue;
                }
            };
            for ent in rd.flatten() {
                let p = ent.path();
                let ft = match ent.file_type() {
                    Ok(t) => t,
                    Err(_) => continue,
                };
                if ft.is_symlink() {
                    continue;
                }
                if ft.is_dir() {
                    let k = norm_key(&p);
                    if k == out_key {
                        output_in_source = true;
                        continue;
                    }
                    if src.recursive {
                        stack.push(p);
                    }
                    continue;
                }
                if !ft.is_file() || !crate::sts::is_audio_path(&p) {
                    continue;
                }
                push_file(&st, &out_key, &mut items, &mut seen, idx, spath, &p);
            }
        }
    }

    items.sort_by(|a, b| a.path.cmp(&b.path));
    let mut taken: HashSet<String> = HashSet::new();
    let short: Vec<String> = st
        .sources
        .iter()
        .map(|s| short_name(s, &mut taken))
        .collect();
    let multi = st.sources.len() > 1;
    let mut out_items = Vec::with_capacity(items.len());
    let mut pending = 0usize;
    for it in &items {
        if !it.excluded {
            pending += 1;
        }
        out_items.push(json!({
            "path": display_path(&it.path),
            "rel": it.rel,
            "name": it.name,
            "size": it.size,
            "mtime": it.mtime,
            "source_id": st.sources[it.source_idx].id,
            "source_name": short[it.source_idx],
            "source_path": st.sources[it.source_idx].path,
            "excluded": it.excluded,
            "excluded_by_dir": it.excluded_by_dir,
            "out_rel": out_rel(it, &short[it.source_idx], multi),
        }));
    }
    json!({
        "sources": st.sources.iter().enumerate().map(|(i, s)| json!({
            "id": s.id, "kind": s.kind, "path": s.path,
            "recursive": s.recursive, "short": short[i],
        })).collect::<Vec<_>>(),
        "items": out_items,
        "missing": missing,
        "total": items.len(),
        "pending": pending,
        "excluded": items.len() - pending,
        "output_in_source": output_in_source,
    })
}

fn push_file(
    st: &SourcesFile,
    _out_key: &str,
    items: &mut Vec<Item>,
    seen: &mut HashSet<String>,
    idx: usize,
    source_root: &Path,
    file: &Path,
) {
    let key = norm_key(file);
    // 规范化后的真实路径身份去重：重叠目录、不同写法只处理一次。
    if !seen.insert(key.clone()) {
        return;
    }
    let src = &st.sources[idx];
    let rel = if src.kind == "dir" {
        file.strip_prefix(source_root)
            .map(|p| p.to_string_lossy().replace('\\', "/"))
            .unwrap_or_else(|_| {
                file.file_name()
                    .map(|n| n.to_string_lossy().into_owned())
                    .unwrap_or_default()
            })
    } else {
        file.file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default()
    };
    let meta = file.metadata().ok();
    let ex_dir = {
        // 文件自身不在排除表里、但父目录在 → 目录级排除。
        match file.parent() {
            Some(par) => is_excluded_dir(&norm_key(par), &st.excludes)
                && !st.excludes.iter().any(|e| e == &key),
            None => false,
        }
    };
    let excluded = ex_dir || st.excludes.iter().any(|e| e == &key);
    items.push(Item {
        name: file
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_else(|| rel.clone()),
        rel,
        path: file.to_path_buf(),
        source_idx: idx,
        size: meta.as_ref().map(|m| m.len()).unwrap_or(0),
        mtime: meta
            .and_then(|m| m.modified().ok())
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs())
            .unwrap_or(0),
        excluded,
        excluded_by_dir: ex_dir,
    });
}

/// 输出相对路径：多来源加「来源短名/」前缀防同名覆盖；单来源保持原层级。
fn out_rel(it: &Item, short: &str, multi: bool) -> String {
    if multi {
        format!("{short}/{}", it.rel)
    } else {
        it.rel.clone()
    }
}

/// 冻结任务快照：点击开始那一刻的「将处理」清单。返回给 worker 的
/// manifest；预览/总数/进度/重试全用这一份，执行中不再扫目录。
pub fn snapshot(root: &Path, output: &str) -> Value {
    let v = scan(root, output);
    let manifest: Vec<Value> = v
        .get("items")
        .and_then(|a| a.as_array())
        .map(|a| {
            a.iter()
                .filter(|it| !it.get("excluded").and_then(|x| x.as_bool()).unwrap_or(false))
                .map(|it| {
                    json!({
                        "src": it.get("path").and_then(|x| x.as_str()).unwrap_or(""),
                        "rel": it.get("out_rel").and_then(|x| x.as_str()).unwrap_or(""),
                    })
                })
                .collect()
        })
        .unwrap_or_default();
    json!({
        "manifest": manifest,
        "total": manifest.len(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn setup() -> PathBuf {
        let root = crate::testutil::scratch("sts-src");
        fs::create_dir_all(paths::user_data(&root)).unwrap();
        root
    }

    fn audio(p: &Path) {
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(p, b"RIFFfake").unwrap();
    }

    fn add_src(root: &Path, p: &Path) {
        add(root, &p.to_string_lossy()).unwrap();
    }

    #[test]
    fn dedupe_overlap_and_same_name_across_sources() {
        let root = setup();
        let base = root.join("素材 库");
        audio(&base.join("a.wav"));
        audio(&base.join("sub").join("b.wav"));
        // 同名不同文件在两个目录里，都得保留且输出不互相覆盖。
        let other = root.join("take 2");
        audio(&other.join("a.wav"));
        add_src(&root, &base);
        add_src(&root, &base.join("sub")); // 与父目录重叠，b.wav 只出现一次
        add_src(&root, &other);
        let v = scan(&root, "");
        assert_eq!(v["total"].as_u64().unwrap(), 3, "{v}");
        assert_eq!(v["pending"].as_u64().unwrap(), 3);
        // 多来源 → out_rel 带来源短名前缀
        let rels: Vec<&str> = v["items"]
            .as_array()
            .unwrap()
            .iter()
            .map(|i| i["out_rel"].as_str().unwrap())
            .collect();
        assert!(rels.iter().all(|r| r.contains('/')), "{rels:?}");
    }

    #[test]
    fn exclude_boundary_and_snapshot_freeze() {
        let root = setup();
        let d = root.join("in");
        audio(&d.join("take1").join("x.wav"));
        audio(&d.join("take10").join("y.wav"));
        add_src(&root, &d);
        // 排除 take1 目录，take10 不能被误伤（路径边界匹配）。
        exclude(&root, &d.join("take1").to_string_lossy()).unwrap();
        let v = scan(&root, "");
        assert_eq!(v["pending"].as_u64().unwrap(), 1);
        assert_eq!(v["excluded"].as_u64().unwrap(), 1);
        // 快照里只有参与项，排除项绝不回流。
        let snap = snapshot(&root, "");
        let m = snap["manifest"].as_array().unwrap();
        assert_eq!(m.len(), 1);
        assert!(m[0]["src"].as_str().unwrap().contains("take10"));
        // 恢复 take1 下的文件仍被目录排除挡住：blocked_by 如实上报。
        let r = restore(&root, &d.join("take1").join("x.wav").to_string_lossy()).unwrap();
        assert!(r["blocked_by"].as_str().unwrap().contains("take1"));
        let v2 = scan(&root, "");
        assert_eq!(v2["pending"].as_u64().unwrap(), 1);
        // 解除目录排除后全部恢复。
        restore(&root, &d.join("take1").to_string_lossy()).unwrap();
        assert_eq!(scan(&root, "")["pending"].as_u64().unwrap(), 2);
    }

    #[test]
    fn output_inside_source_not_scanned() {
        let root = setup();
        let d = root.join("in");
        audio(&d.join("x.wav"));
        let out = d.join("out");
        audio(&out.join("done.wav")); // 已是成品的文件不能回流成输入
        add_src(&root, &d);
        let v = scan(&root, &out.to_string_lossy());
        assert_eq!(v["output_in_source"].as_bool().unwrap(), true);
        assert_eq!(v["pending"].as_u64().unwrap(), 1);
    }

    #[test]
    fn remove_source_drops_its_excludes_and_recovers_overlap() {
        let root = setup();
        let a = root.join("A");
        audio(&a.join("x.wav"));
        let b = root.join("B");
        audio(&b.join("y.wav"));
        add_src(&root, &a);
        add_src(&root, &b);
        exclude(&root, &a.join("x.wav").to_string_lossy()).unwrap();
        let st = load(&root);
        let id_a = st.sources[0].id.clone();
        remove(&root, &id_a).unwrap();
        let st = load(&root);
        assert_eq!(st.sources.len(), 1);
        assert!(st.excludes.is_empty(), "来源移除后其排除不残留");
    }

    #[test]
    fn recursive_off_lists_top_level_only() {
        let root = setup();
        let d = root.join("d");
        audio(&d.join("top.wav"));
        audio(&d.join("sub").join("deep.wav"));
        add_src(&root, &d);
        let st = load(&root);
        set_recursive(&root, &st.sources[0].id, false).unwrap();
        let v = scan(&root, "");
        assert_eq!(v["total"].as_u64().unwrap(), 1);
    }

    #[test]
    fn missing_source_listed_not_silent() {
        let root = setup();
        let d = root.join("ghost");
        fs::create_dir_all(&d).unwrap();
        audio(&d.join("x.wav"));
        add_src(&root, &d);
        fs::remove_dir_all(&d).unwrap();
        let v = scan(&root, "");
        assert_eq!(v["missing"].as_array().unwrap().len(), 1);
        assert_eq!(v["total"].as_u64().unwrap(), 0);
    }

    #[test]
    fn single_source_keeps_legacy_rel() {
        let root = setup();
        let d = root.join("solo");
        audio(&d.join("sub").join("x.wav"));
        add_src(&root, &d);
        let v = scan(&root, "");
        let it = &v["items"].as_array().unwrap()[0];
        assert_eq!(it["out_rel"].as_str().unwrap(), "sub/x.wav");
    }
}
