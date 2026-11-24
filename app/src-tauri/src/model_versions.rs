//! Installed voice weights and the inference snapshots of their exact experiment.
use std::collections::HashMap;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};

use regex::Regex;
use serde::Serialize;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

#[derive(Debug, Clone, Serialize)]
pub struct Version {
    file: String,
    epoch: Option<u64>,
    step: Option<u64>,
    is_final: bool,
    current: bool,
}

#[derive(Debug, Serialize)]
struct Current {
    state: &'static str,
    file: Option<String>,
    epoch: Option<u64>,
    step: Option<u64>,
}

#[derive(Debug, Serialize)]
struct WeightVersions {
    kind: &'static str,
    current: Current,
    versions: Vec<Version>,
}

#[derive(Debug, Serialize)]
pub struct ModelVersions {
    experiment: Option<String>,
    weights_dir: Option<String>,
    weights: Vec<WeightVersions>,
}

pub(crate) struct Source {
    pub experiment: String,
    pub weights_dir: PathBuf,
}

pub(crate) fn training_source(
    root: &Path,
    dir: &Path,
    side: &Map<String, Value>,
) -> Option<Source> {
    let experiment = side
        .get("training")
        .and_then(|t| t["experiment"].as_str())
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .or_else(|| dir.file_name()?.to_str().map(str::to_owned))?;
    let weights_dir = side
        .get("training")
        .and_then(|t| t["weights_dir"].as_str())
        .filter(|p| Path::new(p).is_absolute())
        .map(PathBuf::from)
        .unwrap_or_else(|| crate::paths::engine_weights(root));
    Some(Source {
        experiment,
        weights_dir,
    })
}

fn resolve_target(root: &Path, target: &str) -> Result<PathBuf, String> {
    let dir = Path::new(target);
    crate::voices::guard_model_dir(root, dir)
        .map_err(|_| crate::i18n::t("modelVersions.invalidTarget"))?;
    let dir = dir.canonicalize().map_err(install_error)?;
    let mut roots = vec![crate::paths::models_dir(root)];
    let extra = crate::config::train_output_dir(root);
    if !extra.is_empty() {
        roots.push(PathBuf::from(extra));
    }
    let managed = roots
        .iter()
        .filter_map(|p| p.canonicalize().ok())
        .any(|base| dir.parent() == Some(base.as_path()));
    if !managed
        || dir
            .file_name()
            .is_none_or(|s| s.to_string_lossy().starts_with('.'))
    {
        return Err(crate::i18n::t("modelVersions.invalidTarget"));
    }
    Ok(dir)
}

fn snapshots(source: &Source, side: &Map<String, Value>) -> Vec<Version> {
    let pattern = Regex::new(&format!(
        r"^{}_e([0-9]+)_s([0-9]+)\.pth$",
        regex::escape(&source.experiment)
    ))
    .unwrap();
    let final_name = format!("{}.pth", source.experiment);
    let mut versions = Vec::new();
    for entry in fs::read_dir(&source.weights_dir)
        .into_iter()
        .flatten()
        .flatten()
    {
        if !entry.path().is_file() {
            continue;
        }
        let file = entry.file_name().to_string_lossy().into_owned();
        if file == final_name {
            versions.push(Version {
                file,
                epoch: side
                    .get("training")
                    .and_then(|t| t["final"]["rvc"]["epoch"].as_u64()),
                step: None,
                is_final: true,
                current: false,
            });
        } else if let Some(captures) = pattern.captures(&file) {
            if let (Ok(epoch), Ok(step)) = (captures[1].parse(), captures[2].parse()) {
                versions.push(Version {
                    file,
                    epoch: Some(epoch),
                    step: Some(step),
                    is_final: false,
                    current: false,
                });
            }
        }
    }
    versions.sort_by_key(|v| {
        (
            v.epoch.unwrap_or(u64::MAX),
            v.step.unwrap_or(u64::MAX),
            v.file.clone(),
        )
    });
    versions
}

type HashKey = (PathBuf, u64, SystemTime);
static HASHES: OnceLock<Mutex<HashMap<HashKey, String>>> = OnceLock::new();

fn digest(path: &Path) -> Result<String, String> {
    let mut file = fs::File::open(path).map_err(install_error)?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let count = file.read(&mut buffer).map_err(install_error)?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
    }
    Ok(hex::encode(hash.finalize()))
}

fn cached_digest(path: &Path, metadata: &fs::Metadata) -> Result<String, String> {
    let key = (
        path.to_path_buf(),
        metadata.len(),
        metadata.modified().map_err(install_error)?,
    );
    let cache = HASHES.get_or_init(|| Mutex::new(HashMap::new()));
    if let Some(value) = cache
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .get(&key)
        .cloned()
    {
        return Ok(value);
    }
    let value = digest(path)?;
    cache
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .insert(key, value.clone());
    Ok(value)
}

/// The last epoch snapshot and `<exp>.pth` usually hold the same weights.
/// List them once: keep the snapshot row and mark it final.
fn merge_final_into_snapshot(weights_dir: &Path, versions: &mut Vec<Version>) -> Result<(), String> {
    let Some(final_index) = versions.iter().position(|v| v.is_final) else {
        return Ok(());
    };
    let final_path = weights_dir.join(&versions[final_index].file);
    let final_meta = fs::metadata(&final_path).map_err(install_error)?;
    for index in 0..versions.len() {
        if index == final_index {
            continue;
        }
        let path = weights_dir.join(&versions[index].file);
        let meta = fs::metadata(&path).map_err(install_error)?;
        if meta.len() == final_meta.len()
            && cached_digest(&path, &meta)? == cached_digest(&final_path, &final_meta)?
        {
            versions[index].is_final = true;
            versions.remove(final_index);
            return Ok(());
        }
    }
    Ok(())
}

fn inspect(root: &Path, dir: &Path) -> Result<ModelVersions, String> {
    let side = crate::voices::read_sidecar(dir);
    let source = training_source(root, dir, &side);
    let mut versions = source
        .as_ref()
        .map(|s| snapshots(s, &side))
        .unwrap_or_default();
    if let Some(source) = &source {
        merge_final_into_snapshot(&source.weights_dir, &mut versions)?;
    }
    let mut current = Current {
        state: "missing",
        file: None,
        epoch: None,
        step: None,
    };
    if let Some(installed) = crate::voices::find_pth(dir).filter(|p| p.is_file()) {
        current.state = "external";
        let metadata = fs::metadata(&installed).map_err(install_error)?;
        let selected = side.get("training").map(|t| &t["selected"]["rvc"]);
        // A selected candidate wins ties when final and snapshot contain the same weights.
        let selected_file = selected.and_then(|s| s["file"].as_str());
        let mut order: Vec<usize> = (0..versions.len()).collect();
        order.sort_by_key(|i| Some(versions[*i].file.as_str()) != selected_file);
        if let Some(source) = &source {
            for index in order {
                let candidate = source.weights_dir.join(&versions[index].file);
                let candidate_meta = fs::metadata(&candidate).map_err(install_error)?;
                if metadata.len() == candidate_meta.len()
                    && cached_digest(&installed, &metadata)?
                        == cached_digest(&candidate, &candidate_meta)?
                {
                    let version = &mut versions[index];
                    version.current = true;
                    current = Current {
                        state: "matched",
                        file: Some(version.file.clone()),
                        epoch: version.epoch,
                        step: version.step,
                    };
                    break;
                }
            }
            if current.state == "external" {
                if let Some(file) = selected_file.filter(|f| Path::new(f).components().count() == 1)
                {
                    if !source.weights_dir.join(file).is_file() {
                        current = Current {
                            state: "source_removed",
                            file: Some(file.to_owned()),
                            epoch: selected.and_then(|s| s["epoch"].as_u64()),
                            step: selected.and_then(|s| s["step"].as_u64()),
                        };
                    }
                }
            }
        }
    }
    Ok(ModelVersions {
        experiment: source.as_ref().map(|s| s.experiment.clone()),
        weights_dir: source.map(|s| s.weights_dir.to_string_lossy().into_owned()),
        weights: vec![WeightVersions {
            kind: "rvc",
            current,
            versions,
        }],
    })
}

pub fn list(root: &Path, target: &str) -> Result<ModelVersions, String> {
    inspect(root, &resolve_target(root, target)?)
}

fn install_error(error: impl std::fmt::Display) -> String {
    format!("{} {error}", crate::i18n::t("modelVersions.installFailed"))
}

fn selected_voice(root: &Path, installed: &Path) -> bool {
    let config = crate::config::read(root);
    ["last_model_path", "pth_path"].iter().any(|key| {
        config
            .get(*key)
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
            .and_then(|s| Path::new(s).canonicalize().ok())
            .as_deref()
            == installed.canonicalize().ok().as_deref()
    })
}

pub fn apply(root: &Path, target: &str, kind: &str, file: &str) -> Result<ModelVersions, String> {
    apply_with(root, target, kind, file, |installed| {
        if selected_voice(root, installed) {
            crate::worker::invalidate_model_cache(root)?;
        }
        crate::sts::release_resident();
        Ok(())
    })
}

fn apply_with(
    root: &Path,
    target: &str,
    kind: &str,
    file: &str,
    invalidate: impl FnOnce(&Path) -> Result<(), String>,
) -> Result<ModelVersions, String> {
    let _admission = crate::train::model_version_guard(root)?;
    let dir = resolve_target(root, target)?;
    let mut side = crate::voices::read_sidecar(&dir);
    let source = training_source(root, &dir, &side)
        .ok_or_else(|| crate::i18n::t("modelVersions.invalidVersion"))?;
    let mut candidates = snapshots(&source, &side);
    merge_final_into_snapshot(&source.weights_dir, &mut candidates)?;
    let version = candidates
        .into_iter()
        .find(|v| kind == "rvc" && v.file == file)
        .ok_or_else(|| crate::i18n::t("modelVersions.invalidVersion"))?;
    let installed = crate::voices::find_pth(&dir)
        .filter(|p| p.is_file())
        .unwrap_or_else(|| dir.join(format!("{}.pth", source.experiment)));
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let staged = dir.join(format!(".epoch-{nonce}.tmp"));
    let backup = dir.join(format!(".epoch-{nonce}.bak"));
    let old_config = fs::read(dir.join("config.json")).ok();
    let had_old = installed.is_file();
    let mut replaced = false;
    let mut config_written = false;
    let result = (|| {
        let candidate = source.weights_dir.join(file);
        let size = fs::metadata(&candidate).map_err(install_error)?.len();
        let copied = fs::copy(&candidate, &staged).map_err(install_error)?;
        if size == 0
            || copied != size
            || fs::metadata(&staged).map_err(install_error)?.len() != size
        {
            return Err(crate::i18n::t("modelVersions.installFailed"));
        }
        let sha256 = digest(&staged)?;
        if had_old {
            fs::rename(&installed, &backup).map_err(install_error)?;
        }
        if let Err(error) = fs::rename(&staged, &installed) {
            if had_old {
                fs::rename(&backup, &installed).map_err(install_error)?;
            }
            return Err(install_error(error));
        }
        replaced = true;
        let training = side.entry("training").or_insert_with(|| json!({}));
        if !training.is_object() {
            *training = json!({});
        }
        training["experiment"] = json!(source.experiment);
        training["weights_dir"] = json!(source.weights_dir);
        if !training["selected"].is_object() {
            training["selected"] = json!({});
        }
        training["selected"]["rvc"] =
            json!({"file": file, "epoch": version.epoch, "step": version.step, "sha256": sha256});
        crate::voices::write_sidecar(&dir, &side)?;
        config_written = true;
        if let Some(cache) = HASHES.get() {
            cache
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .retain(|(path, _, _), _| path != &installed);
        }
        invalidate(&installed)?;
        inspect(root, &dir)
    })();
    let _ = fs::remove_file(&staged);
    if let Err(error) = &result {
        if replaced {
            fs::remove_file(&installed).map_err(install_error)?;
            if had_old {
                fs::rename(&backup, &installed).map_err(install_error)?;
            }
        }
        if config_written {
            match old_config {
                Some(bytes) => {
                    fs::write(&staged, bytes).map_err(install_error)?;
                    fs::rename(&staged, dir.join("config.json")).map_err(install_error)?;
                }
                None => fs::remove_file(dir.join("config.json")).map_err(install_error)?,
            }
        }
        return Err(error.clone());
    }
    let _ = fs::remove_file(backup);
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(experiment: &str) -> (PathBuf, PathBuf) {
        let root = crate::testutil::scratch("epoch-versions");
        let dir = crate::paths::models_dir(&root).join("voice");
        fs::create_dir_all(dir.join("profiles")).unwrap();
        let weights = crate::paths::engine_weights(&root);
        fs::create_dir_all(&weights).unwrap();
        fs::write(dir.join("voice.pth"), b"final").unwrap();
        fs::write(dir.join("keep.index"), b"index").unwrap();
        fs::write(dir.join("profiles/soft.tmvp"), b"preset").unwrap();
        fs::write(weights.join(format!("{experiment}.pth")), b"final").unwrap();
        fs::write(weights.join(format!("{experiment}_e2_s40.pth")), b"early").unwrap();
        fs::write(
            weights.join(format!("{experiment}_e10_s200.pth")),
            b"middle",
        )
        .unwrap();
        let side = json!({"name":"Voice", "author":"Author", "pitch":-2, "index":"keep.index", "active_profile":"soft",
            "training":{"experiment":experiment,"weights_dir":weights,"final":{"rvc":{"file":format!("{experiment}.pth"),"epoch":20,"step":null}}}});
        crate::voices::write_sidecar(&dir, side.as_object().unwrap()).unwrap();
        (root, dir)
    }

    #[test]
    fn exact_experiment_names_and_numeric_order() {
        let (root, dir) = fixture("voice.+[test]");
        let weights = crate::paths::engine_weights(&root);
        for name in [
            "voiceZZtest_e3_s60.pth",
            "voice.+[test]2_e4_s80.pth",
            "voice.+[test]_e3_s60_l4.pth",
            "G_40.pth",
            "D_40.pth",
            "voice.+[test]_e4_s80.pth.bak",
        ] {
            fs::write(weights.join(name), b"ignored").unwrap();
        }
        let result = list(&root, dir.to_str().unwrap()).unwrap();
        assert_eq!(
            result.weights[0]
                .versions
                .iter()
                .map(|v| v.epoch)
                .collect::<Vec<_>>(),
            vec![Some(2), Some(10), Some(20)]
        );
        assert!(result.weights[0].versions[2].is_final);
        assert_eq!(result.weights[0].current.state, "matched");
    }

    #[test]
    fn final_weights_equal_to_the_last_snapshot_are_listed_once() {
        let (root, dir) = fixture("voice");
        let weights = crate::paths::engine_weights(&root);
        fs::write(weights.join("voice_e20_s400.pth"), b"final").unwrap();
        let result = list(&root, dir.to_str().unwrap()).unwrap();
        let rows = &result.weights[0].versions;
        assert_eq!(rows.iter().map(|v| v.file.as_str()).collect::<Vec<_>>(),
            vec!["voice_e2_s40.pth", "voice_e10_s200.pth", "voice_e20_s400.pth"]);
        assert!(rows[2].is_final && rows[2].current);
        assert_eq!(result.weights[0].current.state, "matched");
    }

    #[test]
    fn legacy_voice_uses_exact_directory_name_and_unknown_final_epoch() {
        let (root, dir) = fixture("voice");
        crate::voices::write_sidecar(&dir, &Map::new()).unwrap();
        let result = list(&root, dir.to_str().unwrap()).unwrap();
        assert_eq!(result.experiment.as_deref(), Some("voice"));
        assert_eq!(result.weights[0].versions.last().unwrap().epoch, None);
        assert_eq!(result.weights[0].current.state, "matched");
    }

    #[test]
    fn current_state_uses_content_and_tracks_removed_source_and_missing_installation() {
        let (root, dir) = fixture("voice");
        fs::write(dir.join("voice.pth"), b"other").unwrap(); // same size as final
        assert_eq!(
            list(&root, dir.to_str().unwrap()).unwrap().weights[0]
                .current
                .state,
            "external"
        );
        apply(&root, dir.to_str().unwrap(), "rvc", "voice_e2_s40.pth").unwrap();
        let result = list(&root, dir.to_str().unwrap()).unwrap();
        assert_eq!(
            result.weights[0].current.file.as_deref(),
            Some("voice_e2_s40.pth")
        );
        fs::remove_file(crate::paths::engine_weights(&root).join("voice_e2_s40.pth")).unwrap();
        let result = list(&root, dir.to_str().unwrap()).unwrap();
        assert_eq!(result.weights[0].current.state, "source_removed");
        assert_eq!(result.weights[0].current.epoch, Some(2));
        fs::remove_file(dir.join("voice.pth")).unwrap();
        assert_eq!(
            list(&root, dir.to_str().unwrap()).unwrap().weights[0]
                .current
                .state,
            "missing"
        );
    }

    #[test]
    fn rejects_non_candidates_foreign_targets_and_nested_directories() {
        let (root, dir) = fixture("voice");
        let nested = dir.join("profiles");
        for target in [
            &root,
            &crate::paths::models_dir(&root),
            &nested,
            &root.join("assets/weights"),
        ] {
            assert!(list(&root, target.to_str().unwrap()).is_err());
            assert!(apply(&root, target.to_str().unwrap(), "rvc", "voice.pth").is_err());
        }
        for file in [
            "../voice.pth",
            "G_40.pth",
            "voice2_e2_s40.pth",
            "missing.pth",
        ] {
            assert!(apply(&root, dir.to_str().unwrap(), "rvc", file).is_err());
        }
        assert!(apply(&root, dir.to_str().unwrap(), "gpt", "voice.pth").is_err());
        assert_eq!(fs::read(dir.join("voice.pth")).unwrap(), b"final");
    }

    #[test]
    fn apply_preserves_metadata_index_and_profiles_and_records_digest() {
        let (root, dir) = fixture("voice");
        let result = apply(&root, dir.to_str().unwrap(), "rvc", "voice_e2_s40.pth").unwrap();
        assert_eq!(result.weights[0].current.state, "matched");
        let side = crate::voices::read_sidecar(&dir);
        assert_eq!(side["author"], "Author");
        assert_eq!(side["pitch"], -2);
        assert_eq!(side["index"], "keep.index");
        assert_eq!(side["active_profile"], "soft");
        assert_eq!(
            side["training"]["selected"]["rvc"],
            json!({"file":"voice_e2_s40.pth","epoch":2,"step":40,"sha256":hex::encode(Sha256::digest(b"early"))})
        );
        assert_eq!(fs::read(dir.join("keep.index")).unwrap(), b"index");
        assert_eq!(fs::read(dir.join("profiles/soft.tmvp")).unwrap(), b"preset");
        assert!(fs::read_dir(&dir)
            .unwrap()
            .flatten()
            .all(|e| !e.file_name().to_string_lossy().starts_with(".epoch-")));
    }

    #[test]
    fn install_and_config_roll_back_if_cache_invalidation_fails() {
        let (root, dir) = fixture("voice");
        let old = fs::read(dir.join("config.json")).unwrap();
        let result = apply_with(
            &root,
            dir.to_str().unwrap(),
            "rvc",
            "voice_e2_s40.pth",
            |_| Err("cache unavailable".into()),
        );
        assert_eq!(result.unwrap_err(), "cache unavailable");
        assert_eq!(fs::read(dir.join("voice.pth")).unwrap(), b"final");
        assert_eq!(fs::read(dir.join("config.json")).unwrap(), old);
        assert_eq!(
            list(&root, dir.to_str().unwrap()).unwrap().weights[0]
                .current
                .epoch,
            Some(20)
        );
    }

    #[test]
    fn empty_candidate_does_not_replace_existing_weight() {
        let (root, dir) = fixture("voice");
        fs::write(
            crate::paths::engine_weights(&root).join("voice_e2_s40.pth"),
            b"",
        )
        .unwrap();
        assert!(apply(&root, dir.to_str().unwrap(), "rvc", "voice_e2_s40.pth").is_err());
        assert_eq!(fs::read(dir.join("voice.pth")).unwrap(), b"final");
    }

    #[test]
    fn hash_cache_changes_with_file_modification_time_at_the_same_size() {
        let (root, dir) = fixture("voice");
        let installed = dir.join("voice.pth");
        let file = fs::File::options().write(true).open(&installed).unwrap();
        let time = UNIX_EPOCH + std::time::Duration::from_secs(1_700_000_000);
        file.set_times(fs::FileTimes::new().set_modified(time))
            .unwrap();
        assert_eq!(
            list(&root, dir.to_str().unwrap()).unwrap().weights[0]
                .current
                .state,
            "matched"
        );
        fs::write(&installed, b"other").unwrap();
        file.set_times(fs::FileTimes::new().set_modified(time + std::time::Duration::from_secs(1)))
            .unwrap();
        assert_eq!(
            list(&root, dir.to_str().unwrap()).unwrap().weights[0]
                .current
                .state,
            "external"
        );
    }

    #[test]
    fn failed_config_write_restores_old_weight() {
        let (root, dir) = fixture("voice");
        fs::remove_file(dir.join("config.json")).unwrap();
        fs::create_dir(dir.join("config.json")).unwrap();
        assert!(apply(&root, dir.to_str().unwrap(), "rvc", "voice_e2_s40.pth").is_err());
        assert_eq!(fs::read(dir.join("voice.pth")).unwrap(), b"final");
        assert!(dir.join("config.json").is_dir());
    }

    #[test]
    fn custom_training_directory_is_managed_and_missing_weight_can_be_restored() {
        let (root, dir) = fixture("voice");
        let extra = root.join("trained");
        let custom = extra.join("voice");
        fs::create_dir_all(&custom).unwrap();
        fs::copy(dir.join("config.json"), custom.join("config.json")).unwrap();
        crate::config::set_train_output_dir(&root, extra.to_str().unwrap()).unwrap();
        assert_eq!(
            list(&root, custom.to_str().unwrap()).unwrap().weights[0]
                .current
                .state,
            "missing"
        );
        assert_eq!(
            apply(&root, custom.to_str().unwrap(), "rvc", "voice.pth")
                .unwrap()
                .weights[0]
                .current
                .state,
            "matched"
        );
    }

    #[test]
    fn identical_final_and_snapshot_share_one_selectable_row() {
        let (root, dir) = fixture("voice");
        fs::write(
            crate::paths::engine_weights(&root).join("voice_e2_s40.pth"),
            b"final",
        )
        .unwrap();
        assert!(apply(&root, dir.to_str().unwrap(), "rvc", "voice.pth").is_err());
        let result = apply(&root, dir.to_str().unwrap(), "rvc", "voice_e2_s40.pth").unwrap();
        assert_eq!(result.weights[0].current.file.as_deref(), Some("voice_e2_s40.pth"));
        assert!(result.weights[0].versions.iter().any(|v| v.file == "voice_e2_s40.pth" && v.is_final));
        assert_eq!(
            result.weights[0]
                .versions
                .iter()
                .filter(|v| v.current)
                .count(),
            1
        );
    }

    #[test]
    fn catalog_folds_snapshots_only_for_installed_exact_experiments_and_keeps_selection() {
        let (root, dir) = fixture("voice");
        let weights = crate::paths::engine_weights(&root);
        fs::write(weights.join("voice2_e2_s40.pth"), b"other").unwrap();
        let files = |catalog: Value| {
            catalog["models"]
                .as_array()
                .unwrap()
                .iter()
                .filter_map(|m| m["file"].as_str().map(str::to_owned))
                .collect::<Vec<_>>()
        };
        let catalog = files(crate::voices::list_voices(&root));
        assert!(!catalog.contains(&"voice_e2_s40.pth".into()));
        assert!(catalog.contains(&"voice2_e2_s40.pth".into()));
        fs::write(
            crate::paths::app_config_path(&root),
            serde_json::to_vec(&json!({"last_model_path":weights.join("voice_e2_s40.pth")}))
                .unwrap(),
        )
        .unwrap();
        assert!(files(crate::voices::list_voices(&root)).contains(&"voice_e2_s40.pth".into()));
        fs::remove_file(dir.join("voice.pth")).unwrap();
        assert!(files(crate::voices::list_voices(&root)).contains(&"voice_e10_s200.pth".into()));
    }

    #[test]
    fn report_sample() {
        let (root, dir) = fixture("voice");
        println!(
            "EPOCH_LIST={}",
            serde_json::to_string(&list(&root, dir.to_str().unwrap()).unwrap()).unwrap()
        );
        println!(
            "EPOCH_APPLY={}",
            serde_json::to_string(
                &apply(&root, dir.to_str().unwrap(), "rvc", "voice_e2_s40.pth").unwrap()
            )
            .unwrap()
        );
    }
}
