//! Tray, global hotkeys, diagnostics and consult packs.
//!
//! These are the pieces of the Python shell that live outside any page:
//! `launcher/tray.py`, `launcher/hotkeys.py`, the 「其他」page's diagnostics
//! bundle, and `launcher/consult_pack.py`.
//!
//! Hotkey combos match the old shell exactly — users have muscle memory:
//! Ctrl+F2 toggle, Ctrl+F3 mode, Ctrl+F5/F6 previous/next voice.

use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Stdio;

use serde_json::{json, Value};
use std::sync::OnceLock;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager};

use crate::{config, paths, worker};

// ---------------------------------------------------------------------------
// Tray
// ---------------------------------------------------------------------------

/// Build the tray icon. Closing to tray is what keeps conversion running while
/// the window is out of the way, so the tray must always exist — not only when
/// the user picked "minimise to tray".
pub fn install_tray(app: &AppHandle) -> Result<(), String> {
    let show = MenuItem::with_id(app, "show", &crate::i18n::t("tray.show"), true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let toggle = MenuItem::with_id(
        app,
        "toggle",
        &crate::i18n::t("tray.toggle"),
        true,
        None::<&str>,
    )
    .map_err(|e| e.to_string())?;
    let quit = MenuItem::with_id(app, "quit", &crate::i18n::t("tray.quit"), true, None::<&str>)
        .map_err(|e| e.to_string())?;
    let menu =
        Menu::with_items(app, &[&show, &toggle, &quit]).map_err(|e| e.to_string())?;

    TrayIconBuilder::with_id("main")
        .tooltip("RVC Fabric")
        .icon(
            app.default_window_icon()
                .cloned()
                .ok_or_else(|| crate::i18n::t("tray.missingIcon"))?,
        )
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(move |app, event| match event.id.as_ref() {
            "show" => focus_main(app),
            "toggle" => {
                let _ = app.emit("tray://toggle-vc", ());
            }
            "quit" => {
                // Stop the stream before leaving, otherwise the worker keeps
                // holding the audio device after the UI is gone.
                if let Some(root) = root_of(app) {
                    let _ = worker::stop_vc(&root, true);
                }
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            // Only the *left* button opens the window, and only on release.
            //
            // `TrayIconEvent::Click` fires for every button, right-click
            // included. On Windows the right-click menu is a tracked popup
            // owned by a hidden message window: focusing another window while
            // it is up makes Windows dismiss it. Reacting to the right-click
            // here is what made the menu flash and vanish. Matching on Down as
            // well would fire twice per click.
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                focus_main(&tray.app_handle().clone());
            }
        })
        .build(app)
        .map_err(|e| e.to_string())?;
    Ok(())
}

/// 上一次弹出「关闭询问」但**还没被回答**的时刻。
///
/// 用来兜住「界面卡死了，用户连窗口都关不掉」：10 秒内第二次点 X 就直接退出。
///
/// 关键是**答完必须清掉**（`clear_close_ask`）。以前它是个闭包里的局部变量，
/// 谁也够不着，于是用户点 X → 选「最小化到托盘」→ 一会儿又点 X，第二次就撞上
/// 这条兜底：软件不问一声直接没了。用户报的「再次点 X 软件会崩溃」就是这个 ——
/// 它没崩，是被自己的救命开关退掉了。答过一次就证明界面是活的，计时该归零。
static LAST_ASK: std::sync::Mutex<Option<std::time::Instant>> =
    std::sync::Mutex::new(None);

/// 用户答过关闭询问了：界面是活的，把「卡死」计时清掉。
pub fn clear_close_ask() {
    *LAST_ASK.lock().unwrap_or_else(|e| e.into_inner()) = None;
}

fn focus_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        // 显示器拔掉之后窗口会留在一块已经不存在的屏上。这时候「打开主界面」
        // 什么都不会发生，而托盘是用户此刻唯一的入口——先把它拉回来。只在整个
        // 窗口都不在任何屏上时才动，用户自己把窗口摆在哪块屏是他的事。
        crate::window_watch::rescue_if_offscreen(&w);
        let _ = w.set_focus();
    }
}

fn root_of(app: &AppHandle) -> Option<PathBuf> {
    app.try_state::<std::sync::Mutex<crate::AppState>>()
        // Poison-safe: on a poisoned state we still want the tray quit item to
        // be able to stop the worker.
        .map(|s| {
            s.lock()
                .unwrap_or_else(|e| e.into_inner())
                .root
                .clone()
        })
}

// ---------------------------------------------------------------------------
// Global hotkeys
// ---------------------------------------------------------------------------

/// 全局快捷键：配置键名、动作名、默认组合。
///
/// 前四个的默认值和旧的 Python 壳一样，用户有肌肉记忆，不能改。用户改过的
/// 组合存在配置里，这里只是缺省。
///
/// 收录标准只有一条：**这件事值不值得在窗口看不见的时候做**。全局快捷键是给
/// 正在游戏、正在直播、主界面缩在托盘里的人用的。改设置、翻音色库这些非得看着
/// 界面才能做的事，给它配快捷键没有意义。
pub const HOTKEYS: &[(&str, &str, &str)] = &[
    ("hotkey_toggle_vc", "toggle-vc", "CmdOrCtrl+F2"),
    ("hotkey_toggle_mode", "toggle-mode", "CmdOrCtrl+F3"),
    ("hotkey_prev_voice", "prev-voice", "CmdOrCtrl+F5"),
    ("hotkey_next_voice", "next-voice", "CmdOrCtrl+F6"),
    // 音高一次一个半音。开着黑发现音色偏高偏低，不用退出游戏调。
    ("hotkey_pitch_up", "pitch-up", "CmdOrCtrl+F7"),
    ("hotkey_pitch_down", "pitch-down", "CmdOrCtrl+F8"),
    // 监听自己。队友说你声音怪，想立刻听一耳朵自己现在是什么效果。
    ("hotkey_toggle_monitor", "toggle-monitor", "CmdOrCtrl+F9"),
    // 后期音效总开关。怀疑是压缩/均衡把声音搞糊了，一键旁路对比。
    ("hotkey_toggle_fx", "toggle-fx", "CmdOrCtrl+F10"),
    // 显示 / 隐藏主界面。缩在托盘里时这是唯一不用去点托盘图标的入口。
    ("hotkey_toggle_window", "toggle-window", "CmdOrCtrl+F11"),
];

/// 组合键的合法形状：零个或多个修饰键 + 一个主键，`+` 连接。
///
/// 注册失败的组合会被 Tauri 直接拒掉，但一个乱七八糟的字符串还可能让
/// on_shortcut 直接 panic —— 先自己筛一道。
fn combo_ok(s: &str) -> bool {
    let s = s.trim();
    if s.is_empty() || s.len() > 48 {
        return false;
    }
    let parts: Vec<&str> = s.split('+').map(str::trim).collect();
    if parts.len() > 5 || parts.iter().any(|p| p.is_empty()) {
        return false;
    }
    parts
        .iter()
        .all(|p| p.chars().all(|c| c.is_ascii_alphanumeric()))
}

/// 用户配的组合键，没配或配得不合法就用默认值。
fn combo_for(root: Option<&Path>, key: &str, fallback: &str) -> String {
    let Some(root) = root else {
        return fallback.to_string();
    };
    let v = config::read(root);
    let raw = v.get(key).and_then(|x| x.as_str()).unwrap_or("").trim();
    if combo_ok(raw) {
        raw.to_string()
    } else {
        fallback.to_string()
    }
}

/// 某个快捷键要不要抢成全局的。配置键是组合键的键名加 `_global`。
///
/// 默认 true —— 以前九个一律全局，改默认值等于悄悄拿走用户已经在用的功能。
///
/// 关掉之后这个组合就只在 RVC Fabric 是当前窗口时有效（由前端的 keydown
/// 兜着）。这件事有意义是因为全局快捷键是**独占**的：Ctrl+F7 被我们抢走之后，
/// 用户在别的软件里就再也按不出它原本的功能了。有人只想在切回本软件时用一下，
/// 不想为此把这个组合从整台机器上让出来。
pub fn global_for(root: Option<&Path>, key: &str) -> bool {
    let Some(root) = root else {
        return true;
    };
    config::read(root)
        .get(&format!("{key}_global"))
        .and_then(|x| x.as_bool())
        .unwrap_or(true)
}

/// 藏着就叫出来，已经在前面就收回托盘。
///
/// 「已经在前面」用 is_focused 判断，不用 is_visible：窗口可能可见但被游戏
/// 全屏盖住，那时候用户按这个键是想把它调出来，不是想让它消失。
fn toggle_main_window(app: &AppHandle) {
    let Some(w) = app.get_webview_window("main") else {
        return;
    };
    let up = w.is_visible().unwrap_or(false)
        && !w.is_minimized().unwrap_or(false)
        && w.is_focused().unwrap_or(false);
    if up {
        let _ = w.hide();
    } else {
        focus_main(app);
    }
}

/// Register or unregister the global hotkeys. Failing to grab a combo (another
/// app already owns it) must not break the rest — report and carry on.
pub fn apply_hotkeys(app: &AppHandle, enabled: bool) -> Value {
    use tauri_plugin_global_shortcut::GlobalShortcutExt;
    let gs = app.global_shortcut();
    let _ = gs.unregister_all();
    if !enabled {
        return json!({"enabled": false, "registered": [], "failed": []});
    }
    let root = root_of(app);
    let mut ok: Vec<String> = Vec::new();
    let mut failed: Vec<String> = Vec::new();
    // 用户特地设成「只在软件内」的那些。不注册全局，交给前端的 keydown。
    let mut local: Vec<String> = Vec::new();
    for (key, action, default) in HOTKEYS {
        let combo = combo_for(root.as_deref(), key, default);
        if !global_for(root.as_deref(), key) {
            local.push(combo);
            continue;
        }
        let handle = app.clone();
        let act = action.to_string();
        match gs.on_shortcut(combo.as_str(), move |_a, _s, _e| {
            // 显示 / 隐藏窗口在这里就地做完，不往前端发事件。
            //
            // 窗口藏起来的时候 webview 有可能被系统挂起，事件到不了前端 ——
            // 而「窗口是藏着的」恰恰是最需要这个快捷键的时候。发事件让前端
            // 把自己显示出来，等于让一个睡着的人自己叫醒自己。
            if act == "toggle-window" {
                toggle_main_window(&handle);
                return;
            }
            let _ = handle.emit(&format!("hotkey://{act}"), ());
        }) {
            Ok(()) => ok.push(combo),
            // 组合被别的程序占了就跳过这一个，其余的照常注册 —— 一个冲突
            // 不该让所有快捷键全废。界面上会把失败的那个标出来。
            Err(_) => failed.push(combo),
        }
    }
    json!({"enabled": true, "registered": ok, "failed": failed, "local": local})
}

// ---------------------------------------------------------------------------
// Diagnostics bundle
// ---------------------------------------------------------------------------

/// Run `tools/benchmark_realtime.py` in the Runtime, writing a JSON report into
/// `User_Data/perf_reports/`. Takes roughly a minute; callers must say so.
///
/// 以前写成 `--out <目录>` 且没传必填的 `--pth`，脚本一启动就 argparse 失败，
/// 诊断包里永远没有新性能报告——等于「直接生成诊断包」。
pub fn run_perf_bench(root: &Path) -> Result<PathBuf, String> {
    let py = paths::runtime_python(root)
        .or_else(|| paths::runtime_pythonw(root))
        .ok_or_else(|| crate::i18n::t("s.c8c05e7db7"))?;
    let script = root.join("tools").join("benchmark_realtime.py");
    if !script.is_file() {
        return Err(crate::i18n::t("s.c41c6ca117").into());
    }

    let cfg = config::read(root);
    let pth = cfg
        .get("pth_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    let pth = if !pth.is_empty() && Path::new(&pth).is_file() {
        pth
    } else {
        // 兜底 last_model_path（有时 pth_path 是相对路径或空）
        let alt = cfg
            .get("last_model_path")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim()
            .to_string();
        if alt.is_empty() || !Path::new(&alt).is_file() {
            return Err(crate::i18n::t("s.40019094c0").into());
        }
        alt
    };
    let index = cfg
        .get("index_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    let pitch = cfg
        .get("pitch")
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    let formant = cfg
        .get("formant")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0);
    let f0method = cfg
        .get("f0method")
        .and_then(|v| v.as_str())
        .unwrap_or("rmvpe");
    // harvest 在 bench 里不支持
    let f0method = if f0method == "harvest" {
        "rmvpe"
    } else {
        f0method
    };
    let block_time = cfg
        .get("block_time")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.25);
    let crossfade = cfg
        .get("crossfade_length")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.05);
    let extra = cfg
        .get("extra_time")
        .and_then(|v| v.as_f64())
        .unwrap_or(2.5);
    let index_rate = cfg
        .get("index_rate")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0);

    let out_dir = paths::user_data(root).join("perf_reports");
    std::fs::create_dir_all(&out_dir).map_err(|e| e.to_string())?;
    let stamp = now_stamp();
    let json_out = out_dir.join(format!("bench_{stamp}.json"));
    let log_path = crate::logging::daily_path(root, crate::logging::CH_BENCH);
    let _ = std::fs::create_dir_all(paths::logs_dir(root));
    let errfile = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .ok();

    let mut cmd = std::process::Command::new(py);
    cmd.arg(&script)
        .arg("--pth")
        .arg(&pth)
        .arg("--json-out")
        .arg(&json_out)
        .arg("--f0method")
        .arg(f0method)
        .arg("--pitch")
        .arg(pitch.to_string())
        .arg("--formant")
        .arg(formant.to_string())
        .arg("--block-time")
        .arg(block_time.to_string())
        .arg("--crossfade-time")
        .arg(crossfade.to_string())
        .arg("--extra-time")
        .arg(extra.to_string())
        // 诊断场景略减块数，控制在约一分钟内
        .arg("--n-blocks")
        .arg("120")
        .arg("--warmup")
        .arg("8")
        .current_dir(root)
        .envs(worker::env_for_runtime(root))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(match errfile {
            Some(f) => Stdio::from(f),
            None => Stdio::null(),
        });
    if !index.is_empty() && Path::new(&index).is_file() {
        cmd.arg("--index").arg(&index);
        if index_rate > 0.0 {
            cmd.arg("--index-rate").arg(index_rate.to_string());
        }
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    crate::logging::shell_log!(
        "perf bench: pth={} json={}",
        pth,
        json_out.display()
    );
    let status = cmd.status().map_err(|e| crate::i18n::te("s.84256012c6", &(e)))?;
    if !status.success() {
        return Err(crate::i18n::te(
            "s.470a002848",
            &status.code().map(|c| c.to_string()).unwrap_or_else(|| "?".into()),
        ));
    }
    if !json_out.is_file() {
        return Err(crate::i18n::t("s.f9e62f8c38").into());
    }
    Ok(json_out)
}

fn is_log_file(p: &Path) -> bool {
    let name = p
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    name.ends_with(".log") || name.ends_with(".log.1")
}

fn collect_log_files(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return;
    };
    for e in rd.flatten() {
        let p = e.path();
        if p.is_dir() {
            collect_log_files(&p, out);
            continue;
        }
        if is_log_file(&p) {
            out.push(p);
        }
    }
}

fn sort_newest(files: &mut [PathBuf]) {
    files.sort_by_key(|p| {
        std::cmp::Reverse(std::fs::metadata(p).and_then(|m| m.modified()).ok())
    });
}

/// Newest `cap` logs per channel, plus leftover flat files in the logs root.
/// A global newest-N list let one flooded worker file crowd out sts/tts.
fn logs_for_zip(logs: &Path) -> Vec<PathBuf> {
    const PER_CHANNEL: usize = 8;
    let mut out = Vec::new();
    for ch in crate::logging::CHANNELS {
        let mut files = Vec::new();
        collect_log_files(&logs.join(ch), &mut files);
        sort_newest(&mut files);
        out.extend(files.into_iter().take(PER_CHANNEL));
    }
    if let Ok(rd) = std::fs::read_dir(logs) {
        let mut flat: Vec<PathBuf> = rd
            .flatten()
            .map(|e| e.path())
            .filter(|p| p.is_file() && is_log_file(p))
            .collect();
        sort_newest(&mut flat);
        out.extend(flat.into_iter().take(PER_CHANNEL));
    }
    out
}

fn read_range(path: &Path, start: u64, len: usize) -> Vec<u8> {
    use std::io::{Read, Seek, SeekFrom};
    let Ok(mut f) = std::fs::File::open(path) else {
        return Vec::new();
    };
    if f.seek(SeekFrom::Start(start)).is_err() {
        return Vec::new();
    }
    let mut buf = vec![0u8; len];
    let n = f.read(&mut buf).unwrap_or(0);
    buf.truncate(n);
    buf
}

fn tail_bytes(path: &Path, max: usize) -> String {
    let len = std::fs::metadata(path).map(|m| m.len()).unwrap_or(0);
    let start = len.saturating_sub(max as u64);
    let data = read_range(path, start, max);
    String::from_utf8_lossy(&data).into_owned()
}

/// Head + tail so a TypedStorage flood cannot erase the start_vc / delay lines.
fn clip_log(path: &Path, head: usize, tail: usize) -> String {
    let len = std::fs::metadata(path).map(|m| m.len()).unwrap_or(0) as usize;
    if len == 0 {
        return String::new();
    }
    if len <= head.saturating_add(tail) {
        let data = read_range(path, 0, len);
        return String::from_utf8_lossy(&data).into_owned();
    }
    let head_buf = read_range(path, 0, head);
    let mut out = String::from_utf8_lossy(&head_buf).into_owned();
    if let Some(i) = out.rfind('\n') {
        out.truncate(i + 1);
    }
    let skipped = len - head - tail;
    out.push_str(&format!("\n--- truncated {skipped} bytes ---\n\n"));
    let tail_buf = read_range(path, (len - tail) as u64, tail);
    let tail_s = String::from_utf8_lossy(&tail_buf);
    let tail_s = match tail_s.find('\n') {
        Some(i) if i < 4096 => tail_s[i + 1..].to_string(),
        _ => tail_s.into_owned(),
    };
    out.push_str(&tail_s);
    out
}

// ---------------------------------------------------------------------------
// 诊断包脱敏
// ---------------------------------------------------------------------------

/// 用户主目录里那一段个人信息：`C:\Users\张三` 的「张三」。
///
/// 诊断包会被贴进群里、转给旁人。里面几乎每条日志、每个配置项都带绝对路径，
/// 而 Windows 的用户名往往就是真名或常用 ID —— 那是用户没打算公开的东西，
/// 跟排障也没有半点关系。
///
/// 返回 (要替换掉的字符串, 替换成什么)。查不到主目录就返回 None。
pub(crate) fn home_redaction() -> Option<(String, String)> {
    let home = std::env::var("USERPROFILE")
        .or_else(|_| std::env::var("HOME"))
        .ok()?;
    let home = home.trim_end_matches(['/', '\\']).to_string();
    if home.len() < 4 {
        return None; // "/" 之类的，替换掉只会把整份文本搅烂
    }
    Some((home, "<用户目录>".to_string()))
}

/// 把文本里的用户名抹掉。
///
/// 只认主目录整段（连同盘符和 `Users\`），不去猜「哪个词像人名」—— 猜错的
/// 代价是把日志里真正要看的字段也改了，排障的人拿到一份被改坏的证据。
///
/// 反斜杠、正斜杠、以及 JSON 里转义过的 `\\` 三种写法都要认：同一个路径在
/// info.json、config.json 和日志里长得不一样。
pub(crate) fn redact_user(text: &str, redaction: Option<&(String, String)>) -> String {
    let Some((home, mask)) = redaction else {
        return text.to_string();
    };
    let mut out = text.to_string();
    let slash = home.replace('\\', "/");
    let escaped = home.replace('\\', "\\\\");
    // 长的先替换：`C:\\Users\x` 是 `C:\Users\x` 的转义写法，反过来先换短的
    // 会把它切成两半，剩下半截反斜杠留在原地。
    let mut forms = vec![escaped, home.clone(), slash];
    forms.sort_by_key(|f| std::cmp::Reverse(f.len()));
    forms.dedup();
    for f in forms {
        if f.is_empty() {
            continue;
        }
        // 大小写不敏感：Windows 的路径大小写在不同 API 之间并不一致。
        out = replace_ignore_case(&out, &f, mask);
    }
    out
}

/// `str::replace` 的大小写不敏感版。按字节走，只在 ASCII 上折叠大小写 ——
/// 用户名里的中日韩字符本来就没有大小写之分。
fn replace_ignore_case(haystack: &str, needle: &str, to: &str) -> String {
    if needle.is_empty() {
        return haystack.to_string();
    }
    let hay_lower = haystack.to_ascii_lowercase();
    let needle_lower = needle.to_ascii_lowercase();
    let mut out = String::with_capacity(haystack.len());
    let mut at = 0usize;
    while let Some(rel) = hay_lower[at..].find(&needle_lower) {
        let start = at + rel;
        out.push_str(&haystack[at..start]);
        out.push_str(to);
        at = start + needle.len();
    }
    out.push_str(&haystack[at..]);
    out
}

fn zip_text(
    zip: &mut zip::ZipWriter<std::fs::File>,
    opts: zip::write::FileOptions<'_, ()>,
    arc: &str,
    text: &str,
) -> Result<(), String> {
    zip.start_file(arc, opts).map_err(|e| e.to_string())?;
    zip.write_all(text.as_bytes()).map_err(|e| e.to_string())
}

fn delay_estimate(cfg: &serde_json::Map<String, Value>) -> Value {
    let block = cfg
        .get("block_time")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.25);
    let xf = cfg
        .get("crossfade_length")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.08);
    let extra = cfg
        .get("extra_time")
        .and_then(|v| v.as_f64())
        .unwrap_or(2.5);
    let nr = cfg
        .get("I_noise_reduce")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let mut algo = block + xf + 0.01;
    if nr {
        algo += xf.min(0.04);
    }
    json!({
        "block_ms": (block * 1000.0).round() as i64,
        "crossfade_ms": (xf * 1000.0).round() as i64,
        "extra_time_s": extra,
        "algo_ms_without_device": (algo * 1000.0).round() as i64,
        "formula": "device + block + wait_to_start + infer (live; crossfade/extra_time lookback only)",
        "extra_time_note": "lookback only; not in delay_ms",
    })
}

/// 用户在生成诊断包前自己填的那几行。
///
/// 群昵称和 QQ 号是**用户主动交出来**的联系方式 —— 没有它，支援拿到一个
/// `diag_20260817_143012.zip` 也不知道该回复谁。这跟「顺手把系统里的用户名
/// 一起打包出去」是两回事，后者用户既没同意也不知情，`redact_user` 负责抹掉。
#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct UserReport {
    #[serde(default)]
    pub nickname: String,
    #[serde(default)]
    pub qq: String,
    #[serde(default)]
    pub description: String,
    /// 用户随手粘进来的截图。一张图省下的来回，往往比整份日志还多 ——
    /// 「界面出错」这四个字加一张截图就知道是哪扇窗、哪个按钮。
    #[serde(default)]
    pub shots: Vec<Shot>,
}

/// 一张截图。前端已经缩过尺寸、编成 base64；这里只负责解码写盘。
#[derive(Debug, Clone, Default, serde::Deserialize)]
pub struct Shot {
    /// 扩展名（png / jpg）。只认这两种，其余一律当 png 存。
    #[serde(default)]
    pub ext: String,
    /// 不带 `data:` 前缀的 base64。
    #[serde(default)]
    pub data: String,
}

/// 最多收几张、单张最大多少。挡的是手滑，不是人。
const MAX_SHOTS: usize = 6;
const MAX_SHOT_BYTES: usize = 8 * 1024 * 1024;

/// base64 解码。
///
/// 为一个「把粘贴板里的图写进 zip」加一个依赖不划算，何况这段是纯函数、好测。
/// 忽略空白（前端拼出来的串可能带换行），认标准表，`=` 之后就停。
pub fn base64_decode(src: &str) -> Option<Vec<u8>> {
    fn val(c: u8) -> Option<u8> {
        match c {
            b'A'..=b'Z' => Some(c - b'A'),
            b'a'..=b'z' => Some(c - b'a' + 26),
            b'0'..=b'9' => Some(c - b'0' + 52),
            b'+' => Some(62),
            b'/' => Some(63),
            _ => None,
        }
    }
    let mut out = Vec::with_capacity(src.len() / 4 * 3);
    let mut buf: u32 = 0;
    let mut bits: u32 = 0;
    for &c in src.as_bytes() {
        if c.is_ascii_whitespace() {
            continue;
        }
        if c == b'=' {
            break;
        }
        let v = val(c)? as u32;
        buf = (buf << 6) | v;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((buf >> bits) as u8);
        }
    }
    Some(out)
}

impl UserReport {
    /// 三个字段都是自由文本，直接进 zip。裁长度是防手滑粘贴一整本小说进来
    /// 把包撑大，不是防人。
    fn sanitized(&self) -> Value {
        fn clip(s: &str, max: usize) -> String {
            let t = s.trim();
            if t.chars().count() <= max {
                return t.to_string();
            }
            t.chars().take(max).collect::<String>() + "…"
        }
        json!({
            "nickname": clip(&self.nickname, 64),
            "qq": clip(&self.qq, 32),
            "description": clip(&self.description, 4000),
            // 图不进 report.json —— 它是给人读的，塞几兆 base64 进去就没法读了。
            // 只记一句「有几张」，图本身在 shots/ 下。
            "shots": self.shots.len(),
        })
    }

    fn is_empty(&self) -> bool {
        self.nickname.trim().is_empty()
            && self.qq.trim().is_empty()
            && self.description.trim().is_empty()
            && self.shots.is_empty()
    }
}

// ---------------------------------------------------------------------------
// 原生对话框
// ---------------------------------------------------------------------------

/// 主窗口所在的 AppHandle。`setup` 里存一次，给原生对话框认父窗口用。
///
/// 存全局而不是把 `AppHandle` 一路传下去：需要挂父窗口的对话框散在四个模块、
/// 十几个调用点，其中多数是普通函数不是 tauri 命令，逐个改签名会波及一大片。
/// 而「父窗口是哪个」本来就是进程级唯一的事实 —— 只有一个 main 窗口。
static APP: OnceLock<AppHandle> = OnceLock::new();

pub fn remember_app(app: &AppHandle) {
    let _ = APP.set(app.clone());
}

/// 对话框该挂在哪个窗口上：**发起这次调用的那个**。
///
/// 以前写死 `"main"`。人声分离 / 训练音色 / 语音转换都是独立的工具窗口
/// （`tool_window.rs`），从它们里面点「选择文件夹」，对话框却认主窗口当爹
/// —— Windows 把主窗口连同对话框一起拉到前台，工具窗口跟它俩没有归属关系，
/// 于是被挤到后面。用户视角就是「选完文件夹，那个窗口没了」。
///
/// 后来改成「找当前有焦点的那个窗口」，还是不对。窗口内容跑在 WebView2 里，
/// 真正持有键盘焦点的是 WebView2 那个子 HWND，不是顶层窗口；`is_focused()`
/// 读的又是 tao 缓存下来的标志而不是现问系统，于是可能所有窗口都报 false，
/// 一路退回 `"main"`，等于没改。
///
/// 现在不猜了：Tauri v2 的命令可以声明一个 `window: WebviewWindow` 参数，
/// 框架会把**发起这次 invoke 的窗口**注入进来。这是唯一的事实来源，任何缓存
/// 和启发式都比不过它。
///
/// `None` 是留给非命令上下文的（比如托盘菜单），那里确实没有发起窗口，退回
/// 主窗口是对的。
fn resolve_parent(win: Option<&tauri::WebviewWindow>) -> Option<tauri::WebviewWindow> {
    if let Some(w) = win {
        return Some(w.clone());
    }
    APP.get()?.get_webview_window("main")
}

/// 建一个挂在 `win` 上的文件对话框。
///
/// 不设父窗口的话，它是一个跟我们没有归属关系的顶层窗口。而选目录用的是同步
/// 命令（原生对话框要主线程），对话框一开，整个事件循环就停了 —— 用户点主
/// 窗口的关闭按钮没有任何反应，也不可能弹提示告诉他「先关掉对话框」：那句提示
/// 要渲染，而渲染线程正被堵着。
///
/// 设了父窗口，Windows 自己会把这件事说清楚：父窗口标题栏变灰，点父窗口时对话框
/// 闪一下并被拉到前台。这是所有 Windows 程序的既有约定，不需要一个字的文案。
pub fn dialog_on(win: Option<&tauri::WebviewWindow>) -> rfd::FileDialog {
    let d = rfd::FileDialog::new();
    match resolve_parent(win) {
        Some(w) => d.set_parent(&w),
        None => d,
    }
}

/// 同上，给消息框用。
pub fn message_dialog() -> rfd::MessageDialog {
    let d = rfd::MessageDialog::new();
    match resolve_parent(None) {
        Some(w) => d.set_parent(&w),
        None => d,
    }
}

/// 诊断包里一份来自磁盘的文件。生成的那两份（info.json / report.json）不在这里。
#[derive(Debug, Clone)]
pub struct DiagEntry {
    /// 包里的路径。
    pub arc: String,
    /// 磁盘上的来源。
    pub path: PathBuf,
    /// 整份收，还是只收头尾。
    pub clipped: bool,
}

/// 诊断包会收哪些文件 —— 出包和「出包前给用户看清单」用的是同一个函数。
///
/// 两边各写一遍，迟早会分叉：预览说收 12 个，实际收 14 个，而用户是拿这个包去
/// 群里求助的，多出来的那两个他不知道。
pub fn diagnostics_manifest(root: &Path) -> Vec<DiagEntry> {
    let mut out = Vec::new();
    for (arc, path) in [
        ("configs/inuse/config.json", paths::inuse_config_path(root)),
        ("runtime_control/status.json", crate::protocol::status_path(root)),
    ] {
        if path.is_file() {
            out.push(DiagEntry { arc: arc.to_string(), path, clipped: false });
        }
    }
    let logs = paths::logs_dir(root);
    for p in logs_for_zip(&logs) {
        let rel = p
            .strip_prefix(&logs)
            .map(|r| r.to_string_lossy().replace('\\', "/"))
            .unwrap_or_else(|_| {
                p.file_name().unwrap_or_default().to_string_lossy().into_owned()
            });
        out.push(DiagEntry { arc: format!("logs/{rel}"), path: p, clipped: true });
    }
    if let Some(p) = newest_perf_report(root) {
        let name = p.file_name().unwrap_or_default().to_string_lossy().to_string();
        out.push(DiagEntry { arc: format!("perf/{name}"), path: p, clipped: false });
    }
    out
}

fn newest_perf_report(root: &Path) -> Option<PathBuf> {
    let dir = paths::user_data(root).join("perf_reports");
    let rd = std::fs::read_dir(dir).ok()?;
    let mut files: Vec<PathBuf> = rd
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().and_then(|x| x.to_str()) == Some("json"))
        .collect();
    files.sort();
    files.pop()
}

/// 日志头尾各留多少。收全份的话，一次警告刷屏就能把 start_vc 挤掉。
const LOG_HEAD: usize = 128 * 1024;
const LOG_TAIL: usize = 384 * 1024;

/// 一份条目最终进包的文本。预览按它算字节数，出包按它写内容。
fn diag_entry_text(e: &DiagEntry, redaction: Option<&(String, String)>) -> Option<String> {
    if !e.path.is_file() {
        return None;
    }
    let raw = if e.clipped {
        clip_log(&e.path, LOG_HEAD, LOG_TAIL)
    } else {
        std::fs::read_to_string(&e.path).ok()?
    };
    Some(redact_user(&raw, redaction))
}

/// 各个目录各占多少。
///
/// 一个训练实验的中间产物动辄三四个 GB，而用户完全看不见 —— 他只知道 C 盘满了，
/// 不知道是谁占的。异步跑：logs 下可能有好几万个文件。
pub fn storage_usage(root: &Path) -> Value {
    let ud = paths::user_data(root);
    let items = [
        ("logs", root.join("logs")),
        ("weights", root.join("assets").join("weights")),
        ("models", ud.join("models")),
        ("update_cache", paths::update_cache(root)),
        ("diagnostics", ud.join("diagnostics")),
        ("perf_reports", ud.join("perf_reports")),
        // 回收站要单列。删完音色磁盘占用短期不会下降，界面上不写出来的话，
        // 用户会觉得「我清理完反而更满了」。
        ("trash", crate::voices::trash_dir(root)),
        ("app_logs", paths::logs_dir(root)),
    ];
    let list: Vec<Value> = items
        .iter()
        .map(|(name, p)| json!({ "name": name, "bytes": dir_bytes(p) }))
        .collect();
    let total: u64 = list
        .iter()
        .filter_map(|v| v.get("bytes").and_then(|b| b.as_u64()))
        .sum();
    json!({
        "items": list,
        "total_bytes": total,
        "free_bytes": paths::free_space_bytes(root).map(Value::from).unwrap_or(Value::Null),
    })
}

fn dir_bytes(p: &Path) -> u64 {
    let Ok(meta) = std::fs::metadata(p) else {
        return 0;
    };
    if meta.is_file() {
        return meta.len();
    }
    let Ok(rd) = std::fs::read_dir(p) else {
        return 0;
    };
    rd.flatten().map(|e| dir_bytes(&e.path())).sum()
}

/// 一段可以直接粘进群里的环境信息。
///
/// 每一轮群聊问答都从同样三句开始：「你什么版本」「什么显卡」「什么后端」。
/// 用户答不上来不是他的错 —— 这些散在四个页面上。这里把它们凑成一段纯文本，
/// 按一下复制，问答就从第四句开始。
///
/// 出包一样能带这些信息，但发包对很多人来说太重了：他只是想在群里问一句。
///
/// 路径里的 Windows 用户名照样抹掉 —— 这段文字比诊断包更容易被贴到公开场合。
pub fn summary_text(root: &Path) -> String {
    let cfg = config::read(root);
    let st = worker::status_for_ui(root);
    let sv = |k: &str| st.get(k).and_then(|v| v.as_str()).unwrap_or("").to_string();
    let cv = |k: &str| cfg.get(k).and_then(|v| v.as_str()).unwrap_or("").to_string();
    let dash = crate::i18n::t("s.sumUnknown");
    let or_dash = |s: String| if s.trim().is_empty() { dash.clone() } else { s };

    let gpus = crate::provision::list_gpus();
    let backend = {
        let b = sv("compute_backend");
        let d = sv("compute_device");
        match (b.is_empty(), d.is_empty()) {
            (true, true) => dash.clone(),
            (false, false) => format!("{b} / {d}"),
            _ => format!("{b}{d}"),
        }
    };
    let main_gpu = match cfg.get("main_gpu").and_then(|v| v.as_i64()) {
        Some(i) if i >= 0 => i.to_string(),
        _ => crate::i18n::t("s.sumAuto"),
    };
    let audio = format!(
        "{} / {} → {}",
        or_dash(sv("sg_hostapi")),
        or_dash(sv("sg_input_device")),
        or_dash(sv("sg_output_device"))
    );
    let findings = crate::selfcheck::run(root);
    let findings_line = if findings.is_empty() {
        crate::i18n::t("s.diagFindingsNone")
    } else {
        findings
            .iter()
            .map(|f| format!("[{}] {}", f.level, f.title))
            .collect::<Vec<_>>()
            .join("\n  ")
    };

    let mut lines = vec![
        format!("RVC Fabric {}", crate::update::APP_VERSION),
        format!("{}: {} {}", crate::i18n::t("s.sumSystem"), std::env::consts::OS, std::env::consts::ARCH),
        format!(
            "{}: {}",
            crate::i18n::t("s.sumVariant"),
            or_dash(crate::provision::read_package_meta_variant(root).unwrap_or_default())
        ),
        format!(
            "{}: {}",
            crate::i18n::t("s.sumGpu"),
            if gpus.is_empty() { dash.clone() } else { gpus.join(" / ") }
        ),
        format!("{}: {}", crate::i18n::t("s.sumBackend"), backend),
        format!("{}: {}", crate::i18n::t("s.sumMainGpu"), main_gpu),
        format!("{}: {}", crate::i18n::t("s.sumAudio"), audio),
        format!(
            "{}: {}",
            crate::i18n::t("s.sumRuntime"),
            crate::i18n::t(if paths::runtime_ready(root) { "s.sumYes" } else { "s.sumNo" })
        ),
        format!("{}: {}", crate::i18n::t("s.sumVoice"), or_dash(cv("last_model_name"))),
    ];
    let err = sv("error");
    if !err.trim().is_empty() {
        lines.push(format!("{}: {}", crate::i18n::t("s.sumLastError"), err.trim()));
    }
    lines.push(format!("{}:\n  {}", crate::i18n::t("s.sumFindings"), findings_line));

    let text = lines.join("\n");
    let redaction = home_redaction();
    redact_user(&text, redaction.as_ref())
}

/// 出包之前给用户看的清单：包里会有哪些文件、各自多大。
///
/// 用户要把这个包发到群里。「里面只有日志和配置」是一句承诺，清单是这句承诺的
/// 凭据 —— 说得再好听，不如让他自己看一眼。
pub fn diagnostics_preview(root: &Path) -> Value {
    let redaction = home_redaction();
    let redaction = redaction.as_ref();
    let mut items: Vec<Value> = vec![json!({"name": "info.json", "bytes": Value::Null})];
    let mut total: u64 = 0;
    for e in diagnostics_manifest(root) {
        let bytes = diag_entry_text(&e, redaction)
            .map(|t| t.len() as u64)
            .unwrap_or(0);
        total += bytes;
        items.push(json!({"name": e.arc, "bytes": bytes}));
    }
    json!({"items": items, "total_bytes": total})
}

/// Zip logs + machine info + effective settings into `User_Data/diagnostics/`.
///
/// `with_perf`：用户确认后才跑 bench。Log tails 有上限，避免几百 MB 的废包。
/// `report`：用户自己填的昵称 / QQ / 问题描述，落成 `report.json`。
///
/// 出包前所有文本都过一遍 `redact_user`：日志和配置里到处是绝对路径，而
/// Windows 用户名常常就是真名。用户是拿这个包去群里求助的，不该顺带把这个
/// 也交出去。
/// 返回 (zip 路径, 性能测试说明)。
pub fn build_diagnostics(
    root: &Path,
    with_perf: bool,
    report: &UserReport,
) -> Result<(PathBuf, String), String> {
    let perf_note = if with_perf {
        match run_perf_bench(root) {
            Ok(p) => crate::i18n::te("s.37f36c5824", &p.file_name().unwrap_or_default().to_string_lossy()),
            Err(e) => {
                crate::logging::shell_log!("perf bench failed: {e}");
                crate::i18n::te("s.eea9655c7b", &(e))
            }
        }
    } else {
        crate::i18n::t("s.733f7e7b3f")
    };

    let out_dir = paths::user_data(root).join("diagnostics");
    std::fs::create_dir_all(&out_dir).map_err(|e| e.to_string())?;
    let stamp = now_stamp();
    let out = out_dir.join(format!("diag_{stamp}.zip"));

    let file = std::fs::File::create(&out).map_err(|e| e.to_string())?;
    let mut zip = zip::ZipWriter::new(file);
    let opts: zip::write::FileOptions<'_, ()> =
        zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated);

    let redaction = home_redaction();
    let redaction = redaction.as_ref();

    // 用户自己填的那几行排在最前面：支援打开包第一眼就该看到「谁、什么问题」，
    // 而不是先去翻三十个日志文件猜。
    if !report.is_empty() {
        zip_text(
            &mut zip,
            opts,
            "report.json",
            &serde_json::to_string_pretty(&report.sanitized()).unwrap_or_default(),
        )?;
    }

    let cfg = config::read(root);
    // machine + app info
    let info = json!({
        "app_version": crate::update::APP_VERSION,
        "os": std::env::consts::OS,
        "arch": std::env::consts::ARCH,
        "product_root": root.to_string_lossy(),
        "runtime_ready": paths::runtime_ready(root),
        "gpus": crate::provision::list_gpus(),
        // 「主显卡」那个下标是按这份列表数的。少了它，配置里的 main_gpu 是个孤零零
        // 的数字，没法判断用户选中的到底是哪块卡、还是根本越界了。
        "nvidia_gpus": crate::provision::list_nvidia_gpus(),
        "installed_variant": crate::provision::read_package_meta_variant(root),
        "engine_core_missing": crate::engine_assets::engine_core_missing(root),
        "ui_source": crate::ui_assets::source_label(),
        "worker_alive": worker::is_worker_alive(root),
        "status": worker::status_for_ui(root),
        "config": Value::Object(cfg.clone()),
        "delay_estimate": delay_estimate(&cfg),
        "log_inventory": crate::logging::inventory(root),
        "tools": {
            "sts": crate::sts::status(root),
            "tts": {
                "runtime_ready": paths::runtime_ready(root),
                "model_path": cfg.get("pth_path").and_then(|v| v.as_str()).unwrap_or(""),
            },
            "separate": crate::separate::status(root),
            "train": crate::train::status(root),
        },
        "perf_note": perf_note,
        // 包里已经能看出来的问题，跟着包一起走。支援打开 info.json 第一眼就
        // 看到结论，不用先翻三十个日志文件。
        "findings": crate::selfcheck::run(root),
        "generated_at": stamp,
    });
    zip_text(
        &mut zip,
        opts,
        "info.json",
        &redact_user(
            &serde_json::to_string_pretty(&info).unwrap_or_default(),
            redaction,
        ),
    )?;

    // 用户粘进来的截图。放在 report.json 旁边 —— 支援打开包先看这两样。
    for (i, shot) in report.shots.iter().take(MAX_SHOTS).enumerate() {
        let Some(bytes) = base64_decode(&shot.data) else {
            crate::logging::shell_log!("诊断包：第 {} 张截图解码失败，已跳过", i + 1);
            continue;
        };
        if bytes.is_empty() || bytes.len() > MAX_SHOT_BYTES {
            crate::logging::shell_log!(
                "诊断包：第 {} 张截图 {} 字节，超出上限，已跳过",
                i + 1,
                bytes.len()
            );
            continue;
        }
        let ext = if shot.ext.eq_ignore_ascii_case("jpg") || shot.ext.eq_ignore_ascii_case("jpeg") {
            "jpg"
        } else {
            "png"
        };
        zip.start_file(format!("shots/{:02}.{ext}", i + 1), opts)
            .map_err(|e| e.to_string())?;
        zip.write_all(&bytes).map_err(|e| e.to_string())?;
    }

    // 配置、状态、日志、性能报告都走同一份清单 —— 出包前给用户看的预览用的
    // 也是它，两边各写一遍迟早会分叉。日志只收头尾，一次警告刷屏挤不掉 start_vc。
    for e in diagnostics_manifest(root) {
        if let Some(text) = diag_entry_text(&e, redaction) {
            zip_text(&mut zip, opts, &e.arc, &text)?;
        }
    }

    zip.finish().map_err(|e| e.to_string())?;
    Ok((out, perf_note))
}

// ---------------------------------------------------------------------------
// Consult pack (申请专业优化)
// ---------------------------------------------------------------------------

/// Bundle the current voice's config + profiles + environment so tuning can be
/// done off-machine. The model weights are large and are **not** included
/// unless the user explicitly asks — that is a separate, deliberate step.
pub fn build_consult_pack(root: &Path, note: &str) -> Result<PathBuf, String> {
    let out_dir = paths::user_data(root).join("consult_packs");
    std::fs::create_dir_all(&out_dir).map_err(|e| e.to_string())?;
    let stamp = now_stamp();
    let out = out_dir.join(format!("consult_{stamp}.zip"));

    let cfg = config::read(root);
    let pth = cfg.get("pth_path").and_then(|v| v.as_str()).unwrap_or("");
    let model_dir = if pth.is_empty() {
        None
    } else {
        Path::new(pth).parent().map(|p| p.to_path_buf())
    };

    let file = std::fs::File::create(&out).map_err(|e| e.to_string())?;
    let mut zip = zip::ZipWriter::new(file);
    let opts: zip::write::FileOptions<'_, ()> =
        zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated);

    let meta = json!({
        "app_version": crate::update::APP_VERSION,
        "note": note,
        "gpus": crate::provision::list_gpus(),
        "installed_variant": crate::provision::read_package_meta_variant(root),
        "config": Value::Object(cfg.clone()),
        "generated_at": stamp,
    });
    zip.start_file("consult.json", opts).map_err(|e| e.to_string())?;
    zip.write_all(serde_json::to_string_pretty(&meta).unwrap_or_default().as_bytes())
        .map_err(|e| e.to_string())?;

    // The voice's own config.json and any .tmvp profiles — small text files.
    if let Some(dir) = model_dir {
        for entry in std::fs::read_dir(&dir).into_iter().flatten().flatten() {
            let p = entry.path();
            let ext = p.extension().and_then(|x| x.to_str()).unwrap_or("");
            if ext == "json" || ext == "tmvp" {
                if let Ok(text) = std::fs::read_to_string(&p) {
                    let name = p.file_name().unwrap_or_default().to_string_lossy().to_string();
                    zip.start_file(format!("voice/{name}"), opts)
                        .map_err(|e| e.to_string())?;
                    zip.write_all(text.as_bytes()).map_err(|e| e.to_string())?;
                }
            }
        }
    }

    zip.finish().map_err(|e| e.to_string())?;
    Ok(out)
}

/// `YYYYMMDD_HHMMSS` in local time — same shape as the Python shell's
/// `diag_20260727_151048`. Support staff read these filenames; a unix epoch
/// integer tells them nothing.
fn now_stamp() -> String {
    chrono::Local::now().format("%Y%m%d_%H%M%S").to_string()
}

/// Reveal a file in the OS file manager.
pub fn reveal(path: &Path) -> Result<(), String> {
    let dir = path.parent().unwrap_or(path);
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("explorer")
            .arg(dir)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(dir)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(all(not(target_os = "windows"), not(target_os = "macos")))]
    {
        let _ = dir;
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Window close behaviour
// ---------------------------------------------------------------------------

/// Apply the saved `close_action` when the user closes the window.
///
/// * `tray` — hide, keep converting. That is the point of having a tray.
/// * `exit` — stop the stream, then quit.
/// * `ask`  — hand it to the UI, which offers the same two choices plus
///            「记住我的选择」, like the Tk shell.
pub fn install_close_handler(app: &AppHandle) {
    let Some(win) = app.get_webview_window("main") else {
        return;
    };
    let handle = app.clone();
    let w = win.clone();
    win.on_window_event(move |event| {
        // 尺寸变了：Win10 重裁圆角区域；最大化状态只跟区域，尺寸由子类化落地前钳好。
        if matches!(
            event,
            tauri::WindowEvent::Resized(_) | tauri::WindowEvent::ScaleFactorChanged { .. }
        ) {
            crate::window_watch::refresh_corners(&w);
        }
        let tauri::WindowEvent::CloseRequested { api, .. } = event else {
            return;
        };
        let action = root_of(&handle)
            .map(|r| {
                config::read(&r)
                    .get("close_action")
                    .and_then(|v| v.as_str())
                    .unwrap_or("ask")
                    .to_string()
            })
            .unwrap_or_else(|| "ask".into());

        match action.as_str() {
            "exit" => {
                // 同 finish_close：stop_vc 要等几秒，先把窗口收掉再等，
                // 别让用户对着一个不响应的窗口数秒。
                for win in handle.webview_windows().into_values() {
                    let _ = win.hide();
                }
                if let Some(root) = root_of(&handle) {
                    let _ = worker::stop_vc(&root, true);
                }
            }
            "tray" => {
                api.prevent_close();
                let _ = w.hide();
            }
            _ => {
                // If the UI is wedged it can never answer, and the user would
                // be unable to close the window at all. Second attempt within
                // 10s falls back to a plain exit.
                api.prevent_close();
                let now = std::time::Instant::now();
                let mut last = LAST_ASK.lock().unwrap_or_else(|e| e.into_inner());
                let stuck = last
                    .map(|t: std::time::Instant| now.duration_since(t).as_secs() < 10)
                    .unwrap_or(false);
                *last = Some(now);
                drop(last);
                if stuck {
                    if let Some(root) = root_of(&handle) {
                        let _ = worker::stop_vc(&root, true);
                    }
                    handle.exit(0);
                    return;
                }
                let _ = handle.emit("app://close-requested", ());
            }
        }
    });
}

/// Called by the UI once the user answered the close prompt.
pub fn finish_close(app: &AppHandle, to_tray: bool) {
    // 答过了就说明界面是活的，「点两次 X 强退」那条兜底该重新计时。
    clear_close_ask();
    if to_tray {
        if let Some(w) = app.get_webview_window("main") {
            let _ = w.hide();
        }
        return;
    }
    // 先把所有窗口收掉，再做收尾。
    //
    // 收尾要停 worker（最多等 3 秒）再清 TEMP，全在主线程上跑。以前是先收尾
    // 后退出，那几秒里窗口还杵在屏幕上、还不响应 —— 用户报的「关软件会卡顿
    // 一下再关闭」就是这段。hide 走的是 ShowWindow，不用等消息循环，喊完立刻
    // 就没了；后面的活照做，只是用户不用盯着一个死窗口等。
    for w in app.webview_windows().into_values() {
        let _ = w.hide();
    }
    if let Some(root) = root_of(app) {
        let _ = worker::stop_vc(&root, true);
        // 退出前清 TEMP：先停 worker 再删，避免文件被占用删不掉。
        let stats = crate::paths::clean_temps(&root);
        crate::paths::log_clean_stats(&crate::i18n::t("s.c5fcd5c0a9"), &root, &stats);
    }
    app.exit(0);
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 这段文字是给用户贴到群里的，所以两件事必须成立：该有的字段一个不少，
    /// 以及路径里的 Windows 用户名不能跟着出去 —— 它比诊断包更容易被贴到公开
    /// 场合，而发的时候没人会先读一遍。
    #[test]
    fn the_summary_carries_the_fields_support_always_has_to_ask_for() {
        // 断言的是 zh-CN 的字段标签。别的测试（如 i18n 的语言遍历）会在并行
        // 时把全局语言切来切去，必须先把自己的语言钉住，否则标签对不上。
        let _locale = crate::i18n::testing::pin("zh-CN");
        let root = crate::testutil::scratch("summary-text");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();

        let text = summary_text(&root);
        assert!(text.contains(crate::update::APP_VERSION), "少了版本号：{text}");
        for key in ["s.sumSystem", "s.sumGpu", "s.sumBackend", "s.sumMainGpu", "s.sumAudio"] {
            let label = crate::i18n::t(key);
            assert!(text.contains(&label), "少了「{label}」：{text}");
        }
        // 没配过的字段要写「未知」，不能留一个空冒号让人以为是我们漏了。
        assert!(text.contains(&crate::i18n::t("s.sumUnknown")));
        // main_gpu 没设时是「自动」，不是 -1 —— 用户看不懂 -1。
        assert!(text.contains(&crate::i18n::t("s.sumAuto")));

        if let Some(home) = std::env::var("HOME").ok().or_else(|| std::env::var("USERPROFILE").ok()) {
            let home = home.trim_end_matches(['/', '\\']);
            if home.len() >= 4 {
                assert!(!text.contains(home), "用户目录漏出去了：{text}");
            }
        }

        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn base64_round_trips_the_bytes_a_png_would_carry() {
        // 标准表 + 两种补位长度。
        assert_eq!(base64_decode("").unwrap(), b"");
        assert_eq!(base64_decode("QQ==").unwrap(), b"A");
        assert_eq!(base64_decode("QUI=").unwrap(), b"AB");
        assert_eq!(base64_decode("QUJD").unwrap(), b"ABC");
        // PNG 的头八个字节，粘贴板里来的图就长这样。
        let png = base64_decode("iVBORw0KGgo=").unwrap();
        assert_eq!(png, [0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A]);
        // 前端拼出来的串可能带换行，不能因此整张图丢掉。
        assert_eq!(base64_decode("QUJD\n").unwrap(), b"ABC");
        assert_eq!(base64_decode("QU\r\nJD").unwrap(), b"ABC");
        // 认不出来的字符宁可整张跳过，也不要写半张坏图进包。
        assert!(base64_decode("QU*D").is_none());
    }

    /// 图不进 report.json —— 那份是给人读的，塞几兆 base64 进去就没法读了。
    #[test]
    fn the_report_json_records_how_many_shots_but_not_the_images() {
        let r = UserReport {
            nickname: "柠檬酸".into(),
            qq: "12345".into(),
            description: "无法使用".into(),
            shots: vec![
                Shot { ext: "png".into(), data: "QUJD".into() },
                Shot { ext: "jpg".into(), data: "QUJD".into() },
            ],
        };
        let v = r.sanitized();
        assert_eq!(v["shots"].as_u64(), Some(2));
        let text = serde_json::to_string(&v).unwrap();
        assert!(!text.contains("QUJD"), "base64 不该出现在 report.json 里：{text}");
    }

    /// 只填了图、三个字段都空着，也得出包 —— 那张图本身就是全部信息。
    #[test]
    fn a_report_with_only_a_screenshot_is_not_empty() {
        let r = UserReport {
            shots: vec![Shot { ext: "png".into(), data: "QUJD".into() }],
            ..Default::default()
        };
        assert!(!r.is_empty());
        assert!(UserReport::default().is_empty());
    }

    /// 预览和出包必须走同一份清单。
    ///
    /// 两边各写一遍迟早分叉：预览说收 12 个、实际收 14 个，而用户是拿这个包去
    /// 群里求助的，多出来的那两个他不知道。这条测试盯的就是那份清单本身。
    #[test]
    fn the_preview_lists_exactly_what_the_bundle_will_contain() {
        // 同 summary：info.json 的生成文案走 i18n，先钉住语言。
        let _locale = crate::i18n::testing::pin("zh-CN");
        let root = crate::testutil::scratch("diag-manifest");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("configs").join("inuse")).unwrap();
        std::fs::write(
            root.join("configs").join("inuse").join("config.json"),
            "{\"pitch\": 0}",
        )
        .unwrap();
        let logs = root.join("User_Data").join("logs").join("shell");
        std::fs::create_dir_all(&logs).unwrap();
        std::fs::write(logs.join("2026-08-21.log"), "启动\n").unwrap();

        let manifest = diagnostics_manifest(&root);
        let arcs: Vec<&str> = manifest.iter().map(|e| e.arc.as_str()).collect();
        assert!(arcs.contains(&"configs/inuse/config.json"), "{arcs:?}");
        assert!(arcs.contains(&"logs/shell/2026-08-21.log"), "{arcs:?}");
        // 不存在的文件不进清单 —— 预览里列一个包里没有的名字是在骗人。
        assert!(!arcs.iter().any(|a| a.starts_with("perf/")), "{arcs:?}");
        assert!(
            !arcs.contains(&"runtime_control/status.json"),
            "这个 root 下根本没有 status.json：{arcs:?}"
        );

        let preview = diagnostics_preview(&root);
        let items = preview.get("items").and_then(|v| v.as_array()).unwrap();
        // 预览多一条 info.json —— 那份是出包时现生成的，不在磁盘清单里。
        assert_eq!(items.len(), manifest.len() + 1);
        assert_eq!(items[0].get("name").unwrap(), "info.json");
        assert!(items[0].get("bytes").unwrap().is_null());
        // 日志是收头尾的，报出来的必须是进包之后的字节数，不是磁盘上的。
        let total = preview.get("total_bytes").and_then(|v| v.as_u64()).unwrap();
        assert!(total > 0);

        let _ = std::fs::remove_dir_all(&root);
    }

    /// 旧 Python 壳那四个的默认组合和顺序不许动 —— 用户有肌肉记忆。
    ///
    /// 后面新加的不在这条约束里（所以这里比的是前四个，不是整张表），但
    /// 新加的也不许挤到前面去，否则等于把老用户的键改了。
    #[test]
    fn the_windows_username_is_stripped_from_every_path_form() {
        // 同一个路径在 info.json、config.json 和日志里长得不一样：
        // 反斜杠、正斜杠、以及 JSON 转义过的双反斜杠。三种都要认。
        let r = Some(("C:\\Users\\张三".to_string(), "<用户目录>".to_string()));
        let r = r.as_ref();
        assert_eq!(
            redact_user("root=C:\\Users\\张三\\RVC", r),
            "root=<用户目录>\\RVC"
        );
        assert_eq!(
            redact_user("\"root\": \"C:/Users/张三/RVC\"", r),
            "\"root\": \"<用户目录>/RVC\""
        );
        assert_eq!(
            redact_user("\"p\": \"C:\\\\Users\\\\张三\\\\a.pth\"", r),
            "\"p\": \"<用户目录>\\\\a.pth\""
        );
    }

    #[test]
    fn redaction_is_case_insensitive_like_windows_paths() {
        // 同一次运行里 c:\users\… 和 C:\Users\… 都会出现，取决于哪个 API 写的。
        let r = Some(("C:\\Users\\Bob".to_string(), "<用户目录>".to_string()));
        assert_eq!(
            redact_user("open c:\\users\\bob\\x.log failed", r.as_ref()),
            "open <用户目录>\\x.log failed"
        );
    }

    #[test]
    fn without_a_home_path_the_text_is_left_alone() {
        // 抹不掉就原样交出去，不去猜「哪个词像人名」—— 猜错等于把日志改坏，
        // 排障的人拿到的是一份被污染的证据。
        let text = "root=D:\\RVC-Fabric";
        assert_eq!(redact_user(text, None), text);
    }

    #[test]
    fn the_user_report_is_trimmed_and_capped() {
        let r = UserReport {
            nickname: "  老王  ".into(),
            qq: " 12345678 ".into(),
            description: "啊".repeat(5000),
            ..Default::default()
        };
        let v = r.sanitized();
        assert_eq!(v["nickname"], json!("老王"));
        assert_eq!(v["qq"], json!("12345678"));
        // 4000 字 + 一个省略号，防手滑粘贴一整本小说把包撑大。
        assert_eq!(v["description"].as_str().unwrap().chars().count(), 4001);
    }

    #[test]
    fn an_untouched_form_counts_as_empty() {
        // 三个都没填就不写 report.json，别在包里塞一个全空的文件。
        assert!(UserReport::default().is_empty());
        assert!(UserReport { qq: "   ".into(), ..Default::default() }.is_empty());
        assert!(!UserReport { qq: "42".into(), ..Default::default() }.is_empty());
    }

    #[test]
    fn the_original_four_hotkeys_keep_their_combos() {
        let combos: Vec<&str> = HOTKEYS.iter().take(4).map(|(_, _, d)| *d).collect();
        assert_eq!(
            combos,
            vec!["CmdOrCtrl+F2", "CmdOrCtrl+F3", "CmdOrCtrl+F5", "CmdOrCtrl+F6"]
        );
        let actions: Vec<&str> = HOTKEYS.iter().take(4).map(|(_, a, _)| *a).collect();
        assert_eq!(
            actions,
            vec!["toggle-vc", "toggle-mode", "prev-voice", "next-voice"]
        );
    }

    /// 配置里存的组合键要先筛一道再交给系统注册。
    #[test]
    fn combo_shapes_are_checked() {
        assert!(combo_ok("CmdOrCtrl+F2"));
        assert!(combo_ok("Alt+Shift+K"));
        assert!(combo_ok("F9"));
        assert!(!combo_ok(""));
        assert!(!combo_ok("Ctrl+"));
        assert!(!combo_ok("Ctrl++A"));
        assert!(!combo_ok("Ctrl+A+B+C+D+E"));
        assert!(!combo_ok("Ctrl+<script>"));
        assert!(!combo_ok(&"A".repeat(60)));
    }

    /// 配置里是垃圾值时必须退回默认，而不是注册一个乱七八糟的组合。
    #[test]
    fn bad_config_falls_back_to_default() {
        assert_eq!(combo_for(None, "hotkey_toggle_vc", "CmdOrCtrl+F2"), "CmdOrCtrl+F2");
    }

    #[test]
    fn log_tail_is_capped() {
        let p = crate::testutil::scratch("tail-test-log");
        std::fs::write(&p, "x".repeat(50_000)).unwrap();
        assert_eq!(tail_bytes(&p, 1000).len(), 1000);
        let _ = std::fs::remove_file(&p);
    }

    #[test]
    fn clip_log_keeps_head_and_tail() {
        let p = crate::testutil::scratch("clip-test-log");
        let mut body = String::from("HEAD-LINE\n");
        body.push_str(&"m".repeat(20_000));
        body.push_str("\nTAIL-LINE\n");
        std::fs::write(&p, &body).unwrap();
        let clipped = clip_log(&p, 32, 32);
        assert!(clipped.contains("HEAD-LINE"), "{clipped}");
        assert!(clipped.contains("TAIL-LINE"), "{clipped}");
        assert!(clipped.contains("truncated"), "{clipped}");
        let small = clip_log(&p, 100_000, 100_000);
        assert!(!small.contains("truncated"));
        let _ = std::fs::remove_file(&p);
    }

    /// 快捷键的默认组合有三份拷贝：这里的 HOTKEYS、config::defaults()、
    /// 以及设置页 SettingsPage.tsx 的 HOTKEYS 数组。前两份能在这里对上，
    /// 第三份只能靠注释。
    ///
    /// 对不上的后果很隐蔽：设置页显示 F7，实际注册的是别的键，用户按着没反应
    /// 又看不出哪里错了。
    #[test]
    fn hotkey_defaults_match_the_config_defaults() {
        // 语言是进程级全局状态，cargo 默认多线程跑测试。不钉住的话，
        // 断言里两次取文案可能落在不同语言上（实测到过法语 vs 韩语）。
        let _g = crate::i18n::testing::pin("zh-CN");
        let d = crate::config::defaults();
        for (key, _action, default) in HOTKEYS {
            let got = d
                .get(*key)
                .and_then(|v| v.as_str())
                .unwrap_or_else(|| panic!("{}", crate::i18n::t("s.e64959c277")));
            assert_eq!(got, *default);
        }
    }

    /// 每个快捷键都要有自己的 `_global` 开关，而且默认必须是 true。
    ///
    /// 默认值写错成 false 是个静默事故：九个快捷键一夜之间全变成「只在软件内
    /// 生效」，用户在游戏里按 Ctrl+F2 没反应，而界面上什么错都不会报。
    #[test]
    fn every_hotkey_has_a_global_switch_defaulting_to_on() {
        // 语言是进程级全局状态，cargo 默认多线程跑测试。不钉住的话，
        // 断言里两次取文案可能落在不同语言上（实测到过法语 vs 韩语）。
        let _g = crate::i18n::testing::pin("zh-CN");
        let d = crate::config::defaults();
        for (key, _action, _default) in HOTKEYS {
            let k = format!("{key}_global");
            let got = d
                .get(&k)
                .and_then(|v| v.as_bool())
                .unwrap_or_else(|| panic!("{}", crate::i18n::t("s.735eb4e9fd")));
            assert!(got);
        }
    }

    /// 组合键必须过得了自己的校验。写错一个字符（比如 "Ctrl+F7" 而不是
    /// "CmdOrCtrl+F7"）会被 combo_for 当成非法值悄悄换成 fallback ——
    /// 而 fallback 就是它自己，于是永远注册不上，也没人报错。
    #[test]
    fn every_default_combo_is_well_formed() {
        for (key, _action, default) in HOTKEYS {
            assert!(combo_ok(default));
        }
    }

    /// 动作名不能撞：撞了就是两个快捷键触发同一件事，另一件永远做不了。
    #[test]
    fn hotkey_keys_and_actions_are_unique() {
        let mut keys: Vec<&str> = HOTKEYS.iter().map(|h| h.0).collect();
        let n = keys.len();
        keys.sort_unstable();
        keys.dedup();
        assert_eq!(keys.len(), n);

        let mut acts: Vec<&str> = HOTKEYS.iter().map(|h| h.1).collect();
        acts.sort_unstable();
        acts.dedup();
        assert_eq!(acts.len(), n);
    }
}
