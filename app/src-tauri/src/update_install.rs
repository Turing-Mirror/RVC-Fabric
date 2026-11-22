//! Remove obsolete program resources during full-package replacement.
//! Personal files and downloaded components are never part of this inventory.
use std::collections::BTreeSet;
use std::fs;
use std::path::{Component, Path, PathBuf};

use serde_json::{json, Value};

fn backup_dir(root: &Path) -> PathBuf {
    crate::paths::user_data(root).join("update_channels/program_backup")
}

fn allowed(relative: &str) -> bool {
    if relative.contains('\\') || relative.contains(':') {
        return false;
    }
    let p = Path::new(relative);
    if !p.components().all(|c| matches!(c, Component::Normal(_))) {
        return false;
    }
    let top = relative.split('/').next().unwrap_or("");
    match top {
        "frontend" | "frontend.prev" | "shell-i18n" | "infer" | "tools" | "i18n" | "configs"
        | "legal" => relative.contains('/'),
        // This is bundled code/configuration only. Weight and index files stay.
        "assets" => {
            ![
                "assets/weights/",
                "assets/indices/",
                "assets/hubert/",
                "assets/rmvpe/",
                "assets/pretrained/",
                "assets/pretrained_v2/",
            ]
            .iter()
            .any(|s| relative.starts_with(s))
                && matches!(
                    p.extension().and_then(|s| s.to_str()),
                    Some("yaml" | "yml" | "json" | "ico" | "png" | "svg" | "css" | "txt" | "md")
                )
        }
        _ => matches!(
            relative,
            "gui_v1.py"
                | "infer-web.py"
                | ".env"
                | "setup_package.json"
                | "LICENSE"
                | "README.md"
                | "使用说明.txt"
        ),
    }
}

fn inside(root: &Path, path: &Path) -> Result<(), String> {
    let relative = path
        .strip_prefix(root)
        .map_err(|_| "更新路径不在安装目录内")?;
    let mut current = root.to_path_buf();
    for part in relative.components() {
        if !matches!(part, Component::Normal(_)) {
            return Err("更新路径错误".into());
        }
        current.push(part);
        let meta = fs::symlink_metadata(&current).map_err(|e| e.to_string())?;
        if is_link(&meta) {
            return Err("程序资源包含目录链接，无法安全替换".into());
        }
    }
    let actual = path.canonicalize().map_err(|e| e.to_string())?;
    if !actual.starts_with(root) || actual == root {
        return Err("更新文件路径不在当前安装目录内".into());
    }
    Ok(())
}

fn is_link(meta: &fs::Metadata) -> bool {
    if meta.file_type().is_symlink() {
        return true;
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        meta.file_attributes() & 0x400 != 0
    }
    #[cfg(not(windows))]
    {
        false
    }
}

fn collect(
    root: &Path,
    dir: &Path,
    files: &mut BTreeSet<String>,
    caches_only: bool,
) -> Result<(), String> {
    if !dir.exists() {
        return Ok(());
    }
    inside(root, dir)?;
    for entry in fs::read_dir(dir).map_err(|e| e.to_string())? {
        let path = entry.map_err(|e| e.to_string())?.path();
        let meta = fs::symlink_metadata(&path).map_err(|e| e.to_string())?;
        inside(root, &path)?;
        if is_link(&meta) {
            return Err("程序资源包含链接，无法安全替换".into());
        }
        if meta.is_dir() {
            collect(root, &path, files, caches_only)?;
        } else if meta.is_file()
            && (!caches_only || path.extension().is_some_and(|x| x == "pyc" || x == "pyo"))
        {
            let relative = path
                .strip_prefix(root)
                .map_err(|e| e.to_string())?
                .to_string_lossy()
                .replace('\\', "/");
            if allowed(&relative) {
                files.insert(relative);
            }
        }
    }
    Ok(())
}

/// Called only after the signed installer is available and task checks pass.
/// A second call by the installer is harmless: files already moved are absent.
pub fn prepare_install(root: &Path) -> Result<(), String> {
    if !root.exists() {
        return Ok(());
    }
    let root = root.canonicalize().map_err(|e| e.to_string())?;
    if root.parent().is_none() || root.join(".git").exists() {
        return Err("不能将开发仓库或磁盘根目录作为更新清理目标".into());
    }
    let meta_path = root.join("setup_package.json");
    if !meta_path.exists() {
        return Ok(());
    } // fresh install / already prepared
    let meta: Value = serde_json::from_slice(&fs::read(&meta_path).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    if meta["product"] != "RVC Fabric" || !root.join("rvc-fabric.exe").is_file() {
        return Err("无法确认当前目录是 RVC Fabric 安装目录".into());
    }
    let mut files = BTreeSet::new();
    files.insert("setup_package.json".to_owned());
    if let Some(inventory) = meta["program_files"].as_array() {
        for file in inventory {
            let relative = file.as_str().ok_or("程序文件清单格式错误")?;
            if !allowed(relative) {
                // Resources outside this cleanup allowlist are preserved.
                continue;
            }
            files.insert(relative.to_owned());
        }
    }
    // gui_patch files may not be listed in the original installer inventory.
    for name in ["frontend", "frontend.prev", "shell-i18n"] {
        collect(&root, &root.join(name), &mut files, false)?;
    }
    for name in ["infer", "tools", "i18n", "configs"] {
        collect(&root, &root.join(name), &mut files, true)?;
    }
    let backup = backup_dir(&root);
    fs::create_dir_all(&backup).map_err(|e| e.to_string())?;
    inside(&root, &backup)?;
    let record = backup.join("manifest.json");
    let previous = fs::read(&record)
        .ok()
        .and_then(|v| serde_json::from_slice::<Value>(&v).ok());
    let batch = backup.join(format!(
        "files-{}-{}",
        std::process::id(),
        rand::random::<u64>()
    ));
    fs::create_dir_all(&batch).map_err(|e| e.to_string())?;
    let mut moved = Vec::new();
    let result = (|| {
        for relative in &files {
            let src = root.join(relative);
            if !src.exists() {
                continue;
            }
            inside(&root, &src)?;
            if !src.is_file() {
                return Err("程序文件清单指向了目录".into());
            }
            let dst = batch.join(relative);
            fs::create_dir_all(dst.parent().ok_or("备份路径错误")?).map_err(|e| e.to_string())?;
            inside(&root, dst.parent().unwrap())?;
            fs::rename(&src, &dst).map_err(|e| format!("无法替换程序文件 {relative}: {e}"))?;
            moved.push(relative.clone());
        }
        let data =
            json!({"directory": batch.file_name().unwrap().to_string_lossy(), "files": moved});
        let text = serde_json::to_string(&data).map_err(|e| e.to_string())?;
        crate::config::write_atomic(&record, &text).map_err(|e| e.to_string())
    })();
    if result.is_err() {
        let mut restore_failed = false;
        for relative in moved.iter().rev() {
            let src = batch.join(relative);
            let dst = root.join(relative);
            if let Some(parent) = dst.parent() {
                let _ = fs::create_dir_all(parent);
            }
            if fs::rename(src, dst).is_err() {
                restore_failed = true;
            }
        }
        if restore_failed {
            return Err(format!(
                "{}；部分程序文件未能还原，备份保留在 {}，请用原版本安装包修复。",
                result.unwrap_err(),
                batch.display()
            ));
        }
    }
    if result.is_ok() {
        // Keep one program backup, rather than growing with every Beta.
        if let Some(previous) = previous {
            let _ = discard_backup(&root, &backup, &previous);
        }
    }
    result
}

fn discard_backup(root: &Path, backup: &Path, meta: &Value) -> Result<(), String> {
    let directory = meta["directory"].as_str().ok_or("备份目录错误")?;
    if !directory.starts_with("files-") || directory.contains(['/', '\\', ':']) {
        return Err("备份目录错误".into());
    }
    let batch = backup.join(directory);
    if !batch.exists() {
        return Ok(());
    }
    inside(root, &batch)?;
    for entry in meta["files"].as_array().ok_or("备份清单错误")? {
        let rel = entry
            .as_str()
            .filter(|s| allowed(s))
            .ok_or("备份路径错误")?;
        let path = batch.join(rel);
        if path.exists() {
            inside(root, &path)?;
            fs::remove_file(&path).map_err(|e| e.to_string())?;
        }
        let mut parent = path.parent();
        while let Some(dir) = parent {
            if !dir.starts_with(&batch) {
                break;
            }
            if fs::remove_dir(dir).is_err() {
                break;
            }
            parent = dir.parent();
        }
    }
    Ok(())
}

/// Restore program resources if launching the installer fails before exit.
pub fn rollback_preparation(root: &Path) -> Result<(), String> {
    let root = root.canonicalize().map_err(|e| e.to_string())?;
    let backup = backup_dir(&root);
    let record = backup.join("manifest.json");
    if !record.exists() {
        return Ok(());
    }
    inside(&root, &record)?;
    let meta: Value = serde_json::from_slice(&fs::read(&record).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let directory = meta["directory"].as_str().ok_or("备份清单格式错误")?;
    if !directory.starts_with("files-") || directory.contains(['/', '\\', ':']) {
        return Err("备份目录错误".into());
    }
    let batch = backup.join(directory);
    inside(&root, &batch)?;
    for entry in meta["files"].as_array().ok_or("备份清单格式错误")? {
        let rel = entry
            .as_str()
            .filter(|s| allowed(s))
            .ok_or("备份路径错误")?;
        let src = batch.join(rel);
        if !src.exists() {
            continue;
        }
        inside(&root, &src)?;
        let dst = root.join(rel);
        let parent = dst.parent().ok_or("还原路径错误")?;
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        if parent != root {
            inside(&root, parent)?;
        }
        fs::rename(src, dst).map_err(|e| e.to_string())?;
    }
    fs::remove_file(record).map_err(|e| e.to_string())
}

pub fn from_args() -> Option<i32> {
    let args: Vec<String> = std::env::args().collect();
    let (restore, at) = if let Some(i) = args.iter().position(|s| s == "--prepare-update") {
        (false, i)
    } else {
        (true, args.iter().position(|s| s == "--restore-update")?)
    };
    let Some(root) = args.get(at + 1) else {
        return Some(1);
    };
    let result = if restore {
        rollback_preparation(Path::new(root))
    } else {
        prepare_install(Path::new(root))
    };
    if let Err(error) = &result {
        eprintln!("{error}");
    }
    Some(if result.is_ok() { 0 } else { 1 })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "rvc-update-files-{}-{}",
            std::process::id(),
            rand::random::<u64>()
        ));
        fs::create_dir_all(root.join("frontend/assets")).unwrap();
        fs::create_dir_all(root.join("tools/__pycache__")).unwrap();
        fs::create_dir_all(root.join("User_Data/models")).unwrap();
        fs::create_dir_all(root.join("assets/weights")).unwrap();
        fs::write(root.join("rvc-fabric.exe"), "exe").unwrap();
        fs::write(root.join("frontend/index.html"), "beta").unwrap();
        fs::write(root.join("frontend/assets/old.js"), "old").unwrap();
        fs::write(root.join("tools/experimental.py"), "beta-code").unwrap();
        fs::write(root.join("tools/__pycache__/experimental.pyc"), "cache").unwrap();
        fs::write(root.join("assets/weights/user.pth"), "model").unwrap();
        fs::write(root.join("User_Data/models/new.pth"), "new-model").unwrap();
        fs::write(root.join("setup_package.json"), serde_json::to_vec(&json!({"product":"RVC Fabric","program_files":["tools/experimental.py","assets/weights/user.pth","User_Data/models/new.pth","setup_package.json"]})).unwrap()).unwrap();
        root
    }
    #[test]
    fn replaces_program_and_preserves_personal_files() {
        let root = fixture();
        prepare_install(&root).unwrap();
        assert!(!root.join("frontend/index.html").exists());
        assert!(!root.join("tools/experimental.py").exists());
        assert!(!root.join("tools/__pycache__/experimental.pyc").exists());
        assert!(root.join("assets/weights/user.pth").exists());
        assert!(root.join("User_Data/models/new.pth").exists());
        prepare_install(&root).unwrap();
        rollback_preparation(&root).unwrap();
        assert_eq!(
            fs::read_to_string(root.join("frontend/index.html")).unwrap(),
            "beta"
        );
        assert!(root.join("tools/experimental.py").exists());
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn refuses_escape_and_personal_paths() {
        for bad in [
            "../User_Data/a",
            "frontend/../../a",
            "C:/tools/a.py",
            "User_Data/config.json",
            "Runtime/python.exe",
            "assets/rmvpe/rmvpe.pt",
        ] {
            assert!(!allowed(bad), "{bad}");
        }
        let root = fixture();
        fs::create_dir(root.join(".git")).unwrap();
        assert!(prepare_install(&root).is_err());
        assert!(root.join("frontend/index.html").exists());
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn legacy_inventory_preparation_is_idempotent() {
        let root = fixture();
        fs::write(
            root.join("setup_package.json"),
            r#"{"product":"RVC Fabric"}"#,
        )
        .unwrap();
        prepare_install(&root).unwrap();
        let record = fs::read(backup_dir(&root).join("manifest.json")).unwrap();
        prepare_install(&root).unwrap();
        assert_eq!(
            record,
            fs::read(backup_dir(&root).join("manifest.json")).unwrap()
        );
        rollback_preparation(&root).unwrap();
        assert!(root.join("frontend/index.html").is_file());
        fs::remove_dir_all(root).unwrap();
    }
    #[cfg(windows)]
    #[test]
    fn refuses_frontend_junction_to_user_models() {
        let root = fixture();
        fs::remove_dir_all(root.join("frontend")).unwrap();
        let output = std::process::Command::new("powershell.exe")
            .args(["-NoProfile", "-Command", "New-Item -ItemType Junction -Path $env:RVC_TEST_LINK -Target $env:RVC_TEST_TARGET -ErrorAction Stop | Out-Null"])
            .env("RVC_TEST_LINK", root.join("frontend"))
            .env("RVC_TEST_TARGET", root.join("User_Data/models"))
            .output()
            .unwrap();
        assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
        assert!(prepare_install(&root).is_err());
        assert_eq!(
            fs::read_to_string(root.join("User_Data/models/new.pth")).unwrap(),
            "new-model"
        );
        fs::remove_dir(root.join("frontend")).unwrap();
        fs::remove_dir_all(root).unwrap();
    }
}
