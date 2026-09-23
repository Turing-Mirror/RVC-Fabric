//! Native private preview. The device is explicit and never follows the OS default.
use crate::audio_session::{self, PlaybackStatus, Player};
use fabric_audio::{format::ClipRange, output};
use std::{path::Path, sync::Mutex};
use tauri::State;

static PREVIEW: Player = Player::new();

fn preview_device_allowed(root: &Path, id: &str) -> Result<(), String> {
    let device = output::devices()?
        .into_iter()
        .find(|device| device.id == id)
        .ok_or("audio_output_device_missing")?;
    let name = device.name.to_lowercase();
    if [
        "cable input",
        "vb-audio",
        "voicemeeter",
        "blackhole",
        "virtual audio",
        "loopback",
    ]
    .iter()
    .any(|part| name.contains(part))
    {
        return Err("audio_preview_device_is_virtual".into());
    }
    let cfg = crate::config::read(root);
    if cfg
        .get("audio_voice_device_id")
        .and_then(|value| value.as_str())
        == Some(id)
    {
        return Err("audio_preview_device_is_voice_output".into());
    }
    let voice_device = cfg
        .get("sg_output_device")
        .and_then(|value| value.as_str())
        .unwrap_or("")
        .to_lowercase();
    if !voice_device.is_empty() && (name.contains(&voice_device) || voice_device.contains(&name)) {
        return Err("audio_preview_device_is_voice_output".into());
    }
    Ok(())
}

#[tauri::command]
pub fn audio_preview_devices() -> Result<Vec<output::OutputDevice>, String> {
    output::devices()
}

#[tauri::command]
pub async fn audio_preview_start(
    state: State<'_, Mutex<crate::AppState>>,
    entry_id: String,
    device_id: String,
    start: f64,
    end: Option<f64>,
) -> Result<PlaybackStatus, String> {
    let root = crate::root_clone(&state)?;
    let request = PREVIEW.reserve();
    let result = tauri::async_runtime::spawn_blocking(move || {
        preview_device_allowed(&root, &device_id)?;
        let mut source = audio_session::entry(&root, &entry_id)?;
        source.range = ClipRange { start, end };
        source.gain = 1.0;
        PREVIEW.start(&root, request, source, &device_id)
    })
    .await;
    PREVIEW.release(request);
    result.map_err(|e| e.to_string())?
}

#[tauri::command]
pub fn audio_preview_status() -> PlaybackStatus {
    PREVIEW.status()
}

#[tauri::command]
pub fn audio_preview_pause(paused: bool) -> Result<PlaybackStatus, String> {
    PREVIEW.pause(paused)
}

#[tauri::command]
pub fn audio_preview_stop() -> PlaybackStatus {
    PREVIEW.stop()
}
