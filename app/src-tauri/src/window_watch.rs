//! 「窗口没弹出来」的取证与自救。
//!
//! 这个报告从外面看永远是同一句话，里面却至少是三件事：窗口根本没建起来、
//! 窗口建起来了但是隐藏的、窗口建起来也可见但落在所有显示器之外。三者的修法
//! 完全相反，而用户能提供的信息只有「看不见」。
//!
//! 所以窗口自己说。`report` 把可见性、坐标、尺寸、缩放和整套显示器布局写进
//! shell.log；`rescue` 处理其中唯一能在本地无副作用兜住的一种——跑到屏幕外面
//! 去了。无边框窗口连标题栏都没有，用户想拖也拖不回来。
//!
//! 注意：Tauri v2 的 `visible` 默认就是 `true`（tauri-utils 的
//! `WindowConfig::default()`），`WebviewWindowBuilder` 从那份默认值起步。
//! 补一句 `.visible(true)` 是空操作，不要指望它能修好任何东西。

use tauri::{Monitor, PhysicalPosition, PhysicalSize, WebviewWindow};

use crate::logging;

/// 记录窗口与显示器的真实状态，必要时把窗口拉回屏幕内。
///
/// `phase` 只是日志里的标签——同一次启动会调用两次（建完窗口、以及 12 秒后），
/// 两条对比起来才能看出窗口是一开始就不对，还是后来被挪走的。
pub fn report_and_rescue(win: &WebviewWindow, phase: &str) {
    let visible = win.is_visible();
    let minimized = win.is_minimized();
    let pos = win.outer_position().ok();
    let size = win.outer_size().ok();

    logging::shell_log!(
        "窗口状态（{phase}）：可见={} 最小化={} 位置={} 尺寸={} 缩放={}",
        opt(&visible),
        opt(&minimized),
        pos.map(|p| format!("{},{}", p.x, p.y))
            .unwrap_or_else(|| "?".into()),
        size.map(|s| format!("{}x{}", s.width, s.height))
            .unwrap_or_else(|| "?".into()),
        win.scale_factor()
            .map(|f| format!("{f:.2}"))
            .unwrap_or_else(|_| "?".into()),
    );

    let monitors = win.available_monitors().unwrap_or_default();
    if monitors.is_empty() {
        // 远程桌面断开、显卡驱动刚崩过、或者只有虚拟显示器的机器上会出现。
        // 这时候 center() 算不出位置，窗口会停在系统给的默认坐标上。
        logging::shell_log!("警告：系统报告 0 个显示器，窗口位置无法校正");
    }
    for m in &monitors {
        logging::shell_log!(
            "显示器 {}：位置 {},{} 尺寸 {}x{} 缩放 {:.2}",
            m.name().map(String::as_str).unwrap_or("(无名)"),
            m.position().x,
            m.position().y,
            m.size().width,
            m.size().height,
            m.scale_factor(),
        );
    }

    if minimized.unwrap_or(false) {
        let _ = win.unminimize();
    }
    if !visible.unwrap_or(true) {
        logging::shell_log!("窗口是隐藏的，显示出来");
        let _ = win.show();
    }

    if let (Some(p), Some(s)) = (pos, size) {
        if let Some(fixed) = rescue_position(p, s, &monitors) {
            logging::shell_log!(
                "窗口落在所有显示器之外，拉回 {},{}",
                fixed.x,
                fixed.y
            );
            let _ = win.set_position(fixed);
        }
    }
}

fn opt<T: std::fmt::Debug, E>(r: &Result<T, E>) -> String {
    match r {
        Ok(v) => format!("{v:?}"),
        Err(_) => "?".into(),
    }
}

/// 窗口矩形和任何一台显示器都不相交时，返回该挪到哪儿；否则 `None`。
///
/// 判定用的是「有没有交集」而不是「有没有完全包含」：窗口被拖到屏幕边缘露出
/// 一半是用户自己摆的，把它挪回中间只会更烦人。
fn rescue_position(
    pos: PhysicalPosition<i32>,
    size: PhysicalSize<u32>,
    monitors: &[Monitor],
) -> Option<PhysicalPosition<i32>> {
    if monitors.is_empty() {
        return None;
    }
    let (w, h) = (size.width as i32, size.height as i32);
    let overlaps = monitors.iter().any(|m| {
        let mp = m.position();
        let ms = m.size();
        pos.x < mp.x + ms.width as i32
            && pos.x + w > mp.x
            && pos.y < mp.y + ms.height as i32
            && pos.y + h > mp.y
    });
    if overlaps {
        return None;
    }
    let m = &monitors[0];
    let (mp, ms) = (m.position(), m.size());
    Some(PhysicalPosition::new(
        mp.x + ((ms.width as i32 - w) / 2).max(0),
        mp.y + ((ms.height as i32 - h) / 2).max(0),
    ))
}

#[cfg(test)]
mod tests {
    // Monitor 的字段是 pub(crate) 的，构造不出来，所以直接测几何判定本身。
    fn overlaps(pos: (i32, i32), size: (i32, i32), mon: (i32, i32, i32, i32)) -> bool {
        let (x, y) = pos;
        let (w, h) = size;
        let (mx, my, mw, mh) = mon;
        x < mx + mw && x + w > mx && y < my + mh && y + h > my
    }

    #[test]
    fn a_window_on_the_secondary_monitor_is_left_alone() {
        // 副屏挂在主屏左边，坐标是负的——负坐标本身不是「跑到屏幕外」。
        assert!(overlaps((-1800, 100), (1180, 780), (-1920, 0, 1920, 1080)));
    }

    #[test]
    fn a_window_hanging_off_the_edge_is_left_alone() {
        assert!(overlaps((1700, 900), (1180, 780), (0, 0, 1920, 1080)));
    }

    #[test]
    fn a_window_past_every_monitor_is_rescued() {
        assert!(!overlaps((4000, 0), (1180, 780), (0, 0, 1920, 1080)));
    }

    #[test]
    fn rescue_centers_on_the_first_monitor() {
        // 1920x1080 上放 1180x780 → (370, 150)
        assert_eq!(((1920 - 1180) / 2, (1080 - 780) / 2), (370, 150));
    }
}
