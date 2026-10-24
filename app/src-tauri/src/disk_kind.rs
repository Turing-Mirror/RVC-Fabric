//! 安装位置是不是机械硬盘：问系统这块盘有没有「寻道代价」。
//!
//! 装在机械硬盘上，开机后第一次载入推理库要读几 GB 零散文件，
//! 底栏据此提示用户换到固态硬盘。查不出来一律当不是。

use std::path::Path;
use std::sync::OnceLock;

static ON_HDD: OnceLock<bool> = OnceLock::new();

/// 结果整个进程只查一次：安装位置在运行期间不会变。
pub fn install_on_hdd(root: &Path) -> bool {
    *ON_HDD.get_or_init(|| volume_of(root).map(|v| seek_penalty(&v)).unwrap_or(false))
}

/// `E:\RVC Fabric` → `E:`。网络路径等没有盘符的情况返回 None。
fn volume_of(root: &Path) -> Option<String> {
    let canon = root.canonicalize().unwrap_or_else(|_| root.to_path_buf());
    let s = canon.to_string_lossy();
    let s = s.strip_prefix(r"\\?\").unwrap_or(&s);
    let mut chars = s.chars();
    match (chars.next(), chars.next()) {
        (Some(c), Some(':')) if c.is_ascii_alphabetic() => Some(format!("{c}:")),
        _ => None,
    }
}

#[cfg(windows)]
fn seek_penalty(volume: &str) -> bool {
    use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::Storage::FileSystem::{
        CreateFileW, FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING,
    };
    use windows_sys::Win32::System::Ioctl::{
        PropertyStandardQuery, StorageDeviceSeekPenaltyProperty, DEVICE_SEEK_PENALTY_DESCRIPTOR,
        IOCTL_STORAGE_QUERY_PROPERTY, STORAGE_PROPERTY_QUERY,
    };
    use windows_sys::Win32::System::IO::DeviceIoControl;

    let name: Vec<u16> = format!(r"\\.\{volume}")
        .encode_utf16()
        .chain(std::iter::once(0))
        .collect();
    // 不要读写权限：只查属性，普通用户也能打开。
    let h = unsafe {
        CreateFileW(
            name.as_ptr(),
            0,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            std::ptr::null(),
            OPEN_EXISTING,
            0,
            std::ptr::null_mut(),
        )
    };
    if h == INVALID_HANDLE_VALUE {
        return false;
    }
    let query = STORAGE_PROPERTY_QUERY {
        PropertyId: StorageDeviceSeekPenaltyProperty,
        QueryType: PropertyStandardQuery,
        AdditionalParameters: [0],
    };
    let mut out = DEVICE_SEEK_PENALTY_DESCRIPTOR {
        Version: 0,
        Size: 0,
        IncursSeekPenalty: 0,
    };
    let mut got = 0u32;
    let ok = unsafe {
        DeviceIoControl(
            h,
            IOCTL_STORAGE_QUERY_PROPERTY,
            &query as *const _ as *const _,
            std::mem::size_of::<STORAGE_PROPERTY_QUERY>() as u32,
            &mut out as *mut _ as *mut _,
            std::mem::size_of::<DEVICE_SEEK_PENALTY_DESCRIPTOR>() as u32,
            &mut got,
            std::ptr::null_mut(),
        )
    };
    unsafe { CloseHandle(h) };
    ok != 0 && got as usize >= std::mem::size_of::<DEVICE_SEEK_PENALTY_DESCRIPTOR>() && out.IncursSeekPenalty != 0
}

#[cfg(not(windows))]
fn seek_penalty(_volume: &str) -> bool {
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn volume_is_the_drive_letter() {
        assert_eq!(volume_of(Path::new(r"E:\RVC Fabric")).as_deref(), Some("E:"));
        assert_eq!(volume_of(Path::new(r"\\server\share\x")), None);
    }
}
