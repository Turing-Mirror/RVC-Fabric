//! Audio-only voice output. Until the microphone producer moves to this output
//! service, engine startup and audio-only playback are mutually exclusive.
use crate::audio_session::{self, PlaybackStatus, Player};
use fabric_audio::output;
use std::sync::{
    atomic::{AtomicU64, Ordering},
    Mutex,
};
use tauri::State;

static VOICE: Player = Player::new();
static START_GATE: Mutex<()> = Mutex::new(());
static ENGINE_STARTING: AtomicU64 = AtomicU64::new(0);

pub struct EngineStartGuard;

impl Drop for EngineStartGuard {
    fn drop(&mut self) {
        ENGINE_STARTING.fetch_sub(1, Ordering::AcqRel);
    }
}

pub fn begin_engine_start() -> Result<EngineStartGuard, String> {
    let _gate = START_GATE.lock().unwrap_or_else(|e| e.into_inner());
    if VOICE.busy() {
        return Err(crate::i18n::t("audio.voiceStopBeforeEngine"));
    }
    ENGINE_STARTING.fetch_add(1, Ordering::AcqRel);
    Ok(EngineStartGuard)
}

fn engine_output_active(root: &std::path::Path) -> bool {
    let status = crate::worker::status_for_ui(root);
    status.get("worker_alive").and_then(|value| value.as_bool()) == Some(true)
        && matches!(
            status.get("state").and_then(|value| value.as_str()),
            Some("running" | "starting" | "stopping")
        )
}

#[tauri::command]
pub fn audio_voice_devices() -> Result<Vec<output::OutputDevice>, String> {
    output::devices()
}

#[tauri::command]
pub async fn audio_voice_start(
    state: State<'_, Mutex<crate::AppState>>,
    entry_id: String,
    device_id: String,
) -> Result<PlaybackStatus, String> {
    let root = crate::root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        let request = {
            let _gate = START_GATE.lock().unwrap_or_else(|e| e.into_inner());
            if ENGINE_STARTING.load(Ordering::Acquire) != 0 || engine_output_active(&root) {
                return Err("audio_voice_engine_active".into());
            }
            let cfg = crate::config::read(&root);
            if cfg
                .get("audio_preview_device_id")
                .and_then(|value| value.as_str())
                == Some(device_id.as_str())
            {
                return Err("audio_voice_device_is_preview".into());
            }
            VOICE.reserve()
        };
        let result = (|| {
            let source = audio_session::entry(&root, &entry_id)?;
            VOICE.start(&root, request, source, &device_id)
        })();
        VOICE.release(request);
        result
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
pub fn audio_voice_status() -> PlaybackStatus {
    VOICE.status()
}

#[tauri::command]
pub fn audio_voice_pause(paused: bool) -> Result<PlaybackStatus, String> {
    VOICE.pause(paused)
}

#[tauri::command]
pub fn audio_voice_stop() -> PlaybackStatus {
    VOICE.stop()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn engine_start_cannot_race_with_preparing_voice_audio() {
        let id = VOICE.reserve();
        assert!(begin_engine_start().is_err());
        VOICE.stop();
        VOICE.release(id);
        let first = begin_engine_start().unwrap();
        let second = begin_engine_start().unwrap();
        assert_eq!(ENGINE_STARTING.load(Ordering::Acquire), 2);
        drop(first);
        assert_eq!(ENGINE_STARTING.load(Ordering::Acquire), 1);
        drop(second);
        assert_eq!(ENGINE_STARTING.load(Ordering::Acquire), 0);
    }
}
