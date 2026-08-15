//! 独立工具窗口：人声分离、训练音色、语音转换（STS + TTS）。
//!
//! 这三件事以前都是主窗口上的模态弹窗。模态的问题不在于难看，在于它把主窗口
//! 整个锁住了：分离一首歌几分钟、训一个音色几小时，这段时间里用户连换个音色、
//! 调个音高都做不到，只能干等着。而这三件事和变声本身没有任何共享状态 ——
//! 它们各起各的 python 进程，各写各的文件。
//!
//! 所以给它们各自一个真窗口：能挪、能拉大、能最小化、能关掉，主窗口该干嘛
//! 干嘛。窗口内容还是同一份前端，靠 URL 后面的 `#/tool/<kind>` 分流。
//!
//! 同一个工具只开一扇窗：再点一次是把已经开着的那扇拉到前面，不是叠第二扇。

use serde_json::json;
use tauri::{AppHandle, Emitter, Manager, WebviewUrl, WebviewWindowBuilder};

use crate::logging;

/// 一个工具窗口的全部参数：标题、初始大小、最小大小。
struct Spec {
    title: String,
    w: f64,
    h: f64,
    min_w: f64,
    min_h: f64,
}

/// 最小尺寸不是随便填的：比这再窄，里面那几行「标签 + 路径 + 按钮」就要换行，
/// 路径被挤成两个字。宽度按内容排出来的最窄可用宽给。
fn spec_for(kind: &str) -> Option<Spec> {
    Some(match kind {
        "separate" => Spec {
            title: crate::i18n::t("s.8fd038283b"),
            w: 660.0,
            h: 540.0,
            min_w: 520.0,
            min_h: 420.0,
        },
        "train" => Spec {
            title: crate::i18n::t("s.ba65bd5595"),
            w: 720.0,
            h: 640.0,
            min_w: 560.0,
            min_h: 480.0,
        },
        "tts" => Spec {
            // 标签仍用 tts 兼容旧入口；窗体标题是「语音转换」（含音频变声 + 文字合成）。
            title: crate::i18n::t("s.6f311c47fe"),
            w: 720.0,
            h: 780.0,
            min_w: 560.0,
            min_h: 560.0,
        },
        _ => return None,
    })
}

pub fn label_for(kind: &str) -> String {
    format!("tool-{kind}")
}

/// 主窗口用的那个地址，后面挂上分流用的 fragment。
///
/// WebView2 注册不了非标准 scheme，wry 把 `fabric://localhost/x` 改写成
/// `http://fabric.localhost/x` 再拦截，所以 Windows 这条要照着写，
/// 否则 webview 报出来的 origin 和我们注册的对不上。
fn url_for(kind: &str) -> String {
    #[cfg(windows)]
    {
        format!(
            "http://{}.localhost/index.html#/tool/{kind}",
            crate::ui_assets::SCHEME
        )
    }
    #[cfg(not(windows))]
    {
        format!(
            "{}://localhost/index.html#/tool/{kind}",
            crate::ui_assets::SCHEME
        )
    }
}

/// 从工具窗口把主窗口叫到前面，并让它跳到「广场 → 下载模型」。
///
/// 工具窗口以前是就地弹一个下载框。那个框在 720px 高的工具窗里放不下：外层
/// 有 max-h 却没有滚动容器，flex 子项默认又不肯缩到内容以下，于是列表把底部
/// 的关闭按钮顶出可视区，页面还滚不动 —— 用户想关窗口，点到的是下载按钮。
///
/// 与其把那个框塞进小窗口，不如根本不塞：下载模型本来就住在主窗口的广场里，
/// 那儿有完整的高度和滚动，也是主窗口唯一的入口。工具窗口只负责把人带过去。
pub fn focus_main_downloads(app: &AppHandle, reason: &str, filter: &str) -> Result<(), String> {
    let main = app
        .get_webview_window("main")
        .ok_or_else(|| crate::i18n::t("s.toolMainWindowGone"))?;
    let _ = main.unminimize();
    let _ = main.show();
    let _ = main.set_focus();
    main.emit(
        "open-download-models",
        json!({ "reason": reason, "filter": filter }),
    )
    .map_err(|e| e.to_string())?;
    Ok(())
}

/// 工具窗口点「查看说明」：把主窗口叫到前面并跳到说明页对应段。
pub fn focus_main_help(app: &AppHandle, section: &str) -> Result<(), String> {
    let main = app
        .get_webview_window("main")
        .ok_or_else(|| crate::i18n::t("s.toolMainWindowGone"))?;
    let _ = main.unminimize();
    let _ = main.show();
    let _ = main.set_focus();
    main.emit("open-help", json!({ "section": section }))
        .map_err(|e| e.to_string())?;
    Ok(())
}

pub fn open(app: &AppHandle, kind: &str) -> Result<(), String> {
    let sp = spec_for(kind).ok_or_else(|| crate::i18n::te("s.22a95f37e3", &(kind)))?;
    let label = label_for(kind);

    // 已经开着就拉到前面。unminimize 要在 show 之前 —— 一个最小化的窗口
    // 光 show 是不会回到屏幕上的，用户看到的就是「点了没反应」。
    if let Some(win) = app.get_webview_window(&label) {
        let _ = win.unminimize();
        let _ = win.show();
        let _ = win.set_focus();
        return Ok(());
    }

    let url = url_for(kind);
    let win = WebviewWindowBuilder::new(
        app,
        &label,
        WebviewUrl::CustomProtocol(url.parse().map_err(|e| crate::i18n::te("s.c1c11dd8f6", &(e)))?),
    )
    .title(sp.title)
    .inner_size(sp.w, sp.h)
    .min_inner_size(sp.min_w, sp.min_h)
    .resizable(true)
    // 和主窗口一样无边框 + 自己画标题栏。这里用系统标题栏的话，同一个软件里
    // 会同时出现两种窗口长相。
    .decorations(false)
    // 与主窗一致：无边框不带系统 1px 白边。
    .shadow(false)
    .center()
    .build()
    .map_err(|e| crate::i18n::te("s.79a71841b6", &(e)))?;
    logging::shell_log!(crate::i18n::te("s.e1e2bc3a99", &kind));

    // `.center()` 居的是**主显示器**的中。用户把主窗口拖到副屏上用的时候，
    // 工具窗口会开到另一块屏上去 —— 点了按钮，什么都没看见。
    if let Some(main) = app.get_webview_window("main") {
        crate::window_watch::place_next_to(&win, &main);
    }

    crate::window_watch::round_corners(&win);
    // 和主窗口一样：改完大小要重新裁圆角（Win10 兜底那条路）。
    // 这个回调跑在 UI 线程上，里面只能做「标记 + 返回」这类立刻结束的事——
    // 任何会等别的线程/进程的调用都会把整个软件卡死，参见 window_watch 里
    // 那段关于 force_repaint 的注释。
    let w = win.clone();
    win.on_window_event(move |event| {
        if matches!(
            event,
            tauri::WindowEvent::Resized(_) | tauri::WindowEvent::ScaleFactorChanged { .. }
        ) {
            crate::window_watch::refresh_corners(&w);
        }
    });
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_the_three_known_tools_have_a_window() {
        for k in ["separate", "train", "tts"] {
            assert!(spec_for(k).is_some());
        }
        // 前端传什么过来都可能，没登记的一律拒绝 —— 否则一个拼错的名字会开出
        // 一扇加载 `#/tool/whatever` 的空白窗，用户以为软件坏了。
        assert!(spec_for("").is_none());
        assert!(spec_for("separate ").is_none());
        assert!(spec_for("../main").is_none());
    }

    #[test]
    fn each_tool_gets_its_own_label_and_fragment() {
        assert_eq!(label_for("tts"), "tool-tts");
        assert!(url_for("tts").ends_with("#/tool/tts"));
        // 三个工具的 label 必须互不相同，否则第二个工具会「复用」第一个的窗口。
        let labels: Vec<String> = ["separate", "train", "tts"].iter().map(|k| label_for(k)).collect();
        let mut uniq = labels.clone();
        uniq.sort();
        uniq.dedup();
        assert_eq!(uniq.len(), labels.len());
    }

    #[test]
    fn a_tool_window_is_never_smaller_than_its_content_needs() {
        for k in ["separate", "train", "tts"] {
            let s = spec_for(k).unwrap();
            assert!(s.min_w <= s.w && s.min_h <= s.h);
        }
    }
}
