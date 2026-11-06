//! Mobile pairing and audio are owned by the desktop application and its worker.
mod audio;
mod catalog;
mod gateway;
mod media;
mod mixer;
mod pairing;

use serde_json::{json, Map, Value};
use std::{
    collections::HashMap,
    path::PathBuf,
    sync::{
        atomic::{AtomicU16, AtomicU64, Ordering},
        Arc, Mutex, MutexGuard, OnceLock,
    },
};
use tauri::{AppHandle, Emitter, Manager};
use tokio::sync::{broadcast, Mutex as AsyncMutex};

pub(super) fn lock<T>(m: &Mutex<T>) -> MutexGuard<'_, T> {
    m.lock().unwrap_or_else(|e| e.into_inner())
}
fn string<'a>(v: &'a Value, key: &str) -> &'a str {
    v[key].as_str().unwrap_or("")
}
#[derive(Clone)]
enum Outgoing {
    Json(Value),
    Audio(Vec<u8>),
    Close(String),
}
struct Connection {
    id: String,
    name: String,
    nonce: String,
    phone: Value,
    last_seen: u64,
    last_audio: u64,
    microphone_seen: bool,
}
struct Inner {
    pairing: pairing::Pairing,
    online: Option<Connection>,
    selected: bool,
    input: Option<audio::EngineInput>,
    pending: Vec<u8>,
    monitor: Option<audio::Monitor>,
    output: Option<audio::Monitor>,
    monitor_device: String,
    output_device: String,
    clips: mixer::Clips,
    drops: u64,
}
pub struct Service {
    app: AppHandle,
    root: PathBuf,
    session: String,
    port: AtomicU16,
    revision: AtomicU64,
    inner: Mutex<Inner>,
    operations: AsyncMutex<()>,
    listener: AsyncMutex<()>,
    network: Mutex<Option<(String, tokio::sync::oneshot::Sender<()>)>>,
    events: broadcast::Sender<Outgoing>,
    models: Mutex<Vec<Value>>,
    jobs: Mutex<HashMap<String, media::Job>>,
    uploads: Mutex<HashMap<String, String>>,
}
static SERVICE: OnceLock<Arc<Service>> = OnceLock::new();
pub fn initialize(app: AppHandle, root: PathBuf) -> Result<(), String> {
    let pairing = pairing::Pairing::open(&root)?;
    let jobs = media::restore(&root);
    let service = Arc::new(Service {
        app,
        root,
        session: pairing::secret(),
        port: AtomicU16::new(0),
        revision: AtomicU64::new(0),
        inner: Mutex::new(Inner {
            pairing,
            online: None,
            selected: false,
            input: None,
            pending: Vec::new(),
            monitor: None,
            output: None,
            monitor_device: String::new(),
            output_device: String::new(),
            clips: mixer::Clips::new(),
            drops: 0,
        }),
        operations: AsyncMutex::new(()),
        listener: AsyncMutex::new(()),
        network: Mutex::new(None),
        events: broadcast::channel(512).0,
        models: Mutex::new(Vec::new()),
        jobs: Mutex::new(jobs),
        uploads: Mutex::new(HashMap::new()),
    });
    SERVICE
        .set(service)
        .map_err(|_| "mobile_already_initialized".to_string())
}
fn service() -> Result<Arc<Service>, String> {
    SERVICE.get().cloned().ok_or("mobile_unavailable".into())
}
pub fn selected() -> bool {
    SERVICE.get().is_some_and(|s| lock(&s.inner).selected)
}
pub fn stop_audio() {
    if let Some(s) = SERVICE.get() {
        s.stop_audio();
    }
}
pub fn shutdown() {
    if let Some(s) = SERVICE.get() {
        s.disconnect();
        s.close_listener();
    }
}
pub struct Start {
    pub descriptor: Value,
    pub revision: u64,
}
pub fn prepare_start() -> Result<Option<Start>, String> {
    let Some(service) = SERVICE.get() else {
        return Ok(None);
    };
    if service.converting() {
        return Err("conversion_busy".into());
    }
    let mut inner = lock(&service.inner);
    if !inner.selected {
        return Ok(None);
    }
    if !inner
        .online
        .as_ref()
        .is_some_and(|c| c.phone["microphone_ready"].as_bool() == Some(true))
    {
        return Err(crate::i18n::t("mobile.waitMicrophone"));
    }
    let revision = service.revision.fetch_add(1, Ordering::AcqRel) + 1;
    inner.pending.clear();
    let weak = Arc::downgrade(service);
    let input = audio::EngineInput::create(Arc::new(move |pcm| {
        if let Some(s) = weak.upgrade() {
            if s.revision.load(Ordering::Acquire) == revision {
                s.publish(pcm);
            }
        }
    }))?;
    let descriptor = input.descriptor.clone();
    inner.input = Some(input);
    Ok(Some(Start {
        descriptor,
        revision,
    }))
}
pub fn start_current(start: &Start) -> bool {
    SERVICE
        .get()
        .is_some_and(|s| s.revision.load(Ordering::Acquire) == start.revision)
}

impl Service {
    fn close_listener(&self) {
        self.port.store(0, Ordering::Release);
        if let Some((_, stop)) = lock(&self.network).take() {
            let _ = stop.send(());
        }
    }
    fn converting(&self) -> bool {
        lock(&self.jobs)
            .values()
            .any(|j| matches!(string(&j.value, "state"), "queued" | "running"))
    }
    fn engine(&self) -> Value {
        crate::worker::status_for_ui(&self.root)
    }
    fn running(&self) -> bool {
        matches!(string(&self.engine(), "state"), "running" | "vc")
    }
    fn stop_audio(&self) {
        self.revision.fetch_add(1, Ordering::AcqRel);
        let mut inner = lock(&self.inner);
        inner.input = None;
        inner.pending.clear();
        // Close queued hardware audio immediately; opening is an explicit control.
        inner.monitor = None;
        inner.output = None;
    }
    fn disconnect(&self) {
        self.stop_audio();
        let mut inner = lock(&self.inner);
        inner.selected = false;
        if let Some(c) = inner.online.take() {
            let _ = self.events.send(Outgoing::Close(c.nonce));
        }
        inner.clips = mixer::Clips::new();
    }
    fn status(&self) -> Value {
        let engine = self.engine();
        let cfg = crate::config::read(&self.root);
        let inner = lock(&self.inner);
        let voice = cfg.get("pth_path").and_then(Value::as_str).unwrap_or("");
        let profile = cfg
            .get("_active_profile_id")
            .and_then(Value::as_str)
            .unwrap_or("");
        let mut settings = Map::new();
        for key in [
            "pitch",
            "formant",
            "index_rate",
            "in_gain_db",
            "out_gain_db",
            "block_time",
            "I_noise_reduce",
        ] {
            settings.insert(key.into(), cfg.get(key).cloned().unwrap_or(Value::Null));
        }
        json!({"type":"status","running":inner.selected&&matches!(string(&engine,"state"),"running"|"vc"),
            "voice":if voice.is_empty(){String::new()}else{catalog::id(voice)},"profile":profile,
            "settings":settings,"proc_ms":if inner.selected&&string(&engine,"state")=="running"{engine["infer_ms"].clone()}else{Value::Null},
            "buffer_ms":inner.input.as_ref().map(|input|input.queued_ms()),"drops":inner.drops,
            "engine_error":if inner.selected&&string(&engine,"state")=="error"{engine["error"].clone()}else{json!("")},
            "session_id":self.session,"converting":self.converting(),"tracks":inner.clips.status(),
            "diagnostic":false,"selected":inner.selected,"pc_monitor":{"enabled":inner.monitor.is_some(),"device":inner.monitor_device},
            "voice_output":{"enabled":inner.output.is_some(),"device":inner.output_device}})
    }
    fn desktop_status(&self) -> Value {
        let mut status = self.status();
        let inner = lock(&self.inner);
        status["enabled"] = json!(self.port.load(Ordering::Acquire) > 0);
        status["port"] = json!(self.port.load(Ordering::Acquire));
        status["devices"] = inner.pairing.public_devices();
        status["connected"] = json!(inner.online.is_some());
        status["device"] = inner
            .online
            .as_ref()
            .map(|c| json!({"id":c.id,"name":c.name,"phone":c.phone}))
            .unwrap_or(Value::Null);
        status
    }
    fn changed(&self) {
        let _ = self.app.emit("mobile-changed", self.desktop_status());
    }
    fn outputs() -> Value {
        json!(fabric_audio::output::devices()
            .unwrap_or_default()
            .into_iter()
            .map(|d| json!({"id":d.id,"name":d.name,"host":"Windows"}))
            .collect::<Vec<_>>())
    }
    fn refresh(&self) -> Value {
        let models = catalog::models(&self.root);
        let public = catalog::public(&models);
        *lock(&self.models) = models;
        let clips = crate::audio_library::snapshot(&self.root)
            .map(|l| json!(l.entries))
            .unwrap_or_else(|_| json!([]));
        json!({"type":"catalog","voices":public,"clips":clips,"output_devices":Self::outputs()})
    }
    fn publish(&self, pcm: Vec<u8>) {
        let mut inner = lock(&self.inner);
        inner.pending.extend(pcm);
        let complete = inner.pending.len() / (audio::FRAME * 2) * (audio::FRAME * 2);
        let frames: Vec<u8> = inner.pending.drain(..complete).collect();
        for frame in frames.chunks_exact(audio::FRAME * 2) {
            self.output_frame(&mut inner, frame);
        }
    }
    fn output_frame(&self, inner: &mut Inner, frame: &[u8]) {
        let mut samples: Vec<f32> = frame
            .chunks_exact(2)
            .map(|s| i16::from_le_bytes([s[0], s[1]]) as f32 / 32768.0)
            .collect();
        let retired = inner.clips.mix(&mut samples);
        if !retired.is_empty() {
            tauri::async_runtime::spawn_blocking(move || drop(retired));
        }
        if let Some(m) = inner.monitor.as_mut() {
            m.write(&samples);
        }
        if inner.monitor.is_none() || inner.monitor_device != inner.output_device {
            if let Some(m) = inner.output.as_mut() {
                m.write(&samples);
            }
        }
        let bytes: Vec<u8> = samples
            .iter()
            .flat_map(|s| ((s.clamp(-1.0, 1.0) * 32767.0) as i16).to_le_bytes())
            .collect();
        let _ = self.events.send(Outgoing::Audio(bytes));
    }
    async fn stop(&self) -> Result<(), String> {
        self.stop_audio();
        if selected() {
            crate::engine_stop_vc(self.app.state(), Some(false)).await?;
        }
        self.changed();
        Ok(())
    }
    async fn command(self: &Arc<Self>, command: Value) -> Result<Value, String> {
        let kind = string(&command, "type");
        if kind == "stop" {
            self.stop().await?;
            return Ok(self.status());
        }
        if kind == "phone_status" {
            let idle = !self.running();
            let stop = {
                let mut inner = lock(&self.inner);
                let ready = command["microphone_ready"].as_bool() == Some(true);
                let first_ready = if let Some(c) = inner.online.as_mut() {
                    c.last_seen = pairing::now();
                    c.phone = command.clone();
                    let first = !c.microphone_seen && ready;
                    c.microphone_seen |= first;
                    first
                } else {
                    false
                };
                if idle && first_ready {
                    inner.selected = true;
                }
                !ready && inner.selected && inner.input.is_some()
            };
            if stop {
                self.stop().await?;
            }
            return Ok(self.status());
        }
        let revision = command["_revision"]
            .as_u64()
            .unwrap_or_else(|| self.revision.load(Ordering::Acquire));
        let _operation = self.operations.lock().await;
        if kind == "start" && revision != self.revision.load(Ordering::Acquire) {
            return Err("operation_cancelled".into());
        }
        if self.converting() && matches!(kind, "start" | "select" | "settings") {
            return Err("conversion_busy".into());
        }
        if !selected() && self.running() && matches!(kind, "start" | "select" | "settings") {
            return Err("desktop_busy".into());
        }
        match kind {
            "refresh" => {
                let s = self.clone();
                return tokio::task::spawn_blocking(move || s.refresh())
                    .await
                    .map_err(|e| e.to_string());
            }
            "start" => {
                {
                    let mut i = lock(&self.inner);
                    let Some(c) = i.online.as_mut() else {
                        return Err("connection_failed".into());
                    };
                    // Older phones start capture with their connection and have no phone_status message.
                    if c.phone.as_object().is_some_and(|p| p.is_empty()) {
                        c.phone = json!({"microphone_ready":true,"legacy":true});
                    }
                    i.selected = true;
                }
                let result = crate::engine_start_vc(self.app.state()).await?;
                if string(&result, "state") == "error" {
                    return Err(string(&result, "error").into());
                }
            }
            "select" => {
                let model = lock(&self.models)
                    .iter()
                    .find(|v| v["id"] == command["voice"])
                    .cloned()
                    .ok_or("unknown_voice")?;
                let profile = string(&command, "profile");
                if !profile.is_empty() {
                    let valid = model["profiles"]
                        .as_array()
                        .is_some_and(|p| p.iter().any(|p| string(p, "id") == profile));
                    if !valid {
                        return Err("unknown_profile".into());
                    }
                }
                crate::voices_select(
                    self.app.clone(),
                    self.app.state(),
                    Some(string(&model, "path").into()),
                    Some(string(&model, "dir").into()),
                    Some(string(&model, "name").into()),
                )
                .await?;
                if !profile.is_empty() {
                    crate::voices::set_active_profile(
                        &self.root,
                        string(&model, "dir"),
                        if profile == "__default__" {
                            ""
                        } else {
                            profile
                        },
                    )?;
                }
                if self.running() {
                    crate::engine_swap_model(self.app.state()).await?;
                }
                let _ = self.app.emit(
                    "config-changed",
                    json!({"config":crate::config::read(&self.root)}),
                );
            }
            "settings" => {
                let patch = validate_settings(&command["patch"])?;
                let app = self.app.clone();
                let root = self.root.clone();
                tokio::task::spawn_blocking(move || -> Result<(), String> {
                    let out = crate::config::update(&root, patch.clone())?;
                    let _ = app.emit("config-changed", out);
                    if crate::worker::is_worker_alive(&root) {
                        crate::worker::set_hot(&root, patch)?;
                    }
                    Ok(())
                })
                .await
                .map_err(|e| e.to_string())??;
            }
            "monitor" | "output" => {
                let enabled = command["enabled"].as_bool().ok_or("invalid_setting")?;
                let mut device = string(&command, "device").to_string();
                if enabled && device.is_empty() {
                    device = fabric_audio::output::default_output_id()?;
                }
                let d = device.clone();
                let monitor = tokio::task::spawn_blocking(move || {
                    if enabled {
                        audio::Monitor::open(&d).map(Some)
                    } else {
                        Ok(None)
                    }
                })
                .await
                .map_err(|e| e.to_string())??;
                let mut inner = lock(&self.inner);
                if kind == "monitor" {
                    inner.monitor = monitor;
                    inner.monitor_device = device;
                } else {
                    inner.output = monitor;
                    inner.output_device = device;
                }
            }
            "play" | "clip" => {
                let s = self.clone();
                let c = command.clone();
                tokio::task::spawn_blocking(move || -> Result<(), String> {
                    let id = string(&c, "id");
                    let seek = string(&c, "action") == "seek";
                    if string(&c, "type") == "play" || seek {
                        let offset = if seek {
                            c["value"]
                                .as_f64()
                                .filter(|v| v.is_finite() && *v >= 0.0)
                                .ok_or("invalid_setting")?
                                / audio::RATE as f64
                        } else {
                            0.0
                        };
                        {
                            lock(&s.inner).clips.can_play(id, seek)?;
                        }
                        // File probing and decoder creation must never hold the audio mutex.
                        let clip = mixer::Clip::prepare(&s.root, id, offset)?;
                        let old = {
                            let mut inner = lock(&s.inner);
                            if revision != s.revision.load(Ordering::Acquire) {
                                return Err("operation_cancelled".into());
                            }
                            inner.clips.replace(id, clip, seek)?
                        };
                        drop(old);
                    } else {
                        let retired =
                            lock(&s.inner)
                                .clips
                                .control(id, string(&c, "action"), &c["value"])?;
                        drop(retired);
                    }
                    Ok(())
                })
                .await
                .map_err(|e| e.to_string())??;
            }
            "master_gain" => {
                lock(&self.inner).clips.gain = command["value"]
                    .as_f64()
                    .filter(|v| v.is_finite() && *v >= 0.0 && *v <= 2.0)
                    .ok_or("invalid_setting")?
                    as f32;
            }
            "ping" => {}
            _ => return Err("unknown_command".into()),
        }
        self.changed();
        Ok(self.status())
    }
}
fn validate_settings(value: &Value) -> Result<Map<String, Value>, String> {
    let mut out = Map::new();
    for (key, value) in value.as_object().ok_or("invalid_setting")? {
        if key == "I_noise_reduce" && value.is_boolean() {
            out.insert(key.clone(), value.clone());
            continue;
        }
        let (min, max) = match key.as_str() {
            "pitch" => (-24.0, 24.0),
            "formant" => (-2.0, 2.0),
            "in_gain_db" => (-12.0, 24.0),
            "out_gain_db" => (-30.0, 12.0),
            "index_rate" => (0.0, 1.0),
            _ => return Err("invalid_setting".into()),
        };
        let n = value
            .as_f64()
            .filter(|n| n.is_finite() && *n >= min && *n <= max)
            .ok_or("invalid_setting")?;
        out.insert(
            key.clone(),
            if key == "pitch" {
                json!(n.round() as i64)
            } else {
                json!(n)
            },
        );
    }
    Ok(out)
}

#[tauri::command]
pub fn mobile_status() -> Result<Value, String> {
    let s = service()?;
    let mut status = s.desktop_status();
    status["output_devices"] = Service::outputs();
    Ok(status)
}
fn pairing_host(host: Option<String>, addresses: &[String]) -> Result<String, String> {
    match host {
        Some(host) if addresses.contains(&host) => Ok(host),
        Some(_) => Err("network_unavailable".into()),
        None => addresses
            .first()
            .cloned()
            .ok_or("network_unavailable".into()),
    }
}
#[tauri::command]
pub async fn mobile_pairing(host: Option<String>) -> Result<Value, String> {
    let s = service()?;
    let addresses = gateway::addresses();
    let host = pairing_host(host, &addresses)?;
    s.listen(&host).await?;
    let endpoint = format!("http://{host}:{}", s.port.load(Ordering::Acquire));
    let name = std::env::var("COMPUTERNAME").unwrap_or_else(|_| "RVC Fabric".into());
    let invitation = lock(&s.inner).pairing.invite(&endpoint, &name);
    let mut uri = reqwest::Url::parse("rvcfabric://pair").map_err(|e| e.to_string())?;
    uri.query_pairs_mut()
        .append_pair("data", &invitation.to_string());
    let payload = uri.to_string();
    let svg = qrcode::QrCode::new(payload.as_bytes())
        .map_err(|e| e.to_string())?
        .render::<qrcode::render::svg::Color>()
        .min_dimensions(256, 256)
        .build();
    Ok(
        json!({"payload":payload,"svg":svg,"expires_at":invitation["expires_at"],"endpoint":endpoint,"addresses":addresses,"host":host}),
    )
}
#[tauri::command]
pub async fn mobile_action(action: Value) -> Result<Value, String> {
    let s = service()?;
    match string(&action, "type") {
        "use" => {
            crate::engine_stop_vc(s.app.state(), Some(false)).await?;
            let mut i = lock(&s.inner);
            if i.online.is_none() {
                return Err("connection_failed".into());
            }
            i.selected = true;
        }
        "computer" => {
            s.stop().await?;
            let mut i = lock(&s.inner);
            i.selected = false;
            if let Some(c) = i.online.as_mut() {
                c.microphone_seen = true;
            }
        }
        "disconnect" => {
            s.stop().await?;
            s.disconnect();
        }
        "disable" => {
            s.stop().await?;
            s.disconnect();
            s.close_listener();
        }
        "revoke" => {
            let id = string(&action, "id");
            let online = lock(&s.inner).online.as_ref().is_some_and(|c| c.id == id);
            if online {
                s.stop().await?;
                s.disconnect();
            }
            lock(&s.inner).pairing.revoke(id)?;
        }
        _ => {
            s.command(action).await?;
        }
    }
    s.changed();
    Ok(s.desktop_status())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn an_unavailable_selected_interface_is_not_silently_replaced() {
        let addresses = vec!["192.168.1.2".into()];
        assert_eq!(pairing_host(None, &addresses).unwrap(), addresses[0]);
        assert!(pairing_host(Some("192.168.2.3".into()), &addresses).is_err());
        assert!(pairing_host(Some("0.0.0.0".into()), &addresses).is_err());
    }
    #[test]
    fn settings_do_not_accept_paths_or_unbounded_values() {
        assert!(
            validate_settings(&json!({"pitch":12,"I_noise_reduce":true,"out_gain_db":-6})).is_ok()
        );
        for patch in [
            json!({"pth_path":"anything"}),
            json!({"pitch":25}),
            json!({"I_noise_reduce":"true"}),
            json!([]),
            json!({"out_gain_db":100}),
        ] {
            assert!(validate_settings(&patch).is_err());
        }
    }
}
