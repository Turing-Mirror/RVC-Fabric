//! RVC Fabric shell (Tauri).
//!
//! Stages 1–4: window/UI, worker bridge, Runtime provision, voice catalog & store.

pub mod catalog;
mod autostart;
mod ckpt;
mod config;
mod download;
mod dsp;
mod engine_assets;
mod hf;
mod extra_assets;
mod extract;
mod i18n;
mod legacy;
mod logging;
mod mic;
mod mirrors;
pub mod paths;
pub mod plaza;
mod protocol;
mod provision;
mod separate;
mod shell_extras;
mod sts;
mod store;
mod telemetry;
mod tool_window;
mod train;
mod tts;
mod ui_assets;
pub mod update;
mod voices;
mod window_watch;
mod worker;

use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use serde_json::{json, Map, Value};
use tauri::{AppHandle, Emitter, Manager, State};

struct AppState {
    root: PathBuf,
}

fn root_clone(state: &State<'_, Mutex<AppState>>) -> Result<PathBuf, String> {
    let g = state.lock().map_err(|e| e.to_string())?;
    Ok(g.root.clone())
}

/// engine-core / VB-Cable readiness for the first-run gate.
#[tauri::command]
fn assets_status(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    Ok(engine_assets::assets_status(&root_clone(&state)?))
}

/// 下载进度文案用的体积格式（与 provision 侧保持一致）。
fn fmt_size(n: u64) -> String {
    if n >= 1_000_000_000 {
        format!("{:.2} GB", n as f64 / 1e9)
    } else if n >= 1_000_000 {
        format!("{:.1} MB", n as f64 / 1e6)
    } else if n >= 1_000 {
        format!("{:.0} KB", n as f64 / 1e3)
    } else {
        format!("{n} B")
    }
}

/// 补全引擎资源（hubert / rmvpe / ffmpeg）。
///
/// 下载进度转发到 `provision-progress` 事件（phase=engine-core）。以前这里
/// 不传进度回调，首次安装的进度条在 Runtime 下完后停在原地不动 —— 而引擎
/// 资源几百 MB 正在下载，看起来和卡死一模一样。
#[tauri::command]
async fn assets_ensure_engine_core(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let cancel = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    tauri::async_runtime::spawn_blocking(move || {
        let cb: download::ProgressFn = Arc::new(move |done, total, phase| {
            let pct = ((done as f64 / total.max(1) as f64) * 100.0).clamp(0.0, 100.0);
            let m = match phase {
                "verify" => crate::i18n::t("s.34e863a12e"),
                other if other.starts_with("connecting:") => {
                    crate::i18n::te("s.727e8c1993", &(fmt_size(total)))
                }
                _ if done == 0 => crate::i18n::t("s.6bde20da46"),
                _ => crate::i18n::tn("s.1342ffb704", &[&fmt_size(done), &fmt_size(total), &format!("{:.1}", pct)]),
            };
            let _ = app.emit(
                "provision-progress",
                json!({
                    "phase": "engine-core",
                    "done": done,
                    "total": total.max(1),
                    "percent": pct,
                    "message": m,
                }),
            );
        });
        engine_assets::ensure_engine_core(&root, cancel, Some(cb)).map(|_| json!({"ok": true}))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// 补全 VB-Cable 安装包。进度同样走 `provision-progress`（phase=vbcable）。
#[tauri::command]
async fn assets_ensure_vbcable(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let cancel = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    tauri::async_runtime::spawn_blocking(move || {
        let cb: download::ProgressFn = Arc::new(move |done, total, phase| {
            let pct = ((done as f64 / total.max(1) as f64) * 100.0).clamp(0.0, 100.0);
            let m = match phase {
                "verify" => crate::i18n::t("s.3b227dfa30"),
                other if other.starts_with("connecting:") => {
                    crate::i18n::te("s.c86b0f4fc1", &(fmt_size(total)))
                }
                _ if done == 0 => crate::i18n::t("s.3a05d4d51e"),
                _ => crate::i18n::tn("s.350261fb86", &[&fmt_size(done), &fmt_size(total), &format!("{:.1}", pct)]),
            };
            let _ = app.emit(
                "provision-progress",
                json!({
                    "phase": "vbcable",
                    "done": done,
                    "total": total.max(1),
                    "percent": pct,
                    "message": m,
                }),
            );
        });
        engine_assets::ensure_vbcable_pack(&root, cancel, Some(cb)).map(|_| json!({"ok": true}))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// 静默安装虚拟声卡。装驱动能跑十几秒，同步命令会把界面卡死，所以丢到
/// 阻塞线程池里等。
#[tauri::command]
async fn assets_install_vbcable(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        engine_assets::install_vbcable(&root).map(|_| json!({"ok": true}))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// 静默卸载虚拟声卡。优先跑 Program Files 里那份官方卸载程序（和系统
/// 「应用和功能」同一条），没有再退回软件下的安装包。
#[tauri::command]
async fn assets_uninstall_vbcable(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        engine_assets::uninstall_vbcable(&root).map(|_| json!({"ok": true}))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Full effective settings (defaults overlaid with saved values).
#[tauri::command]
fn config_get(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    Ok(Value::Object(config::read(&root_clone(&state)?)))
}

/// Switch shell locale (tray / status message_code). Frontend keeps its own pack.
#[tauri::command]
fn i18n_set_locale(locale: String) -> Result<Value, String> {
    if !i18n::supported(&locale) {
        return Err(format!("unsupported locale: {locale}"));
    }
    i18n::set_locale(&locale);
    Ok(json!({"ok": true, "locale": locale}))
}

#[tauri::command]
fn i18n_get_locale() -> String {
    i18n::current()
}

/// Which keys belong to which settings group, and which are hot vs cold.
#[tauri::command]
fn config_describe() -> Value {
    config::describe()
}

/// Merge a patch, persist, mirror into inuse, and push hot keys to a running
/// stream. Returns `needs_restart` for the cold keys the UI must warn about.
#[tauri::command]
fn config_set(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    patch: Map<String, Value>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let out = config::update(&root, patch.clone())?;
    if let Err(e) = voices::persist_profile_patch(&root, &patch) {
        logging::shell_log!("persist profile: {e}");
    }
    if let Some(hot) = out.get("hot").and_then(|v| v.as_object()) {
        if !hot.is_empty() && worker::is_worker_alive(&root) {
            let _ = worker::set_hot(&root, hot.clone());
        }
    }
    let _ = app.emit("config-changed", &out);
    Ok(out)
}

/// 开机自启状态（读 HKCU Run 键）。状态以注册表为准，不走 app_config：
/// 自启是这台机器的行为，不该跟着配置档案走。
#[tauri::command]
fn autostart_get() -> autostart::AutostartStatus {
    autostart::get()
}

#[tauri::command]
fn autostart_set(enabled: bool) -> Result<(), String> {
    autostart::set(enabled)
}

/// 封面批量本地化（商店 / 模型页 / 首页共用）。返回 url → 本地缓存路径；
/// 失败的条目为空串，前端回退远程直连。
#[tauri::command]
async fn cover_resolve_many(
    state: State<'_, Mutex<AppState>>,
    urls: Vec<String>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        Ok::<Value, String>(Value::Object(store::resolve_covers(&root, &urls)))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Native image picker for the wallpaper setting. Returns the chosen path or
/// null when the user cancels. No size/dimension limits: the file is only
/// referenced by path and decoded by the webview on its own time — a huge
/// image merely loads slowly, it cannot break anything.
#[tauri::command]
fn pick_wallpaper() -> Option<String> {
    rfd::FileDialog::new()
        .add_filter(&crate::i18n::t("s.be8da62ea1"), &["jpg", "jpeg", "png", "webp", "bmp"])
        .set_title(&crate::i18n::t("s.501fdcd3ef"))
        .pick_file()
        .map(|p| p.to_string_lossy().into_owned())
}

/// Ask the catalog whether a newer build exists.
#[tauri::command]
async fn update_check() -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(|| update::check(12))
        .await
        .map_err(|e| e.to_string())?
}

/// Download a gui_patch and swap the external frontend/ directory.
#[tauri::command]
async fn update_apply(
    state: State<'_, Mutex<AppState>>,
    url: String,
    sha256: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let cancel = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    tauri::async_runtime::spawn_blocking(move || {
        update::apply_gui_patch(&root, &url, &sha256, cancel)
            .map(|p| json!({"ok": true, "path": p.to_string_lossy(), "restart_required": true}))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Register / unregister the global hotkeys.
#[tauri::command]
fn hotkeys_apply(app: AppHandle, enabled: bool) -> Value {
    let out = shell_extras::apply_hotkeys(&app, enabled);
    // 取消了「全局」的那些组合由前端的 keydown 接住，前端得知道改了什么。
    // 设置页每改一次快捷键都会调到这里，正好是通知的时机。
    let _ = app.emit("hotkeys://changed", ());
    out
}

/// Zip logs + machine info + settings for support.
///
/// `with_perf`：前端先问用户是否跑约一分钟的性能测试。
#[tauri::command]
async fn diagnostics_build(
    state: State<'_, Mutex<AppState>>,
    with_perf: bool,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        shell_extras::build_diagnostics(&root, with_perf).map(|(p, perf_note)| {
            let _ = shell_extras::reveal(&p);
            json!({
                "ok": true,
                "path": p.to_string_lossy(),
                "perf_note": perf_note,
            })
        })
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Bundle the current voice's config + profiles for paid tuning.
#[tauri::command]
async fn consult_build(
    state: State<'_, Mutex<AppState>>,
    note: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        shell_extras::build_consult_pack(&root, &note).map(|p| {
            let _ = shell_extras::reveal(&p);
            json!({"ok": true, "path": p.to_string_lossy()})
        })
    })
    .await
    .map_err(|e| e.to_string())?
}

/// More page: how much regenerable cache is sitting on disk.
#[tauri::command]
fn cache_status(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let bytes = paths::cache_footprint(&root);
    Ok(json!({
        "bytes": bytes,
        "mb": format!("{:.1}", bytes as f64 / (1024.0 * 1024.0)),
    }))
}

/// More page: wipe logs + TEMP + leftover downloads. Confirm in the UI first.
#[tauri::command]
fn cache_clear(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let stats = paths::clear_user_cache(&root);
    paths::log_clean_stats(&crate::i18n::t("s.cacheClear"), &root, &stats);
    Ok(json!({
        "ok": true,
        "removed_files": stats.removed_files,
        "removed_dirs": stats.removed_dirs,
        "failed": stats.failed,
        "freed_bytes": stats.freed_bytes,
        "freed_mb": format!("{:.1}", stats.freed_bytes as f64 / (1024.0 * 1024.0)),
    }))
}

/// Open a folder under User_Data in the file manager.
#[tauri::command]
fn reveal_user_dir(state: State<'_, Mutex<AppState>>, name: String) -> Result<(), String> {
    let root = root_clone(&state)?;
    let dir = paths::user_data(&root).join(name);
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    shell_extras::reveal(&dir.join("x"))
}

/// Opt-in daily ping. No-op when the user has not agreed.
#[tauri::command]
async fn telemetry_tick(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let accel = provision::read_package_meta_variant(&root).unwrap_or_else(|| "unknown".into());
    tauri::async_runtime::spawn_blocking(move || {
        Ok(telemetry::tick(&root, update::APP_VERSION, &accel))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// The UI answered the close prompt.
#[tauri::command]
fn close_finish(app: AppHandle, to_tray: bool) {
    shell_extras::finish_close(&app, to_tray);
}

/// Strategy B: replace the exe through the signed updater feed.
#[tauri::command]
async fn update_app(app: AppHandle) -> Result<Value, String> {
    update::run_app_updater(&app).await
}

/// 打开一个独立工具窗口（人声分离 / 训练音色 / 语音转换）。
///
/// 必须是 async：同步 command 跑在 WebView2 的 IPC 消息回调里，在那里同步建
/// 第二个 webview，wry 会泵消息等 controller 创建完成（wait_with_pump），
/// 而完成回调要等外层 IPC 回调先返回才能送达——两边互等，窗口永远白屏，
/// 之后所有命令全部挂起（wry#583 同款死锁）。改成 async 后命令体跑在
/// tokio 线程上，建窗经事件循环顶层派发，回调能正常送达。
#[tauri::command]
async fn tools_open(app: AppHandle, kind: String) -> Result<(), String> {
    tool_window::open(&app, &kind)
}

#[tauri::command]
fn ui_source() -> String {
    ui_assets::source_label()
}

/// Shipping version. The 「其他」page had this typed in as a literal, so it
/// would quietly disagree with the binary after any bump.
#[tauri::command]
fn shell_version() -> &'static str {
    update::APP_VERSION
}

/// Reported by the UI on first paint. Turns "the window is blank" from an
/// unfalsifiable user report into a line in `shell.log`.
#[tauri::command]
fn ui_ready() {
    ui_assets::mark_ui_ready();
}

/// Anything the UI's own error screen wants to show, written to `shell.log`.
/// Frontend exceptions otherwise die inside the webview console, which nobody
/// on a user's machine can open.
#[tauri::command]
fn ui_log(line: String) {
    // Bound it: an error loop must not be able to fill the disk one message at
    // a time.
    let line: String = line.chars().take(2000).collect();
    // Rate-limit too. This command is synchronous, which means it runs inline
    // on the thread that receives IPC — the window's own UI thread on Windows —
    // and it touches the disk. A frontend stuck in an error loop calling it
    // would freeze the window rather than report the problem.
    static GATE: Mutex<Option<(std::time::Instant, u32)>> = Mutex::new(None);
    const PER_WINDOW: u32 = 30;
    let window = std::time::Duration::from_secs(10);
    let mut g = GATE.lock().unwrap_or_else(|e| e.into_inner());
    let (since, count) = match *g {
        Some((t, n)) if t.elapsed() < window => (t, n),
        _ => (std::time::Instant::now(), 0),
    };
    *g = Some((since, count + 1));
    drop(g);
    match count {
        n if n < PER_WINDOW => logging::shell_log!("[ui] {line}"),
        n if n == PER_WINDOW => {
            logging::shell_log!(crate::i18n::t("s.b76d1399ec"))
        }
        _ => {}
    }
}

/// Plaza feed + changelog, already filtered for this version and today's date.
///
/// `plaza.rs` had no caller at all: the page shipped hardcoded placeholder
/// cards and a stale 1.2.4 changelog while the parser, the cnb.cool image
/// restriction and the placement rules all sat unused.
#[tauri::command]
async fn plaza_fetch(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        let (items, changelog, errors) = plaza::fetch(12);
        let today = plaza::today_yymmdd();
        let dismissed = config::dismissed_ads(&root);
        // Plaza placements are never dismissible — that rule lives in the
        // parser, so an empty `dismissed` list here would be equivalent. Pass
        // it anyway so the two placements go through one code path.
        let feed = plaza::visible_items(
            &items,
            plaza::PLACEMENT_PLAZA,
            update::APP_VERSION,
            &today,
            &dismissed,
        );
        let banner = plaza::pick_models_banner(&items, update::APP_VERSION, &today, &dismissed);
        // Newest dated row decides the tab dot. Undated rows carry no "new"
        // signal — otherwise an evergreen sponsor slot would keep the dot lit
        // forever, which is exactly the old hardcoded behaviour.
        let newest = feed
            .iter()
            .map(|it| it.date.as_str())
            .filter(|d| !d.is_empty())
            .max()
            .unwrap_or("")
            .to_string();
        let unread = !newest.is_empty() && newest > config::plaza_seen(&root);
        Ok(json!({
            "items": feed,
            "banner": banner,
            "changelog": changelog,
            "errors": errors,
            "app_version": update::APP_VERSION,
            "newest": newest,
            "unread": unread,
        }))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// The user opened the plaza — clear the tab dot up to `newest`.
#[tauri::command]
fn plaza_mark_seen(state: State<'_, Mutex<AppState>>, newest: String) -> Result<(), String> {
    config::set_plaza_seen(&root_clone(&state)?, &newest)
}

/// Remember a dismissed models-page banner so it stays gone across restarts.
#[tauri::command]
fn plaza_dismiss(state: State<'_, Mutex<AppState>>, id: String) -> Result<(), String> {
    config::dismiss_ad(&root_clone(&state)?, &id)
}

/// Open a link in the user's own browser. Restricted to http/https so a feed
/// can never hand us a `file://` or a shell scheme to launch.
#[tauri::command]
fn open_external(app: AppHandle, url: String) -> Result<(), String> {
    let ok = url.starts_with("https://") || url.starts_with("http://");
    if !ok {
        return Err(crate::i18n::t("s.88d3b1cad9").into());
    }
    use tauri_plugin_opener::OpenerExt;
    app.opener()
        .open_url(url, None::<&str>)
        .map_err(|e| e.to_string())
}

/// 「其他」page → 打开原版实时面板（gui_v1）。
#[tauri::command]
async fn legacy_open_panel(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || legacy::open_realtime_panel(&root))
        .await
        .map_err(|e| e.to_string())?
}

/// 「其他」page → 打开原版 WebUI（infer-web.py）。
#[tauri::command]
async fn legacy_open_webui(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || legacy::open_webui(&root))
        .await
        .map_err(|e| e.to_string())?
}

/// Path of the shell log, for the 「其他」page's "打开日志" action.
#[tauri::command]
fn log_path() -> Option<String> {
    logging::path().map(|p| p.to_string_lossy().into_owned())
}

#[tauri::command]
fn product_root(state: State<'_, Mutex<AppState>>) -> Result<String, String> {
    Ok(root_clone(&state)?.to_string_lossy().into_owned())
}

#[tauri::command]
fn engine_status(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    Ok(worker::status_for_ui(&root))
}

#[tauri::command]
async fn engine_ensure(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    if !paths::runtime_ready(&root) {
        let mut st = worker::status_for_ui(&root);
        if let Some(obj) = st.as_object_mut() {
            obj.insert("state".into(), json!("idle"));
            obj.insert("error".into(), json!(crate::i18n::t("s.75b84a31d6")));
            obj.insert("worker_alive".into(), json!(false));
        }
        return Ok(st);
    }
    // Called on app start and waits up to 90s for the worker. Inline, that is
    // a 90-second freeze on the first launch after an install.
    tauri::async_runtime::spawn_blocking(move || {
        let ms = if worker::dsp_requested(&root) {
            20_000
        } else {
            90_000
        };
        Ok(worker::ensure_worker_and_devices(&root, ms))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn engine_start_worker(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    if !paths::runtime_ready(&root) {
        return Ok(json!({"state": "error", "error": crate::i18n::t("s.a36cb645c2"), "pid": 0}));
    }
    // Waits up to 90s for the worker to come up. A sync command runs inline on
    // the IPC thread, so that wait froze the whole window.
    tauri::async_runtime::spawn_blocking(move || {
        worker::start_worker(&root)?;
        Ok(worker::wait_worker_ready(&root, 90_000))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn engine_start_vc(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    if !paths::runtime_ready(&root) {
        return Ok(json!({"state": "error", "error": crate::i18n::t("s.45309ba4c5"), "pid": 0}));
    }
    // The cold start is 20–40s (torch/CUDA) and the wait allows up to 180s.
    // Run it off the IPC thread or the window is frozen for that whole time —
    // no status updates, no way to press 停止.
    tauri::async_runtime::spawn_blocking(move || {
        // 重新把 app_config 刷进 inuse 再启动。app_config 才是选中音色的权威，
        // 而 worker 冷启动只认 inuse 那个文件。「其他」页强制结束引擎之后，
        // 新起的 worker 就是从这个文件里读模型 —— 它但凡漂了一点，用户看到的
        // 就是「引擎错误：请选择pth文件」，而唯一的解法是回去重新点一次音色，
        // 也就是手动干这里该干的事。
        worker::start_vc(&root)?;
        let st = worker::wait_vc_running(&root, 180_000);
        if st.get("state").and_then(|v| v.as_str()) == Some("running") {
            let cfg = crate::config::read(&root);
            let _ = worker::push_running_hot(&root, &cfg);
        }
        Ok(st)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn engine_stop_vc(
    state: State<'_, Mutex<AppState>>,
    force: Option<bool>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let f = force.unwrap_or(false);
    tauri::async_runtime::spawn_blocking(move || {
        worker::stop_vc(&root, f)?;
        Ok(worker::status_for_ui(&root))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn separate_status(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    Ok(separate::status(&root_clone(&state)?))
}

/// 选音频文件 / 选输出目录。原生对话框要主线程，所以留在同步命令里 ——
/// 它本来就只阻塞到用户点完为止。
#[tauri::command]
fn separate_pick(dir: bool, input_folder: Option<bool>) -> Option<String> {
    let d = rfd::FileDialog::new();
    if dir || input_folder.unwrap_or(false) {
        d.set_title(&crate::i18n::t("s.cb12ce77e7")).pick_folder()
    } else {
        d.add_filter(&crate::i18n::t("s.461189f186"), &["wav", "mp3", "flac", "m4a", "ogg", "wma", "aac"])
            .set_title(&crate::i18n::t("s.7ba52d2bf3"))
            .pick_file()
    }
    .map(|p| p.to_string_lossy().into_owned())
}

#[tauri::command]
async fn separate_start(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    input: String,
    output: String,
    model: String,
    format: Option<String>,
    aggression: Option<u32>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let format = format.unwrap_or_else(|| "wav".into());
    let aggression = aggression.unwrap_or(10).min(20);
    // 一次分离是几十秒到几分钟，绝不能占着 IPC 线程 —— 那就是窗口全程卡死。
    tauri::async_runtime::spawn_blocking(move || {
        separate::run(&app, &root, &input, &output, &model, &format, aggression)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn separate_cancel() {
    separate::cancel();
}

#[tauri::command]
fn separate_reveal(path: String) -> Result<(), String> {
    let p = std::path::PathBuf::from(path.trim());
    if p.is_file() {
        return crate::shell_extras::reveal(&p);
    }
    if p.is_dir() {
        return crate::shell_extras::reveal(&p.join("x"));
    }
    Ok(())
}

// --- 离线语音转换 STS（音频 → 目标音色）------------------------------------

/// 工具窗口点「下载模型」：把主窗口叫到前面并跳到广场的下载区。
#[tauri::command]
fn tools_open_downloads(
    app: AppHandle,
    reason: Option<String>,
    filter: Option<String>,
) -> Result<(), String> {
    tool_window::focus_main_downloads(
        &app,
        reason.as_deref().unwrap_or(""),
        filter.as_deref().unwrap_or(""),
    )
}

/// 工具窗口点「查看说明」：主窗口跳到说明页对应段。
#[tauri::command]
fn tools_open_help(app: AppHandle, section: Option<String>) -> Result<(), String> {
    tool_window::focus_main_help(&app, section.as_deref().unwrap_or("train"))
}

/// DSP 变声预设：内置 + 用户自存，同 id 用户覆盖内置。
#[tauri::command]
fn dsp_activate(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    id: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let id = id.trim().to_string();
    let out = dsp::activate(&root, &id)?;
    let _ = app.emit(
        "config-changed",
        json!({
            "config": out.get("config"),
            "hot": {
                "dsp_enabled": true,
                "dsp_preset": id,
                "function": "fx"
            }
        }),
    );
    Ok(out)
}

#[tauri::command]
fn dsp_deactivate(app: AppHandle, state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let out = dsp::deactivate(&root)?;
    let _ = app.emit("config-changed", json!({ "config": out.get("config"), "hot": { "dsp_enabled": false, "dsp_preset": "", "function": "vc" } }));
    Ok(out)
}

#[tauri::command]
async fn dsp_presets(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || Ok(dsp::list(&root)))
        .await
        .map_err(|e| e.to_string())?
}

/// DSP 效果器规格。前端画滑条要用，范围只有引擎侧一份定义。
#[tauri::command]
async fn dsp_effects(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || Ok(dsp::effect_specs(&root)))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn dsp_preset_save(
    state: State<'_, Mutex<AppState>>,
    id: String,
    name: String,
    params: Value,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || dsp::save(&root, &id, &name, &params))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn dsp_preset_delete(
    state: State<'_, Mutex<AppState>>,
    id: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || dsp::delete(&root, &id))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn sts_status(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || Ok(sts::status(&root)))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn sts_pick_input(state: State<'_, Mutex<AppState>>, folder: bool) -> Option<String> {
    let p = sts::pick_input(folder)?;
    if let Ok(root) = root_clone(&state) {
        sts::remember_input(&root, &p);
    }
    Some(p)
}

#[tauri::command]
fn sts_pick_output(state: State<'_, Mutex<AppState>>) -> Option<String> {
    let p = sts::pick_output()?;
    if let Ok(root) = root_clone(&state) {
        sts::remember_output(&root, &p);
    }
    Some(p)
}

#[tauri::command]
async fn sts_list_input(
    state: State<'_, Mutex<AppState>>,
    input: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || Ok(sts::list_input(&root, &input)))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn sts_delete_input(
    state: State<'_, Mutex<AppState>>,
    input: String,
    path: String,
) -> Result<(), String> {
    sts::delete_input_file(&root_clone(&state)?, &input, &path)
}

#[tauri::command]
fn sts_reveal_input(path: String) -> Result<(), String> {
    sts::reveal_path(&path)
}

#[tauri::command]
fn sts_default_input(state: State<'_, Mutex<AppState>>) -> Result<String, String> {
    let root = root_clone(&state)?;
    let dir = sts::default_input_dir(&root);
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    sts::remember_input(&root, &dir.to_string_lossy());
    Ok(dir.to_string_lossy().into_owned())
}

#[tauri::command]
async fn sts_record_start(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    input: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || sts::record(&app, &root, &input))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn sts_record_stop() {
    sts::cancel_record();
}

/// 设置页「测试麦克风」：只开设备读电平，不起引擎、不写文件。
#[tauri::command]
async fn mic_test_start(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || mic::test(&app, &root))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn mic_test_stop() {
    mic::stop();
}

#[tauri::command]
async fn sts_start(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    input: String,
    output: String,
    pitch: i32,
    f0method: String,
    index_rate: f64,
    // Optional override: offline conversion target voice (.pth). Empty = homepage current.
    model_path: Option<String>,
    // Optional .index for that voice. Empty = library binding / config.
    index_path: Option<String>,
    filter_radius: Option<u32>,
    resample_sr: Option<u32>,
    rms_mix_rate: Option<f64>,
    protect: Option<f64>,
    format: Option<String>,
    sid: Option<u32>,
    f0_file: Option<String>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let model_path = model_path.unwrap_or_default();
    let index_path = index_path.unwrap_or_default();
    let opts = sts::ConvertOpts::from_raw(
        filter_radius,
        resample_sr,
        rms_mix_rate,
        protect,
        format,
        sid,
        f0_file,
    );
    tauri::async_runtime::spawn_blocking(move || {
        sts::run(
            &app,
            &root,
            &input,
            &output,
            pitch,
            &f0method,
            index_rate,
            &model_path,
            &index_path,
            opts,
        )
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn sts_cancel() {
    sts::cancel();
}

#[tauri::command]
fn sts_reveal(
    state: State<'_, Mutex<AppState>>,
    path: Option<String>,
) -> Result<(), String> {
    let root = root_clone(&state)?;
    sts::reveal_output(&root, path.as_deref().unwrap_or(""))
}

// --- 文字合成 TTS（文字 → SAPI → 可选 RVC）--------------------------------

#[tauri::command]
async fn tts_status(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // 列系统嗓子要起一次 PowerShell，几百毫秒。放在 IPC 线程上就是开窗那一下
    // 界面先白半秒。
    tauri::async_runtime::spawn_blocking(move || Ok(tts::status(&root)))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn tts_speak(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    text: String,
    voice: String,
    rate: i32,
    pitch: i32,
    use_rvc: bool,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        tts::run(&app, &root, &text, &voice, rate, pitch, use_rvc)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn tts_cancel() {
    tts::cancel();
}

/// 在文件管理器里打开合成结果所在的目录。
#[tauri::command]
fn tts_reveal(state: State<'_, Mutex<AppState>>) -> Result<(), String> {
    let dir = tts::out_dir(&root_clone(&state)?);
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    shell_extras::reveal(&dir.join("x"))
}

// --- 附加资源（分离模型 / 训练底模）-----------------------------------------

#[tauri::command]
async fn extra_list(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // 要拉线上清单，可能等十几秒。同步命令会把 IPC 线程堵死。
    tauri::async_runtime::spawn_blocking(move || extra_assets::list(&root))
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn extra_download(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    key: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || extra_assets::download(&app, &root, &key))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn extra_cancel() {
    extra_assets::cancel();
}

// --- 训练 -------------------------------------------------------------------

#[tauri::command]
fn train_status(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    Ok(train::status(&root_clone(&state)?))
}

/// 选数据集目录。原生对话框要主线程。
#[tauri::command]
fn train_pick_dataset() -> Option<String> {
    rfd::FileDialog::new()
        .set_title(&crate::i18n::t("s.612dddefc4"))
        .pick_folder()
        .map(|p| p.to_string_lossy().into_owned())
}

#[tauri::command]
async fn train_start(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    req: train::TrainReq,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // 训练动辄几小时。放 IPC 线程上等于窗口从此不动。
    tauri::async_runtime::spawn_blocking(move || train::run(&app, &root, req))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn train_cancel() {
    train::cancel();
}

#[tauri::command]
fn ckpt_pick(kind: Option<String>) -> Option<String> {
    ckpt::pick(kind.as_deref().unwrap_or("pth"))
}

#[tauri::command]
async fn ckpt_run(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    req: Value,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || ckpt::run(&app, &root, req))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn ckpt_cancel() {
    ckpt::cancel();
}

#[tauri::command]
async fn engine_force_kill(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        worker::kill_known_workers(&root);
        worker::kill_runtime_pythons(&root, true);
        // 杀完把「当前音色」重新写回引擎配置。
        //
        // 强杀是在引擎已经不正常的时候按的，它中途可能正在写 configs/inuse，
        // 也可能写了一半就没了。下一次「开启变声」读的就是那份配置，读到
        // 半截的 pth_path 就会用错模型或者干脆起不来 —— 用户的解法是「切到
        // 另一个音色再切回来」，因为那一下会把模型路径整个重写一遍。
        //
        // 那一下现在由强杀自己做。它本来就该是「恢复到已知good状态」的按钮，
        // 而不是只负责杀进程。
        if let Err(e) = voices::resync_selected_model(&root) {
            worker::append_log(&root, &crate::i18n::te("s.298dd55e6d", &(e)));
        }
        Ok(worker::status_for_ui(&root))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn engine_set_hot(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    pitch: Option<i32>,
    formant: Option<f64>,
    function: Option<String>,
    threhold: Option<f64>,
    index_rate: Option<f64>,
    rms_mix_rate: Option<f64>,
    dsp_enabled: Option<bool>,
    dsp_preset: Option<String>,
    dsp_params: Option<Value>,
) -> Result<u64, String> {
    let root = root_clone(&state)?;
    let mut payload = Map::new();
    if let Some(v) = pitch {
        payload.insert("pitch".into(), json!(v));
    }
    if let Some(v) = formant {
        payload.insert("formant".into(), json!(v));
    }
    if let Some(v) = function {
        // "fx" = 无模型 DSP 变声，整条 RVC 不走。以前这里只认 im/vc，
        // 别的一律折成 vc —— fx 传进来会被悄悄改成 vc，等于没生效。
        let f = match v.as_str() {
            "bypass" | "im" => "im",
            "fx" => "fx",
            _ => "vc",
        };
        payload.insert("function".into(), json!(f));
    }
    if let Some(v) = threhold {
        payload.insert("threhold".into(), json!(v));
    }
    if let Some(v) = index_rate {
        payload.insert("index_rate".into(), json!(v));
    }
    if let Some(v) = rms_mix_rate {
        payload.insert("rms_mix_rate".into(), json!(v));
    }
    // 无模型 DSP 变声。这三个键在 config::HOT_KEYS 里，但**命令签名里没有的
    // 参数 Tauri 是直接丢掉的** —— 加进 HOT_KEYS 只让它们能落盘，推不推得到
    // worker 是另一回事。少了这一段，模型页点预设是一点反应都没有的。
    if let Some(v) = dsp_enabled {
        payload.insert("dsp_enabled".into(), json!(v));
        if v {
            // 开 DSP 必须和清音色写在同一次落盘、同一条 worker 命令里。
            // 先 setHot 再 clearVoice：mailbox 是单槽，drop 会盖掉 dsp 那条
            // set，引擎内存里 dsp_enabled 仍是 false，start 就会拿空路径去建 RVC。
            payload.insert("function".into(), json!("fx"));
            payload.insert("drop_model".into(), json!(true));
            payload.insert("pth_path".into(), json!(""));
            payload.insert("index_path".into(), json!(""));
            // last_model 留下：关掉 DSP / 下次选音色还认得用户上次用的那个。
        } else {
            payload.insert("function".into(), json!("vc"));
            payload.insert("dsp_preset".into(), json!(""));
            payload.insert("dsp_params".into(), json!({}));
        }
    }
    if let Some(v) = dsp_preset {
        payload.insert("dsp_preset".into(), json!(v));
    }
    if let Some(v) = dsp_params {
        if v.is_object() {
            payload.insert("dsp_params".into(), v);
        }
    }
    if payload.is_empty() {
        return Err(crate::i18n::t("s.40018c2fe1").into());
    }
    // 底栏拖音高/共鸣以前只 set_hot、不写盘：界面重启后仍显示旧数（来自
    // app_config），但 inuse 还是 0，引擎按默认起 —— 显示对、声音不对。
    // 这里顺手落盘并同步 inuse；worker 没起来时只落盘，不算失败。
    if let Ok(out) = config::update(&root, payload.clone()) {
        if let Err(e) = voices::persist_profile_patch(&root, &payload) {
            logging::shell_log!("persist profile: {e}");
        }
        let _ = app.emit("config-changed", &out);
    }
    match worker::set_hot(&root, payload) {
        Ok(seq) => Ok(seq),
        Err(e) if e.contains(&crate::i18n::t("s.b2ba9634d9")) => Ok(0),
        Err(e) => Err(e),
    }
}

/// 变声中换音色。不重开流，只把新模型推给引擎。
#[tauri::command]
fn engine_swap_model(state: State<'_, Mutex<AppState>>) -> Result<u64, String> {
    let root = root_clone(&state)?;
    worker::swap_model(&root)
}

#[tauri::command]
async fn engine_list_devices(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // Starts the worker if needed (up to 90s) and then polls for up to 20s.
    tauri::async_runtime::spawn_blocking(move || list_devices_blocking(root))
        .await
        .map_err(|e| e.to_string())?
}

fn list_devices_blocking(root: std::path::PathBuf) -> Result<Value, String> {
    let root = &root;
    if !paths::runtime_ready(&root) {
        return Ok(json!({
            "state": "error",
            "error": crate::i18n::t("s.9f39847f54"),
            "input_devices": [],
            "output_devices": [],
            "hostapis": []
        }));
    }
    if !worker::is_worker_alive(&root) {
        worker::start_worker(&root)?;
        let st = worker::wait_worker_ready(&root, 90_000);
        if st.get("state").and_then(|v| v.as_str()) == Some("error") {
            return Ok(st);
        }
    }
    let _ = worker::send_command(&root, "list_devices", Map::new());
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(20);
    while std::time::Instant::now() < deadline {
        let st = worker::status_for_ui(&root);
        let has = st
            .get("input_devices")
            .and_then(|v| v.as_array())
            .map(|a| !a.is_empty())
            .unwrap_or(false);
        if has {
            return Ok(st);
        }
        std::thread::sleep(std::time::Duration::from_millis(200));
    }
    Ok(worker::status_for_ui(&root))
}

#[tauri::command]
async fn provision_status(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // Async + spawn_blocking because this resolves a runtime spec, which can
    // reach CNB. A sync command runs on the IPC thread, so an unreachable or
    // slow host froze the window on startup for as long as the request took.
    tauri::async_runtime::spawn_blocking(move || {
        let t = std::time::Instant::now();
        let v = provision::provision_status(&root);
        // This is the first thing a fresh install calls and the gate cannot
        // draw without it, so a slow answer looks exactly like a hang. Say so.
        let ms = t.elapsed().as_millis();
        if ms > 1500 {
            logging::shell_log!(crate::i18n::t("s.7fdbc694cb"));
        }
        Ok(v)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn provision_start(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    variant: String,
    force: Option<bool>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let f = force.unwrap_or(false);
    // This downloads and extracts several GB. Run inline it occupied the IPC
    // path for the whole transfer, which meant the 取消 button's own invoke
    // could not be delivered — the user could watch the progress bar but not
    // stop it.
    tauri::async_runtime::spawn_blocking(move || {
        provision::run_provision(app, root, variant, f)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn provision_cancel() -> Result<(), String> {
    provision::cancel_provision();
    Ok(())
}

// ----- Stage 4: voices + store ------------------------------------------------

#[tauri::command]
async fn voices_list(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // Walks the whole voice library; a large one is a visible stall on the IPC
    // thread.
    tauri::async_runtime::spawn_blocking(move || Ok(voices::list_voices(&root)))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn voices_select(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    path: Option<String>,
    dir: Option<String>,
    name: Option<String>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let out = voices::select_voice(
        &root,
        path.as_deref().unwrap_or(""),
        dir.as_deref().unwrap_or(""),
        name.as_deref().unwrap_or(""),
    )?;
    // 工具窗是独立 webview，不广播的话语音转换的目标音色会停在打开时的那个。
    let _ = app.emit("voices-changed", &out);
    // 音色档案里的音高/共鸣已经写进 app_config，设置页和底栏要一起跟上。
    let cfg = config::read(&root);
    let _ = app.emit("config-changed", json!({ "config": cfg }));
    Ok(out)
}

#[tauri::command]
fn voices_clear(app: AppHandle, state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let out = voices::clear_voice(&root)?;
    let _ = app.emit("voices-changed", &out);
    let cfg = config::read(&root);
    let _ = app.emit("config-changed", json!({ "config": cfg }));
    Ok(out)
}

#[tauri::command]
async fn voices_current(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || {
        Ok(voices::current_selection_summary(&root))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
fn voices_index_list(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::list_index_bindings(&root, &model_dir)
}

#[tauri::command]
fn voices_index_use(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
    index_path: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::set_active_index(&root, &model_dir, &index_path)
}

#[tauri::command]
fn voices_index_bind(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
    index_src: Option<String>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let src = match index_src.filter(|s| !s.is_empty()) {
        Some(s) => s,
        None => voices::pick_index_file().ok_or_else(|| crate::i18n::t("s.a5ffdc95ee"))?,
    };
    voices::bind_index_file(&root, &model_dir, &src)
}

#[tauri::command]
fn voices_index_unbind(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
    index_path: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::unbind_index(&root, &model_dir, &index_path)
}

#[tauri::command]
fn voices_profiles_list(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::list_profiles(&root, &model_dir)
}

#[tauri::command]
fn voices_profile_use(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
    profile_id: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::set_active_profile(&root, &model_dir, &profile_id)
}

#[tauri::command]
fn voices_profile_save(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
    name: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::save_current_as_profile(&root, &model_dir, &name)
}

#[tauri::command]
fn voices_profile_delete(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
    profile_id: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::delete_profile(&root, &model_dir, &profile_id)
}

#[tauri::command]
fn voices_profile_import(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::import_profile(&root, &model_dir)
}

#[tauri::command]
fn voices_profile_export(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::export_active_profile(&root, &model_dir)
}

#[tauri::command]
async fn voices_import(
    state: State<'_, Mutex<AppState>>,
    paths: Option<Vec<String>>,
    current_model_dir: Option<String>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // The picker stays here (native dialogs want the main thread); only the
    // copying, which can be gigabytes, moves off.
    let files = match paths.filter(|p| !p.is_empty()) {
        Some(p) => p,
        None => {
            let picked = voices::pick_import_files();
            if picked.is_empty() {
                return Err(crate::i18n::t("s.a5ffdc95ee").into());
            }
            picked
        }
    };
    tauri::async_runtime::spawn_blocking(move || {
        voices::import_files(&root, &files, current_model_dir.as_deref())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn voices_delete(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    tauri::async_runtime::spawn_blocking(move || voices::delete_voice(&root, &model_dir))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn voices_rename(
    state: State<'_, Mutex<AppState>>,
    model_dir: String,
    new_name: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    voices::rename_voice(&root, &model_dir, &new_name)
}

#[tauri::command]
async fn voices_promote(
    state: State<'_, Mutex<AppState>>,
    pth_path: String,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // Copies a multi-hundred-MB .pth.
    tauri::async_runtime::spawn_blocking(move || voices::promote_legacy(&root, &pth_path))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn voices_open_dir(state: State<'_, Mutex<AppState>>) -> Result<(), String> {
    let root = root_clone(&state)?;
    voices::open_models_dir(&root)
}

#[tauri::command]
async fn store_catalog(
    state: State<'_, Mutex<AppState>>,
    prefer_remote: Option<bool>,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    let remote = prefer_remote.unwrap_or(true);
    // Network fetch — never on the IPC thread.
    tauri::async_runtime::spawn_blocking(move || {
        Ok(store::fetch_store_catalog(&root, remote))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn store_install(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    entry: Value,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // Downloads and unpacks a voice pack. Same reason as provision_start: the
    // per-voice 取消 is its own invoke and has to be able to get through.
    tauri::async_runtime::spawn_blocking(move || store::install_voice_entry(app, root, entry))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn store_cancel(voice_id: Option<String>) -> Result<(), String> {
    // Empty / omitted id cancels everything in flight.
    store::cancel_store_download(voice_id.as_deref().unwrap_or(""));
    Ok(())
}

/// 已下载但还没装的第三方音色。商店据此把按钮换成「查看 / 安装」。
#[tauri::command]
fn store_staged(state: State<'_, Mutex<AppState>>) -> Result<Value, String> {
    Ok(store::staged_status(&root_clone(&state)?))
}

/// 在资源管理器里打开暂存目录，用户自己看文件、自己删。
#[tauri::command]
fn store_reveal_staged(
    state: State<'_, Mutex<AppState>>,
    voice_id: String,
) -> Result<(), String> {
    store::reveal_staged(&root_clone(&state)?, &voice_id)
}

#[tauri::command]
fn store_discard_staged(
    state: State<'_, Mutex<AppState>>,
    voice_id: String,
) -> Result<(), String> {
    store::discard_staged(&root_clone(&state)?, &voice_id)
}

#[tauri::command]
async fn store_install_staged(
    app: AppHandle,
    state: State<'_, Mutex<AppState>>,
    entry: Value,
) -> Result<Value, String> {
    let root = root_clone(&state)?;
    // 解压几百 MB 的包，同样不能占 IPC 线程。
    tauri::async_runtime::spawn_blocking(move || store::install_staged(app, root, entry))
        .await
        .map_err(|e| e.to_string())?
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let root = paths::product_root();
    // Before anything else: a release build has no console, so without this the
    // rest of these lines would go nowhere.
    logging::init(&root);
    i18n::init_from_config(&root);
    // pid 在横幅里，是因为 shell.log 是跨启动追加的：报告「进程还在但看不见
    // 窗口」时，得先能确认手上这段日志和任务管理器里那个进程是同一次运行。
    logging::shell_log!("=== RVC Fabric {} 启动（pid {}）===",
        update::APP_VERSION,
        std::process::id()
    );
    logging::shell_log!("product root: {}", root.display());
    logging::shell_log!("runtime_ready={}", paths::runtime_ready(&root));
    logging::shell_log!(
        "exe: {}",
        std::env::current_exe()
            .map(|p| p.display().to_string())
            .unwrap_or_else(|e| format!("<unknown: {e}>"))
    );
    logging::shell_log!("UI source: {}", ui_assets::source_label());

    // 尽早清 TEMP：放在 setup 之前，避免建窗/预热 worker 占着文件删不掉。
    // 官方 WebUI 也是一启动就 rmtree(TEMP)。
    {
        let stats = paths::clean_temps(&root);
        paths::log_clean_stats(&crate::i18n::t("s.ebd26da421"), &root, &stats);
    }

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_updater::Builder::new().build())
        // OTA strategy A: serve the UI through fabric:// so the frontend/ dir
        // next to the exe can replace the shipped UI without a new exe.
        .register_uri_scheme_protocol(ui_assets::SCHEME, |ctx, req| {
            ui_assets::serve(ctx.app_handle(), req)
        })
        .manage(Mutex::new(AppState { root: root.clone() }))
        .invoke_handler(tauri::generate_handler![
            tools_open,
            tools_open_help,
            ui_source,
            shell_version,
            ui_ready,
            ui_log,
            log_path,
            legacy_open_panel,
            legacy_open_webui,
            plaza_fetch,
            plaza_dismiss,
            plaza_mark_seen,
            open_external,
            config_get,
            config_describe,
            config_set,
            autostart_get,
            autostart_set,
            cover_resolve_many,
            i18n_set_locale,
            i18n_get_locale,
            pick_wallpaper,
            update_check,
            update_apply,
            update_app,
            hotkeys_apply,
            diagnostics_build,
            cache_status,
            cache_clear,
            consult_build,
            reveal_user_dir,
            telemetry_tick,
            close_finish,
            assets_status,
            assets_ensure_engine_core,
            assets_ensure_vbcable,
            assets_install_vbcable,
            assets_uninstall_vbcable,
            product_root,
            engine_status,
            engine_ensure,
            engine_start_worker,
            engine_start_vc,
            engine_stop_vc,
            engine_force_kill,
            engine_set_hot,
            dsp_activate,
            dsp_deactivate,
            engine_swap_model,
            engine_list_devices,
            provision_status,
            provision_start,
            provision_cancel,
            voices_list,
            voices_select,
            voices_clear,
            voices_current,
            voices_index_list,
            voices_index_use,
            voices_index_bind,
            voices_index_unbind,
            voices_profiles_list,
            voices_profile_use,
            voices_profile_save,
            voices_profile_delete,
            voices_profile_import,
            voices_profile_export,
            voices_import,
            voices_delete,
            voices_rename,
            voices_promote,
            voices_open_dir,
            store_catalog,
            store_install,
            store_cancel,
            store_staged,
            store_reveal_staged,
            store_discard_staged,
            store_install_staged,
            separate_status,
            separate_pick,
            separate_start,
            separate_cancel,
            separate_reveal,
            tools_open_downloads,
            dsp_presets,
            dsp_effects,
            dsp_preset_save,
            dsp_preset_delete,
            sts_status,
            sts_pick_input,
            sts_pick_output,
            sts_list_input,
            sts_delete_input,
            sts_reveal_input,
            sts_default_input,
            sts_record_start,
            sts_record_stop,
            mic_test_start,
            mic_test_stop,
            sts_start,
            sts_cancel,
            sts_reveal,
            tts_status,
            tts_speak,
            tts_cancel,
            tts_reveal,
            extra_list,
            extra_download,
            extra_cancel,
            train_status,
            train_pick_dataset,
            train_start,
            train_cancel,
            ckpt_pick,
            ckpt_run,
            ckpt_cancel,
        ])
        .setup(move |app| {
            // Window URL must use the custom scheme registered above.
            // WebView2 cannot register non-standard schemes at all, so wry
            // rewrites `fabric://localhost/x` to `http://fabric.localhost/x`
            // and intercepts that; Windows is spelled out here to match what
            // the webview will actually report as its origin.
            #[cfg(windows)]
            let url = format!("http://{}.localhost/index.html", ui_assets::SCHEME);
            #[cfg(not(windows))]
            let url = format!("{}://localhost/index.html", ui_assets::SCHEME);
            logging::shell_log!("window url: {url}");
            let main_window = tauri::WebviewWindowBuilder::new(
                app,
                "main",
                tauri::WebviewUrl::CustomProtocol(url.parse().expect("fabric url")),
            )
            .title("RVC Fabric")
            .inner_size(1180.0, 780.0)
            .min_inner_size(880.0, 640.0)
            .resizable(true)
            .decorations(false)
            // 无边框 + shadow=true 在 Windows 上会强制 1px 系统白边（Aero 描边）。
            // 最大化时更明显。投影宁可不要，边必须干净。
            .shadow(false)
            .center()
            .build()?;
            // `.center()` 只认主显示器。多显示器的人主屏未必是他正在看的那
            // 块，窗口连同任务栏按钮一起去了另一块屏，这头看起来就跟没启动
            // 一样。摆到光标所在的屏上。
            window_watch::place_on_active_monitor(&main_window);
            // 无边框窗口默认是直角的，Win11 上跟系统其他窗口格格不入。
            window_watch::round_corners(&main_window);
            window_watch::report_and_rescue(&main_window, &crate::i18n::t("s.ad667e5e16"));

            // A blank window is the one failure the user cannot describe and we
            // cannot see. If the UI never reports back, say so in the log with
            // everything needed to tell "assets missing" from "script threw".
            //
            // The window state goes in unconditionally, not just on failure:
            // "界面已挂载" plus "看不见窗口" is a real combination — the HWND
            // exists and WebView2 is painting into it, it is just somewhere the
            // user cannot see. Guessing between "no window" and "window off
            // screen" from the outside is impossible, so let the window say.
            {
                let h = app.handle().clone();
                std::thread::spawn(move || {
                    std::thread::sleep(std::time::Duration::from_secs(12));
                    if !ui_assets::ui_reported_ready() {
                        logging::shell_log!("警告：12 秒内界面没有挂载（白屏）。UI 来源 {} · 已处理 {} 个资源请求 · 404 {} 次",
                            ui_assets::source_label(),
                            ui_assets::served_count(),
                            ui_assets::not_found_count(),
                        );
                        let _ = h.emit("app://ui-stalled", ());
                    }
                    if let Some(w) = h.get_webview_window("main") {
                        window_watch::report_and_rescue(&w, &crate::i18n::t("s.6c0434f6f2"));
                    }
                });
            }

            // "打开就未响应" is the one report that carries no information: the
            // window is frozen, so the UI cannot say anything and neither can
            // any command it would have called. Ping the event loop from a
            // plain thread instead. If these lines are absent from a log that
            // ends mid-session, the loop stopped pumping and the cause is on
            // the Rust side; if they keep appearing, the shell is alive and the
            // webview is what wedged. Either way the next report starts from a
            // fact instead of a guess.
            {
                let h = app.handle().clone();
                std::thread::spawn(move || {
                    let mut stalled = false;
                    loop {
                        std::thread::sleep(std::time::Duration::from_secs(15));
                        let (tx, rx) = std::sync::mpsc::channel();
                        if h.run_on_main_thread(move || {
                            let _ = tx.send(());
                        })
                        .is_err()
                        {
                            return; // app is shutting down
                        }
                        let ok = rx
                            .recv_timeout(std::time::Duration::from_secs(10))
                            .is_ok();
                        if !ok && !stalled {
                            logging::shell_log!(crate::i18n::t("s.03b08ed8b0"));
                            stalled = true;
                        } else if ok && stalled {
                            logging::shell_log!(crate::i18n::t("s.4df93f64ef"));
                            stalled = false;
                        }
                    }
                });
            }

            // Regenerate configs/inuse/config.json from app_config on every
            // start. Setup ships a clean template that overwrites the installed
            // one, so without this an upgrade looks like "my devices were
            // reset" — the real settings are in User_Data and just never got
            // written back down to the engine.
            {
                config::persist_perf_caps(&root);
                let cfg = config::read(&root);
                if let Err(e) = config::sync_inuse(&root, &cfg) {
                    logging::shell_log!("inuse sync failed: {e}");
                }
            }

            // setup 末尾再清一次：中间步骤若又写下临时文件，这里兜底。
            {
                let stats = paths::clean_temps(&root);
                paths::log_clean_stats("setup", &root, &stats);
            }

            shell_extras::install_close_handler(app.handle());
            // Tray always exists: closing to tray is what keeps conversion
            // running while the window is away.
            if let Err(e) = shell_extras::install_tray(app.handle()) {
                logging::shell_log!("tray unavailable: {e}");
            }
            // Restore the saved hotkey preference.
            let want_hotkeys = config::read(&root)
                .get("hotkeys_enabled")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let _ = shell_extras::apply_hotkeys(app.handle(), want_hotkeys);

            let root_bg = root.clone();
            std::thread::spawn(move || {
                if paths::runtime_ready(&root_bg) {
                    // 预热之前先收孤儿：上次留下的多余 worker 还占着输出设备，
                    // 不收掉的话这次认领的那个发不出声。
                    worker::reap_orphan_workers(&root_bg);
                    let _ = worker::ensure_worker_and_devices(&root_bg, 90_000);
                } else {
                    logging::shell_log!("skip worker prewarm: Runtime not ready");
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while running RVC Fabric")
        .run(|app, event| {
            // 退出时再清一遍，把本会话分离/下载留下的中间文件收掉。
            if let tauri::RunEvent::Exit = event {
                if let Ok(g) = app.state::<Mutex<AppState>>().lock() {
                    worker::kill_known_workers(&g.root);
                    worker::kill_runtime_pythons(&g.root, false);
                    let stats = paths::clean_temps(&g.root);
                    paths::log_clean_stats(&crate::i18n::t("s.feecb1e6ad"), &g.root, &stats);
                }
            }
        });
}
