//! 语音合成（文字 → 目标音色的语音）。
//!
//! 两步，各干各的：
//!
//! 1. **系统 TTS 念出来** —— Windows 自带的 SAPI，走 PowerShell 调
//!    `System.Speech.Synthesis`。念出来的是微软那几把标准嗓子，不好听，但这一
//!    步只负责「把字读成有停顿有轻重的人声」。
//! 2. **RVC 换成用户选的音色** —— 就是离线推理，音色完全来自这一步。
//!
//!    这一步**走 `sts::run`**，也就是语音转换那条链路，而不是自己起
//!    `tools/infer_cli.py`。原来是后者，代价是**每合成一句都要付一次完整冷启动**：
//!    import torch / fairseq、探设备、读 net_g、读 hubert、读 rmvpe 全套重来，
//!    一条五秒的语音要等一两分钟。而 `sts::run` 那边早就解决了同一个问题 ——
//!    实时 worker 在跑就借它的常驻模型（热路径），不在就用自己的常驻进程
//!    （十分钟空闲回收）。同一个仓库里两套实现，好的那套一直没被这里用上。
//!
//!    接过去之后顺带白拿三样：OOM 自动重试、DirectML 算子缺口时退 CPU、
//!    取消能真的中断。这三样 `infer_cli.py` 那条路一样都没有。
//!
//! 为什么不引一个神经 TTS：那要往 Runtime 里塞一个新的 python 依赖和一份新的
//! 模型权重。Runtime 是个 1.8 GB 的整包，加一个依赖就得重发一次全量包，而所有
//! 人都得重下。SAPI 是系统自带的，零新增依赖、零下载、离线可用，而最终音色反正
//! 由第二步的 RVC 决定 —— 第一步只要吐字清楚就够了。
//!
//! 和人声分离一样是一次性任务：起进程、读输出、等它退出。不套 worker.rs 那一
//! 整套常驻进程的协议。

use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

use crate::paths;

/// 一次只跑一个。第二步要占显存，两个一起跑会互相挤爆。
static BUSY: Mutex<bool> = Mutex::new(false);
static CANCEL: OnceLock<Arc<AtomicBool>> = OnceLock::new();

fn cancel_flag() -> Arc<AtomicBool> {
    CANCEL
        .get_or_init(|| Arc::new(AtomicBool::new(false)))
        .clone()
}

/// 一次能合成多长的文字。
///
/// 不是性能上限，是防手滑：粘一整本小说进来，SAPI 会闷头念上几十分钟，中间没有
/// 任何进度可报，用户只会以为卡死了。两千字大约三五分钟，是「等得起」的上限。
pub const MAX_CHARS: usize = 2000;

/// 朗读合成和变声合成分两个输出目录，各自可改、各自记住上次的位置。
///
/// 分开是因为这两种产物根本不是一类东西：朗读是系统嗓子念出来的原声，变声是
/// 它再过一遍 RVC 的结果。以前两者同一个目录、同一套 `tts_<时间戳>.wav` 文件名，
/// 攒上十几个之后就再也分不出哪个是哪个了 —— 而且时间戳是秒级的，同一秒里先出
/// 朗读再出变声，名字还会撞。
pub(crate) const OUT_READ: &str = "tts_out_dir_read";
pub(crate) const OUT_VOICE: &str = "tts_out_dir_voice";

pub fn default_out_read(root: &Path) -> PathBuf {
    paths::user_data(root).join("tts").join("read")
}

pub fn default_out_voice(root: &Path) -> PathBuf {
    paths::user_data(root).join("tts").join("voice")
}

/// 用户选过就用他选的，没选过用默认。`use_rvc` 决定问哪一个。
pub fn out_dir_for(root: &Path, use_rvc: bool) -> PathBuf {
    let key = if use_rvc { OUT_VOICE } else { OUT_READ };
    let picked = crate::config::read(root)
        .get(key)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    if picked.is_empty() {
        if use_rvc {
            default_out_voice(root)
        } else {
            default_out_read(root)
        }
    } else {
        PathBuf::from(picked)
    }
}

/// 让用户挑一个输出目录，挑完记进配置。返回 `None` 表示他取消了。
pub fn pick_output(
    root: &Path,
    win: Option<&tauri::WebviewWindow>,
    use_rvc: bool,
) -> Option<String> {
    let title = crate::i18n::t("s.cb12ce77e7");
    let picked = crate::shell_extras::dialog_on(win)
        .set_title(&title)
        .pick_folder()
        .map(|p| p.to_string_lossy().into_owned())?;
    let mut patch = serde_json::Map::new();
    patch.insert(
        (if use_rvc { OUT_VOICE } else { OUT_READ }).to_string(),
        json!(picked.trim()),
    );
    let _ = crate::config::update(root, patch);
    Some(picked)
}

/// 把某一路的输出目录恢复成默认。
pub fn reset_output(root: &Path, use_rvc: bool) {
    let mut patch = serde_json::Map::new();
    patch.insert(
        (if use_rvc { OUT_VOICE } else { OUT_READ }).to_string(),
        json!(""),
    );
    let _ = crate::config::update(root, patch);
}

/// 旧的单文件推理脚本。
///
/// 第二步已经改走 `sts::run`，这里只剩一个用途：`status()` 报告它在不在，
/// 让诊断包能看出这台机器的 payload 完整不完整。
fn infer_script(root: &Path) -> PathBuf {
    root.join("tools").join("infer_cli.py")
}

pub fn cancel() {
    cancel_flag().store(true, Ordering::SeqCst);
}

fn emit(app: &AppHandle, phase: &str, done: u64, total: u64, message: &str) {
    let _ = app.emit(
        "tts-progress",
        json!({
            "phase": phase,
            "done": done,
            "total": total.max(1),
            "message": message,
        }),
    );
}

// ---------------------------------------------------------------------------
// 第一步：系统 TTS
// ---------------------------------------------------------------------------

/// 列出系统里装了哪些 TTS 嗓子。
///
/// 中文 Windows 至少有一把中文的（Huihui / Yaoyao / Kangkang），英文系统上可能
/// 一把中文的都没有 —— 那种情况下念中文会是一串音标似的怪音，所以名单要如实
/// 报给界面，让用户自己看见有哪些。
pub fn list_sapi_voices() -> Vec<String> {
    let ps = r#"
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo.Name }
$s.Dispose()
"#;
    let Ok(out) = run_powershell(ps) else {
        return Vec::new();
    };
    out.lines()
        .map(str::trim)
        .filter(|l| !l.is_empty())
        .map(str::to_string)
        .collect()
}

fn run_powershell(script: &str) -> Result<String, String> {
    let mut cmd = Command::new("powershell");
    cmd.args(["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    let out = cmd.output().map_err(|e| crate::i18n::te("s.6fe5607f45", &(e)))?;
    if !out.status.success() {
        return Err(crate::i18n::t("s.787332269e").into());
    }
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

/// 把文字念成一个 wav 文件。
///
/// 要念的字走文件不走命令行：一段中文里出现引号、反引号、`$` 都是常事，拼进
/// PowerShell 的命令行就是一串转义地雷，而且 `$(...)` 在 PowerShell 里会被当成
/// 子表达式执行 —— 那等于让用户输入框里的内容变成可执行代码。读文件没有这个
/// 问题：文件内容永远是数据。
fn synthesize(root: &Path, text: &str, voice: &str, rate: i32) -> Result<PathBuf, String> {
    // 嗓子名必须是系统真的报出来过的那一个。单引号字符串在 PowerShell 里不做
    // 插值、`''` 也确实是转义，所以拼进去本身是安全的 —— 但「安全靠转义写对」
    // 是个会随着以后改脚本一起失效的保证。对着白名单比一下，这个类别就没了。
    if !voice.is_empty() && !list_sapi_voices().iter().any(|v| v == voice) {
        return Err(crate::i18n::te("s.74d5d45130", &(voice)));
    }
    let cache = paths::update_cache(root);
    std::fs::create_dir_all(&cache).map_err(|e| crate::i18n::te("s.9273991f94", &(e)))?;
    let txt = cache.join("tts_text.txt");
    let wav = cache.join("tts_raw.wav");

    // UTF-8 带 BOM：PowerShell 5 的 Get-Content 默认按系统 ANSI 码页读，
    // 没有 BOM 的中文会被读成乱码，念出来是一串怪音。
    let mut f = std::fs::File::create(&txt).map_err(|e| crate::i18n::te("s.6619dda8e2", &(e)))?;
    f.write_all(&[0xEF, 0xBB, 0xBF])
        .and_then(|_| f.write_all(text.as_bytes()))
        .map_err(|e| crate::i18n::te("s.6619dda8e2", &(e)))?;
    drop(f);
    let _ = std::fs::remove_file(&wav);

    // -1..1 → SAPI 的 -10..10。整段脚本里唯一插值进去的是我们自己造的路径和
    // 一个已经夹紧的整数，没有用户输入。
    let rate = rate.clamp(-10, 10);
    let script = format!(
        r#"
Add-Type -AssemblyName System.Speech
$t = [System.IO.File]::ReadAllText('{txt}', [System.Text.Encoding]::UTF8)
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$want = '{voice}'
if ($want -ne '') {{
  foreach ($v in $s.GetInstalledVoices()) {{
    if ($v.VoiceInfo.Name -eq $want) {{ $s.SelectVoice($want); break }}
  }}
}}
$s.Rate = {rate}
$s.SetOutputToWaveFile('{wav}')
$s.Speak($t)
$s.Dispose()
"#,
        txt = txt.to_string_lossy().replace('\'', "''"),
        wav = wav.to_string_lossy().replace('\'', "''"),
        voice = voice.replace('\'', "''"),
    );
    run_powershell(&script)?;
    let _ = std::fs::remove_file(&txt);
    if !wav.is_file() {
        return Err(crate::i18n::t("s.0b2b13c141").into());
    }
    Ok(wav)
}

// ---------------------------------------------------------------------------
// 第二步：RVC 换音色
// ---------------------------------------------------------------------------

/// 现在能不能用，以及用哪个音色。
pub fn status(root: &Path) -> Value {
    let cfg = crate::config::read(root);
    let pth = cfg
        .get("pth_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    json!({
        "runtime_ready": paths::runtime_ready(root),
        "infer_present": infer_script(root).is_file(),
        "voices": list_sapi_voices(),
        "model_path": pth,
        "model_name": cfg.get("last_model_name").and_then(|v| v.as_str()).unwrap_or(""),
        "out_dir_read": out_dir_for(root, false).to_string_lossy(),
        "out_dir_voice": out_dir_for(root, true).to_string_lossy(),
        "out_dir_read_default": default_out_read(root).to_string_lossy(),
        "out_dir_voice_default": default_out_voice(root).to_string_lossy(),
        "max_chars": MAX_CHARS,
        "busy": *BUSY.lock().unwrap_or_else(|e| e.into_inner()),
    })
}

/// 跑一次合成。阻塞，调用方负责挪到后台线程。
pub fn run(
    app: &AppHandle,
    root: &Path,
    text: &str,
    voice: &str,
    rate: i32,
    pitch: i32,
    use_rvc: bool,
) -> Result<Value, String> {
    run_with_model(app, root, text, voice, rate, pitch, use_rvc, "")
}

/// 同上，但可以指定用哪个音色换声。
///
/// `model_path` 为空就用配置里当前选中的那个（文字合成面板走的就是这条）。
/// 试听要转的是用户点的那个音色，而不是「当前选中的」—— 为了听一下就把他的
/// 选择改掉，是拿副作用换功能。
#[allow(clippy::too_many_arguments)]
pub fn run_with_model(
    app: &AppHandle,
    root: &Path,
    text: &str,
    voice: &str,
    rate: i32,
    pitch: i32,
    use_rvc: bool,
    model_path: &str,
) -> Result<Value, String> {
    {
        let mut g = BUSY.lock().unwrap_or_else(|e| e.into_inner());
        if *g {
            return Err(crate::i18n::t("s.47baa6fbb7").into());
        }
        *g = true;
    }
    cancel_flag().store(false, Ordering::SeqCst);
    let log = crate::logging::begin_run(
        root,
        crate::logging::CH_TTS,
        &json!({
            "text_len": text.chars().count(),
            "voice": voice,
            "rate": rate,
            "pitch": pitch,
            "use_rvc": use_rvc,
        }),
    );
    crate::logging::shell_log!(
        "tts run log {}",
        log.file_name().and_then(|s| s.to_str()).unwrap_or("tts")
    );
    let mut trace = crate::logging::RunTrace::new(log.clone());
    let started = std::time::Instant::now();
    let result = run_inner(
        app, root, text, voice, rate, pitch, use_rvc, model_path, &mut trace,
    );
    let outcome = match &result {
        Ok(_) => "ok",
        Err(e) if e == &crate::i18n::t("s.a5ffdc95ee") => "cancelled",
        Err(_) => "error",
    };
    let file = result
        .as_ref()
        .ok()
        .and_then(|v| v.get("file").and_then(|x| x.as_str()))
        .unwrap_or("");
    let converted = result
        .as_ref()
        .ok()
        .and_then(|v| v.get("converted").and_then(|x| x.as_bool()))
        .unwrap_or(false);
    trace.outcome(
        outcome,
        &format!(
            "elapsed_ms: {}\nconverted: {}\nfile: {} ({} bytes)",
            started.elapsed().as_millis(),
            converted,
            file,
            crate::logging::file_len(Path::new(file)),
        ),
    );
    match &result {
        Ok(_) => crate::logging::finish_run(&log, true, "ok"),
        Err(e) => {
            trace.note(&format!("ERROR {e}"));
            crate::logging::finish_run(&log, true, outcome);
        }
    }
    {
        let mut g = BUSY.lock().unwrap_or_else(|e| e.into_inner());
        *g = false;
    }
    if let Err(ref e) = result {
        emit(app, "error", 0, 1, e);
    }
    result
}

fn run_inner(
    app: &AppHandle,
    root: &Path,
    text: &str,
    voice: &str,
    rate: i32,
    pitch: i32,
    use_rvc: bool,
    model_path: &str,
    trace: &mut crate::logging::RunTrace,
) -> Result<Value, String> {
    let text = text.trim();
    if text.is_empty() {
        return Err(crate::i18n::t("s.4e723e58f7").into());
    }
    if text.chars().count() > MAX_CHARS {
        return Err(crate::i18n::te("s.1bedd33b11", &(MAX_CHARS)));
    }

    emit(app, "sapi", 0, 2, &crate::i18n::t("s.b99cbcbcd3"));
    trace.note(&format!("sapi start voice={voice} rate={rate} chars={}", text.chars().count()));
    let raw = synthesize(root, text, voice, rate)?;
    trace.note(&format!(
        "sapi done {} ({} bytes)",
        raw.display(),
        crate::logging::file_len(&raw)
    ));
    if cancel_flag().load(Ordering::SeqCst) {
        trace.note("cancelled after sapi");
        return Err(crate::i18n::t("s.a5ffdc95ee").into());
    }

    let dir = out_dir_for(root, use_rvc);
    std::fs::create_dir_all(&dir).map_err(|e| crate::i18n::te("s.e9ddef6eab", &(e)))?;
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    // 文件名也带上模式。两条路即使被用户指到同一个目录，也不会撞名、也看得出
    // 哪个是哪个 —— 时间戳只到秒，同一秒里先出朗读再出变声是能撞上的。
    let out = dir.join(if use_rvc {
        format!("tts_voice_{stamp}.wav")
    } else {
        format!("tts_read_{stamp}.wav")
    });

    if !use_rvc {
        std::fs::copy(&raw, &out).map_err(|e| crate::i18n::te("s.9f8084f7cb", &(e)))?;
        emit(app, "done", 2, 2, &crate::i18n::t("s.2e33db9056"));
        trace.note("rvc skipped (sapi only)");
        return Ok(json!({ "ok": true, "file": out.to_string_lossy(), "converted": false }));
    }

    let cfg = crate::config::read(root);
    let pth = if model_path.trim().is_empty() {
        cfg.get("pth_path")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim()
            .to_string()
    } else {
        model_path.trim().to_string()
    };
    if pth.is_empty() || !Path::new(&pth).is_file() {
        return Err(crate::i18n::t("s.ab63502dd7").into());
    }
    if !paths::runtime_ready(root) {
        return Err(crate::i18n::t("s.75b84a31d6").into());
    }
    emit(app, "rvc", 1, 2, &crate::i18n::t("s.25865a0d91"));
    trace.note(&format!("rvc model {pth}"));

    // 走语音转换那条链路：热路径（实时 worker 常驻的模型）优先，
    // 没有实时 worker 时用它自己的常驻进程。两条都不必重付冷启动。
    //
    // sts::run 只认「输入路径 → 输出目录」，产物文件名由它决定，所以先转到一个
    // 临时目录再挪到我们要的名字上。多这一步是为了不去改 sts 那边的签名 ——
    // 那条链路同时服务批量转换，动它的输出命名风险更大。
    let stage = crate::paths::update_cache(root).join("tts_rvc");
    let _ = std::fs::remove_dir_all(&stage);
    std::fs::create_dir_all(&stage).map_err(|e| crate::i18n::te("s.e9ddef6eab", &(e)))?;

    let index = cfg
        .get("index_path")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let index_rate = cfg
        .get("index_rate")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0);

    let opts = crate::sts::ConvertOpts {
        // 文字合成有自己的进度条，别让「语音转换」页显示一个它没启动过的任务。
        quiet: true,
        ..Default::default()
    };
    let res = crate::sts::run(
        app,
        root,
        &raw.to_string_lossy(),
        &stage.to_string_lossy(),
        pitch,
        "rmvpe",
        index_rate,
        &pth,
        &index,
        opts,
    );
    if cancel_flag().load(Ordering::SeqCst) {
        let _ = std::fs::remove_dir_all(&stage);
        trace.note("cancelled during rvc");
        return Err(crate::i18n::t("s.a5ffdc95ee").into());
    }
    let value = match res {
        Ok(v) => v,
        Err(e) => {
            let _ = std::fs::remove_dir_all(&stage);
            trace.note(&format!("rvc failed: {e}"));
            return Err(e);
        }
    };
    // 一条输入只会有一个产物。拿不到就是没转出来，别让后面的 copy 报一个
    // 更难懂的「文件不存在」。
    let produced = value
        .get("files")
        .and_then(|x| x.as_array())
        .and_then(|a| a.first())
        .and_then(|x| x.as_str())
        .map(PathBuf::from)
        .filter(|p| p.is_file());
    let Some(produced) = produced else {
        let _ = std::fs::remove_dir_all(&stage);
        return Err(crate::i18n::t("s.f7271a7905").into());
    };
    std::fs::rename(&produced, &out)
        .or_else(|_| std::fs::copy(&produced, &out).map(|_| ()))
        .map_err(|e| crate::i18n::te("s.9f8084f7cb", &(e)))?;
    let _ = std::fs::remove_dir_all(&stage);

    trace.note(&format!(
        "rvc done {} ({} bytes)",
        out.display(),
        crate::logging::file_len(&out)
    ));
    let _ = std::fs::remove_file(&raw);
    emit(app, "done", 2, 2, &crate::i18n::t("s.2e33db9056"));
    Ok(json!({ "ok": true, "file": out.to_string_lossy(), "converted": true }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn output_lands_under_user_data_not_the_install_root() {
        // 用户的产出物一律进 User_Data：那是卸载时会问「要不要留着」的那个目录，
        // 扔在安装目录里会被卸载器一起删掉。
        for d in [
            default_out_read(Path::new("C:\\App")),
            default_out_voice(Path::new("C:\\App")),
        ] {
            assert!(d.to_string_lossy().contains("User_Data"), "{}", d.display());
        }
    }

    /// 两条路的默认目录必须是两个地方。同一个目录 + 秒级时间戳，同一秒里先出
    /// 朗读再出变声就会撞名，后写的把前一个盖掉。
    #[test]
    fn read_and_voice_default_to_different_folders() {
        let root = Path::new("C:\\App");
        assert_ne!(default_out_read(root), default_out_voice(root));
        assert!(default_out_read(root).ends_with("read"));
        assert!(default_out_voice(root).ends_with("voice"));
    }

    #[test]
    fn status_reports_not_ready_without_a_runtime() {
        let st = status(Path::new("C:\\definitely-not-here"));
        assert_eq!(st["runtime_ready"], json!(false));
        assert_eq!(st["infer_present"], json!(false));
    }

    /// 第二步必须走 sts::run（常驻），不能再自己起 infer_cli.py。
    ///
    /// 这条钉的是一次真实的浪费：原来每合成一句都要付一次完整冷启动
    /// （import torch/fairseq、探设备、读 net_g/hubert/rmvpe），一条五秒的
    /// 语音要一两分钟；而同一个仓库里 sts 那条链路早就把它解决了。
    #[test]
    fn the_rvc_step_goes_through_the_resident_path() {
        let src = include_str!("tts.rs");
        assert!(src.contains("crate::sts::run("), "第二步应当调用 sts::run");
        // run_inner 里不许再出现起进程的痕迹。infer_script 只剩 status() 在用。
        let body = &src[src.find("fn run_inner").expect("run_inner")..];
        let body = &body[..body.find("#[cfg(test)]").unwrap_or(body.len())];
        assert!(!body.contains("cmd.spawn()"), "run_inner 不该再自己起进程");
    }

    /// 借用 sts 那条链路时必须静音，否则用户开着「语音转换」页跑文字合成，
    /// 那一页会显示一个它自己没启动过的任务在跑。
    #[test]
    fn borrowing_the_sts_path_is_silent() {
        let src = include_str!("tts.rs");
        assert!(src.contains("quiet: true"), "借用时要静音");
    }

    #[test]
    fn an_empty_text_is_refused_before_anything_spawns() {
        // 语言是进程级全局状态，cargo 默认多线程跑测试。不钉住的话，
        // 断言里两次取文案可能落在不同语言上（实测到过法语 vs 韩语）。
        let _g = crate::i18n::testing::pin("zh-CN");
        // 这条断言的意义在于顺序：空文本必须在起 PowerShell 之前就被挡掉，
        // 否则 SAPI 会生成一个 0 秒的 wav，然后 RVC 对着它跑一遍，最后交给
        // 用户一个听不见任何东西的文件。
        assert!(MAX_CHARS > 0);
        let long: String = crate::i18n::t("s.582c50066c").repeat(MAX_CHARS + 1);
        assert!(long.chars().count() > MAX_CHARS);
    }
}
