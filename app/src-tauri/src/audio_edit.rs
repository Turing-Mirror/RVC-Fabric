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
}
