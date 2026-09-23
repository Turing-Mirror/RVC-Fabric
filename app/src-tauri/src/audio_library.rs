//! Persistent audio sources and entries. This layer never starts the RVC Runtime.
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, Ordering};
use std::{
    collections::{HashMap, HashSet},
    fs,
    io::Write,
    path::{Path, PathBuf},
    sync::Mutex,
};
use tauri::{AppHandle, Emitter, State};

use crate::paths;

const SCHEMA_VERSION: u32 = 1;
static WRITE_LOCK: Mutex<()> = Mutex::new(());
static EXPORT_BUSY: AtomicBool = AtomicBool::new(false);
static EXPORT_CANCEL: AtomicBool = AtomicBool::new(false);

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

fn collect(root: &Path, path: &Path, recursive: bool) -> Result<Vec<PathBuf>, String> {
    let canonical_root = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let user_data = paths::user_data(&canonical_root);
    let skipped = [user_data.join("audio"), user_data.join("audio_clips")];
    if skipped.iter().any(|directory| path.starts_with(directory)) {
        return Err("audio_source_managed".into());
    }
    if path.is_file() {
        return if audio_file(path) {
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
        for item in fs::read_dir(dir).map_err(|e| e.to_string())? {
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
) -> Result<bool, String> {
    let mut changed = false;
    let mut by_origin: HashMap<String, usize> = library
        .assets
        .iter()
        .enumerate()
        .map(|(index, asset)| (stored_key(&asset.origin), index))
        .collect();
    for file in files {
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
                let copy = copy_to_library(root, &asset.id, &origin)?;
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
            let copy = copy_to_library(root, &id, &origin)?;
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

fn copy_to_library(root: &Path, id: &str, source: &Path) -> Result<PathBuf, String> {
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
    if let Err(e) = std::io::copy(&mut input, &mut output).and_then(|_| output.sync_all()) {
        let _ = fs::remove_file(&temp);
        return Err(e.to_string());
    }
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

pub fn import(
    root: &Path,
    paths: &[PathBuf],
    mode: ImportMode,
    recursive: bool,
) -> Result<Library, String> {
    if paths.is_empty() {
        return snapshot(root);
    }
    // Scan outside the mutation lock. A slow or offline directory cannot block numbering edits.
    let scans: Result<Vec<_>, String> = paths
        .iter()
        .map(|path| {
            let canonical = fs::canonicalize(path).map_err(|e| e.to_string())?;
            let kind = if canonical.is_dir() {
                SourceKind::Directory
            } else {
                SourceKind::File
            };
            let files = collect(root, &canonical, recursive)?;
            Ok((canonical, kind, files))
        })
        .collect();
    let scans = scans?;
    let mut created_copies = Vec::new();
    let result = mutate(root, |library| {
        let mut changed = false;
        for (path, kind, files) in &scans {
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
            changed |= attach_files(root, library, &source, files, &mut created_copies)?;
        }
        Ok(changed)
    });
    if result.is_err() {
        for copy in created_copies {
            let _ = fs::remove_file(copy);
        }
    }
    result
}

pub fn refresh(root: &Path, source_id: &str) -> Result<Library, String> {
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
    let files = match collect(root, Path::new(&source.path), source.recursive) {
        Ok(files) => files,
        Err(error) if error == "audio_source_missing" => Vec::new(),
        Err(error) => return Err(error),
    };
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
        changed |= attach_files(root, library, &current, &files, &mut Vec::new())?;
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
    mutate(root, |library| {
        if !library.assets.iter().any(|asset| asset.id == asset_id) {
            return Err("audio_asset_unknown".into());
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
    mutate(root, |library| {
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
    let library = tauri::async_runtime::spawn_blocking(move || {
        let paths: Vec<PathBuf> = paths.into_iter().map(PathBuf::from).collect();
        import(
            &root,
            &paths,
            if copy {
                ImportMode::Copy
            } else {
                ImportMode::Reference
            },
            recursive,
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
    let library = tauri::async_runtime::spawn_blocking(move || refresh(&root, &source_id))
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
}
