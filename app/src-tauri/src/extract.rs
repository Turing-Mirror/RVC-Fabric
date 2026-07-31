//! Path-safe Runtime tar extract (mirrors launcher.runtime_provision._extract_tar).

use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use flate2::read::GzDecoder;
use tar::Archive;

/// Counts bytes pulled off the archive so the caller can show progress.
///
/// The Runtime tar is several GB and the gate used to sit on a single
/// 「解压 Runtime…」 line for minutes with a bar that never moved — from the
/// user's side indistinguishable from a hang. Counting the *archive* bytes is
/// the right measure: it is exact for a plain tar and still monotonic for a
/// gzip one, where it tracks how far into the file we have read.
struct CountingReader<R> {
    inner: R,
    read: Arc<AtomicU64>,
}

impl<R: Read> Read for CountingReader<R> {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        let n = self.inner.read(buf)?;
        self.read.fetch_add(n as u64, Ordering::Relaxed);
        Ok(n)
    }
}

/// Reject a member whose path would land outside `dest_root`.
///
/// Traversal safety only — it says nothing about whether the entry is *wanted*.
/// Those two questions used to be one function, and the answer for "not wanted"
/// (`Ok(false)`) was read by `extract_zip` as "unsafe", so every zip whose paths
/// did not mention `runtime/` was refused outright. That broke the engine-core
/// pack, the VB-Cable pack and every UI patch — three unrelated features, one
/// overloaded return value.
fn check_path_safety(name: &str) -> Result<(), String> {
    let name = name.replace('\\', "/");
    let name = name.trim_start_matches('/');
    if name.is_empty() {
        return Err("压缩包含空路径".into());
    }
    if name.len() > 1 && name.as_bytes().get(1) == Some(&b':') {
        return Err(format!("含盘符路径：{name}"));
    }
    for c in Path::new(name).components() {
        use std::path::Component;
        match c {
            Component::Normal(_) | Component::CurDir => {}
            Component::ParentDir => return Err(format!("路径越界：{name}")),
            _ => return Err(format!("路径非法：{name}")),
        }
    }
    Ok(())
}

/// Is this tar member part of the Runtime tree we actually want?
///
/// The Runtime tarballs carry build scratch alongside `Runtime/`; anything
/// outside it is skipped rather than treated as an error.
fn is_runtime_member(name: &str) -> bool {
    let name = name.replace('\\', "/");
    let name = name.trim_start_matches('/');
    let lower = name.to_ascii_lowercase();
    let top = lower.split('/').next().unwrap_or("");
    if top == "runtime" || top == "." {
        return true;
    }
    // A single wrapper folder, or a loose top-level file, may hold the tree.
    if !name.contains('/') {
        return true;
    }
    lower.split('/').any(|p| p == "runtime")
}

fn open_archive(
    path: &Path,
    counter: Arc<AtomicU64>,
) -> Result<Archive<Box<dyn Read + Send>>, String> {
    let f = fs::File::open(path).map_err(|e| format!("打开 tar 失败: {e}"))?;
    let f = CountingReader {
        inner: f,
        read: counter,
    };
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

/// Extract so that *dest_root*/Runtime/python.exe exists, calling
/// `on_progress(done_bytes, total_bytes)` as it goes.
///
/// Throttled to ~5 Hz: a multi-GB tar reads in 8 KB chunks, and an unthrottled
/// callback would emit hundreds of thousands of IPC events.
pub fn extract_runtime_tar_with_progress(
    archive: &Path,
    dest_root: &Path,
    on_progress: &dyn Fn(u64, u64),
) -> Result<(), String> {
    let total = fs::metadata(archive).map(|m| m.len()).unwrap_or(0);
    let counter = Arc::new(AtomicU64::new(0));
    let mut last_emit = std::time::Instant::now();
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

    let mut archive = open_archive(archive, counter.clone())?;
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
        check_path_safety(&path).map_err(|e| format!("tar {e}"))?;
        if !is_runtime_member(&path) {
            continue;
        }
        entry
            .unpack_in(&staging)
            .map_err(|e| format!("解压失败 {path}: {e}"))?;
        if last_emit.elapsed() >= std::time::Duration::from_millis(200) {
            last_emit = std::time::Instant::now();
            on_progress(counter.load(Ordering::Relaxed).min(total), total);
        }
    }
    on_progress(total, total);

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
        check_path_safety(&name).map_err(|e| format!("压缩包{e}"))?;
        // Second, independent check: the zip crate refuses anything it cannot
        // prove stays inside the destination.
        let rel = entry
            .enclosed_name()
            .ok_or_else(|| format!("压缩包路径不安全：{name}"))?;
        let out = dest_root.join(&rel);
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[test]
    fn traversal_and_absolute_are_refused() {
        for bad in [
            "../etc/passwd",
            "a/../../b",
            "C:/windows/system32/x.dll",
            "",
        ] {
            assert!(check_path_safety(bad).is_err(), "should refuse {bad:?}");
        }
    }

    #[test]
    fn ordinary_nested_paths_are_allowed() {
        // The regression: these are exactly the shapes a gui_patch, the
        // engine-core pack and the VB-Cable pack are made of, and the old
        // combined check reported every one of them as "unsafe".
        for ok in [
            "index.html",
            "assets/index-Bs5dQX0_.js",
            "assets/rmvpe/rmvpe.pt",
            "VBCABLE/VBCABLE_Setup_x64.exe",
            "./assets/a.css",
        ] {
            assert!(check_path_safety(ok).is_ok(), "should allow {ok:?}");
        }
    }

    #[test]
    fn runtime_filter_keeps_the_tree_and_drops_the_rest() {
        assert!(is_runtime_member("Runtime/python.exe"));
        assert!(is_runtime_member("wrapper/Runtime/python.exe"));
        assert!(is_runtime_member("readme.txt")); // loose top-level
        assert!(!is_runtime_member("build_scratch/obj/foo.o"));
    }

    #[test]
    fn a_normal_zip_round_trips() {
        let dir = std::env::temp_dir().join("rvcf-extract-zip-test");
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        let zip_path = dir.join("ui.zip");

        {
            let f = fs::File::create(&zip_path).unwrap();
            let mut z = zip::ZipWriter::new(f);
            let opts: zip::write::FileOptions<'_, ()> = zip::write::FileOptions::default();
            z.start_file("index.html", opts).unwrap();
            z.write_all(b"<!doctype html>").unwrap();
            z.start_file("assets/app.js", opts).unwrap();
            z.write_all(b"console.log(1)").unwrap();
            z.finish().unwrap();
        }

        let out = dir.join("out");
        extract_zip(&zip_path, &out).expect("a plain UI zip must extract");
        assert!(out.join("index.html").is_file());
        assert!(out.join("assets").join("app.js").is_file());
        let _ = fs::remove_dir_all(&dir);
    }
}
