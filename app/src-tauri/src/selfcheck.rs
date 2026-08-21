//! 出诊断包之前，先把包里已经能看出来的问题说出来。
//!
//! 支援这半年收到的包里，相当一部分的结论用户自己就能得出：选错了模型、数据集
//! 一个音频都没读进去、上一次训练是被显存不足带走的、引擎其实是被系统杀掉的。
//! 这些都写在包里，只是没人替他读。
//!
//! 规则只陈述事实和数字，不下断言 —— 「音高 616/3884」是事实，「你的训练白跑
//! 了」不是。每条都带证据（哪个文件、哪一行），支援能顺着证据自己复核。

use std::path::Path;

use serde::Serialize;
use serde_json::Value;

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct Evidence {
    pub file: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub line: Option<u64>,
    pub text: String,
}

impl Evidence {
    fn new(file: impl Into<String>, text: impl Into<String>) -> Self {
        Self { file: file.into(), line: None, text: text.into() }
    }
    fn at(file: impl Into<String>, line: u64, text: impl Into<String>) -> Self {
        Self { file: file.into(), line: Some(line), text: text.into() }
    }
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct Finding {
    pub code: &'static str,
    pub level: &'static str,
    pub title: String,
    pub evidence: Vec<Evidence>,
}

pub const ERROR: &str = "error";
pub const WARN: &str = "warn";
pub const INFO: &str = "info";

fn rank(level: &str) -> u8 {
    match level {
        ERROR => 0,
        WARN => 1,
        _ => 2,
    }
}

/// 跑一遍全部规则，严重的排前面。
pub fn run(root: &Path) -> Vec<Finding> {
    let cfg = crate::config::read(root);
    let status = crate::protocol::read_status(root);
    let mut out: Vec<Finding> = Vec::new();

    out.extend(known_issue_hits(root));
    out.extend(engine_killed());
    out.extend(chosen_model(&cfg));
    out.extend(train_experiments(root));
    out.extend(pretrained(root));
    out.extend(disk(root));
    out.extend(audio(&cfg, &status));

    out.sort_by_key(|f| rank(f.level));
    out
}

// ------------------------------------------------------------ 已知问题

/// 1.1 和 1.2 共用同一套判断：命中的已知问题也算一条结论，跟着诊断包一起走。
/// 支援打开 info.json 就能看到「这台机器命中了 realtek-asio-enum-crash」，
/// 不用再从显卡声卡列表里自己认。
fn known_issue_hits(root: &Path) -> Vec<Finding> {
    crate::known_issues::hits(root)
        .into_iter()
        .map(|h| Finding {
            code: "known_issue",
            level: match h.level.as_str() {
                "error" => ERROR,
                "info" => INFO,
                _ => WARN,
            },
            title: h.title,
            evidence: vec![Evidence::new("known_issues.json", h.id)],
        })
        .collect()
}

// ---------------------------------------------------------------- 引擎被杀

fn engine_killed() -> Vec<Finding> {
    if !crate::crash::saw_fatal_exit() {
        return Vec::new();
    }
    let mut ev = Vec::new();
    let asio = crate::crash::asio_drivers();
    if !asio.is_empty() {
        ev.push(Evidence::new(
            r"HKLM\SOFTWARE\ASIO",
            asio.join("、"),
        ));
    }
    vec![Finding {
        code: "engine.killed_by_system",
        level: ERROR,
        title: crate::i18n::t("s.chkWorkerKilled"),
        evidence: ev,
    }]
}

// ---------------------------------------------------------------- 选错模型

/// 训练存档的文件名长这样：`G_35200.pth` / `D_2333.pth`。
///
/// 26.8.20 那位选中了 `G_35200.pth`，四次转换四次 `KeyError: 'config'`。两者都
/// 叫 .pth，一个 452 MB 一个 57 MB，用户分不出来很正常 —— 但文件名是分得出的。
pub fn looks_like_training_snapshot(name: &str) -> bool {
    let stem = name.rsplit(['/', '\\']).next().unwrap_or(name);
    let Some(stem) = stem.strip_suffix(".pth") else {
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

fn chosen_model(cfg: &serde_json::Map<String, Value>) -> Vec<Finding> {
    let path = cfg.get("pth_path").and_then(|v| v.as_str()).unwrap_or("");
    if path.is_empty() || !looks_like_training_snapshot(path) {
        return Vec::new();
    }
    let name = path.rsplit(['/', '\\']).next().unwrap_or(path).to_string();
    vec![Finding {
        code: "model.training_snapshot",
        level: ERROR,
        title: crate::i18n::te("s.chkSnapshotModel", &name),
        evidence: vec![Evidence::new("configs/inuse/config.json", format!("pth_path = {path}"))],
    }]
}

// ---------------------------------------------------------------- 训练产物

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StageCounts {
    pub slices: u64,
    pub f0: u64,
    pub feature: u64,
}

/// 三个阶段的产物数目对不上，就说明上一次是中途停的。
///
/// 26.8.20 那位：切片 3884、音高 616、特征 0，而续跑的判据是「目录非空就算做
/// 完」，于是音高整步被跳过，filelist 取交集只剩 618 行 —— 用户以为在拿 3884
/// 条数据训练，实际只用了 16%，界面上一个字都没提。判据已经改了，但已经存在的
/// 半份产物还躺在盘上，出包的时候该说一声。
pub fn stage_mismatch(c: StageCounts) -> bool {
    c.slices > 0 && (c.f0 != c.slices || c.feature != c.slices)
}

/// preprocess.log 里失败了几个。数 `Traceback` 就够 —— 每个读不进来的文件
/// ffmpeg 都会甩一条。
pub fn preprocess_failures(log: &str) -> (u64, Option<(u64, String)>) {
    let mut n = 0u64;
    let mut first: Option<(u64, String)> = None;
    for (i, line) in log.lines().enumerate() {
        if line.contains("Traceback") || line.contains("-> Traceback") {
            n += 1;
            if first.is_none() {
                first = Some((i as u64 + 1, line.trim().chars().take(200).collect()));
            }
        }
    }
    (n, first)
}

/// train.log 的尾巴是不是显存不足。
///
/// 只看尾巴：上一轮的显存不足不能栽给这一轮。
pub fn train_log_oom(tail: &str) -> Option<String> {
    for line in tail.lines().rev() {
        if line.contains("OutOfMemoryError")
            || line.contains("CUDA out of memory")
            || line.contains("out of memory")
        {
            return Some(line.trim().chars().take(200).collect());
        }
    }
    None
}

fn train_experiments(root: &Path) -> Vec<Finding> {
    let mut out = Vec::new();
    let exp_root = crate::train::exp_root(root);
    let Ok(rd) = std::fs::read_dir(&exp_root) else {
        return out;
    };
    let mut dirs: Vec<_> = rd
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.is_dir())
        .collect();
    dirs.sort();
    for dir in dirs {
        let exp = dir
            .file_name()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_default();
        let counts = StageCounts {
            slices: count_dir(&dir.join("1_16k_wavs")),
            f0: count_dir(&dir.join("2a_f0")),
            feature: count_dir(&dir.join("3_feature768")),
        };
        if stage_mismatch(counts) {
            out.push(Finding {
                code: "train.stage_mismatch",
                level: WARN,
                title: crate::i18n::tn(
                    "s.chkStageMismatch",
                    &[
                        &exp,
                        &counts.slices.to_string(),
                        &counts.f0.to_string(),
                        &counts.feature.to_string(),
                    ],
                ),
                evidence: vec![Evidence::new(
                    format!("logs/{exp}/"),
                    format!(
                        "1_16k_wavs={} 2a_f0={} 3_feature768={}",
                        counts.slices, counts.f0, counts.feature
                    ),
                )],
            });
        }
        if let Ok(text) = std::fs::read_to_string(dir.join("preprocess.log")) {
            let (n, first) = preprocess_failures(&text);
            if n > 0 {
                let mut ev = Vec::new();
                if let Some((line, txt)) = first {
                    ev.push(Evidence::at(format!("logs/{exp}/preprocess.log"), line, txt));
                }
                out.push(Finding {
                    code: "train.preprocess_failures",
                    level: WARN,
                    title: crate::i18n::t2("s.chkPreprocessFail", &exp, &n),
                    evidence: ev,
                });
            }
        }
        let tail = crate::logging::tail_lines(&dir.join("train.log"), 80, 64 * 1024);
        if let Some(line) = train_log_oom(&tail) {
            out.push(Finding {
                code: "train.out_of_memory",
                level: ERROR,
                title: crate::i18n::te("s.chkOom", &exp),
                evidence: vec![Evidence::new(format!("logs/{exp}/train.log"), line)],
            });
        }
    }
    out
}

fn count_dir(p: &Path) -> u64 {
    std::fs::read_dir(p)
        .map(|rd| rd.flatten().filter(|e| e.path().is_file()).count() as u64)
        .unwrap_or(0)
}

// ---------------------------------------------------------------- 底模

fn pretrained(root: &Path) -> Vec<Finding> {
    let st = crate::train::status(root);
    let Some(list) = st.get("pretrained").and_then(|v| v.as_array()) else {
        return Vec::new();
    };
    let missing: Vec<String> = list
        .iter()
        .filter(|e| e.get("ready").and_then(|v| v.as_bool()) == Some(false))
        .filter_map(|e| e.get("sample_rate").and_then(|v| v.as_str()).map(String::from))
        .collect();
    if missing.is_empty() || missing.len() == list.len() {
        // 一个都不缺，或者一个都没有 —— 后者是「还没装运行时」，不是这条规则的事。
        return Vec::new();
    }
    vec![Finding {
        code: "assets.pretrained_partial",
        level: INFO,
        title: crate::i18n::te("s.chkPretrainedPartial", &missing.join("、")),
        evidence: vec![Evidence::new("assets/pretrained_v2/", missing.join("、"))],
    }]
}

// ---------------------------------------------------------------- 磁盘

fn disk(root: &Path) -> Vec<Finding> {
    let Some(gb) = free_space_gb(root) else {
        return Vec::new();
    };
    if gb >= 10.0 {
        return Vec::new();
    }
    vec![Finding {
        code: "disk.low",
        level: WARN,
        title: crate::i18n::te("s.chkDiskLow", &format!("{gb:.1}")),
        evidence: vec![Evidence::new(root.to_string_lossy(), format!("{gb:.1} GB"))],
    }]
}

fn free_space_gb(root: &Path) -> Option<f64> {
    crate::paths::free_space_bytes(root).map(|b| b as f64 / 1024.0 / 1024.0 / 1024.0)
}

// ---------------------------------------------------------------- 音频

/// MME 是 Windows 上最老那套接口，缓冲给得很厚。延迟高到这个份上时，换 WASAPI
/// 基本都能明显降下来 —— 但这只是「通常」，所以是提示不是错误。
const MME_DELAY_MS: i64 = 600;
/// 偶尔一两次欠载正常（显卡被别的程序抢一下）。持续累积才是真跟不上。
const UNDERRUN_MANY: i64 = 20;

fn audio(cfg: &serde_json::Map<String, Value>, status: &Value) -> Vec<Finding> {
    let mut out = Vec::new();
    let api = status
        .get("sg_hostapi")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .or_else(|| cfg.get("sg_hostapi").and_then(|v| v.as_str()))
        .unwrap_or("");
    let delay = status
        .get("real_delay_ms")
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    if api.eq_ignore_ascii_case("MME") && delay > MME_DELAY_MS {
        out.push(Finding {
            code: "audio.mme_high_delay",
            level: INFO,
            title: crate::i18n::te("s.chkMmeDelay", &delay),
            evidence: vec![Evidence::new(
                "runtime_control/status.json",
                format!("sg_hostapi=MME real_delay_ms={delay}"),
            )],
        });
    }
    let underrun = status.get("underrun").and_then(|v| v.as_i64()).unwrap_or(0);
    if underrun > UNDERRUN_MANY {
        out.push(Finding {
            code: "audio.underrun",
            level: WARN,
            title: crate::i18n::te("s.chkUnderrun", &underrun),
            evidence: vec![Evidence::new(
                "runtime_control/status.json",
                format!("underrun={underrun}"),
            )],
        });
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn training_snapshots_are_told_apart_from_voice_models() {
        // 26.8.20 那位选中的那个。
        assert!(looks_like_training_snapshot(r"D:\a\User_Data\models\G_35200\G_35200.pth"));
        assert!(looks_like_training_snapshot("D_2333.pth"));
        assert!(looks_like_training_snapshot("G_0.pth"));
        // 音色模型不能被误判 —— 误判一次就是「我的模型明明能用却被说成不对」。
        assert!(!looks_like_training_snapshot("tp-miku.pth"));
        assert!(!looks_like_training_snapshot("G.pth"));
        assert!(!looks_like_training_snapshot("Gundam_x.pth"));
        assert!(!looks_like_training_snapshot("G_35200.index"));
        assert!(!looks_like_training_snapshot("my_G_35200.pth"));
    }

    #[test]
    fn stage_counts_must_all_match_the_slices() {
        // 26.8.20 那位的真实数字。
        assert!(stage_mismatch(StageCounts { slices: 3884, f0: 616, feature: 0 }));
        assert!(stage_mismatch(StageCounts { slices: 100, f0: 100, feature: 99 }));
        assert!(!stage_mismatch(StageCounts { slices: 100, f0: 100, feature: 100 }));
        // 还没预处理过的实验不该报 —— 那不是「半份产物」，是「还没开始」。
        assert!(!stage_mismatch(StageCounts { slices: 0, f0: 0, feature: 0 }));
    }

    #[test]
    fn preprocess_failures_are_counted_with_the_first_one_as_evidence() {
        let log = "start\nfoo -> Traceback (most recent call last)\nbar ok\nbaz -> Traceback (x)\n";
        let (n, first) = preprocess_failures(log);
        assert_eq!(n, 2);
        let (line, text) = first.unwrap();
        assert_eq!(line, 2);
        assert!(text.contains("Traceback"));
        assert_eq!(preprocess_failures("all good\n").0, 0);
    }

    #[test]
    fn only_the_tail_of_train_log_decides_the_oom_verdict() {
        assert!(train_log_oom("Epoch 1\ntorch.cuda.OutOfMemoryError: CUDA out of memory\n").is_some());
        assert!(train_log_oom("Epoch 1\nEpoch 2\n").is_none());
        // 上一轮炸过、这一轮跑完了：调用方只喂尾巴，所以这里拿到的就是干净的尾巴。
        assert!(train_log_oom("====> Epoch: 500\n").is_none());
    }

    #[test]
    fn a_high_mme_delay_is_a_hint_and_many_underruns_are_a_warning() {
        let cfg = serde_json::Map::new();
        let st = json!({"sg_hostapi": "MME", "real_delay_ms": 900, "underrun": 28});
        let f = audio(&cfg, &st);
        assert_eq!(f.len(), 2);
        assert_eq!(f[0].code, "audio.mme_high_delay");
        assert_eq!(f[0].level, INFO);
        assert_eq!(f[1].code, "audio.underrun");
        assert_eq!(f[1].level, WARN);

        // WASAPI 上同样的延迟不报 —— 这条规则说的是接口，不是延迟本身。
        let st2 = json!({"sg_hostapi": "Windows WASAPI", "real_delay_ms": 900, "underrun": 0});
        assert!(audio(&cfg, &st2).is_empty());
    }

    #[test]
    fn findings_are_sorted_with_the_worst_first() {
        let mut v = vec![
            Finding { code: "a", level: INFO, title: "i".into(), evidence: vec![] },
            Finding { code: "b", level: ERROR, title: "e".into(), evidence: vec![] },
            Finding { code: "c", level: WARN, title: "w".into(), evidence: vec![] },
        ];
        v.sort_by_key(|f| rank(f.level));
        assert_eq!(v.iter().map(|f| f.code).collect::<Vec<_>>(), ["b", "c", "a"]);
    }
}
