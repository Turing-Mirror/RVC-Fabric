//! 变声用的麦克风或声卡被拔掉时通知界面。
//!
//! 每两秒看一次系统的设备列表：用户选的那台从「在」变成「不在」，连续两次都不在才算断开，
//! 发 `audio-device://lost`；之后又出现了，发 `audio-device://back`。界面据此停下变声、
//! 提示重新选择，插回来后可以直接继续。
//!
//! 设置里存的是引擎（PortAudio）的叫法，系统列表里是另一套叫法，未必对得上。所以只认
//! 「先对上过、后来对不上」的变化：一开始就对不上的设备不会被当成断开，不会误停变声。
use serde_json::json;
use std::path::PathBuf;
use std::time::Duration;
use tauri::{AppHandle, Emitter};

/// 多久看一次。
const POLL: Duration = Duration::from_secs(2);
/// 连续几次不在才算断开。插拔瞬间系统列表会抖一下，一次不在不算。
const MISSES_TO_LOST: u8 = 2;

/// 两套叫法是不是同一台。忽略大小写与首尾空白；PortAudio 在 MME 下会把名字截到 31 个字符，
/// 所以一方包含另一方也算。太短的名字不做包含判断，免得「扬声器」对上所有扬声器。
pub fn same_device(configured: &str, system: &str) -> bool {
    let a = configured.trim().to_lowercase();
    let b = system.trim().to_lowercase();
    if a.is_empty() || b.is_empty() {
        return false;
    }
    if a == b {
        return true;
    }
    let (short, long) = if a.chars().count() <= b.chars().count() { (&a, &b) } else { (&b, &a) };
    short.chars().count() >= 8 && long.contains(short.as_str())
}

#[derive(Debug, PartialEq, Eq)]
pub enum Change {
    Lost,
    Back,
}

/// 一台设备的在与不在。
#[derive(Default)]
pub struct Tracker {
    name: String,
    seen: bool,
    misses: u8,
    lost: bool,
}

impl Tracker {
    /// 喂一次这一轮的结果，返回这一轮是否刚断开或刚回来。用户换了设备就从头看。
    pub fn step(&mut self, name: &str, present: bool) -> Option<Change> {
        if name != self.name {
            *self = Tracker { name: name.to_string(), ..Tracker::default() };
        }
        if name.is_empty() {
            return None;
        }
        if present {
            self.seen = true;
            self.misses = 0;
            if self.lost {
                self.lost = false;
                return Some(Change::Back);
            }
            return None;
        }
        if !self.seen || self.lost {
            return None;
        }
        self.misses = self.misses.saturating_add(1);
        if self.misses >= MISSES_TO_LOST {
            self.lost = true;
            return Some(Change::Lost);
        }
        None
    }
}

/// 在后台一直看着。设备枚举失败的那一轮跳过，不当成设备都不在。
pub fn spawn(app: AppHandle, root: PathBuf) {
    std::thread::spawn(move || {
        let mut input = Tracker::default();
        let mut output = Tracker::default();
        loop {
            std::thread::sleep(POLL);
            let Ok((inputs, outputs)) = fabric_audio::output::device_names() else {
                continue;
            };
            let cfg = crate::config::read(&root);
            let want = |key: &str| cfg.get(key).and_then(|v| v.as_str()).unwrap_or("").to_string();
            for (kind, tracker, key, list) in [
                ("input", &mut input, "sg_input_device", &inputs),
                ("output", &mut output, "sg_output_device", &outputs),
            ] {
                let name = want(key);
                let present = list.iter().any(|s| same_device(&name, s));
                if let Some(change) = tracker.step(&name, present) {
                    let event = if change == Change::Lost { "audio-device://lost" } else { "audio-device://back" };
                    crate::logging::shell_log!("设备{}：{} {}", if change == Change::Lost { "断开" } else { "恢复" }, kind, name);
                    let _ = app.emit(event, json!({ "kind": kind, "name": name }));
                }
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_match_across_the_two_naming_schemes() {
        assert!(same_device("麦克风 (Realtek(R) Audio)", "麦克风 (Realtek(R) Audio)"));
        assert!(same_device("CABLE Input (VB-Audio Virtual C", "CABLE Input (VB-Audio Virtual Cable)"));
        assert!(!same_device("扬声器", "扬声器 (Realtek(R) Audio)"), "too short to trust a partial match");
        assert!(!same_device("", "anything"));
    }

    #[test]
    fn a_device_is_lost_only_after_it_was_seen_and_then_missed_twice() {
        let mut t = Tracker::default();
        assert_eq!(t.step("Mic", true), None);
        assert_eq!(t.step("Mic", false), None, "one miss is a blip");
        assert_eq!(t.step("Mic", false), Some(Change::Lost));
        assert_eq!(t.step("Mic", false), None, "reported once");
        assert_eq!(t.step("Mic", true), Some(Change::Back));
    }

    #[test]
    fn a_name_that_never_matched_is_never_reported() {
        let mut t = Tracker::default();
        for _ in 0..5 {
            assert_eq!(t.step("Engine-only name", false), None);
        }
    }

    #[test]
    fn switching_devices_starts_over() {
        let mut t = Tracker::default();
        t.step("A", true);
        t.step("A", false);
        assert_eq!(t.step("B", false), None);
        assert_eq!(t.step("B", false), None);
    }
}
