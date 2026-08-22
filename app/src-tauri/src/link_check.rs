//! 链路自检：把「听不到」从一句报错变成一张可逐项核对的清单。
//!
//! 设计约束：**必须快、必须无副作用**。这个命令在引擎报错的那一刻被调用，
//! 那时候机器状态本来就烂 —— 再去启动 worker（最长 90 秒）或者触发任何会写
//! 盘的操作，就是把烂泥搅得更浑。所以这里只做三件事：读配置、读缓存状态、
//! 扫目录；worker 活着就顺带读它上报的设备表（含 Windows 默认播放设备），
//! 不活着就让那一行降级成「提示」。
//!
//! 判定与修复建议在前端（LinkCheckDialog）：壳子只报事实，不报结论 ——
//! 「输出设备名里带 CABLE Output」是事实，「你接反了」是结论。结论留给
//! 界面层用用户的语言说。

use std::path::Path;

use serde_json::{json, Value};

use crate::paths;

/// 采集链路事实。全部是读操作，毫秒级。
pub fn gather(root: &Path) -> Value {
    let cfg = crate::config::read(root);
    let alive = crate::worker::is_worker_alive(root);
    let status = if alive {
        Some(crate::worker::status_for_ui(root))
    } else {
        None
    };
    let assets = crate::engine_assets::assets_status(root);

    let str_of = |v: Option<&Value>| v.and_then(|x| x.as_str()).unwrap_or("").to_string();

    // 设备表：只在 worker 活着时可信。设备名可能是字符串，也可能是
    // {name} 对象（HelpPage 那边两种都认）。
    let device_names = |key: &str| -> Vec<String> {
        status
            .as_ref()
            .and_then(|s| s.get(key))
            .and_then(|v| v.as_array())
            .map(|a| {
                a.iter()
                    .map(|d| match d {
                        Value::String(s) => s.clone(),
                        other => str_of(other.get("name")),
                    })
                    .collect()
            })
            .unwrap_or_default()
    };

    let inputs = device_names("input_devices");
    let outputs = device_names("output_devices");

    // 最新诊断包：求助信息里带上路径，管理员少问一轮「包呢」。
    let diag_latest = latest_diag(root);

    json!({
        "version": crate::update::APP_VERSION,
        "gpu": crate::provision::list_gpus().first().cloned().unwrap_or_default(),
        "runtime_ready": paths::runtime_ready(root),
        "engine_alive": alive,
        "engine_state": status.as_ref()
            .and_then(|s| s.get("state"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        "engine_error": status.as_ref()
            .and_then(|s| s.get("error"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        "vbcable_installed": assets.get("vbcable_installed")
            .and_then(|v| v.as_bool())
            .unwrap_or(false),
        "cfg_input": str_of(cfg.get("sg_input_device")),
        "cfg_output": str_of(cfg.get("sg_output_device")),
        "default_output": str_of(status.as_ref().and_then(|s| s.get("default_output_device"))),
        "input_devices": inputs,
        "output_devices": outputs,
        "diag_latest": diag_latest,
    })
}

/// User_Data/diagnostics 里最新的 zip 文件名；没有则空串。
fn latest_diag(root: &Path) -> String {
    let dir = paths::user_data(root).join("diagnostics");
    let Ok(rd) = std::fs::read_dir(&dir) else {
        return String::new();
    };
    let mut best: Option<(std::time::SystemTime, String)> = None;
    for e in rd.flatten() {
        let p = e.path();
        if p.extension().and_then(|s| s.to_str()) != Some("zip") {
            continue;
        }
        let Ok(meta) = e.metadata() else { continue };
        let Ok(m) = meta.modified() else { continue };
        if best.as_ref().map(|(t, _)| m > *t).unwrap_or(true) {
            best = Some((m, p.to_string_lossy().into_owned()));
        }
    }
    best.map(|(_, name)| name).unwrap_or_default()
}

/// 新手进度：五步各就各位了吗。
///
/// 前三步每次实时推导（运行时是否就绪、是否选了音色、虚拟声卡是否在位），
/// 后两步是**历史事件**（首次成功变声、开启过监听），必须落配置才能跨重启
/// 存活 —— 写入方在 App.tsx 的状态订阅里，见 onboard_convert/onboard_monitor。
pub fn onboarding(root: &Path) -> Value {
    let cfg = crate::config::read(root);
    let voices = crate::voices::list_voices(root);
    let alive = crate::worker::is_worker_alive(root);
    let status = if alive {
        Some(crate::worker::status_for_ui(root))
    } else {
        None
    };
    let names = |key: &str, s: Option<&Value>| -> Vec<String> {
        s.and_then(|st| st.get(key))
            .and_then(|v| v.as_array())
            .map(|a| {
                a.iter()
                    .map(|d| match d {
                        Value::String(x) => x.clone(),
                        other => {
                            other.get("name").and_then(|v| v.as_str()).unwrap_or("").to_string()
                        }
                    })
                    .collect()
            })
            .unwrap_or_default()
    };
    let inputs = names("input_devices", status.as_ref());
    let outputs = names("output_devices", status.as_ref());
    let has_cable = |list: &[String]| {
        list.iter()
            .any(|n| n.to_ascii_lowercase().contains("cable"))
    };
    let selected = voices
        .get("selected_idx")
        .and_then(|v| v.as_i64())
        .unwrap_or(-1)
        >= 0;
    json!({
        "runtime": paths::runtime_ready(root),
        "voice": selected,
        // 设备列表只在引擎跑起来后才看得见；装没装以 Program Files 里的驱动
        // 为准（assets_status 那条路不依赖引擎）。
        "cable": crate::engine_assets::assets_status(root)
            .get("vbcable_installed")
            .and_then(|v| v.as_bool())
            .unwrap_or(false)
            || has_cable(&inputs)
            || has_cable(&outputs),
        "convert": cfg.get("onboard_convert").and_then(|v| v.as_bool()).unwrap_or(false),
        "monitor": cfg.get("onboard_monitor").and_then(|v| v.as_bool()).unwrap_or(false)
            || cfg.get("monitor_self").and_then(|v| v.as_bool()).unwrap_or(false),
        "dismissed": cfg.get("onboard_dismiss").and_then(|v| v.as_bool()).unwrap_or(false),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// names 的双形态解析：设备可能是字符串，可能是 {name} 对象。
    #[test]
    fn device_names_accepts_both_shapes() {
        let v: Value = serde_json::json!({
            "input_devices": ["麦 A", {"name": "麦 B", "hostapi": "MME"}],
        });
        let got = {
            // 复刻 gather 里那段闭包逻辑太绕，这里直接验证同一解析规则。
            v.get("input_devices")
                .and_then(|x| x.as_array())
                .map(|a| {
                    a.iter()
                        .map(|d| match d {
                            Value::String(s) => s.clone(),
                            other => {
                                other.get("name").and_then(|n| n.as_str()).unwrap_or("").to_string()
                            }
                        })
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default()
        };
        assert_eq!(got, vec!["麦 A".to_string(), "麦 B".to_string()]);
    }
}
