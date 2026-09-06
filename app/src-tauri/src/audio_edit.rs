use std::{
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex,
    },
};
use tauri::{AppHandle, State};

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
    let ffmpeg = root.join(if cfg!(windows) { "ffmpeg.exe" } else { "ffmpeg" });
    let mut cmd = Command::new(ffmpeg);
    cmd.args(["-nostdin", "-v", "error", "-n", "-protocol_whitelist", "file,pipe"]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    if start <= 0.01 {
        cmd.args(["-ss", &end.to_string(), "-i"])
            .arg(input)
            .args(["-t", &(duration - end).to_string(), "-vn", "-acodec", "pcm_s16le"]);
    } else if end >= duration - 0.01 {
        cmd.args(["-i"])
            .arg(input)
            .args(["-t", &start.to_string(), "-vn", "-acodec", "pcm_s16le"]);
    } else {
        let filter = format!(
            "[0:a]atrim=start=0:end={start},asetpts=PTS-STARTPTS[pre];[0:a]atrim=start={end}:end={duration},asetpts=PTS-STARTPTS[post];[pre][post]concat=n=2:v=0:a=1[out]"
        );
        cmd.args(["-i"])
            .arg(input)
            .args(["-filter_complex", &filter, "-map", "[out]", "-vn", "-acodec", "pcm_s16le"]);
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
