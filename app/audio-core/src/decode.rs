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
    time::Duration,
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
        let result = hidden(&self.ffprobe)
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
            .output()
            .map_err(|e| e.to_string())?;
        if !result.status.success() {
            return Err("audio_probe_failed".into());
        }
        #[derive(Deserialize)]
        struct DurationInfo {
            duration: Option<String>,
        }
        #[derive(Deserialize)]
        struct Probe {
            streams: Vec<DurationInfo>,
            format: Option<DurationInfo>,
        }
        let info: Probe = serde_json::from_slice(&result.stdout).map_err(|e| e.to_string())?;
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
        if let Ok(mut child) = self.child.lock() {
            let _ = child.wait();
        }
    }
}
pub struct DecodedStream {
    pub decoder: Decoder,
    pub pcm: Consumer<f32>,
    pub range: FrameRange,
    pub format: PcmFormat,
}
pub fn decode(
    tools: &AudioTools,
    input: &Path,
    range: ClipRange,
    format: PcmFormat,
    buffer_seconds: f64,
) -> Result<DecodedStream, String> {
    format.validate()?;
    let frames = range.resolve(tools.probe(input)?, format.sample_rate)?;
    let capacity = format
        .samples_for(buffer_seconds)?
        .max(format.channels as usize);
    let (mut producer, pcm) = RingBuffer::new(capacity);
    let filter = format!(
        "aresample={},atrim=start_sample={}:end_sample={},asetpts=PTS-STARTPTS",
        format.sample_rate, frames.start, frames.end
    );
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
    let mut stdout = BufReader::new(child.stdout.take().ok_or("audio_decoder_pipe_missing")?);
    let child = Arc::new(Mutex::new(child));
    let state = Arc::new(DecodeState::default());
    let ctl = state.clone();
    let process = child.clone();
    let worker = thread::Builder::new()
        .name("fabric-audio-decode".into())
        .spawn(move || {
            let mut bytes = vec![0u8; format.channels as usize * 4];
            let mut count = 0u64;
            while !ctl.cancelled.load(Ordering::Acquire) && count < frames.frames() {
                match stdout.read_exact(&mut bytes) {
                    Ok(()) => {}
                    Err(e) => {
                        if e.kind() != ErrorKind::UnexpectedEof {
                            ctl.failed.store(true, Ordering::Release);
                        }
                        break;
                    }
                }
                while producer.slots() < format.channels as usize {
                    if ctl.cancelled.load(Ordering::Acquire) {
                        return;
                    }
                    thread::sleep(Duration::from_millis(1));
                }
                for sample in bytes.chunks_exact(4) {
                    let value = f32::from_le_bytes(sample.try_into().unwrap());
                    let _ = producer.push(if value.is_finite() { value } else { 0.0 });
                }
                count += 1;
                ctl.decoded_frames.store(count, Ordering::Release);
            }
            // Reap without holding the child lock while waiting: Drop must be able to cancel.
            loop {
                if ctl.cancelled.load(Ordering::Acquire) {
                    break;
                }
                let result = process.lock().unwrap().try_wait();
                match result {
                    Ok(Some(status)) => {
                        if !status.success() {
                            ctl.failed.store(true, Ordering::Release);
                        }
                        break;
                    }
                    Err(_) => {
                        ctl.failed.store(true, Ordering::Release);
                        break;
                    }
                    Ok(None) => thread::sleep(Duration::from_millis(1)),
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
