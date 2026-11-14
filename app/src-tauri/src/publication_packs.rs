use serde::Serialize;
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use tauri::State;

use crate::{download, root_clone, shell_extras, voices, AppState};

#[derive(Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
struct Pack {
    name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    result: Option<PackDetails>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

#[derive(Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
struct PackDetails {
    sha256: String,
    size_bytes: u64,
    metadata: Value,
}

fn details(root: &Path, path: &Path, exported: Option<&Path>) -> Result<PackDetails, String> {
    let config = pack_metadata(root, path, exported)?;
    let size_bytes = fs::metadata(path).map_err(|e| e.to_string())?.len();
    let sha256 = download::file_sha256(path)?;
    let mut metadata = serde_json::Map::new();
    for key in ["name", "author", "author_url", "description", "version", "series", "group", "club", "language", "lang", "license"] {
        if let Some(text) = config[key].as_str().filter(|text| text.len() <= 20_000) {
            metadata.insert(key.into(), Value::String(text.into()));
        }
    }
    Ok(PackDetails { sha256, size_bytes, metadata: Value::Object(metadata) })
}

fn record(name: String, result: Result<PackDetails, String>) -> Pack {
    match result {
        Ok(result) => Pack { name, result: Some(result), error: None },
        Err(error) => Pack { name, result: None, error: Some(error) },
    }
}

#[tauri::command]
pub(crate) async fn publication_read_packs(
    window: tauri::WebviewWindow, state: State<'_, Mutex<AppState>>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let files = shell_extras::dialog_on(Some(&window)).add_filter("ZIP", &["zip"]).pick_files().unwrap_or_default();
    tauri::async_runtime::spawn_blocking(move || {
        let records: Vec<_> = files.iter().map(|file| {
            let name = file.file_name().unwrap_or_default().to_string_lossy().into_owned();
            record(name, details(&root, file, None))
        }).collect();
        serde_json::to_value(records).map_err(|e| e.to_string())
    }).await.map_err(|e| e.to_string())?
}

#[tauri::command]
pub(crate) async fn publication_read_manifest(window: tauri::WebviewWindow) -> Result<Value, String> {
    let Some(path) = shell_extras::dialog_on(Some(&window)).add_filter("JSON", &["json"]).pick_file() else {
        return Ok(Value::Null);
    };
    tauri::async_runtime::spawn_blocking(move || {
        use std::io::Read;
        let mut bytes = Vec::new();
        fs::File::open(path).map_err(|e| e.to_string())?.take(2_000_001).read_to_end(&mut bytes).map_err(|e| e.to_string())?;
        if bytes.len() > 2_000_000 { return Err("Export list is too large.".into()); }
        let value: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
        let records = if let Some(entries) = value.as_object() {
            entries.iter().filter_map(|(name, entry)| {
                let sha256 = entry["sha256"].as_str()?.to_string();
                let size_bytes = entry["size"].as_u64().or_else(|| entry["sizeBytes"].as_u64()).or_else(|| entry["size_bytes"].as_u64()).unwrap_or(0);
                Some(record(name.clone(), Ok(PackDetails { sha256, size_bytes, metadata: entry.clone() })))
            }).collect()
        } else {
            serde_json::from_value::<Vec<Pack>>(value).map_err(|e| e.to_string())?
        };
        serde_json::to_value(records).map_err(|e| e.to_string())
    }).await.map_err(|e| e.to_string())?
}

#[tauri::command]
pub(crate) async fn publication_export_packs(
    window: tauri::WebviewWindow, state: State<'_, Mutex<AppState>>, dirs: Vec<String>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    if dirs.is_empty() {
        return Ok(Value::Null);
    }
    let Some(dest) = shell_extras::dialog_on(Some(&window)).pick_folder() else {
        return Ok(Value::Null);
    };
    tauri::async_runtime::spawn_blocking(move || export(&root, &dest, dirs))
        .await.map_err(|e| e.to_string())?
}

fn export(root: &Path, dest: &Path, dirs: Vec<String>) -> Result<Value, String> {
    let output = dest.join(format!("voice-packs-{}", chrono::Utc::now().timestamp_nanos_opt().unwrap_or_default()));
    fs::create_dir(&output).map_err(|e| e.to_string())?;
    let mut records = Vec::new();
    for (index, dir) in dirs.into_iter().enumerate() {
        let base = Path::new(&dir).file_name().unwrap_or_default().to_string_lossy();
        let name = format!("{:03}-{base}.zip", index + 1);
        let file = output.join(&name);
        let result = voices::export_model(root, &dir, &file).and_then(|_| details(root, &file, Some(Path::new(&dir))));
        if result.is_err() {
            let _ = fs::remove_file(&file);
        }
        records.push(record(name, result));
    }
    let manifest = write_manifest(output.join("pack-checksums.json"), &records)?;
    Ok(serde_json::json!({ "folder": output, "manifest": manifest, "packs": records }))
}

fn write_manifest(path: PathBuf, packs: &[Pack]) -> Result<PathBuf, String> {
    let rows: Vec<_> = packs.iter().filter(|pack| pack.result.is_some()).collect();
    let data = serde_json::to_vec_pretty(&rows).map_err(|e| e.to_string())?;
    fs::write(&path, data).map_err(|e| e.to_string())?;
    Ok(path)
}

fn pack_metadata(root: &Path, path: &Path, exported: Option<&Path>) -> Result<Value, String> {
    use std::io::Read;
    let file = fs::File::open(path).map_err(|e| e.to_string())?;
    let mut zip = zip::ZipArchive::new(file).map_err(|e| e.to_string())?;
    let mut weights = Vec::new();
    for index in 0..zip.len() {
        let entry = zip.by_index_raw(index).map_err(|e| e.to_string())?;
        if entry.enclosed_name().is_none() {
            return Err("Invalid package path.".into());
        }
        if !entry.is_dir() && entry.name().to_ascii_lowercase().ends_with(".pth") {
            weights.push((index, entry.name().to_string()));
        }
    }
    let [(weight_index, weight)] = weights.as_slice() else {
        return Err("An RVC voice package needs one weight.".into());
    };
    let adjacent = weight.rsplit_once('/').map(|(folder, _)| format!("{folder}/config.json"));
    let config_path = if zip.index_for_name("config.json").is_some() {
        "config.json"
    } else {
        adjacent.as_deref().unwrap_or("config.json")
    };
    let mut config: serde_json::Map<String, Value> = if let Ok(entry) = zip.by_name(config_path) {
        let mut bytes = Vec::new();
        entry.take(1024 * 1024 + 1).read_to_end(&mut bytes).map_err(|e| e.to_string())?;
        if bytes.len() > 1024 * 1024 { return Err("Package metadata is too large.".into()); }
        serde_json::from_slice(&bytes).map_err(|e| e.to_string())?
    } else {
        serde_json::Map::new()
    };
    let installed = exported.map(Path::to_path_buf).or_else(|| {
        let id = config.get("voice_id").or_else(|| config.get("id")).and_then(Value::as_str)
            .or_else(|| path.file_stem().and_then(|name| name.to_str()))?;
        let dir = crate::paths::models_dir(root).join(voices::safe_model_dir_name(id).ok()?);
        let local_weight = voices::find_pth(&dir)?;
        let archived_weight = zip.by_index(*weight_index).ok()?;
        same_weight(archived_weight, &local_weight).then_some(dir)
    });
    if let Some(dir) = installed {
        for (key, value) in voices::read_sidecar(&dir) {
            let missing = config.get(&key).is_none_or(|current|
                current.is_null() || current.as_str().is_some_and(|string| string.trim().is_empty()));
            if missing { config.insert(key, value); }
        }
    }
    Ok(Value::Object(config))
}

fn same_weight(entry: zip::read::ZipFile<'_>, installed: &Path) -> bool {
    use sha2::{Digest, Sha256};
    use std::io::Read;
    let size = entry.size();
    if size == 0 || !fs::metadata(installed).is_ok_and(|file| file.is_file() && file.len() == size) {
        return false;
    }
    let Ok(local_hash) = download::file_sha256(installed) else { return false; };
    let mut hasher = Sha256::new();
    std::io::copy(&mut entry.take(size.saturating_add(1)), &mut hasher).is_ok_and(|bytes| bytes == size)
        && hex::encode(hasher.finalize()) == local_hash
}
