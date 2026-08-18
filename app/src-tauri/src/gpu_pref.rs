//! 混合显卡笔记本上，把本程序的图形首选项钉在集显上。
//!
//! 26.8.18 的用户报告：一开训练整个窗口就变纯黑。日志里「界面已挂载」写了、
//! 白屏告警没有、主线程看门狗全程没报 —— HTML 和事件循环都是好的，只是不
//! 往屏幕上画。那台是 RTX 5060 Laptop + AMD 610M，训练把 8G 显存吃光，
//! WebView2 的合成表面申请不到显存，整窗就黑了。
//!
//! Windows 的「图形首选项」按 exe 路径记在 HKCU 下的一行值。写成「节能」
//! 就是让本程序用集显合成，独显整张留给训练。CUDA 不看这个键，python 又是
//! 另一个 exe，推理和训练都不受影响。
//!
//! 两条不碰的红线：单显卡机器不写（没有第二块卡可退，写了只是白改用户的
//! 系统设置）；用户自己设过就不动（那是他的选择）。

// 非 Windows 上 apply_once 是空函数，判据用不到；测试仍然跑。
#![cfg_attr(not(windows), allow(dead_code))]

/// `GpuPreference=1` 是「节能」，2 是「高性能」，0 是「让 Windows 决定」。
#[cfg(windows)]
const LOW_POWER: &str = "GpuPreference=1;";
#[cfg(windows)]
const KEY: &str = r"Software\Microsoft\DirectX\UserGpuPreferences";

/// 不是真显卡的适配器。远程桌面 / 虚拟屏 / 兜底驱动都会出现在显示适配器
/// 类键里，把它们算进「有两块卡」会让我们在纯单卡机上乱写首选项。
fn is_virtual(name: &str) -> bool {
    let n = name.to_ascii_lowercase();
    [
        "basic display",
        "基本显示",
        "virtual",
        "虚拟",
        "idd",
        "parsec",
        "displaylink",
        "remote",
        "citrix",
        "vmware",
        "virtualbox",
        "hyper-v",
        "meta ",
        "oray",
        "todesk",
    ]
    .iter()
    .any(|k| n.contains(k))
}

/// 独显。有独显才谈得上「独显被训练占满、界面退回集显」这件事。
fn is_discrete(name: &str) -> bool {
    let n = name.to_ascii_lowercase();
    if n.contains("nvidia") || n.contains("geforce") || n.contains("quadro") || n.contains("rtx")
    {
        return true;
    }
    // AMD 的集显叫 Radeon(TM) 610M / 780M / Graphics，独显是 RX 系列和 Pro。
    n.contains("radeon rx") || n.contains("radeon pro") || n.contains("radeon(tm) rx")
        // Intel 独显是 Arc，核显是 UHD / Iris。
        || n.contains("intel(r) arc")
}

/// 该不该把界面赶到集显上：至少两块真显卡，其中一块是独显。
pub fn should_prefer_low_power(gpus: &[String]) -> bool {
    let real: Vec<&String> = gpus.iter().filter(|g| !is_virtual(g)).collect();
    real.len() >= 2 && real.iter().any(|g| is_discrete(g))
}

#[cfg(windows)]
mod imp {
    use super::{KEY, LOW_POWER};
    use std::ffi::{OsStr, OsString};
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    use windows_sys::Win32::Foundation::ERROR_SUCCESS;
    use windows_sys::Win32::System::Registry::{
        RegCloseKey, RegCreateKeyExW, RegOpenKeyExW, RegQueryValueExW, RegSetValueExW, HKEY,
        HKEY_CURRENT_USER, KEY_READ, KEY_WRITE, REG_SZ,
    };

    fn wide(s: &str) -> Vec<u16> {
        OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
    }

    fn exe_path() -> Option<String> {
        std::env::current_exe().ok().map(|p| p.display().to_string())
    }

    /// 注册表里这个 exe 现在的首选项。没有键 / 没有值都返回 None。
    pub fn current() -> Option<String> {
        let exe = exe_path()?;
        unsafe {
            let mut key: HKEY = std::ptr::null_mut();
            if RegOpenKeyExW(HKEY_CURRENT_USER, wide(KEY).as_ptr(), 0, KEY_READ, &mut key)
                != ERROR_SUCCESS
            {
                return None;
            }
            let mut buf = [0u16; 256];
            let mut cb: u32 = std::mem::size_of_val(&buf) as u32;
            let rc = RegQueryValueExW(
                key,
                wide(&exe).as_ptr(),
                std::ptr::null(),
                std::ptr::null_mut(),
                buf.as_mut_ptr() as *mut u8,
                &mut cb,
            );
            RegCloseKey(key);
            if rc != ERROR_SUCCESS || cb < 2 {
                return None;
            }
            let chars = (cb as usize / 2).saturating_sub(1).min(buf.len());
            let s = OsString::from_wide(&buf[..chars]).to_string_lossy().to_string();
            if s.is_empty() {
                None
            } else {
                Some(s)
            }
        }
    }

    pub fn write_low_power() -> Result<(), String> {
        let exe = exe_path().ok_or("current_exe 读不到")?;
        unsafe {
            let mut key: HKEY = std::ptr::null_mut();
            if RegCreateKeyExW(
                HKEY_CURRENT_USER,
                wide(KEY).as_ptr(),
                0,
                std::ptr::null(),
                0,
                KEY_WRITE,
                std::ptr::null(),
                &mut key,
                std::ptr::null_mut(),
            ) != ERROR_SUCCESS
            {
                return Err(format!(
                    "建 UserGpuPreferences 键失败 WinError {}",
                    std::io::Error::last_os_error().raw_os_error().unwrap_or(0)
                ));
            }
            let mut val = wide(LOW_POWER);
            let rc = RegSetValueExW(
                key,
                wide(&exe).as_ptr(),
                0,
                REG_SZ,
                val.as_mut_ptr() as *mut u8,
                (val.len() * 2) as u32,
            );
            RegCloseKey(key);
            if rc != ERROR_SUCCESS {
                return Err(format!(
                    "写图形首选项失败 WinError {}",
                    std::io::Error::last_os_error().raw_os_error().unwrap_or(0)
                ));
            }
        }
        Ok(())
    }
}

/// 启动时跑一次。单显卡、用户设过、写失败都只写日志，不打扰用户。
#[cfg(windows)]
pub fn apply_once() {
    let gpus = crate::provision::list_gpus();
    if !should_prefer_low_power(&gpus) {
        return;
    }
    if let Some(cur) = imp::current() {
        crate::logging::shell_log!("图形首选项：已有设置 {cur}，不动");
        return;
    }
    match imp::write_low_power() {
        Ok(()) => crate::logging::shell_log!(
            "图形首选项：本程序设为节能（用集显合成界面），独显留给推理与训练"
        ),
        Err(e) => crate::logging::shell_log!("图形首选项：写入失败 {e}"),
    }
}

#[cfg(not(windows))]
pub fn apply_once() {}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn hybrid_laptop_gets_the_preference() {
        assert!(should_prefer_low_power(&v(&[
            "NVIDIA GeForce RTX 5060 Laptop GPU",
            "AMD Radeon(TM) 610M",
        ])));
        assert!(should_prefer_low_power(&v(&[
            "Intel(R) UHD Graphics",
            "NVIDIA GeForce GTX 1650",
        ])));
    }

    #[test]
    fn single_gpu_is_left_alone() {
        // 台机一块独显：没有第二块卡可退，写了只是白改用户的系统设置。
        assert!(!should_prefer_low_power(&v(&["NVIDIA GeForce RTX 4090"])));
        assert!(!should_prefer_low_power(&v(&["Intel(R) Iris(R) Xe Graphics"])));
    }

    #[test]
    fn a_virtual_adapter_does_not_count_as_a_second_card() {
        // 这条是防我们在纯单卡机上乱写：远程桌面、虚拟屏、兜底驱动都会
        // 出现在显示适配器类键里。
        assert!(!should_prefer_low_power(&v(&[
            "NVIDIA GeForce RTX 4090",
            "Microsoft 基本显示适配器",
        ])));
        assert!(!should_prefer_low_power(&v(&[
            "NVIDIA GeForce RTX 4090",
            "Parsec Virtual Display Adapter",
        ])));
        assert!(!should_prefer_low_power(&v(&[
            "NVIDIA GeForce RTX 4090",
            "ToDesk Virtual Display",
        ])));
    }

    #[test]
    fn two_integrated_only_is_not_our_case() {
        assert!(!should_prefer_low_power(&v(&[
            "Intel(R) UHD Graphics",
            "AMD Radeon(TM) 610M",
        ])));
    }
}
