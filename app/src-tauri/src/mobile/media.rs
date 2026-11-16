use super::*;
use axum::{
    body::Body,
    extract::{Path as RoutePath, Request, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use std::{
    fs,
    path::PathBuf,
    process::{Command, Stdio},
    time::{Duration, Instant},
};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
pub const MAX_UPLOAD: usize = 64 * 1024 * 1024;
#[derive(Serialize, Deserialize)]
pub(super) struct Job {
    pub owner: String,
    pub value: Value,
    files: HashMap<String, PathBuf>,
}
fn generated(name: &str) -> bool {
    let id = name.split(['-', '.']).next().unwrap_or("");
    id.len() == 64 && id.bytes().all(|c| c.is_ascii_hexdigit())
}
pub fn restore(root: &std::path::Path) -> HashMap<String, Job> {
    let folder = root.join("User_Data/mobile/files");
    let cutoff = std::time::SystemTime::now() - Duration::from_secs(7 * 24 * 3600);
    if let Ok(entries) = fs::read_dir(&folder) {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().into_owned();
            if !generated(&name) {
                continue;
            }
            if let Ok(meta) = entry.metadata() {
                if meta.modified().is_ok_and(|t| t < cutoff) && !meta.file_type().is_symlink() {
                    if meta.is_dir() {
                        let _ = fs::remove_dir_all(entry.path());
                    } else {
                        let _ = fs::remove_file(entry.path());
                    }
                }
            }
        }
    }
    let mut jobs: HashMap<String, Job> = fs::read(root.join("User_Data/mobile/jobs.json"))
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok())
        .unwrap_or_default();
    jobs.retain(|id, j| {
        generated(id)
            && j.files
                .values()
                .all(|p| p.starts_with(&folder) && p.is_file())
    });
    for job in jobs.values_mut() {
        if matches!(string(&job.value, "state"), "queued" | "running") {
            job.value["state"] = json!("error");
            job.value["error"] = json!("desktop_restarted");
        }
    }
    jobs
}
fn persist(s: &Service) {
    let jobs = lock(&s.jobs);
    let path = s.root.join("User_Data/mobile/jobs.json");
    let result = (|| -> Result<(), String> {
        fs::write(
            path.with_extension("tmp"),
            serde_json::to_vec(&*jobs).map_err(|e| e.to_string())?,
        )
        .map_err(|e| e.to_string())?;
        fs::rename(path.with_extension("tmp"), path).map_err(|e| e.to_string())
    })();
    if let Err(error) = result {
        crate::logging::shell_log!("mobile job history: {error}");
    }
}
fn error(code: &str) -> Response {
    (StatusCode::BAD_REQUEST, Json(json!({"error":code}))).into_response()
}
fn directory(s: &Service) -> PathBuf {
    s.root.join("User_Data/mobile/files")
}
pub async fn upload(
    State(s): State<Arc<Service>>,
    headers: HeaderMap,
    request: Request,
) -> Response {
    let device = match gateway::authorize(&s, &headers) {
        Ok(d) => d,
        Err(c) => return c.into_response(),
    };
    let name = format!("{}.input", pairing::secret());
    let path = directory(&s).join(&name);
    let result = async {
        tokio::fs::create_dir_all(directory(&s))
            .await
            .map_err(|e| e.to_string())?;
        let mut file = tokio::fs::File::create(&path)
            .await
            .map_err(|e| e.to_string())?;
        let mut stream = request.into_body().into_data_stream();
        let mut count = 0;
        while let Some(chunk) = stream.next().await {
            let chunk = chunk.map_err(|e| e.to_string())?;
            count += chunk.len();
            if count > MAX_UPLOAD {
                return Err("file_too_large".into());
            }
            file.write_all(&chunk).await.map_err(|e| e.to_string())?;
        }
        if count == 0 {
            return Err("empty_audio".into());
        }
        file.flush().await.map_err(|e| e.to_string())
    }
    .await;
    match result {
        Ok(()) => {
            lock(&s.uploads).insert(name.clone(), device.id);
            Json(json!({"file":name})).into_response()
        }
        Err(e) => {
            let _ = tokio::fs::remove_file(path).await;
            error(&e)
        }
    }
}
pub async fn create(
    State(s): State<Arc<Service>>,
    headers: HeaderMap,
    Json(request): Json<Value>,
) -> Response {
    let device = match gateway::authorize(&s, &headers) {
        Ok(d) => d,
        Err(c) => return c.into_response(),
    };
    if lock(&s.inner)
        .online
        .as_ref()
        .is_some_and(|c| c.id != device.id)
    {
        return error("bridge_busy");
    }
    let name = string(&request, "file").to_string();
    if lock(&s.uploads).get(&name) != Some(&device.id) {
        return error("unknown_upload");
    }
    let Some(voices) = request["voices"].as_array() else {
        return error("invalid_voices");
    };
    if voices.is_empty() || voices.len() > 8 {
        return error("invalid_voices");
    }
    let models = lock(&s.models).clone();
    let mut targets = Vec::new();
    for id in voices {
        if targets.iter().any(|v: &Value| &v["id"] == id) {
            return error("invalid_voices");
        }
        let Some(model) = models.iter().find(|m| &m["id"] == id) else {
            return error("invalid_voices");
        };
        targets.push(model.clone());
    }
    let Some(pitch) = request["pitch"].as_i64().filter(|p| (-24..=24).contains(p)) else {
        return error("invalid_pitch");
    };
    let id = pairing::secret();
    let resume;
    let revision;
    {
        let _gate = s.operations.lock().await;
        if s.converting() || crate::sts::is_busy() {
            return error("conversion_busy");
        }
        if s.running() && !selected() {
            return error("desktop_busy");
        }
        resume = s.running() && selected();
        if let Err(e) = s.stop().await {
            return error(&e);
        }
        revision = s.revision.load(Ordering::Acquire);
        let mut jobs = lock(&s.jobs);
        if jobs.len() >= 128 {
            if let Some(old) = jobs.keys().next().cloned() {
                jobs.remove(&old);
            }
        }
        jobs.insert(id.clone(),Job{owner:device.id,value:json!({"id":id,"state":"queued","progress":0.0,"cancel":false,"results":[],"error":""}),files:HashMap::new()});
    }
    persist(&s);
    let key = id.clone();
    let state = s.clone();
    tokio::spawn(async move {
        let _gate = state.operations.lock().await;
        let s = state.clone();
        let k = key.clone();
        let result =
            tokio::task::spawn_blocking(move || convert(&s, &k, &name, &targets, pitch as i32))
                .await;
        if let Err(e) = result {
            update(&state, &key, |j| {
                j.value["state"] = json!("error");
                j.value["error"] = json!(e.to_string());
            });
        }
        if resume && state.revision.load(Ordering::Acquire) == revision && !cancelled(&state, &key)
        {
            if let Err(e) = crate::engine_start_vc(state.app.state()).await {
                let _ = state
                    .events
                    .send(Outgoing::Json(json!({"type":"error","code":e})));
            }
        }
        state.changed();
    });
    Json(json!({"id":id})).into_response()
}
fn update(s: &Service, id: &str, action: impl FnOnce(&mut Job)) {
    let mut jobs = lock(&s.jobs);
    if let Some(j) = jobs.get_mut(id) {
        action(j);
    }
    drop(jobs);
    persist(s);
}
fn cancelled(s: &Service, id: &str) -> bool {
    lock(&s.jobs)
        .get(id)
        .is_none_or(|j| j.value["cancel"].as_bool() == Some(true))
}
fn convert(s: &Service, id: &str, name: &str, models: &[Value], pitch: i32) {
    update(s, id, |j| j.value["state"] = json!("running"));
    let result = (|| -> Result<(), String> {
        let tools = fabric_audio::decode::AudioTools::at(&s.root);
        if cancelled(s, id) {
            return Ok(());
        }
        let source = directory(s).join(name);
        let duration = tools.probe(&source)?;
        if duration <= 0.0 {
            return Err("empty_audio".into());
        }
        if duration > 600.0 {
            return Err("audio_too_long".into());
        }
        let original = format!("{id}-original.wav");
        let input = directory(s).join(&original);
        let mut command = Command::new(&tools.ffmpeg);
        command
            .args(["-nostdin", "-v", "error", "-y", "-i"])
            .arg(&source)
            .args(["-t", "600", "-ac", "1", "-ar", "48000"])
            .arg(&input);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let mut child = command
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| e.to_string())?;
        let deadline = Instant::now() + Duration::from_secs(60);
        loop {
            if cancelled(s, id) || Instant::now() > deadline {
                let _ = child.kill();
                let _ = child.wait();
                let _ = fs::remove_file(&input);
                return if cancelled(s, id) {
                    Ok(())
                } else {
                    Err("decode_timeout".into())
                };
            }
            if let Some(status) = child.try_wait().map_err(|e| e.to_string())? {
                if !status.success() {
                    return Err("decode_failed".into());
                }
                break;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        update(s, id, |j| {
            j.value["original"] = json!(original);
            j.files.insert(original.clone(), input.clone());
        });
        for (index, model) in models.iter().enumerate() {
            if cancelled(s, id) {
                break;
            }
            let folder = directory(s).join(id).join(index.to_string());
            fs::create_dir_all(&folder).map_err(|e| e.to_string())?;
            let opts = crate::sts::ConvertOpts {
                owner: Some(id.into()),
                quiet: true,
                resample_sr: 48000,
                format: "wav".into(),
                ..Default::default()
            };
            let result = crate::sts::run(
                &s.app,
                &s.root,
                &input.to_string_lossy(),
                &folder.to_string_lossy(),
                pitch,
                "rmvpe",
                model["index_rate"].as_f64().unwrap_or(0.0),
                string(model, "path"),
                string(model, "index"),
                opts,
                None,
            )?;
            if cancelled(s, id) {
                break;
            }
            let file = result["files"]
                .as_array()
                .and_then(|v| v.first())
                .and_then(Value::as_str)
                .ok_or("conversion_failed")?;
            let key = format!("{id}-{}.wav", string(model, "id"));
            let path = PathBuf::from(file);
            if !path.is_file() {
                return Err("conversion_failed".into());
            }
            update(s, id, |j| {
                j.files.insert(key.clone(), path);
                j.value["results"]
                    .as_array_mut()
                    .unwrap()
                    .push(json!({"file":key,"voice":model["id"],"name":model["name"]}));
                j.value["progress"] = json!((index + 1) as f64 / models.len() as f64);
            });
        }
        Ok(())
    })();
    let cancel = cancelled(s, id);
    update(s, id, |j| {
        j.value["state"] = json!(if cancel {
            "cancelled"
        } else if result.is_err() {
            "error"
        } else {
            "done"
        });
        if let Err(e) = result {
            j.value["error"] = json!(e);
        }
    });
}
pub async fn status(
    State(s): State<Arc<Service>>,
    headers: HeaderMap,
    RoutePath(id): RoutePath<String>,
) -> Response {
    let device = match gateway::authorize(&s, &headers) {
        Ok(d) => d,
        Err(c) => return c.into_response(),
    };
    match lock(&s.jobs).get(&id).filter(|j| j.owner == device.id) {
        Some(j) => Json(j.value.clone()).into_response(),
        None => StatusCode::NOT_FOUND.into_response(),
    }
}
pub async fn cancel(
    State(s): State<Arc<Service>>,
    headers: HeaderMap,
    RoutePath(id): RoutePath<String>,
) -> Response {
    let device = match gateway::authorize(&s, &headers) {
        Ok(d) => d,
        Err(c) => return c.into_response(),
    };
    {
        let mut jobs = lock(&s.jobs);
        let Some(job) = jobs.get_mut(&id).filter(|j| j.owner == device.id) else {
            return StatusCode::NOT_FOUND.into_response();
        };
        job.value["cancel"] = json!(true);
    }
    crate::sts::cancel_for(Some(&id));
    Json(json!({"ok":true})).into_response()
}
pub async fn download(
    State(s): State<Arc<Service>>,
    headers: HeaderMap,
    RoutePath(name): RoutePath<String>,
) -> Response {
    let device = match gateway::authorize(&s, &headers) {
        Ok(d) => d,
        Err(c) => return c.into_response(),
    };
    let path = lock(&s.jobs)
        .values()
        .filter(|j| j.owner == device.id)
        .find_map(|j| j.files.get(&name).cloned());
    let Some(path) = path else {
        return StatusCode::NOT_FOUND.into_response();
    };
    let Ok(file) = tokio::fs::File::open(path).await else {
        return StatusCode::NOT_FOUND.into_response();
    };
    let stream = futures_util::stream::try_unfold(file, |mut file| async move {
        let mut chunk = vec![0; 65536];
        let n = file.read(&mut chunk).await?;
        chunk.truncate(n);
        Ok::<_, std::io::Error>(if n == 0 { None } else { Some((chunk, file)) })
    });
    ([("content-type", "audio/wav")], Body::from_stream(stream)).into_response()
}
