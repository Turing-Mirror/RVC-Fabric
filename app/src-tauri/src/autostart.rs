//! 开机自启动 —— `HKCU\...\CurrentVersion\Run` 注册表键。
//!
//! 不用 `tauri-plugin-autostart`：产品是 Windows 专属，注册表三行读写就能
//! 做到，少一个插件依赖；值永远指向当前 exe（`current_exe`），用户装到
//! 哪个目录、覆盖安装到哪个目录，自启都指向最新安装位置。
//!
//! 状态以注册表为准（设置页开关即真实生效状态），不写进 `app_config` ——
//! 配置档案是产品语义的真相来源，自启是这台机器的行为，不该跟着档案走。

use serde::Serialize;

/// Run 键路径。值名保持稳定：改掉会让已开启自启的用户悄悄失去自启。
const RUN_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
const VALUE_NAME: &str = "RVC Fabric";

#[derive(Serialize, Debug, PartialEq)]
pub struct AutostartStatus {
    pub enabled: bool,
    /// 注册表里当前的值（可能是别处装的 exe），自启用。
    pub path: String,
}

#[cfg(windows)]
mod imp {
    use super::{AutostartStatus, RUN_KEY, VALUE_NAME};
    use std::ffi::{OsStr, OsString};
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    use windows_sys::Win32::Foundation::ERROR_SUCCESS;
    use windows_sys::Win32::System::Registry::{
        RegCloseKey, RegCreateKeyExW, RegDeleteValueW, RegOpenKeyExW, RegQueryValueExW,
        RegSetValueExW, HKEY, HKEY_CURRENT_USER, KEY_READ, KEY_WRITE, REG_SZ,
    };

    fn wide(s: &str) -> Vec<u16> {
        OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
    }

    fn last_win_error() -> String {
        format!(
            "WinError {}",
            std::io::Error::last_os_error().raw_os_error().unwrap_or(0)
        )
    }

    /// 读 Run 值；键不存在 / 值不存在 / 读失败一律当未开启。
    pub fn read_value() -> AutostartStatus {
        let mut out = AutostartStatus { enabled: false, path: String::new() };
        unsafe {
            let mut key: HKEY = std::ptr::null_mut();
            if RegOpenKeyExW(HKEY_CURRENT_USER, wide(RUN_KEY).as_ptr(), 0, KEY_READ, &mut key)
                != ERROR_SUCCESS
            {
                return out;
            }
            let mut buf = [0u16; 1024];
            let mut cb: u32 = std::mem::size_of_val(&buf) as u32;
            let rc = RegQueryValueExW(
                key,
                wide(VALUE_NAME).as_ptr(),
                std::ptr::null(),
                std::ptr::null_mut(),
                buf.as_mut_ptr() as *mut u8,
                &mut cb,
            );
            RegCloseKey(key);
            if rc == ERROR_SUCCESS && cb > 2 {
                // cb 是字节数、含结尾 NUL；去掉它。
                let chars = (cb as usize / 2).saturating_sub(1);
                out.path = OsString::from_wide(&buf[..chars.min(buf.len())])
                    .to_string_lossy()
                    .to_string();
                out.enabled = !out.path.is_empty();
            }
        }
        out
    }

    /// 写 / 删 Run 值。`enabled=true` 时写入 `"<当前 exe>"`（带引号，
    /// 防安装路径含空格）。失败返回 Windows 错误描述。
    pub fn write_value(enabled: bool) -> Result<(), String> {
        unsafe {
            let mut key: HKEY = std::ptr::null_mut();
            if RegCreateKeyExW(
                HKEY_CURRENT_USER,
                wide(RUN_KEY).as_ptr(),
                0,
                std::ptr::null(),
                0,
                KEY_WRITE,
                std::ptr::null(),
                &mut key,
                std::ptr::null_mut(),
            ) != ERROR_SUCCESS
            {
                return Err(format!("open Run key: {}", last_win_error()));
            }
            let rc = if enabled {
                let exe = std::env::current_exe()
                    .map_err(|e| format!("current_exe: {e}"))?;
                let quoted = format!("\"{}\"", exe.display());
                let mut val = wide(&quoted);
                RegSetValueExW(
                    key,
                    wide(VALUE_NAME).as_ptr(),
                    0,
                    REG_SZ,
                    val.as_mut_ptr() as *mut u8,
                    (val.len() * 2) as u32,
                )
            } else {
                RegDeleteValueW(key, wide(VALUE_NAME).as_ptr())
            };
            RegCloseKey(key);
            if rc != ERROR_SUCCESS {
                return Err(format!("write Run value: {}", last_win_error()));
            }
        }
        Ok(())
    }
}

#[cfg(not(windows))]
mod imp {
    use super::AutostartStatus;
    pub fn read_value() -> AutostartStatus {
        AutostartStatus { enabled: false, path: String::new() }
    }
    pub fn write_value(_enabled: bool) -> Result<(), String> {
        Err("autostart is only supported on Windows".into())
    }
}

pub fn get() -> AutostartStatus {
    imp::read_value()
}

pub fn set(enabled: bool) -> Result<(), String> {
    imp::write_value(enabled)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 真注册表 roundtrip：写开 → 读到开且值是当前 exe → 写关 → 读到关。
    /// 测试结束按进入时的状态恢复，不留残留（值名固定，跑完即还原）。
    #[test]
    fn registry_roundtrip() {
        let before = get();
        let result = (|| -> Result<(), String> {
            set(true)?;
            let on = get();
            assert!(on.enabled, "enabled should be true after set(true)");
            let exe = std::env::current_exe().map_err(|e| e.to_string())?;
            let want = format!("\"{}\"", exe.display());
            assert_eq!(on.path, want, "Run value must point at the current exe");
            set(false)?;
            let off = get();
            assert!(!off.enabled, "enabled should be false after set(false)");
            assert!(off.path.is_empty(), "path should be empty after disable");
            Ok(())
        })();
        // 恢复进入前的状态，即使上面的断言失败也要还原。
        let _ = set(before.enabled);
        result.expect("registry roundtrip failed");
    }
}
