//! Explicit developer harness: listing is silent; playback requires an endpoint ID.
use fabric_audio::{
    decode::{decode, AudioTools},
    format::ClipRange,
    output::{self, Mixer, Track},
};
use std::{
    path::Path,
    sync::atomic::Ordering,
    time::{Duration, Instant},
};
fn main() -> Result<(), String> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.first().map(String::as_str) == Some("list") {
        println!(
            "{}",
            serde_json::to_string_pretty(&output::devices()?).map_err(|e| e.to_string())?
        );
        return Ok(());
    }
    if args.len() != 6 || args[0] != "play" {
        return Err("Usage: audio_probe list | play TOOL_ROOT INPUT DEVICE_ID START END".into());
    }
    let format = output::device_format(&args[3])?;
    let range = ClipRange {
        start: args[4].parse().map_err(|_| "invalid_start")?,
        end: Some(args[5].parse().map_err(|_| "invalid_end")?),
    };
    let decoded = decode(
        &AudioTools::at(Path::new(&args[1])),
        Path::new(&args[2]),
        range,
        format,
        0.25,
    )?;
    let length = decoded.range.frames();
    let decoder = decoded.decoder;
    let (track, control) = Track::new(decoded.pcm, Some(length));
    let stream = output::open(&args[3], Mixer::new(format, vec![track])?)?;
    let deadline =
        Instant::now() + Duration::from_secs_f64(length as f64 / format.sample_rate as f64 + 15.0);
    while control.played_frames.load(Ordering::Acquire) < length {
        if stream.failed.load(Ordering::Acquire) || decoder.state.failed.load(Ordering::Acquire) {
            return Err("audio_playback_failed".into());
        }
        // Compressed-container duration can include encoder padding. The decoder's
        // actual EOF, not that estimate, determines natural completion.
        if decoder.state.finished.load(Ordering::Acquire)
            && control.played_frames.load(Ordering::Acquire)
                >= decoder.state.decoded_frames.load(Ordering::Acquire)
        {
            break;
        }
        if Instant::now() > deadline {
            return Err("audio_playback_timeout".into());
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    // Let the final device buffer drain before dropping its stream.
    std::thread::sleep(Duration::from_millis(250));
    drop(stream);
    drop(decoder);
    println!(
        "frames={length}, underruns={}",
        control.underrun_frames.load(Ordering::Acquire)
    );
    Ok(())
}
