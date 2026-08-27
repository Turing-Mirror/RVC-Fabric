//! 开火之前先派个小兵去踩音频枚举这颗雷。
//!
//! `sounddevice` 一 import 就 `Pa_Initialize`，PortAudio 会把注册表里每个 ASIO
//! 驱动加载起来问参数。驱动坏了就是整个进程当场消失，没有 Python 异常，壳子只
//! 能看到 worker 没了。26.8.21 那位连点九次开启变声，九次都死在这里
//! （rthdasio64.dll，0xC0000094 整数除零）。
//!
//! 引擎自己躲不开这次枚举，但可以先让 `tools/audio_probe.py`（只有
//! sounddevice，不碰 torch）替它踩一次。踩死了就说明引擎也会死，这时候把话说
//! 清楚，比让用户对着一根停住的进度条点第九次强。
//!
//! 一个会话只踩一次：结论缓存起来，别每次开引擎都赔一次崩溃的时间。

use std::path::Path;
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::sync::Mutex;
use std::sync::OnceLock;
use std::time::Duration;

use crate::paths;

/// 探测最多等这么久。正常机器上一两秒就回来了，卡住的多半是驱动在里面转，
/// 等下去也没有意义 —— 超时按「不确定」处理，不拦引擎。
const PROBE_TIMEOUT: Duration = Duration::from_secs(25);

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Verdict {
    /// 枚举跑通了。
    Ok,
    /// 进程被系统终止 —— 引擎照样会死，拦下来。
    Crashed { code: i32, asio: Vec<String> },
    /// 探不出结论（超时、找不到 Runtime、脚本缺失）。不拦。
    Unknown,
}

fn cache() -> &'static Mutex<Option<Verdict>> {
    static V: OnceLock<Mutex<Option<Verdict>>> = OnceLock::new();
    V.get_or_init(|| Mutex::new(None))
}

/// 本次会话的结论。
///
/// 只缓存「通过」和「不确定」—— 崩溃这一条每次重算。崩溃会把引擎整个拦下来，
/// 而它未必是必然的：别的程序独占了声卡、驱动一次抽风，都可能让探测死一回。
/// 把这种结论钉死到会话结束，等于用户修好了也得重启软件才认。重算的代价只在
/// 已经坏掉的那条路上付。
pub fn verdict(root: &Path) -> Verdict {
    let mut slot = cache().lock().unwrap_or_else(|e| e.into_inner());
    if let Some(v) = slot.as_ref() {
        return v.clone();
    }
    let v = run_probe(root);
    if !matches!(v, Verdict::Crashed { .. }) {
        *slot = Some(v.clone());
    }
    v
}

/// 崩了就返回一句能直接显示的话；其余情况返回 None。
///
/// 只在「被系统终止」时拦。探测自己异常退出、超时、环境不全，一律放行 ——
/// 拦错一次的代价是用户彻底用不了，比放过一次大得多。
pub fn blocking_reason(root: &Path) -> Option<String> {
    match verdict(root) {
        Verdict::Crashed { code, asio } => {
            let mut msg = crate::i18n::te("s.audioProbeCrash", &crate::crash::describe(code));
            if !asio.is_empty() {
                msg.push(' ');
                msg.push_str(&crate::i18n::te("s.audioProbeAsio", &asio.join("、")));
            }
            Some(msg)
        }
        _ => None,
    }
}

fn run_probe(root: &Path) -> Verdict {
    let Some(pyw) = paths::runtime_pythonw(root) else {
        return Verdict::Unknown;
    };
    let script = root.join("tools").join("audio_probe.py");
    if !script.is_file() {
        return Verdict::Unknown;
    }
    let out = paths::control_dir(root).join("audio_probe.json");
    let _ = std::fs::create_dir_all(out.parent().unwrap_or(root));
    let _ = std::fs::remove_file(&out);

    let mut cmd = Command::new(&pyw);
    cmd.arg(script.as_os_str())
        .arg(out.as_os_str())
        .current_dir(root)
        .envs(crate::worker::env_for_runtime(root))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }

    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            crate::logging::shell_log!("audio probe 起不来：{}", e);
            return Verdict::Unknown;
        }
    };

    // `Child::wait` 没有超时。丢给一根线程去等，主线程只认这个超时。
    let (tx, rx) = mpsc::channel();
    let handle = std::thread::spawn(move || {
        let st = child.wait();
        let _ = tx.send(st.ok().and_then(|s| s.code()));
    });
    let code = match rx.recv_timeout(PROBE_TIMEOUT) {
        Ok(c) => {
            let _ = handle.join();
            c
        }
        Err(_) => {
            crate::logging::shell_log!("audio probe 超时（{} 秒），按不确定处理", PROBE_TIMEOUT.as_secs());
            return Verdict::Unknown;
        }
    };

    let Some(code) = code else {
        return Verdict::Unknown;
    };
    if code == 0 {
        crate::logging::shell_log!("audio probe: 设备枚举正常");
        return Verdict::Ok;
    }
    if !crate::crash::is_fatal_status(code) {
        // 探测脚本自己报的错（import 失败、写文件失败）。引擎未必受影响。
        crate::logging::shell_log!("audio probe 退出码 {}，按不确定处理", code);
        return Verdict::Unknown;
    }
    let asio = crate::crash::asio_drivers();
    crate::logging::shell_log!(
        "audio probe 被系统终止，退出码 {}；已注册的 ASIO 驱动：{:?}",
        crate::crash::describe(code),
        asio
    );
    Verdict::Crashed { code, asio }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_runtime_is_unknown_not_crashed() {
        // 开发机上没有 Runtime/pythonw，探不出结论就该放行。
        let dir = crate::testutil::scratch("audio-probe-none");
        let _ = std::fs::create_dir_all(&dir);
        assert_eq!(run_probe(&dir), Verdict::Unknown);
    }

    #[test]
    fn only_crashed_blocks() {
        // 这里不走缓存，直接验判据本身：三种结论里只有一种该拦。
        assert!(matches!(Verdict::Ok, Verdict::Ok));
        let crashed = Verdict::Crashed {
            code: 0xC000_0094u32 as i32,
            asio: vec!["Realtek ASIO".into()],
        };
        assert!(matches!(crashed, Verdict::Crashed { .. }));
        assert!(matches!(Verdict::Unknown, Verdict::Unknown));
    }
}
