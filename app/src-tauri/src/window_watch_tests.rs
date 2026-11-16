//! Windows integration test with isolated WebView windows and the real resize callback.
//! Run with: cargo test --lib frame_geometry -- --ignored --nocapture

use super::*;
use std::{panic::{catch_unwind, AssertUnwindSafe}, sync::mpsc, time::Duration};
use tauri::{WebviewUrl, WebviewWindowBuilder};
use windows_sys::Win32::Foundation::{HWND, POINT, RECT};
use windows_sys::Win32::Graphics::Gdi::ClientToScreen;
use windows_sys::Win32::UI::Shell::GetWindowSubclass;
use windows_sys::Win32::UI::WindowsAndMessaging::{
    GetClientRect, GetWindowRect, IsZoomed, SendMessageW, ShowWindow,
    NCCALCSIZE_PARAMS, SW_HIDE, SW_MAXIMIZE, SW_RESTORE, WM_NCCALCSIZE,
};

fn coords(rect: RECT) -> (i32, i32, i32, i32) {
    (rect.left, rect.top, rect.right, rect.bottom)
}

unsafe fn client_bounds(hwnd: HWND) -> RECT {
    let mut rect: RECT = std::mem::zeroed();
    let mut origin: POINT = std::mem::zeroed();
    assert_ne!(GetClientRect(hwnd, &mut rect), 0);
    assert_ne!(ClientToScreen(hwnd, &mut origin), 0);
    RECT { left: origin.x, top: origin.y, right: origin.x + rect.right, bottom: origin.y + rect.bottom }
}

fn on_ui<T: Send + 'static>(win: &WebviewWindow, check: impl FnOnce(HWND) -> T + Send + 'static) -> T {
    let (tx, rx) = mpsc::channel();
    let w = win.clone();
    win.run_on_main_thread(move || {
        let result = catch_unwind(AssertUnwindSafe(|| check(w.hwnd().unwrap().0 as HWND)));
        let _ = tx.send(result);
    }).unwrap();
    match rx.recv_timeout(Duration::from_secs(10)).expect("window callback completed") {
        Ok(value) => value,
        Err(error) => std::panic::resume_unwind(error),
    }
}

#[test]
#[ignore = "requires a Windows desktop session with WebView2"]
fn tool_frame_from_worker_frame_geometry_and_main_window() {
    let (tx, rx) = mpsc::channel();
    let app = tauri::Builder::default()
        .any_thread()
        .setup(move |app| {
            let make = |label: &str| {
                let win = WebviewWindowBuilder::new(app, label, WebviewUrl::External("about:blank".parse().unwrap()))
                    .title("Frame regression").visible(false).focused(false).skip_taskbar(true)
                    .decorations(false).shadow(false).inner_size(720.0, 640.0)
                    .data_directory(std::env::temp_dir().join(format!("trm-frame-test-{}", std::process::id())))
                    .build()?;
                let w = win.clone();
                win.on_window_event(move |event| {
                    if matches!(event, tauri::WindowEvent::Resized(_) | tauri::WindowEvent::ScaleFactorChanged { .. }) {
                        refresh_corners(&w);
                    }
                });
                Ok::<_, tauri::Error>(win)
            };
            let main = make("frame-main")?;
            let worker = make("frame-worker")?;
            round_corners(&main);
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                round_corners(&worker);
                let windows = [main, worker];
                let result = catch_unwind(AssertUnwindSafe(|| {
                    for win in &windows {
                        let normal = on_ui(win, |hwnd| unsafe {
                            let mut data = 0;
                            assert_ne!(GetWindowSubclass(hwnd, Some(work_area_subclass_proc), 0x5246_4357, &mut data), 0, "frame callback must be installed on the owning thread");
                            let mut rect: RECT = std::mem::zeroed();
                            GetWindowRect(hwnd, &mut rect);
                            assert_eq!(coords(client_bounds(hwnd)), coords(rect), "normal borderless client area");
                            coords(rect)
                        });
                        for _ in 0..3 {
                            on_ui(win, |hwnd| unsafe { ShowWindow(hwnd, SW_MAXIMIZE); ShowWindow(hwnd, SW_HIDE); });
                            // Let the real resize callback complete before measuring.
                            std::thread::sleep(Duration::from_millis(80));
                            let (client, work) = on_ui(win, |hwnd| unsafe {
                                assert_ne!(IsZoomed(hwnd), 0);
                                let (work, _) = monitor_work_and_full(hwnd).unwrap();
                                let client = client_bounds(hwnd);
                                assert_eq!(coords(client), coords(work), "maximized content must fit the visible work area exactly");
                                let mut calc: NCCALCSIZE_PARAMS = std::mem::zeroed();
                                calc.rgrc[0] = RECT { left: work.left - 8, top: work.top - 8, right: work.right + 8, bottom: work.bottom + 8 };
                                SendMessageW(hwnd, WM_NCCALCSIZE, 1, &mut calc as *mut _ as isize);
                                assert_eq!(coords(calc.rgrc[0]), coords(work), "hidden frame must not become page content");
                                (coords(client), coords(work))
                            });
                            println!("{} maximized client={client:?} work={work:?}", win.label());
                            on_ui(win, |hwnd| unsafe { ShowWindow(hwnd, SW_RESTORE); ShowWindow(hwnd, SW_HIDE); });
                            std::thread::sleep(Duration::from_millis(80));
                            on_ui(win, move |hwnd| unsafe {
                                assert_eq!(IsZoomed(hwnd), 0);
                                let mut restored: RECT = std::mem::zeroed();
                                GetWindowRect(hwnd, &mut restored);
                                assert_eq!(coords(restored), normal, "restore retains original position and size");
                                assert_eq!(coords(client_bounds(hwnd)), normal);
                            });
                        }
                    }
                }));
                for win in &windows { let _ = win.hide(); }
                tx.send(result.map_err(|_| "native frame geometry regression failed")).unwrap();
                handle.exit(0);
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("build isolated frame test app");
    assert_eq!(app.run_return(|_, _| {}), 0);
    rx.recv().unwrap().unwrap();
}
