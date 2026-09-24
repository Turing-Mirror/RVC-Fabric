//! Bounded waveform extraction shared by the audio library and legacy trim editor.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::HashMap,
    fs,
    io::{BufReader, ErrorKind, Read},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, LazyLock, Mutex,
    },
};
use tauri::State;

const RATE: u32 = 8_000;
const CACHE_VERSION: u8 = 2;
const MAX_WAVEFORM_JOBS: usize = 4;
static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);
static JOBS: LazyLock<Mutex<HashMap<String, Arc<Job>>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

#[derive(Clone, Deserialize, Serialize)]
pub struct Waveform {
    pub duration: f64,
    pub peaks: Vec<u8>,
}

#[derive(Deserialize, Serialize)]
struct Cache {
    version: u8,
    waveform: Waveform,
}

#[derive(Default)]
struct Job {
    cancelled: AtomicBool,
    child: Mutex<Option<Child>>,
}

struct Reap<'a>(&'a Job);
impl Drop for Reap<'_> {
    fn drop(&mut self) {
        if let Ok(mut slot) = self.0.child.lock() {
            if let Some(mut child) = slot.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

impl Job {
    fn cancel(&self) {
        self.cancelled.store(true, Ordering::Release);
        if let Ok(mut child) = self.child.lock() {
            if let Some(child) = child.as_mut() {
                let _ = child.kill();
            }
        }
    }

    fn check(&self) -> Result<(), String> {
        if self.cancelled.load(Ordering::Acquire) {
            Err("audio_waveform_cancelled".into())
        } else {
            Ok(())
        }
    }
}

/// 400 bins per second keeps the envelope detailed at the editor's maximum zoom;
/// the cap bounds memory and IPC size for very long files.
const BINS_PER_SEC: f64 = 400.0;
const MIN_BINS: f64 = 1_200.0;
const MAX_BINS: f64 = 720_000.0;

fn bins_for(duration: f64) -> usize {
    (duration * BINS_PER_SEC).ceil().clamp(MIN_BINS, MAX_BINS) as usize
}

fn cache_path(root: &Path, input: &Path, meta: &fs::Metadata) -> PathBuf {
    let mut hash = Sha256::new();
    hash.update(input.to_string_lossy().as_bytes());
    hash.update(meta.len().to_le_bytes());
    let modified = meta
        .modified()
        .ok()
        .and_then(|time| time.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|duration| duration.as_nanos())
        .unwrap_or_default();
    hash.update(modified.to_le_bytes());
    hash.update([CACHE_VERSION]);
    crate::paths::user_data(root)
        .join("audio/cache/peaks")
        .join(format!("{}.json", hex::encode(hash.finalize())))
}

fn read_cache(path: &Path) -> Option<Waveform> {
    if fs::metadata(path).ok()?.len() > 128 * 1024 {
        return None;
    }
    let data = fs::read(path).ok()?;
    let cache: Cache = serde_json::from_slice(&data).ok()?;
    if cache.version != CACHE_VERSION
        || !cache.waveform.duration.is_finite()
        || cache.waveform.duration <= 0.0
        || cache.waveform.peaks.len() != bins_for(cache.waveform.duration)
    {
        return None;
    }
    Some(cache.waveform)
}

fn write_cache(path: &Path, waveform: &Waveform) {
    let Some(dir) = path.parent() else { return };
    if fs::create_dir_all(dir).is_err() {
        return;
    }
    if fs::symlink_metadata(path).is_ok() && read_cache(path).is_none() {
        let _ = fs::remove_file(path);
    }
    let temp = dir.join(format!(
        ".peaks-{}-{}.tmp",
        std::process::id(),
        NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
    ));
    let cache = Cache {
        version: CACHE_VERSION,
        waveform: waveform.clone(),
    };
    if let Ok(bytes) = serde_json::to_vec(&cache) {
        if fs::write(&temp, bytes).is_ok() {
            let _ = crate::file_publish::publish_new(&temp, path);
        }
    }
    let _ = fs::remove_file(temp);
}

fn extract(root: &Path, input: &Path, job: &Job) -> Result<Waveform, String> {
    job.check()?;
    let input = fs::canonicalize(input).map_err(|_| "audio_file_missing")?;
    let meta = fs::metadata(&input).map_err(|e| e.to_string())?;
    if !meta.is_file() {
        return Err("audio_file_missing".into());
    }
    let cache = cache_path(root, &input, &meta);
    if let Some(waveform) = read_cache(&cache) {
        job.check()?;
        return Ok(waveform);
    }
    let tools = fabric_audio::decode::AudioTools::at(root);
    let duration = tools.probe(&input)?;
    job.check()?;
    let count = bins_for(duration);
    let total_samples = (duration * RATE as f64).ceil().max(1.0) as u64;
    let mut cmd = Command::new(&tools.ffmpeg);
    cmd.args([
        "-nostdin",
        "-v",
        "error",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
    ])
    .arg(&input)
    .args([
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "8000",
        "-f",
        "f32le",
        "-acodec",
        "pcm_f32le",
        "pipe:1",
    ])
    .stdin(Stdio::null())
    .stdout(Stdio::piped())
    .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000);
    }
    let mut child = cmd.spawn().map_err(|e| e.to_string())?;
    let stdout = match child.stdout.take() {
        Some(stdout) => stdout,
        None => {
            let _ = child.kill();
            let _ = child.wait();
            return Err("audio_waveform_pipe_missing".into());
        }
    };
    *job.child.lock().unwrap_or_else(|e| e.into_inner()) = Some(child);
    let _reap = Reap(job);
    if job.cancelled.load(Ordering::Acquire) {
        job.cancel();
    }
    let mut reader = BufReader::with_capacity(64 * 1024, stdout);
    let mut peaks = vec![0u8; count];
    let mut sample = [0u8; 4];
    let mut position = 0u64;
    let read_result = loop {
        job.check()?;
        match reader.read_exact(&mut sample) {
            Ok(()) => {
                let value = f32::from_le_bytes(sample);
                let amplitude = if value.is_finite() {
                    (value.abs().min(1.0) * 255.0).round() as u8
                } else {
                    0
                };
                let index = (((position as u128) * count as u128) / total_samples as u128)
                    .min((count - 1) as u128) as usize;
                peaks[index] = peaks[index].max(amplitude);
                position += 1;
            }
            Err(error) if error.kind() == ErrorKind::UnexpectedEof => break Ok(()),
            Err(error) => break Err(error.to_string()),
        }
    };
    drop(reader);
    let status = job
        .child
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .take()
        .ok_or("audio_waveform_process_missing")?
        .wait()
        .map_err(|e| e.to_string())?;
    job.check()?;
    read_result?;
    if !status.success() || position == 0 {
        return Err("audio_waveform_failed".into());
    }
    let waveform = Waveform { duration, peaks };
    write_cache(&cache, &waveform);
    Ok(waveform)
}

#[tauri::command]
pub async fn audio_waveform_get(
    state: State<'_, Mutex<crate::AppState>>,
    input: String,
    request_id: String,
) -> Result<Waveform, String> {
    if request_id.is_empty()
        || request_id.len() > 80
        || !request_id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-')
    {
        return Err("audio_waveform_request_invalid".into());
    }
    let root = crate::root_clone(&state)?;
    let job = Arc::new(Job::default());
    {
        let mut jobs = JOBS.lock().unwrap_or_else(|e| e.into_inner());
        if jobs.contains_key(&request_id) {
            return Err("audio_waveform_request_busy".into());
        }
        if jobs.len() >= MAX_WAVEFORM_JOBS {
            return Err("audio_waveform_busy".into());
        }
        jobs.insert(request_id.clone(), job.clone());
    }
    let result =
        tauri::async_runtime::spawn_blocking(move || extract(&root, Path::new(&input), &job)).await;
    JOBS.lock()
        .unwrap_or_else(|e| e.into_inner())
        .remove(&request_id);
    result.map_err(|e| e.to_string())?
}

#[tauri::command]
pub fn audio_waveform_cancel(request_id: String) -> bool {
    let job = JOBS
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .get(&request_id)
        .cloned();
    if let Some(job) = job {
        job.cancel();
        true
    } else {
        false
    }
}

pub fn cancel_all() {
    let jobs: Vec<_> = JOBS
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .values()
        .cloned()
        .collect();
    for job in jobs {
        job.cancel();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn waveform_bin_count_is_bounded() {
        assert_eq!(bins_for(1.0), 1_200);
        assert_eq!(bins_for(100.0), 40_000);
        assert_eq!(bins_for(100_000.0), 720_000);
    }
}
