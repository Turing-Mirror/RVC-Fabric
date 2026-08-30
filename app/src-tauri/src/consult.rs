//! 咨询包：用户申请专业优化时，软件替他打的那个 zip。
//!
//! ## 包里必须有声音
//!
//! 这个包原来只装了 `consult.json`（版本、显卡、当前参数）和音色目录里那几个
//! 小文本，**一个音频都没有**。而调参从第一步起就要听声音：用户的嗓音是什么样、
//! 用当前参数转出来是什么样、离目标角色差在哪里 —— 没有这两段录音，
//! 收到包的那一头什么都做不了。
//!
//! 所以现在包里有三样新东西：
//!
//! * `raw/<语言>.wav` —— 用户照着稿子念的原声；
//! * `converted/<语言>.wav` —— 用他**当前这套参数**转过的同一段；
//! * `perf/*.json` —— 这台机器的实时性能记录。
//!
//! 第三样不是凑数：调出来的参数必须在**他那台机器**上跑得动。
//! 调出一组神仙参数而他的显卡带不动，等于没调。
//!
//! ## 为什么要念指定的稿子
//!
//! 让用户随便说，收上来的东西五花八门：有人念三个字，有人全是气声，
//! 有人背景里在放歌。同一段文本才能在用户之间横向比较，也才能保证音素、
//! 语调、长句这几样都覆盖到。稿子见 [`SCRIPT`]。
//!
//! ## 录音是一种语言一条，不是一句一条
//!
//! 四段合起来读大约一分钟。拆成四次录音要点八次按钮，而分句这件事收到包之后
//! 按静音切开就行 —— 把麻烦留给自己，不留给用户。

use std::path::{Path, PathBuf};

use serde_json::{json, Value};
use tauri::AppHandle;

/// 支持的朗读语言。顺序就是界面上的顺序。
pub const LANGS: [&str; 3] = ["zh", "en", "ja"];

/// 朗读稿。
///
/// 四段各有分工，不是随便挑的：
///
/// | 段 | 覆盖 |
/// | --- | --- |
/// | 1 | 短句、日常语调、句末下降 |
/// | 2 | 音素覆盖（英文用全字母句，日文用いろは歌） |
/// | 3 | 书面语，声调起伏大，长元音多 |
/// | 4 | 十几秒的连续朗读 —— 长句里的音色漂移只有这种长度才测得出来 |
///
/// 第 4 段是莎士比亚十四行诗第 54 首前四行。英文是原文（公有领域）；
/// 中文和日文是自译，因为现有名家译本仍在版权保护期内，随软件分发不合适。
///
/// **不需要覆盖高低音域**：角色能唱多高多低是模型自己的属性，
/// 靠扫变调值测，跟用户念什么无关。
pub fn script() -> Value {
    json!({
        "langs": LANGS,
        "zh": {
            "label": "中文",
            "lines": [
                "有一只僵尸在你的草坪上。",
                "有一只狐狸跳过了一条懒狗。",
                "人生若只如初见，何事秋风悲画扇。",
                "真诚为美添上温柔的装点，\n美因此显得更美了多少！\n玫瑰本已姣好，我们却以为它更姣好，\n只因有一缕芬芳活在它里面。",
            ],
        },
        "en": {
            "label": "English",
            "lines": [
                "There's a zombie on your lawn.",
                "The quick brown fox jumps over the lazy dog.",
                "If life were only as it was when we first met, why must the autumn wind grieve the painted fan?",
                "O, how much more doth beauty beauteous seem\nBy that sweet ornament which truth doth give!\nThe rose looks fair, but fairer we it deem\nFor that sweet odour which doth in it live.",
            ],
        },
        "ja": {
            "label": "日本語",
            "lines": [
                "あなたの芝生にゾンビがいる。",
                "いろはにほへと ちりぬるを わかよたれそ つねならむ\nうゐのおくやま けふこえて あさきゆめみし ゑひもせす",
                "人生がただ初めて出会った時のままであったなら、なぜ秋風は絵扇を悲しませるのだろう。",
                "真実という優しい飾りを添えられたとき、\n美はどれほど美しく見えることか。\n薔薇はもとより美しい。それでもなお美しいと思われるのは、\nその内に生きる甘い香りのゆえである。",
            ],
            // 罗马音只给日文，供不会读假名的用户参照。
            "romaji": [
                "Anata no shibafu ni zonbi ga iru.",
                "Iro wa nioedo chirinuru o / waga yo tare zo tsune naran /\nui no okuyama kyō koete / asaki yume miji ei mo sezu",
                "Jinsei ga tada hajimete deatta toki no mama de atta nara, naze akikaze wa e-ōgi o kanashimaseru no darō.",
                "Shinjitsu to iu yasashii kazari o soerareta toki,\nbi wa dore hodo utsukushiku mieru koto ka.\nBara wa motoyori utsukushii. Soredemo nao utsukushii to omowareru no wa,\nsono uchi ni ikiru amai kaori no yue de aru.",
            ],
        },
    })
}

/// `lang` 是不是我们认的那三个。
///
/// 这个值从界面来，而它下面直接跟着一个目录名 —— 不校验的话
/// `../../` 就能把录音写到别处去。
pub fn valid_lang(lang: &str) -> bool {
    LANGS.contains(&lang)
}

fn consult_root(root: &Path) -> PathBuf {
    crate::paths::user_data(root).join("consult")
}

/// 某种语言的原声录音目录。**一种语言一个目录**，里面只留最新那一条。
///
/// 用目录而不是固定文件名，是因为录音那条链路（`sts::record`）自己决定文件名。
/// 给它一个空目录，产物就是里面唯一的文件。
pub fn raw_dir(root: &Path, lang: &str) -> PathBuf {
    consult_root(root).join("raw").join(lang)
}

/// 目录里唯一那个 wav。空目录返回 None。
fn only_wav(dir: &Path) -> Option<PathBuf> {
    let mut found: Option<PathBuf> = None;
    for e in std::fs::read_dir(dir).ok()?.flatten() {
        let p = e.path();
        if p.extension().and_then(|x| x.to_str()).map(|x| x.eq_ignore_ascii_case("wav"))
            != Some(true)
        {
            continue;
        }
        // 有多个就取最新的：上一次录到一半崩了会留下残骸。
        let newer = match (&found, p.metadata().and_then(|m| m.modified()).ok()) {
            (None, _) => true,
            (Some(old), Some(t)) => old
                .metadata()
                .and_then(|m| m.modified())
                .map(|ot| t > ot)
                .unwrap_or(false),
            _ => false,
        };
        if newer {
            found = Some(p);
        }
    }
    found
}

/// 开始录一种语言。旧的先删掉 —— 重录就是重录，不该留两条让人猜用了哪条。
pub fn record_start(app: &AppHandle, root: &Path, lang: &str) -> Result<Value, String> {
    if !valid_lang(lang) {
        return Err(format!("unknown language: {lang}"));
    }
    let dir = raw_dir(root, lang);
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    crate::sts::record(app, root, &dir.to_string_lossy())
}

/// 现在录到什么程度了。界面据此显示每种语言的勾。
pub fn state(root: &Path) -> Value {
    let mut done = serde_json::Map::new();
    for lang in LANGS {
        let entry = only_wav(&raw_dir(root, lang)).map(|p| {
            json!({
                "path": p.to_string_lossy(),
                "bytes": std::fs::metadata(&p).map(|m| m.len()).unwrap_or(0),
            })
        });
        done.insert(lang.to_string(), entry.unwrap_or(Value::Null));
    }
    json!({
        "langs": LANGS,
        "recorded": Value::Object(done),
        "script": script(),
    })
}

/// 把录音清掉（用户想重来）。
pub fn clear(root: &Path) {
    let _ = std::fs::remove_dir_all(consult_root(root));
}

/// 最近几份实时性能报告。
///
/// 交付的参数必须在**用户那台机器**上跑得动，而只有他那台机器知道跑不跑得动。
/// 报告由实时变声停流时自己写下（`tools/perf_report.py`），这里只是捡走。
fn perf_reports(root: &Path) -> Vec<PathBuf> {
    let dir = crate::paths::user_data(root).join("perf_reports");
    let mut out: Vec<PathBuf> = std::fs::read_dir(&dir)
        .into_iter()
        .flatten()
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|x| x.to_str()) == Some("json"))
        .collect();
    // 新的在前，最多带三份：够看出趋势，又不会把包撑大。
    out.sort_by_key(|p| {
        std::cmp::Reverse(
            p.metadata()
                .and_then(|m| m.modified())
                .unwrap_or(std::time::SystemTime::UNIX_EPOCH),
        )
    });
    out.truncate(3);
    out
}

/// 录音是否齐备到可以出包。
///
/// **至少一种语言**即可 —— 稿子上写着推荐全念，但只念中文的人也该能下单。
pub fn has_any_recording(root: &Path) -> bool {
    LANGS.iter().any(|l| only_wav(&raw_dir(root, l)).is_some())
}

/// 用**用户当前这套参数**把每种语言的原声转一遍。
///
/// 为什么要转：收到包的那一头需要一个基线 —— 「他现在听到的是什么样」。
/// 没有这个基线，调完之后就没法回答「比原来好在哪」，报告里那句
/// 「相似度从 0.61 提到 0.79」也就无从谈起。
///
/// 转换走 `sts::run`（静音模式）：实时 worker 在跑就借它常驻的模型，
/// 不在就用冷路径的常驻进程。三种语言只付一次冷启动。
fn convert_all(app: &AppHandle, root: &Path) -> Vec<(String, PathBuf)> {
    let cfg = crate::config::read(root);
    let pth = cfg.get("pth_path").and_then(|v| v.as_str()).unwrap_or("").trim().to_string();
    if pth.is_empty() || !Path::new(&pth).is_file() {
        crate::logging::shell_log!("咨询包：没有选音色，跳过变声样本");
        return Vec::new();
    }
    let index = cfg.get("index_path").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let index_rate = cfg.get("index_rate").and_then(|v| v.as_f64()).unwrap_or(0.0);
    let pitch = cfg.get("pitch").and_then(|v| v.as_f64()).unwrap_or(0.0) as i32;
    let f0method = cfg
        .get("f0method")
        .and_then(|v| v.as_str())
        .filter(|s| !s.trim().is_empty())
        .unwrap_or("rmvpe")
        .to_string();

    let stage = consult_root(root).join("converted");
    let _ = std::fs::remove_dir_all(&stage);

    let mut out = Vec::new();
    for lang in LANGS {
        let Some(raw) = only_wav(&raw_dir(root, lang)) else {
            continue;
        };
        let dst_dir = stage.join(lang);
        if std::fs::create_dir_all(&dst_dir).is_err() {
            continue;
        }
        let opts = crate::sts::ConvertOpts {
            // 用户点的是「申请专业优化」，不是「语音转换」。
            // 不静音的话那一页会显示一个他没启动过的任务。
            quiet: true,
            ..Default::default()
        };
        let res = crate::sts::run(
            app,
            root,
            &raw.to_string_lossy(),
            &dst_dir.to_string_lossy(),
            pitch,
            &f0method,
            index_rate,
            &pth,
            &index,
            opts,
        );
        match res {
            Ok(v) => {
                if let Some(p) = v
                    .get("files")
                    .and_then(|x| x.as_array())
                    .and_then(|a| a.first())
                    .and_then(|x| x.as_str())
                    .map(PathBuf::from)
                    .filter(|p| p.is_file())
                {
                    out.push((lang.to_string(), p));
                }
            }
            // 一种语言转失败不该让整个包出不来 —— 原声照样有价值。
            Err(e) => crate::logging::shell_log!("咨询包：{lang} 变声样本失败：{e}"),
        }
    }
    out
}

/// 打包。
///
/// 顺序是有讲究的：**先转换再打包**。反过来的话，转换那几十秒里用户看着
/// 一个已经生成的 zip，会以为已经好了。
pub fn build(app: &AppHandle, root: &Path, note: &str) -> Result<PathBuf, String> {
    use std::io::Write;

    if !has_any_recording(root) {
        return Err(crate::i18n::t("s.consultNeedRecording"));
    }

    let converted = convert_all(app, root);

    let out_dir = crate::paths::user_data(root).join("consult_packs");
    std::fs::create_dir_all(&out_dir).map_err(|e| e.to_string())?;
    let stamp = chrono::Local::now().format("%Y%m%d_%H%M%S").to_string();
    let out = out_dir.join(format!("consult_{stamp}.zip"));

    let cfg = crate::config::read(root);
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

    let recorded: Vec<&str> = LANGS
        .iter()
        .copied()
        .filter(|l| only_wav(&raw_dir(root, l)).is_some())
        .collect();
    let meta = json!({
        // 收包那头按这个版本号判断该怎么解。加字段不用动它，改结构才动。
        "schema": 2,
        "app_version": crate::update::APP_VERSION,
        "note": note,
        "gpus": crate::provision::list_gpus(),
        "installed_variant": crate::provision::read_package_meta_variant(root),
        "config": Value::Object(cfg.clone()),
        "generated_at": stamp,
        "languages": recorded,
        "converted": converted.iter().map(|(l, _)| l.clone()).collect::<Vec<_>>(),
        "script": script(),
    });
    zip.start_file("consult.json", opts).map_err(|e| e.to_string())?;
    zip.write_all(serde_json::to_string_pretty(&meta).unwrap_or_default().as_bytes())
        .map_err(|e| e.to_string())?;

    // 原声。
    for lang in LANGS {
        if let Some(p) = only_wav(&raw_dir(root, lang)) {
            let bytes = std::fs::read(&p).map_err(|e| format!("{}: {e}", p.display()))?;
            zip.start_file(format!("raw/{lang}.wav"), opts).map_err(|e| e.to_string())?;
            zip.write_all(&bytes).map_err(|e| e.to_string())?;
        }
    }
    // 用当前参数转过的同一段。
    for (lang, p) in &converted {
        let bytes = std::fs::read(p).map_err(|e| format!("{}: {e}", p.display()))?;
        zip.start_file(format!("converted/{lang}.wav"), opts).map_err(|e| e.to_string())?;
        zip.write_all(&bytes).map_err(|e| e.to_string())?;
    }
    // 这台机器跑得动什么。
    for p in perf_reports(root) {
        let name = p.file_name().unwrap_or_default().to_string_lossy().to_string();
        if let Ok(text) = std::fs::read_to_string(&p) {
            zip.start_file(format!("perf/{name}"), opts).map_err(|e| e.to_string())?;
            zip.write_all(text.as_bytes()).map_err(|e| e.to_string())?;
        }
    }
    // 音色自己的 config.json 与 .tmvp 档案 —— 都是小文本。
    // **权重不进包**：几十上百兆，而且收包那头本来就有同一个模型。
    if let Some(dir) = model_dir {
        for entry in std::fs::read_dir(&dir).into_iter().flatten().flatten() {
            let p = entry.path();
            let ext = p.extension().and_then(|x| x.to_str()).unwrap_or("");
            if ext == "json" || ext == "tmvp" {
                if let Ok(text) = std::fs::read_to_string(&p) {
                    let name = p.file_name().unwrap_or_default().to_string_lossy().to_string();
                    zip.start_file(format!("voice/{name}"), opts).map_err(|e| e.to_string())?;
                    zip.write_all(text.as_bytes()).map_err(|e| e.to_string())?;
                }
            }
        }
    }

    zip.finish().map_err(|e| e.to_string())?;
    crate::logging::shell_log!(
        "咨询包已生成 {}（原声 {} 种语言，变声样本 {} 份）",
        out.display(),
        recorded.len(),
        converted.len()
    );
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(tag: &str) -> PathBuf {
        let p = crate::testutil::scratch(tag);
        let _ = std::fs::remove_dir_all(&p);
        std::fs::create_dir_all(crate::paths::user_data(&p)).unwrap();
        p
    }

    /// 语言直接跟着一个目录名走，不校验就能把录音写到别处去。
    #[test]
    fn a_language_cannot_escape_the_consult_dir() {
        assert!(valid_lang("zh") && valid_lang("en") && valid_lang("ja"));
        for bad in ["../../evil", "zh/../..", "", "ZH", "fr"] {
            assert!(!valid_lang(bad), "{bad} 不该被当成语言");
        }
    }

    /// 稿子必须三种语言各四段，且没有空段 —— 界面照着它画，
    /// 缺一段的话用户会对着一个空白格子发呆。
    #[test]
    fn the_script_is_complete() {
        let s = script();
        for lang in LANGS {
            let lines = s[lang]["lines"].as_array().expect("lines");
            assert_eq!(lines.len(), 4, "{lang} 应当有四段");
            for (i, l) in lines.iter().enumerate() {
                let text = l.as_str().unwrap_or("");
                assert!(!text.trim().is_empty(), "{lang} 第 {} 段是空的", i + 1);
            }
            assert!(!s[lang]["label"].as_str().unwrap_or("").is_empty());
        }
        // 日文另外带罗马音，段数要对得上。
        assert_eq!(s["ja"]["romaji"].as_array().map(|a| a.len()), Some(4));
    }

    /// 第 4 段是那段十几秒的连续朗读，明显比前三段长 ——
    /// 长句里的音色漂移只有这种长度才测得出来。
    #[test]
    fn the_fourth_line_is_the_long_one() {
        let s = script();
        for lang in LANGS {
            let lines = s[lang]["lines"].as_array().unwrap();
            let fourth = lines[3].as_str().unwrap().chars().count();
            for i in 0..3 {
                let other = lines[i].as_str().unwrap().chars().count();
                assert!(fourth > other, "{lang}：第 4 段应当比第 {} 段长", i + 1);
            }
        }
    }

    #[test]
    fn nothing_recorded_means_nothing_to_send() {
        let root = scratch("consult-empty");
        assert!(!has_any_recording(&root));
        let st = state(&root);
        for lang in LANGS {
            assert!(st["recorded"][lang].is_null());
        }
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 只念一种语言也该能出包 —— 稿子上写的是「推荐全念」，不是「必须全念」。
    #[test]
    fn one_language_is_enough() {
        let root = scratch("consult-one");
        let dir = raw_dir(&root, "zh");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("rec_1.wav"), b"RIFF....WAVE").unwrap();
        assert!(has_any_recording(&root));
        let st = state(&root);
        assert!(!st["recorded"]["zh"].is_null());
        assert!(st["recorded"]["en"].is_null());
        let _ = std::fs::remove_dir_all(&root);
    }

    /// 重录之后取最新那条。上一次录到一半崩掉会在目录里留下残骸，
    /// 取错的话用户听到的和寄出去的是两段不同的录音。
    #[test]
    fn re_recording_wins() {
        let root = scratch("consult-newest");
        let dir = raw_dir(&root, "en");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("rec_old.wav"), b"old").unwrap();
        std::thread::sleep(std::time::Duration::from_millis(1100));
        std::fs::write(dir.join("rec_new.wav"), b"new").unwrap();
        let got = only_wav(&dir).unwrap();
        assert_eq!(got.file_name().unwrap(), "rec_new.wav");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn clearing_removes_every_language() {
        let root = scratch("consult-clear");
        for lang in LANGS {
            let d = raw_dir(&root, lang);
            std::fs::create_dir_all(&d).unwrap();
            std::fs::write(d.join("rec.wav"), b"x").unwrap();
        }
        assert!(has_any_recording(&root));
        clear(&root);
        assert!(!has_any_recording(&root));
        let _ = std::fs::remove_dir_all(&root);
    }
}
