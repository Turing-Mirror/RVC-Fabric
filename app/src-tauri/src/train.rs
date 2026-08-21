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
        let f0 = count_dir(&p.join("2a_f0"));
        let feats = count_dir(&p.join("3_feature768"));
        // 预处理读进来几个、失败几个。界面上要能说清「上次到底做完没有」，
        // 光一个「可续跑」的布尔值说不出这件事。
        let (ok_files, fail_files) = preprocess_tally(&p.join("preprocess.log"));
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
                "f0": f0,
                "features": feats,
                // 三个数目对不上就说明上一次是中途停的。判据已经修过（数目对得上
                // 才算做完），但界面上也得说出来 —— 否则「补齐并继续」会比用户
                // 预期的慢几分钟，他会以为是更新之后变慢了。
                "complete": slices > 0 && f0 == slices && feats == slices,
                "preprocess_ok": ok_files,
                "preprocess_failed": fail_files,
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

/// preprocess.log 里成功了几个、失败了几个。
///
/// 26.8.20 那位的一个实验 2038 个文件只切出 3 条，训练照跑，500 epoch 之后才
/// 发现音色不像。后端已经会报这件事了，但报完就被下一阶段的进度盖掉；界面上
/// 得能随时翻出来。
///
/// 一个实验的「中间产物」——可以删、删了只是要重跑预处理的东西。
///
/// 这张表是唯一的判据：扫多少和删多少必须来自同一处，两边各写一份迟早会分叉，
/// 而分叉的后果是删掉了不该删的。
///
/// 明确不在表里：`*.pth`（训练存档和权重）、`*.index`（检索索引）、
/// `*.log`（日志）、`config.json`。前两样删了不可再生。
pub const STAGE_ARTIFACTS: [&str; 7] = [
    "0_gt_wavs",
    "1_16k_wavs",
    "2a_f0",
    "2b-f0nsf",
    "3_feature768",
    "total_fea.npy",
    "filelist.txt",
];

/// 中间产物一共占多少字节。
pub fn stage_artifact_bytes(exp_dir: &Path) -> u64 {
    STAGE_ARTIFACTS
        .iter()
        .map(|name| dir_or_file_bytes(&exp_dir.join(name)))
        .sum()
}

fn dir_or_file_bytes(p: &Path) -> u64 {
    let Ok(meta) = std::fs::metadata(p) else {
        return 0;
    };
    if meta.is_file() {
        return meta.len();
    }
    let Ok(rd) = std::fs::read_dir(p) else {
        return 0;
    };
    rd.flatten()
        .map(|e| dir_or_file_bytes(&e.path()))
        .sum()
}

/// 数据集抽样体检。
///
/// 26.8.20 那位跑了 500 epoch 才发现音色不像，原因是 2038 个文件只切出 3 条。
/// 那件事已经在预处理阶段拦住了，但还有一类拦不住：素材本身就不合适 —— 整首歌
/// （带伴奏）、大段静音、采样率五花八门。这些跑完才发现同样是几十分钟白费。
///
/// 用产品自带的 ffprobe 读元数据，不解码 —— 三十个文件几秒钟就回来了。响度和
/// 静音占比要解码，所以只在更小的子集上做。
///
/// 全程可跳过：拿不到 ffprobe（比如开发机上）就返回 available=false，界面不显示
/// 这一块，而不是报错。
pub fn inspect_dataset(root: &Path, dir: &Path) -> Value {
    let probe = root.join(if cfg!(windows) { "ffprobe.exe" } else { "ffprobe" });
    if !probe.is_file() {
        return json!({ "available": false });
    }
    let mut files = Vec::new();
    collect_audio(dir, &mut files, 0);
    if files.is_empty() {
        return json!({ "available": true, "sampled": 0, "files": 0 });
    }
    files.sort();
    let total = files.len();
    // 均匀抽样，不是取前 N 个 —— 用户常按歌手/来源分文件夹，取前 N 个只会看到
    // 第一个文件夹。
    const SAMPLE: usize = 30;
    let step = (total as f64 / SAMPLE as f64).max(1.0);
    let picked: Vec<&PathBuf> = (0..SAMPLE.min(total))
        .map(|i| &files[((i as f64) * step) as usize % total])
        .collect();

    let mut durations: Vec<f64> = Vec::new();
    let mut rates: std::collections::BTreeMap<u32, u64> = Default::default();
    let mut channels: std::collections::BTreeMap<u32, u64> = Default::default();
    for p in &picked {
        let Some((dur, sr, ch)) = probe_one(&probe, p) else {
            continue;
        };
        if dur > 0.0 {
            durations.push(dur);
        }
        if sr > 0 {
            *rates.entry(sr).or_insert(0) += 1;
        }
        if ch > 0 {
            *channels.entry(ch).or_insert(0) += 1;
        }
    }
    if durations.is_empty() {
        return json!({ "available": true, "sampled": 0, "files": total });
    }
    durations.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let median = durations[durations.len() / 2];
    let mean: f64 = durations.iter().sum::<f64>() / durations.len() as f64;
    json!({
        "available": true,
        "files": total,
        "sampled": durations.len(),
        "median_seconds": median,
        // 总时长是估的：抽样均值 × 文件数。界面上必须写成「约」。
        "estimated_total_seconds": mean * total as f64,
        "sample_rates": rates.iter().map(|(k, v)| json!({"rate": k, "files": v})).collect::<Vec<_>>(),
        "channels": channels.iter().map(|(k, v)| json!({"channels": k, "files": v})).collect::<Vec<_>>(),
    })
}

fn collect_audio(dir: &Path, out: &mut Vec<PathBuf>, depth: u32) {
    if depth > 6 || out.len() > 20_000 {
        return;
    }
    let Ok(rd) = std::fs::read_dir(dir) else {
        return;
    };
    for e in rd.flatten() {
        let p = e.path();
        if p.is_dir() {
            collect_audio(&p, out, depth + 1);
            continue;
        }
        let ext = p
            .extension()
            .and_then(|x| x.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        if DATASET_AUDIO_EXT.contains(&ext.as_str()) {
            out.push(p);
        }
    }
}

/// 一个文件的 (时长秒, 采样率, 声道数)。取不到就是 None。
fn probe_one(probe: &Path, file: &Path) -> Option<(f64, u32, u32)> {
    let mut cmd = std::process::Command::new(probe);
    cmd.args([
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=sample_rate,channels:format=duration",
        "-of", "default=noprint_wrappers=1:nokey=0",
    ])
    .arg(file)
    .stdin(std::process::Stdio::null())
    .stderr(std::process::Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    // `output()` 没有超时。坏文件能让 ffprobe 卡住，而这里要连着跑三十次。
    let out = run_with_timeout(cmd, std::time::Duration::from_secs(5))?;
    let text = String::from_utf8_lossy(&out);
    let mut dur = 0.0;
    let mut sr = 0u32;
    let mut ch = 0u32;
    for line in text.lines() {
        let Some((k, v)) = line.split_once('=') else {
            continue;
        };
        match k.trim() {
            "duration" => dur = v.trim().parse().unwrap_or(0.0),
            "sample_rate" => sr = v.trim().parse().unwrap_or(0),
            "channels" => ch = v.trim().parse().unwrap_or(0),
            _ => {}
        }
    }
    Some((dur, sr, ch))
}

fn run_with_timeout(mut cmd: std::process::Command, wait: std::time::Duration) -> Option<Vec<u8>> {
    cmd.stdout(std::process::Stdio::piped());
    let mut child = cmd.spawn().ok()?;
    let mut stdout = child.stdout.take()?;
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        use std::io::Read;
        let mut buf = Vec::new();
        let _ = stdout.read_to_end(&mut buf);
        let _ = tx.send(buf);
    });
    match rx.recv_timeout(wait) {
        Ok(buf) => {
            let _ = child.wait();
            Some(buf)
        }
        Err(_) => {
            let _ = child.kill();
            None
        }
    }
}

/// 可清理的三类。分开列、分开勾 —— 三样的后果完全不同，混成一个「一键清理」
/// 就等于让用户在不知道后果的情况下按下去。
///
/// | 类别 | 匹配 | 删掉之后 |
/// |---|---|---|
/// | snapshots  | `assets/weights/<exp>_e\d+_s\d+.pth` | 无影响 |
/// | checkpoints| `logs/<exp>/[GD]_\d+.pth`             | 不能续训 |
/// | dataset    | `STAGE_ARTIFACTS`                     | 不能续训，要从预处理重来 |
///
/// 永不触碰：`assets/weights/<exp>.pth`（正式权重）、`User_Data/models/**`
/// （已发布的音色）、`logs/<exp>/*.index`（检索索引）、各类 `.log`。
pub const CLEANUP_KINDS: [&str; 3] = ["snapshots", "checkpoints", "dataset"];

/// 「训练途中另存的小模型」：`<exp>_e12_s3456.pth`。
///
/// 判据必须把正式权重 `<exp>.pth` 排除在外 —— 那是训练的最终产物，删了就没了。
pub fn is_epoch_snapshot(exp: &str, name: &str) -> bool {
    let Some(stem) = name.strip_suffix(".pth") else {
        return false;
    };
    let Some(rest) = stem.strip_prefix(exp) else {
        return false;
    };
    // `<exp>.pth` 本身：rest 是空串，不算。
    let Some(rest) = rest.strip_prefix("_e") else {
        return false;
    };
    let Some((epoch, step)) = rest.split_once("_s") else {
        return false;
    };
    !epoch.is_empty()
        && epoch.chars().all(|c| c.is_ascii_digit())
        && !step.is_empty()
        && step.chars().all(|c| c.is_ascii_digit())
}

/// 「训练存档」：`G_35200.pth` / `D_35200.pth`。
pub fn is_train_checkpoint(name: &str) -> bool {
    let Some(stem) = name.strip_suffix(".pth") else {
        return false;
    };
    let Some(rest) = stem.strip_prefix('G').or_else(|| stem.strip_prefix('D')) else {
        return false;
    };
    let Some(digits) = rest.strip_prefix('_') else {
        return false;
    };
    !digits.is_empty() && digits.chars().all(|c| c.is_ascii_digit())
}

/// 某一类在盘上的文件清单。扫描和删除都调它 —— 只有一处判据。
fn cleanup_targets(root: &Path, exp: &str, kind: &str) -> Vec<PathBuf> {
    let exp_dir = exp_root(root).join(exp);
    match kind {
        "snapshots" => {
            let dir = root.join("assets").join("weights");
            list_files(&dir)
                .into_iter()
                .filter(|p| {
                    p.file_name()
                        .and_then(|s| s.to_str())
                        .map(|n| is_epoch_snapshot(exp, n))
                        .unwrap_or(false)
                })
                .collect()
        }
        "checkpoints" => list_files(&exp_dir)
            .into_iter()
            .filter(|p| {
                p.file_name()
                    .and_then(|s| s.to_str())
                    .map(is_train_checkpoint)
                    .unwrap_or(false)
            })
            .collect(),
        "dataset" => STAGE_ARTIFACTS
            .iter()
            .map(|n| exp_dir.join(n))
            .filter(|p| p.exists())
            .collect(),
        _ => Vec::new(),
    }
}

fn list_files(dir: &Path) -> Vec<PathBuf> {
    std::fs::read_dir(dir)
        .map(|rd| rd.flatten().map(|e| e.path()).filter(|p| p.is_file()).collect())
        .unwrap_or_default()
}

/// 每个实验、每一类各占多少、各有几个文件。
pub fn cleanup_scan(root: &Path) -> Value {
    let mut out: Vec<Value> = Vec::new();
    let Ok(rd) = std::fs::read_dir(exp_root(root)) else {
        return json!([]);
    };
    let mut names: Vec<String> = rd
        .flatten()
        .filter(|e| e.path().is_dir())
        .filter_map(|e| e.file_name().to_str().map(String::from))
        .filter(|n| n != "mute" && !n.starts_with('.'))
        .collect();
    names.sort();
    for exp in names {
        let mut kinds = serde_json::Map::new();
        let mut total = 0u64;
        for kind in CLEANUP_KINDS {
            let files = cleanup_targets(root, &exp, kind);
            let bytes: u64 = files.iter().map(|p| dir_or_file_bytes(p)).sum();
            total += bytes;
            kinds.insert(kind.into(), json!({ "files": files.len(), "bytes": bytes }));
        }
        out.push(json!({ "exp": exp, "total_bytes": total, "kinds": Value::Object(kinds) }));
    }
    json!(out)
}

/// 删掉指定实验的指定几类，返回释放的字节数。
///
/// 和 `reset_stages` 同一套闸：训练中拒绝、实验名不许逃逸、删前重扫、写日志。
pub fn cleanup_apply(root: &Path, exp: &str, kinds: &[String]) -> Result<u64, String> {
    let exp_dir = guard_exp_dir(root, exp)?;
    let _ = &exp_dir;
    let mut freed = 0u64;
    for kind in kinds {
        if !CLEANUP_KINDS.contains(&kind.as_str()) {
            continue;
        }
        // 删之前重新扫一次，不复用界面上那份可能已经过时的清单。
        for p in cleanup_targets(root, exp.trim(), kind) {
            let bytes = dir_or_file_bytes(&p);
            let r = if p.is_dir() {
                std::fs::remove_dir_all(&p)
            } else {
                std::fs::remove_file(&p)
            };
            match r {
                Ok(()) => freed += bytes,
                Err(e) => {
                    crate::logging::shell_log!("清理：{} 删除失败 {}", p.display(), e)
                }
            }
        }
    }
    crate::logging::shell_log!(
        "清理：实验 {} 类别 {:?} 释放约 {:.1} MB",
        exp.trim(),
        kinds,
        freed as f64 / (1024.0 * 1024.0)
    );
    Ok(freed)
}

/// 删除类操作共用的那几道闸。
fn guard_exp_dir(root: &Path, exp: &str) -> Result<PathBuf, String> {
    let exp = exp.trim();
    if exp.is_empty() || exp.contains(['/', '\\', ':']) || exp == "." || exp == ".." {
        return Err(crate::i18n::te("s.trainNameInvalid", &exp));
    }
    if *BUSY.lock().unwrap_or_else(|e| e.into_inner()) {
        return Err(crate::i18n::t("s.trainBusyNoReset"));
    }
    let exp_dir = exp_root(root).join(exp);
    let (Ok(canon), Ok(canon_root)) = (exp_dir.canonicalize(), root.canonicalize()) else {
        return Err(crate::i18n::te("s.trainExpMissing", &exp));
    };
    if !canon.starts_with(&canon_root) {
        return Err(crate::i18n::te("s.trainExpMissing", &exp));
    }
    Ok(exp_dir)
}

/// 删掉一个实验的中间产物，返回释放的字节数。
///
/// 五条硬要求，一条都不能少：
/// 1. 扫和删用同一张表（`STAGE_ARTIFACTS`）。
/// 2. 删之前重新算一次体积 —— 对话框开着的时候训练可能刚跑完，盘上的东西变了。
/// 3. 训练进行中一律拒绝。
/// 4. 路径必须落在产品根之下，否则拒绝。
/// 5. 每次操作往日志写一行：删了哪个实验、释放多少。
pub fn reset_stages(root: &Path, exp: &str) -> Result<u64, String> {
    let exp_dir = guard_exp_dir(root, exp)?;
    let exp = exp.trim();

    // 删之前重新算一次。
    let freed = stage_artifact_bytes(&exp_dir);
    for name in STAGE_ARTIFACTS {
        let p = exp_dir.join(name);
        let Ok(meta) = std::fs::metadata(&p) else {
            continue;
        };
        let r = if meta.is_dir() {
            std::fs::remove_dir_all(&p)
        } else {
            std::fs::remove_file(&p)
        };
        if let Err(e) = r {
            crate::logging::shell_log!("清空中间产物：{} 删除失败 {}", p.display(), e);
        }
    }
    crate::logging::shell_log!(
        "清空中间产物：实验 {} 释放约 {:.1} MB",
        exp,
        freed as f64 / (1024.0 * 1024.0)
    );
    Ok(freed)
}

/// preprocess.py 每个文件写一行：成功是 `路径\t-> Success`，失败是
/// `路径\t-> Traceback (most recent call last): …`。数这两种前缀就够。
pub fn preprocess_tally(log: &Path) -> (u64, u64) {
    let Ok(text) = std::fs::read_to_string(log) else {
        return (0, 0);
    };
    let mut ok = 0u64;
    let mut fail = 0u64;
    for line in text.lines() {
        if line.contains("-> Success") {
            ok += 1;
        } else if line.contains("-> Traceback") {
            fail += 1;
        }
    }
    (ok, fail)
}

/// 数据集里算数的音频后缀。
///
/// 必须和 `tools/train_worker.AUDIO_EXT` / `infer/modules/train/preprocess.py`
/// 那两份完全一致 —— 界面上报「找到 120 个音频」而预处理只认出 80 个，比不报
/// 还糟：用户会拿这个数字去判断自己的数据集够不够，而它是假的。有一条测试直接
/// 读 train_worker.py 的那一行来比对，改一边忘了另一边就红。
pub const DATASET_AUDIO_EXT: [&str; 8] =
    ["wav", "mp3", "flac", "ogg", "m4a", "aac", "wma", "opus"];

/// 选完数据集立刻数一遍。
///
/// 26.8.20 那位的另一个实验：2038 个文件只切出 3 条，训练照跑，500 epoch 跑完
/// 才发现音色不像。那是预处理阶段的事，但更早一步就能拦 —— 选目录的当下就该
/// 知道这里到底有几个音频。
///
/// 递归扫子目录，跟 preprocess.py 的 os.walk 一致：用户按歌手分文件夹是常态。
pub fn scan_dataset(dir: &Path) -> Value {
    let mut files: u64 = 0;
    let mut other: u64 = 0;
    let mut bytes: u64 = 0;
    let mut by_ext: std::collections::BTreeMap<String, u64> = Default::default();
    let mut stack = vec![dir.to_path_buf()];
    // 扫到这么多就停：真有人把整块盘选进来，界面不该卡在那儿数。
    const MAX_ENTRIES: u64 = 200_000;
    let mut seen: u64 = 0;
    while let Some(d) = stack.pop() {
        let Ok(rd) = std::fs::read_dir(&d) else {
            continue;
        };
        for e in rd.flatten() {
            seen += 1;
            if seen > MAX_ENTRIES {
                stack.clear();
                break;
            }
            let p = e.path();
            if p.is_dir() {
                stack.push(p);
                continue;
            }
            let ext = p
                .extension()
                .and_then(|x| x.to_str())
                .unwrap_or("")
                .to_ascii_lowercase();
            if DATASET_AUDIO_EXT.contains(&ext.as_str()) {
                files += 1;
                bytes += e.metadata().map(|m| m.len()).unwrap_or(0);
                *by_ext.entry(ext).or_insert(0) += 1;
            } else {
                other += 1;
            }
        }
    }
    json!({
        "files": files,
        "other_files": other,
        "total_bytes": bytes,
        "by_ext": by_ext,
        "truncated": seen > MAX_ENTRIES,
        "supported": DATASET_AUDIO_EXT,
    })
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
    let busy = *BUSY.lock().unwrap_or_else(|e| e.into_inner());
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
        // 产品所在盘还剩多少。训练要在 logs/<实验>/ 下写切片、音高、特征，
        // 写到一半盘满了是「跑了四十分钟然后失败」，值得在开始之前就拦。
        "disk_free_bytes": paths::free_space_bytes(root).map(Value::from).unwrap_or(Value::Null),
        "busy": busy,
        // 正在跑的时候不提「上次断了」—— 那说的就是这一次。
        "interrupted": if busy { Value::Null } else { last_interrupted(root).unwrap_or(Value::Null) },
    })
}

/// 上一次训练是不是没跑完就断了，断在第几轮。
///
/// 训练进度以前只活在内存（`BUSY` 那个 bool）和界面组件的 state 里，程序
/// 一死就全没了。26.8.18 的用户被强杀之后重开，界面显示「空闲」，他完全
/// 不知道刚才那一次跑到了第 99 轮、切片和特征都还在盘上 —— 只能从头再来。
///
/// 判据是日志尾巴：`finish_run` 不管成败都会写一行 `=== done (…) ===`，
/// 没有这行就是壳没活到写它的那一刻。
fn last_interrupted(root: &Path) -> Option<Value> {
    let dir = crate::logging::channel_dir(root, crate::logging::CH_TRAIN);
    let mut newest: Option<(std::time::SystemTime, std::path::PathBuf)> = None;
    for e in std::fs::read_dir(&dir).ok()?.flatten() {
        let p = e.path();
        if p.extension().and_then(|s| s.to_str()) != Some("log") {
            continue;
        }
        let Ok(m) = e.metadata().and_then(|m| m.modified()) else {
            continue;
        };
        if newest.as_ref().map_or(true, |(t, _)| m > *t) {
            newest = Some((m, p));
        }
    }
    let (_, path) = newest?;
    let text = std::fs::read_to_string(&path).ok()?;
    if text.contains("=== done (") {
        return None;
    }
    parse_interrupted(&text).map(|(exp, done, total)| {
        json!({ "exp": exp, "epoch": done, "total": total })
    })
}

/// 从一份没写完的训练日志里挖出实验名和最后一轮。日志格式见 `begin_run`
/// （头部是请求 JSON）和 `note_progress`（`progress stage stage=train 99/200 …`）。
fn parse_interrupted(text: &str) -> Option<(String, u32, u32)> {
    let exp = text
        .lines()
        .find_map(|l| {
            let l = l.trim();
            let rest = l.strip_prefix("\"exp\":")?;
            let v = rest.trim().trim_end_matches(',').trim();
            let v = v.strip_prefix('"')?.strip_suffix('"')?;
            (!v.is_empty()).then(|| v.to_string())
        })?;
    let mut last = None;
    for line in text.lines() {
        let Some(at) = line.find("stage=train ") else {
            continue;
        };
        let tail = line[at + "stage=train ".len()..].split_whitespace().next()?;
        let (a, b) = tail.split_once('/')?;
        if let (Ok(a), Ok(b)) = (a.parse::<u32>(), b.parse::<u32>()) {
            last = Some((a, b));
        }
    }
    let (done, total) = last?;
    // 0/200 是「准备训练」那一下，还没真开始，不值得提示用户续跑。
    (done > 0).then_some((exp, done, total))
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
    /// 训好的音色放哪。空 = `User_Data/models`（老行为）。
    ///
    /// 一个音色连模型带索引三四百 MB，训十个就是几个 G。允许挪到别的盘，
    /// 但必须是绝对路径且建得出来 —— 相对路径会跟着 cwd 跑，训了几小时
    /// 最后落在谁也找不到的地方。
    #[serde(default)]
    pub output_dir: String,
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
    let message_owned = crate::i18n::t_worker_msg(v);
    let message = message_owned.as_str();
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


/// 校验用户选的音色存放目录，返回归一化后的路径（空 = 用默认的 `User_Data/models`）。
///
/// 必须是绝对路径：相对路径会跟着进程的 cwd 走，训了几小时最后落在谁也找不到
/// 的地方。也必须现在就建得出来 —— 拔掉的移动硬盘、写保护的目录，等训完再发现
/// 就是几小时白烧。
pub fn normalize_output_dir(raw: &str) -> Result<String, String> {
    let t = raw.trim();
    if t.is_empty() {
        return Ok(String::new());
    }
    let p = Path::new(t);
    if !p.is_absolute() {
        return Err(crate::i18n::te("s.trainOutRelative", &t));
    }
    std::fs::create_dir_all(p).map_err(|e| crate::i18n::t2("s.trainOutUnwritable", &t, &e))?;
    Ok(p.to_string_lossy().into_owned())
}

/// 阻塞跑一次训练，调用方负责挪到后台线程。
pub fn run(app: &AppHandle, root: &Path, mut req: TrainReq) -> Result<Value, String> {
    {
        let mut g = BUSY.lock().unwrap_or_else(|e| e.into_inner());
        if *g {
            return Err(crate::i18n::t("s.fce4b463c1").into());
        }
        *g = true;
    }
    cancel_flag().store(false, Ordering::SeqCst);
    // 先把输出目录判掉：训了几小时最后落不下去，那几小时就白烧了。
    let out_dir = match normalize_output_dir(&req.output_dir) {
        Ok(d) => d,
        Err(e) => {
            *BUSY.lock().unwrap_or_else(|err| err.into_inner()) = false;
            return Err(e);
        }
    };
    // 记住选择：音色库要一直扫这个目录，不然重启之后训好的音色就「消失」了。
    let _ = crate::config::set_train_output_dir(root, &out_dir);
    req.output_dir = out_dir;
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
            "output_dir": req.output_dir,
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
        "output_dir": req.output_dir,
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
                fail = Some({
                    let m = crate::i18n::t_worker_msg(&v);
                    if m.is_empty() {
                        crate::i18n::t("s.60a21a8105")
                    } else {
                        m
                    }
                })
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
        // 一次训练留下的切片 / 音高 / 特征动辄几个 GB，而用户完全看不见。
        // 训练刚跑完是唯一一个他会读这句话的时刻。只报数，不自动删。
        "leftover_bytes": stage_artifact_bytes(&exp_root(root).join(req.exp.trim())),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 后缀表和 Python 那份必须逐字一致。
    ///
    /// 界面报「找到 120 个音频」而预处理只认 80 个，用户会拿这个假数字判断数据
    /// 集够不够。两边各写一份就一定会漂，所以这里直接读 Python 源码来比。
    /// 「另存的小模型」和正式权重只差一个后缀段。认错了就是把用户训练的最终
    /// 成果删了 —— 这条判据必须窄。
    #[test]
    fn epoch_snapshots_are_told_apart_from_the_final_weight() {
        assert!(is_epoch_snapshot("miku", "miku_e12_s3456.pth"));
        assert!(is_epoch_snapshot("miku", "miku_e1_s1.pth"));
        // 正式权重：删了不可再生。
        assert!(!is_epoch_snapshot("miku", "miku.pth"));
        // 别的实验的东西不归这次清理管。
        assert!(!is_epoch_snapshot("miku", "rin_e12_s3456.pth"));
        // 形似但不是：缺 step、缺数字、后缀不对。
        assert!(!is_epoch_snapshot("miku", "miku_e12.pth"));
        assert!(!is_epoch_snapshot("miku", "miku_e_s1.pth"));
        assert!(!is_epoch_snapshot("miku", "miku_e12_s34.index"));
        // 名字里正好带 _e.._s.. 的音色不能被误伤。
        assert!(!is_epoch_snapshot("miku", "miku_extra.pth"));
    }

    #[test]
    fn training_checkpoints_are_matched_by_their_own_shape() {
        assert!(is_train_checkpoint("G_35200.pth"));
        assert!(is_train_checkpoint("D_0.pth"));
        assert!(!is_train_checkpoint("miku.pth"));
        assert!(!is_train_checkpoint("G.pth"));
        assert!(!is_train_checkpoint("Gundam_1.pth"));
        assert!(!is_train_checkpoint("added_miku.index"));
    }

    /// 扫描给出的数字必须就是删除会释放的数字，而且不该删的不能出现在清单里。
    #[test]
    fn the_cleanup_scan_and_apply_agree_and_spare_everything_irreplaceable() {
        let root = std::env::temp_dir().join("rvcf-cleanup");
        let _ = std::fs::remove_dir_all(&root);
        let exp = root.join("logs").join("miku");
        let weights = root.join("assets").join("weights");
        std::fs::create_dir_all(exp.join("1_16k_wavs")).unwrap();
        std::fs::create_dir_all(&weights).unwrap();
        std::fs::write(exp.join("1_16k_wavs").join("a.wav"), vec![0u8; 300]).unwrap();
        std::fs::write(exp.join("G_100.pth"), vec![0u8; 200]).unwrap();
        std::fs::write(exp.join("D_100.pth"), vec![0u8; 200]).unwrap();
        std::fs::write(exp.join("added_miku.index"), vec![0u8; 7]).unwrap();
        std::fs::write(exp.join("train.log"), vec![0u8; 5]).unwrap();
        std::fs::write(weights.join("miku_e5_s50.pth"), vec![0u8; 100]).unwrap();
        std::fs::write(weights.join("miku.pth"), vec![0u8; 999]).unwrap();

        let scan = cleanup_scan(&root);
        let row = &scan.as_array().unwrap()[0];
        assert_eq!(row["exp"], "miku");
        assert_eq!(row["kinds"]["snapshots"]["bytes"].as_u64(), Some(100));
        assert_eq!(row["kinds"]["checkpoints"]["bytes"].as_u64(), Some(400));
        assert_eq!(row["kinds"]["dataset"]["bytes"].as_u64(), Some(300));
        assert_eq!(row["total_bytes"].as_u64(), Some(800));

        // 只勾两类，第三类必须原样留着。
        let freed = cleanup_apply(
            &root,
            "miku",
            &["snapshots".to_string(), "checkpoints".to_string()],
        )
        .unwrap();
        assert_eq!(freed, 500);
        assert!(!weights.join("miku_e5_s50.pth").exists());
        assert!(!exp.join("G_100.pth").exists());
        assert!(exp.join("1_16k_wavs").join("a.wav").is_file(), "没勾的类别不能动");
        assert!(weights.join("miku.pth").is_file(), "正式权重永远不动");
        assert!(exp.join("added_miku.index").is_file(), "索引永远不动");
        assert!(exp.join("train.log").is_file(), "日志永远不动");

        // 认不出来的类别名直接忽略，不做任何事。
        assert_eq!(cleanup_apply(&root, "miku", &["everything".to_string()]).unwrap(), 0);

        let _ = std::fs::remove_dir_all(&root);
    }

    /// 删中间产物这件事，删错一次就是用户几十分钟白跑。所以钉死两件：
    /// 该删的一个不剩，不该删的一个不碰。
    #[test]
    fn resetting_stages_removes_only_the_regenerable_artifacts() {
        let root = std::env::temp_dir().join("rvcf-reset-stages");
        let _ = std::fs::remove_dir_all(&root);
        let exp = root.join("logs").join("miku");
        std::fs::create_dir_all(exp.join("1_16k_wavs")).unwrap();
        std::fs::create_dir_all(exp.join("2a_f0")).unwrap();
        std::fs::create_dir_all(exp.join("3_feature768")).unwrap();
        std::fs::write(exp.join("1_16k_wavs").join("a.wav"), vec![0u8; 100]).unwrap();
        std::fs::write(exp.join("2a_f0").join("a.npy"), vec![0u8; 50]).unwrap();
        std::fs::write(exp.join("filelist.txt"), b"x").unwrap();
        // 这三样不可再生，绝不能碰。
        std::fs::write(exp.join("G_2333.pth"), b"snapshot").unwrap();
        std::fs::write(exp.join("added_miku.index"), b"index").unwrap();
        std::fs::write(exp.join("train.log"), b"log").unwrap();

        assert_eq!(stage_artifact_bytes(&exp), 151);
        let freed = reset_stages(&root, "miku").unwrap();
        assert_eq!(freed, 151);
        assert!(!exp.join("1_16k_wavs").exists());
        assert!(!exp.join("2a_f0").exists());
        assert!(!exp.join("filelist.txt").exists());
        assert!(exp.join("G_2333.pth").is_file(), "训练存档不能删");
        assert!(exp.join("added_miku.index").is_file(), "索引不能删");
        assert!(exp.join("train.log").is_file(), "日志不能删");

        let _ = std::fs::remove_dir_all(&root);
    }

    /// 实验名里带路径分隔符时必须拒绝 —— 这是删除操作，`../..` 不能有第二种解读。
    #[test]
    fn resetting_refuses_anything_that_could_escape_the_experiment_folder() {
        let root = std::env::temp_dir().join("rvcf-reset-escape");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("logs")).unwrap();
        for bad in ["", "   ", "..", ".", "../mute", "a/b", "a\\b", "C:x"] {
            assert!(reset_stages(&root, bad).is_err(), "{bad:?} 应该被拒绝");
        }
        // 不存在的实验也拒绝，而不是「删了 0 字节」假装成功。
        assert!(reset_stages(&root, "nope").is_err());
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 判据必须跟 preprocess.py 写日志的格式对上。
    ///
    /// 26.8.20 那位的实验里，2038 个文件的日志就长这样 —— 每个文件一行，
    /// 成功写 Success，读不进来写整条 traceback。
    #[test]
    fn the_preprocess_tally_matches_what_preprocess_py_writes() {
        let dir = std::env::temp_dir().join("rvcf-preprocess-tally");
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let log = dir.join("preprocess.log");
        std::fs::write(
            &log,
            "start preprocess\n             D:/ds/a.wav\t-> Success\n             D:/ds/b.m4a\t-> Traceback (most recent call last):\n             \x20 File \"x.py\", line 1\n             D:/ds/c.wav\t-> Success\n             end preprocess\n",
        )
        .unwrap();
        // traceback 后面那几行缩进的栈帧不能被重复计数。
        assert_eq!(preprocess_tally(&log), (2, 1));
        // 日志不在（还没跑过预处理）不是错误，是 0/0。
        assert_eq!(preprocess_tally(&dir.join("nope.log")), (0, 0));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn the_audio_extensions_match_the_python_side() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..");
        let src = std::fs::read_to_string(root.join("tools").join("train_worker.py"))
            .expect("train_worker.py 不在预期位置");
        let line = src
            .lines()
            .find(|l| l.starts_with("AUDIO_EXT"))
            .expect("train_worker.py 里没有 AUDIO_EXT");
        for ext in DATASET_AUDIO_EXT {
            assert!(line.contains(&format!("\".{ext}\"")), "Python 那边没有 {ext}：{line}");
        }
        // 反向：Python 多出来的也要在这边补上。
        let py_count = line.matches('"').count() / 2;
        assert_eq!(py_count, DATASET_AUDIO_EXT.len(), "两边数量对不上：{line}");
    }

    #[test]
    fn a_dataset_scan_counts_audio_recursively_and_ignores_the_rest() {
        let base = std::env::temp_dir().join("rvcf-scan-dataset");
        let _ = std::fs::remove_dir_all(&base);
        std::fs::create_dir_all(base.join("歌手A")).unwrap();
        std::fs::write(base.join("a.wav"), b"1234").unwrap();
        std::fs::write(base.join("歌手A").join("b.MP3"), b"12").unwrap();
        std::fs::write(base.join("cover.jpg"), b"x").unwrap();
        std::fs::write(base.join("readme.txt"), b"x").unwrap();

        let v = scan_dataset(&base);
        // 子目录里的也算 —— 用户按歌手分文件夹是常态，preprocess 也是 os.walk。
        assert_eq!(v["files"].as_u64(), Some(2));
        // 大小写不敏感：.MP3 也是音频。
        assert_eq!(v["by_ext"]["mp3"].as_u64(), Some(1));
        assert_eq!(v["by_ext"]["wav"].as_u64(), Some(1));
        assert_eq!(v["other_files"].as_u64(), Some(2));
        assert_eq!(v["total_bytes"].as_u64(), Some(6));

        // 空目录报 0，不是报错 —— 界面靠这个 0 把提示标红。
        let empty = base.join("空的");
        std::fs::create_dir_all(&empty).unwrap();
        assert_eq!(scan_dataset(&empty)["files"].as_u64(), Some(0));

        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn an_empty_output_dir_means_the_default_library() {
        assert_eq!(normalize_output_dir("").unwrap(), "");
        assert_eq!(normalize_output_dir("   ").unwrap(), "");
    }

    #[test]
    fn a_relative_output_dir_is_rejected() {
        // 相对路径跟着进程的 cwd 走。训了几小时，音色落在谁也找不到的地方，
        // 而用户看到的只是「训练完成」。
        let _g = crate::i18n::testing::pin("zh-CN");
        for bad in ["models", "./out", "..\\elsewhere"] {
            assert!(normalize_output_dir(bad).is_err(), "should reject {bad:?}");
        }
    }

    #[test]
    fn an_absolute_output_dir_is_created_up_front() {
        // 建不出来就得当场报错 —— 拔掉的移动硬盘、写保护的目录，等训完再
        // 发现就是几小时白烧。
        let _g = crate::i18n::testing::pin("zh-CN");
        let base = std::env::temp_dir().join("rvcf-train-out").join("nested");
        let _ = std::fs::remove_dir_all(std::env::temp_dir().join("rvcf-train-out"));
        let got = normalize_output_dir(&base.to_string_lossy()).expect("should accept");
        assert!(Path::new(&got).is_dir(), "目录应当已经建好：{got}");
        let _ = std::fs::remove_dir_all(std::env::temp_dir().join("rvcf-train-out"));
    }

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
    fn an_unfinished_train_log_reports_where_it_stopped() {
        // 壳被强杀 → 日志里没有 `=== done (…) ===`，界面据此告诉用户
        // 「上次断在第几轮、切片还在、可以续跑」。
        let text = "=== train run 2026-08-18 11:42:56 ===\n                    {\n  \"exp\": \"tomori\",\n  \"total_epoch\": 200\n}\n                    2026-08-18 11:43:22 progress stage stage=train 0/200 准备训练…\n                    2026-08-18 11:58:45 progress stage stage=train 99/200 第 99 / 200 轮\n";
        assert_eq!(parse_interrupted(text), Some(("tomori".into(), 99, 200)));
    }

    #[test]
    fn a_run_that_never_reached_epoch_one_is_not_worth_a_prompt() {
        // 只跑到「准备训练」就断了，没有中间产物可续，提示反而添乱。
        let text = "{\n  \"exp\": \"tomori\"\n}\n                    progress stage stage=train 0/200 准备训练…\n";
        assert_eq!(parse_interrupted(text), None);
    }

    #[test]
    fn a_log_without_an_exp_name_is_ignored() {
        let text = "progress stage stage=train 9/200 第 9 / 200 轮\n";
        assert_eq!(parse_interrupted(text), None);
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
            output_dir: String::new(),
        };
        // 没 Runtime 就该在这里停，而不是起个进程再失败。
        assert!(preflight(&base, &req).is_err());
        let _ = std::fs::remove_dir_all(&base);
    }
}
