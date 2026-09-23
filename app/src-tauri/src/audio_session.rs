//! Shared native playback lifecycle for private preview and voice-output audio.
//! Decoding and stream transitions run off the audio callback.
use fabric_audio::{
    decode::{self, AudioTools, Decoder},
    format::ClipRange,
    output::{self, OutputStream, Track, TrackControl},
};
use serde::Serialize;
use std::{
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::Duration,
};

pub struct Source {
    pub name: String,
    pub path: PathBuf,
    pub range: ClipRange,
    pub gain: f32,
}

pub fn entry(root: &Path, entry_id: &str) -> Result<Source, String> {
    let library = crate::audio_library::snapshot(root)?;
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
    Ok(Source {
        name: entry.name.clone(),
        path: PathBuf::from(&asset.path),
        range: ClipRange {
            start: entry.start,
            end: entry.end,
        },
        gain: entry.volume,
    })
}

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
pub struct PlaybackStatus {
    pub state: &'static str,
    pub name: String,
    pub played_frames: u64,
    pub length_frames: u64,
    pub sample_rate: u32,
}

impl PlaybackStatus {
    const fn idle() -> Self {
        Self {
            state: "idle",
            name: String::new(),
            played_frames: 0,
            length_frames: 0,
            sample_rate: 0,
        }
    }
}

fn status_of(session: &Session) -> PlaybackStatus {
    let failed = session.stream.failed.load(Ordering::Acquire)
        || session.decoder.state.failed.load(Ordering::Acquire);
    PlaybackStatus {
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

pub struct Player {
    request: AtomicU64,
    pending: AtomicU64,
    transition: Mutex<()>,
    current: Mutex<Option<Session>>,
    last: Mutex<PlaybackStatus>,
}

impl Player {
    pub const fn new() -> Self {
        Self {
            request: AtomicU64::new(0),
            pending: AtomicU64::new(0),
            transition: Mutex::new(()),
            current: Mutex::new(None),
            last: Mutex::new(PlaybackStatus::idle()),
        }
    }

    pub fn reserve(&self) -> u64 {
        let id = self.request.fetch_add(1, Ordering::AcqRel) + 1;
        self.pending.store(id, Ordering::Release);
        id
    }

    pub fn release(&self, id: u64) {
        let _ = self
            .pending
            .compare_exchange(id, 0, Ordering::AcqRel, Ordering::Acquire);
    }

    pub fn busy(&self) -> bool {
        self.pending.load(Ordering::Acquire) != 0
            || self
                .current
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .is_some()
    }

    pub fn start(
        &'static self,
        root: &Path,
        id: u64,
        source: Source,
        device_id: &str,
    ) -> Result<PlaybackStatus, String> {
        let format = output::device_format(device_id)?;
        let decoded = decode::decode(
            &AudioTools::at(root),
            &source.path,
            source.range,
            format,
            0.25,
        )?;
        let length = decoded.range.frames();
        let (track, control) = Track::new(decoded.pcm, Some(length));
        control.set_gain(source.gain)?;
        control.paused.store(true, Ordering::Release);

        // Only one stream owns this output at a time. The next stream starts
        // silent, and a late decode cannot revive a stopped/replaced request.
        let _transition = self.transition.lock().unwrap_or_else(|e| e.into_inner());
        if id != self.request.load(Ordering::Acquire) {
            return Err("audio_playback_cancelled".into());
        }
        let previous = self
            .current
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .take();
        drop(previous);
        let stream = output::open(device_id, output::Mixer::new(format, vec![track])?)?;
        let session = Session {
            id,
            name: source.name,
            length,
            sample_rate: format.sample_rate,
            control: control.clone(),
            decoder: decoded.decoder,
            stream,
        };
        if id != self.request.load(Ordering::Acquire) {
            return Err("audio_playback_cancelled".into());
        }
        let mut current = self.current.lock().unwrap_or_else(|e| e.into_inner());
        *current = Some(session);
        *self.last.lock().unwrap_or_else(|e| e.into_inner()) = PlaybackStatus::idle();
        let status = status_of(current.as_ref().unwrap());
        drop(current);
        control.paused.store(false, Ordering::Release);
        std::thread::spawn(move || self.watch(id));
        Ok(PlaybackStatus {
            state: "playing",
            ..status
        })
    }

    fn watch(&'static self, id: u64) {
        loop {
            std::thread::sleep(Duration::from_millis(50));
            let mut guard = self.current.lock().unwrap_or_else(|e| e.into_inner());
            let Some(active) = guard.as_ref() else { break };
            if active.id != id {
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
                *self.last.lock().unwrap_or_else(|e| e.into_inner()) = status;
                let completed = guard.take();
                drop(guard);
                drop(completed);
                break;
            }
        }
    }

    pub fn status(&self) -> PlaybackStatus {
        let current = self.current.lock().unwrap_or_else(|e| e.into_inner());
        if let Some(session) = current.as_ref() {
            status_of(session)
        } else {
            self.last.lock().unwrap_or_else(|e| e.into_inner()).clone()
        }
    }

    pub fn pause(&self, paused: bool) -> Result<PlaybackStatus, String> {
        let guard = self.current.lock().unwrap_or_else(|e| e.into_inner());
        let session = guard.as_ref().ok_or("audio_playback_not_playing")?;
        session.control.paused.store(paused, Ordering::Release);
        Ok(status_of(session))
    }

    pub fn stop(&self) -> PlaybackStatus {
        self.request.fetch_add(1, Ordering::AcqRel);
        self.pending.store(0, Ordering::Release);
        let old = self
            .current
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .take();
        drop(old);
        *self.last.lock().unwrap_or_else(|e| e.into_inner()) = PlaybackStatus::idle();
        PlaybackStatus::idle()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stopped_or_replaced_requests_cannot_remain_pending() {
        let player = Player::new();
        let first = player.reserve();
        assert!(player.busy());
        let second = player.reserve();
        player.release(first);
        assert!(player.busy());
        player.stop();
        player.release(second);
        assert!(!player.busy());
    }
}
