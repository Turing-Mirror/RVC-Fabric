//! Native voice-output service. Music changes mixer slots without reopening
//! the selected endpoint. Legacy RVC/DSP output remains mutually exclusive
//! until their microphone producers are connected to the native bus.
use crate::{
    audio_bus::{BridgeDescriptor, VoiceBus},
    audio_session::{self, PlaybackStatus},
};
use fabric_audio::{
    decode::{self, AudioTools},
    output,
};
use std::{
    path::Path,
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex,
    },
    time::Duration,
};
use tauri::State;

struct VoiceState {
    bus: Option<VoiceBus>,
    request: u64,
    pending: u64,
    last: PlaybackStatus,
}

impl VoiceState {
    const fn new() -> Self {
        Self {
            bus: None,
            request: 0,
            pending: 0,
            last: PlaybackStatus::idle(),
        }
    }

    fn busy(&self) -> bool {
        self.pending != 0 || self.bus.as_ref().is_some_and(VoiceBus::has_music)
    }
}

static VOICE: Mutex<VoiceState> = Mutex::new(VoiceState::new());
static START_GATE: Mutex<()> = Mutex::new(());
static ENGINE_STARTING: AtomicU64 = AtomicU64::new(0);

pub struct EngineStartGuard {
    descriptor: Option<BridgeDescriptor>,
    committed: bool,
}

impl EngineStartGuard {
    pub fn descriptor(&self) -> Option<&BridgeDescriptor> {
        self.descriptor.as_ref()
    }

    pub fn commit(&mut self) {
        self.committed = true;
    }
}

impl Drop for EngineStartGuard {
    fn drop(&mut self) {
        if self.descriptor.is_some() && !self.committed {
            let _ = on_engine_stopped();
        }
        ENGINE_STARTING.fetch_sub(1, Ordering::AcqRel);
    }
}

pub fn begin_engine_start(root: &Path) -> Result<EngineStartGuard, String> {
    let _gate = START_GATE.lock().unwrap_or_else(|e| e.into_inner());
    if ENGINE_STARTING.load(Ordering::Acquire) != 0 {
        return Err("audio_voice_engine_active".into());
    }
    let voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
    #[cfg(windows)]
    let mut voice = voice;
    let configured = crate::config::read(root)
        .get("audio_voice_device_id")
        .and_then(|value| value.as_str())
        .unwrap_or("")
        .to_string();
    #[cfg(windows)]
    let descriptor = {
        if !configured.is_empty()
            && voice
                .bus
                .as_ref()
                .is_some_and(|bus| bus.has_music() && bus.device_id() != configured)
        {
            return Err("audio_voice_device_locked".into());
        }
        let selected = voice
            .bus
            .as_ref()
            .filter(|bus| bus.has_music())
            .map(|bus| bus.device_id().to_string())
            .unwrap_or(configured);
        if selected.is_empty() {
            None
        } else {
            if engine_output_active(root) {
                return Err(crate::i18n::t("audio.voiceEngineActive"));
            }
            if crate::config::read(root)
                .get("audio_preview_device_id")
                .and_then(|value| value.as_str())
                == Some(selected.as_str())
            {
                return Err(crate::i18n::t("audio.voiceDeviceInvalid"));
            }
            if voice
                .bus
                .as_ref()
                .is_none_or(|bus| bus.device_id() != selected || bus.failed())
            {
                voice.bus = Some(VoiceBus::open(selected)?);
            }
            let bus = voice.bus.as_mut().unwrap();
            if bus.microphone_attached() {
                bus.detach_microphone()?;
            }
            match bus.attach_microphone() {
                Ok(descriptor) => Some(descriptor),
                Err(error) => {
                    voice.bus = None;
                    return Err(error);
                }
            }
        }
    };
    #[cfg(not(windows))]
    let descriptor: Option<BridgeDescriptor> = {
        let _ = configured;
        None
    };
    if descriptor.is_none() && voice.busy() {
        return Err(crate::i18n::t("audio.voiceStopBeforeEngine"));
    }
    ENGINE_STARTING.fetch_add(1, Ordering::AcqRel);
    Ok(EngineStartGuard {
        descriptor,
        committed: false,
    })
}

pub fn on_engine_stopped() -> Result<(), String> {
    let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
    #[cfg(windows)]
    if let Some(bus) = voice.bus.as_mut() {
        if let Err(error) = bus.detach_microphone() {
            voice.bus = None;
            return Err(error);
        }
    }
    if voice
        .bus
        .as_ref()
        .is_some_and(|bus| !bus.has_music() && !bus.microphone_attached())
    {
        voice.bus = None;
    }
    Ok(())
}

pub fn microphone_failed() -> bool {
    VOICE
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .bus
        .as_ref()
        .is_some_and(|bus| bus.microphone_attached() && (bus.failed() || bus.microphone_failed()))
}

fn engine_output_active(root: &Path) -> bool {
    let status = crate::worker::status_for_ui(root);
    status.get("worker_alive").and_then(|value| value.as_bool()) == Some(true)
        && matches!(
            status.get("state").and_then(|value| value.as_str()),
            Some("running" | "starting" | "stopping")
        )
}

fn playback_status(bus: &VoiceBus) -> PlaybackStatus {
    let Some((name, played, length, paused, failed)) = bus.music_status() else {
        return PlaybackStatus::idle();
    };
    PlaybackStatus {
        state: if failed || bus.failed() {
            "error"
        } else if paused {
            "paused"
        } else {
            "playing"
        },
        name: name.to_string(),
        played_frames: played,
        length_frames: length,
        sample_rate: bus.format().sample_rate,
    }
}

fn watch(request: u64) {
    std::thread::spawn(move || loop {
        std::thread::sleep(Duration::from_millis(50));
        let mut state = VOICE.lock().unwrap_or_else(|e| e.into_inner());
        if state.request != request {
            break;
        }
        let Some(bus) = state.bus.as_mut() else { break };
        if !bus.failed() && !bus.music_finished() {
            continue;
        }
        let mut status = playback_status(bus);
        status.state = if bus.failed() || status.state == "error" {
            "error"
        } else {
            "ended"
        };
        let result = bus.stop_music();
        let idle_bus = !bus.microphone_attached();
        if idle_bus {
            state.bus = None;
        }
        if result.is_err() && !idle_bus {
            status.state = "error";
        }
        state.last = status;
        break;
    });
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
            if ENGINE_STARTING.load(Ordering::Acquire) != 0 {
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
            let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
            if engine_output_active(&root)
                && !voice
                    .bus
                    .as_ref()
                    .is_some_and(VoiceBus::microphone_attached)
            {
                return Err("audio_voice_engine_active".into());
            }
            if voice
                .bus
                .as_ref()
                .is_some_and(|bus| bus.microphone_attached() && bus.device_id() != device_id)
            {
                return Err("audio_voice_device_locked".into());
            }
            if voice
                .bus
                .as_ref()
                .is_some_and(|bus| bus.microphone_attached() && bus.failed())
            {
                return Err("audio_voice_output_failed".into());
            }
            voice.request = voice.request.wrapping_add(1).max(1);
            voice.pending = voice.request;
            voice.request
        };
        let result = (|| {
            let source = audio_session::entry(&root, &entry_id)?;
            let format = {
                let voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
                match voice.bus.as_ref() {
                    Some(bus) if bus.device_id() == device_id && !bus.failed() => bus.format(),
                    _ => output::device_format(&device_id)?,
                }
            };
            let decoded = decode::decode(
                &AudioTools::at(&root),
                &source.path,
                source.range,
                format,
                0.25,
            )?;
            let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
            if voice.request != request {
                return Err("audio_playback_cancelled".into());
            }
            if voice
                .bus
                .as_ref()
                .is_some_and(VoiceBus::microphone_attached)
            {
                let bus = voice.bus.as_ref().unwrap();
                if bus.device_id() != device_id {
                    return Err("audio_voice_device_locked".into());
                }
                if bus.failed() {
                    return Err("audio_voice_output_failed".into());
                }
            } else if ENGINE_STARTING.load(Ordering::Acquire) != 0 || engine_output_active(&root) {
                return Err("audio_voice_engine_active".into());
            }
            if voice
                .bus
                .as_ref()
                .is_none_or(|bus| bus.device_id() != device_id || bus.failed())
            {
                voice.bus = Some(VoiceBus::open(device_id)?);
            }
            let bus = voice.bus.as_mut().unwrap();
            if let Err(error) = bus.play_decoded(source.name, decoded, source.gain) {
                if (error.starts_with("audio_music_swap")
                    || voice.bus.as_ref().is_some_and(VoiceBus::failed))
                    && !voice
                        .bus
                        .as_ref()
                        .is_some_and(VoiceBus::microphone_attached)
                {
                    voice.bus = None;
                }
                return Err(error);
            }
            let status = playback_status(voice.bus.as_ref().unwrap());
            voice.last = PlaybackStatus::idle();
            watch(request);
            Ok(status)
        })();
        let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
        if voice.pending == request {
            voice.pending = 0;
        }
        result
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
pub fn audio_voice_status() -> PlaybackStatus {
    let voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
    voice
        .bus
        .as_ref()
        .filter(|bus| bus.has_music())
        .map(playback_status)
        .unwrap_or_else(|| voice.last.clone())
}

#[tauri::command]
pub fn audio_voice_pause(paused: bool) -> Result<PlaybackStatus, String> {
    let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
    let bus = voice.bus.as_mut().ok_or("audio_playback_not_playing")?;
    bus.pause(paused)?;
    Ok(playback_status(bus))
}

#[tauri::command]
pub fn audio_voice_stop() -> PlaybackStatus {
    let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
    voice.request = voice.request.wrapping_add(1).max(1);
    voice.pending = 0;
    if let Some(bus) = voice.bus.as_mut() {
        if bus.has_music() {
            let _ = bus.stop_music();
        }
        if !bus.microphone_attached() {
            voice.bus = None;
        }
    }
    voice.last = PlaybackStatus::idle();
    voice.last.clone()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn engine_start_cannot_race_with_preparing_voice_audio() {
        {
            let mut state = VOICE.lock().unwrap();
            state.pending = 1;
        }
        let root = Path::new("/nonexistent-audio-voice-test");
        assert!(begin_engine_start(root).is_err());
        {
            let mut state = VOICE.lock().unwrap();
            state.pending = 0;
        }
        let first = begin_engine_start(root).unwrap();
        assert!(begin_engine_start(root).is_err());
        assert_eq!(ENGINE_STARTING.load(Ordering::Acquire), 1);
        drop(first);
        assert_eq!(ENGINE_STARTING.load(Ordering::Acquire), 0);
    }
}
