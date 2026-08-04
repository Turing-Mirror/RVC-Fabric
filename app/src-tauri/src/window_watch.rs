//! 窗口位置的取证与自救。
//!
//! 「看不见窗口」从外面看是一句话，里面至少是三件事：窗口没建起来、建起来但
//! 是隐藏的、可见但开在了用户看不到的那块屏上。三者修法完全相反，而用户手上
//! 只有「看不见」，所以先让窗口自己把状态写进 shell.log。
//!
//! 里面最难自己发现的是第三种。Tauri 的 `.center()` 永远居中在**主显示器**，
//! 而多显示器的人正在看的往往不是主屏——窗口和它的任务栏按钮一起去了另一块
//! 屏，用户这头一点动静都没有，和「根本没启动」长得一模一样。所以启动时按
//! 光标所在的显示器摆窗口，光标在哪块屏人就在哪块屏。
//!
//! 注意：Tauri v2 的 `visible` 默认就是 `true`（tauri-utils 的
//! `WindowConfig::default()`），`WebviewWindowBuilder` 从那份默认值起步。
//! 补一句 `.visible(true)` 是空操作，不要指望它能修好任何事。

use tauri::{Monitor, PhysicalPosition, WebviewWindow};

use crate::logging;

/// 圆角是不是得靠自己裁。DWM 那条能走通就一直是 false，Resized 时什么都不做。
#[cfg(windows)]
static NEEDS_REGION: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
#[cfg(windows)]
use std::sync::atomic::Ordering;

/// 屏幕坐标里的一个矩形。几何判断全部收在这里，好单测。
#[derive(Clone, Copy, Debug, PartialEq)]
struct Rect {
    x: i32,
    y: i32,
    w: i32,
    h: i32,
}

impl Rect {
    fn intersects(&self, o: &Rect) -> bool {
        self.x < o.x + o.w && self.x + self.w > o.x && self.y < o.y + o.h && self.y + self.h > o.y
    }

    fn contains(&self, x: i32, y: i32) -> bool {
        x >= self.x && x < self.x + self.w && y >= self.y && y < self.y + self.h
    }

    /// 把一个 w×h 的窗口居中放进本矩形，返回左上角坐标。
    ///
    /// 窗口比屏幕大时贴左上角而不是给出负坐标：负坐标会把标题栏顶出屏幕，
    /// 而这是个无边框窗口，顶出去就再也拖不回来了。
    fn center_for(&self, w: i32, h: i32) -> PhysicalPosition<i32> {
        PhysicalPosition::new(
            self.x + ((self.w - w) / 2).max(0),
            self.y + ((self.h - h) / 2).max(0),
        )
    }
}

fn full(m: &Monitor) -> Rect {
    Rect {
        x: m.position().x,
        y: m.position().y,
        w: m.size().width as i32,
        h: m.size().height as i32,
    }
}

/// 工作区 = 显示器减掉任务栏。摆窗口用它，判断「在不在屏幕上」用整块。
fn work(m: &Monitor) -> Rect {
    let a = m.work_area();
    Rect {
        x: a.position.x,
        y: a.position.y,
        w: a.size.width as i32,
        h: a.size.height as i32,
    }
}

fn win_rect(win: &WebviewWindow) -> Option<Rect> {
    let p = win.outer_position().ok()?;
    let s = win.outer_size().ok()?;
    Some(Rect {
        x: p.x,
        y: p.y,
        w: s.width as i32,
        h: s.height as i32,
    })
}

/// 记录窗口与显示器的真实状态，顺手把隐藏/最小化/跑到屏幕外的情况兜住。
///
/// `phase` 只是日志标签——一次启动会调用两次（建完窗口、12 秒后），两条对比
/// 才能看出窗口是一开始就不对，还是后来被挪走的。
pub fn report_and_rescue(win: &WebviewWindow, phase: &str) {
    let visible = win.is_visible();
    let minimized = win.is_minimized();
    let rect = win_rect(win);

    logging::shell_log!(
        "窗口状态（{phase}）：可见={} 最小化={} 位置={} 尺寸={} 缩放={}",
        opt(&visible),
        opt(&minimized),
        rect.map(|r| format!("{},{}", r.x, r.y))
            .unwrap_or_else(|| "?".into()),
        rect.map(|r| format!("{}x{}", r.w, r.h))
            .unwrap_or_else(|| "?".into()),
        win.scale_factor()
            .map(|f| format!("{f:.2}"))
            .unwrap_or_else(|_| "?".into()),
    );

    let monitors = win.available_monitors().unwrap_or_default();
    if monitors.is_empty() {
        // 远程桌面断开、显卡驱动刚崩过、只挂虚拟显示器的机器上会出现。
        // 这时候 center() 算不出位置，窗口会停在系统给的默认坐标上。
        logging::shell_log!("警告：系统报告 0 个显示器，窗口位置无法校正");
    }
    let primary = win.primary_monitor().ok().flatten();
    for m in &monitors {
        let f = full(m);
        let w = work(m);
        logging::shell_log!(
            "显示器 {}{}：位置 {},{} 尺寸 {}x{} 工作区 {},{} {}x{} 缩放 {:.2}",
            m.name().map(String::as_str).unwrap_or("(无名)"),
            if primary.as_ref().and_then(|p| p.name()) == m.name() {
                "（主）"
            } else {
                ""
            },
            f.x,
            f.y,
            f.w,
            f.h,
            w.x,
            w.y,
            w.w,
            w.h,
            m.scale_factor(),
        );
    }
    // 光标在哪块屏，用户就在哪块屏。写进日志，下次一眼就能看出窗口是不是开
    // 在了另一块屏上——本地看日志的人未必能复现当时的显示器摆法。
    if let Ok(c) = win.cursor_position() {
        logging::shell_log!("光标位置：{:.0},{:.0}", c.x, c.y);
    }

    if minimized.unwrap_or(false) {
        let _ = win.unminimize();
    }
    if !visible.unwrap_or(true) {
        logging::shell_log!("窗口是隐藏的，显示出来");
        let _ = win.show();
    }
    rescue_if_offscreen(win);
}

/// 窗口矩形和任何一台显示器都不相交时，挪回光标所在（退而求其次：主）屏。
/// 返回是否真的挪了。
///
/// 判定用相交而不是包含：窗口被拖到屏幕边缘露出一半是用户自己摆的，把它挪回
/// 中间只会更烦人。
pub fn rescue_if_offscreen(win: &WebviewWindow) -> bool {
    let Some(r) = win_rect(win) else {
        return false;
    };
    let monitors = win.available_monitors().unwrap_or_default();
    if monitors.is_empty() || monitors.iter().any(|m| r.intersects(&full(m))) {
        return false;
    }
    let Some(target) = active_monitor(win, &monitors) else {
        return false;
    };
    let to = work(&target).center_for(r.w, r.h);
    logging::shell_log!("窗口落在所有显示器之外，拉回 {},{}", to.x, to.y);
    let _ = win.set_position(to);
    true
}

/// 启动时把窗口摆到用户正在用的那块屏上。
///
/// 只在建完窗口后调用一次。之后不再动——用户自己把窗口拖到哪块屏是他的事，
/// 隔一会儿被程序挪回来比开错屏还烦。
/// 去掉 DWM 1px 系统描边色（始终关）。
///
/// 只动边框色，**绝不**关 `DWMWA_NCRENDERING_POLICY`：关掉 NC 绘制会把
/// 任务栏也带成黑条（本机实测）。
#[cfg(windows)]
fn hide_dwm_border_color(hwnd: windows_sys::Win32::Foundation::HWND) {
    use windows_sys::Win32::Graphics::Dwm::DwmSetWindowAttribute;
    const DWMWA_BORDER_COLOR: u32 = 34;
    const DWMWA_COLOR_NONE: u32 = 0xFFFFFFFE;
    let color = DWMWA_COLOR_NONE;
    unsafe {
        let _ = DwmSetWindowAttribute(
            hwnd,
            DWMWA_BORDER_COLOR,
            &color as *const _ as *const core::ffi::c_void,
            std::mem::size_of_val(&color) as u32,
        );
    }
}

/// 最大化时摘掉 `WS_THICKFRAME`；还原时加回，否则拖边缩放会坏。
///
/// 无边框 + resizable 的窗口仍带着厚框：平常是隐形命中区；最大化后那圈
/// 非客户区会露成 Aero 描边。动样式后必须 `SWP_FRAMECHANGED`。
///
/// 注意：摘掉厚框后若仍保持「含边框的全屏外框」尺寸，窗口会盖住任务栏，
/// 任务栏看起来像变黑。调用方必须再钳到工作区（见 `fit_maximized_to_work_area`）。
#[cfg(windows)]
fn set_thickframe(hwnd: windows_sys::Win32::Foundation::HWND, enable: bool) {
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetWindowLongW, SetWindowLongW, SetWindowPos, GWL_STYLE, SWP_FRAMECHANGED,
        SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER,
    };
    const WS_THICKFRAME: u32 = 0x0004_0000;
    const WS_BORDER: u32 = 0x0080_0000;
    // SAFETY: hwnd 是我们自己的窗口。
    unsafe {
        let style = GetWindowLongW(hwnd, GWL_STYLE) as u32;
        let new_style = if enable {
            (style | WS_THICKFRAME) & !WS_BORDER
        } else {
            style & !WS_THICKFRAME & !WS_BORDER
        };
        if new_style == style {
            return;
        }
        SetWindowLongW(hwnd, GWL_STYLE, new_style as i32);
        SetWindowPos(
            hwnd,
            std::ptr::null_mut(),
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        );
    }
}

/// 摘掉厚框后，按**当前样式**重新套一次最大化，把外框落到工作区。
///
/// 为什么不用 `set_size` / `set_position`：
/// Tauri 那两条最终会改窗口的「普通尺寸」（`WINDOWPLACEMENT.rcNormalPosition`），
/// 或者直接清掉 `WS_MAXIMIZE`。结果是：看起来已经铺满工作区，但系统眼里
/// 「还原矩形」已经变成工作区本身——再点最大化按钮等于还原到同样大小，
/// 用户感觉「最大化后再点回不去」。
///
/// 正确做法：先 `set_thickframe(false)`，再 `SetWindowPlacement(SW_SHOWMAXIMIZED)`。
/// 系统按当前样式重算最大化矩形（无厚框就不探出任务栏），同时**保留**进最大化
/// 之前写好的 `rcNormalPosition`，还原按钮才能回到原来的尺寸和位置。
#[cfg(windows)]
fn fit_maximized_to_work_area(win: &WebviewWindow) {
    use windows_sys::Win32::Foundation::HWND;
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetWindowPlacement, SetWindowPlacement, WINDOWPLACEMENT, SW_SHOWMAXIMIZED,
    };

    let Ok(hwnd_raw) = win.hwnd() else {
        return;
    };
    let hwnd = hwnd_raw.0 as HWND;
    // SAFETY: hwnd 是本窗口；length 必须先填对，否则 API 直接失败。
    unsafe {
        let mut place: WINDOWPLACEMENT = std::mem::zeroed();
        place.length = std::mem::size_of::<WINDOWPLACEMENT>() as u32;
        if GetWindowPlacement(hwnd, &mut place) == 0 {
            return;
        }
        // 只重放「最大化」指令，不改 rcNormalPosition。
        place.showCmd = SW_SHOWMAXIMIZED as u32;
        let _ = SetWindowPlacement(hwnd, &place);
    }
}

/// 上一次是不是最大化。状态翻转时才动样式，避免每次 Resized 都 FRAMECHANGED。
#[cfg(windows)]
static WAS_MAXIMIZED: std::sync::atomic::AtomicBool =
    std::sync::atomic::AtomicBool::new(false);

/// 最大化时拆掉系统厚框/描边，还原时恢复可缩放。
///
/// **永远不要** `set_shadow(true)`（无边框 + shadow=true = 1px 白边）。
/// **永远不要** 关 `DWMWA_NCRENDERING_POLICY`（会搞黑任务栏）。
#[cfg(windows)]
fn sync_maximized_frame(win: &WebviewWindow) {
    let maximized = win.is_maximized().unwrap_or(false) || win.is_fullscreen().unwrap_or(false);
    let was = WAS_MAXIMIZED.swap(maximized, Ordering::Relaxed);
    let Ok(hwnd_raw) = win.hwnd() else {
        return;
    };
    let hwnd = hwnd_raw.0 as windows_sys::Win32::Foundation::HWND;

    // 始终关 shadow + 关边框色（幂等）。
    let _ = win.set_shadow(false);
    hide_dwm_border_color(hwnd);

    if maximized {
        // 只在进入最大化时改一次：再 Resized（钳尺寸触发的）会 was=true，
        // 若再 fit 会尺寸抖动循环。
        if !was {
            set_thickframe(hwnd, false);
            // 摘厚框后必须钳到工作区，否则盖住任务栏（看起来像任务栏变黑）。
            fit_maximized_to_work_area(win);
            logging::shell_log!("最大化：已摘厚框并钳到工作区（不碰 DWM NC 策略）");
        }
        // 区域裁切在最大化时必须撤掉，否则四角露桌面。
        if NEEDS_REGION.load(Ordering::Relaxed) {
            use windows_sys::Win32::Graphics::Gdi::SetWindowRgn;
            unsafe {
                SetWindowRgn(hwnd, std::ptr::null_mut(), 1);
            }
        }
    } else if was {
        set_thickframe(hwnd, true);
        hide_dwm_border_color(hwnd);
        if NEEDS_REGION.load(Ordering::Relaxed) {
            apply_corner_region(win);
        }
        logging::shell_log!("还原：已恢复 WS_THICKFRAME（仍无系统描边）");
    } else if NEEDS_REGION.load(Ordering::Relaxed) {
        apply_corner_region(win);
    }
}

/// 给无边框窗口要回系统圆角。
///
/// 走 DWM 的 `DWMWA_WINDOW_CORNER_PREFERENCE`，不走「透明窗口 + CSS 圆角」：
/// 后者要把窗口设成 transparent，于是系统投影一起没了，四角还会露出锯齿边
/// （WebView2 不做窗口级抗锯齿），而且拖动缩放时角上会闪。DWM 这条是系统自己
/// 画的圆角，投影、动画、贴边分屏全都照旧。
///
/// Windows 10 上这个属性不存在，`DwmSetWindowAttribute` 会回一个错误码。
/// 那时候退到 `apply_corner_region`：自己拿 GDI 区域把四角裁掉。
#[cfg(windows)]
pub fn round_corners(win: &WebviewWindow) {
    use windows_sys::Win32::Foundation::HWND;
    use windows_sys::Win32::Graphics::Dwm::{
        DwmSetWindowAttribute, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND,
    };

    let Ok(hwnd) = win.hwnd() else {
        logging::shell_log!("圆角：拿不到 HWND，跳过");
        return;
    };
    let hwnd = hwnd.0 as HWND;
    // 先关系统描边色，避免一启动就有 1px Aero 框。
    hide_dwm_border_color(hwnd);
    let pref = DWMWCP_ROUND;
    // SAFETY: hwnd 来自 Tauri 刚建好的窗口；传的是一个 i32 大小的枚举值，
    // 长度如实给出。属性不支持时函数只是返回错误，不会写回任何东西。
    let hr = unsafe {
        DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE as u32,
            &pref as *const _ as *const core::ffi::c_void,
            std::mem::size_of_val(&pref) as u32,
        )
    };
    // 建窗即关 shadow：与 builder 的 shadow(false) 双保险，避免后续某次
    // set_shadow(true) 把 1px 白边加回来。
    let _ = win.set_shadow(false);
    if hr == 0 {
        logging::shell_log!("圆角：DWM 已生效（无系统描边）");
        // 建窗时若已是最大化（少见），立刻铺满，别等第一次 Resized。
        sync_maximized_frame(win);
        return;
    }
    // 记下走的是兜底那条，之后 Resized 才知道该不该重新裁。DWM 生效的机器上
    // 再去裁一刀，等于拿硬边盖掉系统画好的抗锯齿圆角。
    NEEDS_REGION.store(true, Ordering::Relaxed);
    // Win10 没有这个属性，DWM 这条路走不通。系统不给画就自己画：给窗口套一个
    // 圆角区域，把四角裁掉。区域是按像素算的，窗口一变大小就得重新套，所以
    // 调用方在 Resized 时会再调一次。
    logging::shell_log!("圆角：DWM 不支持（Win10 正常，HRESULT={hr:#x}），改用窗口区域裁切");
    // Win10 上「拖动窗口后左缘留一条永不消失的竖带」也在这条分支里一并治掉。
    // 注意：必须延后到后台线程做，绝不能在建窗现场同步改框架（见函数注释）。
    kill_undecorated_shadow_inset_deferred(win);
    apply_corner_region(win);
    sync_maximized_frame(win);
}

/// Win10 左缘竖带的根治：把「为系统投影预留的隐形边框」关掉。
///
/// 病灶在 tao：无边框窗口默认带着「无装饰投影」标志（对应 `.shadow(true)`，
/// 也是默认值），`WM_NCCALCSIZE` 时把客户区四周内缩一圈边框厚度（这台机器上
/// 左右下各 8px），好让 `WS_THICKFRAME` 的隐形边框画出系统投影。Win11 上那圈
/// 边框真的只画投影，看不见；Win10 上它是实打实的非客户区——WebView 只铺客户区，
/// 这 8px 归窗口框架画。平时没人画它看不出问题，窗口一移动系统重画框架区，画出的
/// 旧像素从此钉在左缘，切页也盖不掉——就是那条「拖动后出现、再也不消失」的竖带。
///
/// `set_shadow(false)` 把那个标志清掉，`WM_NCCALCSIZE` 不再内缩，客户区涨满整个
/// 窗口，WebView 铺满，8px 从此有主人画。代价是没了系统投影——但走到这个分支的
/// Win10 机器上 `SetWindowRgn` 本来就把 DWM 合成打断了，投影早就没有，不损失任何
/// 看得见的东西；Win11（DWM 分支）绝不调用，投影照旧。拉着边改大小不受影响，
/// 命中测试由 tao 的 `WM_NCHITTEST` 自己算。
///
/// 为什么是「延后」而不是当场改：tao 收到标志变化后会同步
/// `SetWindowLong + SetWindowPos(SWP_FRAMECHANGED)` 重算框架，这一串会波及窗口里
/// 的子窗口（WebView2 的渲染窗口在另一个进程）。建窗现场 WebView2 还在初始化，
/// 此刻跟它做跨进程的同步等待，渲染器就此卡死——工具窗口永久白屏。所以不光要
/// 挪到后台线程，还要**等渲染器真的就绪**（`webview_renderer_ready`）再动框架：
/// 只靠固定延时赌不出初始化时长，赌输了就是同款白屏。
#[cfg(windows)]
fn kill_undecorated_shadow_inset_deferred(win: &WebviewWindow) {
    let win = win.clone();
    std::thread::spawn(move || {
        // 等 WebView2 把渲染器子窗口建出来再动框架。最多等 15 秒；等不到就放弃
        // 修复（竖带回来总比把窗口搞白屏强）。
        let mut ready = false;
        for _ in 0..300 {
            if webview_renderer_ready(&win) {
                ready = true;
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(50));
        }
        if !ready {
            logging::shell_log!("竖带修复：渲染器 15 秒内未就绪，放弃动框架");
            return;
        }
        // 渲染器出现后再宽限半秒，让它把首帧提交完。
        std::thread::sleep(std::time::Duration::from_millis(500));
        if let Err(e) = win.set_shadow(false) {
            logging::shell_log!("竖带修复：关投影标志失败（{e}）");
            return;
        }
        // set_shadow 把活派给 tao 的另一个线程，等它改完：标志生效后客户区会和
        // 窗口等大。最多等半秒，等不到也照常往下走。
        for _ in 0..25 {
            if let (Ok(i), Ok(o)) = (win.inner_size(), win.outer_size()) {
                if i.width >= o.width && i.height >= o.height {
                    break;
                }
            }
            std::thread::sleep(std::time::Duration::from_millis(20));
        }
        // 客户区涨满之后区域要按新尺寸重裁一次。set_shadow 引发的 WM_SIZE 可能
        // 比 Resized 回调挂上得还早（工具窗口），不能只指望回调，这里自己补一刀。
        // SetWindowRgn 得在窗口自己的线程上调，run_on_main_thread 会把它送过去。
        // 闭包要把 win 整个搬进去，方法调用还得借用它，先克隆一份给闭包用。
        let for_region = win.clone();
        let _ = win.run_on_main_thread(move || {
            apply_corner_region(&for_region);
        });
        logging::shell_log!("竖带修复：已关闭无装饰投影内缩，客户区铺满全窗");
    });
}

/// WebView2 是不是已经把渲染器子窗口（`Chrome_RenderWidgetHostHWND`）建出来了。
///
/// 这个子窗口属于另一个进程（msedgewebview2.exe 的渲染进程），它一出现就说明
/// 控制器创建完成、页面开始渲染——此刻再对宿主窗口动框架才不会跨进程卡住它。
/// 拿不到 HWND（窗口已关）时返回 false，调用方会一直等到超时放弃。
#[cfg(windows)]
fn webview_renderer_ready(win: &WebviewWindow) -> bool {
    use windows_sys::Win32::Foundation::{BOOL, HWND, LPARAM};
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        EnumChildWindows, GetClassNameW,
    };

    let Ok(hwnd) = win.hwnd() else {
        return false;
    };
    extern "system" fn find_renderer(child: HWND, found: LPARAM) -> BOOL {
        let mut name = [0u16; 64];
        // SAFETY：child 由枚举器给出，缓冲区长度如实传入。
        let len = unsafe { GetClassNameW(child, name.as_mut_ptr(), name.len() as i32) };
        const TARGET: &str = "Chrome_RenderWidgetHostHWND";
        let wide: Vec<u16> = TARGET.encode_utf16().collect();
        let mut buf = [0u16; TARGET.len()];
        buf[..wide.len()].copy_from_slice(&wide);
        if len as usize == wide.len() && name[..len as usize] == buf[..] {
            // 找到了：把标志置位并终止枚举（返回 false）。
            unsafe { *(found as *mut bool) = true };
            return 0;
        }
        1
    }
    let mut found = false;
    // SAFETY：回调只读写自己栈上的标志位；EnumChildWindows 同步走完才返回。
    unsafe {
        EnumChildWindows(
            hwnd.0 as HWND,
            Some(find_renderer),
            &mut found as *mut bool as LPARAM,
        );
    }
    found
}

/// Win10 的兜底：SetWindowRgn 把四角裁圆。
///
/// 缺点是硬边、没有抗锯齿，所以半径取小一点（8px）不至于难看。DWM 能用的时候
/// 绝不走这条 —— 那条是系统合成时画的，带抗锯齿也不影响投影。
#[cfg(windows)]
fn apply_corner_region(win: &WebviewWindow) {
    use windows_sys::Win32::Foundation::HWND;
    // SetWindowRgn 挂在 user32 上，但 windows-sys 把它归在 Graphics::Gdi 里
    // （跟 HRGN 放一起），不在 UI::WindowsAndMessaging。
    use windows_sys::Win32::Graphics::Gdi::{CreateRoundRectRgn, DeleteObject, SetWindowRgn};

    let (Ok(hwnd), Ok(size)) = (win.hwnd(), win.inner_size()) else {
        return;
    };
    // 最小化时尺寸是 0，套上去会得到一个空区域 —— 整个窗口都被裁没。
    if size.width == 0 || size.height == 0 {
        return;
    }
    // 最大化／全屏时窗口是要贴满屏幕的，四角切一刀会在角上露出桌面。这两种
    // 状态下把区域撤掉（传 null），窗口恢复成完整矩形。
    let filling = win.is_maximized().unwrap_or(false) || win.is_fullscreen().unwrap_or(false);
    if filling {
        // SAFETY: 传 null 表示清除区域，是这个 API 明确支持的用法。
        unsafe { SetWindowRgn(hwnd.0 as HWND, std::ptr::null_mut(), 1) };
        return;
    }
    let scale = win.scale_factor().unwrap_or(1.0);
    let r = (8.0 * scale).round() as i32 + 1;
    // SAFETY: 尺寸来自窗口自己，非零；区域交给 SetWindowRgn 之后由系统接管，
    // 成功时不能再 Delete，失败时必须自己删掉，下面按返回值分了。
    unsafe {
        let rgn = CreateRoundRectRgn(0, 0, size.width as i32 + 1, size.height as i32 + 1, r, r);
        if rgn.is_null() {
            return;
        }
        if SetWindowRgn(hwnd.0 as HWND, rgn, 1) == 0 {
            DeleteObject(rgn);
        }
    }
}

/// 窗口尺寸变了：最大化时拆掉系统边框/内缩，还原时重套圆角。
///
/// 以前只在 Win10 区域裁切分支里重裁；Win11 最大化时那层 Vista 描边不会走
/// 区域分支，必须每次 Resized 都看一眼最大化状态。
#[cfg(windows)]
pub fn refresh_corners(win: &WebviewWindow) {
    sync_maximized_frame(win);
    if NEEDS_REGION.load(Ordering::Relaxed) && !win.is_maximized().unwrap_or(false) {
        apply_corner_region(win);
    }
}

#[cfg(not(windows))]
pub fn refresh_corners(_win: &WebviewWindow) {}

// 这里曾经有个 `force_repaint`：Resized 的时候用
// `RedrawWindow(RDW_INVALIDATE | RDW_ALLCHILDREN | RDW_UPDATENOW)` 把窗口连同
// WebView2 的子窗口一起重画一遍，想治「边上留一条没人画的竖带」。
//
// 别再写回来。`RDW_UPDATENOW` 是**同步**重画：它对每个子窗口发 WM_PAINT 并
// 等对方处理完。WebView2 的渲染窗口不归我们这个线程管（另一个进程在泵它的
// 消息），于是这一等就是跨进程等——对方还在初始化、或者正好在等主线程时，
// 两边互相等，整个 UI 线程当场死锁。
//
// 表现是：一开工具窗口（建窗过程本身就会触发 Resized），新窗口停在白屏，
// 主窗口连版本号都读不出来，整个软件假死。而且它压根没治好那条竖带。
#[cfg(not(windows))]
pub fn round_corners(_win: &WebviewWindow) {}

pub fn place_on_active_monitor(win: &WebviewWindow) {
    let monitors = win.available_monitors().unwrap_or_default();
    if monitors.len() < 2 {
        return; // 单屏没有「开错屏」这回事
    }
    let (Some(r), Some(target)) = (win_rect(win), active_monitor(win, &monitors)) else {
        return;
    };
    let t = full(&target);
    // 窗口中心已经在目标屏上就别动，免得把 center() 算好的位置又推一遍。
    if t.contains(r.x + r.w / 2, r.y + r.h / 2) {
        return;
    }
    let to = work(&target).center_for(r.w, r.h);
    logging::shell_log!(
        "窗口开在了非当前显示器上（{},{}），挪到光标所在屏 {},{}",
        r.x,
        r.y,
        to.x,
        to.y
    );
    let _ = win.set_position(to);
}

/// 用户此刻在用的显示器：光标所在那块，取不到就退回主屏，再不行取第一块。
fn active_monitor(win: &WebviewWindow, monitors: &[Monitor]) -> Option<Monitor> {
    if let Ok(c) = win.cursor_position() {
        if let Ok(Some(m)) = win.monitor_from_point(c.x, c.y) {
            return Some(m);
        }
        // monitor_from_point 在某些驱动上会返回 None，自己按坐标找一遍。
        if let Some(m) = monitors
            .iter()
            .find(|m| full(m).contains(c.x as i32, c.y as i32))
        {
            return Some(m.clone());
        }
    }
    win.primary_monitor()
        .ok()
        .flatten()
        .or_else(|| monitors.first().cloned())
}

fn opt<T: std::fmt::Debug, E>(r: &Result<T, E>) -> String {
    match r {
        Ok(v) => format!("{v:?}"),
        Err(_) => "?".into(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // 实测布局：主屏 DISPLAY1 在 0,0，副屏 DISPLAY5 在 -1920,7。
    const MAIN: Rect = Rect { x: 0, y: 0, w: 1920, h: 1080 };
    const MAIN_WORK: Rect = Rect { x: 0, y: 0, w: 1920, h: 1040 };
    const LEFT: Rect = Rect { x: -1920, y: 7, w: 1920, h: 1080 };

    #[test]
    fn center_matches_what_tauri_computed() {
        // 日志里的 370,130 就是这么来的：算的是工作区，不是整块屏。
        assert_eq!(MAIN_WORK.center_for(1196, 788), PhysicalPosition::new(362, 126));
        assert_eq!(MAIN_WORK.center_for(1180, 780), PhysicalPosition::new(370, 130));
    }

    #[test]
    fn a_window_on_the_secondary_monitor_is_not_offscreen() {
        // 负坐标本身不是「跑到屏幕外」——副屏就挂在主屏左边。
        let w = Rect { x: -1800, y: 100, w: 1180, h: 780 };
        assert!(w.intersects(&LEFT));
        assert!(!w.intersects(&MAIN));
    }

    #[test]
    fn a_window_hanging_off_the_edge_is_left_alone() {
        let w = Rect { x: 1700, y: 900, w: 1180, h: 780 };
        assert!(w.intersects(&MAIN));
    }

    #[test]
    fn a_window_past_every_monitor_is_rescued() {
        let w = Rect { x: 4000, y: 0, w: 1180, h: 780 };
        assert!(!w.intersects(&MAIN) && !w.intersects(&LEFT));
    }

    #[test]
    fn the_cursor_picks_the_monitor_it_is_on() {
        assert!(LEFT.contains(-900, 500));
        assert!(!MAIN.contains(-900, 500));
        assert!(MAIN.contains(960, 540));
    }

    #[test]
    fn a_window_wider_than_the_screen_still_starts_on_screen() {
        // 别给出负坐标：无边框窗口顶出屏幕就再也拖不回来。
        let p = MAIN_WORK.center_for(3000, 2000);
        assert_eq!(p, PhysicalPosition::new(0, 0));
    }

    #[test]
    fn the_window_center_decides_which_monitor_it_is_on() {
        // 跨屏摆放时按中心归属，不然两块屏都「相交」，判不出该不该挪。
        // x=-500 宽 1180 → 中心 90，落在主屏那一侧。
        let w = Rect { x: -500, y: 100, w: 1180, h: 780 };
        assert!(w.intersects(&MAIN) && w.intersects(&LEFT));
        assert!(MAIN.contains(w.x + w.w / 2, w.y + w.h / 2));
        assert!(!LEFT.contains(w.x + w.w / 2, w.y + w.h / 2));
    }
}
