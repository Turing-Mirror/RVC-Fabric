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
    resample::Converter,
};
use rtrb::{Producer, RingBuffer};
#[cfg(windows)]
use std::{
    sync::atomic::AtomicBool,
    thread::JoinHandle,
    time::{SystemTime, UNIX_EPOCH},
};
use std::{
    sync::{
        atomic::{AtomicBool as LoopFlag, Ordering},
        Arc, Mutex,
    },
    time::{Duration, Instant},
};

const MIC_BUFFER_SECONDS: f64 = 0.5;
/// Microphone copied to the local output drops input beyond this much backlog,
/// so a slower local clock never turns into growing monitor delay.
const MONITOR_MAX_LAG_SECONDS: f64 = 0.06;
const SWAP_TIMEOUT: Duration = Duration::from_millis(750);
/// Start, pause, stop and replacement ramp over this long instead of clicking.
const FADE_SECONDS: f64 = 0.008;
const FADE_TIMEOUT: Duration = Duration::from_millis(120);
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
    /// The shell plays the microphone on the local output; the worker must not
    /// open its own monitor stream.
    pub monitor: bool,
}

/// Microphone PCM handed from the voice bus to the local output's mixer.
pub struct MicTee {
    producer: Producer<f32>,
    converter: Converter,
    capacity: usize,
    max_fill: usize,
}

impl MicTee {
    fn push(&mut self, samples: &[f32]) {
        if self.capacity - self.producer.slots() > self.max_fill {
            return;
        }
        let producer = &mut self.producer;
        self.converter.process(samples, |frame| {
            if producer.slots() >= frame.len() {
                for sample in frame {
                    let _ = producer.push(*sample);
                }
            }
        });
    }
}

type TeeSlot = Arc<Mutex<Option<MicTee>>>;

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
    /// Whole clip in output frames.
    length: u64,
    /// Where in the clip the current decode started (seek).
    offset: u64,
    looping: Arc<LoopFlag>,
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

    /// The decoder caps every pass at the clip end, so everything it produced
    /// having been played is the end, looping or not.
    fn finished(&self) -> bool {
        self.failed()
            || (self.decoder.state.finished.load(Ordering::Acquire)
                && self.control.played_frames.load(Ordering::Acquire)
                    >= self.decoder.state.decoded_frames.load(Ordering::Acquire))
    }

    fn position(&self) -> u64 {
        clip_position(
            self.offset + self.control.played_frames.load(Ordering::Acquire),
            self.length,
        )
    }
}

/// Position within the clip after any number of loop passes; the exact end of
/// a pass reads as the end, not as zero.
fn clip_position(frames: u64, length: u64) -> u64 {
    if length == 0 || frames <= length {
        frames
    } else {
        (frames - 1) % length + 1
    }
}

pub struct MusicSnapshot {
    pub id: u64,
    pub entry_id: String,
    pub name: String,
    pub played: u64,
    pub length: u64,
    pub paused: bool,
    pub looping: bool,
    pub failed: bool,
}

pub struct NewMusic {
    pub id: u64,
    pub entry_id: String,
    pub name: String,
    pub decoded: DecodedStream,
    pub offset: u64,
    pub looping: Arc<LoopFlag>,
    pub paused: bool,
    pub gain: f32,
    pub master_gain: f32,
    pub placement: MusicPlacement,
}

pub struct VoiceBus {
    device_id: String,
    format: PcmFormat,
    output: OutputStream,
    music_control: MusicControl,
    music: Vec<Option<Music>>,
    mic_producer: Option<Producer<f32>>,
    mic_control: Arc<TrackControl>,
    /// Filled while this bus's microphone is also played on the local output.
    mic_tee: TeeSlot,
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
            mic_control,
            mic_tee: Arc::new(Mutex::new(None)),
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
            monitor: false,
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
        let tee = self.mic_tee.clone();
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
                            let block = &mut samples[..frames * channels];
                            for sample in block.iter_mut() {
                                if !sample.is_finite() {
                                    *sample = 0.0;
                                }
                            }
                            for sample in block.iter() {
                                let _ = producer.push(*sample);
                            }
                            if let Some(tee) = tee.lock().unwrap_or_else(|e| e.into_inner()).as_mut() {
                                tee.push(block);
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

    /// Ask the callback to ramp a track down and give it one fade to finish.
    fn fade_out(&self, control: &TrackControl) {
        control.stopped.store(true, Ordering::Release);
        let deadline = Instant::now() + FADE_TIMEOUT;
        while !control.faded_out.load(Ordering::Acquire)
            && !self.failed()
            && Instant::now() < deadline
        {
            std::thread::sleep(Duration::from_millis(1));
        }
    }

    fn fade_frames(&self) -> u32 {
        (self.format.sample_rate as f64 * FADE_SECONDS).round() as u32
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

    pub fn play_decoded(&mut self, next: NewMusic) -> Result<(), String> {
        let NewMusic {
            id,
            entry_id,
            name,
            decoded,
            offset,
            looping,
            paused,
            gain,
            master_gain,
            placement,
        } = next;
        if decoded.format != self.format {
            return Err("output_format_changed".into());
        }
        let length = decoded.range.frames();
        let (track, control) = Track::with_fade(decoded.pcm, None, self.fade_frames());
        control.set_gain(gain * master_gain)?;
        control.paused.store(true, Ordering::Release);
        let slot = music_slot(placement, self.music.iter().map(|music| music.as_ref().map(|m| m.id)))?;
        if let Some(current) = self.music[slot].as_ref() {
            self.fade_out(&current.control);
        }
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
            offset,
            looping,
            base_gain: gain,
            control: control.clone(),
            decoder: decoded.decoder,
        });
        control.paused.store(paused, Ordering::Release);
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

    pub fn set_looping(&mut self, id: u64, looping: bool) -> Result<(), String> {
        let music = self
            .music
            .iter()
            .flatten()
            .find(|music| music.id == id)
            .ok_or("audio_playback_not_playing")?;
        music.looping.store(looping, Ordering::Release);
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
        self.fade_out(&self.music[slot].as_ref().unwrap().control);
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
            entry_id: music.entry_id.clone(),
            name: music.name.clone(),
            played: music.position(),
            length: music.length,
            paused: music.control.paused.load(Ordering::Acquire),
            looping: music.looping.load(Ordering::Acquire),
            failed: music.failed(),
        })
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
        #[cfg(windows)]
        return self.mic_reader.is_some();
        #[cfg(not(windows))]
        false
    }

    /// Hand this bus's microphone track to another bus's reader, converting
    /// from `source` to this device's format.
    pub fn take_monitor_input(&mut self, source: PcmFormat) -> Result<MicTee, String> {
        if self.microphone_attached() {
            return Err("pcm_bridge_already_attached".into());
        }
        let producer = self.mic_producer.take().ok_or("audio_monitor_input_taken")?;
        let capacity = producer.buffer().capacity();
        let tee = Converter::new(source, self.format).map(|converter| MicTee {
            capacity,
            max_fill: self
                .format
                .samples_for(MONITOR_MAX_LAG_SECONDS)
                .unwrap_or(capacity)
                .min(capacity),
            producer,
            converter,
        });
        match tee {
            Ok(tee) => {
                self.mic_control.stopped.store(false, Ordering::Release);
                Ok(tee)
            }
            Err(error) => Err(error),
        }
    }

    /// Take the microphone track back and drop what it still holds.
    pub fn return_monitor_input(&mut self, tee: MicTee) {
        self.mic_control.stopped.store(true, Ordering::Release);
        self.mic_control.flush.store(true, Ordering::Release);
        self.mic_producer = Some(tee.producer);
    }

    pub fn monitoring_input(&self) -> bool {
        self.mic_producer.is_none() && !self.microphone_attached()
    }

    /// Install or remove the copy of this bus's microphone; returns the previous one.
    pub fn set_mic_tee(&self, tee: Option<MicTee>) -> Option<MicTee> {
        std::mem::replace(&mut *self.mic_tee.lock().unwrap_or_else(|e| e.into_inner()), tee)
    }

    pub fn has_mic_tee(&self) -> bool {
        self.mic_tee.lock().unwrap_or_else(|e| e.into_inner()).is_some()
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

    #[test]
    fn microphone_copy_converts_and_drops_input_instead_of_building_delay() {
        let (producer, mut consumer) = RingBuffer::new(64);
        let mut tee = MicTee {
            capacity: 64,
            max_fill: 8,
            producer,
            converter: Converter::new(
                PcmFormat { sample_rate: 48000, channels: 1 },
                PcmFormat { sample_rate: 48000, channels: 2 },
            )
            .unwrap(),
        };
        tee.push(&[0.1, 0.2, 0.3]);
        let mut got = Vec::new();
        while let Ok(sample) = consumer.pop() {
            got.push(sample);
        }
        assert_eq!(got, [0.1, 0.1, 0.2, 0.2]);
        // Nobody drains: once the backlog passes the limit, input is dropped.
        for _ in 0..20 {
            tee.push(&[0.5; 4]);
        }
        let backlog = 64 - tee.producer.slots();
        assert!(backlog <= 8 + 8, "{backlog}");
    }

    #[test]
    fn loop_position_wraps_but_the_end_of_a_pass_reads_as_the_end() {
        assert_eq!(clip_position(0, 100), 0);
        assert_eq!(clip_position(100, 100), 100);
        assert_eq!(clip_position(101, 100), 1);
        assert_eq!(clip_position(250, 100), 50);
        assert_eq!(clip_position(300, 100), 100);
    }
}
