//! Minimal file-based mixing shared by local capability callers.
use serde_json::{json, Value};
use std::{
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::Duration,
};
use trm_app_protocol::{jobs::JobContext, ApiError, ApiResult};
fn hidden(exe: &Path) -> Command {
    let mut command = Command::new(exe);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000);
    }
    command
}
pub fn artifact(root: &Path, path: &Path, role: &str, id: &str) -> ApiResult {
    if !path.is_file() {
        return Err(ApiError::new("output_missing", path.display()));
    }
    let tools = fabric_audio::decode::AudioTools::at(root);
    let output = hidden(&tools.ffprobe)
        .args([
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels,codec_name,duration:format=duration,format_name",
            "-of",
            "json",
        ])
        .arg(path)
        .output()?;
    if !output.status.success() {
        return Err(ApiError::new(
            "output_invalid",
            String::from_utf8_lossy(&output.stderr),
        ));
    }
    let meta: Value =
        serde_json::from_slice(&output.stdout).map_err(|e| ApiError::new("output_invalid", e))?;
    let stream = meta["streams"]
        .get(0)
        .ok_or_else(|| ApiError::new("output_invalid", "No audio stream"))?;
    let duration = meta["format"]["duration"]
        .as_str()
        .or_else(|| stream["duration"].as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .ok_or_else(|| ApiError::new("output_invalid", "Unknown audio duration"))?;
    let sample_rate = stream["sample_rate"]
        .as_str()
        .and_then(|s| s.parse::<u32>().ok())
        .ok_or_else(|| ApiError::new("output_invalid", "Unknown sample rate"))?;
    Ok(
        json!({"id":id,"role":role,"path":path.canonicalize()?.to_string_lossy(),"format":path.extension().unwrap_or_default().to_string_lossy(),"sampleRate":sample_rate,"channels":stream["channels"],"duration":duration,"codec":stream["codec_name"]}),
    )
}
pub fn mix(root: &Path, context: &JobContext, args: &Value, output: &Path) -> ApiResult {
    let tracks = args["tracks"]
        .as_array()
        .ok_or_else(|| ApiError::invalid("tracks is required"))?;
    let tools = fabric_audio::decode::AudioTools::at(root);
    if !tools.ready() {
        return Err(ApiError::new(
            "audio_tools_missing",
            "Install audio tools in the application",
        ));
    }
    let rate = args["sampleRate"].as_u64().unwrap_or(48000);
    let channels = args["channels"].as_u64().unwrap_or(2);
    let format = args["format"].as_str().unwrap_or("wav");
    let target = output.join(format!("{}.{}", context.id, format));
    let temporary = output.join(format!("{}.part.{}", context.id, format));
    let log_path = output.join(format!("{}.ffmpeg.log", context.id));
    let mut command = hidden(&tools.ffmpeg);
    command.args(["-nostdin", "-v", "error", "-n"]);
    let mut filters = Vec::new();
    let mut duration = 0.0_f64;
    for (index, track) in tracks.iter().enumerate() {
        let path = PathBuf::from(
            track["path"]
                .as_str()
                .ok_or_else(|| ApiError::invalid("Track path is required"))?,
        );
        if !path.is_file() {
            return Err(ApiError::new("input_missing", path.display()));
        }
        command
            .args(["-protocol_whitelist", "file,pipe", "-i"])
            .arg(&path);
        let gain = track["gainDb"].as_f64().unwrap_or(0.0);
        let offset = track["offsetMs"].as_f64().unwrap_or(0.0);
        duration = duration.max(
            tools
                .probe(&path)
                .map_err(|e| ApiError::new("input_invalid", e))?
                + offset / 1000.0,
        );
        let samples = (offset * rate as f64 / 1000.0).round() as i64;
        let alignment = if samples < 0 {
            format!("atrim=start_sample={},asetpts=PTS-STARTPTS", -samples)
        } else {
            format!("asetpts=PTS-STARTPTS,adelay={}S:all=1", samples)
        };
        filters.push(format!("[{index}:a:0]aresample={rate},aformat=channel_layouts={},volume={}dB,{alignment}[r{index}]",if channels==1{"mono"}else{"stereo"},gain));
    }
    if duration <= 0.0 {
        return Err(ApiError::invalid("Track offsets remove all audio"));
    }
    // Pad every track to the same length. Older bundled FFmpeg always normalizes
    // amix; with all inputs alive, multiplying by the track count restores unity gain.
    for index in 0..tracks.len() {
        filters.push(format!(
            "[r{index}]apad,atrim=duration={duration}[a{index}]"
        ));
    }
    let inputs = (0..tracks.len())
        .map(|i| format!("[a{i}]"))
        .collect::<String>();
    let limiter = if args["limiter"].as_bool().unwrap_or(true) {
        let latency = rate / 200;
        let length = (duration * rate as f64).round() as u64;
        format!(",apad=pad_len={latency},alimiter=limit=0.95:level=false:attack=5,atrim=start_sample={latency}:end_sample={},asetpts=PTS-STARTPTS",length+latency)
    } else {
        String::new()
    };
    filters.push(format!(
        "{inputs}amix=inputs={}:duration=longest:dropout_transition=0,volume={}{limiter}[mixed]",
        tracks.len(),
        tracks.len()
    ));
    command
        .args([
            "-filter_complex",
            &filters.join(";"),
            "-map",
            "[mixed]",
            "-ar",
            &rate.to_string(),
            "-ac",
            &channels.to_string(),
            "-c:a",
            if format == "flac" {
                "flac"
            } else {
                "pcm_s16le"
            },
        ])
        .arg(&temporary)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::from(std::fs::File::create(&log_path)?));
    context.check()?;
    context.progress(json!({"phase":"mixing"}));
    let mut child = command.spawn()?;
    let status = loop {
        if context.check().is_err() {
            let _ = child.kill();
            let _ = child.wait();
            let _ = std::fs::remove_file(&temporary);
            return Err(ApiError::canceled());
        }
        if let Some(status) = child.try_wait()? {
            break status;
        }
        std::thread::sleep(Duration::from_millis(50));
    };
    if !status.success() {
        let _ = std::fs::remove_file(&temporary);
        return Err(ApiError::new(
            "mix_failed",
            std::fs::read_to_string(&log_path).unwrap_or_default(),
        ));
    }
    std::fs::rename(&temporary, &target)?;
    let artifact = artifact(root, &target, "mix", &format!("{}:0", context.id))?;
    Ok(json!({"jobId":context.id,"artifacts":[artifact]}))
}
