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

/// 静音样本：filelist 末尾要拼 `mute{sr}.wav`。只看目录在不在会让缺文件的
/// 安装过了预检，训到最后一步才炸。
fn mute_ready(root: &Path, sr: Option<&str>) -> bool {
    let d = root.join("logs").join("mute").join("0_gt_wavs");
    let check = |rate: &str| d.join(format!("mute{rate}.wav")).is_file();
    match sr {
        Some(rate) => check(rate),
        None => SAMPLE_RATES.iter().all(|rate| check(rate)),
    }
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

/// 训练是否在跑。卸载底模前要问一句 —— 训练正读着底模，删掉只会让它在
/// 某个 epoch 中间炸掉。
pub fn busy() -> bool {
    *BUSY.lock().unwrap_or_else(|e| e.into_inner())
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
        "mute_present": mute_ready(root, None),
        "hubert_present": root.join("assets").join("hubert").join("hubert_base.pt").is_file(),
        "nvidia": nvidia,
        "pretrained": pre,
        "experiments": experiments(root),
        "suggested_batch": suggested_batch(),
        "rmvpe_present": rmvpe_ready(root),
        "busy": *BUSY.lock().unwrap_or_else(|e| e.into_inner()),
    })
}

/// rmvpe 是默认音高算法。文件不在或下到一半，预处理跑完才会炸。
fn rmvpe_ready(root: &Path) -> bool {
    root.join("assets")
        .join("rmvpe")
        .join("rmvpe.pt")
        .metadata()
        .map(|m| m.is_file() && m.len() > 1_000_000)
        .unwrap_or(false)
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
    #[serde(default)]
    pub save_every_weights: bool,
}

const F0_METHODS: [&str; 4] = ["rmvpe", "harvest", "pm", "dio"];

/// 原版 `default_batch_size = VRAM_GB // 2`。查不到就给 4（6GB 卡的稳妥值）。
fn suggested_batch() -> u32 {
    static CACHED: std::sync::OnceLock<u32> = std::sync::OnceLock::new();
    *CACHED.get_or_init(|| {
        let mut cmd = Command::new("nvidia-smi");
        cmd.args([
            "--query-gpu=memory.total",
            "--format=csv,noheader,nounits",
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x08000000);
        }
        let Ok(out) = cmd.output() else {
            return 4;
        };
        if !out.status.success() {
            return 4;
        }
        let mut min_mb = u32::MAX;
        for line in String::from_utf8_lossy(&out.stdout).lines() {
            if let Ok(n) = line.trim().parse::<u32>() {
                min_mb = min_mb.min(n);
            }
        }
        if min_mb == u32::MAX {
            return 4;
        }
        let gb = (min_mb / 1024).max(1);
        (gb / 2).clamp(1, 16)
    })
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
    if !F0_METHODS.contains(&req.f0_method.as_str()) {
        return Err(crate::i18n::te("s.trainF0Unsupported", &(req.f0_method)));
    }
    if req.f0_method == "rmvpe" && !rmvpe_ready(root) {
        return Err(crate::i18n::t("s.trainRmvpeMissing").into());
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
    if !mute_ready(root, Some(&req.sample_rate)) {
        return Err(crate::i18n::t("s.625da2c547").into());
    }
    // resume 的时候数据集可以不在了 —— 切片已经在实验目录里，原始素材删掉也无妨。
    let have_slices = count_dir(&exp_root(root).join(&req.exp).join("1_16k_wavs")) > 0;
    if !(req.resume && have_slices) && !Path::new(&req.dataset).is_dir() {
        return Err(crate::i18n::t("s.6c4b38602a").into());
    }
    Ok(())
}

/// 这一趟训练目前走到哪。取消或崩的时候，光看「已取消」不够。
#[derive(Default, Clone)]
struct Progress {
    stage: String,
    done: u64,
    total: u64,
    message: String,
}

/// 训练结束不管成败，都把盘上的产物和阶段日志尾巴写进 run log。
///
/// 26.8.16 两份用户日志只有请求 JSON + 一句 ERROR：一份是预处理
/// `_stop` 崩了，另一份是「已取消」。切片切完没有、权重写没写、训到第
/// 几轮，全看不出来。stdout 进度以前只进界面，不进日志。
fn write_outcome(root: &Path, exp: &str, log: &Path, progress: &Progress, outcome: &str) {
    let exp_dir = exp_root(root).join(exp);
    let counts = [
        ("0_gt_wavs", count_dir(&exp_dir.join("0_gt_wavs"))),
        ("1_16k_wavs", count_dir(&exp_dir.join("1_16k_wavs"))),
        ("2a_f0", count_dir(&exp_dir.join("2a_f0"))),
        ("2b-f0nsf", count_dir(&exp_dir.join("2b-f0nsf"))),
        ("3_feature768", count_dir(&exp_dir.join("3_feature768"))),
    ];
    let filelist = count_text_lines(&exp_dir.join("filelist.txt"));
    let epoch = latest_epoch(&exp_dir.join("train.log"));
    let final_w = root
        .join("assets")
        .join("weights")
        .join(format!("{exp}.pth"));
    let published = root
        .join("User_Data")
        .join("models")
        .join(exp)
        .join(format!("{exp}.pth"));
    let exp_pths = list_pth_names(&exp_dir);
    let weight_pths = list_pth_names(&root.join("assets").join("weights"))
        .into_iter()
        .filter(|n| n == &format!("{exp}.pth") || n.starts_with(&format!("{exp}_e")))
        .collect::<Vec<_>>();
    let usable = if crate::logging::file_len(&final_w) > 0
        || crate::logging::file_len(&published) > 0
    {
        "final"
    } else if !weight_pths.is_empty() || !exp_pths.is_empty() {
        "intermediate"
    } else if counts[1].1 > 0 {
        "slices_only"
    } else {
        "none"
    };
    let last = if progress.stage.is_empty() {
        "-".into()
    } else {
        format!(
            "{} {}/{} {}",
            progress.stage, progress.done, progress.total, progress.message
        )
    };
    crate::logging::note_run(
        log,
        &format!(
            "=== outcome ({outcome}) ===\n\
             last: {last}\n\
             usable: {usable}\n\
             latest_epoch: {}\n\
             counts: {}\n\
             filelist_lines: {filelist}\n\
             final_weights: {} ({} bytes)\n\
             published: {} ({} bytes)\n\
             exp_pths: {}\n\
             weight_pths: {}",
            epoch.map(|n| n.to_string()).unwrap_or_else(|| "-".into()),
            counts
                .iter()
                .map(|(k, n)| format!("{k}={n}"))
                .collect::<Vec<_>>()
                .join(" "),
            final_w.display(),
            crate::logging::file_len(&final_w),
            published.display(),
            crate::logging::file_len(&published),
            if exp_pths.is_empty() {
                "-".into()
            } else {
                exp_pths.join(",")
            },
            if weight_pths.is_empty() {
                "-".into()
            } else {
                weight_pths.join(",")
            },
        ),
    );
    for name in ["preprocess.log", "extract_f0_feature.log", "train.log"] {
        crate::logging::append_file(
            log,
            &crate::logging::tail_lines(&exp_dir.join(name), 50, 64 * 1024),
        );
    }
}

fn count_text_lines(p: &Path) -> u64 {
    std::fs::read_to_string(p)
        .map(|s| s.lines().filter(|l| !l.trim().is_empty()).count() as u64)
        .unwrap_or(0)
}

fn list_pth_names(dir: &Path) -> Vec<String> {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    let mut names: Vec<String> = rd
        .flatten()
        .filter_map(|e| {
            let p = e.path();
            if p.is_file() && p.extension().and_then(|s| s.to_str()) == Some("pth") {
                p.file_name()
                    .and_then(|s| s.to_str())
                    .map(|s| s.to_string())
            } else {
                None
            }
        })
        .collect();
    names.sort();
    names
}

fn latest_epoch(train_log: &Path) -> Option<u32> {
    let text = std::fs::read_to_string(train_log).ok()?;
    let marker = "====> Epoch: ";
    let mut last = None;
    for line in text.lines() {
        let Some(at) = line.find(marker) else {
            continue;
        };
        let tail = line[at + marker.len()..].split_whitespace().next()?;
        if let Ok(n) = tail.parse::<u32>() {
            last = Some(n);
        }
    }
    last
}

fn note_progress(log: &Path, v: &Value, progress: &mut Progress) {
    let phase = v.get("phase").and_then(|x| x.as_str()).unwrap_or("");
    let stage = v.get("stage").and_then(|x| x.as_str()).unwrap_or("");
    let message = v.get("message").and_then(|x| x.as_str()).unwrap_or("");
    let done = v
        .get("done")
        .and_then(|x| x.as_u64().or_else(|| x.as_i64().map(|n| n as u64)));
    let total = v
        .get("total")
        .and_then(|x| x.as_u64().or_else(|| x.as_i64().map(|n| n as u64)));
    if !stage.is_empty() {
        progress.stage = stage.to_string();
    } else if matches!(phase, "start" | "done" | "error" | "env") {
        progress.stage = phase.to_string();
    }
    if let Some(n) = done {
        progress.done = n;
    }
    if let Some(n) = total {
        progress.total = n;
    }
    if !message.is_empty() {
        progress.message = message.to_string();
    }
    // checkpoint 行已经是一份完整快照，原样落下；普通进度压成一行。
    if phase == "checkpoint" || phase == "env" {
        crate::logging::note_run(
            log,
            &format!(
                "{phase} {}",
                serde_json::to_string(v).unwrap_or_else(|_| "{}".into())
            ),
        );
        return;
    }
    crate::logging::note_run(
        log,
        &format!(
            "progress {phase} stage={} {}/{} {}",
            if stage.is_empty() { "-" } else { stage },
            done.map(|n| n.to_string()).unwrap_or_else(|| "-".into()),
            total.map(|n| n.to_string()).unwrap_or_else(|| "-".into()),
            message,
        ),
    );
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
    let device = if is_nvidia(root) { "cuda" } else { "cpu" };
    let log = crate::logging::begin_run(
        root,
        crate::logging::CH_TRAIN,
        &json!({
            "exp": req.exp,
            "dataset": req.dataset,
            "sample_rate": req.sample_rate,
            "total_epoch": req.total_epoch,
            "batch_size": req.batch_size,
            "save_every": req.save_every,
            "f0_method": req.f0_method,
            "resume": req.resume,
            "save_every_weights": req.save_every_weights,
            "device": device,
        }),
    );
    crate::logging::shell_log!(
        "train run log {}",
        log.file_name().and_then(|s| s.to_str()).unwrap_or("train")
    );
    let mut progress = Progress::default();
    let result = run_inner(app, root, &req, &log, &mut progress);
    let outcome = match &result {
        Ok(_) => "ok",
        Err(e) if e == &crate::i18n::t("s.a5ffdc95ee") => "cancelled",
        Err(_) => "error",
    };
    write_outcome(root, req.exp.trim(), &log, &progress, outcome);
    match &result {
        Ok(_) => crate::logging::finish_run(&log, true, "ok"),
        Err(e) => {
            crate::logging::note_run(&log, &format!("ERROR {e}"));
            crate::logging::finish_run(&log, true, outcome);
        }
    }
    *BUSY.lock().unwrap_or_else(|e| e.into_inner()) = false;
    *CHILD.lock().unwrap_or_else(|e| e.into_inner()) = None;
    if let Err(ref e) = result {
        emit(app, json!({ "phase": "error", "message": e }));
    }
    result
}

fn run_inner(
    app: &AppHandle,
    root: &Path,
    req: &TrainReq,
    log: &Path,
    progress: &mut Progress,
) -> Result<Value, String> {
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
        "save_every_weights": req.save_every_weights,
    });
    std::fs::write(
        &reqfile,
        serde_json::to_string_pretty(&payload).unwrap_or_default(),
    )
    .map_err(|e| crate::i18n::te("s.5ee0565f28", &(e)))?;

    let py = paths::runtime_python(root).ok_or(crate::i18n::t("s.47e57cab60"))?;
    let errfile = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(log)
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
    let _keep = crate::worker::ToolPidGuard::new(child.id());
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
        note_progress(log, &v, progress);
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
        // 语言是进程级全局状态，cargo 默认多线程跑测试。不钉住的话，
        // 断言里两次取文案可能落在不同语言上（实测到过法语 vs 韩语）。
        let _g = crate::i18n::testing::pin("zh-CN");
        // 这些字符不拦，用户会在训练跑了半小时之后收到一个建目录失败。
        for bad in ["", "  ", "a/b", "a\\b", "c:d", "x?y", "*", ".hidden", "mute"] {
            assert!(validate_name(bad).is_err(), "should reject {bad:?}");
        }
        for ok in [&crate::i18n::t("s.6ca6738e54"), "my voice", "voice-2026_v2"] {
            assert!(validate_name(ok).is_ok(), "should accept {ok:?}");
        }
    }

    #[test]
    fn mute_ready_needs_the_wav_not_just_the_folder() {
        let base = std::env::temp_dir().join("rvcf-train-mute");
        let _ = std::fs::remove_dir_all(&base);
        let d = base.join("logs").join("mute").join("0_gt_wavs");
        std::fs::create_dir_all(&d).unwrap();
        assert!(!mute_ready(&base, None));
        assert!(!mute_ready(&base, Some("48k")));
        std::fs::write(d.join("mute48k.wav"), b"x").unwrap();
        assert!(mute_ready(&base, Some("48k")));
        assert!(!mute_ready(&base, None));
        std::fs::write(d.join("mute32k.wav"), b"x").unwrap();
        std::fs::write(d.join("mute40k.wav"), b"x").unwrap();
        assert!(mute_ready(&base, None));
        let _ = std::fs::remove_dir_all(&base);
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
    fn rmvpe_ready_rejects_missing_and_tiny_files() {
        let base = std::env::temp_dir().join("rvcf-train-rmvpe");
        let _ = std::fs::remove_dir_all(&base);
        let d = base.join("assets").join("rmvpe");
        std::fs::create_dir_all(&d).unwrap();
        assert!(!rmvpe_ready(&base));
        std::fs::write(d.join("rmvpe.pt"), b"half").unwrap();
        assert!(!rmvpe_ready(&base));
        std::fs::write(d.join("rmvpe.pt"), vec![0u8; 1_000_001]).unwrap();
        assert!(rmvpe_ready(&base));
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn bad_f0_method_is_not_called_a_sample_rate() {
        let _g = crate::i18n::testing::pin("zh-CN");
        let msg = crate::i18n::te("s.trainF0Unsupported", &"crepe");
        assert!(msg.contains("crepe"), "{msg}");
        assert!(
            !msg.contains("采样率"),
            "wrong key reused the sample-rate string: {msg}"
        );
    }

    #[test]
    fn latest_epoch_reads_the_last_marker() {
        let td = std::env::temp_dir().join(format!(
            "rvcf-train-epoch-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&td);
        std::fs::create_dir_all(&td).unwrap();
        let p = td.join("train.log");
        std::fs::write(
            &p,
            "noise\n====> Epoch: 1 [t]\n====> Epoch: 2 [t]\n====> Epoch: 2 [t]\n",
        )
        .unwrap();
        assert_eq!(latest_epoch(&p), Some(2));
        assert_eq!(latest_epoch(&td.join("missing.log")), None);
        let _ = std::fs::remove_dir_all(&td);
    }

    #[test]
    fn outcome_report_can_tell_slices_from_a_finished_model() {
        let td = std::env::temp_dir().join(format!(
            "rvcf-train-outcome-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&td);
        let exp = td.join("logs").join("voice");
        std::fs::create_dir_all(exp.join("1_16k_wavs")).unwrap();
        std::fs::write(exp.join("1_16k_wavs").join("a.wav"), b"x").unwrap();
        std::fs::write(exp.join("preprocess.log"), "sliced 1 file\n").unwrap();
        let log = td.join("run.log");
        std::fs::write(&log, b"").unwrap();
        let progress = Progress {
            stage: "preprocess".into(),
            done: 1,
            total: 1,
            message: "切片与重采样…".into(),
        };
        write_outcome(&td, "voice", &log, &progress, "cancelled");
        let body = std::fs::read_to_string(&log).unwrap();
        assert!(body.contains("usable: slices_only"), "{body}");
        assert!(body.contains("1_16k_wavs=1"), "{body}");
        assert!(body.contains("last: preprocess 1/1"), "{body}");
        assert!(body.contains("preprocess.log"), "{body}");
        assert!(body.contains("sliced 1 file"), "{body}");

        std::fs::create_dir_all(td.join("assets").join("weights")).unwrap();
        std::fs::write(
            td.join("assets").join("weights").join("voice.pth"),
            b"pth",
        )
        .unwrap();
        write_outcome(&td, "voice", &log, &progress, "ok");
        let body = std::fs::read_to_string(&log).unwrap();
        assert!(body.contains("usable: final"), "{body}");
        let _ = std::fs::remove_dir_all(&td);
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
            save_every_weights: false,
        };
        // 没 Runtime 就该在这里停，而不是起个进程再失败。
        assert!(preflight(&base, &req).is_err());
        let _ = std::fs::remove_dir_all(&base);
    }
}
