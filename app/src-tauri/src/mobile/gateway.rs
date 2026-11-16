use super::*;
use axum::{
    extract::{
        ws::{Message, WebSocket},
        DefaultBodyLimit, State, WebSocketUpgrade,
    },
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use futures_util::{SinkExt, StreamExt};
use std::time::Duration;

pub fn addresses() -> Vec<String> {
    let mut interfaces = if_addrs::get_if_addrs().unwrap_or_default();
    interfaces.sort_by_key(|i| {
        let n = i.name.to_lowercase();
        (
            n.contains("virtual")
                || n.contains("vmware")
                || n.contains("vethernet")
                || n.contains("clash"),
            i.name.clone(),
        )
    });
    let mut result = Vec::new();
    for interface in interfaces {
        if let std::net::IpAddr::V4(ip) = interface.ip() {
            if !ip.is_loopback()
                && !ip.is_link_local()
                && !ip.is_unspecified()
                && !result.contains(&ip.to_string())
            {
                result.push(ip.to_string());
            }
        }
    }
    result
}
pub(super) fn authorize(s: &Service, headers: &HeaderMap) -> Result<pairing::Device, StatusCode> {
    let token = headers
        .get("authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .ok_or(StatusCode::UNAUTHORIZED)?;
    lock(&s.inner)
        .pairing
        .authorize(token)
        .ok_or(StatusCode::UNAUTHORIZED)
}
impl Service {
    pub(super) async fn listen(self: &Arc<Self>, host: &str) -> Result<(), String> {
        let _gate = self.listener.lock().await;
        if self.port.load(Ordering::Acquire) > 0 {
            if lock(&self.network)
                .as_ref()
                .is_some_and(|(address, _)| address == host)
            {
                return Ok(());
            }
            if lock(&self.inner).online.is_some() {
                return Err("connection_active".into());
            }
            self.close_listener();
        }
        let address: std::net::Ipv4Addr = host.parse().map_err(|_| "invalid_address")?;
        let socket = match tokio::net::TcpListener::bind((address, 8787)).await {
            Ok(s) => s,
            Err(_) => tokio::net::TcpListener::bind((address, 0))
                .await
                .map_err(|e| e.to_string())?,
        };
        let port = socket.local_addr().map_err(|e| e.to_string())?.port();
        let routes = Router::new()
            .route("/v1/pair", post(pair))
            .route("/v1/health", get(health))
            .route("/v1/ws", get(websocket))
            .route("/v1/uploads", post(media::upload))
            .route("/v1/jobs", post(media::create))
            .route("/v1/jobs/{id}", get(media::status).delete(media::cancel))
            .route("/v1/files/{name}", get(media::download))
            .layer(DefaultBodyLimit::max(media::MAX_UPLOAD))
            .with_state(self.clone());
        self.port.store(port, Ordering::Release);
        let (stop, stopped) = tokio::sync::oneshot::channel();
        *lock(&self.network) = Some((host.into(), stop));
        let s = self.clone();
        tokio::spawn(async move {
            if let Err(e) = axum::serve(socket, routes)
                .with_graceful_shutdown(async {
                    let _ = stopped.await;
                })
                .await
            {
                crate::logging::shell_log!("mobile listener: {e}");
            }
            if s.port.load(Ordering::Acquire) == port {
                s.port.store(0, Ordering::Release);
                s.disconnect();
            }
        });
        let s = self.clone();
        tokio::spawn(async move {
            let mut tick = tokio::time::interval(Duration::from_millis(20));
            tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
            let mut status_ticks = 0;
            loop {
                tick.tick().await;
                if s.port.load(Ordering::Acquire) != port {
                    break;
                }
                let mut expired = false;
                {
                    let mut inner = lock(&s.inner);
                    if let Some(c) = inner.online.as_ref() {
                        expired = pairing::now().saturating_sub(c.last_seen) > 15_000;
                    }
                    if inner.input.is_none() && inner.online.is_some() {
                        s.output_frame(&mut inner, &[0; audio::FRAME * 2]);
                    }
                }
                if expired {
                    let _ = s.stop().await;
                    s.disconnect();
                    s.changed();
                }
                status_ticks += 1;
                if status_ticks >= 25 {
                    status_ticks = 0;
                    let _ = s.events.send(Outgoing::Json(s.status()));
                    s.changed();
                }
            }
        });
        self.changed();
        Ok(())
    }
}
async fn pair(State(s): State<Arc<Service>>, Json(request): Json<Value>) -> Response {
    let result = lock(&s.inner).pairing.pair(
        string(&request, "ticket"),
        string(&request, "device_id"),
        string(&request, "name"),
    );
    match result {
        Ok(mut v) => {
            v["name"] =
                json!(std::env::var("COMPUTERNAME").unwrap_or_else(|_| "RVC Fabric".into()));
            s.changed();
            Json(v).into_response()
        }
        Err(e) => (StatusCode::BAD_REQUEST, Json(json!({"error":e}))).into_response(),
    }
}
async fn health(
    State(s): State<Arc<Service>>,
    headers: HeaderMap,
) -> Result<Json<Value>, StatusCode> {
    authorize(&s, &headers)?;
    Ok(Json(
        json!({"version":env!("CARGO_PKG_VERSION"),"protocol":1,"session_id":s.session,"running":s.status()["running"],"workers_ok":crate::worker::is_worker_alive(&s.root)}),
    ))
}
async fn websocket(
    State(s): State<Arc<Service>>,
    headers: HeaderMap,
    ws: WebSocketUpgrade,
) -> Response {
    let device = match authorize(&s, &headers) {
        Ok(d) => d,
        Err(code) => return code.into_response(),
    };
    ws.max_message_size(16 * 1024)
        .on_upgrade(move |socket| connected(s, socket, device))
}
async fn connected(s: Arc<Service>, mut socket: WebSocket, device: pairing::Device) {
    let nonce = pairing::secret();
    let accepted = {
        let mut inner = lock(&s.inner);
        if inner.online.is_some() {
            false
        } else {
            inner.online = Some(Connection {
                id: device.id.clone(),
                name: device.name.clone(),
                nonce: nonce.clone(),
                phone: json!({}),
                last_seen: pairing::now(),
                last_audio: pairing::now(),
                microphone_seen: false,
            });
            true
        }
    };
    if !accepted {
        let _ = socket
            .send(Message::Text(
                json!({"type":"error","code":"busy"}).to_string().into(),
            ))
            .await;
        let _ = socket.close().await;
        return;
    }
    let state = s.clone();
    let mut welcome = tokio::task::spawn_blocking(move || state.refresh())
        .await
        .unwrap_or_else(|_| json!({}));
    welcome["type"] = json!("welcome");
    welcome["protocol"] = json!(1);
    welcome["sample_rate"] = json!(audio::RATE);
    welcome["frame_samples"] = json!(audio::FRAME);
    welcome["session_id"] = json!(s.session);
    welcome["desktop_version"] = json!(env!("CARGO_PKG_VERSION"));
    welcome["diagnostic"] = json!(false);
    welcome["capabilities"] = json!([
        "pc_monitor",
        "input_denoise",
        "pairing",
        "microphone_control",
        "desktop_session"
    ]);
    let send_welcome = socket.send(Message::Text(welcome.to_string().into())).await;
    if send_welcome.is_ok() {
        let (mut sender, mut receiver) = socket.split();
        let mut events = s.events.subscribe();
        let writer_nonce = nonce.clone();
        let writer = tokio::spawn(async move {
            loop {
                let message = match events.recv().await {
                    Ok(Outgoing::Json(value)) => Message::Text(value.to_string().into()),
                    Ok(Outgoing::Audio(bytes)) => Message::Binary(bytes.into()),
                    Ok(Outgoing::Close(id)) => {
                        if id == writer_nonce {
                            break;
                        } else {
                            continue;
                        }
                    }
                    Err(_) => break,
                };
                if !matches!(
                    tokio::time::timeout(Duration::from_secs(3), sender.send(message)).await,
                    Ok(Ok(()))
                ) {
                    break;
                }
            }
            let _ = sender.close().await;
        });
        let (commands, mut queue) = tokio::sync::mpsc::channel::<Value>(32);
        let control_service = s.clone();
        let control = tokio::spawn(async move {
            while let Some(command) = queue.recv().await {
                let request_id = command["request_id"].clone();
                let mut reply = match control_service.command(command).await {
                    Ok(v) => v,
                    Err(e) => json!({"type":"error","code":e}),
                };
                reply["request_id"] = request_id;
                let _ = control_service.events.send(Outgoing::Json(reply));
            }
        });
        while let Some(Ok(message)) = receiver.next().await {
            let valid = {
                let mut i = lock(&s.inner);
                if let Some(c) = i.online.as_mut() {
                    if c.nonce == nonce {
                        c.last_seen = pairing::now();
                        true
                    } else {
                        false
                    }
                } else {
                    false
                }
            };
            if !valid || writer.is_finished() {
                break;
            }
            match message {
                Message::Binary(bytes) if bytes.len() == audio::FRAME * 2 => {
                    let mut inner = lock(&s.inner);
                    if let Some(c) = inner.online.as_mut() {
                        c.last_audio = pairing::now();
                    }
                    if let Some(input) = inner.input.as_ref() {
                        if !input.send(bytes.to_vec()) {
                            inner.drops += 1;
                        }
                    }
                }
                Message::Text(text) => {
                    let request = serde_json::from_str::<Value>(&text)
                        .ok()
                        .filter(|v| v.is_object() && v["type"].is_string());
                    if let Some(mut request) = request {
                        request["_revision"] = json!(s.revision.load(Ordering::Acquire));
                        if matches!(string(&request, "type"), "stop" | "phone_status") {
                            let request_id = request["request_id"].clone();
                            let mut reply = match s.command(request).await {
                                Ok(v) => v,
                                Err(e) => json!({"type":"error","code":e}),
                            };
                            reply["request_id"] = request_id;
                            let _ = s.events.send(Outgoing::Json(reply));
                        } else if let Err(e) = commands.try_send(request) {
                            let _=s.events.send(Outgoing::Json(json!({"type":"error","code":"command_busy","request_id":e.into_inner()["request_id"]})));
                        }
                    } else {
                        let _ = s.events.send(Outgoing::Json(
                            json!({"type":"error","code":"invalid_command"}),
                        ));
                    }
                }
                Message::Close(_) => break,
                _ => {}
            }
        }
        control.abort();
        writer.abort();
        let _ = control.await;
        let _ = writer.await;
    }
    let own = lock(&s.inner)
        .online
        .as_ref()
        .is_some_and(|c| c.nonce == nonce);
    if own {
        let _ = s.stop().await;
        s.disconnect();
        s.changed();
    }
}
