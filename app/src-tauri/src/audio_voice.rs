//! Native voice-output service. Music changes mixer slots without reopening
//! the selected endpoint. Legacy RVC/DSP output remains mutually exclusive
//! until their microphone producers are connected to the native bus.
use crate::{
    audio_bus::{BridgeDescriptor, MusicPlacement, NewMusic, VoiceBus},
    audio_session::{self, PlaybackStatus},
};
use fabric_audio::{
    decode::{self, AudioTools, ClipOptions},
    output,
};
use serde::Serialize;
use serde_json::{json, Map};
use std::{
    path::Path,
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::Duration,
};
use tauri::{AppHandle, Emitter, State};

const VOLUME_STEPS: i16 = 10;
/// Decoded audio kept ahead of the callback; a loop pass restarts within it.
const DECODE_BUFFER_SECONDS: f64 = 1.0;
/// Fade at clip edges so loop seams and seeks do not click.
const EDGE_FADE_SECONDS: f64 = 0.005;

#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
pub struct AudioVolumeStatus {
    pub volume: f32,
    pub muted: bool,
}

fn volume_settings(root: &Path) -> AudioVolumeStatus {
    let config = crate::config::read(root);
    AudioVolumeStatus {
        volume: config
            .get("audio_music_volume")
            .and_then(serde_json::Value::as_f64)
            .filter(|value| value.is_finite() && (0.0..=1.0).contains(value))
            .unwrap_or(1.0) as f32,
        muted: config
            .get("audio_music_muted")
            .and_then(serde_json::Value::as_bool)
            .unwrap_or(false),
    }
}

fn update_volume(
    root: &Path,
    update: impl FnOnce(AudioVolumeStatus) -> AudioVolumeStatus,
) -> Result<AudioVolumeStatus, String> {
    let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
    let previous = volume_settings(root);
    let next = update(previous);
    if next != previous {
        let mut patch = Map::new();
        patch.insert("audio_music_volume".into(), json!(next.volume));
        patch.insert("audio_music_muted".into(), json!(next.muted));
        crate::config::update(root, patch)?;
        if let Some(bus) = voice.bus.as_mut() {
            bus.set_master_gain(if next.muted { 0.0 } else { next.volume })?;
        }
    }
    Ok(next)
}

pub fn adjust_volume(root: &Path, direction: i8) -> Result<AudioVolumeStatus, String> {
    if !matches!(direction, -1 | 1) {
        return Err("audio_volume_direction_invalid".into());
    }
    update_volume(root, |previous| AudioVolumeStatus {
        volume: ((previous.volume * VOLUME_STEPS as f32).round() as i16 + direction as i16)
            .clamp(0, VOLUME_STEPS) as f32
            / VOLUME_STEPS as f32,
        muted: false,
    })
}

pub fn toggle_mute(root: &Path) -> Result<AudioVolumeStatus, String> {
    update_volume(root, |previous| AudioVolumeStatus {
        muted: !previous.muted,
        ..previous
    })
}

#[tauri::command]
pub fn audio_voice_volume_get(
    state: State<'_, Mutex<crate::AppState>>,
) -> Result<AudioVolumeStatus, String> {
    Ok(volume_settings(&crate::root_clone(&state)?))
}

#[tauri::command]
pub fn audio_voice_volume_adjust(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    direction: i8,
) -> Result<AudioVolumeStatus, String> {
    let status = adjust_volume(&crate::root_clone(&state)?, direction)?;
    let _ = app.emit("audio-volume://changed", status);
    Ok(status)
}

#[tauri::command]
pub fn audio_voice_volume_toggle(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
) -> Result<AudioVolumeStatus, String> {
    let status = toggle_mute(&crate::root_clone(&state)?)?;
    let _ = app.emit("audio-volume://changed", status);
    Ok(status)
}

struct VoiceState {
    bus: Option<VoiceBus>,
    request: u64,
    pending: u64,
    last: VoicePlaybackStatus,
    /// Most recently started entry and device, so replay still works after it ended.
    recent: Option<(String, String)>,
}

#[derive(Clone, Serialize)]
pub struct VoicePlaybackStatus {
    #[serde(flatten)]
    playback: PlaybackStatus,
    pub instance_id: Option<u64>,
    pub active_count: usize,
    pub looping: bool,
}

impl VoicePlaybackStatus {
    const fn idle() -> Self {
        Self {
            playback: PlaybackStatus::idle(),
            instance_id: None,
            active_count: 0,
            looping: false,
        }
    }
}

impl VoiceState {
    const fn new() -> Self {
        Self {
            bus: None,
            request: 0,
            pending: 0,
            last: VoicePlaybackStatus::idle(),
            recent: None,
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
    if voice.pending != 0 {
        return Err("audio_voice_engine_active".into());
    }
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

fn playback_status(bus: &VoiceBus, id: u64) -> VoicePlaybackStatus {
    let Some(music) = bus.music_status(id) else {
        return VoicePlaybackStatus::idle();
    };
    VoicePlaybackStatus {
        playback: PlaybackStatus {
            state: if music.failed || bus.failed() {
                "error"
            } else if music.paused {
                "paused"
            } else {
                "playing"
            },
            name: music.name,
            played_frames: music.played,
            length_frames: music.length,
            sample_rate: bus.format().sample_rate,
        },
        instance_id: Some(music.id),
        active_count: bus.music_count(),
        looping: music.looping,
    }
}

fn current_status(voice: &VoiceState) -> VoicePlaybackStatus {
    voice
        .bus
        .as_ref()
        .and_then(|bus| bus.latest_music_id().map(|id| playback_status(bus, id)))
        .unwrap_or_else(|| voice.last.clone())
}

fn watch(id: u64) {
    std::thread::spawn(move || loop {
        std::thread::sleep(Duration::from_millis(50));
        let mut state = VOICE.lock().unwrap_or_else(|e| e.into_inner());
        let Some(bus) = state.bus.as_mut() else { break };
        if bus.music_status(id).is_none() {
            break;
        }
        if !bus.failed() && !bus.music_finished(id) {
            continue;
        }
        let mut status = playback_status(bus, id);
        status.playback.state = if bus.failed() || status.playback.state == "error" {
            "error"
        } else {
            "ended"
        };
        let result = bus.stop_music(id);
        let idle_bus = !bus.has_music() && !bus.microphone_attached();
        let no_music = !bus.has_music();
        if idle_bus {
            state.bus = None;
        }
        if result.is_err() {
            status.playback.state = "error";
        }
        if no_music {
            status.active_count = 0;
            state.last = status;
        }
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
    mode: Option<String>,
) -> Result<VoicePlaybackStatus, String> {
    let overlay = match mode.as_deref().unwrap_or("replace") {
        "replace" => false,
        "overlay" => true,
        _ => return Err("audio_playback_mode_invalid".into()),
    };
    let root = crate::root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || start_entry(&root, entry_id, device_id, overlay))
        .await
        .map_err(|e| e.to_string())?
}

/// The same service entrypoint is used by UI commands and native global hotkeys.
pub fn start_entry(
    root: &Path,
    entry_id: String,
    device_id: String,
    overlay: bool,
) -> Result<VoicePlaybackStatus, String> {
    start_entry_placed(root, entry_id, device_id, StartOptions::new(if overlay {
        MusicPlacement::Overlay
    } else {
        MusicPlacement::ReplaceAll
    }))
}

struct StartOptions {
    placement: MusicPlacement,
    /// Seconds into the clip; only the first pass starts there.
    offset_seconds: f64,
    /// `None` takes the entry's saved loop setting.
    looping: Option<bool>,
    paused: bool,
}

impl StartOptions {
    fn new(placement: MusicPlacement) -> Self {
        Self {
            placement,
            offset_seconds: 0.0,
            looping: None,
            paused: false,
        }
    }
}

fn start_entry_placed(
    root: &Path,
    entry_id: String,
    device_id: String,
    options: StartOptions,
) -> Result<VoicePlaybackStatus, String> {
    let placement = options.placement;
    let request = {
        let _gate = START_GATE.lock().unwrap_or_else(|e| e.into_inner());
        if ENGINE_STARTING.load(Ordering::Acquire) != 0 {
            return Err("audio_voice_engine_active".into());
        }
        let cfg = crate::config::read(root);
        if cfg
            .get("audio_preview_device_id")
            .and_then(|value| value.as_str())
            == Some(device_id.as_str())
        {
            return Err("audio_voice_device_is_preview".into());
        }
        let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
        if engine_output_active(root)
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
        if matches!(placement, MusicPlacement::Overlay)
            && voice
                .bus
                .as_ref()
                .is_some_and(|bus| bus.has_music() && bus.device_id() != device_id)
        {
            return Err("audio_voice_device_locked".into());
        }
        if let MusicPlacement::ReplaceInstance(id) = placement {
            let bus = voice.bus.as_ref().ok_or("audio_playback_cancelled")?;
            if bus.failed() || bus.device_id() != device_id || bus.music_status(id).is_none() {
                return Err("audio_playback_cancelled".into());
            }
        }
        voice.request = voice.request.wrapping_add(1).max(1);
        voice.pending = voice.request;
        voice.request
    };
    let result = (|| {
        let source = audio_session::entry(root, &entry_id)?;
        let format = {
            let voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
            match voice.bus.as_ref() {
                Some(bus) if bus.device_id() == device_id && !bus.failed() => bus.format(),
                _ => output::device_format(&device_id)?,
            }
        };
        if !options.offset_seconds.is_finite() || options.offset_seconds < 0.0 {
            return Err("invalid_clip_offset".into());
        }
        let looping = Arc::new(AtomicBool::new(options.looping.unwrap_or(source.looped)));
        let offset = (options.offset_seconds * format.sample_rate as f64).floor() as u64;
        let decoded = decode::decode_clip(
            &AudioTools::at(root),
            &source.path,
            source.range,
            format,
            DECODE_BUFFER_SECONDS,
            ClipOptions {
                offset_frames: offset,
                looping: Some(looping.clone()),
                edge_fade_seconds: EDGE_FADE_SECONDS,
            },
        )?;
        let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
        if voice.request != request {
            return Err("audio_playback_cancelled".into());
        }
        if let MusicPlacement::ReplaceInstance(id) = placement {
            if voice.bus.as_ref().is_none_or(|bus| {
                bus.failed() || bus.device_id() != device_id || bus.music_status(id).is_none()
            }) {
                return Err("audio_playback_cancelled".into());
            }
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
        } else if ENGINE_STARTING.load(Ordering::Acquire) != 0 || engine_output_active(root) {
            return Err("audio_voice_engine_active".into());
        }
        if voice
            .bus
            .as_ref()
            .is_none_or(|bus| bus.device_id() != device_id || bus.failed())
        {
            voice.bus = Some(VoiceBus::open(device_id.clone())?);
        }
        let bus = voice.bus.as_mut().unwrap();
        let volume = volume_settings(root);
        let master_gain = if volume.muted { 0.0 } else { volume.volume };
        if let Err(error) = bus.play_decoded(NewMusic {
            id: request,
            entry_id: entry_id.clone(),
            name: source.name,
            decoded,
            offset,
            looping,
            paused: options.paused,
            gain: source.gain,
            master_gain,
            placement,
        }) {
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
        let status = playback_status(voice.bus.as_ref().unwrap(), request);
        voice.last = VoicePlaybackStatus::idle();
        voice.recent = Some((entry_id, device_id));
        watch(request);
        Ok(status)
    })();
    let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
    if voice.pending == request {
        voice.pending = 0;
    }
    result
}

/// Restart an instance from its clip start. With no instance given and nothing
/// playing, the most recently started entry plays again.
pub fn replay(root: &Path, instance_id: Option<u64>) -> Result<VoicePlaybackStatus, String> {
    let target = {
        let voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
        let active = voice
            .bus
            .as_ref()
            .and_then(|bus| instance_id.or_else(|| bus.latest_music_id()).map(|id| (bus, id)));
        match active {
            Some((bus, id)) => {
                let music = bus.music_status(id).ok_or("audio_playback_not_playing")?;
                Some((id, music.entry_id, bus.device_id().to_string(), music.looping))
            }
            None if instance_id.is_some() => return Err("audio_playback_not_playing".into()),
            None => None,
        }
    };
    match target {
        Some((id, entry_id, device_id, looping)) => start_entry_placed(
            root,
            entry_id,
            device_id,
            StartOptions {
                looping: Some(looping),
                ..StartOptions::new(MusicPlacement::ReplaceInstance(id))
            },
        ),
        None => {
            let (entry_id, device_id) = VOICE
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .recent
                .clone()
                .ok_or("audio_playback_not_playing")?;
            start_entry_placed(
                root,
                entry_id,
                device_id,
                StartOptions::new(MusicPlacement::ReplaceAll),
            )
        }
    }
}

/// Jump within the clip. The instance keeps its slot, loop and pause state.
pub fn seek(
    root: &Path,
    instance_id: Option<u64>,
    seconds: f64,
) -> Result<VoicePlaybackStatus, String> {
    if !seconds.is_finite() {
        return Err("invalid_clip_offset".into());
    }
    let (id, entry_id, device_id, looping, paused, length, rate) = {
        let voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
        let bus = voice.bus.as_ref().ok_or("audio_playback_not_playing")?;
        let id = instance_id
            .or_else(|| bus.latest_music_id())
            .ok_or("audio_playback_not_playing")?;
        let music = bus.music_status(id).ok_or("audio_playback_not_playing")?;
        (
            id,
            music.entry_id,
            bus.device_id().to_string(),
            music.looping,
            music.paused,
            music.length,
            bus.format().sample_rate,
        )
    };
    let last_frame = length.saturating_sub(1) as f64 / rate.max(1) as f64;
    start_entry_placed(
        root,
        entry_id,
        device_id,
        StartOptions {
            placement: MusicPlacement::ReplaceInstance(id),
            offset_seconds: seconds.clamp(0.0, last_frame),
            looping: Some(looping),
            paused,
        },
    )
}

#[tauri::command]
pub async fn audio_voice_seek(
    state: State<'_, Mutex<crate::AppState>>,
    instance_id: Option<u64>,
    seconds: f64,
) -> Result<VoicePlaybackStatus, String> {
    let root = crate::root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || seek(&root, instance_id, seconds))
        .await
        .map_err(|e| e.to_string())?
}

/// Switch looping for one instance; `None` toggles. Takes effect until the
/// last decoded frame has played, so it can still rescue an ending clip.
pub fn set_loop(
    instance_id: Option<u64>,
    looping: Option<bool>,
) -> Result<VoicePlaybackStatus, String> {
    let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
    let bus = voice.bus.as_mut().ok_or("audio_playback_not_playing")?;
    let id = instance_id
        .or_else(|| bus.latest_music_id())
        .ok_or("audio_playback_not_playing")?;
    let current = bus
        .music_status(id)
        .ok_or("audio_playback_not_playing")?
        .looping;
    bus.set_looping(id, looping.unwrap_or(!current))?;
    Ok(playback_status(bus, id))
}

#[tauri::command]
pub fn audio_voice_loop(
    instance_id: Option<u64>,
    looping: Option<bool>,
) -> Result<VoicePlaybackStatus, String> {
    set_loop(instance_id, looping)
}

#[tauri::command]
pub async fn audio_voice_replay(
    state: State<'_, Mutex<crate::AppState>>,
    instance_id: Option<u64>,
) -> Result<VoicePlaybackStatus, String> {
    let root = crate::root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || replay(&root, instance_id))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
pub fn audio_voice_status() -> VoicePlaybackStatus {
    let voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
    current_status(&voice)
}

#[tauri::command]
pub fn audio_voice_instances() -> Vec<VoicePlaybackStatus> {
    let voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
    let Some(bus) = voice.bus.as_ref() else {
        return Vec::new();
    };
    let mut instances: Vec<_> = bus
        .music_ids()
        .into_iter()
        .map(|id| playback_status(bus, id))
        .collect();
    instances.sort_by_key(|status| std::cmp::Reverse(status.instance_id));
    instances
}

#[tauri::command]
pub fn audio_voice_pause(
    paused: bool,
    instance_id: Option<u64>,
) -> Result<VoicePlaybackStatus, String> {
    let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
    let bus = voice.bus.as_mut().ok_or("audio_playback_not_playing")?;
    let id = instance_id
        .or_else(|| bus.latest_music_id())
        .ok_or("audio_playback_not_playing")?;
    bus.pause(id, paused)?;
    Ok(playback_status(bus, id))
}

pub fn toggle_pause_latest() -> Result<VoicePlaybackStatus, String> {
    let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
    let bus = voice.bus.as_mut().ok_or("audio_playback_not_playing")?;
    let id = bus.latest_music_id().ok_or("audio_playback_not_playing")?;
    let paused = bus
        .music_status(id)
        .ok_or("audio_playback_not_playing")?
        .paused;
    bus.pause(id, !paused)?;
    Ok(playback_status(bus, id))
}

#[tauri::command]
pub fn audio_voice_stop_instance(instance_id: u64) -> Result<VoicePlaybackStatus, String> {
    let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
    let bus = voice.bus.as_mut().ok_or("audio_playback_not_playing")?;
    bus.stop_music(instance_id)?;
    if !bus.has_music() && !bus.microphone_attached() {
        voice.bus = None;
    }
    voice.last = VoicePlaybackStatus::idle();
    Ok(current_status(&voice))
}

pub fn stop_latest() -> Result<VoicePlaybackStatus, String> {
    let id = VOICE
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .bus
        .as_ref()
        .and_then(VoiceBus::latest_music_id)
        .ok_or("audio_playback_not_playing")?;
    audio_voice_stop_instance(id)
}

#[tauri::command]
pub fn audio_voice_stop() -> VoicePlaybackStatus {
    let mut voice = VOICE.lock().unwrap_or_else(|e| e.into_inner());
    voice.request = voice.request.wrapping_add(1).max(1);
    voice.pending = 0;
    if let Some(bus) = voice.bus.as_mut() {
        if bus.has_music() {
            let _ = bus.stop_all_music();
        }
        if !bus.microphone_attached() {
            voice.bus = None;
        }
    }
    voice.last = VoicePlaybackStatus::idle();
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
        assert_eq!(audio_voice_stop().active_count, 0);
        assert_eq!(VOICE.lock().unwrap().pending, 0);
        let first = begin_engine_start(root).unwrap();
        assert!(begin_engine_start(root).is_err());
        assert_eq!(ENGINE_STARTING.load(Ordering::Acquire), 1);
        drop(first);
        assert_eq!(ENGINE_STARTING.load(Ordering::Acquire), 0);
    }

    #[test]
    fn voice_status_keeps_playback_fields_at_the_top_level() {
        let status = VoicePlaybackStatus {
            playback: PlaybackStatus {
                state: "playing",
                name: "clip".into(),
                played_frames: 1,
                length_frames: 2,
                sample_rate: 48000,
            },
            instance_id: Some(7),
            active_count: 2,
            looping: true,
        };
        let value = serde_json::to_value(status).unwrap();
        assert_eq!(value["state"], "playing");
        assert_eq!(value["instance_id"], 7);
        assert_eq!(value["active_count"], 2);
        assert_eq!(value["looping"], true);
        assert!(value.get("playback").is_none());
    }

    #[test]
    fn volume_changes_are_persistent_and_mute_keeps_the_level() {
        let nonce = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root =
            std::env::temp_dir().join(format!("fabric-volume-{}-{nonce}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        assert_eq!(volume_settings(&root).volume, 1.0);
        assert_eq!(adjust_volume(&root, -1).unwrap().volume, 0.9);
        let muted = toggle_mute(&root).unwrap();
        assert!(muted.muted);
        assert_eq!(muted.volume, 0.9);
        let raised = adjust_volume(&root, 1).unwrap();
        assert!(!raised.muted);
        assert_eq!(raised.volume, 1.0);
        assert_eq!(volume_settings(&root), raised);
        let _ = std::fs::remove_dir_all(root);
    }
}
