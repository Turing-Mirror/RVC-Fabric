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
    name: String,
    length: u64,
    control: Arc<TrackControl>,
    decoder: Decoder,
}

pub struct VoiceBus {
    device_id: String,
    format: PcmFormat,
    output: OutputStream,
    music_control: MusicControl,
    music: Option<Music>,
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
        let (_, empty_music) = RingBuffer::new(format.channels as usize);
        let (idle_track, idle_control) = Track::new(empty_music, None);
        idle_control.stopped.store(true, Ordering::Release);
        let (mixer, music_control) = output::Mixer::with_music_slot(format, mic_track, idle_track)?;
        let output = output::open(&device_id, mixer)?;
        Ok(Self {
            device_id,
            format,
            output,
            music_control,
            music: None,
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

    fn swap_music(&mut self, track: Track) -> Result<(), String> {
        self.music_control
            .try_replace(track)
            .map_err(|_| "audio_music_swap_busy".to_string())?;
        let deadline = Instant::now() + SWAP_TIMEOUT;
        loop {
            if let Some(old) = self.music_control.take_retired() {
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
        name: String,
        decoded: DecodedStream,
        gain: f32,
    ) -> Result<(), String> {
        if decoded.format != self.format {
            return Err("output_format_changed".into());
        }
        let length = decoded.range.frames();
        let (track, control) = Track::new(decoded.pcm, Some(length));
        control.set_gain(gain)?;
        control.paused.store(true, Ordering::Release);
        self.swap_music(track)?;
        self.music = Some(Music {
            name,
            length,
            control: control.clone(),
            decoder: decoded.decoder,
        });
        control.paused.store(false, Ordering::Release);
        Ok(())
    }

    pub fn pause(&mut self, paused: bool) -> Result<(), String> {
        let music = self.music.as_ref().ok_or("audio_playback_not_playing")?;
        music.control.paused.store(paused, Ordering::Release);
        Ok(())
    }

    pub fn stop_music(&mut self) -> Result<(), String> {
        if let Some(music) = self.music.as_ref() {
            music.control.stopped.store(true, Ordering::Release);
        }
        let (_, silent_pcm) = RingBuffer::new(self.format.channels as usize);
        let (silent, ctl) = Track::new(silent_pcm, None);
        ctl.stopped.store(true, Ordering::Release);
        self.swap_music(silent)?;
        self.music = None;
        Ok(())
    }

    pub fn music_status(&self) -> Option<(&str, u64, u64, bool, bool)> {
        self.music.as_ref().map(|music| {
            (
                music.name.as_str(),
                music.control.played_frames.load(Ordering::Acquire),
                music.length,
                music.control.paused.load(Ordering::Acquire),
                music.decoder.state.failed.load(Ordering::Acquire)
                    || (music.decoder.state.finished.load(Ordering::Acquire)
                        && music.decoder.state.decoded_frames.load(Ordering::Acquire) == 0),
            )
        })
    }

    pub fn music_finished(&self) -> bool {
        self.music.as_ref().is_some_and(|music| {
            music.decoder.state.failed.load(Ordering::Acquire)
                || music.control.played_frames.load(Ordering::Acquire) >= music.length
                || (music.decoder.state.finished.load(Ordering::Acquire)
                    && music.control.played_frames.load(Ordering::Acquire)
                        >= music.decoder.state.decoded_frames.load(Ordering::Acquire))
        })
    }

    pub fn has_music(&self) -> bool {
        self.music.is_some()
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
