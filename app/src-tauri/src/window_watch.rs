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

/// 即将套上的外框是不是已经超出工作区 / 铺满整块显示器。
///
/// 最大化时系统常按「整块显示器」给尺寸（无标题栏窗口尤其如此），那会盖住
/// 任务栏。只有这种「过大」的提案才该钳回工作区；还原到最大化前的小矩形
/// 绝不能钳，否则窗口会卡在工作区大小，拖边也缩不回去。
fn size_overflows_work(cx: i32, cy: i32, work_w: i32, work_h: i32, mon_w: i32, mon_h: i32) -> bool {
    if cx <= 0 || cy <= 0 || work_w <= 0 || work_h <= 0 {
        return false;
    }
    (cx + 2 >= mon_w && cy + 2 >= mon_h) || cx > work_w + 2 || cy > work_h + 2
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
/// 记录窗口状态，然后把看不见的窗口救回来。开机建窗后调一次。
pub fn report_and_rescue(win: &WebviewWindow, phase: &str) {
    report(win, phase);
    rescue(win);
}

/// 把窗口和显示器的状态写进日志。**不动窗口。**
pub fn report(win: &WebviewWindow, phase: &str) {
    let visible = win.is_visible();
    let minimized = win.is_minimized();
    let rect = win_rect(win);

    logging::shell_log!("窗口状态（{phase}）：可见={} 最小化={} 位置={} 尺寸={} 缩放={}",
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
        logging::shell_log!(crate::i18n::t("s.27ecfba771"));
    }
    let primary = win.primary_monitor().ok().flatten();
    let unnamed = crate::i18n::t("s.dca24a94ac");
    let primary_mark = crate::i18n::t("s.1029edff5a");
    for m in &monitors {
        let f = full(m);
        let w = work(m);
        let name = m.name().map(String::as_str).unwrap_or(unnamed.as_str());
        let mark = if primary.as_ref().and_then(|p| p.name()) == m.name() {
            primary_mark.as_str()
        } else {
            ""
        };
        logging::shell_log!("显示器 {}{}：位置 {},{} 尺寸 {}x{} 工作区 {},{} {}x{} 缩放 {:.2}",
            name,
            mark,
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

}

/// 把最小化/隐藏/跑到屏幕外的窗口弄回用户眼前。
///
/// **这是补救，不是例行维护**：它会 show 一扇用户可能是故意藏起来的窗口。
/// 只在有理由相信「窗口不见了不是用户的意思」时调用（开机建窗后、界面迟迟
/// 没挂起来），别放进定时体检里。
pub fn rescue(win: &WebviewWindow) {
    if win.is_minimized().unwrap_or(false) {
        let _ = win.unminimize();
    }
    if !win.is_visible().unwrap_or(true) {
        logging::shell_log!(crate::i18n::t("s.4401758653"));
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

/// 去掉 DWM 1px 系统描边色（始终关）。
///
/// 只动边框色，**绝不**关 `DWMWA_NCRENDERING_POLICY`：关掉 NC 绘制会把
/// 任务栏也带成黑条（本机实测）。
/// **绝不** `set_shadow(true)`：无边框 + shadow=true = 1px Aero 白边。
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

/// 无边框窗口要能拖边缩放，必须一直留着 `WS_THICKFRAME`。
///
/// 以前最大化时摘掉厚框想藏 Aero 描边：摘掉之后拖边失效；事后 `SetWindowPos`
/// 再钳工作区会把 `rcNormalPosition` 写成工作区本身，还原/拖边都缩不回
/// 最大化前的尺寸。描边改由 `WM_NCCALCSIZE`（客户区铺满、无非客户区内缩）
/// + `DWMWA_BORDER_COLOR=NONE` 处理。厚框只当隐形命中区，**永远不要再按
/// 最大化状态开关**。
#[cfg(windows)]
fn ensure_thickframe(hwnd: windows_sys::Win32::Foundation::HWND) {
    ensure_frame_styles(hwnd, false)
}

/// 窗口投影的来源是 `WS_CAPTION`，不是 tao 的 `set_shadow(true)`。
///
/// 这是之前搞反的一处。tao 的 `set_shadow(true)` 对无边框窗口做的是
/// `DwmExtendFrameIntoClientArea` 留 1px 边距 —— 那 1px 由 DWM 自己画，
/// 看上去就是那条「Aero 白边」。当时的结论「无边框就不能有投影」是从这个
/// 实现推出来的，对 tao 成立，对 Windows 不成立。
///
/// 系统给窗口画投影看的是样式里有没有 `WS_CAPTION`。加上它，DWM 就照常画
/// 投影、照常做最小化/还原动画；标题栏本身不会露出来，因为
/// `work_area_subclass_proc` 里的 `WM_NCCALCSIZE` 一律把客户区撑满整个窗口。
/// VS Code、Windows Terminal 走的都是这条路。
///
/// `set_shadow(false)` 那几处一个都不用动 —— 投影不再靠它，它继续负责挡住
/// tao 那 1px。
#[cfg(windows)]
fn ensure_caption_for_shadow(hwnd: windows_sys::Win32::Foundation::HWND) {
    ensure_frame_styles(hwnd, true)
}

#[cfg(windows)]
fn ensure_frame_styles(hwnd: windows_sys::Win32::Foundation::HWND, caption: bool) {
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetWindowLongW, SetWindowLongW, SetWindowPos, GWL_STYLE, SWP_FRAMECHANGED,
        SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER,
    };
    const WS_THICKFRAME: u32 = 0x0004_0000;
    const WS_BORDER: u32 = 0x0080_0000;
    const WS_CAPTION: u32 = 0x00C0_0000;
    // SAFETY: hwnd 是我们自己的窗口。
    unsafe {
        let style = GetWindowLongW(hwnd, GWL_STYLE) as u32;
        let mut new_style = (style | WS_THICKFRAME) & !WS_BORDER;
        if caption {
            new_style |= WS_CAPTION;
        }
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

/// 每个窗口自己的最大化状态（主窗 / 工具窗不能共用一个 AtomicBool）。
/// 只给日志和 Win10 圆角区域用，不再据此改窗口样式或尺寸。
#[cfg(windows)]
static MAX_BY_LABEL: std::sync::LazyLock<
    std::sync::Mutex<std::collections::HashMap<String, bool>>,
> = std::sync::LazyLock::new(|| std::sync::Mutex::new(std::collections::HashMap::new()));

#[cfg(windows)]
fn max_was(label: &str) -> bool {
    MAX_BY_LABEL
        .lock()
        .ok()
        .and_then(|g| g.get(label).copied())
        .unwrap_or(false)
}

#[cfg(windows)]
fn set_max_was(label: &str, v: bool) {
    if let Ok(mut g) = MAX_BY_LABEL.lock() {
        g.insert(label.to_string(), v);
    }
}

/// 最大化时只处理圆角区域；尺寸由子类化在落地前钳好。
///
/// **永远不要** `set_shadow(true)`（无边框 + shadow=true = 1px 白边）。
/// **永远不要** 关 `DWMWA_NCRENDERING_POLICY`（会搞黑任务栏）。
/// **永远不要** 最大化后再 `SetWindowPos` / `SetWindowPlacement` 去钳工作区：
/// 那会毁掉 `rcNormalPosition`，还原缩不回最大化前的大小。
#[cfg(windows)]
fn sync_maximized_frame(win: &WebviewWindow) {
    let label = win.label().to_string();
    let maximized =
        win.is_maximized().unwrap_or(false) || win.is_fullscreen().unwrap_or(false);
    let was = max_was(&label);

    let Ok(hwnd_raw) = win.hwnd() else {
        return;
    };
    let hwnd = hwnd_raw.0 as windows_sys::Win32::Foundation::HWND;

    let _ = win.set_shadow(false);
    hide_dwm_border_color(hwnd);
    ensure_thickframe(hwnd);

    if maximized {
        // 区域裁切在最大化时必须撤掉，否则四角露桌面。
        if NEEDS_REGION.load(Ordering::Relaxed) {
            use windows_sys::Win32::Graphics::Gdi::SetWindowRgn;
            unsafe {
                SetWindowRgn(hwnd, std::ptr::null_mut(), 1);
            }
        }
        if !was {
            set_max_was(&label, true);
            logging::shell_log!(
                "最大化：尺寸由 WM_GETMINMAXINFO / WM_WINDOWPOSCHANGING 钳到工作区（不改样式、不碰还原矩形）"
            );
        }
    } else {
        if was {
            set_max_was(&label, false);
            logging::shell_log!(
                "还原：WS_THICKFRAME 未动，系统按 rcNormalPosition 回到最大化前尺寸"
            );
        }
        if NEEDS_REGION.load(Ordering::Relaxed) {
            apply_corner_region(win);
        }
    }
}

/// 子类化：最大化在落地前就用工作区，而不是事后改尺寸。
///
/// 无边框窗的 `WM_GETMINMAXINFO` 常常被系统忽略，仍按整块显示器铺。
/// 真正改提案尺寸要在 `WM_WINDOWPOSCHANGING`：这时系统还没把新尺寸写进
/// `rcNormalPosition`，还原矩形仍是最大化前的窗口。
#[cfg(windows)]
fn install_work_area_minmax(hwnd: windows_sys::Win32::Foundation::HWND) {
    use windows_sys::Win32::UI::Shell::SetWindowSubclass;

    // SAFETY: 本窗 HWND；子类过程只改最大化相关消息，其余交给 DefSubclassProc。
    unsafe {
        let _ = SetWindowSubclass(hwnd, Some(work_area_subclass_proc), 0x5246_4357, 0);
    }
}

#[cfg(windows)]
fn monitor_work_and_full(
    hwnd: windows_sys::Win32::Foundation::HWND,
) -> Option<(
    windows_sys::Win32::Foundation::RECT,
    windows_sys::Win32::Foundation::RECT,
)> {
    use windows_sys::Win32::Graphics::Gdi::{
        GetMonitorInfoW, MonitorFromWindow, MONITORINFO, MONITOR_DEFAULTTONEAREST,
    };
    // SAFETY: hwnd 是本窗；MONITORINFO.cbSize 必须先填对。
    unsafe {
        let monitor = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST);
        let mut mi: MONITORINFO = std::mem::zeroed();
        mi.cbSize = std::mem::size_of::<MONITORINFO>() as u32;
        if GetMonitorInfoW(monitor, &mut mi) == 0 {
            return None;
        }
        Some((mi.rcWork, mi.rcMonitor))
    }
}

#[cfg(windows)]
unsafe extern "system" fn work_area_subclass_proc(
    hwnd: windows_sys::Win32::Foundation::HWND,
    msg: u32,
    wparam: windows_sys::Win32::Foundation::WPARAM,
    lparam: windows_sys::Win32::Foundation::LPARAM,
    _id: usize,
    _data: usize,
) -> windows_sys::Win32::Foundation::LRESULT {
    use windows_sys::Win32::Foundation::RECT;
    use windows_sys::Win32::UI::Shell::DefSubclassProc;
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetWindowRect, MINMAXINFO, WINDOWPOS, SWP_NOMOVE, SWP_NOSIZE,
    };

    const WM_GETMINMAXINFO: u32 = 0x0024;
    const WM_WINDOWPOSCHANGING: u32 = 0x0046;
    const WM_NCCALCSIZE: u32 = 0x0083;

    if msg == WM_GETMINMAXINFO && lparam != 0 {
        // 先拿默认值，再覆盖最大化矩形。
        let ret = DefSubclassProc(hwnd, msg, wparam, lparam);
        let mmi = lparam as *mut MINMAXINFO;
        if let Some((work, mon)) = monitor_work_and_full(hwnd) {
            (*mmi).ptMaxPosition.x = work.left - mon.left;
            (*mmi).ptMaxPosition.y = work.top - mon.top;
            (*mmi).ptMaxSize.x = work.right - work.left;
            (*mmi).ptMaxSize.y = work.bottom - work.top;
            (*mmi).ptMaxTrackSize.x = (*mmi).ptMaxSize.x;
            (*mmi).ptMaxTrackSize.y = (*mmi).ptMaxSize.y;
        }
        return ret;
    }

    if msg == WM_WINDOWPOSCHANGING && lparam != 0 {
        // 先让 tao / 系统改完，我们最后覆盖，避免被默认处理写回全屏尺寸。
        let ret = DefSubclassProc(hwnd, msg, wparam, lparam);
        let wp = lparam as *mut WINDOWPOS;
        let flags = (*wp).flags;
        if flags & (SWP_NOSIZE | SWP_NOMOVE) == (SWP_NOSIZE | SWP_NOMOVE) {
            return ret;
        }
        let Some((work, mon)) = monitor_work_and_full(hwnd) else {
            return ret;
        };
        let mut cur = RECT {
            left: 0,
            top: 0,
            right: 0,
            bottom: 0,
        };
        if flags & (SWP_NOSIZE | SWP_NOMOVE) != 0 {
            let _ = GetWindowRect(hwnd, &mut cur);
        }
        let cx = if flags & SWP_NOSIZE != 0 {
            cur.right - cur.left
        } else {
            (*wp).cx
        };
        let cy = if flags & SWP_NOSIZE != 0 {
            cur.bottom - cur.top
        } else {
            (*wp).cy
        };
        let work_w = work.right - work.left;
        let work_h = work.bottom - work.top;
        let mon_w = mon.right - mon.left;
        let mon_h = mon.bottom - mon.top;
        // 只拦「过大」的提案。还原到最大化前的小矩形必须原样通过，
        // 否则窗口会卡在工作区大小，拖边也缩不回去。
        if !size_overflows_work(cx, cy, work_w, work_h, mon_w, mon_h) {
            return ret;
        }
        if flags & SWP_NOMOVE == 0 {
            (*wp).x = work.left;
            (*wp).y = work.top;
        }
        if flags & SWP_NOSIZE == 0 {
            (*wp).cx = work_w;
            (*wp).cy = work_h;
        }
        return ret;
    }

    if msg == WM_NCCALCSIZE && wparam != 0 {
        // 客户区 = 整个窗口矩形，一律如此，不分最大化。
        //
        // 这一行是整套无边框窗口的地基，之前只在最大化时生效，剩下的情况
        // 交给 DefSubclassProc → tao，而 tao 会按「有边框」把客户区四周内缩
        // 一圈（Win10 上左右下各 8px）。那圈非客户区 WebView 不铺、没人画，
        // 窗口一移动系统重画框架就把旧像素钉在左缘 —— 「拖动后出现、再也不
        // 消失的竖带」。以前是另起一个线程、等 WebView2 渲染器就绪、再翻
        // set_shadow 标志去反推同一个结果；直接在这里拦下就没那回事了。
        //
        // 不调 DefSubclassProc 是有意的：只要它跑了，tao 就会内缩。
        return 0;
    }

    DefSubclassProc(hwnd, msg, wparam, lparam)
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
        logging::shell_log!(crate::i18n::t("s.75af179e2d"));
        return;
    };
    let hwnd = hwnd.0 as HWND;
    // 先关系统描边色，避免一启动就有 1px Aero 框。
    hide_dwm_border_color(hwnd);
    // 厚框只当拖边命中区，最大化时也不摘。
    ensure_thickframe(hwnd);
    // 最大化矩形在落地前钳到工作区（无边框默认会盖任务栏）。
    install_work_area_minmax(hwnd);
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
        // DWM 认这条属性 = Win11。系统会画圆角，也会画投影 —— 只要样式里
        // 有 WS_CAPTION。窗口层次感就是从这儿来的，见 ensure_caption_for_shadow。
        ensure_caption_for_shadow(hwnd);
        logging::shell_log!(crate::i18n::t("s.3db536a84d"));
        // 建窗时若已是最大化（少见），立刻铺满，别等第一次 Resized。
        sync_maximized_frame(win);
        return;
    }
    // 记下走的是兜底那条，之后 Resized 才知道该不该重新裁。DWM 生效的机器上
    // 再去裁一刀，等于拿硬边盖掉系统画好的抗锯齿圆角。
    //
    // 这条分支上 SetWindowRgn 会打断 DWM 合成，投影本来就没有，所以不加
    // WS_CAPTION —— 加了也画不出来，只多一次样式变更。
    NEEDS_REGION.store(true, Ordering::Relaxed);
    // Win10 没有这个属性，DWM 这条路走不通。系统不给画就自己画：给窗口套一个
    // 圆角区域，把四角裁掉。区域是按像素算的，窗口一变大小就得重新套，所以
    // 调用方在 Resized 时会再调一次。
    logging::shell_log!(crate::i18n::t("s.2d0c1739e0"));
    apply_corner_region(win);
    sync_maximized_frame(win);
}

// 这里曾经有两个函数：`kill_undecorated_shadow_inset_deferred` 和它依赖的
// `webview_renderer_ready`。前者另起一个线程、轮询等 WebView2 的渲染器子窗口
// 出现、再翻 tao 的 shadow 标志、再等客户区涨满、再回主线程重裁一次圆角区域，
// 只为了达成一件事：客户区铺满整个窗口，别留一圈没人画的非客户区（Win10 上
// 那圈会变成「拖动后出现、再也不消失的左缘竖带」）。
//
// 现在 `work_area_subclass_proc` 的 `WM_NCCALCSIZE` 一律返回 0，客户区从建窗
// 第一帧起就是整个窗口矩形，上面那一串全是多余的。别再写回来 —— 它引入过
// 「工具窗口永久白屏」（建窗现场跟 WebView2 跨进程同步等待），代价比它治的
// 病还大。

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

/// 窗口尺寸变了：最大化时撤掉 Win10 圆角区域，还原时重套。
///
/// 尺寸钳制已经在子类化里做完。这里只跟圆角区域和 DWM 描边色，
/// 不再改窗口样式或事后 SetWindowPos。
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

/// 启动时把窗口摆到用户正在用的那块屏上。
///
/// 只在建完窗口后调用一次。之后不再动——用户自己把窗口拖到哪块屏是他的事，
/// 隔一会儿被程序挪回来比开错屏还烦。
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
    logging::shell_log!("窗口开在了非当前显示器上（{},{}），挪到光标所在屏 {},{}",
        r.x,
        r.y,
        to.x,
        to.y
    );
    let _ = win.set_position(to);
}

/// 把 `win` 摆到 `anchor` 所在的那块显示器上，居中。
///
/// 工具窗口（人声分离/训练音色/语音合成）建窗时用的是 `.center()`，而 Tauri 的
/// center 算的是**主显示器**。用户把主窗口拖到副屏上用，点一下「训练音色」，
/// 窗口开在了另一块屏 —— 甚至在他视野之外。
///
/// 只按 anchor 的位置算，不看光标：用户点完按钮手可能已经挪开了，而窗口在哪
/// 是确定的。
pub fn place_next_to(win: &WebviewWindow, anchor: &WebviewWindow) {
    let monitors = win.available_monitors().unwrap_or_default();
    if monitors.len() < 2 {
        return; // 单屏没有「开错屏」这回事
    }
    let (Some(r), Some(a)) = (win_rect(win), win_rect(anchor)) else {
        return;
    };
    let center = (a.x + a.w / 2, a.y + a.h / 2);
    let target = win
        .monitor_from_point(center.0 as f64, center.1 as f64)
        .ok()
        .flatten()
        // monitor_from_point 在某些驱动上返回 None，自己按坐标找一遍。
        .or_else(|| {
            monitors
                .iter()
                .find(|m| full(m).contains(center.0, center.1))
                .cloned()
        });
    let Some(target) = target else {
        return;
    };
    // 已经在同一块屏上就别动，免得把 center() 算好的位置又推一遍。
    if full(&target).contains(r.x + r.w / 2, r.y + r.h / 2) {
        return;
    }
    let to = work(&target).center_for(r.w, r.h);
    logging::shell_log!(
        "工具窗口开在了主窗口以外的屏（{},{}），挪到主窗口那块屏 {},{}",
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

    #[test]
    fn a_normal_restore_size_is_not_clamped() {
        // 最大化前 1180×780：还原提案必须原样通过，否则窗口卡在工作区。
        assert!(!size_overflows_work(1180, 780, 1920, 1040, 1920, 1080));
        assert!(!size_overflows_work(1920, 1040, 1920, 1040, 1920, 1080));
    }

    #[test]
    fn a_fullscreen_maximize_is_clamped_to_the_work_area() {
        // 无边框窗系统常按整块显示器给最大化尺寸，会盖住任务栏。
        assert!(size_overflows_work(1920, 1080, 1920, 1040, 1920, 1080));
        // 厚框最大化时外框会比工作区探出一圈。
        assert!(size_overflows_work(1920, 1048, 1920, 1040, 1920, 1080));
    }
}
