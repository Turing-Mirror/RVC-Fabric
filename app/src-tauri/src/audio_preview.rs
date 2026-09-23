//! Native local preview. The device is always explicit and never follows the OS default.
use fabric_audio::{
    decode::{self, AudioTools, Decoder},
    format::ClipRange,
    output::{self, OutputStream, Track, TrackControl},
};
use serde::Serialize;
use std::{
    path::Path,
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::Duration,
};
use tauri::State;

static REQUEST: AtomicU64 = AtomicU64::new(0);
static CURRENT: Mutex<Option<Session>> = Mutex::new(None);
static LAST: Mutex<PreviewStatus> = Mutex::new(PreviewStatus {
    state: "idle",
    name: String::new(),
    played_frames: 0,
    length_frames: 0,
    sample_rate: 0,
});

struct Session {
    id: u64,
    name: String,
    length: u64,
    sample_rate: u32,
    control: Arc<TrackControl>,
    decoder: Decoder,
    stream: OutputStream,
}

#[derive(Clone, Serialize)]
pub struct PreviewStatus {
    pub state: &'static str,
    pub name: String,
    pub played_frames: u64,
    pub length_frames: u64,
    pub sample_rate: u32,
}

fn status_of(session: &Session) -> PreviewStatus {
    let failed = session.stream.failed.load(Ordering::Acquire)
        || session.decoder.state.failed.load(Ordering::Acquire);
    PreviewStatus {
        state: if failed {
            "error"
        } else if session.control.paused.load(Ordering::Acquire) {
            "paused"
        } else {
            "playing"
        },
        name: session.name.clone(),
        played_frames: session.control.played_frames.load(Ordering::Acquire),
        length_frames: session.length,
        sample_rate: session.sample_rate,
    }
}

fn idle() -> PreviewStatus {
    PreviewStatus {
        state: "idle",
        name: String::new(),
        played_frames: 0,
        length_frames: 0,
        sample_rate: 0,
    }
}

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
    let voice_device = crate::config::read(root)
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
) -> Result<PreviewStatus, String> {
    let root = crate::root_clone(&state)?;
    let request = REQUEST.fetch_add(1, Ordering::AcqRel) + 1;
    tauri::async_runtime::spawn_blocking(move || {
        preview_device_allowed(&root, &device_id)?;
        let library = crate::audio_library::snapshot(&root)?;
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
        if !asset.available || asset.excluded_source_ids.len() == asset.source_ids.len() {
            return Err("audio_entry_unavailable".into());
        }
        let format = output::device_format(&device_id)?;
        let decoded = decode::decode(
            &AudioTools::at(&root),
            Path::new(&asset.path),
            ClipRange {
                start: entry.start,
                end: entry.end,
            },
            format,
            0.25,
        )?;
        let length = decoded.range.frames();
        let (track, control) = Track::new(decoded.pcm, Some(length));
        control.paused.store(true, Ordering::Release);
        let stream = output::open(&device_id, output::Mixer::new(format, vec![track])?)?;
        let session = Session {
            id: request,
            name: entry.name.clone(),
            length,
            sample_rate: format.sample_rate,
            control,
            decoder: decoded.decoder,
            stream,
        };
        if request != REQUEST.load(Ordering::Acquire) {
            return Err("audio_preview_cancelled".into());
        }
        let mut current = CURRENT.lock().unwrap_or_else(|e| e.into_inner());
        if request != REQUEST.load(Ordering::Acquire) {
            return Err("audio_preview_cancelled".into());
        }
        let previous = current.replace(session);
        *LAST.lock().unwrap_or_else(|e| e.into_inner()) = idle();
        let status = status_of(current.as_ref().unwrap());
        let control = current.as_ref().unwrap().control.clone();
        drop(current);
        drop(previous);
        // Never let the old and new preview streams emit samples together.
        control.paused.store(false, Ordering::Release);
        std::thread::spawn(move || loop {
            std::thread::sleep(Duration::from_millis(50));
            let mut guard = CURRENT.lock().unwrap_or_else(|e| e.into_inner());
            let Some(active) = guard.as_ref() else { break };
            if active.id != request {
                break;
            }
            let played = active.control.played_frames.load(Ordering::Acquire);
            let finished = active.decoder.state.finished.load(Ordering::Acquire);
            let actual = active.decoder.state.decoded_frames.load(Ordering::Acquire);
            let failed = active.stream.failed.load(Ordering::Acquire)
                || active.decoder.state.failed.load(Ordering::Acquire);
            if failed || (finished && played >= actual) || played >= active.length {
                let mut status = status_of(active);
                status.state = if failed || actual == 0 {
                    "error"
                } else {
                    "ended"
                };
                *LAST.lock().unwrap_or_else(|e| e.into_inner()) = status;
                let completed = guard.take();
                drop(guard);
                drop(completed);
                break;
            }
        });
        Ok(PreviewStatus {
            state: "playing",
            ..status
        })
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
pub fn audio_preview_status() -> PreviewStatus {
    let current = CURRENT.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(session) = current.as_ref() {
        status_of(session)
    } else {
        LAST.lock().unwrap_or_else(|e| e.into_inner()).clone()
    }
}

#[tauri::command]
pub fn audio_preview_pause(paused: bool) -> Result<PreviewStatus, String> {
    let guard = CURRENT.lock().unwrap_or_else(|e| e.into_inner());
    let session = guard.as_ref().ok_or("audio_preview_not_playing")?;
    session.control.paused.store(paused, Ordering::Release);
    Ok(status_of(session))
}

#[tauri::command]
pub fn audio_preview_stop() -> PreviewStatus {
    REQUEST.fetch_add(1, Ordering::AcqRel);
    let old = CURRENT.lock().unwrap_or_else(|e| e.into_inner()).take();
    drop(old);
    *LAST.lock().unwrap_or_else(|e| e.into_inner()) = idle();
    idle()
}
