//! 换安装位置：把旧安装目录里的用户数据和已下载组件搬到新目录，
//! 并把设置里指向旧目录的路径改成新目录。
//!
//! 由安装程序（`installer-hooks.nsh`）在写入新文件之前调用：
//!
//! ```text
//! rvc-fabric.exe --move-install <旧目录> <新目录> <报告文件>
//! ```
//!
//! 退出码 0 表示搬完（或没有可搬的）；2 表示两个其实是同一个目录，不用搬；
//! 1 表示没搬，原因写进报告文件
//! （UTF-16LE 带 BOM，安装程序读出来弹窗）。没搬成时旧目录原样不动，
//! 新目录里已经搬过去的部分全部撤回。

use serde_json::Value;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

/// 随用户走的东西：用户数据，以及首次运行后下载、安装包里没有的组件。
/// 卸载时选「保留用户数据」，这些都留下（见 `installer-hooks.nsh`）。
pub const CARRIED: &[&str] = &[
    "User_Data",
    "UserData",
    "Runtime",
    "package_meta.json",
    "ffmpeg.exe",
    "ffprobe.exe",
    "assets/hubert/hubert_base.pt",
    "assets/rmvpe/rmvpe.pt",
    "assets/rmvpe/rmvpe.onnx",
    "assets/pretrained_v2",
    "assets/pretrained",
    "assets/uvr5_weights",
    "assets/pymss",
    "assets/weights",
];

/// 改路径时不进的目录：运行环境和缓存里没有设置，文件又多。
const SKIP_DIRS: &[&str] = &["runtimes", "downloads", "update_cache", "cover_cache", "logs"];

/// 跨盘复制时，在所需空间之外再留的余量。
const SPACE_MARGIN: u64 = 512 * 1024 * 1024;

/// 退出码：原位置和新位置是同一个目录。
pub const SAME_PLACE: i32 = 2;

/// `--move-install` 入口。不是这个命令时返回 None，照常启动软件。
pub fn from_args() -> Option<i32> {
    let args: Vec<String> = std::env::args().collect();
    let at = args.iter().position(|a| a == "--move-install")?;
    let (Some(old), Some(new), Some(report)) = (args.get(at + 1), args.get(at + 2), args.get(at + 3))
    else {
        return Some(1);
    };
    // 只是写法不同（大小写、末尾斜杠）的同一个目录：没有要搬的，安装程序照常覆盖安装。
    if clean(Path::new(old)).eq_ignore_ascii_case(&clean(Path::new(new))) {
        return Some(SAME_PLACE);
    }
    Some(match move_install(Path::new(old), Path::new(new)) {
        Ok(()) => 0,
        Err(msg) => {
            write_report(Path::new(report), &msg);
            1
        }
    })
}

fn write_report(path: &Path, msg: &str) {
    let mut bytes = vec![0xFF, 0xFE];
    for u in msg.encode_utf16() {
        bytes.extend_from_slice(&u.to_le_bytes());
    }
    let _ = fs::write(path, bytes);
}

fn gb(bytes: u64) -> String {
    format!("{:.1}", bytes as f64 / 1024.0 / 1024.0 / 1024.0)
}

/// 去掉 `\\?\`、统一成反斜杠、去掉末尾分隔符，比较时再忽略大小写。
fn clean(p: &Path) -> String {
    let s = p.to_string_lossy().replace('/', "\\");
    let s = s.strip_prefix(r"\\?\").unwrap_or(&s);
    s.trim_end_matches('\\').to_string()
}

fn same_or_inside(a: &str, b: &str) -> bool {
    let (a, b) = (a.to_lowercase(), b.to_lowercase());
    a == b || a.starts_with(&format!("{b}\\"))
}

/// 空目录当作不存在：安装程序可能已经建好了新目录。
fn occupied(p: &Path) -> bool {
    if p.is_dir() {
        fs::read_dir(p).map(|mut d| d.next().is_some()).unwrap_or(true)
    } else {
        p.exists()
    }
}

fn tree_size(p: &Path) -> io::Result<(u64, u64)> {
    if p.is_file() {
        return Ok((1, fs::metadata(p)?.len()));
    }
    let (mut n, mut bytes) = (0, 0);
    for e in fs::read_dir(p)? {
        let (dn, db) = tree_size(&e?.path())?;
        n += dn;
        bytes += db;
    }
    Ok((n, bytes))
}

fn copy_tree(from: &Path, to: &Path) -> io::Result<()> {
    if from.is_file() {
        if let Some(d) = to.parent() {
            fs::create_dir_all(d)?;
        }
        fs::copy(from, to)?;
        return Ok(());
    }
    fs::create_dir_all(to)?;
    for e in fs::read_dir(from)? {
        let e = e?;
        copy_tree(&e.path(), &to.join(e.file_name()))?;
    }
    Ok(())
}

fn remove_tree(p: &Path) -> io::Result<()> {
    if p.is_dir() {
        fs::remove_dir_all(p)
    } else {
        fs::remove_file(p)
    }
}

/// 已经搬过去、出错时要撤回的一项。
struct Moved {
    from: PathBuf,
    to: PathBuf,
    renamed: bool,
}

fn undo(done: &[Moved]) {
    for m in done.iter().rev() {
        if m.renamed {
            let _ = fs::rename(&m.to, &m.from);
        } else {
            let _ = remove_tree(&m.to);
        }
    }
}

pub fn move_install(old: &Path, new: &Path) -> Result<(), String> {
    let old_s = clean(old);
    let new_s = clean(new);
    if same_or_inside(&new_s, &old_s) || same_or_inside(&old_s, &new_s) {
        return Err(format!(
            "新位置 {new_s} 和原位置 {old_s} 重叠，请选择另一个目录。"
        ));
    }
    let items: Vec<&str> = CARRIED.iter().copied().filter(|i| old.join(i).exists()).collect();
    if items.is_empty() {
        return Ok(());
    }
    if let Some(i) = items.iter().find(|i| occupied(&new.join(i))) {
        return Err(format!(
            "新位置已经有 {}。请选择一个空目录，或先处理新位置里的这些文件。",
            new.join(i).display()
        ));
    }
    let same_volume = crate::disk_kind::volume_of(old)
        .zip(crate::disk_kind::volume_of(new))
        .is_some_and(|(a, b)| a.eq_ignore_ascii_case(&b));
    move_items(old, new, &items, same_volume)
}

/// 同一个盘直接改名；跨盘先复制、核对，全部成功后才删旧的。
fn move_items(old: &Path, new: &Path, items: &[&str], same_volume: bool) -> Result<(), String> {
    let old_s = clean(old);
    let new_s = clean(new);
    let mut sizes = Vec::new();
    if !same_volume {
        for i in items {
            sizes.push(
                tree_size(&old.join(i))
                    .map_err(|e| format!("读取 {} 失败：{e}", old.join(i).display()))?,
            );
        }
        let need: u64 = sizes.iter().map(|s| s.1).sum::<u64>() + SPACE_MARGIN;
        let probe = new.ancestors().find(|a| a.exists()).unwrap_or(new);
        if let Some(free) = crate::paths::free_space_bytes(probe) {
            if free < need {
                return Err(format!(
                    "新位置空间不足：需要 {} GB，剩余 {} GB。",
                    gb(need),
                    gb(free)
                ));
            }
        }
    }

    fs::create_dir_all(new).map_err(|e| format!("无法创建 {new_s}：{e}"))?;
    let mut done: Vec<Moved> = Vec::new();
    for (k, i) in items.iter().enumerate() {
        let from = old.join(i);
        let to = new.join(i);
        let step = if same_volume {
            // 安装程序可能已经建了空目录，改名不能落在已有目录上。
            if to.is_dir() {
                let _ = fs::remove_dir(&to);
            }
            to.parent()
                .map(fs::create_dir_all)
                .transpose()
                .and_then(|_| fs::rename(&from, &to))
                .map(|_| true)
        } else {
            copy_tree(&from, &to).and_then(|_| {
                if tree_size(&to)? == sizes[k] {
                    Ok(false)
                } else {
                    Err(io::Error::other("复制后的文件数或大小与原文件不一致"))
                }
            })
        };
        match step {
            Ok(renamed) => done.push(Moved { from, to, renamed }),
            Err(e) => {
                // 没走完的这一项也可能留了半截。
                if !same_volume {
                    let _ = remove_tree(&to);
                }
                undo(&done);
                return Err(format!("搬移 {} 失败：{e}。原位置未改动。", from.display()));
            }
        }
    }

    let user_data = new.join("User_Data");
    if user_data.is_dir() {
        if let Err(e) = rewrite_tree(&user_data, &old_s, &new_s) {
            undo(&done);
            return Err(format!("更新设置里的路径失败：{e}。原位置未改动。"));
        }
    }

    // 新位置已经齐了。旧位置删不干净不影响使用，不算失败。
    for m in &done {
        if !m.renamed {
            let _ = remove_tree(&m.from);
        }
    }
    Ok(())
}

/// 把 JSON 文件里指向旧目录的路径改成新目录。
fn rewrite_tree(dir: &Path, old: &str, new: &str) -> io::Result<()> {
    for e in fs::read_dir(dir)? {
        let p = e?.path();
        if p.is_dir() {
            let name = p.file_name().map(|n| n.to_string_lossy().to_lowercase());
            if !name.is_some_and(|n| SKIP_DIRS.contains(&n.as_str())) {
                rewrite_tree(&p, old, new)?;
            }
        } else if p
            .extension()
            .is_some_and(|x| x.eq_ignore_ascii_case("json"))
        {
            rewrite_file(&p, old, new)?;
        }
    }
    Ok(())
}

fn rewrite_file(p: &Path, old: &str, new: &str) -> io::Result<()> {
    let Ok(text) = fs::read_to_string(p) else {
        return Ok(());
    };
    // 用记事本之类改过的文件开头可能带 BOM。
    let Ok(mut v) = serde_json::from_str::<Value>(text.trim_start_matches('\u{feff}')) else {
        return Ok(());
    };
    if !rewrite_value(&mut v, old, new) {
        return Ok(());
    }
    let out = serde_json::to_string_pretty(&v).map_err(io::Error::other)?;
    crate::config::write_atomic(p, &out)
}

fn rewrite_value(v: &mut Value, old: &str, new: &str) -> bool {
    match v {
        Value::String(s) => match moved_path(s, old, new) {
            Some(n) => {
                *s = n;
                true
            }
            None => false,
        },
        Value::Array(a) => a
            .iter_mut()
            .fold(false, |c, x| rewrite_value(x, old, new) | c),
        Value::Object(m) => {
            let mut changed = false;
            let keys: Vec<String> = m.keys().cloned().collect();
            for k in keys {
                let mut val = m.remove(&k).unwrap_or(Value::Null);
                changed |= rewrite_value(&mut val, old, new);
                let key = match moved_path(&k, old, new) {
                    Some(n) => {
                        changed = true;
                        n
                    }
                    None => k,
                };
                m.insert(key, val);
            }
            changed
        }
        _ => false,
    }
}

/// `s` 是旧目录或旧目录下面的路径时，换成新目录下的同一路径。
/// 斜杠方向和大小写不同也算；`E:\RVC Fabric2` 不算 `E:\RVC Fabric` 下面。
fn moved_path(s: &str, old: &str, new: &str) -> Option<String> {
    // 有些记录带 Windows 长路径前缀 `\\?\`，保留它，只换后面的目录。
    if let Some(rest) = s.strip_prefix(r"\\?\") {
        return moved_path(rest, old, new).map(|p| format!(r"\\?\{p}"));
    }
    let n = old.len();
    if s.len() < n || !s.is_char_boundary(n) {
        return None;
    }
    let norm = |x: &str| x.replace('/', "\\").to_lowercase();
    if norm(&s[..n]) != norm(old) {
        return None;
    }
    let rest = &s[n..];
    if !(rest.is_empty() || rest.starts_with('\\') || rest.starts_with('/')) {
        return None;
    }
    Some(format!("{new}{rest}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp(name: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!(
            "tm_install_move_{name}_{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&d);
        fs::create_dir_all(&d).unwrap();
        d
    }

    fn put(p: &Path, text: &str) {
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(p, text).unwrap();
    }

    #[test]
    fn a_path_under_the_old_folder_moves_with_it() {
        let (o, n) = (r"E:\RVC Fabric", r"F:\RVCFabric");
        assert_eq!(
            moved_path(r"e:\rvc fabric\User_Data\a.pth", o, n).as_deref(),
            Some(r"F:\RVCFabric\User_Data\a.pth")
        );
        assert_eq!(moved_path("E:/RVC Fabric/x", o, n).as_deref(), Some("F:\\RVCFabric/x"));
        assert_eq!(moved_path(o, o, n).as_deref(), Some(n));
        assert_eq!(
            moved_path(r"\\?\E:\RVC Fabric\User_Data\k.index", o, n).as_deref(),
            Some(r"\\?\F:\RVCFabric\User_Data\k.index")
        );
        assert_eq!(moved_path(r"E:\RVC Fabric2\x", o, n), None);
        assert_eq!(moved_path(r"E:\Record\out", o, n), None);
        assert_eq!(moved_path("RVC Fabric", o, n), None);
    }

    #[test]
    fn moving_carries_data_and_rewrites_settings() {
        let base = tmp("ok");
        let (old, new) = (base.join("old"), base.join("new"));
        let o = clean(&old);
        put(
            &old.join("User_Data").join("app_config.json"),
            &format!(
                r#"{{"pth_path": {}, "last_sts_output": "D:\\out"}}"#,
                serde_json::to_string(&format!(r"{o}\User_Data\models\a.pth")).unwrap()
            ),
        );
        put(&old.join("User_Data").join("runtimes").join("x.json"), &format!("{:?}", o));
        put(&old.join("assets").join("rmvpe").join("rmvpe.pt"), "w");
        put(&old.join("ffmpeg.exe"), "f");
        put(&old.join("rvc-fabric.exe"), "program");
        put(
            &old.join("User_Data").join("bom.json"),
            &format!("\u{feff}{{\"p\": {}}}", serde_json::to_string(&o).unwrap()),
        );
        fs::create_dir_all(&new).unwrap();

        move_install(&old, &new).unwrap();

        let cfg: Value = serde_json::from_str(
            &fs::read_to_string(new.join("User_Data").join("app_config.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(
            cfg["pth_path"].as_str().unwrap(),
            format!(r"{}\User_Data\models\a.pth", clean(&new))
        );
        assert_eq!(cfg["last_sts_output"], r"D:\out");
        let bom = fs::read_to_string(new.join("User_Data").join("bom.json")).unwrap();
        assert!(bom.contains(&serde_json::to_string(&clean(&new)).unwrap()), "{bom}");
        assert!(new.join("assets").join("rmvpe").join("rmvpe.pt").is_file());
        assert!(new.join("ffmpeg.exe").is_file());
        assert!(!old.join("User_Data").exists());
        // 程序文件留给旧的卸载程序删。
        assert!(old.join("rvc-fabric.exe").is_file());
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn copying_to_another_drive_carries_data_and_cleans_up() {
        let base = tmp("copy");
        let (old, new) = (base.join("old"), base.join("new"));
        put(&old.join("User_Data").join("models").join("a").join("config.json"), "{}");
        put(&old.join("ffmpeg.exe"), "f");
        move_items(&old, &new, &["User_Data", "ffmpeg.exe"], false).unwrap();
        assert!(new.join("User_Data").join("models").join("a").join("config.json").is_file());
        assert!(new.join("ffmpeg.exe").is_file());
        assert!(!old.join("User_Data").exists() && !old.join("ffmpeg.exe").exists());
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn a_failed_item_rolls_back_the_ones_already_copied() {
        let base = tmp("undo");
        let (old, new) = (base.join("old"), base.join("new"));
        put(&old.join("User_Data").join("a.json"), "{}");
        // 第二项不存在，复制必然失败。
        assert!(move_items(&old, &new, &["User_Data", "ffmpeg.exe"], false).is_err());
        assert!(old.join("User_Data").join("a.json").is_file());
        assert!(!new.join("User_Data").exists());
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn an_occupied_target_is_refused_and_nothing_moves() {
        let base = tmp("busy");
        let (old, new) = (base.join("old"), base.join("new"));
        put(&old.join("User_Data").join("a.json"), "{}");
        put(&new.join("User_Data").join("b.json"), "{}");
        assert!(move_install(&old, &new).is_err());
        assert!(old.join("User_Data").join("a.json").is_file());
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn overlapping_folders_are_refused() {
        let base = tmp("overlap");
        put(&base.join("User_Data").join("a.json"), "{}");
        assert!(move_install(&base, &base.join("sub")).is_err());
        assert!(move_install(&base.join("sub"), &base).is_err());
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn the_uninstaller_keeps_everything_that_is_carried() {
        // 卸载时选「保留用户数据」要留下的，正是搬家要带走的这些。
        let nsh = include_str!("../installer-hooks.nsh");
        let keep = nsh
            .split("KEEP_LIST_BEGIN")
            .nth(1)
            .and_then(|s| s.split("KEEP_LIST_END").next())
            .expect("installer-hooks.nsh 缺少 KEEP_LIST 标记");
        for i in CARRIED {
            let win = i.replace('/', "\\");
            assert!(
                keep.contains(&format!("$INSTDIR\\{win}\"")),
                "卸载程序没有按 CARRIED 处理 {i}"
            );
        }
    }
}
