//! App settings — `User_Data/app_config.json`, mirrored into
//! `configs/inuse/config.json` for the worker.
//!
//! Ports `launcher/config_store.py` + `launcher/inuse_config.py`. Two rules from
//! the Python shell carry over and must not be dropped:
//!
//! * **`configs/inuse/config.json` must never contain dev-machine absolute
//!   paths.** Shipped builds once leaked `L:\…` and the worker died on user
//!   machines. Anything that looks like an absolute path on another drive is
//!   stripped on write.
//! * **HOT vs COLD.** Hot keys apply to a running stream; cold keys need a
//!   stop + start. The UI has to say which it is instead of silently doing
//!   nothing.

use std::collections::BTreeMap;
use std::path::Path;

use serde_json::{json, Map, Value};

use crate::paths;

/// Applies live while converting (mirrors `realtime_protocol.HOT_KEYS`).
pub const HOT_KEYS: &[&str] = &[
    "pitch",
    "formant",
    "index_rate",
    "rms_mix_rate",
    "threhold",
    "in_gain_db",
    "f0method",
    "I_noise_reduce",
    "O_noise_reduce",
    "use_pv",
    "function",
    // 变声后的 DSP 链：噪声门 → 压缩器 → 五段 EQ → 输出增益。
    //
    // 引擎侧（tools/dsp_fx.py + gui_v1 的 _worker_apply_hot）一直支持这些键，
    // 只是迁到 Tauri 之后壳层没把它们列进来，于是整条链在新界面上消失了 ——
    // 老的 Python 壳有 EQ，新壳没有。全是热键，转着的时候能调。
    "fx_enabled",
    "fx_gate_enabled",
    "fx_gate_threshold_db",
    "fx_gate_release_ms",
    "fx_gate_hold_ms",
    "fx_gate_range_db",
    "fx_comp_enabled",
    "fx_comp_threshold_db",
    "fx_comp_ratio",
    "fx_comp_attack_ms",
    "fx_comp_release_ms",
    "fx_comp_makeup_db",
    "fx_eq_enabled",
    "fx_eq_gains",
    "fx_eq_preset",
    "fx_out_gain_db",
];

/// Needs stop + start (mirrors `realtime_protocol.COLD_KEYS`).
pub const COLD_KEYS: &[&str] = &[
    "pth_path",
    "index_path",
    "sg_hostapi",
    "sg_wasapi_exclusive",
    "sg_input_device",
    "sg_output_device",
    "sr_type",
    "block_time",
    "crossfade_length",
    "extra_time",
    "n_cpu",
    // 「变声时监听自己」 and its device. These were in neither list, so
    // `update()` never set `touched_engine` and `sync_inuse` was never called
    // for them — the toggle wrote app_config and stopped there. The worker
    // reads `monitor_enabled` / `monitor_device` out of inuse, so monitoring
    // could not be switched on at all. Cold because the shell's hot channel
    // (`engine_set_hot`) has a fixed parameter list with no monitor in it.
    "monitor_self",
    "monitor_device",
    // CUDA Graph 推理加速。冷键：要在模型加载前就定下来，转着的时候切不了。
    "cuda_graph",
];

/// Keys the worker consumes — only these are mirrored into `inuse`.
fn engine_keys() -> Vec<&'static str> {
    let mut v: Vec<&'static str> = HOT_KEYS.to_vec();
    v.extend_from_slice(COLD_KEYS);
    v
}

pub fn is_hot(key: &str) -> bool {
    HOT_KEYS.contains(&key)
}

pub fn is_cold(key: &str) -> bool {
    COLD_KEYS.contains(&key)
}

/// Product defaults. Values match the Python shell so a user switching over
/// does not silently get different audio.
pub fn defaults() -> Map<String, Value> {
    let mut m = Map::new();
    // voice params (hot)
    m.insert("pitch".into(), json!(0));
    m.insert("formant".into(), json!(0.0));
    m.insert("index_rate".into(), json!(0.75));
    m.insert("rms_mix_rate".into(), json!(0.25));
    m.insert("threhold".into(), json!(-60));
    m.insert("in_gain_db".into(), json!(0.0));
    m.insert("f0method".into(), json!("rmvpe"));
    m.insert("I_noise_reduce".into(), json!(true));
    m.insert("O_noise_reduce".into(), json!(false));
    m.insert("use_pv".into(), json!(false));
    m.insert("function".into(), json!("vc"));
    // DSP 链（热）。默认整条关掉 —— 开着就改变了所有人听到的声音，
    // 那不该是升级一次软件就默默发生的事。数值与 dsp_fx.DEFAULT_FX_CONFIG 对齐。
    m.insert("fx_enabled".into(), json!(false));
    m.insert("fx_gate_enabled".into(), json!(true));
    m.insert("fx_gate_threshold_db".into(), json!(-50.0));
    m.insert("fx_gate_release_ms".into(), json!(50.0));
    m.insert("fx_gate_hold_ms".into(), json!(20.0));
    m.insert("fx_gate_range_db".into(), json!(20.0));
    m.insert("fx_comp_enabled".into(), json!(true));
    m.insert("fx_comp_threshold_db".into(), json!(-20.0));
    m.insert("fx_comp_ratio".into(), json!(4.0));
    m.insert("fx_comp_attack_ms".into(), json!(5.0));
    m.insert("fx_comp_release_ms".into(), json!(100.0));
    m.insert("fx_comp_makeup_db".into(), json!(0.0));
    m.insert("fx_eq_enabled".into(), json!(true));
    m.insert("fx_eq_gains".into(), json!([0.0, 0.0, 0.0, 0.0, 0.0]));
    m.insert("fx_eq_preset".into(), json!("flat"));
    m.insert("fx_out_gain_db".into(), json!(0.0));
    // model binding (cold) — written by voice selection, not by the settings
    // page, but the worker expects the keys to exist.
    m.insert("pth_path".into(), json!(""));
    m.insert("index_path".into(), json!(""));
    // devices / performance (cold)
    m.insert("sg_hostapi".into(), json!(""));
    m.insert("sg_wasapi_exclusive".into(), json!(false));
    m.insert("sg_input_device".into(), json!(""));
    m.insert("sg_output_device".into(), json!(""));
    m.insert("sr_type".into(), json!("sr_device"));
    m.insert("block_time".into(), json!(0.25));
    m.insert("crossfade_length".into(), json!(0.08));
    m.insert("extra_time".into(), json!(2.5));
    m.insert("n_cpu".into(), json!(4));
    // 默认关。这东西改的是推理核心，先让人自己开、量过再谈默认值。
    m.insert("cuda_graph".into(), json!(false));
    // shell-only
    m.insert("monitor_self".into(), json!(false));
    m.insert("monitor_device".into(), json!(""));
    // 主显卡序号。-1 = 自动（交给 torch 自己挑）。
    //
    // 不进 COLD_KEYS：worker 不读这个键，它是通过进程环境变量
    // CUDA_VISIBLE_DEVICES 生效的（见 worker::env_for_runtime）。写进 inuse
    // 只会多一个没人看的键。needs_restart 在 update() 里单独补。
    m.insert("main_gpu".into(), json!(-1));
    m.insert("close_action".into(), json!("ask"));
    m.insert("theme_mode".into(), json!("system"));
    // UI language (React + Rust tray/errors). Engine logs may stay Chinese.
    // ui_locale_picked 不进 defaults：老配置缺该键时不能被默认 false 盖成「未选过」，
    // 否则老用户升级后会再弹一次语言引导。新装在 read() 里文件不存在时再写 false。
    m.insert("ui_locale".into(), json!("zh-CN"));
    m.insert("wallpaper_path".into(), json!(""));
    m.insert("wallpaper_blur".into(), json!(40));
    m.insert("wallpaper_opacity".into(), json!(70));
    m.insert("hotkeys_enabled".into(), json!(false));
    // 快捷键组合。默认沿用旧 Python 壳的那四个，用户有肌肉记忆；
    // 键名要和 shell_extras::HOTKEYS 对上。
    m.insert("hotkey_toggle_vc".into(), json!("CmdOrCtrl+F2"));
    m.insert("hotkey_toggle_mode".into(), json!("CmdOrCtrl+F3"));
    m.insert("hotkey_prev_voice".into(), json!("CmdOrCtrl+F5"));
    m.insert("hotkey_next_voice".into(), json!("CmdOrCtrl+F6"));
    m.insert("hotkey_pitch_up".into(), json!("CmdOrCtrl+F7"));
    m.insert("hotkey_pitch_down".into(), json!("CmdOrCtrl+F8"));
    m.insert("hotkey_toggle_monitor".into(), json!("CmdOrCtrl+F9"));
    m.insert("hotkey_toggle_fx".into(), json!("CmdOrCtrl+F10"));
    m.insert("hotkey_toggle_window".into(), json!("CmdOrCtrl+F11"));
    // 每个快捷键单独决定要不要抢成全局。默认全开 —— 以前九个一律全局，
    // 改默认值等于悄悄拿走用户已经在用的功能。
    //
    // 关掉的那些只在软件是当前窗口时有效。意义在于全局快捷键是**独占**的：
    // 被我们抢走的组合，用户在别的软件里就再也按不出原本的功能了。
    for (key, _, _) in crate::shell_extras::HOTKEYS {
        m.insert(format!("{key}_global"), json!(true));
    }
    m.insert("telemetry_opt_in".into(), json!(Value::Null));
    // 完成过多少次变声（开启→停止算一次）。攒够十次问一句要不要关注我们。
    // 问过之后 follow_prompt_done 置 true，这辈子不再问第二次。
    m.insert("vc_run_count".into(), json!(0));
    m.insert("follow_prompt_done".into(), json!(false));
    // 第三方 Hugging Face 下载镜像根。空 = 产品默认双镜像
    // （hf-mirror.com → hf-cdn.sufy.com → 规范域）。见 `hf::download_urls`。
    // 不进 worker / inuse。
    m.insert("hf_endpoint".into(), json!(""));
    m
}

fn read_json(path: &Path) -> Map<String, Value> {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .and_then(|v| v.as_object().cloned())
        .unwrap_or_default()
}

/// Full effective config: defaults overlaid with what the user has saved.
pub fn read(root: &Path) -> Map<String, Value> {
    let mut cfg = defaults();
    let path = paths::app_config_path(root);
    if path.is_file() {
        for (k, v) in read_json(&path) {
            cfg.insert(k, v);
        }
    } else {
        // 全新安装：尚无 app_config，标记语言未确认，前端弹首次语言引导。
        cfg.insert("ui_locale_picked".into(), json!(false));
    }
    let _ = clamp_realtime_perf(&mut cfg);
    let _ = apply_device_alias(&mut cfg);
    cfg
}

/// Old shells wrote `input_device`; the engine only reads `sg_input_device`.
/// Fill the empty side. Never overwrite a non-empty sg_ value — Broadcast
/// may be an intentional choice.
fn apply_device_alias(cfg: &mut Map<String, Value>) -> Vec<String> {
    let mut notes = Vec::new();
    let sg = cfg
        .get("sg_input_device")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    let legacy = cfg
        .get("input_device")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    if sg.is_empty() && !legacy.is_empty() {
        cfg.insert("sg_input_device".into(), json!(legacy.clone()));
        notes.push(format!("sg_input_device ← input_device ({legacy})"));
    } else if !sg.is_empty() && !legacy.is_empty() && sg != legacy {
        notes.push(format!(
            "input_device={legacy}  sg_input_device={sg} (engine uses sg_)"
        ));
    }
    let sg_out = cfg
        .get("sg_output_device")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    let legacy_out = cfg
        .get("output_device")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    if sg_out.is_empty() && !legacy_out.is_empty() {
        cfg.insert("sg_output_device".into(), json!(legacy_out.clone()));
        notes.push(format!("sg_output_device ← output_device ({legacy_out})"));
    }
    notes
}

/// Slider / worker ceiling. 1.0s block_time alone makes delay_ms ≥ 1000.
pub const BLOCK_TIME_MAX: f64 = 0.50;
pub const BLOCK_TIME_MIN: f64 = 0.05;
pub const EXTRA_TIME_MAX: f64 = 3.0;
pub const EXTRA_TIME_MIN: f64 = 0.5;

fn clamp_key(cfg: &mut Map<String, Value>, key: &str, min: f64, max: f64) -> Option<String> {
    let Some(v) = cfg.get(key).and_then(|x| x.as_f64()) else {
        return None;
    };
    let c = v.clamp(min, max);
    if (c - v).abs() < 1e-9 {
        return None;
    }
    cfg.insert(key.to_string(), json!(c));
    Some(format!("{key} {v} → {c}"))
}

/// Pull block_time / extra_time back into the range the sliders advertise.
/// Returns a note per key that moved.
pub fn clamp_realtime_perf(cfg: &mut Map<String, Value>) -> Vec<String> {
    let mut notes = Vec::new();
    if let Some(n) = clamp_key(cfg, "block_time", BLOCK_TIME_MIN, BLOCK_TIME_MAX) {
        notes.push(n);
    }
    if let Some(n) = clamp_key(cfg, "extra_time", EXTRA_TIME_MIN, EXTRA_TIME_MAX) {
        notes.push(n);
    }
    notes
}

/// Write clamped perf keys and leftover device aliases back to app_config.
pub fn persist_perf_caps(root: &Path) {
    let path = paths::app_config_path(root);
    if !path.is_file() {
        return;
    }
    let mut raw = read_json(&path);
    let mut notes = clamp_realtime_perf(&mut raw);
    notes.extend(apply_device_alias(&mut raw));
    let changed = notes.iter().any(|n| n.contains('←') || n.contains('→'));
    if changed {
        if let Ok(text) = serde_json::to_string_pretty(&Value::Object(raw)) {
            let _ = write_atomic(&path, &text);
        }
    }
    for n in notes {
        crate::logging::shell_log!("config: {n}");
    }
}

fn write_atomic(path: &Path, text: &str) -> std::io::Result<()> {
    if let Some(p) = path.parent() {
        std::fs::create_dir_all(p)?;
    }
    // Unique temp name: the shell and the worker can both be writing under
    // User_Data, and a fixed `.tmp` was a real source of WinError 5.
    let tmp = path.with_extension(format!(
        "tmp{}",
        std::process::id() as u64
            ^ std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos() as u64)
                .unwrap_or(0)
    ));
    std::fs::write(&tmp, text)?;
    match std::fs::rename(&tmp, path) {
        Ok(()) => Ok(()),
        Err(e) => {
            // Windows can hold the target open; fall back to a direct write
            // rather than losing the user's setting.
            let _ = std::fs::remove_file(&tmp);
            std::fs::write(path, text).map_err(|_| e)
        }
    }
}

/// True when a string looks like an absolute path (drive letter or UNC).
fn looks_absolute(s: &str) -> bool {
    let b = s.as_bytes();
    (b.len() >= 3 && b[1] == b':' && (b[2] == b'\\' || b[2] == b'/'))
        || s.starts_with("\\\\")
        || s.starts_with('/')
}

/// Windows `canonicalize()` hands back extended-length paths (`\\?\E:\…`).
///
/// That prefix is invisible to the user and meaningless to the comparison
/// below, but it makes `strip_prefix(root)` fail — the path looks like it is
/// outside the install, so it gets blanked. `index_path` is canonicalised in
/// several places in `voices.rs`, so the index of a perfectly local model was
/// being thrown away every time inuse was rewritten.
fn strip_verbatim(p: &str) -> &str {
    p.strip_prefix(r"\\?\UNC\")
        .map(|_| p)
        .unwrap_or_else(|| p.strip_prefix(r"\\?\").unwrap_or(p))
}

/// Strip anything that would pin the worker to this machine's layout.
fn sanitize_inuse(root: &Path, m: &mut Map<String, Value>) {
    let root_s = root.to_string_lossy().to_string();
    let root_s = strip_verbatim(&root_s).to_string();
    for key in ["pth_path", "index_path"] {
        let Some(Value::String(p0)) = m.get(key).cloned() else {
            continue;
        };
        let p = strip_verbatim(&p0).to_string();
        if !looks_absolute(&p) {
            continue;
        }
        // Keep it only if it is inside this install, and store it relative.
        if let Some(rel) = p.strip_prefix(&root_s) {
            let rel = rel.trim_start_matches(['\\', '/']).to_string();
            m.insert(key.into(), json!(rel));
        } else {
            m.insert(key.into(), json!(""));
        }
    }
}

/// Mirror the engine-relevant subset into `configs/inuse/config.json`.
pub fn sync_inuse(root: &Path, cfg: &Map<String, Value>) -> Result<(), String> {
    let path = paths::inuse_config_path(root);
    let mut out = read_json(&path);
    for k in engine_keys() {
        let Some(v) = cfg.get(k) else { continue };
        // Never let an empty model path overwrite one that is already set:
        // losing pth_path means the worker starts with no model at all.
        if matches!(k, "pth_path" | "index_path")
            && v.as_str().map(str::is_empty).unwrap_or(false)
            && out.get(k).and_then(|x| x.as_str()).map(|s| !s.is_empty()) == Some(true)
        {
            continue;
        }
        out.insert(k.to_string(), v.clone());
    }
    // The shell calls it `monitor_self`; the worker reads `monitor_enabled`.
    // Nothing translated between the two, so 「变声时监听自己」 was always
    // false on the engine side no matter what the settings page showed.
    out.insert(
        "monitor_enabled".into(),
        json!(cfg
            .get("monitor_self")
            .and_then(|v| v.as_bool())
            .unwrap_or(false)),
    );
    let _ = clamp_realtime_perf(&mut out);
    sanitize_inuse(root, &mut out);
    let text = serde_json::to_string_pretty(&Value::Object(out)).map_err(|e| e.to_string())?;
    write_atomic(&path, &text).map_err(|e| crate::i18n::te("s.4ad9fdccd9", &(e)))
}

/// Merge `patch` into the saved config; returns the new effective config plus
/// which keys need a restart of the stream to take effect.
pub fn update(root: &Path, patch: Map<String, Value>) -> Result<Value, String> {
    let mut saved = read_json(&paths::app_config_path(root));
    let mut hot = Map::new();
    let mut needs_restart: Vec<String> = Vec::new();
    let mut touched_engine = false;
    let mut touched_monitor = false;

    for (k, v) in patch {
        if is_hot(&k) {
            hot.insert(k.clone(), v.clone());
            touched_engine = true;
        } else if is_cold(&k) {
            needs_restart.push(k.clone());
            touched_engine = true;
        }
        if k == "monitor_self" || k == "monitor_device" {
            touched_monitor = true;
        }
        // Keep the leftover `input_device` alias in sync so old fields
        // stop contradicting what the settings page just wrote.
        if k == "sg_input_device" {
            if let Some(s) = v.as_str() {
                saved.insert("input_device".into(), json!(s));
            }
        }
        if k == "sg_output_device" {
            if let Some(s) = v.as_str() {
                saved.insert("output_device".into(), json!(s));
            }
        }
        // 主显卡不是引擎配置键，它改的是 worker 进程的环境变量，所以既不该
        // 进 inuse（touched_engine），也不能靠 is_cold 拿到重启提示 ——
        // 但它确实要重开变声才换得过去，提示得补上。
        if k == "main_gpu" {
            needs_restart.push(k.clone());
        }
        if k == "ui_locale" {
            if let Some(code) = v.as_str() {
                crate::i18n::set_locale(code);
            }
        }
        saved.insert(k, v);
    }

    let text = serde_json::to_string_pretty(&Value::Object(saved)).map_err(|e| e.to_string())?;
    write_atomic(&paths::app_config_path(root), &text)
        .map_err(|e| crate::i18n::te("s.47a27ebb17", &(e)))?;

    let cfg = read(root);
    // Only touch the engine's config file when an engine key actually changed.
    // The worker may be reading it, and theme / wallpaper / telemetry writes
    // have no business rewriting it.
    if touched_engine {
        sync_inuse(root, &cfg)?;
    }

    // 监听是唯一「冷键但其实能热切」的东西。worker 的 _worker_apply_hot 早就
    // 认 monitor_enabled / monitor_device，转着的时候会自己开关监听流；只是
    // shell 从来没把它推过去，于是用户点完监听要重启变声才生效。
    //
    // 仍然留在 COLD_KEYS 里：inuse 得写进去，新起的 worker 才知道该不该监听。
    // 这里只是额外补一次热推送。
    if touched_monitor {
        let mut p = Map::new();
        p.insert(
            "monitor_enabled".into(),
            json!(cfg
                .get("monitor_self")
                .and_then(|v| v.as_bool())
                .unwrap_or(false)),
        );
        p.insert(
            "monitor_device".into(),
            json!(cfg
                .get("monitor_device")
                .and_then(|v| v.as_str())
                .unwrap_or("")),
        );
        // worker 没起来就算了 —— inuse 已经写好，下次启动自然生效。
        let _ = crate::worker::set_hot(root, p);
        needs_restart.retain(|k| k != "monitor_self" && k != "monitor_device");
    }

    Ok(json!({
        "config": Value::Object(cfg),
        "hot": Value::Object(hot),
        "needs_restart": needs_restart,
    }))
}

/// Newest plaza date (`YYMMDD`) the user has actually looked at. Drives the
/// dot on the 广场 tab, which was previously hardcoded on and therefore never
/// meant anything.
const PLAZA_SEEN: &str = "plaza_seen";

pub fn plaza_seen(root: &Path) -> String {
    read_json(&paths::app_config_path(root))
        .get(PLAZA_SEEN)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

pub fn set_plaza_seen(root: &Path, newest: &str) -> Result<(), String> {
    // Only ever move forward: an older feed (a cached response, a rollback)
    // must not resurrect the dot for content already read.
    if newest.is_empty() || newest <= plaza_seen(root).as_str() {
        return Ok(());
    }
    let mut saved = read_json(&paths::app_config_path(root));
    saved.insert(PLAZA_SEEN.into(), json!(newest));
    let text = serde_json::to_string_pretty(&Value::Object(saved)).map_err(|e| e.to_string())?;
    write_atomic(&paths::app_config_path(root), &text).map_err(|e| crate::i18n::te("s.1455f353e7", &(e)))
}

/// Key holding dismissed models-page banner ids. Not a settings key: it never
/// appears in the settings UI and must not reach the engine's config.
const DISMISSED_ADS: &str = "dismissed_ads";
/// Cap so a long-lived install cannot grow this list without bound.
const DISMISSED_MAX: usize = 200;

pub fn dismissed_ads(root: &Path) -> Vec<String> {
    read_json(&paths::app_config_path(root))
        .get(DISMISSED_ADS)
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|x| x.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default()
}

pub fn dismiss_ad(root: &Path, id: &str) -> Result<(), String> {
    if id.is_empty() {
        return Ok(());
    }
    let mut saved = read_json(&paths::app_config_path(root));
    let mut list = dismissed_ads(root);
    if list.iter().any(|x| x == id) {
        return Ok(());
    }
    list.push(id.to_string());
    // Oldest out first: a banner from two years ago will not come back.
    if list.len() > DISMISSED_MAX {
        let drop = list.len() - DISMISSED_MAX;
        list.drain(..drop);
    }
    saved.insert(DISMISSED_ADS.into(), json!(list));
    let text = serde_json::to_string_pretty(&Value::Object(saved)).map_err(|e| e.to_string())?;
    // Deliberately no sync_inuse: this is not an engine key.
    write_atomic(&paths::app_config_path(root), &text)
        .map_err(|e| crate::i18n::te("s.1455f353e7", &(e)))
}

/// Grouped view used by the settings page, so the UI does not hard-code which
/// keys belong to which tab.
pub fn describe() -> Value {
    let mut groups: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    groups.insert(
        "devices",
        vec![
            "sg_hostapi",
            "sg_input_device",
            "in_gain_db",
            "sg_output_device",
            "monitor_self",
            "monitor_device",
            "sg_wasapi_exclusive",
            "sr_type",
        ],
    );
    groups.insert(
        "voice",
        vec![
            "threhold",
            "pitch",
            "formant",
            "index_rate",
            "rms_mix_rate",
            "f0method",
        ],
    );
    groups.insert(
        "perf",
        vec!["block_time", "crossfade_length", "extra_time", "n_cpu"],
    );
    groups.insert("fx", vec!["I_noise_reduce", "O_noise_reduce", "use_pv"]);
    groups.insert(
        "appearance",
        vec!["theme_mode", "wallpaper_path", "wallpaper_blur", "wallpaper_opacity"],
    );
    groups.insert(
        "general",
        vec!["close_action", "ui_locale", "telemetry_opt_in"],
    );
    json!({
        "groups": groups,
        "hot": HOT_KEYS,
        "cold": COLD_KEYS,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn leftover_input_device_fills_empty_sg_key() {
        let mut m = Map::new();
        m.insert("input_device".into(), json!("麦克风 (Realtek(R) Audio)"));
        m.insert("sg_input_device".into(), json!(""));
        let notes = apply_device_alias(&mut m);
        assert_eq!(m["sg_input_device"], json!("麦克风 (Realtek(R) Audio)"));
        assert!(notes.iter().any(|n| n.contains("←")));
    }

    #[test]
    fn leftover_input_device_does_not_override_broadcast() {
        let mut m = Map::new();
        m.insert("input_device".into(), json!("麦克风 (Realtek(R) Audio)"));
        m.insert("sg_input_device".into(), json!("麦克风 (NVIDIA Broadcast)"));
        let notes = apply_device_alias(&mut m);
        assert_eq!(m["sg_input_device"], json!("麦克风 (NVIDIA Broadcast)"));
        assert!(notes.iter().any(|n| n.contains("engine uses sg_")));
    }

    #[test]
    fn realtime_perf_caps_cut_one_second_blocks() {
        let mut m = Map::new();
        m.insert("block_time".into(), json!(1));
        m.insert("extra_time".into(), json!(5));
        let notes = clamp_realtime_perf(&mut m);
        assert_eq!(notes.len(), 2);
        assert_eq!(m["block_time"], json!(BLOCK_TIME_MAX));
        assert_eq!(m["extra_time"], json!(EXTRA_TIME_MAX));
        assert!(clamp_realtime_perf(&mut m).is_empty());
    }

    #[test]
    fn hot_and_cold_do_not_overlap() {
        for k in HOT_KEYS {
            assert!(!COLD_KEYS.contains(k), "{k} in both sets");
        }
    }

    #[test]
    fn monitor_toggle_reaches_the_worker() {
        // 语言是进程级全局状态，别的测试改了会让这里的 t() 前后取到两种语言。
        let _g = crate::i18n::testing::pin("zh-CN");
        // The settings page writes `monitor_self`; the worker only ever looks
        // at `monitor_enabled`. If this mapping goes missing again,
        // 「变声时监听自己」 silently does nothing.
        let root = std::env::temp_dir().join("rvcf-monitor-sync-test");
        let _ = std::fs::remove_dir_all(&root);
        let mut cfg = defaults();
        cfg.insert("monitor_self".into(), json!(true));
        cfg.insert("monitor_device".into(), json!(crate::i18n::t("s.a593781b23")));
        sync_inuse(&root, &cfg).unwrap();

        let out = read_json(&paths::inuse_config_path(&root));
        assert_eq!(out.get("monitor_enabled"), Some(&json!(true)));
        assert_eq!(out.get("monitor_device"), Some(&json!(crate::i18n::t("s.a593781b23"))));

        cfg.insert("monitor_self".into(), json!(false));
        sync_inuse(&root, &cfg).unwrap();
        let out = read_json(&paths::inuse_config_path(&root));
        assert_eq!(out.get("monitor_enabled"), Some(&json!(false)));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn monitor_keys_force_an_inuse_write() {
        // `update()` only touches inuse when a key is hot or cold. Monitoring
        // was in neither list, so the toggle never got as far as the engine.
        assert!(is_cold("monitor_self"));
        assert!(is_cold("monitor_device"));
    }

    #[test]
    fn verbatim_prefixed_paths_survive_sanitize() {
        // Windows canonicalize() 返回 \\?\ 开头的扩展长度路径，voices.rs 里
        // index 全是这么来的。以前 strip_prefix(root) 匹配不上，于是本机模型的
        // 检索库每次重写 inuse 都被清空 —— 用户看到的是「检索库没了」。
        let root = Path::new(r"E:\Dev\RVC-Fabric");
        let mut m = Map::new();
        m.insert(
            "pth_path".into(),
            json!(r"\\?\E:\Dev\RVC-Fabric\User_Data\models\anon\anon.pth"),
        );
        m.insert(
            "index_path".into(),
            json!(r"\\?\E:\Dev\RVC-Fabric\User_Data\models\anon\a.index"),
        );
        sanitize_inuse(root, &mut m);
        assert_eq!(
            m["pth_path"],
            json!(r"User_Data\models\anon\anon.pth"));
        assert_eq!(m["index_path"], json!(r"User_Data\models\anon\a.index"));
    }

    #[test]
    fn verbatim_paths_outside_the_install_are_still_dropped() {
        // 去前缀只是为了能正确比较，不是放行：别的盘上的路径照样得清掉。
        let root = Path::new(r"E:\Dev\RVC-Fabric");
        let mut m = Map::new();
        m.insert("pth_path".into(), json!(r"\\?\L:\somebody-else\x.pth"));
        sanitize_inuse(root, &mut m);
        assert_eq!(m["pth_path"], json!(""));
    }

    #[test]
    fn absolute_paths_are_detected() {
        assert!(looks_absolute("L:\\My Project\\a.pth"));
        assert!(looks_absolute("C:/x/y.index"));
        assert!(looks_absolute("\\\\server\\share\\a"));
        assert!(!looks_absolute("User_Data/models/anon/a.pth"));
        assert!(!looks_absolute(""));
    }

    #[test]
    fn inuse_strips_foreign_absolute_paths() {
        let root = Path::new("C:\\App");
        let mut m = Map::new();
        m.insert("pth_path".into(), json!("Z:\\somewhere\\anon.pth"));
        m.insert("index_path".into(), json!("C:\\App\\User_Data\\a.index"));
        sanitize_inuse(root, &mut m);
        assert_eq!(m["pth_path"], json!(""));
        assert_eq!(m["index_path"], json!("User_Data\\a.index"));
    }

    #[test]
    fn empty_model_path_never_clobbers_a_real_one() {
        // The shell rewrites inuse from app_config at startup. If app_config
        // has not caught up yet, an empty pth_path must not wipe the model the
        // worker is actually using.
        let root = std::env::temp_dir().join("rvcf-inuse-guard");
        let inuse = root.join("configs").join("inuse");
        std::fs::create_dir_all(&inuse).unwrap();
        std::fs::write(
            inuse.join("config.json"),
            r#"{"pth_path":"User_Data/models/anon/anon.pth","index_path":"a.index"}"#,
        )
        .unwrap();

        let mut cfg = defaults(); // pth_path / index_path default to ""
        cfg.insert("pitch".into(), json!(5));
        sync_inuse(&root, &cfg).unwrap();

        let after = read_json(&paths::inuse_config_path(&root));
        assert_eq!(
            after["pth_path"], json!("User_Data/models/anon/anon.pth"),
            "empty default must not clear the selected model"
        );
        assert_eq!(after["pitch"], json!(5), "other keys still sync");
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 「主显卡」是个特例：它不是引擎配置键，改的是 worker 进程的环境变量。
    ///
    /// 所以它既不能进 COLD_KEYS（那会把一个 worker 根本不读的键写进 inuse），
    /// 又必须给出重启提示 —— 换卡不重开变声是换不过去的。以前有人顺手把这类
    /// 键塞进 COLD_KEYS 或者干脆忘了提示，用户改完毫无反应，只会以为功能坏了。
    #[test]
    fn main_gpu_asks_for_a_restart_without_pretending_to_be_an_engine_key() {
        assert!(!is_hot("main_gpu"));
        assert!(!is_cold("main_gpu"));
        assert!(!engine_keys().contains(&"main_gpu"));

        let root = std::env::temp_dir().join("rvcf-main-gpu-test");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();

        let mut patch = Map::new();
        patch.insert("main_gpu".into(), json!(1));
        let out = update(&root, patch).unwrap();

        let restart = out["needs_restart"].as_array().unwrap();
        assert!(
            restart.iter().any(|v| v == "main_gpu"));
        assert_eq!(out["config"]["main_gpu"], json!(1));

        // 不是引擎键，就不该顺手去改引擎的配置文件 —— worker 可能正在读它。
        assert!(
            !paths::inuse_config_path(&root).is_file());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn main_gpu_defaults_to_auto() {
        // -1 才是「自动」。写成 0 的话所有单卡用户会被静默钉在 0 号卡上，
        // 表面看不出区别，出问题时也查不到。
        assert_eq!(defaults()["main_gpu"], json!(-1));
    }

    #[test]
    fn defaults_cover_every_engine_key() {
        let d = defaults();
        for k in engine_keys() {
            assert!(d.contains_key(k), "default missing for {k}");
        }
    }
}
