//! App-side collection and transport. Classification belongs to fabric-diagnostics.
use fabric_diagnostics::{Diagnostic, Evidence, Feature, Outcome};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    io::{Read, Seek, SeekFrom},
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

static NEXT: AtomicU64 = AtomicU64::new(1);

pub fn error_id() -> String {
    format!("{}-{}-{}", std::process::id(), chrono::Utc::now().timestamp_micros(),
        NEXT.fetch_add(1, Ordering::Relaxed))
}

/// Internal String results retain their existing signatures; only the IPC boundary
/// serializes this envelope as an object. Events and queue records reuse it.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CommandError {
    pub message: String,
    pub message_code: Option<String>,
    pub params: Value,
    pub diagnostic: Diagnostic,
}
impl CommandError {
    pub fn encoded(&self) -> String {
        serde_json::to_string(self).expect("diagnostic JSON")
    }
}
impl std::fmt::Display for CommandError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.message.fmt(f)
    }
}
impl std::error::Error for CommandError {}
impl From<CommandError> for String {
    fn from(error: CommandError) -> Self { error.encoded() }
}

pub fn decode(raw: &str) -> Option<CommandError> {
    serde_json::from_str(raw).ok()
}

pub fn failure(evidence: Evidence, message: String) -> CommandError {
    let mut diagnostic = fabric_diagnostics::diagnose(&evidence);
    adopt_specific_cause(&mut diagnostic, evidence.source_code.as_deref(), &evidence.source_params);
    // Keep the exact context alongside the raw chain for copy/support. Do not feed
    // request paths, device names or user input back into the text classifier.
    diagnostic.detail.text = format!("{}\n\n{}", evidence.text,
        serde_json::to_string_pretty(&evidence).expect("evidence JSON"));
    CommandError {
        message,
        message_code: evidence.source_code,
        params: Value::Object(evidence.source_params),
        diagnostic,
    }
}

/// No rule recognised the failure, but the worker already said something specific
/// (for example "the microphone is in use"). Show that sentence as the cause instead
/// of "the cause could not be determined". Templates that only carry an exit code,
/// a raw error or a log path are not specific and stay out.
fn adopt_specific_cause(d: &mut Diagnostic, source_code: Option<&str>, params: &serde_json::Map<String, Value>) {
    if d.code != "diag.unknown" {
        return;
    }
    let Some(code) = source_code.map(str::trim).filter(|c| !c.is_empty()) else { return };
    let key = if code.starts_with("msg.") || code.starts_with("s.") { code.to_string() } else { format!("msg.{code}") };
    let template = crate::i18n::t(&key);
    if template == key || ["{error}", "{detail}", "{log}", "{code}"].iter().any(|m| template.contains(m)) {
        return;
    }
    d.cause = Some(fabric_diagnostics::Message { key, params: params.clone() });
}

pub fn command_feature(command: &str) -> Feature {
    // Commands whose name prefix does not match what the user is doing. Keep this
    // list the same as the frontend's invokeFor calls.
    match command {
        "train_cleanup_scan" | "train_cleanup_apply" | "storage_usage" | "storage_clean"
        | "voices_list" | "consult_build" => return Feature::Other,
        "publication_export_packs" | "publication_read_manifest" | "publication_read_packs" => return Feature::ImportExport,
        "assets_install_vbcable" | "assets_uninstall_vbcable" => return Feature::Provision,
        "consult_record_start" | "sts_default_input" => return Feature::Recording,
        "autostart_set" | "dsp_effects" | "dsp_presets" | "dsp_preset_save" | "dsp_preset_delete"
        | "legacy_hotkey_set" => return Feature::Settings,
        _ => {}
    }
    if command.starts_with("train_") { Feature::Training }
    else if command.starts_with("tts_") || command == "voice_audition" { Feature::Tts }
    else if command.starts_with("separate_") { Feature::Separation }
    else if command.starts_with("sts_record") || command.starts_with("mic_test") { Feature::Recording }
    else if command.starts_with("sts_") { Feature::VoiceChange }
    else if command.starts_with("engine_start") || command == "engine_ensure" { Feature::EngineStart }
    else if command.starts_with("engine_") || command.starts_with("dsp_") { Feature::RealtimeVoiceChange }
    else if command.starts_with("provision_") || command.starts_with("runtime_") { Feature::Provision }
    else if command.starts_with("update_") { Feature::Update }
    else if command.starts_with("extra_") || command.starts_with("assets_") { Feature::Download }
    else if command.starts_with("store_") || command.starts_with("community_") || command.starts_with("plaza_") { Feature::Store }
    else if command.starts_with("voices_") || command.starts_with("ckpt_") || command.starts_with("model_version") { Feature::ImportExport }
    else if command.starts_with("config_") || command.starts_with("audio_") || command.starts_with("hotkey") { Feature::Settings }
    else { Feature::Other }
}

pub fn command_error(command: &str, raw: String) -> CommandError {
    if let Some(error) = decode(&raw) { return error; }
    let mut e = Evidence::new(command_feature(command), error_id());
    e.text = raw.clone();
    e.context.retry_safe = Some(false);
    e.context.outcome = Some(if raw == crate::i18n::t("s.a5ffdc95ee") { Outcome::Cancelled } else { Outcome::Failed });
    failure(e, raw)
}

pub fn worker_evidence(feature: Feature, value: &Value) -> Evidence {
    let mut e = Evidence::new(feature, value["error_id"].as_str().map(str::to_owned).unwrap_or_else(error_id));
    e.stage = value["stage"].as_str().map(str::to_owned);
    e.source_code = value["message_code"].as_str().map(str::to_owned)
        .or_else(|| value["code"].as_str().map(|code| format!("record.{code}")));
    e.source_params = value["message_params"].as_object().or_else(|| value["params"].as_object()).cloned().unwrap_or_default();
    // Python supplies raw evidence separately from its compatibility sentence.
    e.text = ["traceback", "detail", "error", "reason", "message"].iter()
        .filter_map(|key| value[*key].as_str()).filter(|s| !s.is_empty())
        .collect::<Vec<_>>().join("\n");
    e.exit_code = value["exit_code"].as_i64().map(|n| n as i32);
    e.os_error = value["os_error"].as_i64().map(|n| n as i32);
    e.http_status = value["http_status"].as_u64().map(|n| n as u16);
    e.context = serde_json::from_value(value["context"].clone()).unwrap_or_default();
    e.context.outcome.get_or_insert(Outcome::Failed);
    e.context.retry_safe.get_or_insert(false);
    e
}

pub fn worker_error(feature: Feature, value: &Value) -> String {
    let e = worker_evidence(feature, value);
    // Diagnose before the compatibility localization.
    let error = failure(e, crate::i18n::t_worker_msg(value));
    error.encoded()
}

/// Only log bytes written after this operation began may be evidence.
#[derive(Clone)]
pub struct LogSlice { path: PathBuf, start: u64, end: Option<u64> }
impl LogSlice {
    pub fn start(path: &Path) -> Self {
        Self { path: path.into(), start: std::fs::metadata(path).map(|m| m.len()).unwrap_or(0), end: None }
    }
    pub fn text(&self) -> std::io::Result<String> {
        let mut file = std::fs::File::open(&self.path)?;
        if file.metadata()?.len() < self.start {
            return Err(std::io::Error::other("current operation log was rotated or truncated"));
        }
        file.seek(SeekFrom::Start(self.start))?;
        let mut bytes = Vec::new();
        if let Some(end) = self.end { file.take(end.saturating_sub(self.start)).read_to_end(&mut bytes)?; }
        else { file.read_to_end(&mut bytes)?; }
        Ok(String::from_utf8_lossy(&bytes).into_owned())
    }
    pub fn finish(&self, feature: Feature, raw: String) -> String {
        if raw == crate::i18n::t("s.a5ffdc95ee") { return raw; }
        let (text, truncated) = match self.text() {
            Ok(text) => (text, false),
            Err(err) => (err.to_string(), true),
        };
        let mut error = decode(&raw).unwrap_or_else(|| {
            let mut e = Evidence::new(feature, error_id());
            e.text = format!("{raw}\n{text}");
            e.context.retry_safe = Some(false);
            failure(e, raw)
        });
        // A worker diagnostic already has the correctly scoped raw evidence.
        // Append the current process log for support without reclassifying it.
        error.diagnostic.detail.text.push_str(&format!("\n\n{text}"));
        error.diagnostic.detail.truncated |= truncated;
        error.diagnostic.detail.log_ref = Some(self.path.to_string_lossy().into_owned());
        crate::logging::note_run(&self.path, &error.encoded());
        error.encoded()
    }
}

pub fn event(mut value: Value, feature: Feature) -> Value {
    if value["phase"] == "error" || value["state"] == "error" || value["phase"] == "skip" {
        if value.get("diagnostic").is_none() {
            let raw = value["error"].as_str().or_else(|| value["reason"].as_str()).or_else(|| value["message"].as_str()).unwrap_or("");
            let error = decode(raw).unwrap_or_else(|| {
                let mut e = worker_evidence(feature, &value);
                if raw == crate::i18n::t("s.a5ffdc95ee") { e.context.outcome = Some(Outcome::Cancelled); }
                failure(e, raw.to_owned())
            });
            value["diagnostic"] = json!(error.diagnostic);
            value["message"] = json!(error.message);
            if value.get("error").is_some() { value["error"] = json!(error.message); }
            if value.get("message_code").is_none() { value["message_code"] = json!(error.message_code); }
            if value.get("params").is_none() { value["params"] = error.params; }
        }
    }
    if value["phase"] == "done" && value["skip"].as_u64().unwrap_or(0) > 0 {
        let mut e = Evidence::new(feature, error_id());
        e.context.outcome = Some(Outcome::Partial);
        e.context.counts = Some(fabric_diagnostics::Counts {
            total: value["total"].as_u64().unwrap_or(0),
            succeeded: value["ok"].as_u64().unwrap_or(0),
            failed: value["skip"].as_u64().unwrap_or(0), skipped: 0,
        });
        e.text = value.to_string();
        value["diagnostic"] = json!(failure(e, String::new()).diagnostic);
    }
    value
}

pub fn failed_item(mut value: Value, feature: Feature) -> Value {
    let raw = value["reason"].as_str().or_else(|| value["error"].as_str()).unwrap_or("");
    let error = decode(raw).unwrap_or_else(|| failure(worker_evidence(feature, &value), raw.into()));
    value["diagnostic"] = json!(error.diagnostic);
    value
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ipc_and_event_share_identity_and_raw_detail() {
        let error = worker_error(Feature::Recording, &json!({
            "phase":"error", "message_code":"record.open", "detail":"Invalid sample rate",
            "context":{"operation":"device_open"}
        }));
        let rejected = command_error("sts_record_start", error.clone());
        let emitted = event(json!({"phase":"error","message":error}), Feature::Recording);
        assert_eq!(emitted["diagnostic"]["error_id"], rejected.diagnostic.error_id);
        assert!(rejected.diagnostic.detail.text.contains("Invalid sample rate"));
    }
    #[test]
    fn log_slice_excludes_an_earlier_oom() {
        let root = crate::testutil::scratch("diagnostic-log-slice");
        std::fs::create_dir_all(&root).unwrap();
        let path = root.join("train.log");
        std::fs::write(&path, "CUDA out of memory\n").unwrap();
        let slice = LogSlice::start(&path);
        use std::io::Write;
        writeln!(std::fs::OpenOptions::new().append(true).open(&path).unwrap(), "new attempt failed").unwrap();
        assert_eq!(slice.text().unwrap(), "new attempt failed\n");
        let _ = std::fs::remove_dir_all(root);
    }
}

pub fn emit(app: &tauri::AppHandle, name: &str, payload: impl Serialize) -> tauri::Result<()> {
    use tauri::Emitter;
    let value = serde_json::to_value(payload)?;
    app.emit(name, event(value, command_feature(&name.replace('-', "_"))))
}

/// Status polling reuses the worker request's identity instead of inventing one per poll.
pub fn status(mut value: Value, feature: Feature) -> Value {
    use std::sync::{Mutex, OnceLock};
    static LAST: OnceLock<Mutex<std::collections::HashMap<String, Diagnostic>>> = OnceLock::new();
    if value["state"] != "error" && value["model_apply"]["phase"] != "failed" {
        if let Some(obj) = value.as_object_mut() { obj.remove("diagnostic"); }
        return value;
    }
    if serde_json::from_value::<Diagnostic>(value["diagnostic"].clone()).is_ok() { return value; }
    let raw = if value["model_apply"]["phase"] == "failed" {
        value["model_apply"]["error"].as_str().unwrap_or("")
    } else { value["error"].as_str().unwrap_or("") };
    if let Some(error) = decode(raw) {
        value["diagnostic"] = json!(error.diagnostic);
        return value;
    }
    let key = value["error_id"].as_str().map(str::to_owned).unwrap_or_else(||
        format!("{}:{}:{}:{}", value["pid"], value["last_cmd_seq"], value["message_code"], raw));
    let mut cache = LAST.get_or_init(Default::default).lock().unwrap_or_else(|e| e.into_inner());
    if let Some(diagnostic) = cache.get(&key) {
        value["diagnostic"] = json!(diagnostic);
        return value;
    }
    let mut evidence = worker_evidence(feature, &value);
    evidence.error_id = key.clone();
    evidence.text = if raw.is_empty() { evidence.text } else { format!("{raw}\n{}", evidence.text) };
    let diagnostic = failure(evidence, raw.into()).diagnostic;
    if cache.len() >= 64 { cache.clear(); }
    cache.insert(key, diagnostic.clone());
    value["diagnostic"] = json!(diagnostic);
    value
}

#[derive(Clone)]
struct WorkerRequest { seq: u64, id: String, slice: LogSlice }
static WORKER_LOGS: std::sync::OnceLock<std::sync::Mutex<std::collections::HashMap<PathBuf, Vec<WorkerRequest>>>> = std::sync::OnceLock::new();

pub fn worker_request(root: &Path, seq: u64, slice: LogSlice) {
    let mut all = WORKER_LOGS.get_or_init(Default::default).lock().unwrap_or_else(|e| e.into_inner());
    let requests = all.entry(root.into()).or_default();
    if seq == 0 { requests.clear(); }
    if let Some(previous) = requests.last_mut() { previous.slice.end = Some(slice.start); }
    requests.push(WorkerRequest { seq, id: error_id(), slice });
    if requests.len() > 64 { requests.remove(0); }
}

pub fn worker_status(root: &Path, mut value: Value, feature: Feature) -> Value {
    if value["state"] != "error" && value["model_apply"]["phase"] != "failed" { return status(value, feature); }
    let seq = if value["model_apply"]["phase"] == "failed" { value["model_apply"]["seq"].as_u64() }
        else { value["error_request_id"].as_u64().or_else(|| value["last_cmd_seq"].as_u64()) }.unwrap_or(0);
    let request = WORKER_LOGS.get_or_init(Default::default).lock().unwrap_or_else(|e| e.into_inner())
        .get(root).and_then(|requests| requests.iter().find(|r| r.seq == seq)).cloned();
    if let Some(request) = request {
        if value["error_id"].as_str().is_none() { value["error_id"] = json!(request.id); }
        match request.slice.text() {
            Ok(text) => value["detail"] = json!(text),
            Err(error) => { value["detail"] = json!(error.to_string()); value["detail_truncated"] = json!(true); }
        }
        value["log_ref"] = json!(request.slice.path.to_string_lossy());
    }
    let mut result = status(value, feature);
    if let Some(log_ref) = result["log_ref"].as_str().map(str::to_owned) {
        result["diagnostic"]["detail"]["log_ref"] = json!(log_ref);
        result["diagnostic"]["detail"]["truncated"] = json!(result["detail_truncated"] == true);
    }
    result
}

pub fn status_error(root: &Path, value: Value, feature: Feature) -> String {
    let value = worker_status(root, value, feature);
    let message = value["error"].as_str().or_else(|| value["model_apply"]["error"].as_str()).unwrap_or("").to_owned();
    match serde_json::from_value(value["diagnostic"].clone()) {
        Ok(diagnostic) => CommandError { message, message_code: value["message_code"].as_str().map(str::to_owned),
            params: value["message_params"].clone(), diagnostic }.encoded(),
        Err(_) => command_error("engine_start", message).encoded(),
    }
}

pub fn api_error(command: &str, error: impl Serialize) -> Value {
    let mut value = serde_json::to_value(error).expect("API error JSON");
    let mut evidence = worker_evidence(command_feature(command), &value);
    evidence.source_code = value["code"].as_str().map(str::to_owned);
    if value["code"] == "canceled" { evidence.context.outcome = Some(Outcome::Cancelled); }
    value["diagnostic"] = json!(failure(evidence, value["message"].as_str().unwrap_or("").into()).diagnostic);
    value
}
