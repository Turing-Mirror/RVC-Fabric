//! 训练音色。
//!
//! 和 `separate.rs` 同一个形状（一次性子进程 + JSON 行进度），但多两件事：
//!
//! * **它会跑几个小时。** 所以进度必须是「第几步 / 第几轮」而不是一个转圈，
//!   用户要能判断还剩多久，也要能关掉软件明天接着跑。
//! * **它必须能续跑。** 训练中途断电、蓝屏、手滑关窗都太常见了，重头再来
//!   意味着白烧几个小时的电。续跑判据放在 Python 那侧（看产物目录），这里
//!   只负责把 `resume` 传下去。
//!
//! 不复用 `worker.rs`：那套 pid 文件 + status.json 是给常驻变声进程设计的，
//! 训练是一次性任务，套进去只会多出一堆要清理的残留。

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

use crate::paths;

/// 一次只训一个：训练会吃满显存，两个一起跑必爆。
static BUSY: Mutex<bool> = Mutex::new(false);
static CANCEL: OnceLock<Arc<AtomicBool>> = OnceLock::new();
/// 训练子进程本身会再 fork 出 worker 进程，光靠 cancel 标志杀不干净，得留句柄。
static CHILD: Mutex<Option<u32>> = Mutex::new(None);

/// 界面只暴露这三档。原版还有 v1 和无 f0 的组合，那些对着我们的用户没有意义
/// —— 选错了只会训出更差的模型。
pub const SAMPLE_RATES: [&str; 3] = ["32k", "40k", "48k"];

fn cancel_flag() -> Arc<AtomicBool> {
    CANCEL
        .get_or_init(|| Arc::new(AtomicBool::new(false)))
        .clone()
}

fn worker_script(root: &Path) -> PathBuf {
    root.join("tools").join("train_worker.py")
}

pub fn exp_root(root: &Path) -> PathBuf {
    root.join("logs")
}

fn pretrained_dir(root: &Path) -> PathBuf {
    root.join("assets").join("pretrained_v2")
}

/// 某个采样率的底模齐不齐。两个文件缺一不可，只有 G 没有 D 训不起来。
pub fn pretrained_ready(root: &Path, sr: &str) -> bool {
    let d = pretrained_dir(root);
    // 底模都在 100 MB 以上；下到一半的半截文件不能算数。
    let ok = |name: String| {
        d.join(name)
            .metadata()
            .map(|m| m.is_file() && m.len() > 10_000_000)
            .unwrap_or(false)
    };
    ok(format!("f0G{sr}.pth")) && ok(format!("f0D{sr}.pth"))
}

/// 已有的实验（`logs/<名字>`）。`mute` 是随包发的静音样本，不是用户的实验。
fn experiments(root: &Path) -> Vec<Value> {
    let mut out = Vec::new();
    let Ok(rd) = std::fs::read_dir(exp_root(root)) else {
        return out;
    };
    let mut items: Vec<(String, Value)> = Vec::new();
    for e in rd.flatten() {
        let p = e.path();
        if !p.is_dir() {
            continue;
        }
        let Some(name) = p.file_name().and_then(|s| s.to_str()) else {
            continue;
        };
        if name == "mute" || name.starts_with('.') {
            continue;
        }
        let slices = count_dir(&p.join("1_16k_wavs"));
        let feats = count_dir(&p.join("3_feature768"));
        let trained = root
            .join("assets")
            .join("weights")
            .join(format!("{name}.pth"))
            .is_file();
        items.push((
            name.to_string(),
            json!({
                "name": name,
                "slices": slices,
                "features": feats,
                // 有切片就能续跑：预处理是最慢的一步，能跳过就是省下几十分钟。
                "resumable": slices > 0,
                "trained": trained,
            }),
        ));
    }
    items.sort_by(|a, b| a.0.cmp(&b.0));
    out.extend(items.into_iter().map(|(_, v)| v));
    out
}

fn count_dir(p: &Path) -> u64 {
    std::fs::read_dir(p)
        .map(|rd| rd.flatten().filter(|e| e.path().is_file()).count() as u64)
        .unwrap_or(0)
}

/// N 卡才谈得上训练。DirectML 后端不支持训练用到的算子，AMD/Intel 上
/// `train.py` 会退到 CPU —— 那不是「慢一点」，是几百小时。必须在界面上拦住，
/// 而不是让用户跑一晚上才发现。
fn is_nvidia(root: &Path) -> bool {
    match crate::provision::read_package_meta_variant(root).as_deref() {
        Some("nvidia") | Some("nvidia50") => true,
        Some(_) => false,
        // 没写过 package_meta 就现场看显卡名。
        None => {
            let gpus = crate::provision::list_gpus();
            crate::provision::recommend_variant(&gpus).0.starts_with("nvidia")
        }
    }
}

pub fn status(root: &Path) -> Value {
    let nvidia = is_nvidia(root);
    let pre: Vec<Value> = SAMPLE_RATES
        .iter()
        .map(|sr| json!({ "sample_rate": sr, "ready": pretrained_ready(root, sr) }))
        .collect();
    json!({
        "runtime_ready": paths::runtime_ready(root),
        "worker_present": worker_script(root).is_file(),
        "mute_present": root.join("logs").join("mute").join("0_gt_wavs").is_dir(),
        "hubert_present": root.join("assets").join("hubert").join("hubert_base.pt").is_file(),
        "nvidia": nvidia,
        "pretrained": pre,
        "experiments": experiments(root),
        "busy": *BUSY.lock().unwrap_or_else(|e| e.into_inner()),
    })
}

pub fn cancel() {
    cancel_flag().store(true, Ordering::SeqCst);
    // 光设标志不够：训练子进程自己还会 fork 出 DDP worker，父进程不死它们
    // 就一直占着显存。这里直接按 pid 杀。
    let pid = *CHILD.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(pid) = pid {
        kill_tree(pid);
    }
}

#[cfg(windows)]
fn kill_tree(pid: u32) {
    use std::os::windows::process::CommandExt;
    let _ = Command::new("taskkill")
        .args(["/PID", &pid.to_string(), "/T", "/F"])
        .creation_flags(0x08000000)
        .status();
}

#[cfg(not(windows))]
fn kill_tree(pid: u32) {
    let _ = Command::new("kill").args(["-9", &pid.to_string()]).status();
}

fn emit(app: &AppHandle, payload: Value) {
    let _ = app.emit("train-progress", payload);
}

/// 训练请求。字段和 `tools/train_worker.py` 的 `normalize()` 一一对应。
#[derive(Debug, Clone, serde::Deserialize)]
pub struct TrainReq {
    pub exp: String,
    pub dataset: String,
    pub sample_rate: String,
    pub total_epoch: u32,
    pub batch_size: u32,
    pub save_every: u32,
    pub f0_method: String,
    pub resume: bool,
}

/// 名字要当目录名和 .pth 文件名用，非法字符会在训练跑了半小时之后才炸。
pub fn validate_name(name: &str) -> Result<(), String> {
    let n = name.trim();
    if n.is_empty() {
        return Err(crate::i18n::t("s.0dabaf60ef").into());
    }
    if n.len() > 60 {
        return Err(crate::i18n::t("s.950d0895e7").into());
    }
    if n.chars().any(|c| "\\/:*?\"<>|".contains(c)) {
        return Err(crate::i18n::t("s.2633fe7d2f").into());
    }
    if n == "mute" {
        return Err(crate::i18n::t("s.2a330f81d4").into());
    }
    if n.starts_with('.') {
        return Err(crate::i18n::t("s.09d3c05d6b").into());
    }
    Ok(())
}

fn preflight(root: &Path, req: &TrainReq) -> Result<(), String> {
    validate_name(&req.exp)?;
    if !paths::runtime_ready(root) {
        return Err(crate::i18n::t("s.dc92f52f68").into());
    }
    if !worker_script(root).is_file() {
        return Err(crate::i18n::t("s.5164f3e0db").into());
    }
    if !SAMPLE_RATES.contains(&req.sample_rate.as_str()) {
        return Err(crate::i18n::te("s.ab1660b1a1", &(req.sample_rate)));
    }
    if !pretrained_ready(root, &req.sample_rate) {
        return Err(crate::i18n::te("s.c7a9f88925", &req.sample_rate));
    }
    if !root
        .join("assets")
        .join("hubert")
        .join("hubert_base.pt")
        .is_file()
    {
        return Err(crate::i18n::t("s.c2b2787278").into());
    }
    if !root.join("logs").join("mute").join("0_gt_wavs").is_dir() {
        return Err(crate::i18n::t("s.625da2c547").into());
    }
    // resume 的时候数据集可以不在了 —— 切片已经在实验目录里，原始素材删掉也无妨。
    let have_slices = count_dir(&exp_root(root).join(&req.exp).join("1_16k_wavs")) > 0;
    if !(req.resume && have_slices) && !Path::new(&req.dataset).is_dir() {
        return Err(crate::i18n::t("s.6c4b38602a").into());
    }
    Ok(())
}

/// 阻塞跑一次训练，调用方负责挪到后台线程。
pub fn run(app: &AppHandle, root: &Path, req: TrainReq) -> Result<Value, String> {
    {
        let mut g = BUSY.lock().unwrap_or_else(|e| e.into_inner());
        if *g {
            return Err(crate::i18n::t("s.fce4b463c1").into());
        }
        *g = true;
    }
    cancel_flag().store(false, Ordering::SeqCst);
    let result = run_inner(app, root, &req);
    *BUSY.lock().unwrap_or_else(|e| e.into_inner()) = false;
    *CHILD.lock().unwrap_or_else(|e| e.into_inner()) = None;
    if let Err(ref e) = result {
        emit(app, json!({ "phase": "error", "message": e }));
    }
    result
}

fn run_inner(app: &AppHandle, root: &Path, req: &TrainReq) -> Result<Value, String> {
    preflight(root, req)?;

    // 参数走临时文件不走命令行：数据集路径里有中文和空格是常态。
    let reqfile = paths::update_cache(root).join("train_request.json");
    if let Some(p) = reqfile.parent() {
        let _ = std::fs::create_dir_all(p);
    }
    let device = if is_nvidia(root) { "cuda" } else { "cpu" };
    let payload = json!({
        "exp": req.exp.trim(),
        "dataset": req.dataset,
        "sample_rate": req.sample_rate,
        "total_epoch": req.total_epoch,
        "batch_size": req.batch_size,
        "save_every": req.save_every,
        "f0_method": req.f0_method,
        "device": device,
        "is_half": device == "cuda",
        "resume": req.resume,
    });
    std::fs::write(
        &reqfile,
        serde_json::to_string_pretty(&payload).unwrap_or_default(),
    )
    .map_err(|e| crate::i18n::te("s.5ee0565f28", &(e)))?;

    let py = paths::runtime_python(root).ok_or(crate::i18n::t("s.47e57cab60"))?;
    let log = crate::logging::begin_run(root, crate::logging::CH_TRAIN, &payload);
    let errfile = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log)
        .ok();

    let mut cmd = Command::new(&py);
    cmd.arg(worker_script(root).as_os_str())
        .arg(reqfile.as_os_str())
        .current_dir(root)
        .envs(crate::worker::env_for_runtime(root))
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(match errfile {
            Some(f) => Stdio::from(f),
            None => Stdio::null(),
        });
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }

    let mut child: Child = cmd.spawn().map_err(|e| crate::i18n::te("s.217047672d", &(e)))?;
    *CHILD.lock().unwrap_or_else(|e| e.into_inner()) = Some(child.id());
    let stdout = child.stdout.take().ok_or(crate::i18n::t("s.c73d43b29b"))?;

    let mut done: Option<Value> = None;
    let mut fail: Option<String> = None;
    for line in BufReader::new(stdout).lines().map_while(Result::ok) {
        if cancel_flag().load(Ordering::SeqCst) {
            kill_tree(child.id());
            let _ = child.wait();
            return Err(crate::i18n::t("s.a5ffdc95ee").into());
        }
        let Ok(v) = serde_json::from_str::<Value>(&line) else {
            continue; // 不是协议行（tqdm 之类），忽略
        };
        match v.get("phase").and_then(|x| x.as_str()).unwrap_or("") {
            "error" => {
                fail = Some(
                    v.get("message")
                        .and_then(|x| x.as_str())
                        .unwrap_or(&crate::i18n::t("s.60a21a8105"))
                        .to_string(),
                )
            }
            "done" => done = Some(v.clone()),
            _ => {}
        }
        emit(app, v);
    }

    let st = child.wait().map_err(|e| crate::i18n::te("s.d21a4981b7", &(e)))?;
    if cancel_flag().load(Ordering::SeqCst) {
        return Err(crate::i18n::t("s.a5ffdc95ee").into());
    }
    if let Some(e) = fail {
        return Err(e);
    }
    if !st.success() {
        return Err(crate::i18n::t2("s.7803aff201", &st.code().unwrap_or(-1), &req.exp.trim()));
    }
    let d = done.ok_or(crate::i18n::t("s.7dc4ea39fd"))?;
    // 预处理/特征提取可能在 TEMP 落中间文件。
    let stats = crate::paths::clean_temps(root);
    crate::paths::log_clean_stats(&crate::i18n::t("s.4546433411"), root, &stats);
    Ok(json!({
        "ok": true,
        "weights": d.get("weights").cloned().unwrap_or(Value::Null),
        "index": d.get("index").cloned().unwrap_or(Value::Null),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_names_that_would_break_a_path() {
        // 这些字符不拦，用户会在训练跑了半小时之后收到一个建目录失败。
        for bad in ["", "  ", "a/b", "a\\b", "c:d", "x?y", "*", ".hidden", "mute"] {
            assert!(validate_name(bad).is_err(), "should reject {bad:?}");
        }
        for ok in [&crate::i18n::t("s.6ca6738e54"), "my voice", "voice-2026_v2"] {
            assert!(validate_name(ok).is_ok(), "should accept {ok:?}");
        }
    }

    #[test]
    fn pretrained_needs_both_g_and_d() {
        let base = std::env::temp_dir().join("rvcf-train-pretrained");
        let _ = std::fs::remove_dir_all(&base);
        let d = base.join("assets").join("pretrained_v2");
        std::fs::create_dir_all(&d).unwrap();
        assert!(!pretrained_ready(&base, "48k"));

        let big = vec![0u8; 10_000_001];
        std::fs::write(d.join("f0G48k.pth"), &big).unwrap();
        assert!(!pretrained_ready(&base, "48k"));

        std::fs::write(d.join("f0D48k.pth"), &big).unwrap();
        assert!(pretrained_ready(&base, "48k"));
        assert!(!pretrained_ready(&base, "40k"));
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn a_truncated_pretrained_download_is_not_ready() {
        // 下到一半的 .pth 存在但没用；只判存在会让训练在加载底模时才炸。
        let base = std::env::temp_dir().join("rvcf-train-trunc");
        let _ = std::fs::remove_dir_all(&base);
        let d = base.join("assets").join("pretrained_v2");
        std::fs::create_dir_all(&d).unwrap();
        std::fs::write(d.join("f0G48k.pth"), b"half a file").unwrap();
        std::fs::write(d.join("f0D48k.pth"), b"half a file").unwrap();
        assert!(!pretrained_ready(&base, "48k"));
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn mute_is_not_listed_as_a_user_experiment() {
        // 语言是进程级全局状态，别的测试改了会让这里的 t() 前后取到两种语言。
        let _g = crate::i18n::testing::pin("zh-CN");
        // logs/mute 是随包发的静音样本。列出来用户会以为那是自己的音色。
        let base = std::env::temp_dir().join("rvcf-train-exps");
        let _ = std::fs::remove_dir_all(&base);
        std::fs::create_dir_all(base.join("logs").join("mute")).unwrap();
        std::fs::create_dir_all(base.join("logs").join(&crate::i18n::t("s.6ca6738e54")).join("1_16k_wavs")).unwrap();
        std::fs::write(
            base.join("logs").join(&crate::i18n::t("s.6ca6738e54")).join("1_16k_wavs").join("a.wav"),
            b"x",
        )
        .unwrap();

        let exps = experiments(&base);
        assert_eq!(exps.len(), 1);
        assert_eq!(exps[0]["name"], json!(crate::i18n::t("s.6ca6738e54")));
        assert_eq!(exps[0]["slices"], json!(1));
        assert_eq!(exps[0]["resumable"], json!(true));
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn preflight_refuses_before_it_can_waste_hours() {
        let base = std::env::temp_dir().join("rvcf-train-preflight");
        let _ = std::fs::remove_dir_all(&base);
        std::fs::create_dir_all(&base).unwrap();
        let req = TrainReq {
            exp: "x".into(),
            dataset: base.to_string_lossy().into(),
            sample_rate: "48k".into(),
            total_epoch: 10,
            batch_size: 8,
            save_every: 5,
            f0_method: "rmvpe".into(),
            resume: false,
        };
        // 没 Runtime 就该在这里停，而不是起个进程再失败。
        assert!(preflight(&base, &req).is_err());
        let _ = std::fs::remove_dir_all(&base);
    }
}
