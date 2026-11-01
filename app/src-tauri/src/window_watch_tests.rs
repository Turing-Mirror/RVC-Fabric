//! Real Windows regression: tool windows configure their frame from an async command.
//! Run explicitly with `cargo test --lib --release tool_frame_from_worker -- --ignored`.

use super::*;
use std::sync::mpsc;
use tauri::{WebviewUrl, WebviewWindowBuilder};
use windows_sys::Win32::UI::Shell::GetWindowSubclass;
use windows_sys::Win32::UI::WindowsAndMessaging::{
    GetClientRect, GetWindowRect, IsZoomed, SendMessageW, ShowWindow, MINMAXINFO,
    SW_HIDE, SW_MAXIMIZE, SW_RESTORE, WM_GETMINMAXINFO,
};

#[test]
#[ignore = "requires a Windows desktop session with WebView2"]
fn tool_frame_from_worker_installs_on_the_window_thread() {
    let (tx, rx) = mpsc::channel();
    let app = tauri::Builder::default()
        .any_thread()
        .setup(move |app| {
            let win = WebviewWindowBuilder::new(
                app,
                "tool-frame-test",
                WebviewUrl::External("about:blank".parse().unwrap()),
            )
            .visible(false)
            .decorations(false)
            .shadow(false)
            .inner_size(720.0, 780.0)
            .data_directory(std::env::temp_dir().join(format!(
                "rvc-frame-test-{}",
                std::process::id()
            )))
            .build()?;
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                // This is the same thread boundary as the async tools_open command.
                round_corners(&win);
                let check = win.clone();
                win.run_on_main_thread(move || {
                    let hwnd = check.hwnd().unwrap().0 as windows_sys::Win32::Foundation::HWND;
                    let result = std::panic::catch_unwind(|| unsafe {
                        let mut data = 0;
                        assert_ne!(
                            GetWindowSubclass(hwnd, Some(work_area_subclass_proc), 0x5246_4357, &mut data),
                            0,
                            "async tool creation must install the work-area subclass"
                        );
                        let (work, mon) = monitor_work_and_full(hwnd).unwrap();
                        let mut limits: MINMAXINFO = std::mem::zeroed();
                        SendMessageW(hwnd, WM_GETMINMAXINFO, 0, &mut limits as *mut _ as isize);
                        assert_eq!(limits.ptMaxPosition.x, work.left - mon.left);
                        assert_eq!(limits.ptMaxPosition.y, work.top - mon.top);
                        assert_eq!(limits.ptMaxSize.x, work.right - work.left);
                        assert_eq!(limits.ptMaxSize.y, work.bottom - work.top);

                        let mut outer = std::mem::zeroed();
                        let mut client = std::mem::zeroed();
                        assert_ne!(GetWindowRect(hwnd, &mut outer), 0);
                        assert_ne!(GetClientRect(hwnd, &mut client), 0);
                        assert_eq!(outer.right - outer.left, client.right);
                        assert_eq!(outer.bottom - outer.top, client.bottom);

                        for _ in 0..3 {
                            ShowWindow(hwnd, SW_MAXIMIZE);
                            let mut maximized = std::mem::zeroed();
                            assert_ne!(GetWindowRect(hwnd, &mut maximized), 0);
                            assert_ne!(IsZoomed(hwnd), 0);
                            assert_eq!(
                                (maximized.left, maximized.top, maximized.right, maximized.bottom),
                                (work.left, work.top, work.right, work.bottom),
                                "maximizing must leave the taskbar's work-area exclusion intact"
                            );
                            ShowWindow(hwnd, SW_RESTORE);
                            let mut restored = std::mem::zeroed();
                            assert_ne!(GetWindowRect(hwnd, &mut restored), 0);
                            assert_eq!(IsZoomed(hwnd), 0);
                            assert_eq!(
                                (restored.left, restored.top, restored.right, restored.bottom),
                                (outer.left, outer.top, outer.right, outer.bottom),
                                "restore must retain the original position and size"
                            );
                        }
                    });
                    unsafe { ShowWindow(hwnd, SW_HIDE); }
                    tx.send(result.map_err(|_| "tool frame regression failed")).unwrap();
                    handle.exit(0);
                })
                .unwrap();
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("build isolated frame test app");
    assert_eq!(app.run_return(|_, _| {}), 0);
    rx.recv().unwrap().unwrap();
}
