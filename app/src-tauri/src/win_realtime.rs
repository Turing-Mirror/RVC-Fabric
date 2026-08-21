//! Keep the shell and pythonw off Windows 11 EcoQoS.
//!
//! pythonw has no window. Game Mode treats it as a background process and
//! throttles it the moment a fullscreen game takes the screen — inference
//! then misses the audio deadline (diag 26.8.21/1).

#![cfg_attr(not(windows), allow(dead_code))]

pub fn boost_current() {
    #[cfg(windows)]
    imp::boost_current();
}

#[cfg(windows)]
pub fn boost_child(child: &std::process::Child) {
    use std::os::windows::io::AsRawHandle;
    imp::boost_handle(child.as_raw_handle());
}

#[cfg(not(windows))]
pub fn boost_child(_child: &std::process::Child) {}

#[cfg(windows)]
mod imp {
    use std::os::windows::io::RawHandle;
    use windows_sys::Win32::Foundation::HANDLE;
    use windows_sys::Win32::System::Threading::{
        GetCurrentProcess, SetPriorityClass, ABOVE_NORMAL_PRIORITY_CLASS,
    };

    #[repr(C)]
    struct PowerThrottling {
        version: u32,
        control_mask: u32,
        state_mask: u32,
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn SetProcessInformation(
            hprocess: HANDLE,
            class: i32,
            info: *const core::ffi::c_void,
            size: u32,
        ) -> i32;
    }

    const PROCESS_POWER_THROTTLING: i32 = 4;
    const EXECUTION_SPEED: u32 = 0x1;

    pub fn boost_current() {
        unsafe { boost_handle(GetCurrentProcess() as RawHandle) }
    }

    pub fn boost_handle(raw: RawHandle) {
        if raw.is_null() {
            return;
        }
        let h = raw as HANDLE;
        unsafe {
            let _ = SetPriorityClass(h, ABOVE_NORMAL_PRIORITY_CLASS);
            let mut state = PowerThrottling {
                version: 1,
                control_mask: EXECUTION_SPEED,
                state_mask: 0,
            };
            let _ = SetProcessInformation(
                h,
                PROCESS_POWER_THROTTLING,
                (&mut state as *mut PowerThrottling).cast(),
                std::mem::size_of::<PowerThrottling>() as u32,
            );
        }
    }
}
