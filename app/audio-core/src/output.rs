use crate::format::PcmFormat;
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use rtrb::{Consumer, Producer, RingBuffer};
use serde::Serialize;
use std::sync::{
    atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering},
    Arc,
};

pub struct TrackControl {
    pub paused: AtomicBool,
    pub stopped: AtomicBool,
    pub flush: AtomicBool,
    pub played_frames: AtomicU64,
    pub underrun_frames: AtomicU64,
    gain: AtomicU32,
}
impl Default for TrackControl {
    fn default() -> Self {
        Self {
            paused: AtomicBool::new(false),
            stopped: AtomicBool::new(false),
            flush: AtomicBool::new(false),
            played_frames: AtomicU64::new(0),
            underrun_frames: AtomicU64::new(0),
            gain: AtomicU32::new(1.0f32.to_bits()),
        }
    }
}
impl TrackControl {
    pub fn set_gain(&self, value: f32) -> Result<(), String> {
        if !value.is_finite() || value < 0.0 {
            return Err("invalid_audio_gain".into());
        }
        self.gain.store(value.to_bits(), Ordering::Relaxed);
        Ok(())
    }
}
pub struct Track {
    pcm: Consumer<f32>,
    control: Arc<TrackControl>,
    length: Option<u64>,
}
impl Track {
    pub fn new(pcm: Consumer<f32>, length: Option<u64>) -> (Self, Arc<TrackControl>) {
        let control = Arc::new(TrackControl::default());
        (
            Self {
                pcm,
                control: control.clone(),
                length,
            },
            control,
        )
    }
}
/// Construction happens off callback. Each input is already converted to this format.
pub struct Mixer {
    format: PcmFormat,
    tracks: Vec<Track>,
    scratch: Vec<f32>,
    music_swap: Vec<MusicSwapCallback>,
}

struct MusicSwapCallback {
    incoming: Consumer<Track>,
    retired: Producer<Track>,
}

/// SPSC control plane. The callback only moves a prepared track between
/// preallocated queues; old decoder/ring memory is reclaimed by the owner.
pub struct MusicControl {
    slots: Vec<MusicSlotControl>,
}

struct MusicSlotControl {
    incoming: Producer<Track>,
    retired: Consumer<Track>,
}

impl MusicControl {
    pub fn try_replace(&mut self, track: Track) -> Result<(), Track> {
        self.try_replace_at(0, track)
    }

    pub fn try_replace_at(&mut self, slot: usize, track: Track) -> Result<(), Track> {
        let Some(control) = self.slots.get_mut(slot) else {
            return Err(track);
        };
        control.incoming.push(track).map_err(|error| match error {
            rtrb::PushError::Full(track) => track,
        })
    }

    pub fn take_retired(&mut self) -> Option<Track> {
        self.take_retired_at(0)
    }

    pub fn take_retired_at(&mut self, slot: usize) -> Option<Track> {
        self.slots.get_mut(slot)?.retired.pop().ok()
    }

    pub fn slot_count(&self) -> usize {
        self.slots.len()
    }
}
impl Mixer {
    pub fn new(format: PcmFormat, tracks: Vec<Track>) -> Result<Self, String> {
        format.validate()?;
        Ok(Self {
            format,
            tracks,
            scratch: vec![0.0; format.channels as usize],
            music_swap: Vec::new(),
        })
    }

    /// The first track is microphone PCM; the second is replaceable music.
    /// Both tracks must already use the output device's PCM format.
    pub fn with_music_slot(
        format: PcmFormat,
        microphone: Track,
        music: Track,
    ) -> Result<(Self, MusicControl), String> {
        Self::with_music_tracks(format, microphone, vec![music])
    }

    /// Reserve all music slots before the output stream starts. Every slot
    /// has its own bounded command and retirement queue, so adding or removing
    /// a music track never allocates or drops it in the audio callback.
    pub fn with_music_tracks(
        format: PcmFormat,
        microphone: Track,
        music: Vec<Track>,
    ) -> Result<(Self, MusicControl), String> {
        if music.is_empty() {
            return Err("audio_music_slots_empty".into());
        }
        let count = music.len();
        let mut tracks = Vec::with_capacity(count + 1);
        tracks.push(microphone);
        tracks.extend(music);
        let mut mixer = Self::new(format, tracks)?;
        let mut slots = Vec::with_capacity(count);
        mixer.music_swap.reserve(count);
        for _ in 0..count {
            let (incoming, callback_incoming) = RingBuffer::new(1);
            let (callback_retired, retired) = RingBuffer::new(1);
            mixer.music_swap.push(MusicSwapCallback {
                incoming: callback_incoming,
                retired: callback_retired,
            });
            slots.push(MusicSlotControl { incoming, retired });
        }
        Ok((mixer, MusicControl { slots }))
    }

    fn apply_music_swap(&mut self) {
        for (slot, control) in self.music_swap.iter_mut().enumerate() {
            // Do not pop a command unless the old track can be handed back.
            if control.retired.slots() == 0 {
                continue;
            }
            if let Ok(next) = control.incoming.pop() {
                let old = std::mem::replace(&mut self.tracks[slot + 1], next);
                let _ = control.retired.push(old);
            }
        }
    }
    pub fn format(&self) -> PcmFormat {
        self.format
    }
    pub fn render<T: cpal::Sample + cpal::FromSample<f32>>(&mut self, data: &mut [T]) {
        self.apply_music_swap();
        for track in &mut self.tracks {
            if track.control.flush.swap(false, Ordering::AcqRel) {
                while track.pcm.pop().is_ok() {}
                track.control.played_frames.store(0, Ordering::Release);
            }
        }
        let channels = self.format.channels as usize;
        // Whole-frame consumption avoids channel skew on starvation.
        let mut frames = data.chunks_exact_mut(channels);
        for frame in &mut frames {
            self.scratch.fill(0.0);
            for track in &mut self.tracks {
                let ctl = &track.control;
                if ctl.paused.load(Ordering::Relaxed) || ctl.stopped.load(Ordering::Relaxed) {
                    continue;
                }
                let position = ctl.played_frames.load(Ordering::Relaxed);
                if track.length.is_some_and(|n| position >= n) {
                    continue;
                }
                if track.pcm.slots() < channels {
                    ctl.underrun_frames.fetch_add(1, Ordering::Relaxed);
                    continue;
                }
                let gain = f32::from_bits(ctl.gain.load(Ordering::Relaxed));
                for value in &mut self.scratch {
                    let sample = track.pcm.pop().unwrap_or(0.0);
                    *value += if sample.is_finite() {
                        sample * gain
                    } else {
                        0.0
                    };
                }
                ctl.played_frames.fetch_add(1, Ordering::Relaxed);
            }
            // Linked-channel peak control preserves stereo balance; no lookahead latency.
            let peak = self.scratch.iter().fold(1.0f32, |p, v| p.max(v.abs()));
            for (out, sample) in frame.iter_mut().zip(&self.scratch) {
                *out = T::from_sample(if sample.is_finite() {
                    sample / peak
                } else {
                    0.0
                });
            }
        }
        for sample in frames.into_remainder() {
            *sample = T::EQUILIBRIUM;
        }
    }
}

#[derive(Serialize)]
pub struct OutputDevice {
    pub id: String,
    pub name: String,
    pub format: Option<PcmFormat>,
}
pub fn devices() -> Result<Vec<OutputDevice>, String> {
    let host = cpal::default_host();
    host.output_devices()
        .map_err(|e| e.to_string())?
        .map(|d| {
            Ok(OutputDevice {
                id: d.id().map_err(|e| e.to_string())?.to_string(),
                name: d
                    .description()
                    .map_err(|e| e.to_string())?
                    .name()
                    .to_string(),
                format: d.default_output_config().ok().map(|c| PcmFormat {
                    sample_rate: c.sample_rate(),
                    channels: c.channels(),
                }),
            })
        })
        .collect()
}
pub fn device_format(id: &str) -> Result<PcmFormat, String> {
    let device = resolve(id)?;
    let config = device.default_output_config().map_err(|e| e.to_string())?;
    Ok(PcmFormat {
        sample_rate: config.sample_rate(),
        channels: config.channels(),
    })
}
fn resolve(id: &str) -> Result<cpal::Device, String> {
    // Never fall back to the default endpoint: it could be a public/virtual output.
    let id = id.parse().map_err(|_| "invalid_output_device_id")?;
    cpal::default_host()
        .device_by_id(&id)
        .ok_or_else(|| "output_device_missing".into())
}
pub struct OutputStream {
    _stream: cpal::Stream,
    pub failed: Arc<AtomicBool>,
}
pub fn open(id: &str, mixer: Mixer) -> Result<OutputStream, String> {
    let device = resolve(id)?;
    let config = device.default_output_config().map_err(|e| e.to_string())?;
    if mixer.format()
        != (PcmFormat {
            sample_rate: config.sample_rate(),
            channels: config.channels(),
        })
    {
        return Err("output_format_changed".into());
    }
    let failed = Arc::new(AtomicBool::new(false));
    let stream = match config.sample_format() {
        cpal::SampleFormat::F32 => build::<f32>(&device, config.into(), mixer, failed.clone()),
        cpal::SampleFormat::F64 => build::<f64>(&device, config.into(), mixer, failed.clone()),
        cpal::SampleFormat::I16 => build::<i16>(&device, config.into(), mixer, failed.clone()),
        cpal::SampleFormat::I32 => build::<i32>(&device, config.into(), mixer, failed.clone()),
        cpal::SampleFormat::U16 => build::<u16>(&device, config.into(), mixer, failed.clone()),
        _ => Err("unsupported_output_format".into()),
    }?;
    stream.play().map_err(|e| e.to_string())?;
    Ok(OutputStream {
        _stream: stream,
        failed,
    })
}
fn build<T: cpal::SizedSample + cpal::FromSample<f32>>(
    device: &cpal::Device,
    config: cpal::StreamConfig,
    mut mixer: Mixer,
    failed: Arc<AtomicBool>,
) -> Result<cpal::Stream, String> {
    let halted = failed.clone();
    device
        .build_output_stream(
            config,
            move |data: &mut [T], _| {
                if halted.load(Ordering::Relaxed) {
                    data.fill(T::EQUILIBRIUM);
                } else {
                    mixer.render(data);
                }
            },
            move |_| {
                failed.store(true, Ordering::Release);
            },
            None,
        )
        .map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use rtrb::RingBuffer;
    fn track(values: &[f32], frames: Option<u64>) -> (Track, Arc<TrackControl>) {
        let (mut producer, consumer) = RingBuffer::new(values.len().max(1));
        for &v in values {
            producer.push(v).unwrap();
        }
        Track::new(consumer, frames)
    }
    fn format() -> PcmFormat {
        PcmFormat {
            sample_rate: 48000,
            channels: 2,
        }
    }
    #[test]
    fn mixes_and_preserves_stereo() {
        let (a, _) = track(&[0.2, 0.1], None);
        let (b, _) = track(&[0.3, -0.1], None);
        let mut mixer = Mixer::new(format(), vec![a, b]).unwrap();
        let mut out = [0.0f32; 2];
        mixer.render(&mut out);
        assert_eq!(out, [0.5, 0.0]);
    }
    #[test]
    fn pauses_without_consuming_and_stops_without_replaying() {
        let (t, ctl) = track(&[0.4, 0.5, 0.6, 0.7], None);
        let mut mixer = Mixer::new(format(), vec![t]).unwrap();
        let mut out = [1.0f32; 2];
        ctl.paused.store(true, Ordering::Relaxed);
        mixer.render(&mut out);
        assert_eq!(out, [0.0, 0.0]);
        assert_eq!(ctl.played_frames.load(Ordering::Relaxed), 0);
        ctl.paused.store(false, Ordering::Relaxed);
        mixer.render(&mut out);
        assert_eq!(out, [0.4, 0.5]);
        ctl.stopped.store(true, Ordering::Relaxed);
        mixer.render(&mut out);
        assert_eq!(out, [0.0, 0.0]);
        assert_eq!(ctl.played_frames.load(Ordering::Relaxed), 1);
    }
    #[test]
    fn hungry_mic_does_not_interrupt_music() {
        let (mic, ctl) = track(&[], None);
        let (music, _) = track(&[0.2, 0.3], None);
        let mut mixer = Mixer::new(format(), vec![mic, music]).unwrap();
        let mut out = [0.0f32; 2];
        mixer.render(&mut out);
        assert_eq!(out, [0.2, 0.3]);
        assert_eq!(ctl.underrun_frames.load(Ordering::Relaxed), 1);
    }
    #[test]
    fn ends_at_sample_boundary_and_zeroes_partial_frame() {
        let (t, ctl) = track(&[0.2, 0.3, 0.4, 0.5], Some(1));
        let mut mixer = Mixer::new(format(), vec![t]).unwrap();
        let mut out = [9.0f32; 5];
        mixer.render(&mut out);
        assert_eq!(out, [0.2, 0.3, 0.0, 0.0, 0.0]);
        assert_eq!(ctl.played_frames.load(Ordering::Relaxed), 1);
    }
    #[test]
    fn gain_validation_and_linked_peak_limit() {
        let (t, ctl) = track(&[0.8, 0.4], None);
        assert!(ctl.set_gain(f32::NAN).is_err());
        assert!(ctl.set_gain(-1.0).is_err());
        ctl.set_gain(2.0).unwrap();
        let mut mixer = Mixer::new(format(), vec![t]).unwrap();
        let mut out = [0.0f32; 2];
        mixer.render(&mut out);
        assert_eq!(out, [1.0, 0.5]);
    }

    #[test]
    fn replaces_music_at_a_buffer_boundary_and_returns_old_track() {
        let (mic, _) = track(&[0.1, 0.1, 0.1, 0.1], None);
        let (old, _) = track(&[0.2, 0.2], None);
        let (new, _) = track(&[0.4, -0.4], None);
        let (mut mixer, mut control) = Mixer::with_music_slot(format(), mic, old).unwrap();
        control.try_replace(new).ok().unwrap();
        assert!(control.take_retired().is_none());
        let mut out = [0.0f32; 2];
        mixer.render(&mut out);
        assert_eq!(out, [0.5, -0.3]);
        assert!(control.take_retired().is_some());
        mixer.render(&mut out);
        assert_eq!(out, [0.1, 0.1]);
    }

    #[test]
    fn full_control_queues_defer_replacement_without_dropping_in_callback() {
        let (mic, _) = track(&[], None);
        let (old, _) = track(&[0.1, 0.1], None);
        let (next, _) = track(&[0.2, 0.2], None);
        let (later, _) = track(&[0.3, 0.3], None);
        let (mut mixer, mut control) = Mixer::with_music_slot(format(), mic, old).unwrap();
        control.try_replace(next).ok().unwrap();
        let later = control
            .try_replace(later)
            .err()
            .expect("queue must be bounded");
        let mut out = [0.0f32; 2];
        mixer.render(&mut out);
        assert_eq!(out, [0.2, 0.2]);
        control.try_replace(later).ok().unwrap();
        // Retired queue is still occupied, so the new command waits.
        mixer.render(&mut out);
        assert_eq!(out, [0.0, 0.0]);
        let _old = control.take_retired().unwrap();
        mixer.render(&mut out);
        assert_eq!(out, [0.3, 0.3]);
        assert!(control.take_retired().is_some());
    }

    #[test]
    fn independent_music_slots_mix_and_retire_without_interrupting_microphone() {
        let (mic, _) = track(&[0.125, 0.125, 0.125, 0.125], None);
        let (idle_a, _) = track(&[], None);
        let (idle_b, _) = track(&[], None);
        let (mut mixer, mut control) =
            Mixer::with_music_tracks(format(), mic, vec![idle_a, idle_b]).unwrap();
        assert_eq!(control.slot_count(), 2);
        let (a, _) = track(&[0.25, 0.25], None);
        let (b, _) = track(&[0.5, -0.5, 0.25, -0.25], None);
        control.try_replace_at(0, a).ok().unwrap();
        control.try_replace_at(1, b).ok().unwrap();
        let mut out = [0.0f32; 2];
        mixer.render(&mut out);
        assert_eq!(out, [0.875, -0.125]);
        assert!(control.take_retired_at(0).is_some());
        assert!(control.take_retired_at(1).is_some());

        let (silence, _) = track(&[], None);
        control.try_replace_at(0, silence).ok().unwrap();
        mixer.render(&mut out);
        assert_eq!(out, [0.375, -0.125]);
        assert!(control.take_retired_at(0).is_some());
    }

    #[test]
    fn music_slots_require_a_nonempty_fixed_budget() {
        let (mic, _) = track(&[], None);
        assert!(Mixer::with_music_tracks(format(), mic, vec![]).is_err());
    }

    #[test]
    fn stopped_microphone_can_discard_old_frames_before_restarting() {
        let (mic, ctl) = track(&[0.7, 0.7, 0.6, 0.6], None);
        let mut mixer = Mixer::new(format(), vec![mic]).unwrap();
        ctl.stopped.store(true, Ordering::Release);
        ctl.flush.store(true, Ordering::Release);
        let mut out = [1.0f32; 2];
        mixer.render(&mut out);
        assert_eq!(out, [0.0, 0.0]);
        assert!(!ctl.flush.load(Ordering::Acquire));
        ctl.stopped.store(false, Ordering::Release);
        mixer.render(&mut out);
        assert_eq!(out, [0.0, 0.0]);
    }
}
