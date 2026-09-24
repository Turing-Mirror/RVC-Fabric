//! Run with FABRIC_AUDIO_TOOLS set to an existing FFmpeg/ffprobe directory.
//! Generates only synthetic PCM in the system temp directory. Never opens a device.
use fabric_audio::{
    decode::{decode, decode_clip, AudioTools, ClipOptions, DecodedStream},
    format::{ClipRange, PcmFormat},
};
use std::{
    fs,
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc,
    },
    time::{Duration, Instant},
};

struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        static SEQ: AtomicU64 = AtomicU64::new(0);
        let dir = std::env::temp_dir().join(format!(
            "fabric-audio-{}-{}",
            std::process::id(),
            SEQ.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&dir).unwrap();
        let frames = 44100u32;
        let mut wav = Vec::new();
        wav.extend_from_slice(b"RIFF");
        wav.extend_from_slice(&(36 + frames * 2).to_le_bytes());
        wav.extend_from_slice(b"WAVEfmt ");
        wav.extend_from_slice(&16u32.to_le_bytes());
        wav.extend_from_slice(&1u16.to_le_bytes());
        wav.extend_from_slice(&1u16.to_le_bytes());
        wav.extend_from_slice(&44100u32.to_le_bytes());
        wav.extend_from_slice(&88200u32.to_le_bytes());
        wav.extend_from_slice(&2u16.to_le_bytes());
        wav.extend_from_slice(&16u16.to_le_bytes());
        wav.extend_from_slice(b"data");
        wav.extend_from_slice(&(frames * 2).to_le_bytes());
        for i in 0..frames {
            let value =
                ((i as f64 * 440.0 * std::f64::consts::TAU / 44100.0).sin() * 8000.0) as i16;
            wav.extend_from_slice(&value.to_le_bytes());
        }
        fs::write(dir.join("tone.wav"), wav).unwrap();
        Self(dir)
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn tools() -> AudioTools {
    AudioTools::at(&PathBuf::from(
        std::env::var_os("FABRIC_AUDIO_TOOLS").expect("set FABRIC_AUDIO_TOOLS"),
    ))
}
#[test]
#[ignore = "requires explicitly supplied FFmpeg tools; no audio hardware"]
fn decodes_resamples_and_crops_exactly_without_runtime() {
    let fixture = Fixture::new();
    let input = fixture.0.join("tone.wav");
    let original = fs::read(&input).unwrap();
    assert_eq!(tools().probe(&input).unwrap(), 1.0);
    let mut stream = decode(
        &tools(),
        &input,
        ClipRange {
            start: 0.25,
            end: Some(0.75),
        },
        PcmFormat {
            sample_rate: 48000,
            channels: 2,
        },
        0.01,
    )
    .unwrap();
    let deadline = Instant::now() + Duration::from_secs(10);
    let mut samples = Vec::new();
    loop {
        while let Ok(sample) = stream.pcm.pop() {
            samples.push(sample);
        }
        if stream.decoder.state.finished.load(Ordering::Acquire) && stream.pcm.slots() == 0 {
            break;
        }
        assert!(Instant::now() < deadline, "decoder hung");
        std::thread::sleep(Duration::from_millis(1));
    }
    assert!(!stream.decoder.state.failed.load(Ordering::Acquire));
    assert_eq!(samples.len(), 24000 * 2);
    assert!(samples.iter().all(|x| x.is_finite() && x.abs() <= 1.0));
    assert!(samples.iter().any(|x| x.abs() > 0.1));
    for pair in samples.chunks_exact(2) {
        assert_eq!(pair[0], pair[1]);
    }
    assert_eq!(fs::read(input).unwrap(), original);
}
#[test]
#[ignore = "requires explicitly supplied FFmpeg tools; no audio hardware"]
fn cancelling_full_buffer_reaps_decoder() {
    let fixture = Fixture::new();
    let stream = decode(
        &tools(),
        &fixture.0.join("tone.wav"),
        ClipRange::default(),
        PcmFormat {
            sample_rate: 48000,
            channels: 2,
        },
        0.001,
    )
    .unwrap();
    std::thread::sleep(Duration::from_millis(100));
    let started = Instant::now();
    drop(stream);
    assert!(started.elapsed() < Duration::from_secs(2));
}
#[test]
#[ignore = "requires explicitly supplied FFmpeg tools; no audio hardware"]
fn invalid_file_and_range_do_not_start_playback() {
    let fixture = Fixture::new();
    fs::write(fixture.0.join("broken.wav"), b"not audio").unwrap();
    assert!(tools().probe(&fixture.0.join("broken.wav")).is_err());
    assert!(decode(
        &tools(),
        &fixture.0.join("tone.wav"),
        ClipRange {
            start: 0.0,
            end: Some(2.0)
        },
        PcmFormat {
            sample_rate: 48000,
            channels: 2
        },
        0.1
    )
    .is_err());
}

fn drain(stream: &mut DecodedStream, mut on_frames: impl FnMut(usize)) -> Vec<f32> {
    let deadline = Instant::now() + Duration::from_secs(20);
    let mut samples = Vec::new();
    loop {
        while let Ok(sample) = stream.pcm.pop() {
            samples.push(sample);
        }
        on_frames(samples.len() / 2);
        if stream.decoder.state.finished.load(Ordering::Acquire) && stream.pcm.slots() == 0 {
            break;
        }
        assert!(Instant::now() < deadline, "decoder hung");
        std::thread::sleep(Duration::from_millis(1));
    }
    assert!(!stream.decoder.state.failed.load(Ordering::Acquire));
    samples
}

#[test]
#[ignore = "requires explicitly supplied FFmpeg tools; no audio hardware"]
fn seek_offset_starts_inside_the_clip_and_keeps_its_end() {
    let fixture = Fixture::new();
    let mut stream = decode_clip(
        &tools(),
        &fixture.0.join("tone.wav"),
        ClipRange { start: 0.25, end: Some(0.75) },
        PcmFormat { sample_rate: 48000, channels: 2 },
        0.05,
        ClipOptions { offset_frames: 18000, ..ClipOptions::default() },
    )
    .unwrap();
    assert_eq!(stream.range.frames(), 24000);
    let samples = drain(&mut stream, |_| {});
    assert_eq!(samples.len(), 6000 * 2);
    assert!(decode_clip(
        &tools(),
        &fixture.0.join("tone.wav"),
        ClipRange { start: 0.25, end: Some(0.75) },
        PcmFormat { sample_rate: 48000, channels: 2 },
        0.05,
        ClipOptions { offset_frames: 24000, ..ClipOptions::default() },
    )
    .is_err());
}

#[test]
#[ignore = "requires explicitly supplied FFmpeg tools; no audio hardware"]
fn looping_repeats_whole_passes_and_stops_after_the_current_one() {
    let fixture = Fixture::new();
    let looping = Arc::new(AtomicBool::new(true));
    let mut stream = decode_clip(
        &tools(),
        &fixture.0.join("tone.wav"),
        ClipRange { start: 0.25, end: Some(0.75) },
        PcmFormat { sample_rate: 48000, channels: 2 },
        0.05,
        ClipOptions {
            offset_frames: 12000,
            looping: Some(looping.clone()),
            edge_fade_seconds: 0.005,
        },
    )
    .unwrap();
    let flag = looping.clone();
    let samples = drain(&mut stream, |frames| {
        if frames > 12000 + 24000 * 2 {
            flag.store(false, Ordering::Release);
        }
    });
    // First pass from the seek point, then whole passes; the pass in progress
    // when looping was switched off still finishes.
    let frames = samples.len() / 2;
    assert!(frames >= 12000 + 24000 * 3, "{frames}");
    assert_eq!((frames - 12000) % 24000, 0, "{frames}");
    // Edge fades: each pass starts from silence instead of mid-waveform.
    assert!(samples[0].abs() < 0.01);
    assert!(samples[12000 * 2].abs() < 0.01);
    assert!(samples.iter().any(|x| x.abs() > 0.1));
}

#[test]
#[ignore = "requires explicitly supplied FFmpeg tools; no audio hardware"]
fn loop_switched_on_before_the_last_frame_plays_still_repeats() {
    let fixture = Fixture::new();
    let looping = Arc::new(AtomicBool::new(false));
    let mut stream = decode_clip(
        &tools(),
        &fixture.0.join("tone.wav"),
        ClipRange { start: 0.0, end: Some(0.1) },
        PcmFormat { sample_rate: 48000, channels: 2 },
        1.0,
        ClipOptions { looping: Some(looping.clone()), ..ClipOptions::default() },
    )
    .unwrap();
    // The whole pass fits in the buffer; nothing has been consumed yet.
    let deadline = Instant::now() + Duration::from_secs(10);
    while stream.decoder.state.decoded_frames.load(Ordering::Acquire) < 4800 {
        assert!(Instant::now() < deadline, "decoder hung");
        std::thread::sleep(Duration::from_millis(1));
    }
    std::thread::sleep(Duration::from_millis(50));
    assert!(!stream.decoder.state.finished.load(Ordering::Acquire));
    looping.store(true, Ordering::Release);
    let flag = looping.clone();
    let samples = drain(&mut stream, |frames| {
        if frames > 4800 {
            flag.store(false, Ordering::Release);
        }
    });
    assert_eq!(samples.len() / 2 % 4800, 0);
    assert!(samples.len() / 2 >= 9600);
}
