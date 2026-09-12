/// Configure every WebView, including floating/tool windows.
pub fn configure(window: &tauri::WebviewWindow) {
    #[cfg(windows)]
    {
        use webview2_com::Microsoft::Web::WebView2::Win32::ICoreWebView2Settings3;
        use windows_core::Interface;
        if let Err(e) = window.with_webview(|webview| unsafe {
            let result = (|| -> windows_core::Result<()> {
                let settings = webview.controller().CoreWebView2()?.Settings()?;
                settings.SetAreDevToolsEnabled(false)?;
                settings
                    .cast::<ICoreWebView2Settings3>()?
                    .SetAreBrowserAcceleratorKeysEnabled(false)?;
                Ok(())
            })();
            if let Err(e) = result {
                crate::logging::shell_log!("WebView keyboard configuration: {e}");
            }
        }) {
            crate::logging::shell_log!("WebView keyboard configuration: {e}");
        }
    }
    #[cfg(not(windows))]
    let _ = window;
}
