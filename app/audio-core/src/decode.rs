//! Blocking file work is confined to a decoder thread; the callback only consumes PCM.
use crate::format::{ClipRange, FrameRange, PcmFormat};
use rtrb::{Consumer, RingBuffer};
use serde::Deserialize;
use std::{
    io::{BufReader, ErrorKind, Read},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex,
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

#[derive(Clone, Debug)]
pub struct AudioTools {
    pub ffmpeg: PathBuf,
    pub ffprobe: PathBuf,
}
impl AudioTools {
    pub fn at(root: &Path) -> Self {
        Self {
            ffmpeg: root.join(if cfg!(windows) {
                "ffmpeg.exe"
            } else {
                "ffmpeg"
            }),
            ffprobe: root.join(if cfg!(windows) {
                "ffprobe.exe"
            } else {
                "ffprobe"
            }),
        }
    }
    pub fn ready(&self) -> bool {
        self.ffmpeg.is_file() && self.ffprobe.is_file()
    }
    pub fn probe(&self, input: &Path) -> Result<f64, String> {
        if !input.is_file() {
            return Err("audio_file_missing".into());
        }
        if !self.ready() {
            return Err("audio_tools_missing".into());
        }
        let mut child = hidden(&self.ffprobe)
            .args([
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_type,duration:format=duration",
                "-of",
                "json",
            ])
            .arg(input)
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| e.to_string())?;
        let deadline = Instant::now() + Duration::from_secs(15);
        let status = loop {
            match child.try_wait() {
                Ok(Some(status)) => break status,
                Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(20)),
                Ok(None) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err("audio_probe_timeout".into());
                }
                Err(e) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(e.to_string());
                }
            }
        };
        if !status.success() {
            return Err("audio_probe_failed".into());
        }
        let mut stdout = Vec::new();
        child
            .stdout
            .take()
            .ok_or("audio_probe_pipe_missing")?
            .read_to_end(&mut stdout)
            .map_err(|e| e.to_string())?;
        #[derive(Deserialize)]
        struct DurationInfo {
            duration: Option<String>,
        }
        #[derive(Deserialize)]
        struct Probe {
            streams: Vec<DurationInfo>,
            format: Option<DurationInfo>,
        }
        let info: Probe = serde_json::from_slice(&stdout).map_err(|e| e.to_string())?;
        let stream = info.streams.first().ok_or("audio_stream_missing")?;
        let duration = stream
            .duration
            .as_ref()
            .and_then(|s| s.parse::<f64>().ok())
            .or_else(|| {
                info.format
                    .and_then(|f| f.duration)
                    .and_then(|s| s.parse().ok())
            })
            .filter(|n| n.is_finite() && *n > 0.0)
            .ok_or("audio_duration_unknown")?;
        Ok(duration)
    }
}
fn hidden(program: &Path) -> Command {
    let mut cmd = Command::new(program);
    cmd.stdin(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    cmd
}

#[derive(Default)]
pub struct DecodeState {
    pub finished: AtomicBool,
    pub failed: AtomicBool,
    pub decoded_frames: AtomicU64,
    cancelled: AtomicBool,
}
/// Controller stays off the real-time callback. Drop kills and reaps its own child only.
pub struct Decoder {
    child: Arc<Mutex<Child>>,
    pub state: Arc<DecodeState>,
    worker: Option<JoinHandle<()>>,
}
impl Drop for Decoder {
    fn drop(&mut self) {
        self.state.cancelled.store(true, Ordering::Release);
        if let Ok(mut child) = self.child.lock() {
            let _ = child.kill();
        }
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
        // A looping worker may have started the next pass after the first kill.
        if let Ok(mut child) = self.child.lock() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}
pub struct DecodedStream {
    pub decoder: Decoder,
    pub pcm: Consumer<f32>,
    /// The whole clip in output frames, independent of any first-pass offset.
    pub range: FrameRange,
    pub format: PcmFormat,
}

#[derive(Clone, Default)]
pub struct ClipOptions {
    /// Skip this many clip frames on the first pass only (seek).
    pub offset_frames: u64,
    /// While raised, each pass is followed by another from the clip start.
    /// Checked until the last decoded frame is consumed, so it can be
    /// switched on or off during playback.
    pub looping: Option<Arc<AtomicBool>>,
    /// Short fade at each pass's edges so seams and seeks do not click.
    pub edge_fade_seconds: f64,
}

pub fn decode(
    tools: &AudioTools,
    input: &Path,
    range: ClipRange,
    format: PcmFormat,
    buffer_seconds: f64,
) -> Result<DecodedStream, String> {
    decode_clip(
        tools,
        input,
        range,
        format,
        buffer_seconds,
        ClipOptions::default(),
    )
}

fn pass_filter(pass: FrameRange, format: PcmFormat, edge_fade_seconds: f64) -> String {
    let mut filter = format!(
        "aresample={},atrim=start_sample={}:end_sample={},asetpts=PTS-STARTPTS",
        format.sample_rate, pass.start, pass.end
    );
    let length = pass.frames() as f64 / format.sample_rate as f64;
    let fade = edge_fade_seconds.min(length / 4.0);
    if fade.is_finite() && fade > 0.0 {
        filter.push_str(&format!(
            ",afade=t=in:d={fade:.6},afade=t=out:st={:.6}:d={fade:.6}",
            length - fade
        ));
    }
    filter
}

fn spawn_pass(
    tools: &AudioTools,
    input: &Path,
    pass: FrameRange,
    format: PcmFormat,
    edge_fade_seconds: f64,
) -> Result<(Child, BufReader<std::process::ChildStdout>), String> {
    let filter = pass_filter(pass, format, edge_fade_seconds);
    let mut child = hidden(&tools.ffmpeg)
        .args([
            "-nostdin",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
        ])
        .arg(input)
        .args([
            "-map",
            "0:a:0",
            "-vn",
            "-af",
            &filter,
            "-ac",
            &format.channels.to_string(),
            "-ar",
            &format.sample_rate.to_string(),
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "pipe:1",
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| e.to_string())?;
    match child.stdout.take() {
        Some(stdout) => Ok((child, BufReader::new(stdout))),
        None => {
            let _ = child.kill();
            let _ = child.wait();
            Err("audio_decoder_pipe_missing".into())
        }
    }
}

enum PassEnd {
    Done,
    Failed,
    Cancelled,
}

fn read_pass(
    stdout: &mut BufReader<std::process::ChildStdout>,
    frames: u64,
    producer: &mut rtrb::Producer<f32>,
    ctl: &DecodeState,
    channels: usize,
    total: &mut u64,
) -> PassEnd {
    let mut bytes = vec![0u8; channels * 4];
    let mut count = 0u64;
    while count < frames {
        if ctl.cancelled.load(Ordering::Acquire) {
            return PassEnd::Cancelled;
        }
        match stdout.read_exact(&mut bytes) {
            Ok(()) => {}
            Err(e) if e.kind() == ErrorKind::UnexpectedEof => return PassEnd::Done,
            Err(_) => return PassEnd::Failed,
        }
        while producer.slots() < channels {
            if ctl.cancelled.load(Ordering::Acquire) {
                return PassEnd::Cancelled;
            }
            thread::sleep(Duration::from_millis(1));
        }
        for sample in bytes.chunks_exact(4) {
            let value = f32::from_le_bytes(sample.try_into().unwrap());
            let _ = producer.push(if value.is_finite() { value } else { 0.0 });
        }
        count += 1;
        *total += 1;
        ctl.decoded_frames.store(*total, Ordering::Release);
    }
    PassEnd::Done
}

/// Reap without holding the child lock while waiting: Drop must be able to cancel.
/// `None` means cancelled.
fn reap(process: &Mutex<Child>, ctl: &DecodeState) -> Option<bool> {
    loop {
        if ctl.cancelled.load(Ordering::Acquire) {
            return None;
        }
        let result = process.lock().unwrap().try_wait();
        match result {
            Ok(Some(status)) => return Some(status.success()),
            Err(_) => return Some(false),
            Ok(None) => thread::sleep(Duration::from_millis(1)),
        }
    }
}

pub fn decode_clip(
    tools: &AudioTools,
    input: &Path,
    range: ClipRange,
    format: PcmFormat,
    buffer_seconds: f64,
    options: ClipOptions,
) -> Result<DecodedStream, String> {
    format.validate()?;
    let frames = range.resolve(tools.probe(input)?, format.sample_rate)?;
    if options.offset_frames >= frames.frames() {
        return Err("invalid_clip_offset".into());
    }
    let capacity = format
        .samples_for(buffer_seconds)?
        .max(format.channels as usize);
    let (mut producer, pcm) = RingBuffer::new(capacity);
    let first = FrameRange {
        start: frames.start + options.offset_frames,
        end: frames.end,
    };
    let (child, mut stdout) = spawn_pass(tools, input, first, format, options.edge_fade_seconds)?;
    let child = Arc::new(Mutex::new(child));
    let state = Arc::new(DecodeState::default());
    let ctl = state.clone();
    let process = child.clone();
    let tools = tools.clone();
    let input = input.to_path_buf();
    let worker = thread::Builder::new()
        .name("fabric-audio-decode".into())
        .spawn(move || {
            let channels = format.channels as usize;
            let mut pass = first;
            let mut total = 0u64;
            loop {
                match read_pass(&mut stdout, pass.frames(), &mut producer, &ctl, channels, &mut total) {
                    PassEnd::Cancelled => return,
                    PassEnd::Failed => {
                        ctl.failed.store(true, Ordering::Release);
                        break;
                    }
                    PassEnd::Done => {}
                }
                match reap(&process, &ctl) {
                    None => return,
                    Some(false) => {
                        ctl.failed.store(true, Ordering::Release);
                        break;
                    }
                    Some(true) => {}
                }
                let Some(looping) = options.looping.as_ref() else {
                    break;
                };
                let again = loop {
                    if ctl.cancelled.load(Ordering::Acquire) {
                        return;
                    }
                    if looping.load(Ordering::Acquire) {
                        break true;
                    }
                    if producer.slots() == capacity {
                        break false;
                    }
                    thread::sleep(Duration::from_millis(5));
                };
                if !again {
                    break;
                }
                pass = frames;
                match spawn_pass(&tools, &input, pass, format, options.edge_fade_seconds) {
                    Ok((next, reader)) => {
                        *process.lock().unwrap() = next;
                        stdout = reader;
                        if ctl.cancelled.load(Ordering::Acquire) {
                            let _ = process.lock().unwrap().kill();
                            return;
                        }
                    }
                    Err(_) => {
                        ctl.failed.store(true, Ordering::Release);
                        break;
                    }
                }
            }
            ctl.finished.store(true, Ordering::Release);
        })
        .map_err(|e| {
            if let Ok(mut p) = child.lock() {
                let _ = p.kill();
                let _ = p.wait();
            }
            e.to_string()
        })?;
    Ok(DecodedStream {
        decoder: Decoder {
            child,
            state,
            worker: Some(worker),
        },
        pcm,
        range: frames,
        format,
    })
}
