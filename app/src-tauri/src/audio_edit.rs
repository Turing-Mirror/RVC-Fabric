use std::{
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Mutex,
    },
};
use tauri::{AppHandle, State};

/// Export a saved clip as a decoded PCM WAV. The source and any existing target stay untouched.
pub(crate) fn export_precise(
    root: &Path,
    input: &Path,
    target: &Path,
    start: f64,
    end: Option<f64>,
    cancelled: &AtomicBool,
) -> Result<(), String> {
    if target
        .extension()
        .and_then(|s| s.to_str())
        .map(str::to_ascii_lowercase)
        .as_deref()
        != Some("wav")
    {
        return Err("audio_export_requires_wav".into());
    }
    if target.exists() {
        return Err("audio_export_exists".into());
    }
    let tools = fabric_audio::decode::AudioTools::at(root);
    let duration = tools.probe(input)?;
    let frames = fabric_audio::format::ClipRange { start, end }.resolve(duration, 48_000)?;
    let parent = target.parent().ok_or("audio_export_path_invalid")?;
    if !parent.is_dir() {
        return Err("audio_export_path_invalid".into());
    }
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let temp = parent.join(format!(
        ".fabric-export-{}-{}-{}.wav",
        std::process::id(),
        chrono::Utc::now().timestamp_millis(),
        SEQ.fetch_add(1, Ordering::Relaxed)
    ));
    let filter = format!(
        "aresample=48000,atrim=start_sample={}:end_sample={},asetpts=PTS-STARTPTS",
        frames.start, frames.end
    );
    let mut cmd = Command::new(&tools.ffmpeg);
    cmd.args([
        "-nostdin",
        "-v",
        "error",
        "-n",
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
        "-ar",
        "48000",
        "-acodec",
        "pcm_s16le",
        "-f",
        "wav",
    ])
    .arg(&temp)
    .stdin(Stdio::null())
    .stdout(Stdio::null())
    .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    if cancelled.load(Ordering::Acquire) {
        return Err("audio_export_cancelled".into());
    }
    let mut child = cmd.spawn().map_err(|e| e.to_string())?;
    let status = loop {
        if cancelled.load(Ordering::Acquire) {
            let _ = child.kill();
            let _ = child.wait();
            let _ = std::fs::remove_file(&temp);
            return Err("audio_export_cancelled".into());
        }
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) => std::thread::sleep(std::time::Duration::from_millis(50)),
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                let _ = std::fs::remove_file(&temp);
                return Err(e.to_string());
            }
        }
    };
    let success = status.success()
        && std::fs::metadata(&temp)
            .map(|meta| meta.len() > 44)
            .unwrap_or(false);
    if !success {
        let _ = std::fs::remove_file(&temp);
        return Err("audio_export_failed".into());
    }
    if cancelled.load(Ordering::Acquire) {
        let _ = std::fs::remove_file(&temp);
        return Err("audio_export_cancelled".into());
    }
    crate::file_publish::publish_new(&temp, target).map_err(|e| {
        let _ = std::fs::remove_file(&temp);
        if e.kind() == std::io::ErrorKind::AlreadyExists {
            "audio_export_exists".to_string()
        } else {
            e.to_string()
        }
    })
}

fn valid_range(start: f64, end: f64) -> bool {
    start.is_finite() && end.is_finite() && start >= 0.0 && end > start
}

fn valid_cut_range(start: f64, end: f64, duration: f64) -> bool {
    valid_range(start, end)
        && duration.is_finite()
        && duration > 0.0
        && start < duration
        && end <= duration
        && end - start < duration
}

fn trim(root: &Path, input: &Path, start: f64, end: f64) -> Result<PathBuf, String> {
    if !input.is_file() || !valid_range(start, end) {
        return Err(crate::i18n::t("neptune.trimInvalid"));
    }
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let dir = crate::paths::user_data(root).join("audio_clips");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let stamp = chrono::Utc::now().timestamp_millis();
    let dest = dir.join(format!(
        "clip_{stamp}_{}.wav",
        SEQ.fetch_add(1, Ordering::Relaxed)
    ));
    let ffmpeg = root.join(if cfg!(windows) {
        "ffmpeg.exe"
    } else {
        "ffmpeg"
    });
    let mut cmd = Command::new(ffmpeg);
    cmd.args([
        "-nostdin",
        "-v",
        "error",
        "-n",
        "-protocol_whitelist",
        "file,pipe",
        "-ss",
        &start.to_string(),
        "-i",
    ])
    .arg(input)
    .args([
        "-t",
        &(end - start).to_string(),
        "-vn",
        "-acodec",
        "pcm_s16le",
    ])
    .arg(&dest)
    .stdin(Stdio::null())
    .stdout(Stdio::null())
    .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    let output = cmd.output().map_err(|e| e.to_string())?;
    if !output.status.success()
        || std::fs::metadata(&dest)
            .map(|m| m.len() <= 44)
            .unwrap_or(true)
    {
        let _ = std::fs::remove_file(&dest);
        return Err(format!(
            "{} {}",
            crate::i18n::t("neptune.trimFailed"),
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    Ok(dest)
}

fn cut(root: &Path, input: &Path, start: f64, end: f64, duration: f64) -> Result<PathBuf, String> {
    if !input.is_file() || !valid_cut_range(start, end, duration) {
        return Err(crate::i18n::t("neptune.trimInvalid"));
    }
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let dir = crate::paths::user_data(root).join("audio_clips");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let stamp = chrono::Utc::now().timestamp_millis();
    let dest = dir.join(format!(
        "clip_{stamp}_{}.wav",
        SEQ.fetch_add(1, Ordering::Relaxed)
    ));
    let ffmpeg = root.join(if cfg!(windows) {
        "ffmpeg.exe"
    } else {
        "ffmpeg"
    });
    let mut cmd = Command::new(ffmpeg);
    cmd.args([
        "-nostdin",
        "-v",
        "error",
        "-n",
        "-protocol_whitelist",
        "file,pipe",
    ]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    if start <= 0.01 {
        cmd.args(["-ss", &end.to_string(), "-i"]).arg(input).args([
            "-t",
            &(duration - end).to_string(),
            "-vn",
            "-acodec",
            "pcm_s16le",
        ]);
    } else if end >= duration - 0.01 {
        cmd.args(["-i"])
            .arg(input)
            .args(["-t", &start.to_string(), "-vn", "-acodec", "pcm_s16le"]);
    } else {
        let filter = format!(
            "[0:a]atrim=start=0:end={start},asetpts=PTS-STARTPTS[pre];[0:a]atrim=start={end}:end={duration},asetpts=PTS-STARTPTS[post];[pre][post]concat=n=2:v=0:a=1[out]"
        );
        cmd.args(["-i"]).arg(input).args([
            "-filter_complex",
            &filter,
            "-map",
            "[out]",
            "-vn",
            "-acodec",
            "pcm_s16le",
        ]);
    }
    let output = cmd
        .arg(&dest)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .output()
        .map_err(|e| e.to_string())?;
    if !output.status.success()
        || std::fs::metadata(&dest)
            .map(|m| m.len() <= 44)
            .unwrap_or(true)
    {
        let _ = std::fs::remove_file(&dest);
        return Err(format!(
            "{} {}",
            crate::i18n::t("neptune.trimFailed"),
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    Ok(dest)
}

#[tauri::command]
pub async fn audio_trim(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    input: String,
    start: f64,
    end: f64,
) -> Result<String, String> {
    let root = crate::root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        let dest = trim(&root, Path::new(&input), start, end)?;
        let path = dest.to_string_lossy().into_owned();
        crate::asset_scope::grant_file(&app, &path);
        Ok(path)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
pub async fn audio_cut(
    app: AppHandle,
    state: State<'_, Mutex<crate::AppState>>,
    input: String,
    start: f64,
    end: f64,
    duration: f64,
) -> Result<String, String> {
    let root = crate::root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        let dest = cut(&root, Path::new(&input), start, end, duration)?;
        let path = dest.to_string_lossy().into_owned();
        crate::asset_scope::grant_file(&app, &path);
        Ok(path)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_finite_ordered_ranges_are_valid() {
        assert!(valid_range(0.0, 1.25));
        for (a, b) in [
            (-1.0, 2.0),
            (2.0, 1.0),
            (1.0, 1.0),
            (0.0, f64::INFINITY),
            (f64::NAN, 1.0),
        ] {
            assert!(!valid_range(a, b));
        }
    }

    #[test]
    fn only_valid_nonempty_cut_ranges_are_accepted() {
        assert!(valid_cut_range(0.0, 1.0, 3.0));
        assert!(!valid_cut_range(0.0, 3.0, 3.0));
        assert!(!valid_cut_range(2.0, 4.0, 3.0));
        assert!(!valid_cut_range(1.0, 1.0, 3.0));
    }
}
