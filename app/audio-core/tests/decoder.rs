//! Run with FABRIC_AUDIO_TOOLS set to an existing FFmpeg/ffprobe directory.
//! Generates only synthetic PCM in the system temp directory. Never opens a device.
use fabric_audio::{
    decode::{decode, AudioTools},
    format::{ClipRange, PcmFormat},
};
use std::{
    fs,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
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
