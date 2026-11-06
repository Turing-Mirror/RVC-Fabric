use fabric_audio::{
    decode::{self, AudioTools, ClipOptions, DecodedStream},
    format::PcmFormat,
};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    path::Path,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
};

pub struct Clip {
    stream: DecodedStream,
    looping: Arc<AtomicBool>,
    paused: bool,
    gain: f32,
    position: u64,
    entry: crate::audio_library::Entry,
}
impl Clip {
    pub fn prepare(root: &Path, id: &str, offset: f64) -> Result<Self, String> {
        let library = crate::audio_library::snapshot(root)?;
        let entry = library
            .entries
            .iter()
            .find(|e| e.id == id)
            .ok_or("unknown_clip")?
            .clone();
        let asset = library
            .assets
            .iter()
            .find(|a| a.id == entry.asset_id)
            .ok_or("unknown_clip")?;
        let path = std::path::PathBuf::from(&asset.path);
        let path = if path.is_absolute() {
            path
        } else {
            root.join(path)
        };
        let looping = Arc::new(AtomicBool::new(entry.looped));
        let range = fabric_audio::format::ClipRange {
            start: entry.start,
            end: entry.end,
        };
        let stream = decode::decode_clip(
            &AudioTools::at(root),
            &path,
            range,
            PcmFormat {
                sample_rate: 48000,
                channels: 1,
            },
            2.0,
            ClipOptions {
                offset_frames: (offset.max(0.0) * 48000.0) as u64,
                looping: Some(looping.clone()),
                edge_fade_seconds: 0.008,
            },
        )?;
        Ok(Self {
            stream,
            looping,
            paused: false,
            gain: entry.volume,
            position: (offset * 48000.0) as u64,
            entry,
        })
    }
}
#[derive(Default)]
pub struct Clips {
    tracks: BTreeMap<String, Clip>,
    pub gain: f32,
}
impl Clips {
    pub fn new() -> Self {
        Self {
            gain: 1.0,
            ..Default::default()
        }
    }
    pub fn can_play(&self, id: &str, seek: bool) -> Result<(), String> {
        if seek && !self.tracks.contains_key(id) {
            return Err("unknown_track".into());
        }
        if !self.tracks.contains_key(id) && self.tracks.len() >= 16 {
            return Err("clip_limit".into());
        }
        Ok(())
    }
    pub fn replace(
        &mut self,
        id: &str,
        mut clip: Clip,
        seek: bool,
    ) -> Result<Option<Clip>, String> {
        self.can_play(id, seek)?;
        if seek {
            let old = self.tracks.get(id).ok_or("unknown_track")?;
            clip.paused = old.paused;
            clip.gain = old.gain;
            clip.looping
                .store(old.looping.load(Ordering::Acquire), Ordering::Release);
        }
        Ok(self.tracks.insert(id.into(), clip))
    }
    // Return retired decoders so the caller can reap them outside the audio mutex.
    pub fn control(&mut self, id: &str, action: &str, value: &Value) -> Result<Vec<Clip>, String> {
        if action == "stop_all" {
            return Ok(std::mem::take(&mut self.tracks).into_values().collect());
        }
        if action == "stop" {
            return Ok(self.tracks.remove(id).into_iter().collect());
        }
        let track = self.tracks.get_mut(id).ok_or("unknown_track")?;
        match action {
            "pause" => track.paused = value.as_bool().ok_or("invalid_setting")?,
            "loop" => track
                .looping
                .store(value.as_bool().ok_or("invalid_setting")?, Ordering::Release),
            "volume" | "gain" => {
                track.gain = value
                    .as_f64()
                    .filter(|v| v.is_finite() && *v >= 0.0 && *v <= 2.0)
                    .ok_or("invalid_setting")? as f32
            }
            _ => return Err("unknown_command".into()),
        }
        Ok(Vec::new())
    }
    pub fn mix(&mut self, pcm: &mut [f32]) -> Vec<Clip> {
        for clip in self.tracks.values_mut().filter(|c| !c.paused) {
            for sample in pcm.iter_mut() {
                if let Ok(value) = clip.stream.pcm.pop() {
                    *sample += value * clip.gain;
                    clip.position += 1;
                    let frames = clip.stream.range.frames();
                    if frames > 0 && clip.looping.load(Ordering::Acquire) {
                        clip.position %= frames;
                    }
                }
            }
        }
        let finished: Vec<String> = self
            .tracks
            .iter()
            .filter(|(_, c)| {
                c.stream.decoder.state.finished.load(Ordering::Acquire) && c.stream.pcm.is_empty()
            })
            .map(|(id, _)| id.clone())
            .collect();
        let retired = finished
            .into_iter()
            .filter_map(|id| self.tracks.remove(&id))
            .collect();
        for sample in pcm {
            *sample = (*sample * self.gain).clamp(-1.0, 1.0);
        }
        retired
    }
    pub fn status(&self) -> Value {
        json!(self.tracks.iter().map(|(id,c)|json!({"id":id,"name":c.entry.name,"paused":c.paused,"pos":c.position,
        "position":c.position as f64/48000.0,"duration":c.stream.range.frames()as f64/48000.0,"gain":c.gain,"loop":c.looping.load(Ordering::Acquire)})).collect::<Vec<_>>())
    }
}
