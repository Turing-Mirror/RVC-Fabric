//! Standalone capabilities for scripts, tools and MCP clients.
use crate::{paths, separate, sts, voices, worker};
use serde_json::{json, Value};
use std::{
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    time::Duration,
};
use tauri::{AppHandle, Listener, Manager};
use tauri_plugin_opener::OpenerExt;
use trm_app_protocol::{discovery::Installation, jobs::JobContext, *};
include!(concat!(env!("OUT_DIR"), "/ui_dispatch.rs"));

pub fn headless() -> bool {
    std::env::args().any(|arg| arg == "--headless")
}
pub struct AudioApp {
    app: AppHandle,
    root: PathBuf,
    listened: std::sync::Mutex<std::collections::HashSet<String>>,
}
fn capability(
    id: &str,
    description: &str,
    kind: &str,
    mut properties: Value,
    required: Vec<&str>,
) -> Capability {
    let title = match id {
        "rvc.convert" => "转换音色",
        "audio.separate" => "人声分离",
        "audio.mix" => "混音",
        "rvc.voices" => "本机音色",
        _ => id,
    };
    let mut schema = json!({"type":"object","title":title,"properties":properties.take(),"required":required,"additionalProperties":false});
    schema["description"] = json!(match id {
        "rvc.convert" => "将人声转换为所选音色。",
        "audio.separate" => "从歌曲中分离人声与伴奏。",
        "audio.mix" => "调整音轨音量与时间，混合并导出音频。",
        "rvc.voices" => "查看已安装的音色。",
        _ => description,
    });
    label_schema(&mut schema);
    serde_json::from_value(json!({"id":id,"description":description,"kind":kind,"contractVersion":1,"inputSchema":schema,"resultSchema":if kind=="job" {audio_result_schema(match id {"audio.separate"=>&["vocal","accompaniment"],"rvc.convert"=>&["converted_vocal"],_=>&["mix"]})}else{json!({"type":"object"})},"cancelable":kind=="job","effects":if kind=="job"{vec!["write_output"]}else{vec![]}})).expect("capability")
}
fn file() -> Value {
    json!({"type":"string","minLength":1,"x-trm-kind":"file","x-trm-media":"audio"})
}
fn output() -> Value {
    json!({"type":"string","x-trm-kind":"directory"})
}
pub fn manifest() -> Manifest {
    let common = json!({"outputDirectory":output()});
    let mut convert = json!({"input":file(),"modelPath":{"type":"string","minLength":1,"x-trm-kind":"resource","x-trm-resource":"rvc.voice"},"indexPath":{"type":"string"},"pitch":{"type":"integer","minimum":-48,"maximum":48,"default":0,"x-trm-unit":"semitone"},"f0method":{"type":"string","enum":["rmvpe","harvest","pm","crepe"],"default":"rmvpe"},"indexRate":{"type":"number","minimum":0,"maximum":1,"default":0.75},"protect":{"type":"number","minimum":0,"maximum":0.5,"default":0.33},"rmsMixRate":{"type":"number","minimum":0,"maximum":1,"default":0.25},"format":{"type":"string","enum":["wav","flac","mp3","m4a"],"default":"wav"}});
    convert
        .as_object_mut()
        .unwrap()
        .extend(common.as_object().unwrap().clone());
    let mut separation = json!({"input":file(),"model":{"type":"string","minLength":1,"x-trm-kind":"resource","x-trm-resource":"separation.model"},"format":{"type":"string","enum":["wav","flac","mp3","m4a"],"default":"wav"},"aggression":{"type":"integer","minimum":0,"maximum":20,"default":10}});
    separation
        .as_object_mut()
        .unwrap()
        .extend(common.as_object().unwrap().clone());
    let mut mixing = json!({"tracks":{"type":"array","x-trm-default-items":2,"minItems":1,"maxItems":16,"items":{"type":"object","properties":{"path":file(),"gainDb":{"type":"number","minimum":-96,"maximum":24,"default":0},"offsetMs":{"type":"number","minimum":-3600000,"maximum":3600000,"default":0}},"required":["path"],"additionalProperties":false}},"sampleRate":{"type":"integer","enum":[16000,22050,24000,32000,44100,48000,88200,96000],"default":48000},"channels":{"type":"integer","enum":[1,2],"default":2},"format":{"type":"string","enum":["wav","flac"],"default":"wav"},"limiter":{"type":"boolean","default":true}});
    mixing
        .as_object_mut()
        .unwrap()
        .extend(common.as_object().unwrap().clone());
    Manifest{product_id:"com.turingmirror.rvcfabric".into(),name:"RVC Fabric".into(),version:env!("CARGO_PKG_VERSION").into(),protocol:PROTOCOL,channel:"neptune".into(),capabilities:vec![
        capability("rvc.voices","List installed voice models and their file references","query",json!({}),vec![]),
        capability("rvc.convert","Convert a local vocal recording with an installed RVC voice model. Returns a job ID; the completed job contains converted vocal audio.","job",convert,vec!["input","modelPath"]),
        capability("audio.separate","Separate a local song with an installed separation model. Completed artifacts retain the model's actual stem labels.","job",separation,vec!["input","model"]),
        capability("audio.mix","Mix local audio tracks with independent gain in dB and offset in milliseconds. Positive offsets delay a track; negative offsets trim its start.","job",mixing,vec!["tracks"]),
    ],ui:Some(json!({"protocol":1,"entry":"index.html","adapter":"tauri-v2","windowCommands":{"tools_open":{"argument":"kind","labels":{"separate":crate::i18n::t("s.8fd038283b"),"train":crate::i18n::t("s.ba65bd5595"),"tts":crate::i18n::t("s.6f311c47fe")}},"tools_open_downloads":{"kind":"main","event":"open-download-models"},"tools_open_help":{"kind":"main","event":"open-help"},"tools_open_audio":{"kind":"main","event":"open-audio"}},"windows":[{"id":"main"}]}))}
}
impl Application for AudioApp {
    fn manifest(&self) -> Manifest {
        manifest()
    }
    fn status(&self) -> ApiResult {
        Ok(
            json!({"runtimeReady":paths::runtime_ready(&self.root),"engine":worker::status_for_ui(&self.root),"conversion":sts::status(&self.root),"separation":separate::status(&self.root),"audioToolsReady":fabric_audio::decode::AudioTools::at(&self.root).ready()}),
        )
    }
    fn resources(&self) -> ApiResult {
        let voices = voices::list_voices(&self.root);
        let separation = separate::status(&self.root);
        let mut resources = Vec::new();
        if let Some(rows) = voices["models"].as_array() {
            for row in rows {
                resources.push(json!({"id":row["path"],"kind":"rvc.voice","name":row["name"],"value":row["path"],"metadata":row}));
            }
        }
        if let Some(rows) = separation["models"].as_array() {
            for row in rows {
                let path = row
                    .as_str()
                    .and_then(|name| resource_file(&separate::model_dir(&self.root), name));
                resources.push(json!({"id":row,"kind":"separation.model","name":row,"value":row,"metadata":{"file":path,"config":path.as_ref().map(|p|p.with_extension("yaml"))}}));
            }
        }
        Ok(json!({"voices":voices,"separation":separation,"resources":resources}))
    }
    fn query(&self, id: &str, _: Value) -> ApiResult {
        match id {
            "rvc.voices" => Ok(voices::list_voices(&self.root)),
            _ => Err(ApiError::new("capability_not_found", id)),
        }
    }
    fn show(&self) -> ApiResult {
        let app = self.app.clone();
        self.app
            .run_on_main_thread(move || show_window(&app))
            .map_err(|e| ApiError::new("window_failed", e))?;
        Ok(json!({}))
    }
    fn quit(&self) -> ApiResult {
        if matches!(
            worker::status_for_ui(&self.root)["state"].as_str(),
            Some("running" | "starting")
        ) || sts::status(&self.root)["busy"].as_bool().unwrap_or(false)
            || separate::status(&self.root)["busy"]
                .as_bool()
                .unwrap_or(false)
        {
            return Err(ApiError::new(
                "application_busy",
                "An operation is still running",
            ));
        }
        let app = self.app.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(150));
            app.exit(0);
        });
        Ok(json!({}))
    }
    fn ui_listen(&self, event: &str, events: tokio::sync::broadcast::Sender<Value>) -> ApiResult {
        let mut listened = self.listened.lock().unwrap_or_else(|e| e.into_inner());
        if !listened.contains(event) {
            let name = event.to_string();
            self.app.listen(event.to_string(),move |event| {let payload=serde_json::from_str::<Value>(event.payload()).unwrap_or(Value::Null);let _=events.send(json!({"jsonrpc":"2.0","method":"ui.event","params":{"event":name,"payload":payload}}));});
            listened.insert(event.to_string());
        }
        Ok(json!({}))
    }
    fn ui_file(&self, path: &str) -> ApiResult {
        let path = std::path::Path::new(path).canonicalize()?;
        if !path.is_file() || !self.app.asset_protocol_scope().is_allowed(&path) {
            return Err(ApiError::new(
                "file_not_allowed",
                "File is outside the application's media scope",
            ));
        }
        Ok(json!({"path":path}))
    }
    fn ui_attach(&self) -> ApiResult {
        if let Some(win) = self.app.get_webview_window("main") {
            win.hide().map_err(|e| ApiError::new("window_failed", e))?;
        }
        Ok(json!({}))
    }
    fn ui_invoke(&self, command: &str, args: Value) -> ApiResult {
        match command {
            "plugin:opener|open_url" => {
                self.app
                    .opener()
                    .open_url(
                        args["url"]
                            .as_str()
                            .ok_or_else(|| ApiError::invalid("Missing URL"))?,
                        None::<&str>,
                    )
                    .map_err(|e| ApiError::new("open_failed", e))?;
                Ok(json!({}))
            }
            "plugin:opener|open_path" => {
                self.app
                    .opener()
                    .open_path(
                        args["path"]
                            .as_str()
                            .ok_or_else(|| ApiError::invalid("Missing path"))?,
                        None::<&str>,
                    )
                    .map_err(|e| ApiError::new("open_failed", e))?;
                Ok(json!({}))
            }
            "plugin:event|emit" | "plugin:event|emit_to" => {
                use tauri::Emitter;
                self.app
                    .emit(
                        args["event"]
                            .as_str()
                            .ok_or_else(|| ApiError::invalid("Missing event"))?,
                        args["payload"].clone(),
                    )
                    .map_err(|e| ApiError::new("event_failed", e))?;
                Ok(json!({}))
            }
            _ => tauri::async_runtime::block_on(dispatch_ui(self.app.clone(), command, args)),
        }
    }
    fn execute(&self, context: JobContext, id: &str, args: Value) -> ApiResult {
        context.check()?;
        if id != "audio.mix" {
            let state = worker::status_for_ui(&self.root);
            if matches!(state["state"].as_str(), Some("running" | "starting")) {
                return Err(ApiError::new(
                    "engine_busy",
                    "Real-time voice conversion is running",
                ));
            }
            if !paths::runtime_ready(&self.root) {
                return Err(ApiError::new(
                    "runtime_missing",
                    "Install the application's runtime first",
                ));
            }
        }
        let output = args["outputDirectory"]
            .as_str()
            .filter(|s| !s.trim().is_empty())
            .map(PathBuf::from)
            .unwrap_or_else(|| paths::user_data(&self.root).join("api").join("outputs"))
            .join(&context.id);
        std::fs::create_dir_all(&output)?;
        crate::asset_scope::grant_dir(&self.app, &output);
        if id == "audio.mix" {
            return crate::audio_mix::mix(&self.root, &context, &args, &output);
        }
        let event = if id == "rvc.convert" {
            "sts-progress"
        } else {
            "separate-progress"
        };
        let observer = context.clone();
        let owner = context.id.clone();
        let listener = self.app.listen(event, move |event| {
            if let Ok(value) = serde_json::from_str::<Value>(event.payload()) {
                if value["owner"].as_str() == Some(&owner) {
                    observer.progress(value);
                }
            }
        });
        let ended = Arc::new(AtomicBool::new(false));
        let stop = ended.clone();
        let cancel = context.canceled.clone();
        let owner = context.id.clone();
        let conversion = id == "rvc.convert";
        let watcher = std::thread::spawn(move || {
            while !stop.load(Ordering::Acquire) {
                if cancel.load(Ordering::Acquire) {
                    if conversion {
                        sts::cancel_for(Some(&owner));
                    } else {
                        separate::cancel_for(Some(&owner));
                    }
                }
                std::thread::sleep(Duration::from_millis(50));
            }
        });
        let result = match id {
            "rvc.convert" => {
                let mut opts = sts::ConvertOpts::default();
                opts.owner = Some(context.id.clone());
                opts.format = args["format"].as_str().unwrap_or("wav").into();
                opts.protect = args["protect"].as_f64().unwrap_or(opts.protect);
                opts.rms_mix_rate = args["rmsMixRate"].as_f64().unwrap_or(opts.rms_mix_rate);
                sts::run(
                    &self.app,
                    &self.root,
                    args["input"].as_str().unwrap(),
                    &output.to_string_lossy(),
                    args["pitch"].as_i64().unwrap_or(0) as i32,
                    args["f0method"].as_str().unwrap_or("rmvpe"),
                    args["indexRate"].as_f64().unwrap_or(0.75),
                    args["modelPath"].as_str().unwrap(),
                    args["indexPath"].as_str().unwrap_or(""),
                    opts,
                    None,
                )
            }
            "audio.separate" => separate::run_owned(
                &self.app,
                &self.root,
                args["input"].as_str().unwrap(),
                &output.to_string_lossy(),
                args["model"].as_str().unwrap(),
                args["format"].as_str().unwrap_or("wav"),
                args["aggression"].as_u64().unwrap_or(10) as u32,
                Some(context.id.clone()),
            ),
            _ => Err("Unknown capability".into()),
        };
        ended.store(true, Ordering::Release);
        let _ = watcher.join();
        self.app.unlisten(listener);
        let result = result.map_err(|e| {
            if context.canceled.load(Ordering::Acquire) {
                ApiError::canceled()
            } else {
                ApiError::new("execution_failed", e)
            }
        })?;
        let files = result["files"]
            .as_array()
            .ok_or_else(|| ApiError::new("output_invalid", "No output files"))?;
        if files.is_empty() {
            return Err(ApiError::new(
                "output_missing",
                "The engine produced no audio files",
            ));
        }
        let mut artifacts = Vec::new();
        for (index, file) in files.iter().enumerate() {
            let path = file
                .as_str()
                .ok_or_else(|| ApiError::new("output_invalid", "Invalid output reference"))?;
            let role = if id == "rvc.convert" {
                "converted_vocal"
            } else {
                result["stems"]
                    .as_array()
                    .and_then(|rows| rows.iter().find(|r| r["path"].as_str() == Some(path)))
                    .and_then(|r| r["role"].as_str())
                    .unwrap_or("stem")
            };
            let mut artifact = crate::audio_mix::artifact(
                &self.root,
                Path::new(path),
                role,
                &format!("{}:{index}", context.id),
            )?;
            if id == "audio.separate" {
                artifact["stem"] = result["stems"]
                    .as_array()
                    .and_then(|rows| rows.iter().find(|r| r["path"].as_str() == Some(path)))
                    .map(|r| r["stem"].clone())
                    .unwrap_or(Value::Null);
            }
            artifacts.push(artifact);
        }
        Ok(json!({"jobId":context.id,"artifacts":artifacts}))
    }
}
pub fn start(app: &AppHandle, root: PathBuf) -> Result<(), String> {
    let application = Arc::new(AudioApp {
        app: app.clone(),
        root: root.clone(),
        listened: std::sync::Mutex::new(std::collections::HashSet::new()),
    });
    let installation = Installation::new(
        manifest(),
        std::env::current_exe().map_err(|e| e.to_string())?,
        root.clone(),
        crate::ui_assets::external_dir(),
    );
    let service = Service::new(
        application,
        installation,
        paths::user_data(&root).join("api").join("jobs.json"),
    )
    .map_err(|e| e.to_string())?;
    service.start().map_err(|e| e.to_string())?;
    app.manage(service);
    Ok(())
}

pub fn main_url() -> String {
    if cfg!(windows) {
        format!("http://{}.localhost/index.html", crate::ui_assets::SCHEME)
    } else {
        format!("{}://localhost/index.html", crate::ui_assets::SCHEME)
    }
}
pub fn show_window(app: &AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        if win.url().ok().is_some_and(|url| url.scheme() == "about") {
            let _ = win.navigate(main_url().parse().expect("UI URL"));
        }
        crate::window_watch::rescue(&win);
        let _ = win.set_focus();
    }
}

fn label_schema(schema: &mut Value) {
    if let Some(properties) = schema.get_mut("properties").and_then(Value::as_object_mut) {
        for (key, child) in properties {
            let title = [
                ("input", "输入音频"),
                ("modelPath", "音色模型"),
                ("indexPath", "索引文件"),
                ("pitch", "音高"),
                ("f0method", "音高提取方法"),
                ("indexRate", "索引比例"),
                ("protect", "清辅音保护"),
                ("rmsMixRate", "响度包络比例"),
                ("format", "输出格式"),
                ("outputDirectory", "输出目录"),
                ("model", "分离模型"),
                ("aggression", "分离强度"),
                ("tracks", "音轨"),
                ("path", "音频文件"),
                ("gainDb", "增益（dB）"),
                ("offsetMs", "偏移（毫秒）"),
                ("sampleRate", "采样率"),
                ("channels", "声道"),
                ("limiter", "限制峰值"),
                ("roleId", "角色"),
                ("text", "合成文本"),
                ("referenceAudio", "参考音频"),
                ("referenceText", "参考文本"),
                ("referenceLanguage", "参考语言"),
                ("parameters", "合成参数"),
                ("text_lang", "文本语言"),
                ("speed", "语速"),
                ("top_k", "候选数量"),
                ("top_p", "采样范围"),
                ("temperature", "采样温度"),
                ("repetition_penalty", "重复惩罚"),
                ("text_split_method", "切句方式"),
                ("fragment_interval", "句间间隔"),
                ("seed", "随机种子"),
                ("sample_steps", "采样步数"),
            ]
            .into_iter()
            .find(|(name, _)| *name == key.as_str())
            .map(|(_, label)| label);
            if let Some(title) = title {
                child["title"] = json!(title);
            }
            label_schema(child);
        }
    }
    if let Some(items) = schema.get_mut("items") {
        label_schema(items);
    }
}

fn resource_file(dir: &Path, name: &str) -> Option<PathBuf> {
    for entry in std::fs::read_dir(dir).ok()?.flatten() {
        let path = entry.path();
        if path.is_dir() {
            if let Some(found) = resource_file(&path, name) {
                return Some(found);
            }
        } else if path.file_name().is_some_and(|n| n == name) {
            return Some(path);
        }
    }
    None
}
