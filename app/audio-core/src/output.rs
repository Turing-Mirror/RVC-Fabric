use crate::format::PcmFormat;
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use rtrb::Consumer;
use serde::Serialize;
use std::sync::{
    atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering},
    Arc,
};

pub struct TrackControl {
    pub paused: AtomicBool,
    pub stopped: AtomicBool,
    pub played_frames: AtomicU64,
    pub underrun_frames: AtomicU64,
    gain: AtomicU32,
}
impl Default for TrackControl {
    fn default() -> Self {
        Self {
            paused: AtomicBool::new(false),
            stopped: AtomicBool::new(false),
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
/// Topology is fixed for this A00 prototype; dynamic instance replacement is B03.
pub struct Mixer {
    format: PcmFormat,
    tracks: Vec<Track>,
    scratch: Vec<f32>,
}
impl Mixer {
    pub fn new(format: PcmFormat, tracks: Vec<Track>) -> Result<Self, String> {
        format.validate()?;
        Ok(Self {
            format,
            tracks,
            scratch: vec![0.0; format.channels as usize],
        })
    }
    pub fn format(&self) -> PcmFormat {
        self.format
    }
    pub fn render<T: cpal::Sample + cpal::FromSample<f32>>(&mut self, data: &mut [T]) {
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
}
