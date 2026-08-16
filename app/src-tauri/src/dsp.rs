//! DSP 变声预设：列举 / 保存 / 删除。
//!
//! 预设是几百字节的 JSON（`{效果器: {参数: 值}}`），跟 55MB 的 .pth 完全是
//! 两种东西 —— 广场上点一下就下完了。
//!
//! 内置的在 `configs/dsp_presets/`，用户存的在 `User_Data/dsp_presets/`，
//! 同 id 时用户的覆盖内置（这样用户可以改内置预设而不必动安装目录）。
//!
//! 参数的合法范围由引擎侧 `tools/dsp_voice.py` 的 EFFECT_SPECS 定义，这里
//! **不**重复一份 —— 抄一遍就一定会跟引擎走散。壳只负责读写文件和挡住明显
//! 非法的 id；真正的钳位在 `dsp_presets._sanitize` 里，引擎每次载入都会做。

use std::fs;
use std::path::{Path, PathBuf};

use serde_json::{json, Map, Value};

use crate::paths;

/// 一次最多返回多少条。预设是几百字节，但目录是用户可写的，不设上限
/// 等于让一个塞了十万个文件的目录把界面卡死。
const LIST_CAP: usize = 500;

pub fn builtin_dir(root: &Path) -> PathBuf {
    root.join("configs").join("dsp_presets")
}

pub fn user_dir(root: &Path) -> PathBuf {
    paths::user_data(root).join("dsp_presets")
}

/// 预设 id 只允许小写字母、数字、下划线。
///
/// 它同时是文件名和配置里的键：不挡的话 `../../config` 这种 id 就能写到
/// 目录外面去。长度也要限，NTFS 的路径上限撞上去只会是一个看不懂的报错。
pub fn is_valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 48
        && id
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
}

fn read_json(path: &Path) -> Option<Value> {
    let text = fs::read_to_string(path).ok()?;
    serde_json::from_str(&text).ok()
}

fn read_dir_presets(dir: &Path, source: &str, out: &mut Map<String, Value>) {
    let Ok(rd) = fs::read_dir(dir) else {
        return;
    };
    let mut files: Vec<PathBuf> = rd
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.extension().and_then(|e| e.to_str()) == Some("json"))
        .collect();
    files.sort();
    for path in files.into_iter().take(LIST_CAP) {
        let Some(stem) = path.file_stem().and_then(|s| s.to_str()) else {
            continue;
        };
        if !is_valid_id(stem) {
            continue;
        }
        let Some(raw) = read_json(&path) else {
            continue;
        };
        // 没有 params 的文件是坏的，不是「空预设」—— 当空的收下，界面上就会
        // 多出一条点了没反应的预设。
        let Some(params) = raw.get("params").cloned().filter(Value::is_object) else {
            continue;
        };
        out.insert(
            stem.to_string(),
            json!({
                "id": stem,
                "name": raw.get("name").and_then(|v| v.as_str()).unwrap_or(stem),
                "desc": raw.get("desc").and_then(|v| v.as_str()).unwrap_or(""),
                "params": params,
                "source": source,
            }),
        );
    }
}

/// 全部预设。内置在前、用户的在后；同 id 用户覆盖内置。
pub fn list(root: &Path) -> Value {
    let mut merged = Map::new();
    read_dir_presets(&builtin_dir(root), "builtin", &mut merged);
    let builtin_ids: Vec<String> = merged.keys().cloned().collect();
    read_dir_presets(&user_dir(root), "user", &mut merged);

    let mut items: Vec<Value> = Vec::new();
    for id in &builtin_ids {
        if let Some(v) = merged.remove(id.as_str()) {
            items.push(v);
        }
    }
    let mut rest: Vec<Value> = merged.into_iter().map(|(_, v)| v).collect();
    rest.sort_by(|a, b| {
        a.get("id")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .cmp(b.get("id").and_then(|v| v.as_str()).unwrap_or(""))
    });
    items.extend(rest);
    json!({ "presets": items })
}

/// 效果器规格（参数名、默认值、取值范围）。
///
/// 由 `configs/dsp_effects.json` 提供，那份文件是从引擎侧
/// `tools/dsp_voice.py` 的 EFFECT_SPECS 生成的。**壳不手抄一份范围** ——
/// 抄了就一定会跟引擎走散：界面上能拉到的值引擎那边会被静默钳回去，
/// 用户看到的和听到的对不上，而且从哪一侧都查不出原因。
pub fn effect_specs(root: &Path) -> Value {
    read_json(&root.join("configs").join("dsp_effects.json"))
        .filter(Value::is_object)
        .unwrap_or_else(|| json!({ "order": [], "effects": {} }))
}

/// 按 id 取一条预设（用户覆盖内置）。没有或坏文件返回 None。
pub fn get(root: &Path, id: &str) -> Option<Value> {
    if !is_valid_id(id) {
        return None;
    }
    let listed = list(root);
    listed
        .get("presets")
        .and_then(|v| v.as_array())
        .and_then(|arr| {
            arr.iter()
                .find(|p| p.get("id").and_then(|x| x.as_str()) == Some(id))
                .cloned()
        })
}

/// 选用一条预设：配置和 inuse 一次写完，再推一条 worker 命令。
///
/// 点「使用」和点「开启变声」都走这里。以前分两次 setHot，mailbox 单槽
/// 会把预设那条盖掉，配置里永远是空的，启动就报「请先选用预设」。
pub fn activate(root: &Path, id: &str) -> Result<Value, String> {
    let preset = get(root, id).ok_or_else(|| crate::i18n::te("s.dspPresetBadId", &id))?;
    let params = preset.get("params").cloned().unwrap_or_else(|| json!({}));
    if !params.is_object() || params.as_object().map(|m| m.is_empty()).unwrap_or(true) {
        return Err(crate::i18n::t("s.dspPresetBadParams"));
    }
    let cfg = crate::config::write_dsp_on(root, id, &params)?;
    let mut payload = Map::new();
    payload.insert("dsp_enabled".into(), json!(true));
    payload.insert("dsp_preset".into(), json!(id));
    payload.insert("dsp_params".into(), params);
    payload.insert("function".into(), json!("fx"));
    payload.insert("drop_model".into(), json!(true));
    // RVC 还在 import torch：立刻换成 DSP worker，选预设不该卡住。
    // 已经就绪的 RVC worker 留下，热推 fx 即可。
    let kind = crate::worker::worker_kind_of(root);
    let rvc_importing = kind == Some(crate::worker::WorkerKind::Rvc) && protocol_starting_import(root);
    if kind.is_none() || rvc_importing {
        let _ = crate::worker::start_worker_kind(root, crate::worker::WorkerKind::Dsp);
    }
    // worker 没起来只算配置写好了，开启变声会再推一次。
    let _ = crate::worker::set_hot(root, payload);
    Ok(json!({ "ok": true, "id": id, "config": cfg }))
}

fn protocol_starting_import(root: &Path) -> bool {
    let st = crate::protocol::read_status(root);
    let state = st.get("state").and_then(|v| v.as_str()).unwrap_or("");
    let code = st.get("message_code").and_then(|v| v.as_str()).unwrap_or("");
    state == "starting"
        && (code == "engine.starting" || code == "engine.importing" || code.is_empty())
}

pub fn deactivate(root: &Path) -> Result<Value, String> {
    let cfg = crate::config::write_dsp_off(root)?;
    let mut payload = Map::new();
    payload.insert("dsp_enabled".into(), json!(false));
    payload.insert("dsp_preset".into(), json!(""));
    payload.insert("dsp_params".into(), json!({}));
    let _ = crate::worker::set_hot(root, payload);
    Ok(json!({ "ok": true, "config": cfg }))
}

pub fn save(root: &Path, id: &str, name: &str, params: &Value) -> Result<Value, String> {
    if !is_valid_id(id) {
        return Err(crate::i18n::t("s.dspPresetBadId"));
    }
    if !params.is_object() {
        return Err(crate::i18n::t("s.dspPresetBadParams"));
    }
    let dir = user_dir(root);
    fs::create_dir_all(&dir).map_err(|e| crate::i18n::te("s.dspPresetSaveFail", &e))?;
    let body = json!({
        "name": if name.trim().is_empty() { id } else { name.trim() },
        "desc": "",
        "params": params,
    });
    let text = serde_json::to_string_pretty(&body).unwrap_or_default() + "\n";
    fs::write(dir.join(format!("{id}.json")), text)
        .map_err(|e| crate::i18n::te("s.dspPresetSaveFail", &e))?;
    Ok(json!({ "ok": true, "id": id }))
}

/// 删用户预设。内置的删不掉 —— 那是安装目录里的东西，删了升级还会回来，
/// 而且用户真想改的话，存一个同 id 的用户预设就盖住了。
pub fn delete(root: &Path, id: &str) -> Result<Value, String> {
    if !is_valid_id(id) {
        return Err(crate::i18n::t("s.dspPresetBadId"));
    }
    let f = user_dir(root).join(format!("{id}.json"));
    if !f.is_file() {
        return Err(crate::i18n::t("s.dspPresetNotUser"));
    }
    fs::remove_file(&f).map_err(|e| crate::i18n::te("s.dspPresetDeleteFail", &e))?;
    Ok(json!({ "ok": true, "id": id }))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 仓库里没有 tempfile 依赖，其他模块的测试都是这么开临时目录的。
    fn scratch(name: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("rvcf-dsp-{name}"));
        let _ = fs::remove_dir_all(&d);
        fs::create_dir_all(&d).unwrap();
        d
    }

    #[test]
    fn get_returns_params_for_a_real_preset() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..");
        let got = get(&root, "chipmunk").expect("chipmunk.json 必须在仓库里");
        let params = got.get("params").and_then(|v| v.as_object()).unwrap();
        assert!(params.contains_key("pitch"), "got {got}");
    }

    #[test]
    fn id_rules() {
        assert!(is_valid_id("robot"));
        assert!(is_valid_id("male_to_female"));
        assert!(is_valid_id("a1_2"));
        assert!(!is_valid_id(""));
        assert!(!is_valid_id("Robot"), "大写不许");
        assert!(!is_valid_id("my preset"), "空格不许");
        // 它同时是文件名，穿越必须挡住
        assert!(!is_valid_id("../../config"));
        assert!(!is_valid_id("a/b"));
        assert!(!is_valid_id("a\\b"));
        assert!(!is_valid_id(&"x".repeat(49)), "太长不许");
    }

    #[test]
    fn user_overrides_builtin_and_builtin_comes_first() {
        let root = &scratch("override");
        fs::create_dir_all(builtin_dir(root)).unwrap();
        fs::create_dir_all(user_dir(root)).unwrap();
        fs::write(
            builtin_dir(root).join("robot.json"),
            r#"{"name":"机器人","params":{"ring":{"mix":0.8}}}"#,
        )
        .unwrap();
        fs::write(
            builtin_dir(root).join("alien.json"),
            r#"{"name":"外星人","params":{"ring":{"mix":0.5}}}"#,
        )
        .unwrap();
        fs::write(
            user_dir(root).join("robot.json"),
            r#"{"name":"我的机器人","params":{"ring":{"mix":0.9}}}"#,
        )
        .unwrap();
        fs::write(
            user_dir(root).join("zz_mine.json"),
            r#"{"name":"自制","params":{"pitch":{"semitones":3}}}"#,
        )
        .unwrap();

        let v = list(root);
        let arr = v.get("presets").unwrap().as_array().unwrap();
        let ids: Vec<&str> = arr
            .iter()
            .map(|p| p.get("id").unwrap().as_str().unwrap())
            .collect();
        // 内置两条在前（按文件名排序），用户新增的在后
        assert_eq!(ids, vec!["alien", "robot", "zz_mine"]);
        let robot = arr.iter().find(|p| p["id"] == "robot").unwrap();
        assert_eq!(robot["name"], "我的机器人", "同 id 时用户的该覆盖内置");
        assert_eq!(robot["source"], "user");
    }

    #[test]
    fn bad_files_are_skipped_not_fatal() {
        let root = &scratch("badfiles");
        fs::create_dir_all(user_dir(root)).unwrap();
        fs::write(user_dir(root).join("ok.json"), r#"{"params":{}}"#).unwrap();
        fs::write(user_dir(root).join("broken.json"), "{ not json").unwrap();
        fs::write(user_dir(root).join("noparams.json"), r#"{"name":"x"}"#).unwrap();
        fs::write(user_dir(root).join("Bad Name.json"), r#"{"params":{}}"#).unwrap();
        let v = list(root);
        let arr = v.get("presets").unwrap().as_array().unwrap();
        let ids: Vec<&str> = arr
            .iter()
            .map(|p| p.get("id").unwrap().as_str().unwrap())
            .collect();
        assert_eq!(ids, vec!["ok"]);
    }

    #[test]
    fn delete_refuses_builtin() {
        let root = &scratch("delbuiltin");
        fs::create_dir_all(builtin_dir(root)).unwrap();
        fs::write(builtin_dir(root).join("robot.json"), r#"{"params":{}}"#).unwrap();
        assert!(delete(root, "robot").is_err(), "内置的不该删得掉");
        assert!(builtin_dir(root).join("robot.json").is_file());
    }

    #[test]
    fn save_then_delete_roundtrip() {
        let root = &scratch("roundtrip");
        let params = json!({"pitch": {"semitones": 5.0}});
        save(root, "mine", "我的", &params).unwrap();
        let arr = list(root)
            .get("presets")
            .unwrap()
            .as_array()
            .unwrap()
            .clone();
        assert_eq!(arr.len(), 1);
        assert_eq!(arr[0]["name"], "我的");
        assert_eq!(arr[0]["params"]["pitch"]["semitones"], 5.0);
        delete(root, "mine").unwrap();
        assert!(list(root).get("presets").unwrap().as_array().unwrap().is_empty());
    }

    #[test]
    fn save_rejects_traversal_id() {
        let root = &scratch("traversal");
        assert!(save(root, "../evil", "x", &json!({})).is_err());
    }
}
