//! Persistent audio sources and entries. This layer never starts the RVC Runtime.
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, Ordering};
use std::{
    collections::{HashMap, HashSet},
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    sync::Mutex,
};
use tauri::{AppHandle, Emitter, State};

use crate::paths;

const SCHEMA_VERSION: u32 = 1;
static WRITE_LOCK: Mutex<()> = Mutex::new(());
static EXPORT_BUSY: AtomicBool = AtomicBool::new(false);
static EXPORT_CANCEL: AtomicBool = AtomicBool::new(false);
static SCAN_BUSY: AtomicBool = AtomicBool::new(false);
static SCAN_CANCEL: AtomicBool = AtomicBool::new(false);

struct ScanGuard;
impl ScanGuard {
    fn start() -> Result<Self, String> {
        SCAN_BUSY
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .map_err(|_| "audio_scan_busy".to_string())?;
        SCAN_CANCEL.store(false, Ordering::Release);
        Ok(Self)
    }
}
impl Drop for ScanGuard {
    fn drop(&mut self) {
        SCAN_BUSY.store(false, Ordering::Release);
    }
}

fn scan_check(cancel: &AtomicBool) -> Result<(), String> {
    if cancel.load(Ordering::Acquire) {
        Err("audio_scan_cancelled".into())
    } else {
        Ok(())
    }
}

struct ExportGuard;
impl ExportGuard {
    fn start() -> Result<Self, String> {
        EXPORT_BUSY
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .map_err(|_| "audio_export_busy".to_string())?;
        EXPORT_CANCEL.store(false, Ordering::Release);
        Ok(Self)
    }
}
impl Drop for ExportGuard {
    fn drop(&mut self) {
        EXPORT_BUSY.store(false, Ordering::Release);
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceKind {
    File,
    Directory,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ImportMode {
    Reference,
    Copy,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Source {
    pub id: String,
    pub path: String,
    pub kind: SourceKind,
    pub mode: ImportMode,
    pub recursive: bool,
    #[serde(default)]
    pub excludes: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Asset {
    pub id: String,
    pub path: String,
    pub origin: String,
    pub source_ids: Vec<String>,
    pub size: u64,
    pub modified_ms: Option<u64>,
    #[serde(default)]
    pub duration: Option<f64>,
    #[serde(default = "default_available")]
    pub available: bool,
    #[serde(skip)]
    pub excluded_source_ids: Vec<String>,
}

fn default_available() -> bool {
    true
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Entry {
    pub id: String,
    pub asset_id: String,
    pub name: String,
    pub number: Option<u64>,
    pub start: f64,
    pub end: Option<f64>,
    pub volume: f32,
    pub looped: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Library {
    pub schema_version: u32,
    pub revision: u64,
    next_id: u64,
    pub sources: Vec<Source>,
    pub assets: Vec<Asset>,
    pub entries: Vec<Entry>,
}

impl Default for Library {
    fn default() -> Self {
        Self {
            schema_version: SCHEMA_VERSION,
            revision: 0,
            next_id: 1,
            sources: Vec::new(),
            assets: Vec::new(),
            entries: Vec::new(),
        }
    }
}

impl Library {
    fn id(&mut self, prefix: &str) -> String {
        let id = format!("{prefix}-{}", self.next_id);
        self.next_id += 1;
        id
    }

    fn validate(&self) -> Result<(), String> {
        if self.schema_version != SCHEMA_VERSION {
            return Err("audio_library_unsupported_version".into());
        }
        if self.next_id == 0 {
            return Err("audio_library_invalid_id".into());
        }
        let mut numbers = HashSet::new();
        let asset_ids: HashSet<_> = self.assets.iter().map(|asset| asset.id.as_str()).collect();
        for entry in &self.entries {
            if entry.number.is_some_and(|n| n == 0 || !numbers.insert(n)) {
                return Err("audio_library_duplicate_number".into());
            }
            if !asset_ids.contains(entry.asset_id.as_str()) {
                return Err("audio_library_missing_asset".into());
            }
        }
        Ok(())
    }
}

fn store_path(root: &Path) -> PathBuf {
    paths::user_data(root).join("audio").join("library.json")
}

fn load(root: &Path) -> Result<Library, String> {
    let path = store_path(root);
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Library::default()),
        Err(e) => return Err(e.to_string()),
    };
    let library: Library =
        serde_json::from_str(&text).map_err(|_| "audio_library_corrupt".to_string())?;
    library.validate()?;
    Ok(library)
}

fn save(root: &Path, library: &Library) -> Result<(), String> {
    library.validate()?;
    let path = store_path(root);
    let dir = path.parent().ok_or("audio_library_path_invalid")?;
    fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    let data = serde_json::to_vec_pretty(library).map_err(|e| e.to_string())?;
    let mut seq = 0u32;
    loop {
        let tmp = dir.join(format!("library-{}-{seq}.tmp", std::process::id()));
        match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&tmp)
        {
            Ok(mut file) => {
                let result = (|| -> std::io::Result<()> {
                    file.write_all(&data)?;
                    file.sync_all()?;
                    fs::rename(&tmp, &path)
                })();
                if result.is_err() {
                    let _ = fs::remove_file(&tmp);
                }
                return result.map_err(|e| e.to_string());
            }
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => seq += 1,
            Err(e) => return Err(e.to_string()),
        }
    }
}

fn mutate<F>(root: &Path, operation: F) -> Result<Library, String>
where
    F: FnOnce(&mut Library) -> Result<bool, String>,
{
    let _guard = WRITE_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let mut library = load(root)?;
    if operation(&mut library)? {
        library.revision += 1;
        save(root, &library)?;
    }
    mark_status(&mut library);
    Ok(library)
}

pub fn snapshot(root: &Path) -> Result<Library, String> {
    let _guard = WRITE_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let mut library = load(root)?;
    mark_status(&mut library);
    Ok(library)
}

fn mark_status(library: &mut Library) {
    let sources: HashMap<_, _> = library
        .sources
        .iter()
        .map(|source| (source.id.as_str(), source))
        .collect();
    for asset in &mut library.assets {
        let key = stored_key(&asset.origin);
        asset.excluded_source_ids = asset
            .source_ids
            .iter()
            .filter(|id| {
                sources
                    .get(id.as_str())
                    .is_some_and(|source| source.excludes.contains(&key))
            })
            .cloned()
            .collect();
    }
}

fn path_key(path: &Path) -> String {
    let canonical = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
    stored_key(&canonical.to_string_lossy())
}

fn stored_key(text: &str) -> String {
    if cfg!(windows) {
        text.replace("\\\\?\\UNC\\", "\\\\")
            .replace("\\\\?\\", "")
            .to_lowercase()
    } else {
        text.to_string()
    }
}

fn audio_file(path: &Path) -> bool {
    matches!(
        path.extension()
            .and_then(|x| x.to_str())
            .unwrap_or("")
            .to_ascii_lowercase()
            .as_str(),
        "wav" | "mp3" | "flac" | "m4a" | "ogg" | "aac" | "opus"
    )
}

fn collect(
    root: &Path,
    path: &Path,
    recursive: bool,
    cancel: &AtomicBool,
    found: &mut u64,
    progress: &mut dyn FnMut(u64),
) -> Result<Vec<PathBuf>, String> {
    scan_check(cancel)?;
    let canonical_root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let user_data = paths::user_data(&canonical_root);
    let skipped = [user_data.join("audio"), user_data.join("audio_clips")];
    if skipped.iter().any(|directory| path.starts_with(directory)) {
        return Err("audio_source_managed".into());
    }
    if path.is_file() {
        return if audio_file(path) {
            *found += 1;
            progress(*found);
            Ok(vec![path.to_path_buf()])
        } else {
            Err("audio_file_type_unsupported".into())
        };
    }
    if !path.is_dir() {
        return Err("audio_source_missing".into());
    }
    let mut files = Vec::new();
    let mut pending = vec![path.to_path_buf()];
    while let Some(dir) = pending.pop() {
        scan_check(cancel)?;
        for item in fs::read_dir(dir).map_err(|e| e.to_string())? {
            scan_check(cancel)?;
            let item = item.map_err(|e| e.to_string())?;
            let kind = item.file_type().map_err(|e| e.to_string())?;
            if skipped
                .iter()
                .any(|directory| item.path().starts_with(directory))
            {
                continue;
            }
            if kind.is_symlink() {
                continue;
            }
            if kind.is_dir() && recursive {
                pending.push(item.path());
            } else if kind.is_file() && audio_file(&item.path()) {
                files.push(item.path());
                *found += 1;
                if *found % 32 == 0 {
                    progress(*found);
                }
            }
        }
    }
    files.sort();
    Ok(files)
}

fn file_stamp(path: &Path) -> Result<(u64, Option<u64>), String> {
    let meta = fs::metadata(path).map_err(|e| e.to_string())?;
    let modified_ms = meta.modified().ok().and_then(|time| {
        time.duration_since(std::time::UNIX_EPOCH)
            .ok()
            .map(|duration| duration.as_millis() as u64)
    });
    Ok((meta.len(), modified_ms))
}

fn attach_files(
    root: &Path,
    library: &mut Library,
    source: &Source,
    files: &[PathBuf],
    created_copies: &mut Vec<PathBuf>,
    cancel: &AtomicBool,
) -> Result<bool, String> {
    let mut changed = false;
    let mut by_origin: HashMap<String, usize> = library
        .assets
        .iter()
        .enumerate()
        .map(|(index, asset)| (stored_key(&asset.origin), index))
        .collect();
    for file in files {
        scan_check(cancel)?;
        let origin = fs::canonicalize(file).map_err(|e| e.to_string())?;
        let key = path_key(&origin);
        if source.excludes.contains(&key) {
            continue;
        }
        if let Some(&index) = by_origin.get(&key) {
            let asset = &mut library.assets[index];
            if !asset.source_ids.contains(&source.id) {
                asset.source_ids.push(source.id.clone());
                changed = true;
            }
            if asset.path == asset.origin && !asset.available {
                asset.available = true;
                changed = true;
            }
            if asset.path != asset.origin {
                let available = Path::new(&asset.path).is_file();
                changed |= asset.available != available;
                asset.available = available;
            }
            if source.mode == ImportMode::Copy && asset.path == asset.origin {
                let copy = copy_to_library(root, &asset.id, &origin, cancel)?;
                created_copies.push(copy.clone());
                asset.path = copy.to_string_lossy().into_owned();
                changed = true;
            }
            if asset.path == asset.origin {
                let (size, modified_ms) = file_stamp(&origin)?;
                if asset.size != size || asset.modified_ms != modified_ms {
                    asset.size = size;
                    asset.modified_ms = modified_ms;
                    asset.duration = None;
                    changed = true;
                }
            }
            continue;
        }
        let id = library.id("asset");
        let path = if source.mode == ImportMode::Copy {
            let copy = copy_to_library(root, &id, &origin, cancel)?;
            created_copies.push(copy.clone());
            copy
        } else {
            origin.clone()
        };
        let (size, modified_ms) = file_stamp(&origin)?;
        let asset = Asset {
            id: id.clone(),
            path: path.to_string_lossy().into_owned(),
            origin: origin.to_string_lossy().into_owned(),
            source_ids: vec![source.id.clone()],
            size,
            modified_ms,
            duration: None,
            available: true,
            excluded_source_ids: Vec::new(),
        };
        by_origin.insert(key, library.assets.len());
        library.assets.push(asset);
        let name = origin
            .file_stem()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_else(|| "Audio".into());
        let entry_id = library.id("entry");
        library.entries.push(Entry {
            id: entry_id,
            asset_id: id,
            name,
            number: None,
            start: 0.0,
            end: None,
            volume: 1.0,
            looped: false,
        });
        changed = true;
    }
    Ok(changed)
}

fn copy_to_library(
    root: &Path,
    id: &str,
    source: &Path,
    cancel: &AtomicBool,
) -> Result<PathBuf, String> {
    let media = paths::user_data(root).join("audio").join("media");
    fs::create_dir_all(&media).map_err(|e| e.to_string())?;
    let ext = source.extension().and_then(|s| s.to_str()).unwrap_or("wav");
    let target = media.join(format!("{id}.{ext}"));
    let temp = media.join(format!(".{id}-{}.part", std::process::id()));
    let mut input = fs::File::open(source).map_err(|e| e.to_string())?;
    let mut output = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(|e| e.to_string())?;
    let copied = (|| -> Result<(), String> {
        let mut buffer = [0u8; 256 * 1024];
        loop {
            scan_check(cancel)?;
            let read = input.read(&mut buffer).map_err(|e| e.to_string())?;
            if read == 0 {
                break;
            }
            output
                .write_all(&buffer[..read])
                .map_err(|e| e.to_string())?;
        }
        output.sync_all().map_err(|e| e.to_string())?;
        scan_check(cancel)
    })();
    if let Err(e) = copied {
        drop(output);
        let _ = fs::remove_file(&temp);
        return Err(e);
    }
    drop(output);
    crate::file_publish::publish_new(&temp, &target).map_err(|e| {
        let _ = fs::remove_file(&temp);
        if e.kind() == std::io::ErrorKind::AlreadyExists {
            "audio_copy_target_exists".to_string()
        } else {
            e.to_string()
        }
    })?;
    Ok(target)
}

#[cfg(test)]
fn import(
    root: &Path,
    paths: &[PathBuf],
    mode: ImportMode,
    recursive: bool,
) -> Result<Library, String> {
    import_with_progress(
        root,
        paths,
        mode,
        recursive,
        &AtomicBool::new(false),
        &mut |_| {},
    )
}

fn import_with_progress(
    root: &Path,
    paths: &[PathBuf],
    mode: ImportMode,
    recursive: bool,
    cancel: &AtomicBool,
    progress: &mut dyn FnMut(u64),
) -> Result<Library, String> {
    if paths.is_empty() {
        return snapshot(root);
    }
    // Scan outside the mutation lock. A slow or offline directory cannot block numbering edits.
    let mut found = 0;
    let scans: Result<Vec<_>, String> = paths
        .iter()
        .map(|path| {
            scan_check(cancel)?;
            let canonical = fs::canonicalize(path).map_err(|e| e.to_string())?;
            let kind = if canonical.is_dir() {
                SourceKind::Directory
            } else {
                SourceKind::File
            };
            let files = collect(root, &canonical, recursive, cancel, &mut found, progress)?;
            Ok((canonical, kind, files))
        })
        .collect();
    let scans = scans?;
    progress(found);
    scan_check(cancel)?;
    let mut created_copies = Vec::new();
    let result = mutate(root, |library| {
        let mut changed = false;
        for (path, kind, files) in &scans {
            scan_check(cancel)?;
            let key = path_key(path);
            let source = if let Some(existing) =
                library.sources.iter().find(|s| stored_key(&s.path) == key)
            {
                if existing.mode != mode
                    || (existing.kind == SourceKind::Directory && existing.recursive != recursive)
                {
                    return Err("audio_source_options_conflict".into());
                }
                existing.clone()
            } else {
                let source = Source {
                    id: library.id("source"),
                    path: path.to_string_lossy().into_owned(),
                    kind: *kind,
                    mode,
                    recursive,
                    excludes: Vec::new(),
                };
                library.sources.push(source.clone());
                changed = true;
                source
            };
            changed |= attach_files(root, library, &source, files, &mut created_copies, cancel)?;
        }
        scan_check(cancel)?;
        Ok(changed)
    });
    if result.is_err() {
        for copy in created_copies {
            let _ = fs::remove_file(copy);
        }
    }
    result
}

#[cfg(test)]
fn refresh(root: &Path, source_id: &str) -> Result<Library, String> {
    refresh_with_progress(root, source_id, &AtomicBool::new(false), &mut |_| {})
}

fn relocated_path(source: &Source, replacement: &Path, original: &str) -> Result<PathBuf, String> {
    if source.kind == SourceKind::File {
        if stored_key(original) != stored_key(&source.path) {
            return Err("audio_relink_invalid_source".into());
        }
        return Ok(replacement.to_path_buf());
    }
    let old_root = stored_key(&source.path);
    let old_path = stored_key(original);
    let relative = Path::new(&old_path)
        .strip_prefix(&old_root)
        .map_err(|_| "audio_relink_invalid_source")?;
    Ok(replacement.join(relative))
}

#[cfg(test)]
fn relink_source(root: &Path, source_id: &str, replacement: &Path) -> Result<Library, String> {
    relink_source_with_progress(
        root,
        source_id,
        replacement,
        &AtomicBool::new(false),
        &mut |_| {},
    )
}

fn relink_source_with_progress(
    root: &Path,
    source_id: &str,
    replacement: &Path,
    cancel: &AtomicBool,
    progress: &mut dyn FnMut(u64),
) -> Result<Library, String> {
    scan_check(cancel)?;
    let replacement = fs::canonicalize(replacement).map_err(|e| e.to_string())?;
    let current = snapshot(root)?;
    let source = current
        .sources
        .iter()
        .find(|s| s.id == source_id)
        .ok_or("audio_source_unknown")?;
    if source.mode != ImportMode::Reference {
        return Err("audio_relink_copy_source".into());
    }
    if current
        .sources
        .iter()
        .any(|item| item.id != source_id && stored_key(&item.path) == path_key(&replacement))
    {
        return Err("audio_relink_conflict".into());
    }
    if current
        .assets
        .iter()
        .any(|asset| asset.source_ids.contains(&source.id) && asset.source_ids.len() != 1)
    {
        return Err("audio_relink_shared_asset".into());
    }
    let is_expected_kind = match source.kind {
        SourceKind::File => replacement.is_file() && audio_file(&replacement),
        SourceKind::Directory => replacement.is_dir(),
    };
    if !is_expected_kind {
        return Err("audio_relink_kind_mismatch".into());
    }
    let mut found = 0;
    let files = collect(
        root,
        &replacement,
        source.recursive,
        cancel,
        &mut found,
        progress,
    )?;
    progress(found);
    scan_check(cancel)?;
    mutate(root, |library| {
        let index = library
            .sources
            .iter()
            .position(|s| s.id == source_id)
            .ok_or("audio_source_unknown")?;
        let original = library.sources[index].clone();
        let new_key = path_key(&replacement);
        if library
            .sources
            .iter()
            .any(|s| s.id != source_id && stored_key(&s.path) == new_key)
        {
            return Err("audio_relink_conflict".into());
        }
        let moving: HashSet<_> = library
            .assets
            .iter()
            .filter(|asset| asset.source_ids.contains(&original.id))
            .map(|asset| asset.id.as_str())
            .collect();
        let occupied: HashSet<_> = library
            .assets
            .iter()
            .filter(|asset| !moving.contains(asset.id.as_str()))
            .map(|asset| stored_key(&asset.origin))
            .collect();
        let mut changes = Vec::new();
        for (asset_index, asset) in library.assets.iter().enumerate() {
            if !moving.contains(asset.id.as_str()) {
                continue;
            }
            if asset.source_ids.len() != 1 || asset.path != asset.origin {
                return Err("audio_relink_shared_asset".into());
            }
            let target = relocated_path(&original, &replacement, &asset.origin)?;
            let key = path_key(&target);
            if occupied.contains(&key) {
                return Err("audio_relink_conflict".into());
            }
            changes.push((asset_index, target));
        }
        let mut updated = original.clone();
        updated.path = replacement.to_string_lossy().into_owned();
        updated.excludes = original
            .excludes
            .iter()
            .map(|excluded| relocated_path(&original, &replacement, excluded).map(|p| path_key(&p)))
            .collect::<Result<_, _>>()?;
        library.sources[index] = updated.clone();
        for (asset_index, target) in changes {
            scan_check(cancel)?;
            let asset = &mut library.assets[asset_index];
            let path = target.canonicalize().unwrap_or(target);
            let path_str = path.to_string_lossy().into_owned();
            if asset.path != path_str {
                asset.duration = None;
            }
            let available = path.is_file();
            if available {
                let (size, modified_ms) = file_stamp(&path)?;
                if asset.size != size || asset.modified_ms != modified_ms {
                    asset.duration = None;
                }
                asset.size = size;
                asset.modified_ms = modified_ms;
            }
            asset.origin = path_str.clone();
            asset.path = path_str;
            asset.available = available;
        }
        attach_files(root, library, &updated, &files, &mut Vec::new(), cancel)?;
        scan_check(cancel)?;
        Ok(true)
    })
}

pub fn relink_asset(
    root: &Path,
    asset_id: &str,
    replacement: &Path,
    replace_scanned_duplicate: bool,
) -> Result<Library, String> {
    let replacement = fs::canonicalize(replacement).map_err(|e| e.to_string())?;
    if !replacement.is_file() || !audio_file(&replacement) {
        return Err("audio_relink_kind_mismatch".into());
    }
    let canonical_root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let user_data = paths::user_data(&canonical_root);
    if replacement.starts_with(user_data.join("audio"))
        || replacement.starts_with(user_data.join("audio_clips"))
    {
        return Err("audio_source_managed".into());
    }
    mutate(root, |library| {
        let index = library
            .assets
            .iter()
            .position(|a| a.id == asset_id)
            .ok_or("audio_asset_unknown")?;
        let old = library.assets[index].clone();
        if old.path != old.origin {
            return Err("audio_relink_copy_source".into());
        }
        let new_key = path_key(&replacement);
        let collision = library
            .assets
            .iter()
            .find(|a| a.id != asset_id && stored_key(&a.origin) == new_key)
            .cloned();
        if library.sources.iter().any(|source| {
            source.kind == SourceKind::File
                && !old.source_ids.contains(&source.id)
                && stored_key(&source.path) == new_key
        }) {
            return Err("audio_relink_conflict".into());
        }
        let mut related = old.source_ids.clone();
        if let Some(duplicate) = &collision {
            let entries: Vec<_> = library
                .entries
                .iter()
                .filter(|entry| entry.asset_id == duplicate.id)
                .collect();
            let default_name = replacement
                .file_stem()
                .unwrap_or_default()
                .to_string_lossy();
            let untouched = entries.len() == 1
                && entries[0].name == default_name
                && entries[0].number.is_none()
                && entries[0].start == 0.0
                && entries[0].end.is_none()
                && entries[0].volume == 1.0
                && !entries[0].looped;
            if duplicate.path != duplicate.origin || !untouched {
                return Err("audio_relink_conflict".into());
            }
            if !replace_scanned_duplicate {
                return Err("audio_relink_duplicate_target".into());
            }
            for id in &duplicate.source_ids {
                if !related.contains(id) {
                    related.push(id.clone());
                }
            }
        }
        for source in &library.sources {
            if !related.contains(&source.id) {
                continue;
            }
            if source.kind == SourceKind::Directory {
                let source_path = stored_key(&source.path);
                let selected_path = Path::new(&new_key);
                if !selected_path.starts_with(&source_path)
                    || (!source.recursive
                        && selected_path.parent() != Some(Path::new(&source_path)))
                {
                    return Err("audio_relink_outside_source".into());
                }
            }
        }
        let old_key = stored_key(&old.origin);
        for source in &mut library.sources {
            if !related.contains(&source.id) {
                continue;
            }
            if source.kind == SourceKind::File {
                source.path = replacement.to_string_lossy().into_owned();
            }
            for excluded in &mut source.excludes {
                if *excluded == old_key {
                    *excluded = new_key.clone();
                }
            }
        }
        let (size, modified_ms) = file_stamp(&replacement)?;
        if let Some(duplicate) = &collision {
            library
                .entries
                .retain(|entry| entry.asset_id != duplicate.id);
            library.assets.retain(|asset| asset.id != duplicate.id);
        }
        let asset = library
            .assets
            .iter_mut()
            .find(|asset| asset.id == asset_id)
            .ok_or("audio_asset_unknown")?;
        asset.source_ids = related;
        let next_path = replacement.to_string_lossy().into_owned();
        if asset.path != next_path {
            asset.duration = None;
        }
        asset.origin = next_path;
        asset.path = asset.origin.clone();
        asset.available = true;
        if asset.size != size || asset.modified_ms != modified_ms {
            asset.duration = None;
        }
        asset.size = size;
        asset.modified_ms = modified_ms;
        Ok(true)
    })
}

fn refresh_with_progress(
    root: &Path,
    source_id: &str,
    cancel: &AtomicBool,
    progress: &mut dyn FnMut(u64),
) -> Result<Library, String> {
    let source = snapshot(root)?
        .sources
        .into_iter()
        .find(|source| source.id == source_id)
        .ok_or("audio_source_unknown")?;
    if source.mode == ImportMode::Copy {
        return mutate(root, |library| {
            let mut changed = false;
            for asset in library
                .assets
                .iter_mut()
                .filter(|asset| asset.source_ids.contains(&source.id))
            {
                let available = Path::new(&asset.path).is_file();
                changed |= asset.available != available;
                asset.available = available;
            }
            Ok(changed)
        });
    }
    let mut found = 0;
    let files = match collect(
        root,
        Path::new(&source.path),
        source.recursive,
        cancel,
        &mut found,
        progress,
    ) {
        Ok(files) => files,
        Err(error) if error == "audio_source_missing" => Vec::new(),
        Err(error) => return Err(error),
    };
    progress(found);
    scan_check(cancel)?;
    let found: HashSet<_> = files.iter().map(|path| path_key(path)).collect();
    mutate(root, |library| {
        let current = library
            .sources
            .iter()
            .find(|item| item.id == source_id)
            .ok_or("audio_source_unknown")?
            .clone();
        let mut changed = false;
        for asset in library
            .assets
            .iter_mut()
            .filter(|asset| asset.source_ids.contains(&current.id))
        {
            let available = if asset.path == asset.origin {
                found.contains(&stored_key(&asset.origin))
            } else {
                Path::new(&asset.path).is_file()
            };
            changed |= asset.available != available;
            asset.available = available;
        }
        changed |= attach_files(root, library, &current, &files, &mut Vec::new(), cancel)?;
        scan_check(cancel)?;
        Ok(changed)
    })
}

pub fn set_number(root: &Path, entry_id: &str, number: Option<u64>) -> Result<Library, String> {
    if number == Some(0) {
        return Err("audio_number_invalid".into());
    }
    mutate(root, |library| {
        if let Some(number) = number {
            if library
                .entries
                .iter()
                .any(|entry| entry.id != entry_id && entry.number == Some(number))
            {
                return Err("audio_number_taken".into());
            }
        }
        let entry = library
            .entries
            .iter_mut()
            .find(|entry| entry.id == entry_id)
            .ok_or("audio_entry_unknown")?;
        let changed = entry.number != number;
        entry.number = number;
        Ok(changed)
    })
}

pub fn rename_entry(root: &Path, entry_id: &str, name: &str) -> Result<Library, String> {
    let name = name.trim();
    if name.is_empty() || name.len() > 200 {
        return Err("audio_name_invalid".into());
    }
    mutate(root, |library| {
        let entry = library
            .entries
            .iter_mut()
            .find(|entry| entry.id == entry_id)
            .ok_or("audio_entry_unknown")?;
        let changed = entry.name != name;
        entry.name = name.to_string();
        Ok(changed)
    })
}

pub fn add_clip(
    root: &Path,
    asset_id: &str,
    name: &str,
    start: f64,
    end: Option<f64>,
) -> Result<Library, String> {
    let name = name.trim();
    if name.is_empty()
        || name.len() > 200
        || !start.is_finite()
        || start < 0.0
        || end.is_some_and(|end| !end.is_finite() || end <= start)
    {
        return Err("audio_clip_invalid".into());
    }
    let asset = snapshot(root)?
        .assets
        .into_iter()
        .find(|asset| asset.id == asset_id)
        .ok_or("audio_asset_unknown")?;
    fabric_audio::format::ClipRange { start, end }
        .resolve(
            fabric_audio::decode::AudioTools::at(root).probe(Path::new(&asset.path))?,
            48_000,
        )
        .map_err(|_| "audio_clip_invalid")?;
    mutate(root, |library| {
        if !library
            .assets
            .iter()
            .any(|current| current.id == asset_id && current.path == asset.path)
        {
            return Err("audio_asset_changed".into());
        }
        let id = library.id("entry");
        library.entries.push(Entry {
            id,
            asset_id: asset_id.to_string(),
            name: name.to_string(),
            number: None,
            start,
            end,
            volume: 1.0,
            looped: false,
        });
        Ok(true)
    })
}

pub fn set_range(
    root: &Path,
    entry_id: &str,
    start: f64,
    end: Option<f64>,
) -> Result<Library, String> {
    if !start.is_finite() || start < 0.0 || end.is_some_and(|end| !end.is_finite() || end <= start)
    {
        return Err("audio_clip_invalid".into());
    }
    let snapshot = snapshot(root)?;
    let current_entry = snapshot
        .entries
        .iter()
        .find(|entry| entry.id == entry_id)
        .ok_or("audio_entry_unknown")?;
    let asset = snapshot
        .assets
        .iter()
        .find(|asset| asset.id == current_entry.asset_id)
        .ok_or("audio_asset_unknown")?;
    fabric_audio::format::ClipRange { start, end }
        .resolve(
            fabric_audio::decode::AudioTools::at(root).probe(Path::new(&asset.path))?,
            48_000,
        )
        .map_err(|_| "audio_clip_invalid")?;
    let validated_path = asset.path.clone();
    mutate(root, |library| {
        if !library
            .assets
            .iter()
            .any(|asset| asset.id == current_entry.asset_id && asset.path == validated_path)
        {
            return Err("audio_asset_changed".into());
        }
        let entry = library
            .entries
            .iter_mut()
            .find(|entry| entry.id == entry_id)
            .ok_or("audio_entry_unknown")?;
        let changed = entry.start != start || entry.end != end;
        entry.start = start;
        entry.end = end;
        Ok(changed)
    })
}

pub fn exclude(root: &Path, source_id: &str, asset_id: &str) -> Result<Library, String> {
    mutate(root, |library| {
        let asset = library
            .assets
            .iter()
            .find(|asset| asset.id == asset_id)
            .ok_or("audio_asset_unknown")?;
        if !asset.source_ids.iter().any(|id| id == source_id) {
            return Err("audio_source_asset_unrelated".into());
        }
        let key = stored_key(&asset.origin);
        let source = library
            .sources
            .iter_mut()
            .find(|source| source.id == source_id)
            .ok_or("audio_source_unknown")?;
        if source.excludes.contains(&key) {
            return Ok(false);
        }
        source.excludes.push(key);
        Ok(true)
    })
}

pub fn restore(root: &Path, source_id: &str, path: &str) -> Result<Library, String> {
    let key = path_key(Path::new(path));
    mutate(root, |library| {
        let source = library
            .sources
            .iter_mut()
            .find(|source| source.id == source_id)
            .ok_or("audio_source_unknown")?;
        let before = source.excludes.len();
        source.excludes.retain(|excluded| excluded != &key);
        if source.excludes.len() == before {
            return Err("audio_exclusion_unknown".into());
        }
        Ok(true)
    })
}

pub fn remove_source(root: &Path, source_id: &str) -> Result<Library, String> {
    mutate(root, |library| {
        let before = library.sources.len();
        library.sources.retain(|source| source.id != source_id);
        if before == library.sources.len() {
            return Err("audio_source_unknown".into());
        }
        for asset in &mut library.assets {
            asset.source_ids.retain(|id| id != source_id);
        }
        library.assets.retain(|asset| !asset.source_ids.is_empty());
        let kept: HashSet<_> = library
            .assets
            .iter()
            .map(|asset| asset.id.as_str())
            .collect();
        library
            .entries
            .retain(|entry| kept.contains(entry.asset_id.as_str()));
        Ok(true)
    })
}

#[tauri::command]
pub async fn audio_library_get(
    state: State<'_, Mutex<crate::AppState>>,
) -> Result<Library, String> {
    let root = crate::root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || snapshot(&root))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
pub async fn audio_library_pick(
    window: tauri::WebviewWindow,
    kind: String,
) -> Result<Vec<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let picker = crate::shell_extras::dialog_on(Some(&window));
        let paths = match kind.as_str() {
            "file" => picker
                .set_title(&crate::i18n::t("audio.importFiles"))
                .add_filter(
                    &crate::i18n::t("audio.title"),
                    &["wav", "mp3", "flac", "m4a", "ogg", "aac", "opus"],
                )
                .pick_files(),
            "directory" => picker
                .set_title(&crate::i18n::t("audio.importFolders"))
                .pick_folders(),
            _ => return Err("audio_pick_kind_invalid".into()),
        };
        Ok(paths
            .unwrap_or_default()
            .into_iter()
            .map(|path| path.to_string_lossy().into_owned())
            .collect())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
pub async fn audio_library_pick_replacement(
    window: tauri::WebviewWindow,
    kind: String,
) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let picker = crate::shell_extras::dialog_on(Some(&window));
        let path = match kind.as_str() {
            "file" => picker
                .set_title(&crate::i18n::t("audio.relinkFile"))
                .add_filter(
                    &crate::i18n::t("audio.title"),
                    &["wav", "mp3", "flac", "m4a", "ogg", "aac", "opus"],
                )
                .pick_file(),
            "directory" => picker
                .set_title(&crate::i18n::t("audio.relinkSource"))
                .pick_folder(),
            _ => return Err("audio_pick_kind_invalid".into()),
        };
        Ok(path.map(|path| path.to_string_lossy().into_owned()))
    })
    .await
    .map_err(|e| e.to_string())?
}

fn notify(app: &AppHandle, library: &Library) {
    let _ = app.emit("audio-library://changed", library.revision);
}

#[tauri::command]
pub async fn audio_library_import(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    paths: Vec<String>,
    copy: bool,
    recursive: bool,
) -> Result<Library, String> {
    let root = crate::root_clone(&state)?;
    let progress_app = app.clone();
    let library = tauri::async_runtime::spawn_blocking(move || {
        let _guard = ScanGuard::start()?;
        let paths: Vec<PathBuf> = paths.into_iter().map(PathBuf::from).collect();
        import_with_progress(
            &root,
            &paths,
            if copy {
                ImportMode::Copy
            } else {
                ImportMode::Reference
            },
            recursive,
            &SCAN_CANCEL,
            &mut |files| {
                let _ = progress_app.emit("audio-library://scan", files);
            },
        )
    })
    .await
    .map_err(|e| e.to_string())??;
    notify(&app, &library);
    Ok(library)
}

#[tauri::command]
pub async fn audio_library_refresh(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    source_id: String,
) -> Result<Library, String> {
    let root = crate::root_clone(&state)?;
    let progress_app = app.clone();
    let library = tauri::async_runtime::spawn_blocking(move || {
        let _guard = ScanGuard::start()?;
        refresh_with_progress(&root, &source_id, &SCAN_CANCEL, &mut |files| {
            let _ = progress_app.emit("audio-library://scan", files);
        })
    })
    .await
    .map_err(|e| e.to_string())??;
    notify(&app, &library);
    Ok(library)
}

#[tauri::command]
pub fn audio_library_scan_cancel() -> bool {
    if SCAN_BUSY.load(Ordering::Acquire) {
        SCAN_CANCEL.store(true, Ordering::Release);
        true
    } else {
        false
    }
}

#[tauri::command]
pub async fn audio_library_relink_source(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    source_id: String,
    replacement: String,
) -> Result<Library, String> {
    let root = crate::root_clone(&state)?;
    let progress_app = app.clone();
    let library = tauri::async_runtime::spawn_blocking(move || {
        let _guard = ScanGuard::start()?;
        relink_source_with_progress(
            &root,
            &source_id,
            Path::new(&replacement),
            &SCAN_CANCEL,
            &mut |files| {
                let _ = progress_app.emit("audio-library://scan", files);
            },
        )
    })
    .await
    .map_err(|e| e.to_string())??;
    notify(&app, &library);
    Ok(library)
}

#[tauri::command]
pub async fn audio_library_relink_asset(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    asset_id: String,
    replacement: String,
    replace_scanned_duplicate: bool,
) -> Result<Library, String> {
    let root = crate::root_clone(&state)?;
    let library = tauri::async_runtime::spawn_blocking(move || {
        relink_asset(
            &root,
            &asset_id,
            Path::new(&replacement),
            replace_scanned_duplicate,
        )
    })
    .await
    .map_err(|e| e.to_string())??;
    notify(&app, &library);
    Ok(library)
}

#[tauri::command]
pub fn audio_library_set_number(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    entry_id: String,
    number: Option<u64>,
) -> Result<Library, String> {
    let library = set_number(&crate::root_clone(&state)?, &entry_id, number)?;
    notify(&app, &library);
    Ok(library)
}

#[tauri::command]
pub fn audio_library_rename_entry(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    entry_id: String,
    name: String,
) -> Result<Library, String> {
    let library = rename_entry(&crate::root_clone(&state)?, &entry_id, &name)?;
    notify(&app, &library);
    Ok(library)
}

#[tauri::command]
pub async fn audio_library_add_clip(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    asset_id: String,
    name: String,
    start: f64,
    end: Option<f64>,
) -> Result<Library, String> {
    let root = crate::root_clone(&state)?;
    let library = tauri::async_runtime::spawn_blocking(move || {
        let asset = snapshot(&root)?
            .assets
            .into_iter()
            .find(|asset| asset.id == asset_id)
            .ok_or("audio_asset_unknown")?;
        let duration = fabric_audio::decode::AudioTools::at(&root).probe(Path::new(&asset.path))?;
        fabric_audio::format::ClipRange { start, end }.resolve(duration, 48_000)?;
        add_clip(&root, &asset_id, &name, start, end)
    })
    .await
    .map_err(|e| e.to_string())??;
    notify(&app, &library);
    Ok(library)
}

#[tauri::command]
pub async fn audio_library_set_range(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    entry_id: String,
    start: f64,
    end: Option<f64>,
) -> Result<Library, String> {
    let root = crate::root_clone(&state)?;
    let library = tauri::async_runtime::spawn_blocking(move || {
        let snapshot = snapshot(&root)?;
        let entry = snapshot
            .entries
            .iter()
            .find(|entry| entry.id == entry_id)
            .ok_or("audio_entry_unknown")?;
        let asset = snapshot
            .assets
            .iter()
            .find(|asset| asset.id == entry.asset_id)
            .ok_or("audio_asset_unknown")?;
        let duration = fabric_audio::decode::AudioTools::at(&root).probe(Path::new(&asset.path))?;
        fabric_audio::format::ClipRange { start, end }.resolve(duration, 48_000)?;
        set_range(&root, &entry_id, start, end)
    })
    .await
    .map_err(|e| e.to_string())??;
    notify(&app, &library);
    Ok(library)
}

#[tauri::command]
pub fn audio_library_exclude(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    source_id: String,
    asset_id: String,
) -> Result<Library, String> {
    let library = exclude(&crate::root_clone(&state)?, &source_id, &asset_id)?;
    notify(&app, &library);
    Ok(library)
}

#[tauri::command]
pub async fn audio_library_restore(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    source_id: String,
    path: String,
) -> Result<Library, String> {
    let root = crate::root_clone(&state)?;
    let library = tauri::async_runtime::spawn_blocking(move || restore(&root, &source_id, &path))
        .await
        .map_err(|e| e.to_string())??;
    notify(&app, &library);
    Ok(library)
}

#[tauri::command]
pub fn audio_library_remove_source(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    source_id: String,
) -> Result<Library, String> {
    let library = remove_source(&crate::root_clone(&state)?, &source_id)?;
    notify(&app, &library);
    Ok(library)
}

#[tauri::command]
pub fn audio_library_grant_asset(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    asset_id: String,
) -> Result<String, String> {
    let asset = snapshot(&crate::root_clone(&state)?)?
        .assets
        .into_iter()
        .find(|asset| asset.id == asset_id)
        .ok_or("audio_asset_unknown")?;
    if !Path::new(&asset.path).is_file() {
        return Err("audio_file_missing".into());
    }
    crate::asset_scope::grant_file(&app, &asset.path);
    Ok(asset.path)
}

#[tauri::command]
pub async fn audio_library_export(
    window: tauri::WebviewWindow,
    state: State<'_, Mutex<crate::AppState>>,
    entry_id: String,
    start: f64,
    end: Option<f64>,
) -> Result<Option<String>, String> {
    let root = crate::root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        let _guard = ExportGuard::start()?;
        let library = snapshot(&root)?;
        let entry = library
            .entries
            .iter()
            .find(|entry| entry.id == entry_id)
            .ok_or("audio_entry_unknown")?;
        let asset = library
            .assets
            .iter()
            .find(|asset| asset.id == entry.asset_id)
            .ok_or("audio_asset_unknown")?;
        let suggested: String = entry
            .name
            .chars()
            .map(|ch| if "\\/:*?\"<>|".contains(ch) { '_' } else { ch })
            .collect();
        let Some(target) = crate::shell_extras::dialog_on(Some(&window))
            .add_filter("WAV", &["wav"])
            .set_title(&crate::i18n::t("audio.exportWav"))
            .set_file_name(format!("{suggested}.wav"))
            .save_file()
        else {
            return Ok(None);
        };
        crate::audio_edit::export_precise(
            &root,
            Path::new(&asset.path),
            &target,
            start,
            end,
            &EXPORT_CANCEL,
        )?;
        Ok(Some(target.to_string_lossy().into_owned()))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
pub fn audio_library_export_cancel() -> bool {
    if EXPORT_BUSY.load(Ordering::Acquire) {
        EXPORT_CANCEL.store(true, Ordering::Release);
        true
    } else {
        false
    }
}

pub fn stop_export_on_exit() {
    EXPORT_CANCEL.store(true, Ordering::Release);
    for _ in 0..40 {
        if !EXPORT_BUSY.load(Ordering::Acquire) {
            break;
        }
        std::thread::sleep(std::time::Duration::from_millis(50));
    }
}

pub fn stop_scan_on_exit() {
    SCAN_CANCEL.store(true, Ordering::Release);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            static SEQ: AtomicU64 = AtomicU64::new(0);
            let dir = std::env::temp_dir().join(format!(
                "fabric-library-{}-{}",
                std::process::id(),
                SEQ.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir_all(&dir).unwrap();
            Self(dir)
        }
        fn audio(&self, path: &str) -> PathBuf {
            let file = self.0.join(path);
            fs::create_dir_all(file.parent().unwrap()).unwrap();
            fs::write(&file, b"fixture").unwrap();
            file
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn overlapping_sources_keep_one_asset_and_stable_number() {
        let f = Fixture::new();
        let audio = f.audio("music/album/a.wav");
        let parent = f.0.join("music");
        let first = import(&f.0, &[parent], ImportMode::Reference, true).unwrap();
        let id = first.entries[0].id.clone();
        let source_id = first.sources[0].id.clone();
        set_number(&f.0, &id, Some(1200)).unwrap();
        let second = import(&f.0, &[audio], ImportMode::Reference, true).unwrap();
        assert_eq!(second.assets.len(), 1);
        assert_eq!(second.entries.len(), 1);
        assert_eq!(second.assets[0].source_ids.len(), 2);
        assert_eq!(second.entries[0].number, Some(1200));
        let after = remove_source(&f.0, &source_id).unwrap();
        assert_eq!(after.entries[0].id, id);
        assert_eq!(after.entries[0].number, Some(1200));
    }

    #[test]
    fn duplicate_number_is_rejected_without_changing_state() {
        let f = Fixture::new();
        let a = f.audio("a.wav");
        let b = f.audio("b.wav");
        let st = import(&f.0, &[a, b], ImportMode::Reference, true).unwrap();
        set_number(&f.0, &st.entries[0].id, Some(999_999)).unwrap();
        assert!(set_number(&f.0, &st.entries[1].id, Some(999_999)).is_err());
        assert_eq!(snapshot(&f.0).unwrap().entries[1].number, None);
    }

    #[test]
    fn corrupt_state_is_preserved() {
        let f = Fixture::new();
        let path = store_path(&f.0);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, b"{broken").unwrap();
        assert!(import(&f.0, &[f.audio("a.wav")], ImportMode::Reference, true).is_err());
        assert_eq!(fs::read(path).unwrap(), b"{broken");
    }

    #[test]
    fn copying_keeps_original_and_uses_managed_media() {
        let f = Fixture::new();
        let original = f.audio("song.wav");
        let st = import(&f.0, &[original.clone()], ImportMode::Copy, true).unwrap();
        assert_ne!(st.assets[0].path, original.to_string_lossy());
        assert!(Path::new(&st.assets[0].path).is_file());
        assert_eq!(fs::read(original).unwrap(), b"fixture");
    }

    #[test]
    fn exclusion_survives_refresh_and_restores_identity() {
        let f = Fixture::new();
        let file = f.audio("folder/a.wav");
        let imported = import(&f.0, &[f.0.join("folder")], ImportMode::Reference, true).unwrap();
        let source_id = &imported.sources[0].id;
        let asset_id = &imported.assets[0].id;
        let entry_id = &imported.entries[0].id;
        set_number(&f.0, entry_id, Some(36)).unwrap();
        let excluded = exclude(&f.0, source_id, asset_id).unwrap();
        assert_eq!(excluded.entries[0].id, *entry_id);
        assert_eq!(
            refresh(&f.0, source_id).unwrap().entries[0].number,
            Some(36)
        );
        let restored = restore(&f.0, source_id, file.to_str().unwrap()).unwrap();
        assert_eq!(restored.entries.len(), 1);
        assert_eq!(restored.entries[0].id, *entry_id);
        assert_eq!(restored.entries[0].number, Some(36));
    }

    #[test]
    fn refresh_keeps_missing_entry_and_number_while_adding_new_files() {
        let f = Fixture::new();
        let old = f.audio("folder/old.wav");
        let initial = import(&f.0, &[f.0.join("folder")], ImportMode::Reference, true).unwrap();
        let entry_id = initial.entries[0].id.clone();
        set_number(&f.0, &entry_id, Some(10_000)).unwrap();
        fs::remove_file(old).unwrap();
        f.audio("folder/new.wav");
        let updated = refresh(&f.0, &initial.sources[0].id).unwrap();
        assert_eq!(updated.entries.len(), 2);
        let old_entry = updated
            .entries
            .iter()
            .find(|entry| entry.id == entry_id)
            .unwrap();
        assert_eq!(old_entry.number, Some(10_000));
        let old_asset = updated
            .assets
            .iter()
            .find(|asset| asset.id == old_entry.asset_id)
            .unwrap();
        assert!(!old_asset.available);
        assert!(updated.entries.iter().any(|entry| entry.name == "new"));
    }

    #[test]
    fn offline_source_keeps_entry_and_marks_it_unavailable() {
        let f = Fixture::new();
        f.audio("folder/song.wav");
        let original = import(&f.0, &[f.0.join("folder")], ImportMode::Reference, true).unwrap();
        set_number(&f.0, &original.entries[0].id, Some(20001)).unwrap();
        fs::rename(f.0.join("folder"), f.0.join("offline")).unwrap();
        let updated = refresh(&f.0, &original.sources[0].id).unwrap();
        assert_eq!(updated.entries[0].id, original.entries[0].id);
        assert_eq!(updated.entries[0].number, Some(20001));
        assert!(!updated.assets[0].available);
    }

    #[test]
    fn reference_refresh_does_not_mask_missing_managed_copy() {
        let f = Fixture::new();
        let original = f.audio("song.wav");
        let copied = import(&f.0, &[original.clone()], ImportMode::Copy, true).unwrap();
        let managed = copied.assets[0].path.clone();
        let both = import(&f.0, &[f.0.clone()], ImportMode::Reference, true).unwrap();
        assert_eq!(both.assets.len(), 1);
        fs::remove_file(managed).unwrap();
        let updated = refresh(&f.0, &both.sources[1].id).unwrap();
        assert!(!updated.assets[0].available);
    }

    #[test]
    fn relocating_offline_directory_preserves_identity_number_and_exclusions() {
        let f = Fixture::new();
        f.audio("old/song.wav");
        let excluded = f.audio("old/excluded.wav");
        let first = import(&f.0, &[f.0.join("old")], ImportMode::Reference, true).unwrap();
        let source_id = first.sources[0].id.clone();
        let song = first
            .entries
            .iter()
            .find(|entry| entry.name == "song")
            .unwrap();
        let entry_id = song.id.clone();
        let asset_id = song.asset_id.clone();
        let excluded_asset = first
            .assets
            .iter()
            .find(|asset| asset.origin == excluded.canonicalize().unwrap().to_string_lossy())
            .unwrap();
        exclude(&f.0, &source_id, &excluded_asset.id).unwrap();
        set_number(&f.0, &entry_id, Some(12345)).unwrap();
        fs::rename(f.0.join("old"), f.0.join("new")).unwrap();
        f.audio("new/fresh.wav");
        let moved = relink_source(&f.0, &source_id, &f.0.join("new")).unwrap();
        let song_after = moved
            .entries
            .iter()
            .find(|entry| entry.id == entry_id)
            .unwrap();
        let asset_after = moved
            .assets
            .iter()
            .find(|asset| asset.id == asset_id)
            .unwrap();
        assert_eq!(song_after.number, Some(12345));
        assert!(asset_after.available);
        assert!(asset_after.origin.ends_with("new/song.wav"));
        assert!(moved.sources[0]
            .excludes
            .iter()
            .any(|key| key.ends_with("new/excluded.wav")));
        assert_eq!(moved.entries.len(), first.entries.len() + 1);
        assert_eq!(
            refresh(&f.0, &source_id).unwrap().entries.len(),
            moved.entries.len()
        );
    }

    #[test]
    fn relocating_file_source_keeps_entry_and_rejects_collision() {
        let f = Fixture::new();
        let old = f.audio("old.wav");
        let other = f.audio("other.wav");
        let first = import(
            &f.0,
            &[old.clone(), other.clone()],
            ImportMode::Reference,
            true,
        )
        .unwrap();
        let original = first.entries[0].id.clone();
        set_number(&f.0, &original, Some(777)).unwrap();
        assert!(relink_source(&f.0, &first.sources[0].id, &other).is_err());
        assert_eq!(snapshot(&f.0).unwrap().entries[0].number, Some(777));
        let replacement = f.audio("moved.wav");
        fs::remove_file(old).unwrap();
        let after = relink_source(&f.0, &first.sources[0].id, &replacement).unwrap();
        assert_eq!(after.entries[0].id, original);
        assert_eq!(after.entries[0].number, Some(777));
        assert_eq!(
            after.sources[0].path,
            replacement.canonicalize().unwrap().to_string_lossy()
        );
    }

    #[test]
    fn relocating_single_missing_asset_inside_source_keeps_number() {
        let f = Fixture::new();
        let old = f.audio("folder/old.wav");
        let first = import(&f.0, &[f.0.join("folder")], ImportMode::Reference, false).unwrap();
        set_number(&f.0, &first.entries[0].id, Some(98)).unwrap();
        let next = f.0.join("folder/new.wav");
        fs::rename(old, &next).unwrap();
        refresh(&f.0, &first.sources[0].id).unwrap();
        assert_eq!(
            relink_asset(&f.0, &first.assets[0].id, &next, false)
                .err()
                .as_deref(),
            Some("audio_relink_duplicate_target")
        );
        let after = relink_asset(&f.0, &first.assets[0].id, &next, true).unwrap();
        assert_eq!(after.entries.len(), 1);
        assert_eq!(after.entries[0].id, first.entries[0].id);
        assert_eq!(after.entries[0].number, Some(98));
        assert!(after.assets[0].available);
        assert_eq!(
            after.assets[0].path,
            next.canonicalize().unwrap().to_string_lossy()
        );
    }

    #[test]
    fn cancelling_scan_leaves_library_unchanged() {
        let f = Fixture::new();
        let file = f.audio("file.wav");
        let cancel = AtomicBool::new(true);
        let result =
            import_with_progress(&f.0, &[file], ImportMode::Copy, true, &cancel, &mut |_| {});
        assert_eq!(result.err().as_deref(), Some("audio_scan_cancelled"));
        assert!(snapshot(&f.0).unwrap().entries.is_empty());
    }

    #[test]
    fn relocating_shared_asset_is_rejected_without_mutation() {
        let f = Fixture::new();
        let file = f.audio("old/song.wav");
        let first = import(&f.0, &[f.0.join("old"), file], ImportMode::Reference, true).unwrap();
        let revision = first.revision;
        f.audio("new/song.wav");
        assert_eq!(
            relink_source(&f.0, &first.sources[0].id, &f.0.join("new"))
                .err()
                .as_deref(),
            Some("audio_relink_shared_asset")
        );
        assert_eq!(snapshot(&f.0).unwrap().revision, revision);
    }
}
