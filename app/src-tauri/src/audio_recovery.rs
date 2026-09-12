//! Opt-in device exclusions and a non-ASIO PortAudio backend.
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::sync::{atomic::AtomicBool, Arc, Mutex};
use tauri::Emitter;

pub fn dll_path(root: &Path) -> PathBuf {
    crate::paths::user_data(root).join("audio_backend/libportaudio64bit.dll")
}

fn prepare_backend(root: &Path) -> Result<(), String> {
    let dll = dll_path(root);
    if dll.is_file() {
        return Ok(());
    }
    let dir = dll.parent().unwrap();
    std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    let wheel = dir.join("sounddevice-0.5.2.whl");
    // Official PyPI wheel. This does not replace the installed Python bindings.
    crate::download::download_file(&["https://files.pythonhosted.org/packages/e1/3e/61d88e6b0a7383127cdc779195cb9d83ebcf11d39bc961de5777e457075e/sounddevice-0.5.2-py3-none-win_amd64.whl".into()],
        &wheel, "e18944b767d2dac3771a7771bdd7ff7d3acd7d334e72c4bedab17d1aed5dbc22", Arc::new(AtomicBool::new(false)), None)?;
    let mut zip = zip::ZipArchive::new(std::fs::File::open(&wheel).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    // Extract exact members, never the archive's paths.
    for i in 0..zip.len() {
        let mut entry = zip.by_index(i).map_err(|e| e.to_string())?;
        if (entry.name().to_ascii_lowercase().contains("license")
            || entry.name() == "_sounddevice_data/portaudio-binaries/README.md")
            && !entry.is_dir()
        {
            let path = dir.join(format!("LICENSE-{i}.txt"));
            std::io::copy(
                &mut entry,
                &mut std::fs::File::create(path).map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?;
        }
    }
    let mut entry = zip
        .by_name("_sounddevice_data/portaudio-binaries/libportaudio64bit.dll")
        .map_err(|e| e.to_string())?;
    let stage = dir.join("portaudio.partial");
    std::io::copy(
        &mut entry,
        &mut std::fs::File::create(&stage).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    std::fs::rename(stage, dll).map_err(|e| e.to_string())
}

fn checked_devices(root: &Path) -> Result<Value, String> {
    use std::process::{Command, Stdio};
    let py = crate::paths::runtime_pythonw(root)
        .ok_or_else(|| crate::i18n::t("neptune.compatibilityFailed"))?;
    let out = crate::paths::control_dir(root).join("audio_check.json");
    std::fs::create_dir_all(out.parent().unwrap()).map_err(|e| e.to_string())?;
    let _ = std::fs::remove_file(&out);
    let mut cmd = Command::new(py);
    cmd.arg(root.join("tools/audio_probe.py"))
        .arg(&out)
        .arg("--check")
        .current_dir(root)
        .envs(crate::worker::env_for_runtime(root))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    let mut child = cmd.spawn().map_err(|e| e.to_string())?;
    if crate::audio_probe::wait_probe(&mut child) != Some(0) {
        return Err(crate::i18n::t("neptune.deviceCheckFailed"));
    }
    serde_json::from_slice(&std::fs::read(out).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())
}

pub fn merge_failed(existing: &[Value], failed: &[Value]) -> Vec<Value> {
    let mut result = existing.to_vec();
    for item in failed {
        if !result.contains(item) {
            result.push(item.clone());
        }
    }
    result
}

#[tauri::command]
pub async fn audio_recover(
    app: tauri::AppHandle,
    state: tauri::State<'_, Mutex<crate::AppState>>,
    action: String,
    device: Option<Value>,
    enabled: Option<bool>,
) -> Result<Value, String> {
    let root = crate::root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        static LOCK: Mutex<()> = Mutex::new(());
        let _lock = LOCK
            .try_lock()
            .map_err(|_| crate::i18n::t("neptune.deviceRecovery"))?;
        if !matches!(
            action.as_str(),
            "check" | "compatibility" | "restore" | "ignore"
        ) {
            return Err("unknown audio action".into());
        }
        if action == "compatibility" && enabled == Some(true) {
            if !cfg!(windows) {
                return Err(crate::i18n::t("neptune.compatibilityFailed"));
            }
            prepare_backend(&root)?;
        }
        crate::worker::stop_vc(&root, true)?;
        let cfg = crate::config::read(&root);
        let old = cfg
            .get("ignored_audio_devices")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut patch = serde_json::Map::new();
        if action == "compatibility" {
            patch.insert(
                "audio_compatibility".into(),
                json!(enabled.unwrap_or(false)),
            );
            patch.insert("sg_hostapi".into(), json!("MME"));
            patch.insert("sg_input_device".into(), json!(""));
            patch.insert("sg_output_device".into(), json!(""));
        } else if action == "ignore" {
            patch.insert(
                "audio_ignore_enabled".into(),
                json!(enabled.unwrap_or(false)),
            );
        } else if action == "restore" {
            patch.insert(
                "ignored_audio_devices".into(),
                json!(old
                    .into_iter()
                    .filter(|v| Some(v) != device.as_ref())
                    .collect::<Vec<_>>()),
            );
        } else {
            let report = checked_devices(&root)?;
            let failed = report["failed"].as_array().cloned().unwrap_or_default();
            patch.insert("audio_ignore_enabled".into(), json!(true));
            patch.insert(
                "ignored_audio_devices".into(),
                json!(merge_failed(&old, &failed)),
            );
            for item in failed {
                if let Some(dir) = item["direction"]
                    .as_str()
                    .filter(|v| matches!(*v, "input" | "output"))
                {
                    patch.insert(format!("sg_{dir}_device"), json!(""));
                }
            }
        }
        crate::config::update(&root, patch)?;
        crate::audio_probe::reset();
        let cfg = crate::config::read(&root);
        let _ = app.emit("config-changed", json!({"config": cfg}));
        // Start only the idle worker. Conversion remains an explicit user action.
        let status = crate::worker::ensure_worker_and_devices(&root, 120_000);
        if status["state"] == "error" {
            return Err(status["error"].as_str().unwrap_or("").to_string());
        }
        Ok(json!({"config": cfg, "status": status}))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn disabling_ignores_restores_devices_without_forgetting_the_list() {
        let root = crate::testutil::scratch("audio-ignore-toggle");
        let list = json!([{"name":"USB", "hostapi":"MME", "direction":"input"}]);
        crate::config::update(
            &root,
            json!({"ignored_audio_devices":list, "audio_ignore_enabled":true})
                .as_object()
                .unwrap()
                .clone(),
        )
        .unwrap();
        assert_eq!(
            crate::worker::env_for_runtime(&root)["TM_AUDIO_IGNORED"],
            list.to_string()
        );
        crate::config::update(
            &root,
            json!({"audio_ignore_enabled":false})
                .as_object()
                .unwrap()
                .clone(),
        )
        .unwrap();
        assert_eq!(
            crate::worker::env_for_runtime(&root)["TM_AUDIO_IGNORED"],
            "[]"
        );
        assert_eq!(crate::config::read(&root)["ignored_audio_devices"], list);
    }
    #[test]
    fn exclusions_are_unique_and_directional() {
        let input = json!({"name":"USB", "hostapi":"MME", "direction":"input"});
        let output = json!({"name":"USB", "hostapi":"MME", "direction":"output"});
        assert_eq!(
            merge_failed(&[input.clone()], &[input.clone(), output.clone()]),
            vec![input, output]
        );
    }
}
