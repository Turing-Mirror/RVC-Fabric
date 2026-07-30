//! Path-safe Runtime tar extract (mirrors launcher.runtime_provision._extract_tar).

use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

use flate2::read::GzDecoder;
use tar::Archive;

fn is_safe_member(name: &str, dest_root: &Path) -> Result<bool, String> {
    let name = name.replace('\\', "/").trim_start_matches('/').to_string();
    if name.is_empty() || name.starts_with("../") || name.contains("/../") {
        return Err(format!("tar 含非法路径：{name}"));
    }
    if name.starts_with('/') || (name.len() > 1 && name.as_bytes().get(1) == Some(&b':')) {
        return Err(format!("tar 含绝对路径：{name}"));
    }
    let target = dest_root.join(&name);
    let dest_c = dest_root
        .canonicalize()
        .unwrap_or_else(|_| dest_root.to_path_buf());
    // Parent may not exist yet — check prefix logically
    let mut cur = PathBuf::new();
    for c in Path::new(&name).components() {
        use std::path::Component;
        match c {
            Component::ParentDir => return Err(format!("tar 路径越界：{name}")),
            Component::Normal(s) => cur.push(s),
            Component::CurDir => {}
            _ => return Err(format!("tar 路径非法：{name}")),
        }
    }
    let _ = target;
    let _ = dest_c;

    let top = name.split('/').next().unwrap_or("").to_ascii_lowercase();
    let lower = name.to_ascii_lowercase();
    if top == "runtime" || lower.starts_with("runtime/") || top == "." {
        return Ok(true);
    }
    // Allow single wrapper folder; skip junk outside Runtime tree
    if !name.contains('/') {
        return Ok(true); // top-level dir/file
    }
    if lower.split('/').any(|p| p == "runtime") {
        return Ok(true);
    }
    Ok(false) // skip
}

fn open_archive(path: &Path) -> Result<Archive<Box<dyn Read + Send>>, String> {
    let f = fs::File::open(path).map_err(|e| format!("打开 tar 失败: {e}"))?;
    let name = path
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if name.ends_with(".tar.gz") || name.ends_with(".tgz") {
        let dec = GzDecoder::new(f);
        Ok(Archive::new(Box::new(dec) as Box<dyn Read + Send>))
    } else {
        Ok(Archive::new(Box::new(f) as Box<dyn Read + Send>))
    }
}

fn find_python_exe(dir: &Path) -> Option<PathBuf> {
    fn walk(d: &Path, depth: u32) -> Option<PathBuf> {
        if depth > 6 {
            return None;
        }
        let rd = fs::read_dir(d).ok()?;
        for ent in rd.flatten() {
            let p = ent.path();
            if p.is_file() {
                if p.file_name().and_then(|s| s.to_str()) == Some("python.exe") {
                    return Some(p);
                }
            } else if p.is_dir() {
                if let Some(f) = walk(&p, depth + 1) {
                    return Some(f);
                }
            }
        }
        None
    }
    walk(dir, 0)
}

/// Extract so that *dest_root*/Runtime/python.exe exists.
pub fn extract_runtime_tar(archive: &Path, dest_root: &Path) -> Result<(), String> {
    dest_root
        .canonicalize()
        .or_else(|_| {
            fs::create_dir_all(dest_root).ok();
            dest_root.canonicalize()
        })
        .map_err(|e| e.to_string())?;

    let rt = dest_root.join("Runtime");
    if rt.exists() {
        let _ = fs::remove_dir_all(&rt);
    }

    let staging = dest_root
        .join("User_Data")
        .join("update_cache")
        .join("runtime_extract");
    if staging.exists() {
        let _ = fs::remove_dir_all(&staging);
    }
    fs::create_dir_all(&staging).map_err(|e| e.to_string())?;

    let mut archive = open_archive(archive)?;
    let entries = archive
        .entries()
        .map_err(|e| format!("读取 tar 失败: {e}"))?;

    for entry in entries {
        let mut entry = entry.map_err(|e| format!("tar 条目错误: {e}"))?;
        let path = entry
            .path()
            .map_err(|e| e.to_string())?
            .to_string_lossy()
            .to_string();
        match is_safe_member(&path, &staging)? {
            true => {
                entry
                    .unpack_in(&staging)
                    .map_err(|e| format!("解压失败 {path}: {e}"))?;
            }
            false => continue,
        }
    }

    let mut candidate = staging.join("Runtime");
    if !(candidate.join("python.exe")).is_file() {
        if let Some(py) = find_python_exe(&staging) {
            if let Some(parent) = py.parent().map(|p| p.to_path_buf()) {
                if parent
                    .file_name()
                    .and_then(|s| s.to_str())
                    .map(|s| s.eq_ignore_ascii_case("runtime"))
                    .unwrap_or(false)
                    || parent.join("Lib").join("site-packages").is_dir()
                {
                    candidate = parent;
                }
            }
        }
    }
    if !(candidate.join("python.exe")).is_file() {
        let _ = fs::remove_dir_all(&staging);
        return Err("解压后未找到 Runtime\\python.exe。请检查 tar 是否完整或重试。".into());
    }

    let final_rt = dest_root.join("Runtime");
    if final_rt.exists() {
        let _ = fs::remove_dir_all(&final_rt);
    }
    fs::rename(&candidate, &final_rt).map_err(|e| {
        let _ = fs::remove_dir_all(&staging);
        format!("移动 Runtime 失败: {e}")
    })?;
    let _ = fs::remove_dir_all(&staging);

    if !(final_rt.join("python.exe")).is_file() {
        return Err("解压后未找到 Runtime\\python.exe。".into());
    }
    Ok(())
}

/// Extract a zip into `dest_root`, reusing the same traversal guard as the tar
/// path (equivalent of the Python shell's `safe_zip`).
pub fn extract_zip(archive: &Path, dest_root: &Path) -> Result<(), String> {
    let file = std::fs::File::open(archive).map_err(|e| format!("打开压缩包失败：{e}"))?;
    let mut zip = zip::ZipArchive::new(file).map_err(|e| format!("读取压缩包失败：{e}"))?;
    std::fs::create_dir_all(dest_root).map_err(|e| e.to_string())?;

    for i in 0..zip.len() {
        let mut entry = zip.by_index(i).map_err(|e| e.to_string())?;
        let name = entry.name().replace('\\', "/");
        if !is_safe_member(&name, dest_root)? {
            return Err(format!("压缩包含有不安全路径：{name}"));
        }
        let out = dest_root.join(&name);
        if entry.is_dir() || name.ends_with('/') {
            std::fs::create_dir_all(&out).map_err(|e| e.to_string())?;
            continue;
        }
        if let Some(parent) = out.parent() {
            std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        let mut dst = std::fs::File::create(&out)
            .map_err(|e| format!("写入 {} 失败：{e}", out.display()))?;
        std::io::copy(&mut entry, &mut dst).map_err(|e| e.to_string())?;
    }
    Ok(())
}
