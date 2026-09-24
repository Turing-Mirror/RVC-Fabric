//! Persistent native voice-output bus. Music changes its mixer slot without
//! reopening the device; microphone PCM has a separate bounded input ring.
#[cfg(windows)]
use crate::audio_pcm_mapping::PcmMapping;
#[cfg(windows)]
use fabric_audio::pcm_bridge::Header;
use fabric_audio::{
    decode::{DecodedStream, Decoder},
    format::PcmFormat,
    output::{self, MusicControl, OutputStream, Track, TrackControl},
};
use rtrb::{Producer, RingBuffer};
#[cfg(windows)]
use std::{
    sync::atomic::AtomicBool,
    thread::JoinHandle,
    time::{SystemTime, UNIX_EPOCH},
};
use std::{
    sync::{atomic::Ordering, Arc},
    time::{Duration, Instant},
};

const MIC_BUFFER_SECONDS: f64 = 0.5;
const SWAP_TIMEOUT: Duration = Duration::from_millis(750);
// Only concurrent decoder/track resources are bounded; the library is not.
pub const MAX_MUSIC_INSTANCES: usize = 16;

#[derive(Clone, Copy)]
pub enum MusicPlacement {
    ReplaceAll,
    Overlay,
    ReplaceInstance(u64),
}

fn music_slot(
    placement: MusicPlacement,
    ids: impl Iterator<Item = Option<u64>>,
) -> Result<usize, String> {
    match placement {
        MusicPlacement::ReplaceAll => Ok(0),
        MusicPlacement::Overlay => ids
            .enumerate()
            .find_map(|(slot, id)| id.is_none().then_some(slot))
            .ok_or("audio_music_capacity_reached".into()),
        MusicPlacement::ReplaceInstance(target) => ids
            .enumerate()
            .find_map(|(slot, id)| (id == Some(target)).then_some(slot))
            .ok_or("audio_playback_cancelled".into()),
    }
}
#[cfg(windows)]
const BRIDGE_BUFFER_SECONDS: u32 = 1;
#[cfg(windows)]
const MIC_MAX_LAG_MS: u32 = 400;

#[derive(Clone)]
pub struct BridgeDescriptor {
    pub name: String,
    pub epoch: u64,
}

#[cfg(windows)]
struct MicReader {
    stop: Arc<AtomicBool>,
    failed: Arc<AtomicBool>,
    thread: Option<JoinHandle<Producer<f32>>>,
}

#[cfg(windows)]
impl MicReader {
    fn stop(mut self) -> Result<Producer<f32>, String> {
        self.stop.store(true, Ordering::Release);
        self.thread
            .take()
            .ok_or("pcm_bridge_thread_missing")?
            .join()
            .map_err(|_| "pcm_bridge_thread_failed".to_string())
    }
}

#[cfg(windows)]
impl Drop for MicReader {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

struct Music {
    id: u64,
    entry_id: String,
    name: String,
    length: u64,
    base_gain: f32,
    control: Arc<TrackControl>,
    decoder: Decoder,
}

impl Music {
    fn failed(&self) -> bool {
        self.decoder.state.failed.load(Ordering::Acquire)
            || (self.decoder.state.finished.load(Ordering::Acquire)
                && self.decoder.state.decoded_frames.load(Ordering::Acquire) == 0)
    }

    fn finished(&self) -> bool {
        self.failed()
            || self.control.played_frames.load(Ordering::Acquire) >= self.length
            || (self.decoder.state.finished.load(Ordering::Acquire)
                && self.control.played_frames.load(Ordering::Acquire)
                    >= self.decoder.state.decoded_frames.load(Ordering::Acquire))
    }
}

pub struct MusicSnapshot {
    pub id: u64,
    pub name: String,
    pub played: u64,
    pub length: u64,
    pub paused: bool,
    pub failed: bool,
}

pub struct VoiceBus {
    device_id: String,
    format: PcmFormat,
    output: OutputStream,
    music_control: MusicControl,
    music: Vec<Option<Music>>,
    mic_producer: Option<Producer<f32>>,
    #[cfg(windows)]
    mic_control: Arc<TrackControl>,
    #[cfg(windows)]
    mic_reader: Option<MicReader>,
}

impl VoiceBus {
    pub fn open(device_id: String) -> Result<Self, String> {
        let format = output::device_format(&device_id)?;
        let capacity = format.samples_for(MIC_BUFFER_SECONDS)?;
        let (mic_producer, mic_pcm) = RingBuffer::new(capacity);
        let (mic_track, mic_control) = Track::new(mic_pcm, None);
        mic_control.stopped.store(true, Ordering::Release);
        let tracks = (0..MAX_MUSIC_INSTANCES)
            .map(|_| Self::idle_track(format))
            .collect();
        let (mixer, music_control) = output::Mixer::with_music_tracks(format, mic_track, tracks)?;
        let output = output::open(&device_id, mixer)?;
        Ok(Self {
            device_id,
            format,
            output,
            music_control,
            music: (0..MAX_MUSIC_INSTANCES).map(|_| None).collect(),
            mic_producer: Some(mic_producer),
            #[cfg(windows)]
            mic_control,
            #[cfg(windows)]
            mic_reader: None,
        })
    }

    pub fn device_id(&self) -> &str {
        &self.device_id
    }

    pub fn format(&self) -> PcmFormat {
        self.format
    }

    pub fn failed(&self) -> bool {
        self.output.failed.load(Ordering::Acquire)
    }

    fn idle_track(format: PcmFormat) -> Track {
        let (_, pcm) = RingBuffer::new(format.channels as usize);
        let (track, control) = Track::new(pcm, None);
        control.stopped.store(true, Ordering::Release);
        track
    }

    #[cfg(windows)]
    pub fn attach_microphone(&mut self) -> Result<BridgeDescriptor, String> {
        if self.mic_reader.is_some() {
            return Err("pcm_bridge_already_attached".into());
        }
        let epoch = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|e| e.to_string())?
            .as_nanos() as u64;
        let header = Header {
            format: self.format,
            capacity_frames: self.format.sample_rate * BRIDGE_BUFFER_SECONDS,
            epoch: epoch.max(1),
        };
        let mapping = PcmMapping::create(header)?;
        let descriptor = BridgeDescriptor {
            name: mapping.name().to_string(),
            epoch: header.epoch,
        };
        let mut producer = self
            .mic_producer
            .take()
            .ok_or("pcm_bridge_producer_missing")?;
        let stop = Arc::new(AtomicBool::new(false));
        let stopping = stop.clone();
        let failed = Arc::new(AtomicBool::new(false));
        let failure = failed.clone();
        let channels = self.format.channels as usize;
        let max_lag = (self.format.sample_rate / 1000 * MIC_MAX_LAG_MS).max(1);
        let thread = std::thread::Builder::new()
            .name("fabric-microphone-bridge".into())
            .spawn(move || {
                let mut mapping = mapping;
                let mut samples = vec![0f32; 1024 * channels];
                while !stopping.load(Ordering::Acquire) {
                    let free_frames = (producer.slots() / channels).min(1024);
                    if free_frames == 0 {
                        std::thread::sleep(Duration::from_millis(2));
                        continue;
                    }
                    match mapping.read_into(&mut samples[..free_frames * channels], max_lag) {
                        Ok(0) => std::thread::sleep(Duration::from_millis(2)),
                        Ok(frames) => {
                            for frame in samples[..frames * channels].chunks_exact(channels) {
                                for sample in frame {
                                    let _ = producer.push(if sample.is_finite() {
                                        *sample
                                    } else {
                                        0.0
                                    });
                                }
                            }
                        }
                        Err(_) => {
                            failure.store(true, Ordering::Release);
                            break;
                        }
                    }
                }
                producer
            })
            .map_err(|e| e.to_string())?;
        self.mic_reader = Some(MicReader {
            stop,
            failed,
            thread: Some(thread),
        });
        self.mic_control.stopped.store(false, Ordering::Release);
        Ok(descriptor)
    }

    #[cfg(windows)]
    pub fn detach_microphone(&mut self) -> Result<(), String> {
        let Some(reader) = self.mic_reader.take() else {
            return Ok(());
        };
        self.mic_control.stopped.store(true, Ordering::Release);
        self.mic_producer = Some(reader.stop()?);
        self.mic_control.flush.store(true, Ordering::Release);
        let deadline = Instant::now() + SWAP_TIMEOUT;
        while self.mic_control.flush.load(Ordering::Acquire) {
            if self.failed() || Instant::now() >= deadline {
                return Err("pcm_bridge_flush_failed".into());
            }
            std::thread::sleep(Duration::from_millis(2));
        }
        Ok(())
    }

    fn swap_music(&mut self, slot: usize, track: Track) -> Result<(), String> {
        self.music_control
            .try_replace_at(slot, track)
            .map_err(|_| "audio_music_swap_busy".to_string())?;
        let deadline = Instant::now() + SWAP_TIMEOUT;
        loop {
            if let Some(old) = self.music_control.take_retired_at(slot) {
                drop(old);
                return Ok(());
            }
            if self.failed() || Instant::now() >= deadline {
                return Err("audio_music_swap_failed".into());
            }
            std::thread::sleep(Duration::from_millis(2));
        }
    }

    pub fn play_decoded(
        &mut self,
        id: u64,
        entry_id: String,
        name: String,
        decoded: DecodedStream,
        gain: f32,
        master_gain: f32,
        placement: MusicPlacement,
    ) -> Result<(), String> {
        if decoded.format != self.format {
            return Err("output_format_changed".into());
        }
        let length = decoded.range.frames();
        let (track, control) = Track::new(decoded.pcm, Some(length));
        control.set_gain(gain * master_gain)?;
        control.paused.store(true, Ordering::Release);
        let slot = music_slot(placement, self.music.iter().map(|music| music.as_ref().map(|m| m.id)))?;
        if let Err(error) = self.swap_music(slot, track) {
            // A timed-out command may still reach a live callback. Never let
            // that late track become audible after the caller saw an error.
            control.stopped.store(true, Ordering::Release);
            return Err(error);
        }
        if matches!(placement, MusicPlacement::ReplaceAll) {
            for music in self.music.iter().flatten().filter(|music| music.id != id) {
                music.control.stopped.store(true, Ordering::Release);
            }
        }
        self.music[slot] = Some(Music {
            id,
            entry_id,
            name,
            length,
            base_gain: gain,
            control: control.clone(),
            decoder: decoded.decoder,
        });
        control.paused.store(false, Ordering::Release);
        if matches!(placement, MusicPlacement::ReplaceAll) {
            let other_ids: Vec<_> = self
                .music
                .iter()
                .flatten()
                .filter(|music| music.id != id)
                .map(|music| music.id)
                .collect();
            for other_id in other_ids {
                self.stop_music(other_id)?;
            }
        }
        Ok(())
    }

    pub fn pause(&mut self, id: u64, paused: bool) -> Result<(), String> {
        let music = self
            .music
            .iter()
            .flatten()
            .find(|music| music.id == id)
            .ok_or("audio_playback_not_playing")?;
        music.control.paused.store(paused, Ordering::Release);
        Ok(())
    }

    pub fn set_master_gain(&mut self, gain: f32) -> Result<(), String> {
        for music in self.music.iter().flatten() {
            music.control.set_gain(music.base_gain * gain)?;
        }
        Ok(())
    }

    pub fn stop_music(&mut self, id: u64) -> Result<(), String> {
        let slot = self
            .music
            .iter()
            .position(|music| music.as_ref().is_some_and(|m| m.id == id))
            .ok_or("audio_playback_not_playing")?;
        self.music[slot]
            .as_ref()
            .unwrap()
            .control
            .stopped
            .store(true, Ordering::Release);
        self.swap_music(slot, Self::idle_track(self.format))?;
        self.music[slot] = None;
        Ok(())
    }

    pub fn stop_all_music(&mut self) -> Result<(), String> {
        for music in self.music.iter().flatten() {
            music.control.stopped.store(true, Ordering::Release);
        }
        let ids = self.music_ids();
        for id in ids {
            self.stop_music(id)?;
        }
        Ok(())
    }

    pub fn music_status(&self, id: u64) -> Option<MusicSnapshot> {
        let music = self.music.iter().flatten().find(|music| music.id == id)?;
        Some(MusicSnapshot {
            id,
            name: music.name.clone(),
            played: music.control.played_frames.load(Ordering::Acquire),
            length: music.length,
            paused: music.control.paused.load(Ordering::Acquire),
            failed: music.failed(),
        })
    }

    pub fn music_entry_id(&self, id: u64) -> Option<&str> {
        self.music.iter().flatten().find(|music| music.id == id)
            .map(|music| music.entry_id.as_str())
    }

    pub fn music_ids(&self) -> Vec<u64> {
        self.music.iter().flatten().map(|music| music.id).collect()
    }

    pub fn music_finished(&self, id: u64) -> bool {
        self.music
            .iter()
            .flatten()
            .find(|music| music.id == id)
            .is_some_and(Music::finished)
    }

    pub fn latest_music_id(&self) -> Option<u64> {
        self.music.iter().flatten().map(|music| music.id).max()
    }

    pub fn music_count(&self) -> usize {
        self.music.iter().flatten().count()
    }

    pub fn has_music(&self) -> bool {
        self.music.iter().any(Option::is_some)
    }

    pub fn microphone_attached(&self) -> bool {
        self.mic_producer.is_none()
    }

    pub fn microphone_failed(&self) -> bool {
        #[cfg(windows)]
        if let Some(reader) = self.mic_reader.as_ref() {
            return reader.failed.load(Ordering::Acquire)
                || reader.thread.as_ref().is_some_and(JoinHandle::is_finished);
        }
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn replay_reuses_only_its_own_slot_and_rejects_a_stopped_target() {
        let ids = [Some(11), Some(12), None];
        assert_eq!(music_slot(MusicPlacement::ReplaceInstance(12), ids.into_iter()).unwrap(), 1);
        assert_eq!(music_slot(MusicPlacement::Overlay, ids.into_iter()).unwrap(), 2);
        assert_eq!(music_slot(MusicPlacement::ReplaceAll, ids.into_iter()).unwrap(), 0);
        assert_eq!(music_slot(MusicPlacement::ReplaceInstance(9), ids.into_iter()).unwrap_err(),
            "audio_playback_cancelled");
    }
}
