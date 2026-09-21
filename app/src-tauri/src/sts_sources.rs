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
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, MutexGuard};

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

/// 清单文件的读写串行锁。save 本身是原子替换，但 load→改→save 三步合起来
/// 不是事务：两个并发 add 各拿旧副本写回，后到者把先到者的来源整个抹掉
/// （验收探针 30/30 复现丢更新）。所有改动状态的入口都要在锁内完成。
static STATE: Mutex<()> = Mutex::new(());

fn lock_state() -> MutexGuard<'static, ()> {
    STATE.lock().unwrap_or_else(|e| e.into_inner())
}

/// 扫描代次。UI 每发一次扫描先取一个 gen；scan_cancel 作废已发的全部。
/// 作废检查只在目录遍历的迭代点做一次无锁原子读——扫描全程不碰 STATE
/// 锁（它只 load 一次），取消延迟 = 一个目录条目的处理时间。
static SCAN_GEN: AtomicU64 = AtomicU64::new(0);
static SCAN_CANCELLED: AtomicU64 = AtomicU64::new(0);

/// 发起一代扫描。命令层（sts_sources_scan）先取 gen 再 spawn_blocking
/// 调 scan_with_gen。
pub fn scan_begin() -> u64 {
    SCAN_GEN.fetch_add(1, Ordering::SeqCst) + 1
}

/// 作废当前所有已发出的扫描代次；之后新发的代次不受影响。
/// fetch_max 保证水位单调：两个线程并发取消时，先到者读到旧 gen 的
/// store 不能盖掉后到者已经抬上去的水位。
pub fn scan_cancel() {
    SCAN_CANCELLED.fetch_max(SCAN_GEN.load(Ordering::SeqCst), Ordering::SeqCst);
}

fn scan_expired(gen: u64) -> bool {
    // gen=0 是不参与取消的内部路径（snapshot 冻结任务清单必须拿全量）。
    gen != 0 && gen <= SCAN_CANCELLED.load(Ordering::SeqCst)
}

/// 转换进行中冻结来源/排除：返回的是**持有着**的 RUN 锁守卫 —— 调用方
/// 必须把它活到整个「读状态→改→写回/文件操作」事务结束。busy 判定与
/// 后续变更在同一把锁内串行：不存在「查完没被占用、run() 随后认领」的
/// TOCTOU 窗口。锁序 RUN → STATE（sts.rs 顶注），扫描/快照不拿 RUN，
/// 无环。
fn ensure_not_running() -> Result<MutexGuard<'static, crate::sts::RunCtl>, String> {
    crate::sts::mutation_guard()
}

pub fn load(root: &Path) -> SourcesFile {
    let p = store_path(root);
    if !p.is_file() {
        return SourcesFile::default();
    }
    let text = std::fs::read_to_string(&p).unwrap_or_default();
    serde_json::from_str(&text).unwrap_or_default()
}

/// 写路径专用读取：JSON 损坏时返回 Err 而不是默认空表。load() 在文件
/// 坏掉时给空表是给只读路径的容忍（scan 显示空清单但不写回）；写路径
/// 若拿空表继续 save，用户现有的 sources/excludes 会被一次操作静默
/// 抹掉。所有「改状态」的入口一律走这里——读不出来就停手，原文件
/// 一个字节不动。
fn load_for_write(root: &Path) -> Result<SourcesFile, String> {
    let p = store_path(root);
    match std::fs::metadata(&p) {
        // 不存在 → 空态（第一次使用）；权限拒绝/IO 错 ≠ 不存在，
        // 当不存在继续走会在 save 时覆盖掉读不出来的那份清单。
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            return Ok(SourcesFile::default());
        }
        Err(e) => return Err(crate::i18n::te("s.stsStateUnreadable", &e)),
        Ok(m) if !m.is_file() => {
            return Err(crate::i18n::t("s.stsStateUnreadable").into());
        }
        Ok(_) => {}
    }
    let text = std::fs::read_to_string(&p)
        .map_err(|e| crate::i18n::te("s.stsStateUnreadable", &e))?;
    serde_json::from_str(&text).map_err(|_| crate::i18n::t("s.stsStateCorrupt").into())
}

fn save(root: &Path, st: &SourcesFile) -> Result<(), String> {
    let p = store_path(root);
    if let Some(d) = p.parent() {
        let _ = std::fs::create_dir_all(d);
    }
    let text = serde_json::to_string_pretty(st).map_err(|e| e.to_string())?;
    crate::config::write_atomic(&p, &text).map_err(|e| e.to_string())
}

/// `\\?\UNC\server\share` 与 `\\server\share` 是同一个 UNC 路径的两种写法：
/// canonicalize 出的规范形带 `\\?\UNC\`，而 share 暂时掉线时只能拿到原始
/// `\\server\share` 拼写。统一折回 `\\` 形态，否则同一份文件在掉线/恢复
/// 前后拿到两个身份，去重和排除记录会当场失效。
fn unverbatim_unc(s: &str) -> String {
    if let Some(rest) = s
        .strip_prefix("UNC\\")
        .or_else(|| s.strip_prefix("unc\\"))
    {
        format!("\\\\{rest}")
    } else {
        s.to_string()
    }
}

/// 路径身份：canonicalize 解析别名/链接写法，去 `\\?\` 前缀并把 UNC 规范形
/// 折回 `\\server\share`，统一分隔符，Windows 文件系统大小写不敏感所以整体
/// 小写。比较、去重、排除全用它；展示永远用 display 路径，不拿小写键当界面
/// 文本。
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
    unverbatim_unc(&s).trim_end_matches('\\').to_lowercase()
}

/// 展示路径：canonicalize 成功用规范形（同样的文件不同写法只显一份），
/// 失败（文件已消失）原样返回，调用方标 missing。UNC 同样折回 `\\` 形态，
/// 不然界面上会显示成无法直接使用的 `UNC\server\share`。
fn display_path(path: &Path) -> String {
    let canon = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
    let s = canon.to_string_lossy().replace('/', "\\");
    let s = s.strip_prefix("\\\\?\\").map(str::to_string).unwrap_or(s);
    unverbatim_unc(&s)
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
    let _g = lock_state();
    // 拿到锁再确认一次：等锁期间别的迁移/写入可能已经把文件建出来了。
    if store_path(root).is_file() {
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

/// 排除/恢复收到的是规范化规则的身份：空串会被 norm_key 折成进程 cwd，
/// 相对路径也一样 —— 存下去就是把整个产品根静默排除掉的幽灵规则
/// （验收探针复现）。这类输入直接拒，不猜用户想干什么。
fn rule_key(raw: &str) -> Result<String, String> {
    let raw = raw.trim();
    let p = Path::new(raw);
    if raw.is_empty() || !p.is_absolute() {
        return Err(crate::i18n::t("s.e9c01e81cb").into());
    }
    Ok(norm_key(p))
}

/// 添加来源（文件或目录）。同一路径规范化后已存在则返回已有 id。
pub fn add(root: &Path, raw: &str) -> Result<Value, String> {
    let _run_guard = ensure_not_running()?;
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
    let _g = lock_state();
    let mut st = load_for_write(root)?;
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
/// 记录按规范化路径存，来源都没了还留着只会变成幽灵规则。但「排除优先」
/// 要一起守住：仍被其它存活来源覆盖的排除必须留下，不然移除一个重叠来源
/// 会把用户明确排除过的文件悄悄放回清单。
pub fn remove(root: &Path, id: &str) -> Result<Value, String> {
    let _run_guard = ensure_not_running()?;
    let _g = lock_state();
    let mut st = load_for_write(root)?;
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
        let remaining: Vec<String> = st
            .sources
            .iter()
            .map(|s| norm_key(Path::new(&s.path)))
            .collect();
        st.excludes.retain(|e| {
            // 仍与任一存活来源的子树相交 → 排除继续生效。相交是双向的：
            // 排除在存活来源之下（文件/子目录规则），或存活来源在排除之下
            // （祖先目录规则仍罩住剩余子源）都成立。
            let live = remaining.iter().any(|k| {
                e == k
                    || e.starts_with(&format!("{k}\\"))
                    || k.starts_with(&format!("{e}\\"))
            });
            if live {
                return true;
            }
            // 只覆盖被删来源子树的排除清掉。
            !(e == &base || e.starts_with(&format!("{base}\\")))
        });
    }
    save(root, &st)
        .map(|_| json!({ "removed": before - st.sources.len() }))
}

pub fn set_recursive(root: &Path, id: &str, recursive: bool) -> Result<(), String> {
    let _run_guard = ensure_not_running()?;
    let _g = lock_state();
    let mut st = load_for_write(root)?;
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
    let _run_guard = ensure_not_running()?;
    let key = rule_key(raw)?;
    let _g = lock_state();
    let mut st = load_for_write(root)?;
    if !st.excludes.iter().any(|e| e == &key) {
        st.excludes.push(key);
        save(root, &st)?;
    }
    Ok(())
}

/// 恢复一条路径。若它仍落在某个被排除的目录下，解除目录排除才算真恢复：
/// 返回 blocked_by 让界面提示，不暗中建反向规则。
pub fn restore(root: &Path, raw: &str) -> Result<Value, String> {
    let _run_guard = ensure_not_running()?;
    let key = rule_key(raw)?;
    let _g = lock_state();
    let mut st = load_for_write(root)?;
    st.excludes.retain(|e| e != &key);
    let blocked = excluded_by(&key, &st.excludes);
    save(root, &st)?;
    Ok(json!({ "blocked_by": blocked }))
}

pub fn clear(root: &Path) -> Result<(), String> {
    let _run_guard = ensure_not_running()?;
    let _g = lock_state();
    save(root, &SourcesFile::default())
}

/// 文件是否落在某个来源内：file 源必须是自己，dir 源在子树内。
/// 删除/改名只允许动清单内的文件——不能拿面板当通用文件管理器删任意路径。
fn path_in_sources(st: &SourcesFile, path: &str) -> bool {
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
/// 运行中禁止：正在转换的文件被删掉只会变成一个说不清的执行失败。
/// 顺序：先严格读清单（读不出来就整体停手），再动磁盘上的文件——不能
/// 报「本次修改未生效」而文件已经被删掉。
pub fn delete_file(root: &Path, path: &str) -> Result<(), String> {
    let _run_guard = ensure_not_running()?;
    let file = Path::new(path);
    if !file.is_file() {
        return Err(crate::i18n::t("s.stsInputDirMissing"));
    }
    let _g = lock_state();
    let mut st = load_for_write(root)?;
    if !crate::sts::is_audio_path(file) || !path_in_sources(&st, path) {
        return Err(crate::i18n::t("s.stsDeleteUnsafe"));
    }
    trash::delete(file).map_err(|e| crate::i18n::te("s.stsDeleteFail", &e))?;
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
    let _run_guard = ensure_not_running()?;
    let file = Path::new(path);
    if !file.is_file() {
        return Err(crate::i18n::t("s.stsInputDirMissing"));
    }
    // 先严格读清单再动文件：清单读不出来时连 rename 都不能做。
    let _g = lock_state();
    let mut st = load_for_write(root)?;
    if !crate::sts::is_audio_path(file) || !path_in_sources(&st, path) {
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
/// 输出目录落在某来源内部时把该子树整体当排除处理并置 output_in_source；
/// 反过来来源落在输出树里（根相等 / file 源在输出树下）置 source_in_output。
/// 内部路径：不参与 UI 取消。
pub fn scan(root: &Path, output: &str) -> Value {
    scan_impl(root, output, 0)
}

/// UI 扫描入口：带代次，作废后在遍历途中提前收工。返回体带
/// `{"cancelled": true}`，调用方按代次/标志丢弃即可。
pub fn scan_with_gen(root: &Path, output: &str, gen: u64) -> Value {
    scan_impl(root, output, gen)
}

fn cancelled_result(gen: u64) -> Value {
    json!({
        "cancelled": true,
        "gen": gen,
        "sources": [],
        "items": [],
        "missing": [],
        "total": 0,
        "pending": 0,
        "excluded": 0,
        "output_in_source": false,
        "source_in_output": false,
    })
}

fn scan_impl(root: &Path, output: &str, gen: u64) -> Value {
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
    let mut source_in_output = false;

    for (idx, src) in st.sources.iter().enumerate() {
        if scan_expired(gen) {
            return cancelled_result(gen);
        }
        let spath = Path::new(&src.path);
        let skey = norm_key(spath);
        if src.kind == "file" {
            if !spath.is_file() {
                missing.push(json!({"id": src.id, "path": src.path, "state": "missing"}));
                continue;
            }
            // 文件源落在输出树里：它是成品不是输入，回流只会再造一份 _rvc。
            if skey == out_key || skey.starts_with(&format!("{out_key}\\")) {
                source_in_output = true;
                continue;
            }
            push_file(&st, &out_key, &mut items, &mut seen, &mut source_in_output, idx, spath, spath);
            continue;
        }
        if !spath.is_dir() {
            missing.push(json!({"id": src.id, "path": src.path, "state": "missing"}));
            continue;
        }
        // 来源根本身就是输出目录：整个来源都是成品，全跳过并提示范围变化。
        if skey == out_key {
            source_in_output = true;
            continue;
        }
        // 迭代遍历 + 排除剪枝；不跟随链接循环（file_type 的 symlink 不展开）。
        let mut stack = vec![spath.to_path_buf()];
        while let Some(dir) = stack.pop() {
            if scan_expired(gen) {
                return cancelled_result(gen);
            }
            // 排除的目录不剪枝：里面的文件要逐条列出（标 excluded_by_dir），
            // 「已排除」过滤和恢复入口才看得见它们。只有输出子树真跳过。
            // 目录不存在与目录读不了分开上报（missing / unreadable），不混成一条。
            let rd = match std::fs::read_dir(&dir) {
                Ok(r) => r,
                Err(_) => {
                    missing.push(json!({
                        "id": src.id,
                        "path": display_path(&dir),
                        "state": "unreadable",
                    }));
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
                push_file(&st, &out_key, &mut items, &mut seen, &mut output_in_source, idx, spath, &p);
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
        "source_in_output": source_in_output,
    })
}

fn push_file(
    st: &SourcesFile,
    out_key: &str,
    items: &mut Vec<Item>,
    seen: &mut HashSet<String>,
    source_in_output: &mut bool,
    idx: usize,
    source_root: &Path,
    file: &Path,
) {
    let key = norm_key(file);
    // 输出树里的文件一律不当输入。目录层已经把输出子树剪掉，这里是 file
    // 源/非常规入口的兜底——之前 `_out_key` 接了不用，成品能被扫回清单。
    if key == out_key || key.starts_with(&format!("{out_key}\\")) {
        *source_in_output = true;
        return;
    }
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
        // 冻结口径的计数：pending 即执行条数，excluded 透传扫描排除数——
        // 前端把它回传给 sts_start 落 run 日志，不用 manifest 长度冒充。
        "pending": v.get("pending").cloned().unwrap_or(json!(manifest.len())),
        "excluded": v.get("excluded").cloned().unwrap_or(json!(0)),
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

    #[test]
    fn remove_keeps_excludes_covered_by_remaining_source() {
        // sources=[in, in\sub]，排除 in\sub\y.wav 后移除子来源：
        // y.wav 仍落在父源 in 之下，排除记录必须留住（F-1）。
        let root = setup();
        let d = root.join("in");
        audio(&d.join("x.wav"));
        let sub = d.join("sub");
        audio(&sub.join("y.wav"));
        add_src(&root, &d);
        add_src(&root, &sub);
        exclude(&root, &sub.join("y.wav").to_string_lossy()).unwrap();
        let st = load(&root);
        let id_sub = st
            .sources
            .iter()
            .find(|s| norm_key(Path::new(&s.path)) == norm_key(&sub))
            .unwrap()
            .id
            .clone();
        remove(&root, &id_sub).unwrap();
        let st = load(&root);
        assert_eq!(st.excludes.len(), 1, "仍被存活来源覆盖的排除不能丢");
        let v = scan(&root, "");
        assert_eq!(v["pending"].as_u64().unwrap(), 1);
        assert_eq!(v["excluded"].as_u64().unwrap(), 1);
    }

    #[test]
    fn remove_keeps_ancestor_exclude_covering_child_source() {
        // 反向关系：sources=[in, in\sub]，排除的是父目录 in，移除来源 in
        // 后 in\sub 仍被这条祖先规则罩住，不能整棵回流。
        let root = setup();
        let d = root.join("in");
        let sub = d.join("sub");
        audio(&sub.join("y.wav"));
        audio(&d.join("x.wav"));
        add_src(&root, &d);
        add_src(&root, &sub);
        exclude(&root, &d.to_string_lossy()).unwrap();
        let st = load(&root);
        let id_in = st
            .sources
            .iter()
            .find(|s| norm_key(Path::new(&s.path)) == norm_key(&d))
            .unwrap()
            .id
            .clone();
        remove(&root, &id_in).unwrap();
        let st = load(&root);
        assert_eq!(st.excludes.len(), 1, "祖先排除规则必须留住");
        let v = scan(&root, "");
        assert_eq!(v["total"].as_u64().unwrap(), 1, "{v}");
        assert_eq!(v["pending"].as_u64().unwrap(), 0, "子源文件仍应被排除");
    }

    #[test]
    fn output_root_equal_to_source_skipped() {
        // 来源根就是输出目录：整棵都是成品，一个都不能回流（F-3）。
        let root = setup();
        let d = root.join("same");
        audio(&d.join("x.wav"));
        audio(&d.join("done_rvc.wav"));
        add_src(&root, &d);
        let v = scan(&root, &d.to_string_lossy());
        assert_eq!(v["total"].as_u64().unwrap(), 0, "{v}");
        assert!(v["source_in_output"].as_bool().unwrap());
    }

    #[test]
    fn file_source_inside_output_not_scanned() {
        // 文件源指到输出树里：它是成品不是输入，且要给界面提示（F-3）。
        let root = setup();
        let d = root.join("in");
        audio(&d.join("x.wav"));
        let out = root.join("out");
        let produced = out.join("a_rvc.wav");
        audio(&produced);
        add_src(&root, &d);
        add_src(&root, &produced);
        let v = scan(&root, &out.to_string_lossy());
        assert!(v["source_in_output"].as_bool().unwrap(), "{v}");
        assert_eq!(v["total"].as_u64().unwrap(), 1);
        let it = &v["items"].as_array().unwrap()[0];
        assert!(it["path"].as_str().unwrap().ends_with("x.wav"), "{it}");
    }

    #[test]
    fn unc_spellings_share_one_identity() {
        // \\server\share 与 \\?\UNC\server\share 是同一网络位置：
        // 身份必须统一，展示路径折回可用的 \\ 形态（G-1）。
        let a = norm_key(Path::new(r"\\server\share\dir\F.wav"));
        let b = norm_key(Path::new(r"\\?\UNC\server\share\dir\f.wav"));
        assert_eq!(a, b);
        assert_eq!(a, r"\\server\share\dir\f.wav");
        let d = display_path(Path::new(r"\\?\UNC\server\share\dir\f.wav"));
        assert_eq!(d, r"\\server\share\dir\f.wav");
    }

    #[test]
    fn blank_and_relative_rules_rejected() {
        // 空串会被 norm_key 折成进程 cwd——存下去就是整棵产品树被静默
        // 排除的幽灵规则；相对路径同理。直接拒（G-2）。
        let root = setup();
        let d = root.join("in");
        audio(&d.join("x.wav"));
        add_src(&root, &d);
        assert!(exclude(&root, "").is_err());
        assert!(exclude(&root, "   ").is_err());
        assert!(exclude(&root, r"rel\x.wav").is_err());
        assert!(restore(&root, "").is_err());
        assert!(load(&root).excludes.is_empty());
        assert_eq!(scan(&root, "")["pending"].as_u64().unwrap(), 1);
    }

    #[test]
    fn case_variant_path_is_same_source() {
        // Windows 文件系统大小写不敏感：同一路径不同写法是一个来源。
        let root = setup();
        let d = root.join("MiXeD");
        audio(&d.join("x.wav"));
        add_src(&root, &d);
        let alt = d.to_string_lossy().to_lowercase();
        let r = add(&root, &alt).unwrap();
        assert!(r["dup"].as_bool().unwrap(), "{r}");
        assert_eq!(load(&root).sources.len(), 1);
    }

    #[test]
    fn exclude_same_path_twice_is_idempotent() {
        let root = setup();
        let d = root.join("in");
        audio(&d.join("x.wav"));
        add_src(&root, &d);
        exclude(&root, &d.join("x.wav").to_string_lossy()).unwrap();
        exclude(&root, &d.join("x.wav").to_string_lossy()).unwrap();
        assert_eq!(load(&root).excludes.len(), 1);
    }

    #[test]
    fn concurrent_adds_do_not_lose_updates() {
        // 以前 add 是无锁 load→改→save，并发必丢更新（探针 30/30）。
        // 现在 STATE 锁串行化持久化事务，全都要落盘（F-4）。
        let root = setup();
        let mut handles = Vec::new();
        for i in 0..8 {
            let r = root.clone();
            handles.push(std::thread::spawn(move || {
                let d = r.join(format!("src{i}"));
                fs::create_dir_all(&d).unwrap();
                add(&r, &d.to_string_lossy()).unwrap();
            }));
        }
        for h in handles {
            h.join().unwrap();
        }
        assert_eq!(load(&root).sources.len(), 8);
    }

    #[test]
    fn scan_during_concurrent_adds_reads_consistent_state() {
        // 扫描与写入并发：读到的可以是旧或新，但绝不能是撕裂状态——
        // 原子替换 + 串行写保证每次 load 都是完整 JSON。
        let root = setup();
        let base = root.join("base");
        for i in 0..4 {
            audio(&base.join(format!("f{i}.wav")));
        }
        add_src(&root, &base);
        let r = root.clone();
        let adder = std::thread::spawn(move || {
            for i in 4..8 {
                let d = r.join(format!("extra{i}"));
                fs::create_dir_all(&d).unwrap();
                audio(&d.join("x.wav"));
                let _ = add(&r, &d.to_string_lossy());
            }
        });
        for _ in 0..4 {
            let v = scan(&root, "");
            assert!(v["total"].as_u64().unwrap() >= 4, "{v}");
        }
        adder.join().unwrap();
        assert_eq!(load(&root).sources.len(), 5);
    }

    #[test]
    fn scan_over_2000_entries_not_truncated() {
        let root = setup();
        let d = root.join("big");
        fs::create_dir_all(&d).unwrap();
        for i in 0..2100 {
            fs::write(d.join(format!("f{i:04}.wav")), b"RIFFfake").unwrap();
        }
        add_src(&root, &d);
        let v = scan(&root, "");
        assert_eq!(v["total"].as_u64().unwrap(), 2100);
        assert_eq!(v["pending"].as_u64().unwrap(), 2100);
        let snap = snapshot(&root, "");
        assert_eq!(snap["manifest"].as_array().unwrap().len(), 2100);
    }

    #[test]
    fn scan_and_snapshot_do_not_mutate_state() {
        // 扫描/快照是只读：持久化文件一个字节都不能动。
        let root = setup();
        let d = root.join("in");
        audio(&d.join("x.wav"));
        add_src(&root, &d);
        exclude(&root, &d.join("x.wav").to_string_lossy()).unwrap();
        let before = fs::read(store_path(&root)).unwrap();
        let _ = scan(&root, "");
        let _ = snapshot(&root, "");
        assert_eq!(before, fs::read(store_path(&root)).unwrap());
    }

    #[test]
    fn scan_cancel_drops_issued_generation_snapshot_immune() {
        // UI 扫描可作废；snapshot 走无代次内部路径，取消打不断——任务
        // 冻结清单必须拿到全量。
        let root = setup();
        let d = root.join("in");
        audio(&d.join("x.wav"));
        add_src(&root, &d);
        let gen = scan_begin();
        assert!(gen > 0);
        scan_cancel();
        let v = scan_with_gen(&root, "", gen);
        assert_eq!(v["cancelled"].as_bool().unwrap(), true);
        // 作废后再发的新一代不受影响。
        let gen2 = scan_begin();
        let v2 = scan_with_gen(&root, "", gen2);
        assert_eq!(v2["total"].as_u64().unwrap(), 1, "{v2}");
        // snapshot 不受 UI 取消影响。
        scan_cancel();
        let snap = snapshot(&root, "");
        assert_eq!(snap["total"].as_u64().unwrap(), 1);
    }

    #[test]
    fn malformed_state_file_blocks_writes_preserves_file() {
        // 持久化 JSON 损坏：写路径必须报错停手（拿默认空表继续 save 会把
        // 用户现有 sources/excludes 静默抹掉）；原文件一字节不动。
        // 只读路径仍容忍：scan 返回空清单而不是报错。
        let root = setup();
        let p = store_path(&root);
        fs::write(&p, b"{\"sources\": [truncated").unwrap();
        let before = fs::read(&p).unwrap();
        let d = root.join("in");
        audio(&d.join("x.wav"));
        assert!(add(&root, &d.to_string_lossy()).is_err());
        assert!(exclude(&root, &d.join("x.wav").to_string_lossy()).is_err());
        assert_eq!(before, fs::read(&p).unwrap(), "原文件不能被覆盖");
        let v = scan(&root, "");
        assert_eq!(v["total"].as_u64().unwrap(), 0);
    }

    #[test]
    fn unreadable_state_blocks_delete_before_touching_file() {
        // 状态坏掉时 delete/rename 必须先在严格读取处停手——源文件本身
        // 一个字节都不能动，而不是先删文件再发现状态写不回去。
        let root = setup();
        let d = root.join("in");
        let f = d.join("keep.wav");
        audio(&f);
        add(&root, &d.to_string_lossy()).unwrap();
        // 把状态文件改坏，再请删文件：必须报错且文件还在。
        fs::write(store_path(&root), b"garbage{").unwrap();
        let before = fs::read(&f).unwrap();
        assert!(delete_file(&root, &f.to_string_lossy()).is_err());
        assert!(rename_file(&root, &f.to_string_lossy(), "new.wav").is_err());
        assert_eq!(before, fs::read(&f).unwrap(), "源文件不能被碰");
        // 状态路径是个目录（不是文件）也按 unreadable 拒，不能当空态。
        fs::remove_file(store_path(&root)).unwrap();
        fs::create_dir(store_path(&root)).unwrap();
        assert!(add(&root, &d.to_string_lossy()).is_err());
    }
}
