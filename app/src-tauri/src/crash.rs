//! 判读 worker 的异常退出码，并说出可能的祸首。
//!
//! Windows 上把 worker 干掉的常常不是 Python 异常，而是第三方驱动在我们的
//! 进程里炸掉：26.8.21 那份诊断包里是 Realtek 的 ASIO 驱动 rthdasio64.dll
//! 整数除零（0xC0000094）——PortAudio 初始化时会把注册表里注册的每个 ASIO
//! 驱动都加载起来问一遍，问到坏的就当场没了。这类退出没有 traceback，而壳子
//! 以前 spawn 完就 `std::mem::forget(child)`，退出码也不收，于是九次崩溃在
//! 日志里一个字都没留下，界面只会退回空闲。

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, OnceLock};

/// 本次会话里有没有 worker 被系统终止过。
///
/// 用来决定要不要付探测的钱：正常机器一辈子不会置位，探测也就永远不跑；一旦
/// 出事，下一次点开启之前先去把祸首找出来。
static SAW_FATAL: AtomicBool = AtomicBool::new(false);

pub fn saw_fatal_exit() -> bool {
    SAW_FATAL.load(Ordering::Relaxed)
}

/// 最近一次已知的退出码，按 pid 记。worker 是一次性的，表不会长。
fn table() -> &'static Mutex<HashMap<u32, i32>> {
    static T: OnceLock<Mutex<HashMap<u32, i32>>> = OnceLock::new();
    T.get_or_init(|| Mutex::new(HashMap::new()))
}

/// 记下某个 pid 的退出码。同一个 pid 迟早会被系统复用，所以表满了就清空重来
/// ——这张表只服务「刚刚那个 worker 是怎么没的」，没有保留价值。
pub fn record_exit(pid: u32, code: i32) {
    if is_fatal_status(code) {
        SAW_FATAL.store(true, Ordering::Relaxed);
    }
    if let Ok(mut m) = table().lock() {
        if m.len() >= 64 {
            m.clear();
        }
        m.insert(pid, code);
    }
}

/// 取回退出码；没记录过就是 None（进程可能还活着，或者根本不是我们起的）。
pub fn exit_code_of(pid: u32) -> Option<i32> {
    table().lock().ok().and_then(|m| m.get(&pid).copied())
}

pub fn forget_exit(pid: u32) {
    if let Ok(mut m) = table().lock() {
        m.remove(&pid);
    }
}

/// NTSTATUS 区间：0xC0000000 起是错误码，正常退出用不到这个范围。
pub fn is_fatal_status(code: i32) -> bool {
    (code as u32) >= 0xC000_0000
}

/// 认得出来的崩溃类型 → 语言包 key。认不出来就只报十六进制。
pub fn status_key(code: i32) -> Option<&'static str> {
    match code as u32 {
        0xC000_0005 => Some("s.exitAccessViolation"),
        0xC000_0094 => Some("s.exitDivideByZero"),
        0xC000_001D => Some("s.exitIllegalInstruction"),
        0xC000_0409 => Some("s.exitStackBufferOverrun"),
        0xC000_00FD => Some("s.exitStackOverflow"),
        0xC000_0135 | 0xC000_0139 => Some("s.exitMissingDll"),
        0xC000_013A => Some("s.exitInterrupted"),
        _ => None,
    }
}

/// 「0xC0000094（整数除零）」/「0xC0000123」/「3」——给日志和界面共用。
pub fn describe(code: i32) -> String {
    if !is_fatal_status(code) {
        return code.to_string();
    }
    let hex = format!("0x{:08X}", code as u32);
    match status_key(code) {
        Some(k) => format!("{hex}（{}）", crate::i18n::t(k)),
        None => hex,
    }
}

/// 注册表里注册过的 ASIO 驱动名。只读，不需要管理员。
///
/// PortAudio 会把这里的每一项都 CoCreateInstance 起来问参数，所以引擎一崩在
/// 音频枚举上，嫌疑人就在这张表里。空表说明这台机器没装 ASIO，那就是别的
/// 原因，别顺口栽赃。
#[cfg(windows)]
pub fn asio_drivers() -> Vec<String> {
    use std::ffi::{OsStr, OsString};
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    use windows_sys::Win32::Foundation::ERROR_SUCCESS;
    use windows_sys::Win32::System::Registry::{
        RegCloseKey, RegEnumKeyExW, RegOpenKeyExW, HKEY, HKEY_LOCAL_MACHINE, KEY_READ,
    };

    fn wide(s: &str) -> Vec<u16> {
        OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
    }

    let mut out: Vec<String> = Vec::new();
    unsafe {
        let mut key: HKEY = std::ptr::null_mut();
        if RegOpenKeyExW(
            HKEY_LOCAL_MACHINE,
            wide(r"SOFTWARE\ASIO").as_ptr(),
            0,
            KEY_READ,
            &mut key,
        ) != ERROR_SUCCESS
        {
            return out;
        }
        let mut i: u32 = 0;
        loop {
            let mut name = [0u16; 256];
            let mut len: u32 = name.len() as u32;
            if RegEnumKeyExW(
                key,
                i,
                name.as_mut_ptr(),
                &mut len,
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
            ) != ERROR_SUCCESS
            {
                break;
            }
            i += 1;
            let sub = OsString::from_wide(&name[..len as usize])
                .to_string_lossy()
                .trim()
                .to_string();
            // 支持渠道让用户改名停用过的会带这个后缀，别再算进嫌疑人里。
            if sub.is_empty() || sub.ends_with(".tm-disabled") {
                continue;
            }
            if !out.contains(&sub) {
                out.push(sub);
            }
        }
        RegCloseKey(key);
    }
    out
}

#[cfg(not(windows))]
pub fn asio_drivers() -> Vec<String> {
    Vec::new()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fatal_status_starts_at_c0000000() {
        assert!(!is_fatal_status(0));
        assert!(!is_fatal_status(1));
        // 正常退出码不该被当成崩溃，哪怕是 Python 的 sys.exit(3)。
        assert!(!is_fatal_status(3));
        assert!(is_fatal_status(0xC000_0005u32 as i32));
        assert!(is_fatal_status(0xC000_0094u32 as i32));
    }

    /// 0821 用户日志里的原文：rthdasio64.dll，异常代码 0xc0000094。
    #[test]
    fn divide_by_zero_is_named() {
        let code = 0xC000_0094u32 as i32;
        assert_eq!(status_key(code), Some("s.exitDivideByZero"));
        assert!(describe(code).starts_with("0xC0000094"));
    }

    #[test]
    fn unknown_status_still_shows_hex() {
        let code = 0xC000_0123u32 as i32;
        assert_eq!(status_key(code), None);
        assert_eq!(describe(code), "0xC0000123");
    }

    #[test]
    fn normal_exit_is_plain_decimal() {
        assert_eq!(describe(0), "0");
        assert_eq!(describe(3), "3");
    }

    #[test]
    fn a_fatal_exit_arms_the_probe_and_a_normal_one_does_not() {
        // 这个标志是全局的，测试之间不互相清 —— 先钉住「正常退出不置位」这半边，
        // 再看致命退出把它抬起来。
        record_exit(4241, 0);
        record_exit(4241, 1);
        forget_exit(4241);
        record_exit(4243, 0xC000_0005u32 as i32);
        assert!(saw_fatal_exit());
        forget_exit(4243);
    }

    #[test]
    fn table_records_and_forgets() {
        record_exit(4242, 0xC000_0005u32 as i32);
        assert_eq!(exit_code_of(4242), Some(0xC000_0005u32 as i32));
        forget_exit(4242);
        assert_eq!(exit_code_of(4242), None);
    }
}
